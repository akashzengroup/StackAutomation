import re
import time
import subprocess

from connection import SwitchConnection


TEST_CASE_ID = "TC-STK-012"
TEST_CASE_TITLE = "RELOAD ENTIRE STACK"

PING_INTERVAL = 3
REBOOT_TIMEOUT = 300
SSH_RETRY_INTERVAL = 5
SSH_RETRY_TIMEOUT = 180


# ============================================================
# PING
# ============================================================

def _ping_host(ip):
    try:
        result = subprocess.run(
            ["ping", "-n", "1", "-w", "1000", ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return result.returncode == 0

    except Exception:
        return False


# ============================================================
# CONNECT TO MASTER
# Same connection method already used by main.py
# ============================================================

def _connect_to_master(
    master_ip,
    master_username,
    master_password,
    connection_type
):
    print("\n" + "=" * 70)
    print("              CONNECTING TO MASTER")
    print("=" * 70)

    start_time = time.time()
    attempt = 0

    while time.time() - start_time < SSH_RETRY_TIMEOUT:

        attempt += 1

        print(f"\nConnection attempt #{attempt}")
        print(
            f"Connecting to {master_ip}:22 "
            f"using {connection_type.upper()}..."
        )

        try:
            connection = SwitchConnection(
                connection_type=connection_type,
                ip=master_ip,
                username=master_username,
                password=master_password
            )

            if connection.connect():
                print("\nUnit-ID 1 / MASTER connected.")
                return connection

        except Exception as exc:
            print(f"Connection failed: {exc}")

        time.sleep(SSH_RETRY_INTERVAL)

    print("\nERROR: Unable to reconnect to Unit-ID 1.")
    return None


# ============================================================
# SHOW STACK PARSER
# ============================================================

def _parse_stack(output):

    members = []

    if not output:
        return members

    pattern = re.compile(
        r"^\s*(\d+)\s+"
        r"([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})\s+"
        r"(controller|backup|member)\b",
        re.IGNORECASE
    )

    for line in output.splitlines():

        match = pattern.search(line)

        if not match:
            continue

        unit_id = int(match.group(1))
        mac = match.group(2)
        role = match.group(3).lower()

        members.append({
            "unit_id": unit_id,
            "mac": mac,
            "role": role
        })

    return members


# ============================================================
# SEND COMMAND
#
# IMPORTANT:
# send_command() already displays command/output.
# Do not print returned output again.
# ============================================================

def _send_command(connection, command):

    try:
        return connection.send_command(command)

    except Exception as exc:
        print(f"\nCommand execution error: {exc}")
        return None


# ============================================================
# WAIT FOR SWITCH TO GO DOWN
#
# This is important.
#
# Before declaring reboot successful, we wait until the old
# SSH/ICMP state disappears.
# ============================================================

def _wait_for_master_down(master_ip):

    print("\nWaiting for Unit-ID 1 to go DOWN...")

    start_time = time.time()

    while time.time() - start_time < 90:

        if not _ping_host(master_ip):
            print("Unit-ID 1 is DOWN. Reboot detected.")
            return True

        print("Unit-ID 1 is still responding...")
        time.sleep(PING_INTERVAL)

    print(
        "\nWARNING: Unit-ID 1 never became unreachable."
    )

    return False


# ============================================================
# WAIT FOR SWITCH TO COME UP
# ============================================================

def _wait_for_master_up(master_ip):

    print("\n" + "=" * 70)
    print("           WAITING FOR UNIT-ID 1")
    print("=" * 70)

    print(f"\nMASTER IP : {master_ip}")
    print("\nWaiting for the switch to reboot...")

    start_time = time.time()

    # First wait a little so we don't mistake the old session
    # for the newly booted switch.
    print("\nWaiting for reboot to start...")
    time.sleep(10)

    while time.time() - start_time < REBOOT_TIMEOUT:

        if _ping_host(master_ip):

            print("\nUnit-ID 1 is UP!")
            print(f"MASTER {master_ip} is responding.")

            # Give SSH service a little time to start.
            print("Waiting for SSH service...")
            time.sleep(5)

            return True

        elapsed = int(time.time() - start_time)

        print(
            f"Waiting for Unit-ID 1... "
            f"{elapsed}s elapsed"
        )

        time.sleep(PING_INTERVAL)

    print("\nERROR: Unit-ID 1 did not come UP.")

    return False


# ============================================================
# TC-STK-012
# ============================================================

def run_tc_stk_012(
    master_connection=None,
    connection=None,
    master_ip=None,
    master_username=None,
    master_password=None,
    username=None,
    password=None,
    connection_type=None,
    expected_members=None,
    member_count=None,
    switch_count=None,
    expected_units=None,
    **kwargs
):

    print("\n" + "=" * 70)
    print("              STARTING TC-STK-012")
    print("=" * 70)

    print("\n" + "=" * 70)
    print("       TC-STK-012 - RELOAD ENTIRE STACK")
    print("=" * 70)

    # --------------------------------------------------------
    # Validate MASTER connection
    # --------------------------------------------------------

    if master_connection is None:
        master_connection = connection

    if master_connection is None:
        print("\nERROR: MASTER connection is not available.")
        return False

    if not master_ip:
        print("\nERROR: MASTER IP is not available.")
        return False

    print("\nSTEP 1: Verify Unit-ID 1 / MASTER")
    print(f"\nUnit-ID 1 IP : {master_ip}")

    # --------------------------------------------------------
    # STEP 2
    # --------------------------------------------------------

    print("\nSTEP 2: Check stack before reload")

    print("\n[>] do show stack")

    before_output = _send_command(
        master_connection,
        "do show stack"
    )

    before_members = _parse_stack(before_output)

    if not before_members:
        print("\nERROR: Unable to detect stack members before reload.")
        return False

    print("\nCurrent Stack Members:")

    for member in before_members:

        print(
            f"  Unit-ID {member['unit_id']}  "
            f"Role: {member['role']:<10} "
            f"MAC: {member['mac']}"
        )

    # Expected count
    expected_count = expected_members

    if expected_count is None:
        expected_count = member_count

    if expected_count is None:
        expected_count = switch_count

    if expected_count is None:
        expected_count = len(before_members)

    # --------------------------------------------------------
    # STEP 3
    # --------------------------------------------------------

    print("\nSTEP 3: Reload entire stack")

    print("\nRunning command:")
    print("do reload")

    print("\nThe entire stack will reboot.")
    print("Please wait for Unit-ID 1 to come back UP.")

    print("\n[>] do reload")

    reload_success = False

    try:

        # IMPORTANT:
        # Do not print the returned output.
        # send_command() already displays it.
        reload_output = master_connection.send_command(
            "do reload"
        )

        reload_success = True

    except Exception as exc:

        # Connection closing during reload is NORMAL.
        # The switch can close SSH immediately after accepting
        # the reload command.
        print(
            f"\nConnection closed during reload: {exc}"
        )

        reload_success = True

    print("\nReload command has been sent.")

    if not reload_success:
        print("\nERROR: Reload command could not be sent.")
        return False

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Do NOT immediately call ping and consider the switch UP.
    #
    # First verify that the old switch goes DOWN.
    # --------------------------------------------------------

    print("\nChecking whether Unit-ID 1 actually started rebooting...")

    down_detected = _wait_for_master_down(master_ip)

    if not down_detected:

        print(
            "\nERROR: Unit-ID 1 never became unreachable."
        )

        print(
            "The reload command was accepted, but the switch "
            "did not enter the expected reboot state."
        )

        return False

    # --------------------------------------------------------
    # STEP 4
    # --------------------------------------------------------

    print("\nSTEP 4: Wait for Unit-ID 1 to come UP")

    if not _wait_for_master_up(master_ip):

        print("\nERROR: Unit-ID 1 did not recover.")

        return False

    # --------------------------------------------------------
    # STEP 5
    # --------------------------------------------------------

    print("\nSTEP 5: Reconnect to Unit-ID 1")

    new_master_connection = _connect_to_master(
        master_ip=master_ip,
        master_username=master_username,
        master_password=master_password,
        connection_type=connection_type
    )

    if new_master_connection is None:

        print("\nERROR: SSH reconnection failed.")

        return False

    # --------------------------------------------------------
    # STEP 6
    # --------------------------------------------------------

    print("\nSTEP 6: Verify stack after reload")

    print("\n[>] do show stack")

    after_output = _send_command(
        new_master_connection,
        "do show stack"
    )

    after_members = _parse_stack(after_output)

    if not after_members:

        print(
            "\nERROR: Unable to detect stack members "
            "after reload."
        )

        try:
            new_master_connection.close()
        except Exception:
            pass

        return False

    # --------------------------------------------------------
    # STEP 7
    # --------------------------------------------------------

    print("\nSTEP 7: Verify stack formation")

    detected_units = sorted(
        member["unit_id"]
        for member in after_members
    )

    detected_count = len(after_members)

    print(
        f"Expected stack members : {expected_count}"
    )

    print(
        "Detected unit IDs     : "
        + ", ".join(map(str, detected_units))
    )

    # Member count
    member_count_pass = (
        detected_count == int(expected_count)
    )

    print(
        f"Member count           : "
        f"{'PASS' if member_count_pass else 'FAIL'}"
    )

    # --------------------------------------------------------
    # Unit-ID 1
    # --------------------------------------------------------

    unit1 = None

    for member in after_members:

        if member["unit_id"] == 1:
            unit1 = member
            break

    if unit1 is None:

        print(
            "Unit-ID 1 role         : FAIL "
            "(Unit-ID 1 not detected)"
        )

        unit1_role_pass = False

    else:

        print(
            f"Unit-ID 1 role         : "
            f"{unit1['role']}"
        )

        unit1_role_pass = (
            unit1["role"].lower() == "controller"
        )

        print(
            "Unit-ID 1 / MASTER     : "
            f"{'PASS' if unit1_role_pass else 'FAIL'}"
        )

    # --------------------------------------------------------
    # Display members
    # --------------------------------------------------------

    print("\nDetected Stack Members:")

    for member in after_members:

        print(
            f"  Unit-ID {member['unit_id']}  "
            f"Role: {member['role']:<10} "
            f"MAC: {member['mac']}"
        )

    # --------------------------------------------------------
    # Final result
    # --------------------------------------------------------

    stack_verification_pass = (
        member_count_pass and
        unit1_role_pass
    )

    overall_pass = (
        reload_success and
        down_detected and
        stack_verification_pass
    )

    print("\n" + "=" * 70)
    print("             TC-STK-012 RESULT")
    print("=" * 70)

    print(
        "Stack Reload              : "
        f"{'PASS' if reload_success and down_detected else 'FAIL'}"
    )

    print(
        "Unit-ID 1 Recovery        : "
        f"{'PASS' if down_detected else 'FAIL'}"
    )

    print(
        "SSH Reconnection          : "
        f"{'PASS' if new_master_connection else 'FAIL'}"
    )

    print(
        "Stack Verification        : "
        f"{'PASS' if stack_verification_pass else 'FAIL'}"
    )

    print(
        f"\nTC-STK-012                : "
        f"{'PASS' if overall_pass else 'FAIL'}"
    )

    if overall_pass:

        print(
            "\nNew Unit-ID 1 / MASTER "
            "connection is now active."
        )

        return new_master_connection

    try:
        new_master_connection.close()
    except Exception:
        pass

    return False