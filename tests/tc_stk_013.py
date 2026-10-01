
import time
import re


# =========================================================
# TC-STK-013
# Reboot One Stack Member and Verify Automatic Rejoin
# =========================================================

TEST_CASE_ID = "TC-STK-013"

SHOW_STACK_COMMAND = "do show stack"
SHOW_LOG_COMMAND = "show logging"

LOG_POLL_INTERVAL = 3

MEMBER_REMOVAL_TIMEOUT = 180
MEMBER_REJOIN_TIMEOUT = 300

# After a rejoin-related log is detected, wait a little
# before running final "show stack" so the stack has time
# to complete its membership/role synchronization.
STACK_SETTLE_TIME = 10


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

        print(
            f"\nCommand execution error: {e}"
        )

    return ""


# =========================================================
# RUN COMMAND WITH DISPLAY
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
        r"^\s*"
        r"(\d+)"
        r"\s+"
        r"([0-9A-Fa-f:]{17})"
        r"\s+"
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

        mac = match.group(2)
        role = match.group(3).lower()

        if any(
            item["unit_id"] == unit_id
            for item in members
        ):
            continue

        members.append({

            "unit_id":
                unit_id,

            "mac":
                mac,

            "role":
                role
        })

    return members


# =========================================================
# PRINT STACK MEMBERS
# =========================================================

def _print_stack_members(members):

    if not members:

        print(
            "No stack members were parsed."
        )

        return

    print()
    print(
        "Current Stack Members:"
    )

    for member in members:

        print(
            f"  Unit-ID {member['unit_id']} "
            f"Role: {member['role']:<10} "
            f"MAC: {member['mac']}"
        )


# =========================================================
# GET NON-MASTER MEMBERS
# =========================================================

def _get_non_master_members(members):

    result = []

    for member in members:

        unit_id = member["unit_id"]
        role = member["role"].lower()

        if unit_id == 1:
            continue

        if role in (
            "controller",
            "master"
        ):
            continue

        result.append(member)

    return result


# =========================================================
# SELECT MEMBER
# =========================================================

def _select_member_to_reboot(
    non_master_members
):

    if not non_master_members:

        print()
        print(
            "ERROR: No non-master member found."
        )

        return None

    print()
    print("=" * 70)
    print(
        "          SELECT NON-MASTER MEMBER TO REBOOT"
    )
    print("=" * 70)

    print()

    for index, member in enumerate(
        non_master_members,
        start=1
    ):

        print(
            f"{index}. "
            f"Unit-ID {member['unit_id']}  "
            f"Role: {member['role']}  "
            f"MAC: {member['mac']}"
        )

    print()

    while True:

        choice = input(
            "Select member to reboot: "
        ).strip()

        try:

            number = int(choice)

        except ValueError:

            print(
                "Please enter a valid number."
            )

            continue

        if (
            number < 1
            or number > len(non_master_members)
        ):

            print(
                "Invalid selection."
            )

            continue

        return non_master_members[
            number - 1
        ]


# =========================================================
# NORMALIZE LOG
# =========================================================

def _normalize_log(text):

    if not text:
        return ""

    text = str(text)

    # Remove ANSI escape sequences
    text = re.sub(
        r"\x1b\[[0-9;?]*[ -/]*[@-~]",
        "",
        text
    )

    return text.lower()


# =========================================================
# GET LOG
# =========================================================

def _get_logging(connection):

    return _send_command(
        connection,
        SHOW_LOG_COMMAND
    )


# =========================================================
# CHECK MEMBER REMOVAL
# =========================================================

def _member_removed_from_log(
    log_text,
    unit_id
):

    text = _normalize_log(
        log_text
    )

    if not text:
        return False

    patterns = [

        rf"unit\s+{unit_id}\s+was\s+removed\s+from\s+the\s+stack",

        rf"unit\s+{unit_id}\s+was\s+removed",

        rf"unit\s+id\s+{unit_id}.*removed",

        rf"member.*unit\s+{unit_id}.*removed",

        rf"unit\s+{unit_id}.*not\s+present",

        rf"unit\s+{unit_id}.*offline"
    ]

    for pattern in patterns:

        if re.search(
            pattern,
            text,
            re.IGNORECASE
        ):

            return True

    return False


