
import time
import re


# =========================================================
# TC-STK-017
# Stack Event / Log Verification
#
# Events:
#   1. Member Join
#   2. Member Leave
#   3. MASTER Change
#   4. Stack Link Failure
#   5. Upgrade
#
# IMPORTANT:
#   - This testcase does NOT use SNMP traps.
#   - It only checks the switch's own "show logging" output.
#   - Existing testcase files are not modified.
# =========================================================

TEST_CASE_ID = "TC-STK-017"

SHOW_STACK_COMMAND = "do show stack"
SHOW_LOG_COMMAND = "show logging"

STACK_WAIT_TIME = 10
MASTER_RECOVERY_WAIT = 25
LOG_CHECK_WAIT = 5


# =========================================================
# ROS7 LOG SIGNATURES
# =========================================================

# Member Join / Stack Link Recovery
MEMBER_JOIN_PATTERNS = [
    r"%cscdlag-i-up:\s*stack port\s+\S+\s+operational status is up",
    r"%cscdlag-i-active:\s*stack port\s+\S+\s+is active in stack lag",
    r"%stck\s+sysl-i-unitmsg:.*%cscdlag-i-up:",
    r"%stck\s+sysl-i-unitmsg:.*%cscdlag-i-active:",
    r"%cscdlag-w-cfg-chng:.*chain to ring",
    r"%cscdlag-i-cfg-chng:.*chain to ring",
    r"%cscdlag-w-cfg-chng:.*ring to chain",
    r"%cscdlag-i-cfg-chng:.*ring to chain",
]

# Member Leave / Stack Link Down
MEMBER_LEAVE_PATTERNS = [
    r"%cscdlag-w-down:\s*stack port\s+\S+\s+operational status is down",
    r"%stck\s+sysl-w-unitmsg:.*%cscdlag-w-down:",
    r"%cscdlag-w-cfg-chng:.*ring to chain",
    r"%cscdlag-i-cfg-chng:.*ring to chain",
]

# Master / Controller change
MASTER_CHANGE_PATTERNS = [
    r"%stck.*controller",
    r"%stck.*backup",
    r"%stck.*master",
    r"controller.*backup",
    r"backup.*controller",
    r"master.*change",
    r"controller.*change",
    r"role.*change",
]

# Stack link failure
STACK_LINK_FAILURE_PATTERNS = [
    r"%cscdlag-w-down:\s*stack port\s+\S+\s+operational status is down",
    r"%stck\s+sysl-w-unitmsg:.*%cscdlag-w-down:",
    r"stack port\s+\S+\s+operational status is down",
]

# Stack link recovery
STACK_LINK_RECOVERY_PATTERNS = [
    r"%cscdlag-i-up:\s*stack port\s+\S+\s+operational status is up",
    r"%cscdlag-i-active:\s*stack port\s+\S+\s+is active in stack lag",
    r"%stck\s+sysl-i-unitmsg:.*%cscdlag-i-up:",
    r"%stck\s+sysl-i-unitmsg:.*%cscdlag-i-active:",
]

# Upgrade
#
# ROS7 releases can produce different messages depending on
# platform / upgrade mechanism. We intentionally do NOT use
# generic words such as "software", "version", or "reload"
# alone because those can appear during normal operation.
UPGRADE_PATTERNS = [
    r"upgrade",
    r"firmware upgrade",
    r"software upgrade",
    r"image upgrade",
    r"install.*image",
    r"install.*firmware",
    r"upgrade.*image",
    r"upgrade.*firmware",
]


# =========================================================
# PRINT HEADER
# =========================================================

def _print_header(title):

    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


# =========================================================
# SEND COMMAND
# =========================================================

def _send_command(connection, command):

    try:

        if connection is None:
            return ""

        if hasattr(connection, "send_command"):

            output = connection.send_command(command)

            if output is None:
                return ""

            return str(output)

        if hasattr(connection, "send"):

            output = connection.send(command)

            if output is None:
                return ""

            return str(output)

        if hasattr(connection, "execute"):

            output = connection.execute(command)

            if output is None:
                return ""

            return str(output)

    except Exception as e:

        print()
        print(f"Command execution error: {e}")

    return ""


