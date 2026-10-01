import time


class MasterCLI:

    def __init__(self, connection, master_ip):

        self.connection = connection
        self.master_ip = master_ip

        self.prompt = "MASTER# "

    # =====================================================
    # START MASTER CLI
    # =====================================================

    def start(self):

        print("\n" + "=" * 70)
        print("                 MASTER SWITCH")
        print("=" * 70)

        print(
            f"\nMASTER IP : {self.master_ip}"
        )

        print(
            "UNIT-ID   : 1"
        )

        print("\n" + "-" * 70)
        print("          SWITCH BOOT / STACK LOG")
        print("-" * 70)

        # -------------------------------------------------
        # IMPORTANT:
        #
        # Do NOT send:
        #   show logging
        #
        # Do NOT send:
        #   terminal monitor
        #
        # The switch automatically sends its boot/stack
        # messages after login.
        # -------------------------------------------------

        self._read_boot_logs()

        print("\n" + "-" * 70)
        print("              MASTER CLI ACCESS")
        print("-" * 70)

        print(
            "\nConnected to Unit-ID 1 / MASTER."
        )

        print(
            "Enter switch commands normally."
        )

        print(
            "Type 'exit-cli' to exit."
        )

        print("-" * 70)

        # -------------------------------------------------
        # Interactive CLI
        # -------------------------------------------------

        self._command_loop()

    # =====================================================
    # READ AUTOMATIC SWITCH OUTPUT
    # =====================================================

    def _read_boot_logs(self):

        # Give the switch some time to send all
        # boot/stack messages after login.

        time.sleep(3)

        output = ""

        # -------------------------------------------------
        # Read everything currently available
        # -------------------------------------------------

        while self.connection.shell.recv_ready():

            try:

                data = self.connection.shell.recv(
                    65535
                )

            except Exception:

                break

            if not data:

                break

            output += data.decode(
                "utf-8",
                errors="ignore"
            )

            # Small delay so additional switch output
            # can arrive.

            time.sleep(0.1)

        # -------------------------------------------------
        # Display actual switch output
        # -------------------------------------------------

        if output:

            print(
                output.rstrip()
            )

        else:

            print(
                "[No automatic boot log received.]"
            )

    # =====================================================
    # INTERACTIVE MASTER CLI
    # =====================================================

    def _command_loop(self):

        while True:

            try:

                command = input(
                    self.prompt
                ).strip()

                if not command:

                    continue

                # -------------------------------------------------
                # EXIT
                # -------------------------------------------------

                if command.lower() == "exit-cli":

                    print(
                        "\nLeaving MASTER CLI..."
                    )

                    break

                # -------------------------------------------------
                # SEND COMMAND TO MASTER
                # -------------------------------------------------

                self.connection.shell.send(
                    command + "\n"
                )

                # Give switch time to respond

                time.sleep(1)

                # -------------------------------------------------
                # READ COMMAND RESPONSE
                # -------------------------------------------------

                output = ""

                while self.connection.shell.recv_ready():

                    try:

                        data = self.connection.shell.recv(
                            65535
                        )

                    except Exception:

                        break

                    if not data:

                        break

                    output += data.decode(
                        "utf-8",
                        errors="ignore"
                    )

                if output:

                    print(
                        output.rstrip()
                    )

            except KeyboardInterrupt:

                print(
                    "\n\nLeaving MASTER CLI..."
                )

                break

            except Exception as e:

                print(
                    f"\nCLI error: {e}"
                )

                break


# =========================================================
# FUNCTION USED BY MAIN.PY
# =========================================================

def master_cli(connection, master_ip):

    cli = MasterCLI(
        connection=connection,
        master_ip=master_ip
    )

    cli.start()