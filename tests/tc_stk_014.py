import time
import re


# =========================================================
# TC-STK-014
# Maximum Supported Stack Members + Soak Test
# =========================================================

TEST_CASE_ID = "TC-STK-014"

SHOW_STACK_COMMAND = "do show stack"
SHOW_LOG_COMMAND = "show logging"

DEFAULT_SOAK_HOURS = 24
MAX_SOAK_HOURS = 72

LOG_POLL_INTERVAL = 30


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
# PARSE STACK
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

        match = pattern.match(line.strip())

        if not match:
            continue

        try:
            unit_id = int(match.group(1))
        except ValueError:
            continue

        if unit_id < 1 or unit_id > 64:
            continue

        if any(
            item["unit_id"] == unit_id
            for item in members
        ):
            continue

        members.append({
            "unit_id": unit_id,
            "mac": match.group(2),
            "role": match.group(3).lower()
        })

    return sorted(
        members,
        key=lambda x: x["unit_id"]
    )


# =========================================================
# PRINT STACK
# =========================================================

def _print_stack_members(members):

    if not members:
        print("No stack members detected.")
        return

    print()
    print("Detected Stack Members:")

    for member in members:

        print(
            f"  Unit-ID {member['unit_id']} "
            f"Role: {member['role']:<10} "
            f"MAC: {member['mac']}"
        )


# =========================================================
# ASK MAXIMUM MEMBER COUNT
# =========================================================

def _get_max_supported_members():

    print()
    print("=" * 70)
    print("       MAXIMUM SUPPORTED STACK MEMBERS")
    print("=" * 70)

    print()
    print(
        "Enter the maximum number of stack members "
        "supported by your switch platform."
    )

    while True:

        value = input(
            "\nMaximum supported members: "
        ).strip()

        try:
            count = int(value)

            if count < 2:
                print(
                    "A stack must contain at least 2 members."
                )
                continue

            return count

        except ValueError:
            print(
                "Please enter a valid number."
            )


# =========================================================
# ASK SOAK TIME
# =========================================================

def _get_soak_hours():

    print()
    print("=" * 70)
    print("                 SOAK DURATION")
    print("=" * 70)

    print()
    print(
        "Acceptance criteria: 24 to 72 hours."
    )

    while True:

        value = input(
            f"\nEnter soak duration in hours "
            f"[default {DEFAULT_SOAK_HOURS}]: "
        ).strip()

        if not value:
            return DEFAULT_SOAK_HOURS

        try:
            hours = float(value)

            if hours < 24:
                print(
                    "Soak duration must be at least 24 hours."
                )
                continue

            if hours > MAX_SOAK_HOURS:
                print(
                    "Soak duration cannot exceed 72 hours."
                )
                continue

            return hours

        except ValueError:
            print(
                "Please enter a valid number."
            )


# =========================================================
# CHECK MASTER
# =========================================================

def _verify_master(members):

    for member in members:

        if member["unit_id"] == 1:

            role = member["role"].lower()

            return role in (
                "controller",
                "master"
            )

    return False


# =========================================================
# TC-STK-014
# =========================================================

