import asyncio
import time
import paramiko
import telnetlib3


class SwitchConnection:

    def __init__(self, connection_type, ip, username, password, port=None):
        self.connection_type = connection_type.lower()
        self.ip = ip
        self.username = username
        self.password = password

        if port:
            self.port = port
        elif self.connection_type == "ssh":
            self.port = 22
        elif self.connection_type == "telnet":
            self.port = 23
        else:
            raise ValueError("Invalid connection type")

        self.ssh = None
        self.shell = None
        self.telnet_reader = None
        self.telnet_writer = None

    # =====================================================
    # CONNECTION HEALTH / RECONNECT
    # =====================================================

    def is_connected(self):
        try:
            if self.connection_type == "ssh":
                if self.ssh is None or self.shell is None:
                    return False
                if getattr(self.shell, "closed", False):
                    return False
                transport = self.ssh.get_transport()
                return transport is not None and transport.is_active()

            if self.connection_type == "telnet":
                return self.telnet_writer is not None

        except Exception:
            return False

        return False

    def reconnect(self, retry_count=1, retry_interval=2):
        """Reconnect using the same object so callers keep the same reference."""
        old_ssh = self.ssh
        old_shell = self.shell
        old_writer = self.telnet_writer

        try:
            if old_shell:
                old_shell.close()
        except Exception:
            pass
        try:
            if old_ssh:
                old_ssh.close()
        except Exception:
            pass
        try:
            if old_writer:
                old_writer.close()
        except Exception:
            pass

        self.ssh = None
        self.shell = None
        self.telnet_reader = None
        self.telnet_writer = None

        for attempt in range(1, retry_count + 1):
            print(
                f"\nReconnect attempt #{attempt} to "
                f"{self.ip}:{self.port} using {self.connection_type.upper()}..."
            )
            try:
                if self.connect():
                    print("Connection restored successfully!")
                    return True
            except Exception as exc:
                print(f"Reconnect failed: {exc}")

            if attempt < retry_count:
                time.sleep(retry_interval)

        return False

    # =====================================================
    # CONNECT
    # =====================================================

    def connect(self):
        if self.connection_type == "ssh":
            return self._connect_ssh()
        elif self.connection_type == "telnet":
            return self._connect_telnet()
        return False

    # =====================================================
    # SSH CONNECT
    # =====================================================

    def _connect_ssh(self):
        try:
            print(
                f"\nConnecting to {self.ip}:{self.port} using SSH..."
            )

            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            self.ssh.connect(
                hostname=self.ip,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=10,
                look_for_keys=False,
                allow_agent=False,
            )

            self.shell = self.ssh.invoke_shell()
            self.shell.settimeout(2)

            time.sleep(1)

            if self.shell.recv_ready():
                self.shell.recv(65535)

            print("SSH connection successful!")
            return True

        except Exception as e:
            print(f"SSH connection failed: {e}")
            try:
                if self.ssh:
                    self.ssh.close()
            except Exception:
                pass
            self.ssh = None
            self.shell = None
            return False

    # =====================================================
    # TELNET CONNECT
    # =====================================================

    def _connect_telnet(self):
        try:
            print(
                f"\nConnecting to {self.ip}:{self.port} using Telnet..."
            )
            asyncio.run(self._telnet_login())
            return True
        except Exception as e:
            print(f"Telnet connection failed: {e}")
            return False

    async def _telnet_login(self):
        (
            self.telnet_reader,
            self.telnet_writer,
        ) = await telnetlib3.open_connection(
            host=self.ip,
            port=self.port,
        )

        output = await self.telnet_reader.read(1000)
        print(output)

        self.telnet_writer.write(self.username + "\r\n")
        await asyncio.sleep(1)
        output = await self.telnet_reader.read(1000)
        print(output)

        self.telnet_writer.write(self.password + "\r\n")
        await asyncio.sleep(2)
        output = await self.telnet_reader.read(2000)
        print(output)

        print("Telnet connection successful!")

    # =====================================================
    # SSH COMMAND
    # =====================================================

    def _send_ssh_command(self, command):
        if self.shell is None or getattr(self.shell, "closed", False):
            raise ConnectionError("SSH shell is closed")

        self.shell.send(command + "\n")
        time.sleep(1)

        output = ""
        try:
            while self.shell.recv_ready():
                data = self.shell.recv(65535)
                if not data:
                    break
                output += data.decode("utf-8", errors="ignore")
        except Exception:
            pass

        return output

    # =====================================================
    # TELNET COMMAND
    # =====================================================

    def _send_telnet_command(self, command):
        return asyncio.run(self._telnet_command(command))

    async def _telnet_command(self, command):
        if self.telnet_writer is None:
            raise ConnectionError("Telnet connection is closed")

        self.telnet_writer.write(command + "\r\n")
        await asyncio.sleep(1)
        return await self.telnet_reader.read(5000)

    # =====================================================
    # SEND COMMAND
    # =====================================================

    def send_command(self, command, retry_on_socket_error=True):
        print(f"\n[>] {command}")

        try:
            if not self.is_connected():
                raise ConnectionError("Socket is closed / connection is not active")

            if self.connection_type == "ssh":
                output = self._send_ssh_command(command)
            else:
                output = self._send_telnet_command(command)

        except Exception as exc:
            message = str(exc)
            print(f"Command execution error: {message}")

            if retry_on_socket_error:
                print("\nConnection is not usable. Reconnecting automatically...")
                if self.reconnect(retry_count=3, retry_interval=2):
                    try:
                        if self.connection_type == "ssh":
                            output = self._send_ssh_command(command)
                        else:
                            output = self._send_telnet_command(command)
                    except Exception as retry_exc:
                        print(f"Command retry failed: {retry_exc}")
                        raise
                else:
                    raise
            else:
                raise

        if output:
            print(output)

        return output

    # =====================================================
    # SEND MULTIPLE COMMANDS
    # =====================================================

    def send_commands(self, commands):
        output = ""
        for command in commands:
            result = self.send_command(command)
            output += result or ""
        return output

    # =====================================================
    # DISCONNECT
    # =====================================================

    def disconnect(self):
        try:
            if self.connection_type == "ssh":
                if self.shell:
                    self.shell.close()
                if self.ssh:
                    self.ssh.close()
            elif self.connection_type == "telnet":
                if self.telnet_writer:
                    self.telnet_writer.close()

            print(f"\nConnection closed: {self.ip}")

        except Exception as e:
            print(f"Disconnect error: {e}")