import re
import subprocess
import time

from connection import SwitchConnection
from reload import reload_all_switches, wait_for_reboot
from config import WAIT_AFTER_RELOAD


TEST_CASE_ID = "TC-STK-006"
TEST_CASE_TITLE = "VLAN Configuration Persistence on Stack"

COMMAND_SHOW_STACK = "do sh stack"
COMMAND_SHOW_VLAN = "do show vlan"
PAGINATION_MARKER = "More:"
PAGINATION_WAIT = 0.15
COMMAND_WRITE = "do write"

MASTER_RECONNECT_INTERVAL = 5
COMMAND_TIMEOUT = 15
POST_REBOOT_CONNECT_RETRY = 5


# =========================================================
# DISPLAY HELPERS
# =========================================================

def _print_header(title):
    print()
    print("=" * 70)
    print(f"{title:^70}")
    print("=" * 70)


def _print_step(step, title):
    print()
    print("-" * 70)
    print(f"STEP {step}: {title}")
    print("-" * 70)


# =========================================================
# CONNECTION HELPERS
# =========================================================

def _connection_is_usable(connection):
    try:
        if connection is None:
            return False

        shell = getattr(connection, "shell", None)
        if shell is None:
            return False

        if getattr(shell, "closed", False):
            return False

        return True
    except Exception:
        return False


def _update_connection_object(existing, replacement):
    """Keep main.py's original master connection object alive."""
    if existing is None:
        return replacement

    try:
        existing.__dict__.update(replacement.__dict__)
        return existing
    except Exception:
        return replacement


def _connect_switch(ip, username, password, connection_type, retries=1):
    """Connect to a switch with a bounded number of attempts."""
    for attempt in range(1, retries + 1):
        connection = SwitchConnection(
            connection_type=connection_type,
            ip=ip,
            username=username,
            password=password,
        )

        try:
            if connection.connect():
                return connection
        except Exception as exc:
            print(f"Connection attempt #{attempt} failed: {exc}")

        if attempt < retries:
            time.sleep(POST_REBOOT_CONNECT_RETRY)

    return None


def _reconnect_master(
    master_connection,
    master_ip,
    master_username,
    master_password,
    connection_type,
):
    """Reconnect Unit-1 after stack reboot and preserve the original object."""
    attempt = 0

    while True:
        attempt += 1
        print()
        print(f"MASTER connection attempt #{attempt}")
        print(
            f"Connecting to Unit-1 / MASTER at {master_ip} "
            f"using {connection_type.upper()}..."
        )

        replacement = _connect_switch(
            master_ip,
            master_username,
            master_password,
            connection_type,
            retries=1,
        )

        if replacement is not None:
            print("✓ Unit-1 / MASTER connected successfully.")
            return _update_connection_object(master_connection, replacement)

        print("Master is not ready yet.")
        print(f"Retrying in {MASTER_RECONNECT_INTERVAL} seconds...")
        time.sleep(MASTER_RECONNECT_INTERVAL)


# =========================================================
# COMMAND OUTPUT
# =========================================================

def _clear_shell(shell):
    try:
        while shell.recv_ready():
            shell.recv(65535)
    except Exception:
        pass


def _get_command_output(connection, command, timeout=COMMAND_TIMEOUT):
    """Run a CLI command and collect output until the shell becomes quiet."""
    try:
        shell = getattr(connection, "shell", None)

        if shell is None:
            print("\nERROR: Shell is not available.")
            return None

        _clear_shell(shell)

        print()
        print(f"Executing: {command}")
        shell.send(command + "\n")

        output = ""
        start_time = time.time()
        last_data_time = start_time
        quiet_required = 2.0

        while True:
            if shell.recv_ready():
                data = shell.recv(65535)

                if data:
                    chunk = data.decode("utf-8", errors="ignore")
                    output += chunk
                    print(chunk, end="", flush=True)
                    last_data_time = time.time()

                    # The switch paginates long output as:
                    # "More: <space>, Quit: q or CTRL+Z".
                    # Automatically press SPACE so the complete output is
                    # collected (for example VLAN 60 on page 2).
                    if PAGINATION_MARKER in chunk:
                        time.sleep(PAGINATION_WAIT)
                        try:
                            shell.send(" ")
                            last_data_time = time.time()
                        except Exception as page_exc:
                            print(f"\nPagination handling error: {page_exc}")

                    # QN CLI paginates long output. Automatically press SPACE
                    # whenever the switch displays the More prompt.
                    if re.search(r"More:\s*<space>", chunk, re.IGNORECASE):
                        try:
                            shell.send(" ")
                            last_data_time = time.time()
                        except Exception:
                            pass
            else:
                time.sleep(0.1)

            if output and time.time() - last_data_time >= quiet_required:
                break

            if time.time() - start_time >= timeout:
                break

        if output and not output.endswith("\n"):
            print()

        return output

    except Exception as exc:
        print(f"\nCommand execution error: {exc}")
        return None


