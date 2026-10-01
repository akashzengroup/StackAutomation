import time
import getpass

from connection import SwitchConnection


TEST_CASE_ID = "TC-STK-004"
TEST_CASE_TITLE = "Add Member to Running Stack"

OBSERVATION_TIME = 300
LOG_POLL_INTERVAL = 1
REJOIN_POLL_INTERVAL = 10
REJOIN_TIMEOUT = 600
NEW_SWITCH_STACK_PORT = "3-4"
NEW_SWITCH_STACK_PORT_TYPE = "tf"


# =========================================================
# HEADER / STEP
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
# MASTER CONNECTION RECOVERY
# =========================================================

def _connection_is_usable(connection):
    try:
        if connection is None:
            return False
        shell = getattr(connection, "shell", None)
        if shell is None or getattr(shell, "closed", False):
            return False
        return True
    except Exception:
        return False


def _reconnect_master(master_ip, master_username, master_password, connection_type):
    print()
    print("Master connection is not usable.")
    print("Reconnecting to Unit-1 / MASTER...")
    attempt = 0
    while True:
        attempt += 1
        print()
        print(f"Master reconnect attempt #{attempt}")
        print(f"Connecting to {master_ip} using {connection_type.upper()}...")
        try:
            new_connection = SwitchConnection(
                connection_type=connection_type,
                ip=master_ip,
                username=master_username,
                password=master_password,
            )
            if new_connection.connect():
                print("\n✓ Unit-1 / MASTER reconnected successfully.")
                return new_connection
        except Exception as exc:
            print(f"Reconnect error: {exc}")
        print("Master is not ready yet. Retrying in 5 seconds...")
        time.sleep(5)


def _update_connection_object(existing, replacement):
    if existing is None:
        return replacement
    try:
        existing.__dict__.update(replacement.__dict__)
        return existing
    except Exception:
        return replacement


# =========================================================
# COMMAND HELPERS
# =========================================================

def _clear_shell(shell):
    try:
        while shell.recv_ready():
            shell.recv(65535)
    except Exception:
        pass


def _get_command_output(connection, command, timeout=15):
    try:
        shell = connection.shell
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
        while True:
            if shell.recv_ready():
                data = shell.recv(65535)
                if data:
                    chunk = data.decode("utf-8", errors="ignore")
                    output += chunk
                    print(chunk, end="", flush=True)
                    last_data_time = time.time()
            else:
                time.sleep(0.1)
            if output and time.time() - last_data_time >= 1.0:
                break
            if time.time() - start_time >= timeout:
                break
        if output and not output.endswith("\n"):
            print()
        return output
    except Exception as exc:
        print(f"\nCommand execution error: {exc}")
        return None


def _send_command(connection, command, wait=1):
    try:
        shell = connection.shell
        if shell is None:
            print("\nERROR: Shell is not available.")
            return False
        _clear_shell(shell)
        print()
        print(f"Sending: {command}")
        shell.send(command + "\n")
        time.sleep(wait)
        try:
            while shell.recv_ready():
                data = shell.recv(65535)
                if data:
                    print(data.decode("utf-8", errors="ignore"), end="", flush=True)
                else:
                    break
        except Exception:
            pass
        return True
    except Exception as exc:
        print(f"\nCommand send error: {exc}")
        return False


def _run_master_command(master_connection, command, master_ip, master_username,
                        master_password, connection_type, timeout=15):
    if not _connection_is_usable(master_connection):
        replacement = _reconnect_master(
            master_ip, master_username, master_password, connection_type
        )
        master_connection = _update_connection_object(master_connection, replacement)

    output = _get_command_output(master_connection, command, timeout=timeout)
    if output is not None:
        return master_connection, output

    print("\nMaster command failed because the session may have been closed.")
    print("Recovering MASTER connection and retrying...")
    replacement = _reconnect_master(
        master_ip, master_username, master_password, connection_type
    )
    master_connection = _update_connection_object(master_connection, replacement)
    output = _get_command_output(master_connection, command, timeout=timeout)
    return master_connection, output


