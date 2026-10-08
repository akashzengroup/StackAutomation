
import subprocess
import time
import inspect
import re

from connection import SwitchConnection
from stack_config import configure_switch

from reload import (
    reload_all_switches,
    wait_for_reboot
)

from master_terminal import open_master_terminal

from config import (
    WAIT_AFTER_RELOAD,
    DEFAULT_STACK_PORT
)

from tests.tc_stk_001 import run_tc_stk_001
from tests.tc_stk_002 import run_tc_stk_002
from tests.tc_stk_003 import run_tc_stk_003

try:
    from tests.tc_stk_004 import run_tc_stk_004
except ImportError:
    run_tc_stk_004 = None

try:
    from tests.tc_stk_005 import run_tc_stk_005
except ImportError:
    run_tc_stk_005 = None

try:
    from tests.tc_stk_006 import run_tc_stk_006
except ImportError:
    run_tc_stk_006 = None

try:
    from tests.tc_stk_007 import run_tc_stk_007
except ImportError:
    run_tc_stk_007 = None

try:
    from tests.tc_stk_008 import run_tc_stk_008
except ImportError:
    run_tc_stk_008 = None

try:
    from tests.tc_stk_009 import run_tc_stk_009
except ImportError:
    run_tc_stk_009 = None

try:
    from tests.tc_stk_010 import run_tc_stk_010
except ImportError:
    run_tc_stk_010 = None

try:
    from tests.tc_stk_011 import run_tc_stk_011
except ImportError:
    run_tc_stk_011 = None

try:
    from tests.tc_stk_012 import run_tc_stk_012
except ImportError:
    run_tc_stk_012 = None

try:
    from tests.tc_stk_013 import run_tc_stk_013
except ImportError:
    run_tc_stk_013 = None

try:
    from tests.tc_stk_014 import run_tc_stk_014
except ImportError:
    run_tc_stk_014 = None

try:
    from tests.tc_stk_015 import run_tc_stk_015
except ImportError:
    run_tc_stk_015 = None

try:
    from tests.tc_stk_016 import run_tc_stk_016
except ImportError:
    run_tc_stk_016 = None

try:
    from tests.tc_stk_017 import run_tc_stk_017
except ImportError:
    run_tc_stk_017 = None

try:
    from tests.tc_stk_018 import run_tc_stk_018
except ImportError:
    run_tc_stk_018 = None

try:
    from tests.tc_stk_019 import run_tc_stk_019
except ImportError:
    run_tc_stk_019 = None

# =========================================================
# TC-STK-020
# Different Firmware Unit Join / Auto Synchronization
# =========================================================

try:
    from tests.tc_stk_020 import run_tc_stk_020
except ImportError:
    run_tc_stk_020 = None


# =========================================================
# STARTUP MODE
# =========================================================

def get_startup_mode():

    print("\n" + "=" * 70)
    print("                 STARTUP MODE")
    print("=" * 70)
    print()

    print(
        "Is your switch already part of a running stack?"
    )

    print(
        "  Yes -> Connect to Unit-ID 1 and start directly "
        "from test cases"
    )

    print(
        "  No  -> Continue with the normal stack creation flow"
    )

    while True:

        choice = input(
            "\nIs the stack already running? (y/n): "
        ).strip().lower()

        if choice in ("y", "yes"):
            return True

        if choice in ("n", "no"):
            return False

        print(
            "Invalid input. Please enter Y or N."
        )


# =========================================================
# EXISTING STACK DETAILS
# =========================================================

def get_existing_stack_details():

    print("\n" + "=" * 70)
    print("              EXISTING STACK DETAILS")
    print("=" * 70)

    while True:

        try:

            count = int(
                input(
                    "\nCurrent number of stack members: "
                ).strip()
            )

            if count < 2:

                print(
                    "Minimum 2 stack members are required."
                )

                continue

            break

        except ValueError:

            print(
                "Please enter a valid number."
            )

    switch_details = []

    for unit_id in range(1, count + 1):

        print()
        print("-" * 60)

        if unit_id == 1:

            print(
                "                 MASTER / UNIT-1"
            )

        elif unit_id == 2:

            print(
                "                 UNIT-2 / BACKUP"
            )

        else:

            print(
                f"                 UNIT-{unit_id}"
            )

        print("-" * 60)

        if unit_id == 2:

            print(
                "(Required for TC-STK-003 Controller Failover)"
            )

        ip = input(
            "IP Address: "
        ).strip()

        username = input(
            "User Name: "
        ).strip()

        password = input(
            "Password: "
        ).strip()

        switch_details.append({

            "ip": ip,

            "username": username,

            "password": password,

            "unit_id": unit_id
        })

    connection_type = get_connection_type()

    master = switch_details[0]

    return (
        count,
        connection_type,
        switch_details,
        master["ip"],
        master["username"],
        master["password"]
    )


# =========================================================
# GET SWITCH COUNT
# =========================================================

def get_switch_count():

    while True:

        try:

            count = int(
                input(
                    "\nNumber of switches: "
                ).strip()
            )

            if count < 2:

                print(
                    "Minimum 2 switches are required."
                )

                continue

            return count

        except ValueError:

            print(
                "Please enter a valid number."
            )


# =========================================================
# GET PORT TYPE
# =========================================================