# =========================================================
# CHECK REJOIN ACTIVITY
# =========================================================

def _member_rejoin_activity(
    log_text,
    unit_id
):

    text = _normalize_log(
        log_text
    )

    if not text:
        return False

    # -----------------------------------------------------
    # Important:
    #
    # Do NOT require one exact log line.
    #
    # Different ROS versions can print different
    # messages during stack member rejoin.
    # -----------------------------------------------------

    patterns = [

        # Direct selected unit messages
        rf"unit\s+id\s+{unit_id}.*connection.*established",

        rf"unit\s+id\s+{unit_id}.*member.*mode",

        rf"unit\s+id\s+{unit_id}.*initialization.*completed",

        rf"unit\s+id\s+{unit_id}.*active",

        rf"unit\s+id\s+{unit_id}.*operational\s+status\s+is\s+up",

        rf"unit\s+id\s+{unit_id}.*stack\s+port.*active",

        rf"unit\s+id\s+{unit_id}.*stack\s+port.*up",

        rf"unit\s+id\s+{unit_id}.*joined",

        rf"unit\s+id\s+{unit_id}.*rejoin",

        # Generic stack membership messages
        rf"unit\s+{unit_id}.*joined.*stack",

        rf"unit\s+{unit_id}.*rejoin",

        rf"unit\s+{unit_id}.*active",

        rf"unit\s+{unit_id}.*operational\s+status.*up",

        # Stack port activation
        rf"stack\s+port.*active",

        rf"stack\s+port.*operational\s+status\s+is\s+up",

        # Member mode
        r"switching\s+to\s+the\s+member\s+mode",

        # Initialization
        r"initialization\s+task\s+is\s+completed",

        # Connection established
        r"connection\s+to\s+unit\s+1\s+is\s+established"
    ]

    for pattern in patterns:

        if re.search(
            pattern,
            text,
            re.IGNORECASE
        ):

            return True

    return False


# =========================================================
# WAIT FOR REMOVAL
# =========================================================

def _wait_for_member_removal(
    connection,
    unit_id
):

    print()
    print("=" * 70)
    print(
        f"       MONITORING UNIT-1 FOR UNIT-{unit_id} REMOVAL"
    )
    print("=" * 70)

    print()
    print(
        "Unit-ID 1 / MASTER is being monitored."
    )

    print(
        "Waiting for the selected member removal event..."
    )

    start_time = time.time()

    while (
        time.time() - start_time
        < MEMBER_REMOVAL_TIMEOUT
    ):

        try:

            log_output = _get_logging(
                connection
            )

            if _member_removed_from_log(
                log_output,
                unit_id
            ):

                print()
                print(
                    f"Unit-ID {unit_id} removal event "
                    "detected in Unit-1 log."
                )

                return True

        except Exception as e:

            print(
                f"\nLog monitoring error: {e}"
            )

        elapsed = int(
            time.time() - start_time
        )

        print(
            f"\rWaiting for Unit-ID {unit_id} "
            f"removal event... {elapsed}s",
            end="",
            flush=True
        )

        time.sleep(
            LOG_POLL_INTERVAL
        )

    print()

    print()
    print(
        "WARNING:"
    )

    print(
        f"Unit-ID {unit_id} removal event "
        "was not detected within the timeout."
    )

    return False


# =========================================================
# WAIT FOR REJOIN ACTIVITY
# =========================================================