# =========================================================
# STACK PARSING
# =========================================================

def _parse_stack_unit_ids(output):
    unit_ids = []
    if not output:
        return unit_ids
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.lower().startswith("unit id") or line.startswith("-------"):
            continue
        parts = line.split()
        if not parts:
            continue
        try:
            unit_id = int(parts[0])
            if 1 <= unit_id <= 64:
                unit_ids.append(unit_id)
        except ValueError:
            continue
    return sorted(set(unit_ids))


def _get_unit_line(output, unit_id):
    if not output:
        return ""
    for line in output.splitlines():
        parts = line.strip().split()
        if parts and parts[0] == str(unit_id):
            return line.strip()
    return ""


def _find_next_unit_id(detected_unit_ids, max_unit_id=64):
    detected = set(detected_unit_ids)
    for unit_id in range(1, max_unit_id + 1):
        if unit_id not in detected:
            return unit_id
    return None


def _verify_running_stack(output):
    if not output:
        return False, "No output received from 'show stack'.", []
    unit_ids = _parse_stack_unit_ids(output)
    if not unit_ids:
        return False, "Unable to detect any Unit-ID from 'show stack'.", []
    unit1_line = _get_unit_line(output, 1).lower()
    if not any(word in unit1_line for word in ("controller", "master", "active")):
        return False, "Unit-1 Controller role was not detected.", unit_ids
    if 2 in unit_ids:
        unit2_line = _get_unit_line(output, 2).lower()
        if not any(word in unit2_line for word in ("backup", "standby")):
            return False, "Unit-2 Backup role was not detected.", unit_ids
    return True, "Running stack is valid.", unit_ids


# =========================================================
# NEW SWITCH INPUT / CONFIGURATION
# =========================================================

def _get_new_switch_connection_type():
    print()
    print("Connection Type for NEW Switch")
    print("1. SSH")
    print("2. Telnet")
    while True:
        choice = input("\nEnter your choice: ").strip()
        if choice == "1":
            return "ssh"
        if choice == "2":
            return "telnet"
        print("Invalid choice. Enter 1 or 2.")


def _connect_new_switch(new_ip, new_username, new_password, new_connection_type):
    try:
        connection = SwitchConnection(
            connection_type=new_connection_type,
            ip=new_ip,
            username=new_username,
            password=new_password,
        )
        if connection.connect():
            print("\n✓ New switch connected successfully.")
            return connection
    except Exception as exc:
        print(f"\n✗ New switch connection failed: {exc}")
    print("\n✗ Unable to connect to the new switch.")
    print("Please verify IP address and credentials.")
    return None


# =========================================================
# 4.1 OBSERVATION / VERIFICATION HELPERS
# =========================================================

def _observe_master_logs(master_connection, master_ip, master_username,
                         master_password, connection_type, seconds=OBSERVATION_TIME):
    print()
    print("=" * 70)
    print("             5-MINUTE MASTER OBSERVATION")
    print("=" * 70)
    print("\nMonitoring Unit-1 / Controller for 5 minutes.")
    print("Switch-generated discovery, compatibility and")
    print("configuration-sync messages will be displayed below.")
    print("\nNo reload will be performed on the running stack.\n")
    start = time.time()
    collected = ""
    while time.time() - start < seconds:
        shell = getattr(master_connection, "shell", None)
        try:
            if shell is None or getattr(shell, "closed", False):
                replacement = _reconnect_master(
                    master_ip, master_username, master_password, connection_type
                )
                master_connection = _update_connection_object(master_connection, replacement)
                shell = master_connection.shell
            while shell.recv_ready():
                data = shell.recv(65535)
                if not data:
                    break
                chunk = data.decode("utf-8", errors="ignore")
                collected += chunk
                print(chunk, end="", flush=True)
        except Exception as exc:
            print(f"\nMaster log socket error: {exc}")
            replacement = _reconnect_master(
                master_ip, master_username, master_password, connection_type
            )
            master_connection = _update_connection_object(master_connection, replacement)
        elapsed = int(time.time() - start)
        remaining = max(0, seconds - elapsed)
        print(f"\rMonitoring... {remaining // 60:02d}:{remaining % 60:02d} remaining",
              end="", flush=True)
        time.sleep(LOG_POLL_INTERVAL)
    print("\n\n5-minute observation completed.")
    return collected