# =========================================================
# RUN COMMAND
# =========================================================

def _run_command(connection, command):

    print()
    print(f"[>] {command}")
    print()

    output = _send_command(
        connection,
        command
    )

    if output:
        print(output)

    return output


# =========================================================
# PARSE STACK MEMBERS
# =========================================================

def _parse_stack_members(output):

    members = []

    if not output:
        return members

    pattern = re.compile(
        r"^\s*(\d+)\s+"
        r"([0-9A-Fa-f:]{17})\s+"
        r"([A-Za-z_-]+)"
        r"(?:\s+.*)?$",
        re.IGNORECASE
    )

    for line in output.splitlines():

        match = pattern.match(
            line.strip()
        )

        if not match:
            continue

        try:

            unit_id = int(
                match.group(1)
            )

        except ValueError:

            continue

        if unit_id < 1 or unit_id > 64:
            continue

        if any(
            item["unit_id"] == unit_id
            for item in members
        ):
            continue

        members.append(
            {
                "unit_id": unit_id,
                "mac": match.group(2),
                "role": match.group(3).lower()
            }
        )

    return sorted(
        members,
        key=lambda x: x["unit_id"]
    )


# =========================================================
# DISPLAY STACK MEMBERS
# =========================================================

def _display_stack_members(members):

    print()

    if not members:

        print(
            "No stack members detected."
        )

        return

    print(
        f"Detected stack members: {len(members)}"
    )

    print()

    for member in members:

        print(
            f"Unit-ID {member['unit_id']} : "
            f"{member['role'].upper()} : "
            f"{member['mac']}"
        )


# =========================================================
# GET STACK STATE
# =========================================================

def _get_stack_state(connection):

    output = _run_command(
        connection,
        SHOW_STACK_COMMAND
    )

    members = _parse_stack_members(
        output
    )

    return members, output


# =========================================================
# SHOW CURRENT LOG
# =========================================================

def _get_logging(connection):

    print()
    print("=" * 70)
    print("                 SWITCH SYSTEM LOG")
    print("=" * 70)

    output = _run_command(
        connection,
        SHOW_LOG_COMMAND
    )

    if not output:

        print()
        print(
            "WARNING: No logging output received."
        )

    return output


# =========================================================
# NORMALIZE LOG
# =========================================================

def _normalize_log(output):

    if not output:
        return ""

    return output.lower()


# =========================================================
# FIND ROS7 LOG SIGNATURES
# =========================================================

def _find_log_signatures(
    log_output,
    patterns
):

    if not log_output:
        return []

    normalized = _normalize_log(
        log_output
    )

    found = []

    for pattern in patterns:

        try:

            match = re.search(
                pattern,
                normalized,
                re.IGNORECASE
            )

        except re.error:

            continue

        if match:

            matched_text = match.group(0).strip()

            if matched_text not in found:
                found.append(
                    matched_text
                )

    return found


# =========================================================
# FIND MATCHING LOG LINES
# =========================================================

def _find_matching_log_lines(
    log_output,
    patterns
):

    if not log_output:
        return []

    matching_lines = []

    for line in log_output.splitlines():

        stripped = line.strip()

        if not stripped:
            continue

        normalized_line = stripped.lower()

        for pattern in patterns:

            try:

                if re.search(
                    pattern,
                    normalized_line,
                    re.IGNORECASE
                ):

                    if stripped not in matching_lines:

                        matching_lines.append(
                            stripped
                        )

                    break

            except re.error:

                continue

    return matching_lines


# =========================================================
# DISPLAY ROS7 LOG MATCH RESULT
# =========================================================

