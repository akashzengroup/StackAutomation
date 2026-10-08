import time
import re
from connection import SwitchConnection


# =========================================================
# TC-STK-005
# Remove Non-Master Member
# =========================================================

TEST_CASE_ID = "TC-STK-005"
TEST_CASE_TITLE = "Remove Non-Master Member"

REMOVAL_TIMEOUT = 120
POLL_INTERVAL = 10


# =========================================================
# Display Helpers
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
# Connection Helpers
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


def _reconnect_master(
    master_ip,
    master_username,
    master_password,
    connection_type,
    existing_connection=None,
):
    print()
    print("Master connection is not usable.")
    print("Reconnecting to Unit-1 / MASTER...")

    attempt = 0

    while True:
        attempt += 1

        print()
        print(f"Connection attempt #{attempt}")
        print(
            f"Connecting to {master_ip} using "
            f"{connection_type.upper()}..."
        )

        connection = SwitchConnection(
            connection_type=connection_type,
            ip=master_ip,
            username=master_username,
            password=master_password,
        )

        try:
            if connection.connect():
                print("✓ Unit-1 / MASTER reconnected successfully.")

                if existing_connection is not None:
                    try:
                        existing_connection.__dict__.update(
                            connection.__dict__
                        )
                        return existing_connection
                    except Exception:
                        pass

                return connection

        except Exception as e:
            print(f"Connection error: {e}")

        print("Master connection is not ready yet.")
        print("Retrying in 5 seconds...")
        time.sleep(5)


def _ensure_master_connection(
    master_connection,
    master_ip,
    master_username,
    master_password,
    connection_type,
):
    if _connection_is_usable(master_connection):
        return master_connection

    return _reconnect_master(
        master_ip,
        master_username,
        master_password,
        connection_type,
        existing_connection=master_connection,
    )


# =========================================================
# Shell / Command Helpers
# =========================================================

def _clear_shell(shell):
    try:
        while shell.recv_ready():
            shell.recv(65535)
    except Exception:
        pass


def _get_command_output(connection, command, timeout=15):
    """
    Execute a CLI command and collect complete output.

    Stack events can be printed asynchronously while the command
    is running, so wait until the CLI becomes quiet instead of
    stopping at the first short gap in output.
    """

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

        quiet_required = 2.0

        while True:
            received = False

            try:
                while shell.recv_ready():

                    data = shell.recv(65535)

                    if not data:
                        break

                    chunk = data.decode(
                        "utf-8",
                        errors="ignore",
                    )

                    output += chunk

                    print(
                        chunk,
                        end="",
                        flush=True,
                    )

                    last_data_time = time.time()
                    received = True

            except Exception as e:
                print(f"\nCommand read error: {e}")

                return None if not output else output

            now = time.time()

            if (
                output
                and not received
                and (now - last_data_time) >= quiet_required
            ):
                break

            if now - start_time >= timeout:
                break

            time.sleep(0.1)

        if output and not output.endswith("\n"):
            print()

        return output

    except Exception as e:
        print(f"\nCommand execution error: {e}")
        return None


def _run_master_command_with_reconnect(
    master_connection,
    command,
    master_ip,
    master_username,
    master_password,
    connection_type,
    timeout=15,
):
    """
    Run a command on Unit-1 / MASTER.

    If the connection is unusable or the command fails,
    reconnect automatically and retry once.
    """

    master_connection = _ensure_master_connection(
        master_connection,
        master_ip,
        master_username,
        master_password,
        connection_type,
    )

    output = _get_command_output(
        master_connection,
        command,
        timeout=timeout,
    )

    if output is not None:
        return master_connection, output

    print()
    print("Master command failed. Checking the connection...")

    master_connection = _reconnect_master(
        master_ip,
        master_username,
        master_password,
        connection_type,
        existing_connection=master_connection,
    )

    output = _get_command_output(
        master_connection,
        command,
        timeout=timeout,
    )

    return master_connection, output