def _run_master_command(
    master_connection,
    command,
    master_ip,
    master_username,
    master_password,
    connection_type,
    timeout=COMMAND_TIMEOUT,
):
    """Run a command on Unit-1 and reconnect automatically if needed."""
    if not _connection_is_usable(master_connection):
        master_connection = _reconnect_master(
            master_connection,
            master_ip,
            master_username,
            master_password,
            connection_type,
        )

    output = _get_command_output(master_connection, command, timeout)

    if output is not None:
        return master_connection, output

    print("\nMaster command failed. Reconnecting and retrying...")

    master_connection = _reconnect_master(
        master_connection,
        master_ip,
        master_username,
        master_password,
        connection_type,
    )

    output = _get_command_output(master_connection, command, timeout)
    return master_connection, output


# =========================================================
# STACK VERIFICATION
# =========================================================

def _clean_output(output):
    if not output:
        return ""

    # Remove common ANSI escape sequences.
    return re.sub(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "", output)


def _get_unit_ids(output):
    """Parse Unit-ID rows from the stack table."""
    unit_ids = []
    output = _clean_output(output)

    for line in output.splitlines():
        parts = line.strip().split()

        if len(parts) < 2:
            continue

        if not parts[0].isdigit():
            continue

        unit_id = int(parts[0])

        if 1 <= unit_id <= 64 and unit_id not in unit_ids:
            unit_ids.append(unit_id)

    return sorted(unit_ids)


def _get_unit_line(output, unit_id):
    output = _clean_output(output)

    for line in output.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0] == str(unit_id):
            return line.strip()

    return ""


def _is_controller(output, unit_id=1):
    line = _get_unit_line(output, unit_id).lower()
    return any(word in line for word in ("controller", "master", "active"))


def _verify_running_stack(output, expected_members):
    if not output:
        return False, "No output received from 'do sh stack'."

    unit_ids = _get_unit_ids(output)

    if not unit_ids:
        return False, "No Unit-ID rows were detected in 'do sh stack' output."

    missing = [
        unit_id
        for unit_id in range(1, expected_members + 1)
        if unit_id not in unit_ids
    ]

    if missing:
        return False, f"Expected Unit-ID(s) missing: {missing}"

    if not _is_controller(output, 1):
        return False, "Unit-1 is not shown as Controller/Master."

    return True, f"Unit-1 is Controller/Master. Members detected: {unit_ids}"


# =========================================================
# VLAN INPUT
# =========================================================

def _get_vlan_configuration():
    _print_step(2, "VLAN CONFIGURATION ON STACK MASTER")

    print("Select VLAN configuration type:")
    print("  1. Single VLAN")
    print("  2. VLAN Range")

    while True:
        choice = input("\nEnter choice: ").strip()

        if choice == "1":
            while True:
                vlan_id = input("Enter VLAN ID (1-4094): ").strip()
                if vlan_id.isdigit() and 1 <= int(vlan_id) <= 4094:
                    vlan_id = int(vlan_id)
                    break
                print("Invalid VLAN ID. Enter a value from 1 to 4094.")

            while True:
                name = input("Enter VLAN name: ").strip()
                if name:
                    break
                print("VLAN name cannot be empty.")

            return {
                "type": "single",
                "ids": [vlan_id],
                "command": f"vlan {vlan_id} name {name}",
                "name": name,
            }

        if choice == "2":
            while True:
                vlan_range = input("Enter VLAN range (example: 10-20): ").strip()
                match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", vlan_range)

                if not match:
                    print("Invalid range. Use the format: 10-20")
                    continue

                start = int(match.group(1))
                end = int(match.group(2))

                if not (1 <= start <= 4094 and 1 <= end <= 4094):
                    print("VLAN IDs must be between 1 and 4094.")
                    continue

                if start >= end:
                    print("Start VLAN must be smaller than end VLAN.")
                    continue

                ids = list(range(start, end + 1))
                return {
                    "type": "range",
                    "ids": ids,
                    "command": f"vlan {start}-{end}",
                    "name": None,
                }

        print("Invalid choice. Please enter 1 or 2.")


# =========================================================
# VLAN PARSING / VERIFICATION
# =========================================================

def _vlan_row_ids(output):
    """Return VLAN IDs from rows whose first column is the VLAN ID."""
    vlan_ids = set()
    output = _clean_output(output)

    for line in output.splitlines():
        parts = line.strip().split()

        if len(parts) < 2 or not parts[0].isdigit():
            continue

        vlan_id = int(parts[0])
        if 1 <= vlan_id <= 4094:
            vlan_ids.add(vlan_id)

    return vlan_ids