def _display_ros7_log_result(
    event_name,
    patterns,
    log_output
):

    print()
    print("=" * 70)
    print(
        f"LOG VERIFICATION - {event_name}"
    )
    print("=" * 70)

    if not log_output:

        print()
        print(
            "No switch log output received."
        )

        print()
        print(
            f"{event_name} LOG : FAIL"
        )

        return False

    matching_lines = _find_matching_log_lines(
        log_output,
        patterns
    )

    print()
    print(
        "ROS7 log signatures checked:"
    )

    for pattern in patterns:

        print(
            f"  - {pattern}"
        )

    print()

    if matching_lines:

        print(
            "Matching ROS7 log messages found:"
        )

        print()

        for line in matching_lines:

            print(
                f"  + {line}"
            )

        print()

        print(
            f"{event_name} LOG : PASS"
        )

        return True

    print(
        "No expected ROS7 event log message "
        "was found."
    )

    print()

    print(
        f"{event_name} LOG : FAIL"
    )

    return False


# =========================================================
# WAIT
# =========================================================

def _wait_seconds(seconds):

    print()

    print(
        f"Waiting {seconds} seconds..."
    )

    for remaining in range(
        seconds,
        0,
        -1
    ):

        print(
            f"\rRemaining: {remaining:02d} seconds",
            end="",
            flush=True
        )

        time.sleep(1)

    print()


# =========================================================
# WAIT FOR USER
# =========================================================

def _wait_for_user(message):

    print()

    input(
        message
    )


# =========================================================
# MEMBER JOIN
# =========================================================

def _test_member_join(
    connection,
    initial_members
):

    _print_header(
        "1. MEMBER JOIN"
    )

    print()
    print(
        "Current stack members:"
    )

    _display_stack_members(
        initial_members
    )

    print()
    print(
        "ACTION REQUIRED:"
    )

    print(
        "Reconnect / add the stack member cable."
    )

    print(
        "The member should join the running stack."
    )

    _wait_for_user(
        "\nPress ENTER after reconnecting the member..."
    )

    _wait_seconds(
        STACK_WAIT_TIME
    )

    print()
    print(
        "Checking stack membership..."
    )

    members_after, stack_output = (
        _get_stack_state(
            connection
        )
    )

    _display_stack_members(
        members_after
    )

    # -----------------------------------------------------
    # IMPORTANT:
    # Do NOT require member count to increase.
    #
    # A member may already be present in the stack table
    # while the physical stack link is disconnected/reconnected.
    #
    # The actual ROS7 event log is the primary indication
    # of the join/recovery event.
    # -----------------------------------------------------

    initial_unit_ids = {
        member["unit_id"]
        for member in initial_members
    }

    after_unit_ids = {
        member["unit_id"]
        for member in members_after
    }

    new_unit_ids = (
        after_unit_ids
        - initial_unit_ids
    )

    if new_unit_ids:

        print()
        print(
            "New stack member detected:"
        )

        print(
            "  Unit-ID(s): "
            + ", ".join(
                str(unit_id)
                for unit_id in sorted(new_unit_ids)
            )
        )

    else:

        print()
        print(
            "No new Unit-ID appeared."
        )

        print(
            "Continuing because MEMBER JOIN is "
            "verified using the ROS7 event logs."
        )

    print()
    print(
        "Waiting before checking switch logs..."
    )

    _wait_seconds(
        LOG_CHECK_WAIT
    )

    log_output = _get_logging(
        connection
    )

    log_pass = _display_ros7_log_result(
        "MEMBER JOIN",
        MEMBER_JOIN_PATTERNS,
        log_output
    )

    # -----------------------------------------------------
    # Stack state must still contain the original members.
    # The count does not have to increase.
    # -----------------------------------------------------

    stack_state_pass = True

    for unit_id in initial_unit_ids:

        if unit_id not in after_unit_ids:

            stack_state_pass = False

            print()
            print(
                f"WARNING: Previously detected Unit-ID "
                f"{unit_id} is missing after join."
            )

    result = (
        stack_state_pass
        and log_pass
    )

    print()
    print(
        "MEMBER JOIN RESULT : "
        + (
            "PASS"
            if result
            else "FAIL"
        )
    )

    return result, members_after


# =========================================================
# MEMBER LEAVE
# =========================================================