# =========================================================
# Stack Parsing Helpers
# =========================================================

def _clean_line(line):
    """
    Remove ANSI escape sequences and normalize whitespace.
    """

    if not line:
        return ""

    line = re.sub(
        r"\x1b\[[0-?]*[ -/]*[@-~]",
        "",
        line,
    )

    return line.strip()


def _get_unit_ids(output):
    """
    Return Unit-IDs from actual stack member table rows.

    Only lines whose first field is a valid Unit-ID (1-64)
    are considered.
    """

    unit_ids = []

    if not output:
        return unit_ids

    for line in output.splitlines():

        text = _clean_line(line)

        if not text:
            continue

        parts = text.split()

        if not parts:
            continue

        if not re.fullmatch(r"[0-9]+", parts[0]):
            continue

        try:
            unit_id = int(parts[0])
        except ValueError:
            continue

        if 1 <= unit_id <= 64 and len(parts) >= 2:

            if unit_id not in unit_ids:
                unit_ids.append(unit_id)

    return sorted(unit_ids)


def _get_unit_line(output, unit_id):
    """
    Return the complete stack-table line for a Unit-ID.
    """

    if not output:
        return ""

    for line in output.splitlines():

        text = _clean_line(line)

        parts = text.split()

        if parts and parts[0] == str(unit_id):
            return text

    return ""


def _get_unit_mac(output, unit_id):
    """
    Extract MAC address from a stack-table row.

    Example:
        4  58:61:63:fa:2b:c7  member

    Returns:
        58:61:63:fa:2b:c7
    """

    line = _get_unit_line(
        output,
        unit_id,
    )

    if not line:
        return None

    mac_match = re.search(
        r"\b[0-9a-fA-F]{2}"
        r"(?::[0-9a-fA-F]{2}){5}\b",
        line,
    )

    if mac_match:
        return mac_match.group(0).lower()

    return None


def _get_stack_members(output):
    """
    Return stack members as:

        {
            unit_id: {
                "mac": "...",
                "line": "..."
            }
        }
    """

    members = {}

    if not output:
        return members

    for unit_id in _get_unit_ids(output):

        line = _get_unit_line(
            output,
            unit_id,
        )

        mac = _get_unit_mac(
            output,
            unit_id,
        )

        members[unit_id] = {
            "mac": mac,
            "line": line,
        }

    return members


def _is_controller(output, unit_id=1):
    line = _get_unit_line(
        output,
        unit_id,
    ).lower()

    return any(
        word in line
        for word in (
            "controller",
            "master",
            "active",
        )
    )


# =========================================================
# Stack Verification Helpers
# =========================================================

def _get_verified_stack_output(
    master_connection,
    master_ip,
    master_username,
    master_password,
    connection_type,
    attempts=3,
):
    """
    Get a usable show-stack output.

    Retry because asynchronous stack messages can sometimes
    interfere with the first command output.
    """

    last_output = None

    for attempt in range(1, attempts + 1):

        if attempt > 1:
            print()
            print(
                f"Retrying stack verification "
                f"({attempt}/{attempts})..."
            )

            time.sleep(2)

        (
            master_connection,
            output,
        ) = _run_master_command_with_reconnect(
            master_connection,
            "show stack",
            master_ip,
            master_username,
            master_password,
            connection_type,
            timeout=20,
        )

        last_output = output

        if _get_unit_ids(output):
            return master_connection, output

    return master_connection, last_output


# =========================================================
# Log Helpers
# =========================================================

