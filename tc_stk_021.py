<<<<<<< HEAD
import re
import time

from connection import SwitchConnection


# ============================================================
# TC-STK-021 - Stack Split and Recovery
# ============================================================

TEST_CASE_ID = "TC-STK-021"
TEST_CASE_TITLE = "Stack Split and Recovery"

# Check for split detection for up to 60 seconds.
SPLIT_DETECTION_TIMEOUT = 60
SPLIT_POLL_INTERVAL = 5

# Check stack recovery every 15 seconds.
RECOVERY_POLL_INTERVAL = 15
RECOVERY_TIMEOUT = 600

COMMAND_TIMEOUT = 15


# ============================================================
# DISPLAY HELPERS
# ============================================================

def _print_header(title):
    print()
    print("=" * 75)
    print(f"{title:^75}")
    print("=" * 75)


def _print_step(number, title):
    print()
    print("-" * 75)
    print(f"STEP {number}: {title}")
    print("-" * 75)


def _pause(message):
    input(f"\n{message}\nPress ENTER to continue...")


# ============================================================
# CONNECTION HELPERS
# ============================================================

def _connect_switch(ip, username, password, connection_type):
    """
    Open a separate management connection to a switch.

    Does not close or replace the existing MASTER connection.
    """

    connection = None

    try:
        connection = SwitchConnection(
            connection_type=connection_type,
            ip=ip,
            username=username,
            password=password,
        )

        result = connection.connect()

        if result is False:
            print(f"Connection failed: {ip}")
            _close_connection(connection)
            return None

        print(f"Management connection established: {ip}")
        return connection

    except Exception as exc:
        print(f"Unable to connect to {ip}: {exc}")
        _close_connection(connection)
        return None


def _close_connection(connection):
    """
    Close only a temporary connection created by this testcase.
    """

    if connection is None:
        return

    for method_name in ("close", "disconnect"):
        method = getattr(connection, method_name, None)

        if callable(method):
            try:
                method()
                return
            except Exception:
                pass


def _reconnect_master(
    master_connection,
    master_ip,
    master_username,
    master_password,
    connection_type,
):
    """
    Restore the Unit-1 connection if it becomes unusable.

    Keep the original connection object's identity where possible,
    so the existing main.py reference remains valid.
    """

    print()
    print("Unit-1 connection is unavailable.")
    print("Attempting to reconnect to Unit-1...")

    try:
        replacement = _connect_switch(
            master_ip,
            master_username,
            master_password,
            connection_type,
        )

        if replacement is None:
            return None

        if master_connection is None:
            return replacement

        try:
            master_connection.__dict__.update(replacement.__dict__)
            return master_connection
        except Exception:
            return replacement

    except Exception as exc:
        print(f"MASTER reconnection error: {exc}")
        return None


# ============================================================
# COMMAND EXECUTION
# ============================================================

def _remove_ansi(text):
    if not text:
        return ""

    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)


def _get_command_output(connection, command, timeout=COMMAND_TIMEOUT):
    """
    Execute a command using the existing SwitchConnection API.

    Prefer send_command(). Fall back to the existing interactive
    shell when that method is unavailable.
    """

    if connection is None:
        raise RuntimeError("Switch connection is unavailable.")

    print()
    print(f">>> {command}")

    send_command = getattr(connection, "send_command", None)

    if callable(send_command):
        try:
            output = send_command(command, timeout=timeout)

            if output is not None:
                output = _remove_ansi(str(output))
                print(output)
                return output

        except TypeError:
            try:
                output = send_command(command)

                if output is not None:
                    output = _remove_ansi(str(output))
                    print(output)
                    return output

            except Exception:
                pass

        except Exception as exc:
            print(f"Command execution error: {exc}")

    # Interactive-shell fallback.
    shell = getattr(connection, "shell", None)

    if shell is None:
        shell = getattr(connection, "ssh_shell", None)

    if shell is None:
        raise RuntimeError(
            "No supported command execution method is available."
        )

    output_parts = []

    try:
        # Drain old output before sending a new command.
        if hasattr(shell, "recv_ready"):
            while shell.recv_ready():
                shell.recv(65535)

        shell.send(command + "\n")

        start_time = time.time()
        last_data_time = start_time

        while time.time() - start_time < timeout:
            if shell.recv_ready():
                data = shell.recv(65535)

                if not data:
                    time.sleep(0.1)
                    continue

                if isinstance(data, bytes):
                    chunk = data.decode(
                        "utf-8",
                        errors="ignore",
                    )
                else:
                    chunk = str(data)

                output_parts.append(chunk)
                last_data_time = time.time()

            else:
                time.sleep(0.1)

            # Stop after the response has become idle.
            if (
                output_parts
                and time.time() - last_data_time >= 1.0
            ):
                break

        output = _remove_ansi("".join(output_parts))

        if output:
            print(output)

        return output

    except Exception as exc:
        raise RuntimeError(
            f"Failed to execute '{command}': {exc}"
        ) from exc