def _verify_stack_links(output):
    if not output:
        return False, "No output received from 'show stack links details'."
    text = output.lower()
    if "active" not in text:
        return False, "No Active stack link detected."
    bad_patterns = (
        "link down", "failed", "failure", "error", "incompatible",
        "software mismatch", "version mismatch", "config sync failed",
        "configuration sync failed", "sync failed", "join failed",
        "stack join failed",
    )
    problems = [p for p in bad_patterns if p in text]
    if problems:
        return False, "Stack problem detected: " + ", ".join(problems)
    return True, "Stack links are Active and no link failure was detected."


def _verify_compatibility_and_sync(output):
    if not output:
        return True, "No master log text was captured; no failure can be confirmed."
    text = output.lower()
    failures = (
        "software mismatch", "version mismatch", "incompatible",
        "compatibility failed", "compatibility failure", "sw compatibility failed",
        "config sync failed", "configuration sync failed", "sync failed",
        "configuration failed", "config synchronization failed",
        "configuration synchronization failed",
    )
    problem = next((p for p in failures if p in text), None)
    if problem:
        return False, f"Software/configuration synchronization problem detected: {problem}"
    return True, "No software compatibility or configuration-sync failure detected."


# =========================================================
# 4.2 RE-ADD HELPERS
# =========================================================

def _get_readd_unit_id(detected_unit_ids):
    print()
    print("Current Unit-IDs in the running stack:")
    print("  " + ", ".join(f"Unit-{x}" for x in detected_unit_ids))
    print()
    print("Enter the Unit-ID of the previously removed switch that you want to re-add.")
    print("The Unit-ID must currently be ABSENT from the running stack.")
    print()
    while True:
        value = input("Unit-ID to re-add: ").strip()
        try:
            unit_id = int(value)
        except ValueError:
            print("Invalid Unit-ID. Enter a number from 1 to 64.")
            continue
        if not 1 <= unit_id <= 64:
            print("Unit-ID must be between 1 and 64.")
            continue
        if unit_id in detected_unit_ids:
            print(f"Unit-{unit_id} is already present in the running stack.")
            print("Please enter the Unit-ID of the member that was physically removed.")
            continue
        return unit_id


def _wait_for_readded_member(master_connection, master_ip, master_username,
                             master_password, connection_type, target_unit_id,
                             timeout=REJOIN_TIMEOUT, poll_interval=REJOIN_POLL_INTERVAL):
    print()
    print("=" * 70)
    print("             WAITING FOR REMOVED MEMBER")
    print("=" * 70)
    print()
    print(f"Waiting for Unit-{target_unit_id} to return to the stack.")
    print(f"Checking 'show stack' every {poll_interval} seconds.")
    print(f"Timeout: {timeout // 60} minutes.")
    print()
    start = time.time()
    check_number = 0
    while time.time() - start < timeout:
        check_number += 1
        master_connection, output = _run_master_command(
            master_connection, "show stack", master_ip, master_username,
            master_password, connection_type, timeout=15
        )
        unit_ids = _parse_stack_unit_ids(output)
        elapsed = int(time.time() - start)
        print()
        print(f"Check #{check_number} | Elapsed: {elapsed}s")
        print(f"Current Unit-IDs: {unit_ids}")
        if target_unit_id in unit_ids:
            print()
            print(f"✓ Unit-{target_unit_id} is now visible in 'show stack'.")
            return master_connection, True, output
        remaining = max(0, timeout - elapsed)
        print(f"Unit-{target_unit_id} not detected yet.")
        print(f"Next check in {poll_interval}s. Remaining timeout: {remaining}s")
        time.sleep(poll_interval)
    return master_connection, False, None