def get_port_type():

    print("\nStack Port Type")
    print("1. TE")
    print("2. HU")
    print("3. TF")

    while True:

        choice = input(
            "\nEnter port type: "
        ).strip().lower()

        if choice in ("1", "te"):

            return "te"

        elif choice in ("2", "hu"):

            return "hu"

        elif choice in ("3", "tf"):

            return "tf"

        else:

            print(
                "Invalid choice. Enter TE, HU or TF."
            )


# =========================================================
# GET STACK PORT
# =========================================================

def get_stack_port():

    port = input(
        f"\nStack Port (default {DEFAULT_STACK_PORT}): "
    ).strip()

    return (
        port
        if port
        else DEFAULT_STACK_PORT
    )


# =========================================================
# GET CONNECTION TYPE
# =========================================================

def get_connection_type():

    print("\nConnection Type")
    print("1. SSH")
    print("2. Telnet")

    while True:

        choice = input(
            "\nEnter your choice: "
        ).strip()

        if choice == "1":

            return "ssh"

        elif choice == "2":

            return "telnet"

        else:

            print(
                "Invalid choice."
            )


# =========================================================
# PING HOST
# =========================================================

def ping_host(ip):

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
# WAIT FOR UNIT-ID 1
# =========================================================

def wait_for_master(master_ip):

    print("\n" + "=" * 70)
    print("           WAITING FOR UNIT-ID 1")
    print("=" * 70)

    print(
        f"\nMASTER IP : {master_ip}"
    )

    print(
        "\nStarting ping check..."
    )

    while True:

        try:

            if ping_host(master_ip):

                print(
                    "\n\nUnit-ID 1 is UP!"
                )

                print(
                    f"MASTER {master_ip} is responding."
                )

                return True

            print(
                f"\rWaiting for {master_ip}...",
                end="",
                flush=True
            )

            time.sleep(2)

        except KeyboardInterrupt:

            print(
                "\n\nMaster detection stopped."
            )

            return False


# =========================================================
# CONNECT TO MASTER
# =========================================================

def connect_to_master(
    master_ip,
    master_username,
    master_password,
    connection_type,
    retry_interval=5
):

    print("\n" + "=" * 70)
    print("              CONNECTING TO MASTER")
    print("=" * 70)

    attempt = 0

    while True:

        attempt += 1

        port = (
            22
            if connection_type == "ssh"
            else 23
        )

        print(
            f"\nConnection attempt #{attempt}"
        )

        print(
            f"Connecting to {master_ip}:{port} "
            f"using {connection_type.upper()}..."
        )

        try:

            master_connection = SwitchConnection(
                connection_type=connection_type,
                ip=master_ip,
                username=master_username,
                password=master_password
            )

            if master_connection.connect():

                print(
                    "\nUnit-ID 1 / MASTER connected."
                )

                return master_connection

            print(
                "\nMaster SSH/Telnet service is "
                "not ready yet."
            )

        except Exception as e:

            print(
                f"\nConnection attempt failed: {e}"
            )

        print(
            f"Retrying in {retry_interval} seconds..."
        )

        time.sleep(
            retry_interval
        )


# =========================================================
# SEND COMMAND FOR STACK READINESS CHECK
# =========================================================

def _send_stack_check_command(
    connection,
    command="sh stack"
):

    if connection is None:

        return ""

    try:

        # -------------------------------------------------
        # Preferred send_command()
        # -------------------------------------------------

        if hasattr(
            connection,
            "send_command"
        ):

            try:

                output = connection.send_command(
                    command,
                    timeout=15
                )

            except TypeError:

                output = connection.send_command(
                    command
                )

            if output is None:

                return ""

            return str(output)

        # -------------------------------------------------
        # Fallback send()
        # -------------------------------------------------

        if hasattr(
            connection,
            "send"
        ):

            output = connection.send(
                command
            )

            if output is None:

                return ""

            return str(output)

        # -------------------------------------------------
        # Fallback execute()
        # -------------------------------------------------

        if hasattr(
            connection,
            "execute"
        ):

            output = connection.execute(
                command
            )

            if output is None:

                return ""

            return str(output)

    except Exception:

        return ""

    return ""


# =========================================================
# PARSE STACK UNIT IDs
# =========================================================

def _get_detected_stack_unit_ids(
    output
):

    detected_units = set()

    if not output:

        return detected_units

    for line in output.splitlines():

        line = line.strip()

        if not line:

            continue

        match = re.match(
            r"^(\d+)\s+"
            r"([0-9A-Fa-f]{2}:"
            r"[0-9A-Fa-f]{2}:"
            r"[0-9A-Fa-f]{2}:"
            r"[0-9A-Fa-f]{2}:"
            r"[0-9A-Fa-f]{2}:"
            r"[0-9A-Fa-f]{2})"
            r"\s+",
            line
        )

        if match:

            try:

                unit_id = int(
                    match.group(1)
                )

            except ValueError:

                continue

            if 1 <= unit_id <= 64:

                detected_units.add(
                    unit_id
                )

    return detected_units


# =========================================================
# WAIT FOR COMPLETE STACK
# =========================================================