def _test_member_leave(
    connection,
    current_members
):

    _print_header(
        "2. MEMBER LEAVE"
    )

    print()
    print(
        "Current stack members:"
    )

    _display_stack_members(
        current_members
    )

    if len(current_members) < 2:

        print()
        print(
            "ERROR: At least two stack members "
            "are required for member-leave testing."
        )

        return False, current_members

    print()
    print(
        "ACTION REQUIRED:"
    )

    print(
        "Disconnect the stack cable of one "
        "non-MASTER member."
    )

    print()
    print(
        "IMPORTANT:"
    )

    print(
        "Do NOT disconnect Unit-ID 1 / MASTER."
    )

    _wait_for_user(
        "\nPress ENTER after disconnecting the member..."
    )

    _wait_seconds(
        STACK_WAIT_TIME
    )

    print()
    print(
        "Checking stack membership..."
    )

    members_after, stack_output = (
        _get_stack_state(
            connection
        )
    )

    _display_stack_members(
        members_after
    )

    current_unit_ids = {
        member["unit_id"]
        for member in current_members
    }

    after_unit_ids = {
        member["unit_id"]
        for member in members_after
    }

    missing_unit_ids = (
        current_unit_ids
        - after_unit_ids
    )

    if missing_unit_ids:

        print()
        print(
            "Stack member leave detected."
        )

        print(
            "Missing Unit-ID(s): "
            + ", ".join(
                str(unit_id)
                for unit_id in sorted(missing_unit_ids)
            )
        )

    else:

        print()
        print(
            "WARNING: No Unit-ID disappeared from "
            "the current stack table."
        )

        print(
            "The ROS7 log will be used to verify "
            "the member/link leave event."
        )

    print()
    print(
        "Waiting before checking switch logs..."
    )

    _wait_seconds(
        LOG_CHECK_WAIT
    )

    log_output = _get_logging(
        connection
    )

    log_pass = _display_ros7_log_result(
        "MEMBER LEAVE",
        MEMBER_LEAVE_PATTERNS,
        log_output
    )

    # A member-leave event is considered successful
    # when either the member disappears OR the ROS7
    # member/link-down event is logged.
    stack_state_pass = bool(missing_unit_ids)

    result = (
        stack_state_pass
        and log_pass
    )

    print()
    print(
        "MEMBER LEAVE RESULT : "
        + (
            "PASS"
            if result
            else "FAIL"
        )
    )

    return result, members_after


# =========================================================
# MASTER CHANGE
# =========================================================

def _test_master_change(
    connection,
    current_members
):

    _print_header(
        "3. MASTER CHANGE"
    )

    print()
    print(
        "Current stack state:"
    )

    _display_stack_members(
        current_members
    )

    print()
    print(
        "ACTION REQUIRED:"
    )

    print(
        "Trigger the MASTER/controller change "
        "using your supported stack procedure."
    )

    print()
    print(
        "For example, perform the supported "
        "MASTER/controller failover procedure."
    )

    print()

    _wait_for_user(
        "Press ENTER after MASTER change has been triggered..."
    )

    _wait_seconds(
        MASTER_RECOVERY_WAIT
    )

    print()
    print(
        "Checking stack after MASTER change..."
    )

    members_after, stack_output = (
        _get_stack_state(
            connection
        )
    )

    _display_stack_members(
        members_after
    )

    controller_units = [
        member
        for member in members_after
        if "controller" in member["role"]
        or "master" in member["role"]
    ]

    backup_units = [
        member
        for member in members_after
        if "backup" in member["role"]
    ]

    if controller_units:

        print()
        print(
            "Current controller/master Unit-ID(s): "
            + ", ".join(
                str(member["unit_id"])
                for member in controller_units
            )
        )

        stack_state_pass = True

    else:

        print()
        print(
            "WARNING: No controller/master role "
            "was detected in show stack."
        )

        stack_state_pass = False

    if backup_units:

        print()
        print(
            "Current backup Unit-ID(s): "
            + ", ".join(
                str(member["unit_id"])
                for member in backup_units
            )
        )

    print()
    print(
        "Waiting before checking switch logs..."
    )

    _wait_seconds(
        LOG_CHECK_WAIT
    )

    log_output = _get_logging(
        connection
    )

    log_pass = _display_ros7_log_result(
        "MASTER CHANGE",
        MASTER_CHANGE_PATTERNS,
        log_output
    )

    result = (
        stack_state_pass
        and log_pass
    )

    print()
    print(
        "MASTER CHANGE RESULT : "
        + (
            "PASS"
            if result
            else "FAIL"
        )
    )

    return result, members_after


