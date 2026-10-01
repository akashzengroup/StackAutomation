import time
import subprocess

from config import (
    SHOW_STACK_COMMAND,
    STACK_MONITOR_INTERVAL
)


# =========================================================
# HELPER
# =========================================================

def press_enter(message):

    input(
        f"\n{message}\n"
        "Press ENTER to continue..."
    )


# =========================================================
# SHOW STACK
# =========================================================

def show_stack(
    connection
):

    print("\n" + "-" * 60)

    print(
        f"Running: {SHOW_STACK_COMMAND}"
    )

    print("-" * 60)

    try:

        output = connection.send_command(
            SHOW_STACK_COMMAND
        )

        if not output:

            print(
                "\nNo output received."
            )

            return ""

        return output

    except Exception as e:

        print(
            f"\nFailed to execute "
            f"'{SHOW_STACK_COMMAND}': {e}"
        )

        return ""


# =========================================================
# CHECK PING
# =========================================================

def check_ping(
    ip
):

    try:

        result = subprocess.run(

            [
                "ping",
                "-n",
                "1",
                "-w",
                "1000",
                ip
            ],

            stdout=subprocess.DEVNULL,

            stderr=subprocess.DEVNULL
        )

        return result.returncode == 0

    except Exception:

        return False


# =========================================================
# TC1
# STACK MASTER ELECTION
# =========================================================

def test_stack_master_election(
    switches,
    master_connection
):

    print("\n" + "=" * 60)
    print("             TC1 - STACK MASTER ELECTION")
    print("=" * 60)

    print(
        "\nPrecondition / Setup:"
    )

    print(
        "All units powered off; "
        "stack cabling is in place."
    )

    # -----------------------------------------------------
    # STEP 1
    # -----------------------------------------------------

    print(
        "\n1. Boot all members simultaneously."
    )

    press_enter(
        "ASSISTANCE:\n"
        "Boot all stack members simultaneously."
    )

    # -----------------------------------------------------
    # STEP 2
    # -----------------------------------------------------

    print(
        "\n2. Waiting for stack initialization..."
    )

    print(
        "\nThe automation will monitor "
        "Unit-ID 1."
    )

    master_ip = switches[0].ip

    print(
        f"\nUnit-ID 1 IP : {master_ip}"
    )

    timeout = 180

    start_time = time.time()

    while (
        time.time() - start_time
        < timeout
    ):

        if check_ping(master_ip):

            print(
                "\nUnit-ID 1 is reachable."
            )

            break

        print(
            "\rWaiting for Unit-ID 1...",
            end="",
            flush=True
        )

        time.sleep(2)

    else:

        print(
            "\n\nUnit-ID 1 did not become "
            "reachable within timeout."
        )

        print(
            "\nTEST RESULT : FAIL"
        )

        return False

    # -----------------------------------------------------
    # STEP 3
    # -----------------------------------------------------

    print(
        "\n3. Stack initialization completed."
    )

    print(
        "\nASSISTANCE:"
    )

    print(
        "The MASTER SSH session is already "
        "open through the automation."
    )

    print(
        "Run 'show stack' to observe "
        "the election result."
    )

    # -----------------------------------------------------
    # STEP 4
    # -----------------------------------------------------

    output = show_stack(
        master_connection
    )

    if not output:

        print(
            "\nUnable to retrieve stack status."
        )

        print(
            "\nTEST RESULT : FAIL"
        )

        return False

    print(
        "\n4. Observe and record "
        "the election result."
    )

    print(
        "\nASSISTANCE:"
    )

    print(
        "Verify which unit is MASTER "
        "and which unit is BACKUP."
    )

    press_enter(
        "After recording the election result, "
        "press ENTER to finish TC1."
    )

    print("\n" + "=" * 60)
    print("                 TC1 RESULT")
    print("=" * 60)

    print(
        "\nActual 'show stack' output "
        "was captured above."
    )

    print(
        "\nTEST RESULT : VERIFY / PASS"
    )

    return True


# =========================================================
# TC2
# ACTIVE CONTROLLER POWER FAILURE
# =========================================================