def _vlan_present(output, vlan_id):
    return vlan_id in _vlan_row_ids(output)


def _vlan_name_present(output, vlan_id, name):
    output = _clean_output(output)
    expected_name = name.lower()

    for line in output.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0] == str(vlan_id):
            return expected_name in line.lower()

    return False


def _verify_vlan_output(output, vlan_config):
    if not output:
        return False, [], "No output received from 'do show vlan'."

    missing = []

    for vlan_id in vlan_config["ids"]:
        if not _vlan_present(output, vlan_id):
            missing.append(vlan_id)

    if missing:
        return False, missing, f"Missing VLAN ID(s): {missing}"

    if vlan_config["type"] == "single":
        vlan_id = vlan_config["ids"][0]
        name = vlan_config["name"]
        if not _vlan_name_present(output, vlan_id, name):
            return False, [], (
                f"VLAN {vlan_id} is present, but VLAN name '{name}' "
                "was not detected in the output."
            )

    return True, [], "All configured VLANs were detected."


# =========================================================
# MEMBER VLAN VERIFICATION
# =========================================================

def _verify_vlan_on_member(member, vlan_config, member_label):
    print()
    print(f"Checking {member_label} ({member['ip']})...")

    connection = _connect_switch(
        member["ip"],
        member["username"],
        member["password"],
        member["connection_type"],
        retries=3,
    )

    if connection is None:
        print(f"✗ {member_label}: Connection FAILED.")
        return False

    try:
        output = _get_command_output(connection, COMMAND_SHOW_VLAN)
        passed, missing, reason = _verify_vlan_output(output, vlan_config)

        if passed:
            print(f"✓ {member_label}: VLAN verification PASS.")
        else:
            print(f"✗ {member_label}: VLAN verification FAIL.")
            print(f"  Reason: {reason}")

        return passed

    finally:
        try:
            connection.disconnect()
        except Exception:
            pass


# =========================================================
# MAIN TEST CASE
# =========================================================

