import threading
import time
import sys


class MasterMonitor:

    def __init__(self, connection, master_ip):

        self.connection = connection
        self.master_ip = master_ip

        self.running = False
        self.reader_thread = None

    # =====================================================
    # START MASTER MONITOR
    # =====================================================

    def start(self):

        print("\n" + "=" * 70)
        print("              STACK LIVE MONITOR")
        print("=" * 70)

        print(
            f"\nMASTER IP : {self.master_ip}"
        )

        print(
            "UNIT-ID   : 1"
        )

        print(
            "\nConnected to Unit-ID 1 / MASTER."
        )

        print(
            "\nThe switch's own asynchronous logs "
            "will appear here."
        )

        print(
            "You can also enter CLI commands."
        )

        print(
            "\nType 'exit-monitor' to stop monitoring."
        )

        print("=" * 70)

        # -------------------------------------------------
        # Start continuous SSH reader
        # -------------------------------------------------

        self.running = True

        self.reader_thread = threading.Thread(
            target=self._read_switch_output,
            daemon=True
        )

        self.reader_thread.start()

        # -------------------------------------------------
        # Interactive CLI
        # -------------------------------------------------

        self._command_loop()

    # =====================================================
    # CONTINUOUS SWITCH OUTPUT
    # =====================================================

    def _read_switch_output(self):

        while self.running:

            try:

                if not self.connection.shell:

                    time.sleep(0.2)

                    continue

                if self.connection.shell.recv_ready():

                    data = self.connection.shell.recv(
                        65535
                    )

                    if not data:

                        time.sleep(0.1)

                        continue

                    output = data.decode(
                        "utf-8",
                        errors="ignore"
                    )

                    if output:

                        # Print EXACT switch output.
                        #
                        # No parsing.
                        # No fake messages.
                        # No generated status.

                        sys.stdout.write(output)

                        sys.stdout.flush()

                else:

                    time.sleep(0.1)

            except Exception as e:

                if self.running:

                    print(
                        f"\n\n[SSH MONITOR ERROR] {e}"
                    )

                break

    # =====================================================
    # INTERACTIVE COMMAND LINE
    # =====================================================

    def _command_loop(self):

        while self.running:

            try:

                command = input()

                if not command:

                    continue

                # -------------------------------------------------
                # Exit
                # -------------------------------------------------

                if command.strip().lower() == "exit-monitor":

                    print(
                        "\nStopping live monitor..."
                    )

                    self.running = False

                    break

                # -------------------------------------------------
                # Send user's actual command
                # -------------------------------------------------

                self.connection.shell.send(
                    command + "\n"
                )

            except KeyboardInterrupt:

                print(
                    "\n\nStopping live monitor..."
                )

                self.running = False

                break

            except EOFError:

                self.running = False

                break

            except Exception as e:

                print(
                    f"\nCLI error: {e}"
                )

                self.running = False

                break

        # -------------------------------------------------
        # Stop reader
        # -------------------------------------------------

        self.running = False

        if self.reader_thread:

            self.reader_thread.join(
                timeout=2
            )


# =========================================================
# FUNCTION
# =========================================================

def start_master_monitor(
    connection,
    master_ip
):

    monitor = MasterMonitor(
        connection=connection,
        master_ip=master_ip
    )

    monitor.start()