def _wait_for_member_rejoin(
    connection,
    unit_id
):

    print()
    print("=" * 70)
    print(
        f"       MONITORING UNIT-1 FOR UNIT-{unit_id} REJOIN"
    )
    print("=" * 70)

    print()
    print(
        "Unit-ID 1 / MASTER log monitoring started."
    )

    print()
    print(
        "The script will accept any valid stack "
        "rejoin activity."
    )

    print()
    print(
        "Examples:"
    )

    print(
        "  - Connection to Unit 1 is established"
    )

    print(
        "  - Switching to member mode"
    )

    print(
        "  - Stack port becomes active"
    )

    print(
        "  - Stack port operational status is UP"
    )

    print(
        "  - Initialization completed"
    )

    print()

    start_time = time.time()

    while (
        time.time() - start_time
        < MEMBER_REJOIN_TIMEOUT
    ):

        try:

            log_output = _get_logging(
                connection
            )

            if _member_rejoin_activity(
                log_output,
                unit_id
            ):

                print()
                print(
                    "Stack rejoin activity detected "
                    "in Unit-1 log."
                )

                return True

        except Exception as e:

            print(
                f"\nLog monitoring error: {e}"
            )

        elapsed = int(
            time.time() - start_time
        )

        print(
            f"\rWaiting for Unit-ID {unit_id} "
            f"rejoin activity... {elapsed}s",
            end="",
            flush=True
        )

        time.sleep(
            LOG_POLL_INTERVAL
        )

    print()

    print()
    print(
        "WARNING:"
    )

    print(
        f"No specific Unit-ID {unit_id} "
        "rejoin log was captured."
    )

    print(
        "The final 'do show stack' verification "
        "will now determine the actual result."
    )

    # -----------------------------------------------------
    # IMPORTANT:
    #
    # Do not fail TC here.
    #
    # The switch may have completed the rejoin while
    # the polling command returned only part of the log.
    # -----------------------------------------------------

    return False


# =========================================================
# VERIFY UNIT IN STACK
# =========================================================

def _verify_unit_in_stack(
    stack_output,
    unit_id
):

    members = _parse_stack_members(
        stack_output
    )

    for member in members:

        if member["unit_id"] == unit_id:

            return True, members

    return False, members


# =========================================================
# WAIT FOR FINAL STACK
# =========================================================

def _wait_for_final_stack(
    connection,
    unit_id,
    expected_members
):

    print()
    print("=" * 70)
    print(
        "       WAITING FOR FINAL STACK FORMATION"
    )
    print("=" * 70)

    print()

    start_time = time.time()

    last_members = []

    while (
        time.time() - start_time
        < MEMBER_REJOIN_TIMEOUT
    ):

        output = _send_command(
            connection,
            SHOW_STACK_COMMAND
        )

        found, members = _verify_unit_in_stack(
            output,
            unit_id
        )

        last_members = members

        if found:

            # -------------------------------------------------
            # If expected member count is known, wait until
            # the complete stack is visible.
            # -------------------------------------------------

            if expected_members is not None:

                if len(members) >= expected_members:

                    print()
                    print(
                        f"Unit-ID {unit_id} is present "
                        "in the final stack."
                    )

                    print(
                        f"Detected {len(members)} "
                        "stack members."
                    )

                    return True, members

            else:

                print()
                print(
                    f"Unit-ID {unit_id} is present "
                    "in the final stack."
                )

                return True, members

        elapsed = int(
            time.time() - start_time
        )

        print(
            f"\rWaiting for Unit-ID {unit_id} "
            f"to appear in stack... {elapsed}s",
            end="",
            flush=True
        )

        time.sleep(
            LOG_POLL_INTERVAL
        )

    print()

    return False, last_members


# =========================================================
# TC-STK-013
# =========================================================