def run_tc_stk_006(
    master_connection,
    master_ip,
    master_username,
    master_password,
    connection_type,
    expected_members=2,
    switch_details=None,
    **kwargs,
):
    _print_header(f"{TEST_CASE_ID} - {TEST_CASE_TITLE}")

    print()
    print("Objective:")
    print("  1. Apply VLAN configuration on the Stack Master.")
    print("  2. Verify VLAN configuration on all stack members.")
    print("  3. Reboot the stack and verify VLAN configuration again.")

    print()
    print("VLAN commands used:")
    print("  Single VLAN : vlan <id> name <name>")
    print("  VLAN Range  : vlan <start>-<end>")
    print("  Verification: do show vlan")

    # ---------------------------------------------------------
    # Validate member information
    # ---------------------------------------------------------
    if not switch_details:
        _print_header(f"{TEST_CASE_ID} RESULT")
        print("FAIL")
        print("\n✗ Switch details are not available.")
        print("Master connection remains active.")
        return False

    if len(switch_details) < expected_members:
        _print_header(f"{TEST_CASE_ID} RESULT")
        print("FAIL")
        print()
        print(
            f"✗ Expected details for {expected_members} members, "
            f"but only {len(switch_details)} member details are available."
        )
        print("Please provide all stack member IP/credential details in main.py.")
        print("Master connection remains active.")
        return False

    members = []
    for index in range(expected_members):
        member = dict(switch_details[index])
        member["connection_type"] = connection_type
        members.append(member)

    # =========================================================
    # STEP 1 - VERIFY RUNNING STACK
    # =========================================================
    _print_step(1, "VERIFY RUNNING STACK")

    master_connection, stack_output = _run_master_command(
        master_connection,
        COMMAND_SHOW_STACK,
        master_ip,
        master_username,
        master_password,
        connection_type,
    )

    stack_ok, stack_reason = _verify_running_stack(
        stack_output,
        expected_members,
    )

    print()
    if stack_ok:
        print(f"✓ {stack_reason}")
    else:
        print(f"✗ {stack_reason}")
        _print_header(f"{TEST_CASE_ID} RESULT")
        print("FAIL")
        print("\nMaster connection remains active.")
        return False

    # =========================================================
    # STEP 2 - VLAN CONFIGURATION ON MASTER
    # =========================================================
    vlan_config = _get_vlan_configuration()

    print()
    print("Configuration to be applied:")
    print(f"  Command: {vlan_config['command']}")

    confirm = input("\nProceed with VLAN configuration? (y/n): ").strip().lower()

    while confirm not in ("y", "yes", "n", "no"):
        print("Invalid input. Please enter Y or N.")
        confirm = input("Proceed with VLAN configuration? (y/n): ").strip().lower()

    if confirm in ("n", "no"):
        print("\nTC cancelled by user.")
        return False

    # Enter configuration mode and apply VLAN.
    master_connection, _ = _run_master_command(
        master_connection,
        "configure terminal",
        master_ip,
        master_username,
        master_password,
        connection_type,
        timeout=5,
    )

    master_connection, vlan_apply_output = _run_master_command(
        master_connection,
        vlan_config["command"],
        master_ip,
        master_username,
        master_password,
        connection_type,
        timeout=8,
    )

    if vlan_apply_output is None:
        _print_header(f"{TEST_CASE_ID} RESULT")
        print("FAIL")
        print("\n✗ VLAN configuration command failed.")
        print("Master connection remains active.")
        return False

    # Save from configuration mode.
    master_connection, write_output = _run_master_command(
        master_connection,
        COMMAND_WRITE,
        master_ip,
        master_username,
        master_password,
        connection_type,
        timeout=10,
    )

    if write_output is None:
        _print_header(f"{TEST_CASE_ID} RESULT")
        print("FAIL")
        print("\n✗ Unable to save VLAN configuration.")
        print("Master connection remains active.")
        return False

    print("\n✓ VLAN configuration applied and saved on Unit-1 / MASTER.")

    # =========================================================
    # STEP 3 - RELOAD MASTER
    _print_step(3, "RELOAD MASTER SWITCH")
    print("\nOnly Unit-1 / MASTER will be reloaded.")
    confirm = input("Proceed with MASTER reload? (y/n): ").strip().lower()
    while confirm not in ("y", "yes", "n", "no"):
        print("Invalid input. Please enter Y or N.")
        confirm = input("Proceed with MASTER reload? (y/n): ").strip().lower()
    if confirm in ("n", "no"):
        print("\nTC cancelled by user.")
        return False

    reload_connection = _connect_switch(master_ip, master_username, master_password, connection_type, retries=3)
    if reload_connection is None:
        _print_header(f"{TEST_CASE_ID} RESULT")
        print("FAIL\n\n✗ Unable to connect to Unit-1 / MASTER for reload.")
        return False
    try:
        print("\nSending reload command to Unit-1 / MASTER...")
        reload_ok = reload_all_switches([reload_connection])
    finally:
        try:
            reload_connection.disconnect()
        except Exception:
            pass
    if not reload_ok:
        _print_header(f"{TEST_CASE_ID} RESULT")
        print("FAIL\n\n✗ MASTER reload operation failed.")
        return False
    print("✓ Reload command sent to Unit-1 / MASTER.")

    # STEP 4 - WAIT FOR MASTER AND RECONNECT
    _print_step(4, "WAIT FOR MASTER AND RECONNECT")
    print(f"\nWaiting {WAIT_AFTER_RELOAD} seconds for MASTER reboot...")
    wait_for_reboot(WAIT_AFTER_RELOAD)
    master_connection = _reconnect_master(master_connection, master_ip, master_username, master_password, connection_type)
    if not _connection_is_usable(master_connection):
        _print_header(f"{TEST_CASE_ID} RESULT")
        print("FAIL\n\n✗ Unit-1 / MASTER could not be reconnected.")
        return False
    print("✓ Unit-1 / MASTER is back online and SSH is connected.")

    # STEP 5 - VERIFY VLAN AFTER REBOOT
    _print_step(5, "VERIFY VLAN AFTER REBOOT")
    print(f"\nVerification command: {COMMAND_SHOW_VLAN}")
    master_connection, after_vlan_output = _run_master_command(master_connection, COMMAND_SHOW_VLAN, master_ip, master_username, master_password, connection_type, timeout=COMMAND_TIMEOUT)
    after_passed, _, after_reason = _verify_vlan_output(after_vlan_output, vlan_config)
    print()
    print(f"Unit-1 / MASTER: {'PASS' if after_passed else 'FAIL'}")
    if not after_passed:
        print(f"  Reason: {after_reason}")

    # FINAL RESULT
    # =========================================================
    _print_header(f"{TEST_CASE_ID} RESULT")

    print()
    print(f"VLAN Configuration on Master : {'PASS' if vlan_apply_output is not None else 'FAIL'}")
    print(f"Master Reload                  : {'PASS' if reload_ok else 'FAIL'}")
    print(f"Master Reconnect               : {'PASS' if _connection_is_usable(master_connection) else 'FAIL'}")
    print(f"VLAN Verification After Reboot : {'PASS' if after_passed else 'FAIL'}")

    result = (
        vlan_apply_output is not None
        and reload_ok
        and _connection_is_usable(master_connection)
        and after_passed
    )

    print()
    print("=" * 70)
    print(f"{TEST_CASE_ID} : {'PASS' if result else 'FAIL'}")
    print("=" * 70)
    print()
    print("Master connection remains active.")

    return result