def _show_readd_logs(master_connection, master_ip, master_username,
                     master_password, connection_type, target_unit_id):
    print()
    print("=" * 70)
    print("                    STACK LOG CHECK")
    print("=" * 70)
    print()
    print(f"Checking logs for Unit-{target_unit_id} rejoin messages...")
    master_connection, logging_output = _run_master_command(
        master_connection, "show logging", master_ip, master_username,
        master_password, connection_type
    )
    if logging_output:
        print("\nLog check completed.")
    else:
        print("\nNo logging output was returned.")
    return master_connection, logging_output


# =========================================================
# SCENARIO 4.1 - NEW MEMBER
# =========================================================

def _run_scenario_4_1(master_connection, master_ip, master_username,
                       master_password, connection_type, detected_unit_ids):
    _print_header("TC-STK-004.1 - ADD NEW SWITCH TO RUNNING STACK")
    new_unit_id = _find_next_unit_id(detected_unit_ids)
    if new_unit_id is None:
        print("\nFAIL: No available Unit-ID found. Maximum is 64.")
        return master_connection, False

    print()
    print(f"Current stack member count : {len(detected_unit_ids)}")
    print(f"Current Unit-IDs           : {detected_unit_ids}")
    print()
    if new_unit_id <= max(detected_unit_ids):
        print(f"Missing Unit-ID detected: Unit-{new_unit_id}")
        print("The new switch will be configured with this missing Unit-ID.")
    else:
        print("All current Unit-IDs are consecutive.")
        print(f"Next Unit-ID will be: Unit-{new_unit_id}")

    print()
    print("Examples:")
    print("  [1, 2, 3]       -> Unit-4")
    print("  [1, 3, 4]       -> Unit-2")
    print("  [1, 2, 4]       -> Unit-3")
    print("  [1, 2, 3, 4]    -> Unit-5")

    _print_step("4.1", f"PREPARE NEW SWITCH / UNIT-{new_unit_id}")
    new_ip = input("New Switch IP Address: ").strip()
    new_username = input("New Switch User Name: ").strip()
    new_password = getpass.getpass("New Switch Password: ")
    new_connection_type = _get_new_switch_connection_type()

    print()
    print(f"Unit-ID         : {new_unit_id}")
    print(f"IP Address      : {new_ip}")
    print(f"Connection Type : {new_connection_type.upper()}")
    print(f"Stack Link      : {NEW_SWITCH_STACK_PORT_TYPE.upper()}{NEW_SWITCH_STACK_PORT}")
    print()
    confirm = input(f"Configure this NEW switch as Unit-{new_unit_id}? (y/n): ").strip().lower()
    if confirm != "y":
        print("\nTC-STK-004.1 cancelled by user.")
        return master_connection, False

    _print_step("4.1", f"CONFIGURE UNIT-{new_unit_id} AS NEW STACK MEMBER")
    new_connection = _connect_new_switch(
        new_ip, new_username, new_password, new_connection_type
    )
    if new_connection is None:
        return master_connection, False

    try:
        commands = [
            "configure terminal",
            f"stack configuration unit-id {new_unit_id} links {NEW_SWITCH_STACK_PORT_TYPE}{NEW_SWITCH_STACK_PORT}",
        ]
        for command in commands:
            if _get_command_output(new_connection, command) is None:
                print(f"\n✗ Failed to execute: {command}")
                return master_connection, False

        print("\nSaving new switch configuration...")
        if _get_command_output(new_connection, "do write") is None:
            print("\n✗ Unable to save configuration.")
            return master_connection, False
        print(f"✓ Unit-{new_unit_id} configuration saved.")

        print()
        print("=" * 70)
        print(f"                 RELOADING UNIT-{new_unit_id}")
        print("=" * 70)
        print("\nThe existing running stack will NOT be reloaded.")
        print(f"Only Unit-{new_unit_id} will be reloaded.")
        if not _send_command(new_connection, "do reload", wait=2):
            print(f"\n✗ Failed to send reload command to Unit-{new_unit_id}.")
            return master_connection, False
        print(f"\n✓ Reload command sent to Unit-{new_unit_id}.")
    finally:
        try:
            new_connection.close()
        except Exception:
            pass

    print()
    print("=" * 70)
    print("                  USER ASSISTANCE")
    print("=" * 70)
    print()
    print(f"Please connect the stack cable(s) to Unit-{new_unit_id}.")
    print("Connect the new switch to the already RUNNING stack.")
    print("Do NOT power off Unit-1 or Unit-2.")
    input(f"After Unit-{new_unit_id} is powered ON and the stack cable is connected, press ENTER to continue.")

    _print_step(4, "OBSERVE DISCOVERY / SW COMPATIBILITY / CONFIG SYNC")
    log_output = _observe_master_logs(
        master_connection, master_ip, master_username, master_password,
        connection_type, OBSERVATION_TIME
    )

    _print_step(5, f"VERIFY UNIT-{new_unit_id} IN RUNNING STACK")
    master_connection, final_stack = _run_master_command(
        master_connection, "show stack", master_ip, master_username,
        master_password, connection_type
    )
    final_unit_ids = _parse_stack_unit_ids(final_stack)
    discovered = new_unit_id in final_unit_ids
    print(f"\nFinal detected Unit-IDs: {final_unit_ids}")
    print(f"{'✓' if discovered else '✗'} Unit-{new_unit_id} {'is' if discovered else 'is NOT'} present in the running stack.")

    master_connection, links_output = _run_master_command(
        master_connection, "show stack links details", master_ip,
        master_username, master_password, connection_type
    )
    links_ok, links_message = _verify_stack_links(links_output)
    print(f"\nStack Link Verification: {links_message}")

    master_connection, logging_output = _run_master_command(
        master_connection, "show logging", master_ip, master_username,
        master_password, connection_type
    )
    compatibility_ok, compatibility_message = _verify_compatibility_and_sync(
        (log_output or "") + "\n" + (logging_output or "")
    )
    print(f"\nSW Compatibility / Config Sync: {compatibility_message}")

    _print_header("TC-STK-004.1 RESULT")
    if discovered and links_ok and compatibility_ok:
        print("\nPASS\n")
        print(f"✓ Unit-{new_unit_id} was added to the running stack.")
        print("✓ Stack link verification passed.")
        print("✓ No software compatibility or configuration-sync failure detected.")
        return master_connection, True
    print("\nFAIL\n")
    if not discovered:
        print(f"✗ Unit-{new_unit_id} was not discovered in the running stack.")
    if not links_ok:
        print(f"✗ {links_message}")
    if not compatibility_ok:
        print(f"✗ {compatibility_message}")
    return master_connection, False