def _log_mentions_removal(
    output,
    removed_unit_id,
    removed_mac=None,
):
    """
    Detect whether show logging contains an event related
    to the selected Unit-ID or its MAC address.
    """

    if not output:
        return False

    text = output.lower()

    unit_patterns = (
        f"unit-{removed_unit_id}",
        f"unit {removed_unit_id}",
        f"unitid {removed_unit_id}",
        f"unit id {removed_unit_id}",
        f"unit:{removed_unit_id}",
    )

    event_patterns = (
        "down",
        "removed",
        "leave",
        "offline",
        "disconnect",
        "lost",
        "link down",
        "unreachable",
    )

    unit_event_found = (
        any(p in text for p in unit_patterns)
        and any(p in text for p in event_patterns)
    )

    if unit_event_found:
        return True

    if removed_mac:
        mac = removed_mac.lower()

        if mac in text and any(
            p in text
            for p in event_patterns
        ):
            return True

    return False


# =========================================================
# Main Test Case
# =========================================================

def run_tc_stk_005(
    master_connection,
    master_ip,
    master_username,
    master_password,
    connection_type,
    expected_members=2,
    **kwargs,
):
    _print_header(
        f"{TEST_CASE_ID} - {TEST_CASE_TITLE}"
    )

    print()
    print("Objective:")
    print("  1. Remove a selected non-master member.")
    print("  2. Verify that the selected member actually leaves.")
    print("  3. Verify that Unit-1 / MASTER remains active.")
    print("  4. Observe stack logs.")
    print("  5. Verify traffic continuity.")

    print()
    print("Important:")
    print("  - Unit-1 / MASTER must remain running.")
    print("  - Only a non-master member can be selected.")
    print("  - No automatic reload is performed.")
    print("  - Physical removal is performed by the user.")
    print("  - The selected Unit-ID and MAC are recorded before removal.")
    print("  - The selected MAC must disappear from the final stack.")

    # =====================================================
    # STEP 1
    # =====================================================

    _print_step(
        1,
        "VERIFY RUNNING STACK",
    )

    (
        master_connection,
        stack_output,
    ) = _run_master_command_with_reconnect(
        master_connection,
        "show stack",
        master_ip,
        master_username,
        master_password,
        connection_type,
        timeout=20,
    )

    if not stack_output:

        _print_header(
            f"{TEST_CASE_ID} RESULT"
        )

        print()
        print("FAIL")
        print()
        print(
            "✗ No output received from "
            "'show stack'."
        )

        print()
        print("Master connection remains active.")

        return False

    initial_members = _get_stack_members(
        stack_output
    )

    initial_unit_ids = sorted(
        initial_members.keys()
    )

    if 1 not in initial_unit_ids:

        _print_header(
            f"{TEST_CASE_ID} RESULT"
        )

        print()
        print("FAIL")
        print()
        print(
            "✗ Unit-1 was not found in the "
            "running stack."
        )

        print()
        print("Master connection remains active.")

        return False

    if not _is_controller(
        stack_output,
        1,
    ):

        _print_header(
            f"{TEST_CASE_ID} RESULT"
        )

        print()
        print("FAIL")
        print()
        print(
            "✗ Unit-1 is not shown as "
            "Controller/Master."
        )

        print()
        print("Master connection remains active.")

        return False

    non_master_units = [
        unit_id
        for unit_id in initial_unit_ids
        if unit_id != 1
    ]

    print()
    print("✓ Unit-1 is Controller/Master.")

    print()
    print("Current Stack Members:")

    for unit_id in initial_unit_ids:

        line = _get_unit_line(
            stack_output,
            unit_id,
        )

        print(
            f"  Unit-{unit_id}: {line}"
        )

    if not non_master_units:

        _print_header(
            f"{TEST_CASE_ID} RESULT"
        )

        print()
        print("FAIL")
        print()
        print(
            "✗ No non-master member is "
            "available to remove."
        )

        print()
        print("Master connection remains active.")

        return False

    # =====================================================
    # STEP 2
    # =====================================================

    _print_step(
        2,
        "SELECT NON-MASTER MEMBER TO REMOVE",
    )

    print()
    print("Available non-master Unit-IDs:")

    for unit_id in non_master_units:

        line = _get_unit_line(
            stack_output,
            unit_id,
        )

        mac = _get_unit_mac(
            stack_output,
            unit_id,
        )

        print(
            f"  Unit-{unit_id}: "
            f"MAC={mac or 'Unknown'}"
        )

        print(
            f"           {line}"
        )

    while True:

        try:
            selected_unit = int(
                input(
                    "\nEnter Unit-ID to remove: "
                ).strip()
            )

        except ValueError:
            print(
                "Please enter a valid Unit-ID."
            )
            continue

        if selected_unit == 1:

            print(
                "Unit-1 is the MASTER and "
                "cannot be removed in TC-STK-005."
            )

            continue

        if selected_unit not in non_master_units:

            print(
                "Invalid selection. Choose one of: "
                + ", ".join(
                    str(x)
                    for x in non_master_units
                )
            )

            continue

        break

    # Record selected member identity
    selected_mac = _get_unit_mac(
        stack_output,
        selected_unit,
    )

    selected_line = _get_unit_line(
        stack_output,
        selected_unit,
    )

    print()
    print("Selected Member:")
    print(
        f"  Unit-ID : {selected_unit}"
    )
    print(
        f"  MAC     : "
        f"{selected_mac or 'Unknown'}"
    )
    print(
        f"  Details : {selected_line}"
    )

    # =====================================================
    # STEP 3
    # =====================================================

    _print_step(
        3,
        f"PREPARE TO REMOVE UNIT-{selected_unit}",
    )

    print()
    print("Please make sure your normal/continuous traffic")
    print("is running before removing the member.")

    print()
    print("Observe the traffic now and make sure it is healthy.")

    input(
        "\nPress ENTER when traffic is running and ready..."
    )

    print()
    print("IMPORTANT:")
    print(
        f"  • Do NOT power off Unit-1 / MASTER."
    )
    print(
        f"  • Remove Unit-{selected_unit} from "
        "the running stack."
    )
    print(
        "  • If physically removing the switch, "
        "power it OFF"
    )
    print(
        "    and disconnect its stack cable(s)."
    )
    print(
        "  • Keep the remaining stack members "
        "powered ON."
    )

    print()
    print(
        "Expected behavior:"
    )

    print(
        f"  Unit-{selected_unit} "
        "must disappear from the stack."
    )

    if selected_mac:
        print(
            f"  MAC {selected_mac} "
            "must also disappear."
        )

    input(
        f"\nPress ENTER after Unit-{selected_unit} "
        "has been removed..."
    )

    # =====================================================
    # STEP 4
    # =====================================================

    _print_step(
        4,
        f"OBSERVE UNIT-{selected_unit} REMOVAL",
    )

    print()
    print(
        f"Waiting for Unit-{selected_unit} "
        "to disappear from 'show stack'."
    )

    print(
        f"Checking every {POLL_INTERVAL} seconds, "
        f"timeout {REMOVAL_TIMEOUT} seconds."
    )

    removed = False

    wrong_member_removed = None

    latest_stack_output = stack_output

    start_time = time.time()

    while (
        time.time() - start_time
        < REMOVAL_TIMEOUT
    ):

        time.sleep(
            POLL_INTERVAL
        )

        (
            master_connection,
            latest_stack_output,
        ) = _run_master_command_with_reconnect(
            master_connection,
            "show stack",
            master_ip,
            master_username,
            master_password,
            connection_type,
            timeout=20,
        )

        current_members = _get_stack_members(
            latest_stack_output
        )

        current_units = sorted(
            current_members.keys()
        )

        print()
        print(
            "Current Stack Units: "
            + (
                ", ".join(
                    str(x)
                    for x in current_units
                )
                if current_units
                else "None"
            )
        )

        # -------------------------------------------------
        # Primary verification:
        # Selected Unit-ID must disappear
        # -------------------------------------------------

        if selected_unit not in current_units:

            # If MAC is known, verify that it also disappeared.
            current_macs = [
                info.get("mac")
                for info in current_members.values()
                if info.get("mac")
            ]

            if (
                selected_mac is None
                or selected_mac.lower()
                not in current_macs
            ):

                removed = True

                print()
                print(
                    f"✓ Unit-{selected_unit} "
                    "is no longer present."
                )

                if selected_mac:
                    print(
                        f"✓ Selected MAC "
                        f"{selected_mac} is also absent."
                    )

                break

        # -------------------------------------------------
        # Detect if another member disappeared
        # -------------------------------------------------

        initial_unit_set = set(
            initial_members.keys()
        )

        current_unit_set = set(
            current_members.keys()
        )

        disappeared_units = (
            initial_unit_set
            - current_unit_set
        )

        disappeared_units.discard(
            selected_unit
        )

        if disappeared_units:

            wrong_member_removed = sorted(
                disappeared_units
            )

            print()
            print(
                "⚠ A different stack member "
                "has disappeared:"
            )

            print(
                "  "
                + ", ".join(
                    f"Unit-{x}"
                    for x in wrong_member_removed
                )
            )

            print()
            print(
                f"✗ Selected Unit-{selected_unit} "
                "is still present."
            )

        elapsed = int(
            time.time() - start_time
        )

        print(
            f"Unit-{selected_unit} still present. "
            f"Elapsed: {elapsed}s"
        )

    # =====================================================
    # STEP 5
    # =====================================================

    _print_step(
        5,
        "OBSERVE STACK LOGS",
    )

    (
        master_connection,
        logging_output,
    ) = _run_master_command_with_reconnect(
        master_connection,
        "show logging",
        master_ip,
        master_username,
        master_password,
        connection_type,
        timeout=20,
    )

    logs_available = bool(
        logging_output
        and logging_output.strip()
    )

    removal_log_found = _log_mentions_removal(
        logging_output,
        selected_unit,
        selected_mac,
    )

    print()

    if logs_available:

        print(
            "✓ Master logging output captured."
        )

    else:

        print(
            "✗ No output received from "
            "'show logging'."
        )

    if removal_log_found:

        print(
            f"✓ Log output contains an event "
            f"related to Unit-{selected_unit} "
            "removal/down."
        )

    else:

        print(
            f"! No explicit Unit-{selected_unit} "
            "removal message was detected "
            "by the parser."
        )

        print(
            "  Review the displayed "
            "'show logging' output manually."
        )

    # =====================================================
    # STEP 6
    # =====================================================

    _print_step(
        6,
        "VERIFY TRAFFIC AFTER MEMBER REMOVAL",
    )

    print()
    print(
        "Please verify that the expected traffic "
        "is still running"
    )

    print(
        "after the non-master member was removed."
    )

    print()
    print(
        "Check your traffic generator / application / "
        "continuous traffic"
    )

    print(
        "and confirm that there was no unexpected "
        "traffic interruption."
    )

    while True:

        traffic_answer = input(
            "\nDid traffic remain healthy after "
            "member removal? (y/n): "
        ).strip().lower()

        if traffic_answer in (
            "y",
            "yes",
        ):

            traffic_ok = True
            break

        if traffic_answer in (
            "n",
            "no",
        ):

            traffic_ok = False
            break

        print(
            "Please enter y or n."
        )

    # =====================================================
    # STEP 7
    # =====================================================

    _print_step(
        7,
        "FINAL STACK VERIFICATION",
    )

    (
        master_connection,
        final_stack,
    ) = _get_verified_stack_output(
        master_connection,
        master_ip,
        master_username,
        master_password,
        connection_type,
        attempts=3,
    )

    final_members = _get_stack_members(
        final_stack
    )

    final_units = sorted(
        final_members.keys()
    )

    master_ok = _is_controller(
        final_stack,
        1,
    )

    # -----------------------------------------------------
    # Verify selected Unit-ID
    # -----------------------------------------------------

    final_selected_unit_present = (
        selected_unit in final_units
    )

    # -----------------------------------------------------
    # Verify selected MAC
    # -----------------------------------------------------

    final_selected_mac_present = False

    if selected_mac:

        for info in final_members.values():

            member_mac = info.get("mac")

            if (
                member_mac
                and member_mac.lower()
                == selected_mac.lower()
            ):

                final_selected_mac_present = True
                break

    # -----------------------------------------------------
    # Identify disappeared units
    # -----------------------------------------------------

    initial_unit_set = set(
        initial_members.keys()
    )

    final_unit_set = set(
        final_members.keys()
    )

    disappeared_units = sorted(
        initial_unit_set - final_unit_set
    )

    # -----------------------------------------------------
    # Determine final removal status
    # -----------------------------------------------------

    if selected_mac:

        final_removed = (
            not final_selected_unit_present
            and not final_selected_mac_present
        )

    else:

        final_removed = (
            not final_selected_unit_present
        )

    print()
    print("Final Stack Members:")

    if final_units:

        for unit_id in final_units:

            line = _get_unit_line(
                final_stack,
                unit_id,
            )

            print(
                f"  {line}"
            )

    else:

        print(
            "  No Unit-ID rows detected."
        )

    print()
    print("Removal Verification:")

    print(
        f"  Selected Unit-ID : "
        f"Unit-{selected_unit}"
    )

    print(
        f"  Selected MAC     : "
        f"{selected_mac or 'Unknown'}"
    )

    print(
        f"  Unit-ID present  : "
        f"{'YES' if final_selected_unit_present else 'NO'}"
    )

    if selected_mac:

        print(
            f"  MAC present      : "
            f"{'YES' if final_selected_mac_present else 'NO'}"
        )

    if disappeared_units:

        print()
        print(
            "Members that disappeared "
            "from the initial stack:"
        )

        for unit_id in disappeared_units:

            print(
                f"  Unit-{unit_id}"
            )

    # =====================================================
    # FINAL RESULT
    # =====================================================

    _print_header(
        f"{TEST_CASE_ID} RESULT"
    )

    print()

    if (
        final_removed
        and master_ok
        and traffic_ok
    ):

        print("PASS")
        print()

        print(
            f"✓ Selected Unit-{selected_unit} "
            "was removed from the running stack."
        )

        if selected_mac:

            print(
                f"✓ Selected MAC {selected_mac} "
                "is no longer present."
            )

        print(
            "✓ Unit-1 remained "
            "Controller/Master."
        )

        if logs_available:

            print(
                "✓ Master log output was captured."
            )

        print(
            "✓ Traffic was confirmed healthy "
            "by the user."
        )

        print()
        print(
            "Master connection remains active."
        )

        return True

    # -----------------------------------------------------
    # FAIL RESULT
    # -----------------------------------------------------

    print("FAIL")
    print()

    if final_selected_unit_present:

        print(
            f"✗ Selected Unit-{selected_unit} "
            "is still present in the final "
            "'show stack'."
        )

    if (
        selected_mac
        and final_selected_mac_present
    ):

        print(
            f"✗ Selected MAC {selected_mac} "
            "is still present in the final stack."
        )

    if disappeared_units:

        print()

        print(
            "✗ The following member(s) disappeared "
            "instead of the selected member:"
        )

        for unit_id in disappeared_units:

            print(
                f"  Unit-{unit_id}"
            )

    if not master_ok:

        print(
            "✗ Unit-1 is not shown as "
            "Controller/Master."
        )

    if not logs_available:

        print(
            "✗ No output received from "
            "'show logging'."
        )

    if not traffic_ok:

        print(
            "✗ User reported traffic "
            "interruption/degradation."
        )

    print()
    print(
        "Master connection remains active."
    )

    return False