def run_tc_stk_014(
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

    _print_header(
        "       TC-STK-014 - MAXIMUM STACK MEMBERS + SOAK"
    )

    # =====================================================
    # STEP 1
    # =====================================================

    print()
    print("STEP 1: Enter maximum supported member count")

    max_members = _get_max_supported_members()

    # =====================================================
    # STEP 2
    # =====================================================

    print()
    print("=" * 70)
    print("STEP 2: Verify current stack")
    print("=" * 70)

    before_output = _run_command(
        active_connection,
        SHOW_STACK_COMMAND
    )

    before_members = _parse_stack_members(
        before_output
    )

    _print_stack_members(
        before_members
    )

    if not before_members:

        print()
        print(
            "ERROR: Current stack could not be detected."
        )

        return False

    # =====================================================
    # STEP 3
    # =====================================================

    print()
    print("=" * 70)
    print("STEP 3: Verify maximum supported stack")
    print("=" * 70)

    detected_count = len(
        before_members
    )

    print()
    print(
        f"Expected maximum members : {max_members}"
    )

    print(
        f"Detected stack members   : {detected_count}"
    )

    if detected_count != max_members:

        print()
        print(
            "Maximum-member requirement is not met."
        )

        print(
            "Please build the stack with the maximum "
            "supported number of members before running "
            "the soak test."
        )

        print()
        print(
            "TC-STK-014 : FAIL"
        )

        return False

    master_pass = _verify_master(
        before_members
    )

    print(
        "Unit-ID 1 / MASTER        : "
        + ("PASS" if master_pass else "FAIL")
    )

    if not master_pass:
        return False

    # =====================================================
    # STEP 4
    # =====================================================

    soak_hours = _get_soak_hours()

    soak_seconds = int(
        soak_hours * 60 * 60
    )

    print()
    print("=" * 70)
    print("STEP 4: START STACK SOAK TEST")
    print("=" * 70)

    print()
    print(
        f"Stack members : {detected_count}"
    )

    print(
        f"Soak duration : {soak_hours:g} hours"
    )

    print()
    print(
        "The MASTER connection will remain active."
    )

    print(
        "The script will periodically monitor the stack."
    )

    input(
        "\nPress ENTER to start the soak test..."
    )

    # =====================================================
    # STEP 5 - SOAK
    # =====================================================

    start_time = time.time()
    end_time = start_time + soak_seconds

    check_number = 0
    soak_pass = True

    while time.time() < end_time:

        check_number += 1

        remaining = max(
            0,
            int(end_time - time.time())
        )

        hours_left = remaining // 3600
        minutes_left = (
            remaining % 3600
        ) // 60
        seconds_left = remaining % 60

        print()
        print("-" * 70)
        print(
            f"SOAK CHECK #{check_number}"
        )
        print("-" * 70)

        print(
            f"Remaining: "
            f"{hours_left:02d}:"
            f"{minutes_left:02d}:"
            f"{seconds_left:02d}"
        )

        stack_output = _send_command(
            active_connection,
            SHOW_STACK_COMMAND
        )

        current_members = _parse_stack_members(
            stack_output
        )

        current_count = len(
            current_members
        )

        print(
            f"Expected members : {max_members}"
        )

        print(
            f"Detected members : {current_count}"
        )

        if current_count != max_members:

            print(
                "Stack member count : FAIL"
            )

            soak_pass = False

            break

        if not _verify_master(
            current_members
        ):

            print(
                "Unit-ID 1 / MASTER : FAIL"
            )

            soak_pass = False

            break

        print(
            "Stack health       : PASS"
        )

        if remaining <= 0:
            break

        sleep_time = min(
            LOG_POLL_INTERVAL,
            remaining
        )

        time.sleep(
            sleep_time
        )

    # =====================================================
    # STEP 6
    # =====================================================

    print()
    print("=" * 70)
    print("STEP 6: Final stack verification")
    print("=" * 70)

    final_output = _run_command(
        active_connection,
        SHOW_STACK_COMMAND
    )

    final_members = _parse_stack_members(
        final_output
    )

    _print_stack_members(
        final_members
    )

    final_count = len(
        final_members
    )

    final_count_pass = (
        final_count == max_members
    )

    final_master_pass = _verify_master(
        final_members
    )

    # =====================================================
    # FINAL RESULT
    # =====================================================

    result = (
        soak_pass
        and final_count_pass
        and final_master_pass
    )

    print()
    print("=" * 70)
    print("             TC-STK-014 RESULT")
    print("=" * 70)

    print()
    print(
        "Maximum Stack Members : "
        + (
            "PASS"
            if final_count_pass
            else "FAIL"
        )
    )

    print(
        "Unit-ID 1 / MASTER    : "
        + (
            "PASS"
            if final_master_pass
            else "FAIL"
        )
    )

    print(
        "Stack Soak            : "
        + (
            "PASS"
            if soak_pass
            else "FAIL"
        )
    )

    print()
    print(
        "TC-STK-014            : "
        + (
            "PASS"
            if result
            else "FAIL"
        )
    )

    print()
    print(
        "Unit-ID 1 / MASTER connection "
        "remains active."
    )

    return result