# =========================================================
# SCENARIO 4.2 - RE-ADD REMOVED MEMBER
# =========================================================

def _run_scenario_4_2(master_connection, master_ip, master_username,
                       master_password, connection_type, detected_unit_ids):
    _print_header("TC-STK-004.2 - RE-ADD REMOVED STACK MEMBER")
    print()
    print("This scenario is for a switch that was previously part of the stack.")
    print("Only the stack cable is removed/reconnected.")
    print("NO Unit-ID configuration will be performed.")
    print("NO reload will be performed.")
    print()

    target_unit_id = _get_readd_unit_id(detected_unit_ids)

    _print_step("4.2", f"RECONNECT STACK CABLE TO UNIT-{target_unit_id}")
    print()
    print(f"Target Unit-ID: Unit-{target_unit_id}")
    print()
    print("IMPORTANT:")
    print("  - Do NOT configure the switch.")
    print("  - Do NOT reload the switch.")
    print("  - The existing Unit-ID/configuration must remain unchanged.")
    print()
    print(f"Please reconnect the stack cable to Unit-{target_unit_id}.")
    print("After connecting the stack cable, press ENTER.")
    input()

    print()
    print(f"✓ Stack cable reconnection confirmed by user for Unit-{target_unit_id}.")
    print("Starting live stack monitoring...")

    master_connection, detected, final_output = _wait_for_readded_member(
        master_connection, master_ip, master_username, master_password,
        connection_type, target_unit_id
    )

    # A log check is informational; presence in show stack is the PASS criterion.
    master_connection, logging_output = _show_readd_logs(
        master_connection, master_ip, master_username, master_password,
        connection_type, target_unit_id
    )

    if detected:
        final_ids = _parse_stack_unit_ids(final_output)
        print()
        print("=" * 70)
        print("                 TC-STK-004.2 RESULT")
        print("=" * 70)
        print("\nPASS\n")
        print(f"✓ Unit-{target_unit_id} returned to the running stack.")
        print(f"✓ Unit-{target_unit_id} is visible in 'show stack'.")
        print(f"✓ Final Unit-IDs: {final_ids}")
        print("✓ No Unit-ID configuration was performed.")
        print("✓ No reload was performed.")
        print("\nMaster connection remains active.")
        return master_connection, True

    print()
    print("=" * 70)
    print("                 TC-STK-004.2 RESULT")
    print("=" * 70)
    print("\nFAIL\n")
    print(f"✗ Unit-{target_unit_id} was not detected in 'show stack' within the timeout.")
    print("✗ Re-add operation could not be verified.")
    print("\nMaster connection remains active.")
    return master_connection, False