# =========================================================
# STACK LINK FAILURE
# =========================================================

def _test_stack_link_failure(
    connection
):

    _print_header(
        "4. STACK LINK FAILURE"
    )

    print()
    print(
        "ACTION REQUIRED:"
    )

    print(
        "Disconnect ONE stack link cable."
    )

    print()
    print(
        "Keep at least one other stack link active "
        "so the stack remains reachable."
    )

    print()

    _wait_for_user(
        "Press ENTER after disconnecting the stack link..."
    )

    _wait_seconds(
        STACK_WAIT_TIME
    )

    print()
    print(
        "Checking switch logs..."
    )

    log_output = _get_logging(
        connection
    )

    failure_result = _display_ros7_log_result(
        "STACK LINK FAILURE",
        STACK_LINK_FAILURE_PATTERNS,
        log_output
    )

    print()
    print(
        "ACTION REQUIRED:"
    )

    print(
        "Reconnect the disconnected stack link."
    )

    _wait_for_user(
        "\nPress ENTER after reconnecting the stack link..."
    )

    _wait_seconds(
        STACK_WAIT_TIME
    )

    print()
    print(
        "Checking recovery logs..."
    )

    recovery_log = _get_logging(
        connection
    )

    recovery_pass = _display_ros7_log_result(
        "STACK LINK RECOVERY",
        STACK_LINK_RECOVERY_PATTERNS,
        recovery_log
    )

    final_result = (
        failure_result
        and recovery_pass
    )

    print()
    print(
        "STACK LINK FAILURE RESULT : "
        + (
            "PASS"
            if final_result
            else "FAIL"
        )
    )

    return final_result


# =========================================================
# UPGRADE
# =========================================================

def _test_upgrade(
    connection
):

    _print_header(
        "5. UPGRADE"
    )

    print()
    print(
        "ACTION REQUIRED:"
    )

    print(
        "Perform the supported switch/stack "
        "upgrade procedure."
    )

    print()
    print(
        "This testcase does NOT automatically upload "
        "or install firmware."
    )

    print(
        "It only verifies the switch logs after "
        "the upgrade operation."
    )

    print()

    _wait_for_user(
        "Press ENTER after the upgrade operation is completed..."
    )

    print()
    print(
        "Waiting for the switch/stack to stabilize..."
    )

    _wait_seconds(
        MASTER_RECOVERY_WAIT
    )

    print()
    print(
        "Checking stack state after upgrade..."
    )

    members_after, stack_output = (
        _get_stack_state(
            connection
        )
    )

    _display_stack_members(
        members_after
    )

    stack_pass = (
        len(members_after) >= 2
    )

    if stack_pass:

        print()
        print(
            "Stack is still formed after upgrade."
        )

    else:

        print()
        print(
            "WARNING: Stack members were not detected "
            "after upgrade."
        )

    print()
    print(
        "Checking switch logs..."
    )

    log_output = _get_logging(
        connection
    )

    log_pass = _display_ros7_log_result(
        "UPGRADE",
        UPGRADE_PATTERNS,
        log_output
    )

    result = (
        stack_pass
        and log_pass
    )

    print()
    print(
        "UPGRADE RESULT : "
        + (
            "PASS"
            if result
            else "FAIL"
        )
    )

    return result, members_after


# =========================================================
# FINAL RESULT
# =========================================================