def test_controller_power_failure(
    switches,
    master_connection
):

    print("\n" + "=" * 60)
    print(
        "       TC2 - CONTROLLER POWER FAILURE"
    )
    print(
        "              / SWITCHOVER"
    )
    print("=" * 60)

    print(
        "\nPrecondition / Setup:"
    )

    print(
        "Healthy stack; continuous traffic "
        "running through member ports."
    )

    if len(switches) < 2:

        print(
            "\nTC2 requires at least "
            "2 switches."
        )

        return False

    unit1 = switches[0]
    unit2 = switches[1]

    # -----------------------------------------------------
    # STEP 1
    # -----------------------------------------------------

    print(
        "\n1. Verify Unit-1 Controller / "
        "Unit-2 Backup."
    )

    print(
        "\nASSISTANCE:"
    )

    print(
        "Run 'show stack' from the "
        "current MASTER session."
    )

    output = show_stack(
        master_connection
    )

    if not output:

        print(
            "\nUnable to retrieve stack status."
        )

        return False

    press_enter(
        "Confirm Unit-1 is Controller/MASTER "
        "and Unit-2 is Backup."
    )

    # -----------------------------------------------------
    # STEP 2
    # -----------------------------------------------------

    print(
        "\n2. Verify continuous traffic."
    )

    print(
        "\nASSISTANCE:"
    )

    print(
        "Confirm continuous traffic is "
        "running through the member ports."
    )

    press_enter(
        "Confirm traffic is running normally."
    )

    # -----------------------------------------------------
    # STEP 3
    # -----------------------------------------------------

    print(
        "\n3. Disconnect power from "
        "Active/Controller."
    )

    print(
        "\nASSISTANCE:"
    )

    print(
        "Physically disconnect power "
        "from Unit-1."
    )

    press_enter(
        "Disconnect Unit-1 power now, "
        "then press ENTER."
    )

    print(
        "\nUnit-1 power failure acknowledged."
    )

    # -----------------------------------------------------
    # STEP 4
    # -----------------------------------------------------

    print(
        "\n4. Observe switchover."
    )

    print(
        "\nUnit-1 should now become unavailable."
    )

    print(
        "The automation will monitor "
        "Unit-2."
    )

    unit2_up = False

    timeout = 120

    start_time = time.time()

    while (
        time.time() - start_time
        < timeout
    ):

        if check_ping(unit2.ip):

            print(
                "\nUnit-2 is reachable."
            )

            unit2_up = True

            break

        print(
            "\rWaiting for Unit-2...",
            end="",
            flush=True
        )

        time.sleep(
            STACK_MONITOR_INTERVAL
        )

    if not unit2_up:

        print(
            "\n\nUnit-2 did not become "
            "reachable within timeout."
        )

        print(
            "\nTEST RESULT : FAIL"
        )

        return False

    # -----------------------------------------------------
    # STEP 5
    # -----------------------------------------------------

    print(
        "\n5. Verify Unit-2 MASTER/Controller."
    )

    print(
        "\nASSISTANCE:"
    )

    print(
        "The previous Unit-1 session is "
        "expected to be unavailable."
    )

    print(
        f"\nConnecting to Unit-2:"
    )

    print(
        f"IP : {unit2.ip}"
    )

    unit2_connection = None

    try:

        # Import here to avoid circular import
        from connection import SwitchConnection

        unit2_connection = SwitchConnection(

            connection_type=unit1.connection_type,

            ip=unit2.ip,

            username=unit2.username,

            password=unit2.password
        )

        if not unit2_connection.connect():

            print(
                "\nUnable to connect to Unit-2."
            )

            print(
                "\nTEST RESULT : FAIL"
            )

            return False

    except Exception as e:

        print(
            f"\nUnit-2 connection failed: {e}"
        )

        return False

    # -----------------------------------------------------
    # STEP 6
    # -----------------------------------------------------

    print(
        "\n6. Run 'show stack' on Unit-2."
    )

    output = show_stack(
        unit2_connection
    )

    if not output:

        unit2_connection.disconnect()

        print(
            "\nUnable to retrieve stack "
            "status from Unit-2."
        )

        print(
            "\nTEST RESULT : FAIL"
        )

        return False

    print(
        "\nASSISTANCE:"
    )

    print(
        "Verify from the actual 'show stack' "
        "output that Unit-2 is now "
        "MASTER/Controller."
    )

    press_enter(
        "Confirm the Unit-2 switchover "
        "from 'show stack'."
    )

    # -----------------------------------------------------
    # STEP 7
    # -----------------------------------------------------

    print(
        "\n7. Verify traffic after switchover."
    )

    print(
        "\nASSISTANCE:"
    )

    print(
        "Check the continuous traffic "
        "through the member ports."
    )

    print(
        "Verify whether traffic remained "
        "operational or recovered successfully."
    )

    press_enter(
        "After verifying traffic, "
        "press ENTER."
    )

    unit2_connection.disconnect()

    # -----------------------------------------------------
    # RESULT
    # -----------------------------------------------------

    print("\n" + "=" * 60)
    print("                 TC2 RESULT")
    print("=" * 60)

    print(
        "\nUnit-2 was reachable after "
        "Unit-1 power failure."
    )

    print(
        "Final MASTER/Controller role "
        "was displayed by 'show stack'."
    )

    print(
        "\nTEST RESULT : VERIFY / PASS"
    )

    return True


# =========================================================
# STACK TEST MENU
# =========================================================

def stack_test_menu(
    switches,
    master_connection
):

    while True:

        print("\n")
        print("=" * 60)
        print("                 STACK TEST MENU")
        print("=" * 60)

        print(
            "\n1. Stack Master Election"
        )

        print(
            "2. Active Controller Power "
            "Failure / Switchover"
        )

        print(
            "3. Exit"
        )

        print("=" * 60)

        choice = input(
            "\nEnter test case: "
        ).strip()

        # -------------------------------------------------
        # TC1
        # -------------------------------------------------

        if choice == "1":

            test_stack_master_election(
                switches,
                master_connection
            )

        # -------------------------------------------------
        # TC2
        # -------------------------------------------------

        elif choice == "2":

            test_controller_power_failure(
                switches,
                master_connection
            )

        # -------------------------------------------------
        # EXIT
        # -------------------------------------------------

        elif choice == "3":

            print(
                "\nExiting Stack Test Menu."
            )

            break

        else:

            print(
                "\nInvalid choice."
            )