def run_tc_stk_013(
    master_connection=None,
    connection=None,
    master_ip=None,
    master_username=None,
    master_password=None,
    connection_type=None,
    expected_members=None,
    member_count=None,
    **kwargs
):

    # =====================================================
    # ACTIVE MASTER CONNECTION
    # =====================================================

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
    # EXPECTED MEMBER COUNT
    # =====================================================

    if expected_members is None:

        expected_members = member_count

    # =====================================================
    # HEADER
    # =====================================================

    _print_header(
        "       TC-STK-013 - REBOOT ONE STACK MEMBER"
    )

    # =====================================================
    # STEP 1
    # =====================================================

    print()
    print(
        "STEP 1: CHECK STACK BEFORE MEMBER REBOOT"
    )

    before_output = _run_command(
        active_connection,
        SHOW_STACK_COMMAND
    )

    before_members = _parse_stack_members(
        before_output
    )

    if not before_members:

        print()
        print(
            "ERROR: Unable to determine current "
            "stack members."
        )

        return False

    _print_stack_members(
        before_members
    )

    # -----------------------------------------------------
    # Verify Unit-ID 1
    # -----------------------------------------------------

    master_found = any(
        member["unit_id"] == 1
        for member in before_members
    )

    if not master_found:

        print()
        print(
            "ERROR: Unit-ID 1 / MASTER was not found."
        )

        return False

    print()
    print(
        "Unit-ID 1 / MASTER : PASS"
    )

    # =====================================================
    # STEP 2
    # =====================================================

    print()
    print(
        "STEP 2: SELECT NON-MASTER MEMBER TO REBOOT"
    )

    non_master_members = _get_non_master_members(
        before_members
    )

    selected_member = _select_member_to_reboot(
        non_master_members
    )

    if selected_member is None:
        return False

    selected_unit_id = selected_member[
        "unit_id"
    ]

    selected_mac = selected_member[
        "mac"
    ]

    selected_role = selected_member[
        "role"
    ]

    print()
    print(
        f"Selected Unit-ID : {selected_unit_id}"
    )

    print(
        f"Role             : {selected_role}"
    )

    print(
        f"MAC              : {selected_mac}"
    )

    # =====================================================
    # STEP 3 - POWER OFF
    # =====================================================

    print()
    print("=" * 70)
    print(
        f"STEP 3: POWER OFF UNIT-ID {selected_unit_id}"
    )
    print("=" * 70)

    print()

    print(
        f"Please POWER OFF Unit-ID {selected_unit_id}."
    )

    print()

    print(
        "IMPORTANT:"
    )

    print(
        "  Unit-ID 1 / MASTER must remain powered ON."
    )

    print(
        f"  Only Unit-ID {selected_unit_id} "
        "should be powered OFF."
    )

    input(
        "\nPress ENTER after the selected member "
        "has been powered OFF..."
    )

    # =====================================================
    # REMOVAL
    # =====================================================

    removal_detected = _wait_for_member_removal(
        active_connection,
        selected_unit_id
    )

    # -----------------------------------------------------
    # Do not immediately fail.
    #
    # Some firmware/log configurations can miss the
    # exact removal line. The user has physically powered
    # off the member, so continue to the power-on step.
    # -----------------------------------------------------

    if removal_detected:

        print()
        print(
            "Member removal detected : PASS"
        )

    else:

        print()
        print(
            "Member removal log      : NOT CAPTURED"
        )

        print(
            "Continuing because final stack verification "
            "will determine the actual state."
        )

    # =====================================================
    # STEP 4 - POWER ON
    # =====================================================

    print()
    print("=" * 70)
    print(
        f"STEP 4: POWER ON UNIT-ID {selected_unit_id}"
    )
    print("=" * 70)

    print()

    print(
        f"Please POWER ON Unit-ID {selected_unit_id}."
    )

    print()

    print(
        "Keep Unit-ID 1 / MASTER connected."
    )

    input(
        "\nPress ENTER after the selected member "
        "has been powered ON..."
    )

    # =====================================================
    # STEP 5 - MONITOR MASTER
    # =====================================================

    print()
    print("=" * 70)
    print(
        "STEP 5: MONITOR UNIT-1 / MASTER LOG"
    )
    print("=" * 70)

    print()

    print(
        "Unit-ID 1 / MASTER remains connected."
    )

    print(
        "Monitoring Unit-1 logging for rejoin activity..."
    )

    rejoin_log_detected = _wait_for_member_rejoin(
        active_connection,
        selected_unit_id
    )

    if rejoin_log_detected:

        print()
        print(
            "Rejoin log activity      : PASS"
        )

    else:

        print()
        print(
            "Rejoin log activity      : NOT CAPTURED"
        )

        print(
            "This alone will NOT fail the test."
        )

    # =====================================================
    # STEP 6 - ALLOW STACK TO SETTLE
    # =====================================================

    print()
    print("=" * 70)
    print(
        "STEP 6: WAIT FOR STACK SYNCHRONIZATION"
    )
    print("=" * 70)

    print()

    print(
        f"Waiting {STACK_SETTLE_TIME} seconds "
        "before final stack verification..."
    )

    for remaining in range(
        STACK_SETTLE_TIME,
        0,
        -1
    ):

        print(
            f"\rContinuing in {remaining:02d}s...",
            end="",
            flush=True
        )

        time.sleep(1)

    print()

    # =====================================================
    # STEP 7 - FINAL SHOW STACK
    # =====================================================

    print()
    print("=" * 70)
    print(
        "STEP 7: VERIFY AUTOMATIC REJOIN"
    )
    print("=" * 70)

    print()

    print(
        "Final verification is based on:"
    )

    print(
        f"  {SHOW_STACK_COMMAND}"
    )

    print()

    final_found, final_members = _wait_for_final_stack(
        active_connection,
        selected_unit_id,
        expected_members
    )

    # =====================================================
    # PRINT FINAL SHOW STACK ONCE MORE
    # =====================================================

    print()
    print(
        "Final stack status:"
    )

    final_output = _run_command(
        active_connection,
        SHOW_STACK_COMMAND
    )

    final_found, final_members = _verify_unit_in_stack(
        final_output,
        selected_unit_id
    )

    # =====================================================
    # STEP 8 - FINAL VERIFICATION
    # =====================================================

    print()
    print("=" * 70)
    print(
        "STEP 8: VERIFY STACK FORMATION"
    )
    print("=" * 70)

    detected_ids = [
        member["unit_id"]
        for member in final_members
    ]

    print()

    print(
        f"Expected Unit-ID         : "
        f"{selected_unit_id}"
    )

    print(
        "Detected Unit-IDs        : "
        + (
            ", ".join(
                str(unit_id)
                for unit_id in detected_ids
            )
            if detected_ids
            else "None"
        )
    )

    if final_found:

        print(
            f"Unit-ID {selected_unit_id} rejoin : PASS"
        )

    else:

        print(
            f"Unit-ID {selected_unit_id} rejoin : FAIL"
        )

    # =====================================================
    # MEMBER COUNT
    # =====================================================

    member_count_pass = True

    if expected_members is not None:

        detected_count = len(
            final_members
        )

        print()

        print(
            f"Expected stack members : "
            f"{expected_members}"
        )

        print(
            f"Detected stack members : "
            f"{detected_count}"
        )

        if detected_count == expected_members:

            print(
                "Member count           : PASS"
            )

        else:

            print(
                "Member count           : FAIL"
            )

            member_count_pass = False

    # =====================================================
    # PRINT COMPLETE STACK
    # =====================================================

    if final_members:

        print()
        print(
            "Detected Stack Members:"
        )

        for member in final_members:

            print(
                f"  Unit-ID {member['unit_id']} "
                f"Role: {member['role']:<10} "
                f"MAC: {member['mac']}"
            )

    # =====================================================
    # FINAL RESULT
    # =====================================================

    # -----------------------------------------------------
    # IMPORTANT:
    #
    # Final result depends on actual "show stack":
    #
    # 1. Selected member exists
    # 2. Expected member count matches
    #
    # The log is supporting evidence only.
    # -----------------------------------------------------

    stack_verification_pass = (

        final_found
        and member_count_pass
    )

    print()
    print("=" * 70)
    print(
        "             TC-STK-013 RESULT"
    )
    print("=" * 70)

    print()

    print(
        "Stack Before Reboot      : PASS"
    )

    print(
        "Member Removal Detected  : "
        + (
            "PASS"
            if removal_detected
            else "NOT CAPTURED"
        )
    )

    print(
        "Member Rejoin Log        : "
        + (
            "PASS"
            if rejoin_log_detected
            else "NOT CAPTURED"
        )
    )

    print(
        "Stack Verification       : "
        + (
            "PASS"
            if stack_verification_pass
            else "FAIL"
        )
    )

    print()

    print(
        "TC-STK-013              : "
        + (
            "PASS"
            if stack_verification_pass
            else "FAIL"
        )
    )

    print()

    if stack_verification_pass:

        print(
            f"Unit-ID {selected_unit_id} "
            "successfully rejoined the stack."
        )

        print(
            "The final 'do show stack' confirms "
            "the expected stack membership."
        )

    else:

        print(
            f"Unit-ID {selected_unit_id} "
            "was not confirmed in the final stack."
        )

        print(
            "Please check the final 'do show stack' output."
        )

    print()

    print(
        "Unit-ID 1 / MASTER connection remains active."
    )

    return stack_verification_pass