def _display_final_result(
    member_join,
    member_leave,
    master_change,
    stack_link_failure,
    upgrade
):

    _print_header(
        "             TC-STK-017 RESULT"
    )

    print()

    print(
        "Member Join          : "
        + (
            "PASS"
            if member_join
            else "FAIL"
        )
    )

    print(
        "Member Leave         : "
        + (
            "PASS"
            if member_leave
            else "FAIL"
        )
    )

    print(
        "MASTER Change        : "
        + (
            "PASS"
            if master_change
            else "FAIL"
        )
    )

    print(
        "Stack Link Failure   : "
        + (
            "PASS"
            if stack_link_failure
            else "FAIL"
        )
    )

    print(
        "Upgrade              : "
        + (
            "PASS"
            if upgrade
            else "FAIL"
        )
    )

    overall = (
        member_join
        and member_leave
        and master_change
        and stack_link_failure
        and upgrade
    )

    print()

    print("=" * 70)

    print(
        "TC-STK-017 : "
        + (
            "PASS"
            if overall
            else "FAIL"
        )
    )

    print("=" * 70)

    print()

    return overall


# =========================================================
# TC-STK-017
# =========================================================

def run_tc_stk_017(
    master_connection=None,
    connection=None,
    expected_members=None,
    member_count=None,
    **kwargs
):

    active_connection = (
        master_connection
        if master_connection is not None
        else connection
    )

    if active_connection is None:

        print()
        print(
            "ERROR: Unit-ID 1 / MASTER connection "
            "is not available."
        )

        return False

    # =====================================================
    # HEADER
    # =====================================================

    _print_header(
        "       TC-STK-017 - STACK EVENT LOG VERIFICATION"
    )

    print()

    print(
        "This testcase verifies stack events using "
        "the switch's own system logs."
    )

    print()

    print(
        "SNMP traps are NOT used."
    )

    print(
        "Only the following switch commands are used:"
    )

    print(
        f"  - {SHOW_STACK_COMMAND}"
    )

    print(
        f"  - {SHOW_LOG_COMMAND}"
    )

    # =====================================================
    # INITIAL STACK CHECK
    # =====================================================

    _print_header(
        "INITIAL STACK STATE"
    )

    initial_members, initial_output = (
        _get_stack_state(
            active_connection
        )
    )

    _display_stack_members(
        initial_members
    )

    if len(initial_members) < 2:

        print()
        print(
            "ERROR: TC-STK-017 requires a running "
            "stack with at least 2 members."
        )

        print()
        print(
            "TC-STK-017 : FAIL"
        )

        return False

    # =====================================================
    # OPTIONAL EXPECTED MEMBER COUNT
    # =====================================================

    if expected_members is not None:

        try:

            expected = int(
                expected_members
            )

            if len(initial_members) != expected:

                print()
                print(
                    f"WARNING: Expected {expected} "
                    f"members but detected "
                    f"{len(initial_members)}."
                )

                print(
                    "Continuing with the actual "
                    "stack membership."
                )

        except (
            ValueError,
            TypeError
        ):

            pass

    # =====================================================
    # STEP 1 - MEMBER JOIN
    # =====================================================

    member_join_pass, members_after_join = (
        _test_member_join(
            active_connection,
            initial_members
        )
    )

    # =====================================================
    # STEP 2 - MEMBER LEAVE
    # =====================================================

    member_leave_pass, members_after_leave = (
        _test_member_leave(
            active_connection,
            members_after_join
        )
    )

    # =====================================================
    # STEP 3 - MASTER CHANGE
    # =====================================================

    master_change_pass, members_after_master = (
        _test_master_change(
            active_connection,
            members_after_leave
        )
    )

    # =====================================================
    # STEP 4 - STACK LINK FAILURE
    # =====================================================

    stack_link_failure_pass = (
        _test_stack_link_failure(
            active_connection
        )
    )

    # =====================================================
    # STEP 5 - UPGRADE
    # =====================================================

    upgrade_pass, final_members = (
        _test_upgrade(
            active_connection
        )
    )

    # =====================================================
    # FINAL RESULT
    # =====================================================

    result = _display_final_result(
        member_join_pass,
        member_leave_pass,
        master_change_pass,
        stack_link_failure_pass,
        upgrade_pass
    )

    print()

    print(
        "Final detected stack members: "
        f"{len(final_members)}"
    )

    print()

    print(
        "Unit-ID 1 / MASTER connection "
        "remains active."
    )

    return result