def wait_for_complete_stack(
    master_connection,
    expected_members,
    timeout=600,
    poll_interval=5
):

    if master_connection is None:

        print(
            "\nERROR: MASTER connection "
            "is not available."
        )

        return False

    if expected_members is None:

        return True

    try:

        expected_members = int(
            expected_members
        )

    except (
        TypeError,
        ValueError
    ):

        print(
            "\nERROR: Invalid expected "
            "stack member count."
        )

        return False

    if expected_members < 1:

        return False

    print("\n" + "=" * 70)
    print("          WAITING FOR COMPLETE STACK")
    print("=" * 70)

    print()

    print(
        f"Expected stack members : "
        f"{expected_members}"
    )

    print()

    print(
        "Unit-ID 1 is UP, but the script will"
    )

    print(
        "wait until ALL expected stack members"
    )

    print(
        "appear in 'sh stack'."
    )

    print()

    print(
        "Partial stack output will not be shown."
    )

    print()

    start_time = time.time()

    last_detected_count = -1

    expected_units = set(
        range(
            1,
            expected_members + 1
        )
    )

    while True:

        elapsed = int(
            time.time() - start_time
        )

        if elapsed >= timeout:

            print()
            print()

            print("=" * 70)
            print("          STACK WAIT TIMEOUT")
            print("=" * 70)

            print()

            print(
                f"Expected stack members : "
                f"{expected_members}"
            )

            print(
                f"Last detected members  : "
                f"{max(last_detected_count, 0)}"
            )

            print()

            print(
                "The MASTER is reachable, but the "
                "complete stack was not detected."
            )

            print()

            print(
                "Initial MASTER terminal will "
                "not be opened."
            )

            return False

        try:

            output = _send_stack_check_command(
                master_connection,
                "sh stack"
            )

            detected_units = (
                _get_detected_stack_unit_ids(
                    output
                )
            )

            expected_detected = (
                expected_units.intersection(
                    detected_units
                )
            )

            detected_count = len(
                expected_detected
            )

            if (
                detected_count
                != last_detected_count
            ):

                print(
                    f"\rDetected stack members : "
                    f"{detected_count}/"
                    f"{expected_members}",
                    end="",
                    flush=True
                )

                last_detected_count = (
                    detected_count
                )

            if (
                expected_units.issubset(
                    detected_units
                )
            ):

                print()
                print()

                print("=" * 70)
                print(
                    "             COMPLETE STACK DETECTED"
                )
                print("=" * 70)

                print()

                print(
                    f"Expected members : "
                    f"{expected_members}"
                )

                print(
                    "Detected Unit-IDs : "
                    + ", ".join(
                        str(unit)
                        for unit in sorted(
                            expected_detected
                        )
                    )
                )

                print()

                print(
                    "All stack members are now visible."
                )

                print(
                    "Proceeding with MASTER terminal..."
                )

                print()

                return True

        except Exception:

            print(
                f"\rWaiting for complete stack... "
                f"{elapsed}s",
                end="",
                flush=True
            )

        time.sleep(
            poll_interval
        )


# =========================================================
# INITIAL MASTER TERMINAL
# =========================================================

def open_initial_master_terminal(
    master_connection,
    master_ip,
    expected_members=None
):

    print("\n" + "=" * 70)
    print("          OPENING UNIT-ID 1 TERMINAL")
    print("=" * 70)

    print()

    print(
        "Unit-ID 1 is reachable."
    )

    print(
        "Before opening the MASTER terminal,"
    )

    print(
        "the script will verify that the complete"
    )

    print(
        "stack is available."
    )

    print()

    print(
        "MASTER connection will remain active."
    )

    if not wait_for_complete_stack(
        master_connection=master_connection,
        expected_members=expected_members
    ):

        print()

        print(
            "ERROR: Complete stack was not detected."
        )

        print(
            "Initial MASTER terminal will not be opened."
        )

        return False

    print(
        "\nOpening MASTER terminal..."
    )

    print(
        "\nThe terminal will automatically run "
        "'sh stack' after 15 seconds."
    )

    print(
        "After initial stack verification, "
        "control will return to the test case menu."
    )

    print(
        "\nMASTER connection will remain active."
    )

    open_master_terminal(
        master_connection=master_connection,
        master_ip=master_ip,
        return_after_stack=True
    )

    return True


# =========================================================
# SAFE TEST CASE RUNNER
# =========================================================

def run_test_case_safely(
    test_function,
    available_arguments
):

    try:

        signature = inspect.signature(
            test_function
        )

        parameters = signature.parameters

        kwargs = {}

        for name, value in available_arguments.items():

            if name in parameters:

                kwargs[name] = value

        missing = []

        for name, parameter in parameters.items():

            if (
                parameter.kind in (
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.KEYWORD_ONLY
                )
                and parameter.default
                is inspect.Parameter.empty
                and name not in kwargs
            ):

                missing.append(
                    name
                )

        if missing:

            print()

            print(
                "Test case function is missing "
                "required parameters:"
            )

            for item in missing:

                print(
                    f"  - {item}"
                )

            print()

            return False

        return test_function(
            **kwargs
        )

    except Exception as e:

        print()

        print(
            f"TC execution error: {e}"
        )

        return False


# =========================================================
# RESULT DISPLAY
# =========================================================

