import threading
import time
import sys


class MasterTerminal:

    def __init__(
        self,
        connection,
        master_ip,
        return_after_stack=False
    ):

        self.connection = connection
        self.master_ip = master_ip
        self.return_after_stack = return_after_stack

        self.running = True

        self.reader_thread = None
        self.stack_thread = None

        self.stack_command_sent = threading.Event()

    # =====================================================
    # START
    # =====================================================

    def start(self):

        print()
        print("=" * 70)
        print("                    SWITCH CLI")
        print("=" * 70)

        print(
            f"Connected to Unit-ID 1 / MASTER: "
            f"{self.master_ip}"
        )

        print(
            "Actual switch logs and CLI output "
            "will appear below."
        )

        print("=" * 70)
        print()

        # -------------------------------------------------
        # Reader thread
        # -------------------------------------------------

        self.reader_thread = threading.Thread(
            target=self._read_switch_output,
            daemon=True
        )

        self.reader_thread.start()

        # -------------------------------------------------
        # Request real switch prompt
        # -------------------------------------------------

        time.sleep(0.5)

        try:

            self.connection.shell.send("\n")

        except Exception as e:

            print(
                f"\nUnable to request switch prompt: {e}"
            )

        # -------------------------------------------------
        # Automatic sh stack
        # -------------------------------------------------

        self.stack_thread = threading.Thread(
            target=self._automatic_stack_command,
            daemon=True
        )

        self.stack_thread.start()

        # -------------------------------------------------
        # INITIAL AUTOMATION MODE
        #
        # Wait for automatic sh stack and return to
        # test-case menu.
        #
        # DO NOT close connection.
        # -------------------------------------------------

        if self.return_after_stack:

            self.stack_command_sent.wait()

            # Allow complete switch output
            time.sleep(3)

            print()
            print("=" * 70)
            print("Initial stack verification completed.")
            print("Returning to test case menu...")
            print("Master connection remains active.")
            print("=" * 70)

            self.running = False

            if self.reader_thread:

                self.reader_thread.join(
                    timeout=2
                )

            return

        # -------------------------------------------------
        # Interactive terminal mode
        # -------------------------------------------------

        self._command_loop()

    # =====================================================
    # READ SWITCH OUTPUT
    # =====================================================

    def _read_switch_output(self):

        while self.running:

            try:

                if self.connection.shell is None:

                    time.sleep(0.1)
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

                        sys.stdout.write(output)
                        sys.stdout.flush()

                else:

                    time.sleep(0.1)

            except Exception as e:

                if self.running:

                    print(
                        f"\n[SSH Monitor Error] {e}"
                    )

                break

    # =====================================================
    # AUTOMATIC SHOW STACK
    # =====================================================

    def _automatic_stack_command(self):

        for _ in range(15):

            if not self.running:
                return

            time.sleep(1)

        if not self.running:
            return

        try:

            print()
            print(
                "[Automatic verification] "
                "Running: sh stack"
            )

            self.connection.shell.send(
                "sh stack\n"
            )

            self.stack_command_sent.set()

        except Exception as e:

            print(
                f"\n[Stack command error] {e}"
            )

            self.stack_command_sent.set()

    # =====================================================
    # INTERACTIVE COMMAND LOOP
    # =====================================================

    def _command_loop(self):

        while self.running:

            try:

                command = input()

                if not command:

                    self.connection.shell.send("\n")
                    continue

                if command.strip().lower() == "exit-monitor":

                    self.running = False

                    print(
                        "\nClosing terminal mode."
                    )

                    break

                self.connection.shell.send(
                    command + "\n"
                )

            except KeyboardInterrupt:

                self.running = False

                print(
                    "\n\nClosing terminal mode."
                )

                break

            except EOFError:

                self.running = False
                break

            except Exception as e:

                print(
                    f"\nCommand error: {e}"
                )

                self.running = False
                break

        self.running = False

        if self.reader_thread:

            self.reader_thread.join(
                timeout=2
            )


# =========================================================
# MAIN FUNCTION
# =========================================================

def open_master_terminal(
    master_connection,
    master_ip,
    return_after_stack=False
):

    terminal = MasterTerminal(
        connection=master_connection,
        master_ip=master_ip,
        return_after_stack=return_after_stack
    )

    terminal.start()