def _show_stack(connection):
    """
    Display the current stack table.
    """

    try:
        return _get_command_output(
            connection,
            "do show stack",
        )

    except Exception as first_error:
        print(
            f"Command 'do show stack' failed: {first_error}"
        )

        # Fallback for environments that use the command
        # without the 'do' prefix.
        try:
            return _get_command_output(
                connection,
                "show stack",
            )

        except Exception as second_error:
            print(
                f"Unable to retrieve stack information: "
                f"{second_error}"
            )

            return None


# ============================================================
# STACK OUTPUT PARSING
# ============================================================

def _parse_stack_roles(output):
    """
    Parse Unit-ID and role from the show stack table.

    Example supported roles:
        controller
        master
        backup
        member

    Returns:
        {1: "controller", 2: "backup", ...}
    """

    roles = {}

    if not output:
        return roles

    role_pattern = re.compile(
        r"\b(controller|master|backup|standby|member)\b",
        re.IGNORECASE,
    )

    for line in output.splitlines():
        match = re.match(
            r"^\s*(\d+)\s+(.+)$",
            line,
        )

        if not match:
            continue

        unit_id = int(match.group(1))
        remaining_text = match.group(2)

        role_match = role_pattern.search(remaining_text)

        if role_match:
            roles[unit_id] = role_match.group(1).lower()

    return roles


def _get_unit_ids(roles):
    return sorted(roles.keys())


def _is_controller(role):
    return role in ("controller", "master")


def _is_backup(role):
    return role in ("backup", "standby")


def _display_roles(roles):
    print()
    print("Detected stack roles:")
    print("-" * 45)

    if not roles:
        print("No Unit-ID/role rows could be parsed.")
        return

    for unit_id in sorted(roles):
        print(f"Unit {unit_id}: {roles[unit_id].upper()}")

    print("-" * 45)


def _all_expected_units_present(roles, expected_members):
    expected_ids = set(range(1, expected_members + 1))
    detected_ids = set(roles.keys())

    return expected_ids.issubset(detected_ids)


# ============================================================
# MAIN TESTCASE
# ============================================================