def display_result(
    tc_id,
    result
):

    print()

    print("=" * 70)
    print("                 TEST CASE RESULT")
    print("=" * 70)

    print()

    print(
        f"{tc_id} : "
        + (
            "PASS"
            if result
            else "FAIL"
        )
    )

    print()

    print(
        "MASTER connection remains available for the test case."
    )


# =========================================================
# UPDATE MASTER CONNECTION FROM TEST RESULT
# =========================================================

def _consume_connection_result(
    current_connection,
    test_result
):

    if (
        hasattr(test_result, "connect")
        and hasattr(test_result, "send_command")
    ):

        return (
            test_result,
            True
        )

    return (
        current_connection,
        bool(test_result)
    )


# =========================================================
# TEST CASE MENU
# =========================================================

def test_case_menu(
    master_connection,
    master_ip,
    master_username,
    master_password,
    connection_type,
    expected_members,
    switch_details
):

    while True:

        # -------------------------------------------------
        # Keep Unit-1 credentials synchronized
        # -------------------------------------------------

        unit1 = switch_details[0]

        unit1_ip = unit1["ip"]
        unit1_username = unit1["username"]
        unit1_password = unit1["password"]

        unit2 = switch_details[1]

        unit2_ip = unit2["ip"]
        unit2_username = unit2["username"]
        unit2_password = unit2["password"]

        # -------------------------------------------------
        # MENU
        # -------------------------------------------------

        print()

        print("=" * 70)
        print("                    TEST CASE MENU")
        print("=" * 70)

        print()

        print(
            "1. TC-STK-001 - Create New Stack"
        )

        print(
            "2. TC-STK-002 - Member Number "
            "(Unit-ID) Assignment"
        )

        print(
            "3. TC-STK-003 - Controller Failover"
        )

        print(
            "4. TC-STK-004 - Add Member to Running Stack"
        )

        print(
            "5. TC-STK-005 - Remove Non-Master Member"
        )

        print(
            "6. TC-STK-006 - VLAN Configuration Persistence"
        )

        print(
            "7. TC-STK-007 - Host Connectivity "
            "Through Stack Members"
        )

        print(
            "8. TC-STK-008 - STP Redundant Link Convergence"
        )

        print(
            "9. TC-STK-009 - LACP Port-Channel / "
            "LAG Across Stack Units"
        )

        print(
            "10. TC-STK-010 - LAG Traffic Failover"
        )

        print(
            "11. TC-STK-011 - Stack Software Upgrade "
            "& Member Verification"
        )

        print(
            "12. TC-STK-012 - Reload Entire Stack & Verify"
        )

        print(
            "13. TC-STK-013 - Reboot One Non-Master "
            "Member & Verify Rejoin"
        )

        print(
            "14. TC-STK-014 - Maximum Stack Members "
            "Soak Test"
        )

        print(
            "15. TC-STK-015 - Maximum VLANs "
            "Forwarding & Synchronization"
        )

        print(
            "16. TC-STK-016 - SNMP Configuration + SNMP Walk"
        )

        print(
            "17. TC-STK-017 - Stack Event Log Verification"
        )

        print(
            "18. TC-STK-018 - Multiple Stack Link Failure"
        )

        print(
            "19. TC-STK-019 - Different-Model Unit Join"
        )

        print(
            "20. TC-STK-020 - Different Firmware Unit Join / "
            "Auto Synchronization"
        )

        print(
            "21. Open MASTER Terminal"
        )

        print(
            "22. Exit"
        )

        print()

        choice = input(
            "Select test case: "
        ).strip()

        # =================================================
        # COMMON ARGUMENTS
        # =================================================

        common_arguments = {

            "master_connection":
                master_connection,

            "connection":
                master_connection,

            "master_ip":
                master_ip,

            "master_username":
                master_username,

            "master_password":
                master_password,

            "username":
                master_username,

            "password":
                master_password,

            "connection_type":
                connection_type,

            "expected_members":
                expected_members,

            "member_count":
                expected_members,

            "switch_count":
                expected_members,

            "expected_units":
                expected_members,

            "unit1_ip":
                unit1_ip,

            "unit1_username":
                unit1_username,

            "unit1_password":
                unit1_password,

            "unit2_ip":
                unit2_ip,

            "unit2_username":
                unit2_username,

            "unit2_password":
                unit2_password,

            "backup_ip":
                unit2_ip,

            "backup_username":
                unit2_username,

            "backup_password":
                unit2_password,

            "switch_details":
                switch_details,
        }

        # =================================================
        # TC-STK-001
        # =================================================

        if choice == "1":

            print(
                "\n" + "=" * 70
            )

            print(
                "              STARTING TC-STK-001"
            )

            print(
                "=" * 70
            )

            result = run_test_case_safely(
                run_tc_stk_001,
                common_arguments
            )

            display_result(
                "TC-STK-001",
                result
            )

        # =================================================
        # TC-STK-002
        # =================================================

        elif choice == "2":

            print(
                "\n" + "=" * 70
            )

            print(
                "              STARTING TC-STK-002"
            )

            print(
                "=" * 70
            )

            tc_result = run_test_case_safely(
                run_tc_stk_002,
                common_arguments
            )

            master_connection, result = _consume_connection_result(
                master_connection,
                tc_result
            )

            display_result(
                "TC-STK-002",
                result
            )

        # =================================================
        # TC-STK-003
        # =================================================

        elif choice == "3":

            print(
                "\n" + "=" * 70
            )

            print(
                "              STARTING TC-STK-003"
            )

            print(
                "=" * 70
            )

            print()

            print(
                "Unit-1 / Controller:"
            )

            print(
                f"  IP       : {unit1_ip}"
            )

            print(
                f"  Username : {unit1_username}"
            )

            print()

            print(
                "Unit-2 / Backup:"
            )

            print(
                f"  IP       : {unit2_ip}"
            )

            print(
                f"  Username : {unit2_username}"
            )

            print()

            tc_result = run_test_case_safely(
                run_tc_stk_003,
                common_arguments
            )

            master_connection, result = _consume_connection_result(
                master_connection,
                tc_result
            )

            display_result(
                "TC-STK-003",
                result
            )

        # =================================================
        # TC-STK-004
        # =================================================

        elif choice == "4":

            print(
                "\n" + "=" * 70
            )

            print(
                "              STARTING TC-STK-004"
            )

            print(
                "=" * 70
            )

            if run_tc_stk_004 is None:

                print(
                    "\nERROR: tests/tc_stk_004.py "
                    "was not found."
                )

                result = False

            else:

                result = run_test_case_safely(
                    run_tc_stk_004,
                    common_arguments
                )

            display_result(
                "TC-STK-004",
                result
            )

        # =================================================
        # TC-STK-005
        # =================================================

        elif choice == "5":

            print(
                "\n" + "=" * 70
            )

            print(
                "              STARTING TC-STK-005"
            )

            print(
                "=" * 70
            )

            if run_tc_stk_005 is None:

                print(
                    "\nERROR: tests/tc_stk_005.py "
                    "was not found."
                )

                result = False

            else:

                result = run_test_case_safely(
                    run_tc_stk_005,
                    common_arguments
                )

            display_result(
                "TC-STK-005",
                result
            )

        # =================================================
        # TC-STK-006
        # =================================================

        elif choice == "6":

            print(
                "\n" + "=" * 70
            )

            print(
                "              STARTING TC-STK-006"
            )

            print(
                "=" * 70
            )

            if run_tc_stk_006 is None:

                print(
                    "\nERROR: tests/tc_stk_006.py "
                    "was not found."
                )

                result = False

            else:

                result = run_test_case_safely(
                    run_tc_stk_006,
                    common_arguments
                )

            display_result(
                "TC-STK-006",
                result
            )

        # =================================================
        # TC-STK-007
        # =================================================

        elif choice == "7":

            print(
                "\n" + "=" * 70
            )

            print(
                "              STARTING TC-STK-007"
            )

            print(
                "=" * 70
            )

            if run_tc_stk_007 is None:

                print(
                    "\nERROR: tests/tc_stk_007.py "
                    "was not found."
                )

                result = False

            else:

                result = run_test_case_safely(
                    run_tc_stk_007,
                    common_arguments
                )

            display_result(
                "TC-STK-007",
                result
            )

        # =================================================
        # TC-STK-008
        # =================================================

        elif choice == "8":

            print(
                "\n" + "=" * 70
            )

            print(
                "              STARTING TC-STK-008"
            )

            print(
                "=" * 70
            )

            if run_tc_stk_008 is None:

                print(
                    "\nERROR: tests/tc_stk_008.py "
                    "was not found."
                )

                result = False

            else:

                result = run_test_case_safely(
                    run_tc_stk_008,
                    common_arguments
                )

            display_result(
                "TC-STK-008",
                result
            )

        # =================================================
        # TC-STK-009
        # =================================================

        elif choice == "9":

            print(
                "\n" + "=" * 70
            )

            print(
                "              STARTING TC-STK-009"
            )

            print(
                "=" * 70
            )

            if run_tc_stk_009 is None:

                print(
                    "\nERROR: tests/tc_stk_009.py "
                    "was not found."
                )

                result = False

            else:

                result = run_test_case_safely(
                    run_tc_stk_009,
                    common_arguments
                )

            display_result(
                "TC-STK-009",
                result
            )

        # =================================================
        # TC-STK-010
        # =================================================

        elif choice == "10":

            print(
                "\n" + "=" * 70
            )

            print(
                "              STARTING TC-STK-010"
            )

            print(
                "=" * 70
            )

            if run_tc_stk_010 is None:

                print(
                    "\nERROR: tests/tc_stk_010.py "
                    "was not found."
                )

                result = False

            else:

                result = run_test_case_safely(
                    run_tc_stk_010,
                    common_arguments
                )

            display_result(
                "TC-STK-010",
                result
            )

        # =================================================
        # TC-STK-011
        # =================================================

        elif choice == "11":

            print(
                "\n" + "=" * 70
            )

            print(
                "              STARTING TC-STK-011"
            )

            print(
                "=" * 70
            )

            if run_tc_stk_011 is None:

                print(
                    "\nERROR: tests/tc_stk_011.py "
                    "was not found."
                )

                result = False

            else:

                result = run_test_case_safely(
                    run_tc_stk_011,
                    common_arguments
                )

            display_result(
                "TC-STK-011",
                result
            )

        # =================================================
        # TC-STK-012
        # =================================================

        elif choice == "12":

            print(
                "\n" + "=" * 70
            )

            print(
                "              STARTING TC-STK-012"
            )

            print(
                "=" * 70
            )

            if run_tc_stk_012 is None:

                print(
                    "\nERROR: tests/tc_stk_012.py "
                    "was not found."
                )

                result = False

            else:

                tc_result = run_test_case_safely(
                    run_tc_stk_012,
                    common_arguments
                )

                if (
                    tc_result is not False
                    and tc_result is not None
                ):

                    master_connection = (
                        tc_result
                    )

                    result = True

                    print()

                    print(
                        "New Unit-ID 1 / MASTER "
                        "connection is now active."
                    )

                else:

                    result = False

            display_result(
                "TC-STK-012",
                result
            )

        # =================================================
        # TC-STK-013
        # =================================================

        elif choice == "13":

            print(
                "\n" + "=" * 70
            )

            print(
                "              STARTING TC-STK-013"
            )

            print(
                "=" * 70
            )

            if run_tc_stk_013 is None:

                print(
                    "\nERROR: tests/tc_stk_013.py "
                    "was not found."
                )

                result = False

            else:

                tc_result = run_test_case_safely(
                    run_tc_stk_013,
                    common_arguments
                )

                if (
                    tc_result is not False
                    and tc_result is not None
                ):

                    if hasattr(
                        tc_result,
                        "connect"
                    ):

                        master_connection = (
                            tc_result
                        )

                    result = True

                else:

                    result = False

            display_result(
                "TC-STK-013",
                result
            )

        # =================================================
        # TC-STK-014
        # =================================================

        elif choice == "14":

            print(
                "\n" + "=" * 70
            )

            print(
                "              STARTING TC-STK-014"
            )

            print(
                "=" * 70
            )

            if run_tc_stk_014 is None:

                print(
                    "\nERROR: tests/tc_stk_014.py "
                    "was not found."
                )

                result = False

            else:

                result = run_test_case_safely(
                    run_tc_stk_014,
                    common_arguments
                )

            display_result(
                "TC-STK-014",
                result
            )

        # =================================================
        # TC-STK-015
        # =================================================

        elif choice == "15":

            print(
                "\n" + "=" * 70
            )

            print(
                "              STARTING TC-STK-015"
            )

            print(
                "=" * 70
            )

            if run_tc_stk_015 is None:

                print(
                    "\nERROR: tests/tc_stk_015.py "
                    "was not found."
                )

                result = False

            else:

                result = run_test_case_safely(
                    run_tc_stk_015,
                    common_arguments
                )

            display_result(
                "TC-STK-015",
                result
            )

        # =================================================
        # TC-STK-016
        # =================================================

        elif choice == "16":

            print(
                "\n" + "=" * 70
            )

            print(
                "              STARTING TC-STK-016"
            )

            print(
                "=" * 70
            )

            if run_tc_stk_016 is None:

                print(
                    "\nERROR: tests/tc_stk_016.py "
                    "was not found."
                )

                result = False

            else:

                result = run_test_case_safely(
                    run_tc_stk_016,
                    common_arguments
                )

            display_result(
                "TC-STK-016",
                result
            )

        # =================================================
        # TC-STK-017
        # =================================================

        elif choice == "17":

            print(
                "\n" + "=" * 70
            )

            print(
                "              STARTING TC-STK-017"
            )

            print(
                "=" * 70
            )

            if run_tc_stk_017 is None:

                print(
                    "\nERROR: tests/tc_stk_017.py "
                    "was not found."
                )

                result = False

            else:

                tc_result = run_test_case_safely(
                    run_tc_stk_017,
                    common_arguments
                )

                master_connection, result = _consume_connection_result(
                    master_connection,
                    tc_result
                )

            display_result(
                "TC-STK-017",
                result
            )

        # =================================================
        # TC-STK-018
        # =================================================

        elif choice == "18":

            print(
                "\n" + "=" * 70
            )

            print(
                "              STARTING TC-STK-018"
            )

            print(
                "=" * 70
            )

            if run_tc_stk_018 is None:

                print(
                    "\nERROR: tests/tc_stk_018.py "
                    "was not found."
                )

                result = False

            else:

                common_arguments["master_connection"] = (
                    master_connection
                )

                common_arguments["connection"] = (
                    master_connection
                )

                tc_result = run_test_case_safely(
                    run_tc_stk_018,
                    common_arguments
                )

                master_connection, result = _consume_connection_result(
                    master_connection,
                    tc_result
                )

            display_result(
                "TC-STK-018",
                result
            )

        # =================================================
        # TC-STK-019
        # Different-Model Unit Join
        # =================================================

        elif choice == "19":

            print(
                "\n" + "=" * 70
            )

            print(
                "              STARTING TC-STK-019"
            )

            print(
                "=" * 70
            )

            if run_tc_stk_019 is None:

                print(
                    "\nERROR: tests/tc_stk_019.py "
                    "was not found."
                )

                result = False

            else:

                # -------------------------------------------------
                # Use the existing Unit-1 / MASTER connection.
                #
                # TC-STK-019 will:
                #
                #   1. Check the existing stack.
                #   2. Ask the user to configure the different-
                #      model switch.
                #   3. Ask the user to reload the new switch.
                #   4. Poll "do show stack" from Unit 1.
                #   5. Poll every 5 seconds.
                #   6. PASS when the new Unit-ID appears.
                # -------------------------------------------------

                common_arguments["master_connection"] = (
                    master_connection
                )

                common_arguments["connection"] = (
                    master_connection
                )

                tc_result = run_test_case_safely(
                    run_tc_stk_019,
                    common_arguments
                )

                master_connection, result = _consume_connection_result(
                    master_connection,
                    tc_result
                )

            display_result(
                "TC-STK-019",
                result
            )

        # =================================================
        # TC-STK-020
        # Different-Firmware Unit Join /
        # Auto Synchronization
        # =================================================

        elif choice == "20":

            print(
                "\n" + "=" * 70
            )

            print(
                "              STARTING TC-STK-020"
            )

            print(
                "=" * 70
            )

            if run_tc_stk_020 is None:

                print(
                    "\nERROR: tests/tc_stk_020.py "
                    "was not found."
                )

                result = False

            else:

                # -------------------------------------------------
                # Use the existing Unit-1 / MASTER connection.
                #
                # TC-STK-020 will:
                #
                #   1. Read the existing stack information.
                #   2. Read the current firmware version.
                #   3. Determine the next available Unit-ID.
                #   4. Ask for the new switch credentials.
                #   5. Verify the new switch has a different
                #      firmware version.
                #   6. Automatically configure the new switch.
                #   7. Reload the new switch.
                #   8. Monitor relevant stack/firmware logs
                #      while the join/synchronization happens.
                #   9. Verify the new Unit-ID joins the stack.
                #  10. Verify firmware synchronization.
                #
                # The TC itself handles the parallel log
                # monitoring. Only relevant logs generated
                # during this process should be displayed.
                # -------------------------------------------------

                common_arguments["master_connection"] = (
                    master_connection
                )

                common_arguments["connection"] = (
                    master_connection
                )

                tc_result = run_test_case_safely(
                    run_tc_stk_020,
                    common_arguments
                )

                master_connection, result = _consume_connection_result(
                    master_connection,
                    tc_result
                )

            display_result(
                "TC-STK-020",
                result
            )

        # =================================================
        # MASTER TERMINAL
        # =================================================

        elif choice == "21":

            print(
                "\n" + "=" * 70
            )

            print(
                "              MASTER TERMINAL"
            )

            print(
                "=" * 70
            )

            print()

            open_master_terminal(
                master_connection=master_connection,
                master_ip=master_ip,
                return_after_stack=False
            )

            print()

            print(
                "Returned from MASTER terminal."
            )

            print(
                "MASTER connection remains active."
            )

        # =================================================
        # EXIT
        # =================================================

        elif choice == "22":

            print(
                "\n" + "=" * 70
            )

            print(
                "                 EXITING"
            )

            print(
                "=" * 70
            )

            print()

            print(
                "Test case menu closed."
            )

            print(
                "MASTER connection remains available."
            )

            print()

            return

        else:

            print()

            print(
                "Invalid selection."
            )

            print(
                "Please select 1 to 22."
            )