# =========================================================
# TC-STK-004
# =========================================================

def run_tc_stk_004(master_connection, master_ip, master_username,
                    master_password, connection_type, expected_members=None, **kwargs):
    _print_header(f"{TEST_CASE_ID} - {TEST_CASE_TITLE}")
    print()
    print("Objective:")
    print("  4.1 Add a NEW switch to the already running stack.")
    print("  4.2 Re-add a PREVIOUSLY REMOVED member using its existing configuration.")
    print()
    print("IMPORTANT:")
    print("  - Startup member count is NOT used as expected Unit-IDs for TC-STK-004.")
    print("  - TC-STK-004 always uses live 'show stack' as the source of truth.")
    print("  - Other test cases are not changed by this testcase.")

    # -----------------------------------------------------
    # Step 1 - live stack state
    # -----------------------------------------------------
    _print_step(1, "VERIFY CURRENT RUNNING STACK")
    master_connection, stack_output = _run_master_command(
        master_connection, "show stack", master_ip, master_username,
        master_password, connection_type
    )
    stack_ok, stack_message, detected_unit_ids = _verify_running_stack(stack_output)
    print(f"\nRunning Stack Verification: {stack_message}")
    if not stack_ok:
        _print_header(f"{TEST_CASE_ID} RESULT")
        print("\nFAIL")
        print(f"\n✗ {stack_message}")
        return False

    print()
    print("=" * 70)
    print("                 CURRENT STACK STATE")
    print("=" * 70)
    print(f"\nCurrent stack member count : {len(detected_unit_ids)}")
    print(f"Current Unit-IDs           : {detected_unit_ids}")
    print()

    # -----------------------------------------------------
    # Step 2 - scenario selection
    # -----------------------------------------------------
    _print_step(2, "SELECT TC-STK-004 SCENARIO")
    print()
    print("1. 4.1 - Add NEW switch to running stack")
    print("2. 4.2 - Re-add PREVIOUSLY REMOVED member")
    print()
    while True:
        scenario = input("Select scenario [1-2]: ").strip()
        if scenario in ("1", "2"):
            break
        print("Invalid selection. Enter 1 or 2.")

    if scenario == "1":
        master_connection, result = _run_scenario_4_1(
            master_connection, master_ip, master_username, master_password,
            connection_type, detected_unit_ids
        )
    else:
        master_connection, result = _run_scenario_4_2(
            master_connection, master_ip, master_username, master_password,
            connection_type, detected_unit_ids
        )

    print()
    print("Master connection remains active.")
    return result


# =========================================================
# ALIAS FOR MAIN.PY
# =========================================================

run_test_case = run_tc_stk_004


# =========================================================
# DIRECT EXECUTION
# =========================================================

if __name__ == "__main__":
    print()
    print("TC-STK-004 is normally executed through main.py.")
    print()
    print("Use:")
    print("    python main.py")