def run_tc_stk_021(
    master_connection=None,
    master_ip=None,
    master_username=None,
    master_password=None,
    connection_type=None,
    expected_members=None,
    switch_details=None,
    **kwargs,
):
    """
    TC-STK-021: Stack Split and Recovery

    Flow:
      1. Verify initial stack membership and roles.
      2. Ask the user to disconnect the Unit-1/Unit-2 cable.
      3. Verify management access and roles on both switches.
      4. Observe whether a split actually occurs.
      5. Ask the user to reconnect the cable.
      6. Poll Unit-1 show stack every 15 seconds.
      7. Verify the original stack membership returns.

    This testcase does not change any other project file.
    """

    _print_header(
        f"{TEST_CASE_ID} - {TEST_CASE_TITLE}"
    )

    print()
    print("TEST OBJECTIVES")
    print("1. Verify the existing stack roles.")
    print("2. Disconnect the Unit-1 / Unit-2 stack cable.")
    print("3. Check management access to both switches.")
    print("4. Record the actual roles after disconnection.")
    print("5. Reconnect the cable.")
    print("6. Check Unit-1 show stack every 15 seconds.")
    print("7. Verify that the original stack membership returns.")

    # --------------------------------------------------------
    # Validate inputs supplied by main.py
    # --------------------------------------------------------

    if master_connection is None:
        print("\nERROR: Unit-1 / MASTER connection is unavailable.")
        return False

    if not master_ip:
        print("\nERROR: Unit-1 IP address was not provided.")
        return False

    if not connection_type:
        print("\nERROR: Connection type was not provided.")
        return False

    if not switch_details or len(switch_details) < 2:
        print(
            "\nERROR: At least Unit-1 and Unit-2 connection "
            "details are required."
        )
        return False

    # Use the saved switch details collected by main.py.
    unit1 = next(
        (
            item for item in switch_details
            if int(item.get("unit_id", 0)) == 1
        ),
        switch_details[0],
    )

    unit2 = next(
        (
            item for item in switch_details
            if int(item.get("unit_id", 0)) == 2
        ),
        switch_details[1],
    )

    unit1_ip = unit1.get("ip") or master_ip
    unit1_username = unit1.get("username") or master_username
    unit1_password = unit1.get("password") or master_password

    unit2_ip = unit2.get("ip")
    unit2_username = unit2.get("username")
    unit2_password = unit2.get("password")

    if not all((unit2_ip, unit2_username, unit2_password)):
        print(
            "\nERROR: Unit-2 IP address, username, or password "
            "is missing from switch_details."
        )
        return False

    try:
        expected_members = int(
            expected_members or len(switch_details)
        )
    except (TypeError, ValueError):
        expected_members = len(switch_details)

    print()
    print(f"Expected stack members : {expected_members}")
    print(f"Unit-1 management IP   : {unit1_ip}")
    print(f"Unit-2 management IP   : {unit2_ip}")
    print(f"Connection type        : {connection_type}")

    # --------------------------------------------------------
    # STEP 1: Verify initial stack
    # --------------------------------------------------------

    _print_step(
        1,
        "Verify Initial Stack and Roles",
    )

    initial_output = _show_stack(master_connection)

    if initial_output is None:
        print("\nFAIL: Unable to read the initial stack table.")
        return False

    initial_roles = _parse_stack_roles(initial_output)

    _display_roles(initial_roles)

    initial_membership_ok = _all_expected_units_present(
        initial_roles,
        expected_members,
    )

    unit1_role_ok = _is_controller(
        initial_roles.get(1, "")
    )

    unit2_role_ok = _is_backup(
        initial_roles.get(2, "")
    )

    if not initial_membership_ok:
        print(
            "\nWARNING: The initial stack table does not show "
            "all expected Unit-IDs."
        )

    if not unit1_role_ok:
        print(
            "\nWARNING: Unit-1 is not shown as Controller/Master."
        )

    if not unit2_role_ok:
        print(
            "\nWARNING: Unit-2 is not shown as Backup."
        )

    initial_roles_ok = (
        initial_membership_ok
        and unit1_role_ok
        and unit2_role_ok
    )

    if initial_roles_ok:
        print("\nPASS: Initial stack membership and roles verified.")
    else:
        print(
            "\nFAIL: Initial stack membership or expected roles "
            "could not be verified."
        )

        print(
            "The testcase will stop before asking you to remove "
            "the cable."
        )

        return False

    # --------------------------------------------------------
    # STEP 2: Ask user to disconnect the cable
    # --------------------------------------------------------

    _print_step(
        2,
        "Disconnect the Unit-1 / Unit-2 Stack Cable",
    )

    print()
    print("Cable to disconnect:")
    print("    Unit 1 tf4 <----> Unit 2 tf3")
    print()
    print(
        "Disconnect only this cable, then allow the switches "
        "time to detect the link change."
    )
    print()
    print(
        "IMPORTANT: The existing five-switch topology is a ring. "
        "The remaining links may keep Unit-1 and Unit-2 in the "
        "same stack."
    )

    _pause(
        "Disconnect the specified cable"
    )

    # --------------------------------------------------------
    # STEP 3: Connect to Unit-2 and check management access
    # --------------------------------------------------------

    _print_step(
        3,
        "Verify Management Access to Unit-1 and Unit-2",
    )

    # Unit-1: use the existing master connection.
    unit1_output = _show_stack(master_connection)

    unit1_access_ok = unit1_output is not None

    if unit1_access_ok:
        print("\nPASS: Unit-1 management access is available.")
    else:
        print(
            "\nUnit-1 command failed. Attempting to restore "
            "its management connection."
        )

        restored_master = _reconnect_master(
            master_connection,
            unit1_ip,
            unit1_username,
            unit1_password,
            connection_type,
        )

        if restored_master is not None:
            master_connection = restored_master
            unit1_output = _show_stack(master_connection)
            unit1_access_ok = unit1_output is not None

    # Unit-2: use its saved management credentials.
    unit2_connection = None
    unit2_output = None
    unit2_access_ok = False

    for attempt in range(1, 4):
        print()
        print(
            f"Unit-2 management connection attempt "
            f"{attempt}/3"
        )

        unit2_connection = _connect_switch(
            unit2_ip,
            unit2_username,
            unit2_password,
            connection_type,
        )

        if unit2_connection is not None:
            unit2_output = _show_stack(unit2_connection)

            if unit2_output is not None:
                unit2_access_ok = True
                break

            _close_connection(unit2_connection)
            unit2_connection = None

        if attempt < 3:
            print("Retrying in 5 seconds...")
            time.sleep(5)

    if unit2_access_ok:
        print("\nPASS: Unit-2 management access is available.")
    else:
        print(
            "\nFAIL: Unable to access Unit-2 after cable "
            "disconnection."
        )

    # --------------------------------------------------------
    # STEP 4: Observe split detection and roles
    # --------------------------------------------------------

    _print_step(
        4,
        "Observe Split Detection and Role Changes",
    )

    print(
        f"\nPolling Unit-1 and Unit-2 every "
        f"{SPLIT_POLL_INTERVAL} seconds for up to "
        f"{SPLIT_DETECTION_TIMEOUT} seconds."
    )

    split_detected = False
    split_deadline = time.time() + SPLIT_DETECTION_TIMEOUT

    latest_unit1_roles = {}
    latest_unit2_roles = {}

    while time.time() < split_deadline:
        print()
        print("=" * 65)
        print("SPLIT DETECTION CHECK")
        print("=" * 65)

        unit1_output = _show_stack(master_connection)

        if unit1_output is not None:
            latest_unit1_roles = _parse_stack_roles(unit1_output)

        # Re-establish Unit-2 access if the session closed.
        if unit2_connection is None:
            unit2_connection = _connect_switch(
                unit2_ip,
                unit2_username,
                unit2_password,
                connection_type,
            )

        if unit2_connection is not None:
            unit2_output = _show_stack(unit2_connection)

            if unit2_output is not None:
                latest_unit2_roles = _parse_stack_roles(
                    unit2_output
                )

        unit1_current_role = latest_unit1_roles.get(1, "")
        unit2_current_role = latest_unit2_roles.get(2, "")

        print()
        print(
            f"Unit-1 reported role: "
            f"{unit1_current_role or 'Unknown'}"
        )
        print(
            f"Unit-2 reported role: "
            f"{unit2_current_role or 'Unknown'}"
        )

        if (
            _is_controller(unit1_current_role)
            and _is_controller(unit2_current_role)
        ):
            split_detected = True

            print(
                "\nOBSERVED: Both switches report "
                "Controller/Master roles."
            )

            break

        remaining = int(
            max(0, split_deadline - time.time())
        )

        if remaining > 0:
            print(
                f"\nSplit not confirmed. "
                f"Checking again in {SPLIT_POLL_INTERVAL} seconds."
            )
            time.sleep(
                min(SPLIT_POLL_INTERVAL, remaining)
            )

    if split_detected:
        print("\nPASS: Both switches reported Controller/Master.")
    else:
        print(
            "\nWARNING: Both switches did not report "
            "Controller/Master within the detection window."
        )

        print(
            "This can be expected when the remaining ring links "
            "still connect the stack."
        )

    # --------------------------------------------------------
    # STEP 5: Ask user to reconnect cable
    # --------------------------------------------------------

    _print_step(
        5,
        "Reconnect the Unit-1 / Unit-2 Stack Cable",
    )

    print()
    print("Reconnect the original cable:")
    print("    Unit 1 tf4 <----> Unit 2 tf3")
    print()
    print(
        "After reconnecting, Unit-1 will be checked for "
        "the restored stack membership."
    )

    _pause(
        "Reconnect the cable"
    )

    # --------------------------------------------------------
    # STEP 6: Monitor recovery on Unit-1 every 15 seconds
    # --------------------------------------------------------

    _print_step(
        6,
        "Monitor Stack Recovery on Unit-1",
    )

    print()
    print(
        f"Polling interval : {RECOVERY_POLL_INTERVAL} seconds"
    )
    print(
        f"Recovery timeout : {RECOVERY_TIMEOUT} seconds"
    )
    print(
        f"Expected Unit-IDs: 1 to {expected_members}"
    )

    recovery_deadline = time.time() + RECOVERY_TIMEOUT
    recovery_success = False
    latest_recovery_roles = {}

    check_number = 0

    while time.time() < recovery_deadline:
        check_number += 1

        print()
        print("=" * 75)
        print(f"RECOVERY CHECK #{check_number}")
        print("=" * 75)

        # Try to keep the Unit-1 session available.
        output = _show_stack(master_connection)

        if output is None:
            print(
                "\nUnit-1 command failed. Attempting to reconnect..."
            )

            restored_master = _reconnect_master(
                master_connection,
                unit1_ip,
                unit1_username,
                unit1_password,
                connection_type,
            )

            if restored_master is not None:
                master_connection = restored_master
                output = _show_stack(master_connection)

        if output is not None:
            latest_recovery_roles = _parse_stack_roles(output)

            current_ids = _get_unit_ids(
                latest_recovery_roles
            )

            print()
            print(f"Detected Unit-IDs: {current_ids}")

            unit2_returned = 2 in latest_recovery_roles

            complete_stack_returned = (
                _all_expected_units_present(
                    latest_recovery_roles,
                    expected_members,
                )
            )

            if unit2_returned and complete_stack_returned:
                recovery_success = True

                print()
                print(
                    "PASS: Unit-2 has reappeared in the stack, "
                    "and all expected Unit-IDs are present."
                )

                break

            print()
            print(
                "Unit-2 or other expected members are still "
                "missing from the stack table."
            )

        else:
            print(
                "\nUnable to retrieve show stack output from Unit-1."
            )

        remaining = recovery_deadline - time.time()

        if remaining > 0:
            sleep_time = min(
                RECOVERY_POLL_INTERVAL,
                remaining,
            )

            print()
            print(
                f"Next show stack check in "
                f"{int(sleep_time)} seconds..."
            )

            time.sleep(sleep_time)

    # --------------------------------------------------------
    # STEP 7: Final result
    # --------------------------------------------------------

    _print_step(
        7,
        "Final Result",
    )

    print()
    print("Initial stack roles verified :", initial_roles_ok)
    print("Unit-1 management accessible :", unit1_access_ok)
    print("Unit-2 management accessible :", unit2_access_ok)
    print("Split detected               :", split_detected)
    print("Stack recovery verified      :", recovery_success)

    # Close only the temporary Unit-2 session.
    # Do not close the existing MASTER connection.
    _close_connection(unit2_connection)

    # Strict overall PASS requires all stages to succeed.
    overall_pass = (
        initial_roles_ok
        and unit1_access_ok
        and unit2_access_ok
        and split_detected
        and recovery_success
    )

    print()
    print("=" * 75)

    if overall_pass:
        print("TC-STK-021 RESULT: PASS")
    else:
        print("TC-STK-021 RESULT: FAIL")

        if not split_detected:
            print(
                "\nReason: Split behavior was not confirmed. "
                "Check whether the remaining topology still "
                "provides an alternate path."
            )

        if not recovery_success:
            print(
                "\nReason: The original complete stack was not "
                "restored before the recovery timeout."
            )

    print("=" * 75)

    print()
    print(
        "The original Unit-1 MASTER connection has not been "
        "intentionally closed."
    )
    return overall_pass