# =========================================================
# MAIN
# =========================================================

def main():

    print(
        "=" * 70
    )

    print(
        "             SWITCH STACK AUTOMATION"
    )

    print(
        "=" * 70
    )

    existing_stack = get_startup_mode()

    # =====================================================
    # EXISTING STACK MODE
    # =====================================================

    if existing_stack:

        (
            switch_count,
            connection_type,
            switch_details,
            master_ip,
            master_username,
            master_password
        ) = get_existing_stack_details()

        print(
            "\n" + "=" * 70
        )

        print(
            "          EXISTING STACK MODE SELECTED"
        )

        print(
            "=" * 70
        )

        print()

        print(
            "No stack configuration or reload "
            "will be performed."
        )

        print(
            "The script will connect to Unit-ID 1 "
            "and verify the running stack."
        )

        master_connection = connect_to_master(
            master_ip=master_ip,
            master_username=master_username,
            master_password=master_password,
            connection_type=connection_type
        )

        if master_connection is None:

            print(
                "\nUnable to connect to "
                "Unit-ID 1 / MASTER."
            )

            return

        terminal_opened = (
            open_initial_master_terminal(
                master_connection=master_connection,
                master_ip=master_ip,
                expected_members=switch_count
            )
        )

        if not terminal_opened:

            print()

            print(
                "Complete stack was not detected."
            )

            print(
                "Automation stopped before "
                "test-case menu."
            )

            return

        test_case_menu(
            master_connection=master_connection,
            master_ip=master_ip,
            master_username=master_username,
            master_password=master_password,
            connection_type=connection_type,
            expected_members=switch_count,
            switch_details=switch_details
        )

        print(
            "\n" + "=" * 70
        )

        print(
            "             AUTOMATION COMPLETED"
        )

        print(
            "=" * 70
        )

        print()

        print(
            "MASTER connection remains available."
        )

        print(
            "No automatic connection close "
            "was performed."
        )

        return

    # =====================================================
    # NEW STACK MODE
    # =====================================================

    switch_count = get_switch_count()

    port_type = get_port_type()

    stack_port = get_stack_port()

    connection_type = get_connection_type()

    switch_details = []

    print(
        "\n" + "=" * 70
    )

    print(
        "              SWITCH INFORMATION"
    )

    print(
        "=" * 70
    )

    for switch_number in range(
        1,
        switch_count + 1
    ):

        print()

        print(
            "-" * 60
        )

        print(
            f"                 SWITCH "
            f"{switch_number}"
        )

        print(
            "-" * 60
        )

        ip = input(
            "\nIP Address: "
        ).strip()

        username = input(
            "User Name: "
        ).strip()

        password = input(
            "Password: "
        ).strip()

        switch_details.append({

            "ip": ip,

            "username": username,

            "password": password,

            "unit_id": switch_number
        })

    # =====================================================
    # SHOW CONFIGURATION
    # =====================================================

    print(
        "\n" + "=" * 70
    )

    print(
        "                CONFIGURATION"
    )

    print(
        "=" * 70
    )

    print()

    print(
        f"Number of switches : {switch_count}"
    )

    print(
        f"Port Type          : "
        f"{port_type.upper()}"
    )

    print(
        f"Stack Port         : {stack_port}"
    )

    print(
        f"Connection Type    : "
        f"{connection_type.upper()}"
    )

    for switch in switch_details:

        print()

        print(
            f"Switch {switch['unit_id']}"
        )

        print(
            f"  IP      : {switch['ip']}"
        )

        print(
            f"  Unit-ID : {switch['unit_id']}"
        )

        print(
            f"  Stack   : "
            f"{port_type}{stack_port}"
        )

    confirm = input(
        "\nProceed? (y/n): "
    ).strip().lower()

    if confirm != "y":

        print(
            "\nCancelled."
        )

        return

    # =====================================================
    # CREATE CONNECTION OBJECTS
    # =====================================================

    switches = []

    for switch in switch_details:

        connection = SwitchConnection(

            connection_type=connection_type,

            ip=switch["ip"],

            username=switch["username"],

            password=switch["password"]
        )

        switches.append(
            connection
        )

    # =====================================================
    # CONFIGURE ALL SWITCHES
    # =====================================================

    print(
        "\n" + "=" * 70
    )

    print(
        "             CONFIGURING SWITCHES"
    )

    print(
        "=" * 70
    )

    for index, connection in enumerate(
        switches,
        start=1
    ):

        print()

        print(
            "-" * 60
        )

        print(
            f"                 SWITCH {index}"
        )

        print(
            "-" * 60
        )

        if not connection.connect():

            print(
                f"\nSwitch {index} "
                "connection FAILED."
            )

            return

        print(
            f"\nSwitch {index} connected."
        )

        result = configure_switch(
            connection=connection,
            unit_id=index,
            port_type=port_type,
            stack_port=stack_port
        )

        if not result:

            print(
                f"\nSwitch {index} "
                "configuration FAILED."
            )

            return

        print(
            f"\nSwitch {index} "
            "configuration completed."
        )

    # =====================================================
    # ALL SWITCHES CONFIGURED
    # =====================================================

    print(
        "\n" + "=" * 70
    )

    print(
        "          ALL SWITCHES CONFIGURED"
    )

    print(
        "=" * 70
    )

    # =====================================================
    # RELOAD ALL SWITCHES
    # =====================================================

    print(
        "\n" + "=" * 70
    )

    print(
        "           RELOADING ALL SWITCHES"
    )

    print(
        "=" * 70
    )

    if not reload_all_switches(
        switches
    ):

        print(
            "\nReload operation FAILED."
        )

        return

    print(
        "\nReload command sent to ALL switches."
    )

    wait_for_reboot(
        WAIT_AFTER_RELOAD
    )

    # =====================================================
    # UNIT-1 / MASTER
    # =====================================================

    master = switch_details[0]

    master_ip = master["ip"]

    master_username = master["username"]

    master_password = master["password"]

    if not wait_for_master(
        master_ip
    ):

        return

    master_connection = connect_to_master(
        master_ip=master_ip,
        master_username=master_username,
        master_password=master_password,
        connection_type=connection_type
    )

    if master_connection is None:

        print(
            "\nUnable to connect to "
            "Unit-ID 1 / MASTER."
        )

        return

    terminal_opened = (
        open_initial_master_terminal(
            master_connection=master_connection,
            master_ip=master_ip,
            expected_members=switch_count
        )
    )

    if not terminal_opened:

        print()

        print(
            "Complete stack was not detected."
        )

        print(
            "Automation stopped before "
            "test-case menu."
        )

        return

    # =====================================================
    # TEST CASE MENU
    # =====================================================

    test_case_menu(
        master_connection=master_connection,
        master_ip=master_ip,
        master_username=master_username,
        master_password=master_password,
        connection_type=connection_type,
        expected_members=switch_count,
        switch_details=switch_details
    )

    # =====================================================
    # COMPLETED
    # =====================================================

    print()

    print(
        "=" * 70
    )

    print(
        "             AUTOMATION COMPLETED"
    )

    print(
        "=" * 70
    )

    print()

    print(
        "MASTER connection remains available."
    )

    print(
        "No automatic connection close "
        "was performed."
    )

    print()


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print()
        print()

        print(
            "Automation interrupted by user."
        )

    except Exception as e:

        print()
        print()

        print(
            f"Unexpected error: {e}"
        )

