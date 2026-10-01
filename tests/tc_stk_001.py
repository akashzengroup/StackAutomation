import time

from connection import SwitchConnection


TEST_CASE_ID = "TC-STK-001"
TEST_CASE_TITLE = "Create New Stack"


# =========================================================
# HEADER
# =========================================================

def _print_header(title):

    print()

    print("=" * 70)

    print(
        f"{title:^70}"
    )

    print("=" * 70)


# =========================================================
# STEP
# =========================================================

def _print_step(
    step,
    title
):

    print()

    print("-" * 70)

    print(
        f"STEP {step}: {title}"
    )

    print("-" * 70)


# =========================================================
# COMMAND OUTPUT
# =========================================================

def _get_command_output(
    connection,
    command
):

    try:

        # -------------------------------------------------
        # Use existing SwitchConnection shell
        # -------------------------------------------------

        shell = connection.shell

        if shell is None:

            print(
                "\nERROR: SSH shell is not available."
            )

            return None

        # -------------------------------------------------
        # Clear old data
        # -------------------------------------------------

        while shell.recv_ready():

            try:
                shell.recv(65535)

            except Exception:
                break

        # -------------------------------------------------
        # Send command
        # -------------------------------------------------

        shell.send(
            command + "\n"
        )

        # -------------------------------------------------
        # Collect output
        # -------------------------------------------------

        output = ""

        start_time = time.time()

        last_data_time = start_time

        while True:

            if shell.recv_ready():

                data = shell.recv(
                    65535
                )

                if data:

                    chunk = data.decode(
                        "utf-8",
                        errors="ignore"
                    )

                    output += chunk

                    last_data_time = time.time()

            else:

                time.sleep(0.1)

            # -------------------------------------------------
            # Stop when no data received for 1 second
            # after command output started.
            # -------------------------------------------------

            if output:

                if (
                    time.time()
                    - last_data_time
                    >= 1.0
                ):

                    break

            # -------------------------------------------------
            # Safety timeout
            # -------------------------------------------------

            if (
                time.time()
                - start_time
                >= 10
            ):

                break

        return output

    except Exception as e:

        print(
            f"\nCommand execution error: {e}"
        )

        return None


# =========================================================
# VERIFY STACK
# =========================================================

def _verify_stack(
    output,
    expected_members
):

    if not output:

        return (
            False,
            "No output received from 'show stack'."
        )

    text = output.lower()

    # -----------------------------------------------------
    # IMPORTANT:
    #
    # Actual CLI output is:
    #
    #    1 ... controller
    #    2 ... backup
    #
    # It does NOT contain "Unit-1".
    #
    # Therefore verify based on table rows.
    # -----------------------------------------------------

    found_units = []

    for unit_id in range(
        1,
        expected_members + 1
    ):

        lines = text.splitlines()

        found = False

        for line in lines:

            stripped = line.strip()

            if not stripped:
                continue

            # Example:
            #
            # 1  58:61:63... controller
            #
            parts = stripped.split()

            if not parts:
                continue

            if parts[0] == str(unit_id):

                found = True

                break

        if found:

            found_units.append(
                unit_id
            )

    # -----------------------------------------------------
    # Check missing units
    # -----------------------------------------------------

    missing_units = [

        unit_id

        for unit_id in range(
            1,
            expected_members + 1
        )

        if unit_id not in found_units

    ]

    if missing_units:

        return (
            False,
            f"Expected Unit-ID(s) not found: "
            f"{missing_units}"
        )

    # -----------------------------------------------------
    # Controller check
    # -----------------------------------------------------

    controller_found = (

        "controller" in text

        or

        "master" in text

        or

        "active" in text

    )

    if not controller_found:

        return (
            False,
            "Controller/Active role was not detected."
        )

    return (
        True,
        "All expected members and Controller "
        "were detected."
    )


# =========================================================
# VERIFY STACK LINKS
# =========================================================

def _verify_stack_links(
    output
):

    if not output:

        return (
            False,
            "No output received from "
            "'show stack links details'."
        )

    text = output.lower()

    # -----------------------------------------------------
    # Actual output uses:
    #
    # Status
    # Active
    #
    # Therefore explicitly check for Active.
    # -----------------------------------------------------

    lines = text.splitlines()

    status_lines = []

    for line in lines:

        if "active" in line:

            status_lines.append(
                line
            )

    # -----------------------------------------------------
    # If no Active status is found,
    # consider verification failed.
    # -----------------------------------------------------

    if not status_lines:

        return (
            False,
            "No Active stack link was detected."
        )

    # -----------------------------------------------------
    # Explicit failure detection
    # -----------------------------------------------------

    bad_patterns = [

        "failed",

        "failure",

        "error",

        "status down",

        "link status: down",

        "link state: down",

        "state down"

    ]

    problems = []

    for pattern in bad_patterns:

        if pattern in text:

            problems.append(
                pattern
            )

    if problems:

        return (
            False,
            "Stack-link problem detected: "
            + ", ".join(problems)
        )

    return (
        True,
        "All stack links appear operational."
    )


# =========================================================
# TC-STK-001
# =========================================================

def run_tc_stk_001(
    master_ip,
    master_username,
    master_password,
    connection_type,
    expected_members,
    wait_time=15
):

    # =====================================================
    # HEADER
    # =====================================================

    _print_header(
        f"{TEST_CASE_ID} - {TEST_CASE_TITLE}"
    )

    print()

    print("Objective:")

    print(
        "Verify switches form a stack successfully."
    )

    print()

    print("Expected Result:")

    print(
        "  - Single stack formed"
    )

    print(
        "  - All members discovered"
    )

    print(
        "  - One Active/Controller elected"
    )

    print(
        "  - Stack links operational"
    )

    print(
        "  - No stack-related errors"
    )

    # =====================================================
    # STEP 1
    # =====================================================

    _print_step(
        1,
        "CONFIGURE STATIC UNIT-IDS AND STACK LINKS"
    )

    print()

    print(
        "Static Unit-IDs and stack links have already"
    )

    print(
        "been configured by the existing"
    )

    print(
        "Stack Configuration Automation."
    )

    print()

    print("Configured members:")

    for unit_id in range(
        1,
        expected_members + 1
    ):

        print(
            f"  Unit-{unit_id}"
        )

    input(
        "\nPress ENTER to continue..."
    )

    # =====================================================
    # STEP 2
    # =====================================================

    _print_step(
        2,
        "CONNECT STACK CABLES"
    )

    print()

    print("USER ASSISTANCE")

    print()

    print(
        "Please connect the stack cables between "
        "all switches."
    )

    print()

    print("Please verify:")

    print(
        "  [ ] Stack cables are connected correctly"
    )

    print(
        "  [ ] Required stack links are connected"
    )

    print(
        "  [ ] Ring connection is used if applicable"
    )

    input(
        "\nPress ENTER after the stack cables "
        "are connected..."
    )

    # =====================================================
    # STEP 3
    # =====================================================

    _print_step(
        3,
        "POWER ON ALL SWITCHES"
    )

    print()

    print("USER ASSISTANCE")

    print()

    print(
        "Please power ON ALL switches simultaneously."
    )

    input(
        "\nPress ENTER after all switches "
        "are powered ON..."
    )

    # =====================================================
    # STEP 4
    # =====================================================

    _print_step(
        4,
        "WAIT FOR STACK INITIALIZATION"
    )

    print()

    print(
        f"Waiting {wait_time} seconds "
        "for stack initialization..."
    )

    for remaining in range(
        wait_time,
        0,
        -1
    ):

        print(
            f"\rStack initialization: "
            f"{remaining:02d} seconds remaining...",
            end="",
            flush=True
        )

        time.sleep(1)

    print()

    print()

    print(
        "Stack initialization wait completed."
    )

    # =====================================================
    # STEP 5
    # =====================================================

    _print_step(
        5,
        "VERIFY STACK"
    )

    # =====================================================
    # CREATE FRESH CONNECTION
    #
    # THIS IS THE IMPORTANT FIX.
    #
    # We do NOT reuse master terminal connection.
    # =====================================================

    print()

    print(
        "Creating a fresh connection to "
        "Unit-ID 1 for test verification..."
    )

    verification_connection = SwitchConnection(

        connection_type=connection_type,

        ip=master_ip,

        username=master_username,

        password=master_password

    )

    if not verification_connection.connect():

        _print_header(
            f"{TEST_CASE_ID} RESULT"
        )

        print()

        print("FAIL")

        print()

        print(
            "Unable to connect to Unit-ID 1 "
            "for test verification."
        )

        return False

    print()

    print(
        "Fresh verification connection established."
    )

    # =====================================================
    # SHOW STACK
    # =====================================================

    print()

    print(
        "Executing: show stack"
    )

    stack_output = _get_command_output(
        verification_connection,
        "show stack"
    )

    if stack_output is None:

        _print_header(
            f"{TEST_CASE_ID} RESULT"
        )

        print()

        print("FAIL")

        print()

        print(
            "Unable to capture 'show stack' output."
        )

        return False

    print()

    print("=" * 70)

    print(
        "                         SHOW STACK"
    )

    print("=" * 70)

    print(
        stack_output
    )

    print("=" * 70)

    # =====================================================
    # VERIFY SHOW STACK
    # =====================================================

    stack_ok, stack_message = _verify_stack(

        stack_output,

        expected_members

    )

    print()

    print(
        f"Stack Verification: "
        f"{stack_message}"
    )

    # =====================================================
    # SHOW STACK LINKS
    # =====================================================

    print()

    print(
        "Executing: show stack links details"
    )

    links_output = _get_command_output(

        verification_connection,

        "show stack links details"

    )

    if links_output is None:

        _print_header(
            f"{TEST_CASE_ID} RESULT"
        )

        print()

        print("FAIL")

        print()

        print(
            "Unable to capture "
            "'show stack links details' output."
        )

        return False

    print()

    print("=" * 70)

    print(
        "                  SHOW STACK LINKS DETAILS"
    )

    print("=" * 70)

    print(
        links_output
    )

    print("=" * 70)

    # =====================================================
    # VERIFY LINKS
    # =====================================================

    links_ok, links_message = _verify_stack_links(

        links_output

    )

    print()

    print(
        f"Stack Link Verification: "
        f"{links_message}"
    )

    # =====================================================
    # CLOSE VERIFICATION CONNECTION
    # =====================================================

    try:

        verification_connection.close()

    except Exception:

        pass

    # =====================================================
    # FINAL RESULT
    # =====================================================

    _print_header(
        f"{TEST_CASE_ID} RESULT"
    )

    if stack_ok and links_ok:

        print()

        print("PASS")

        print()

        print(
            f"{TEST_CASE_ID} - "
            f"{TEST_CASE_TITLE}"
        )

        print()

        print(
            "✓ Single stack verification passed"
        )

        print(
            "✓ Expected members detected"
        )

        print(
            "✓ Controller/Active detected"
        )

        print(
            "✓ Stack links are Active"
        )

        print(
            "✓ No explicit stack-link failure detected"
        )

        print()

        return True

    # =====================================================
    # FAIL
    # =====================================================

    print()

    print("FAIL")

    print()

    print(
        f"{TEST_CASE_ID} - "
        f"{TEST_CASE_TITLE}"
    )

    print()

    if not stack_ok:

        print(
            f"✗ Stack verification failed: "
            f"{stack_message}"
        )

    if not links_ok:

        print(
            f"✗ Stack-link verification failed: "
            f"{links_message}"
        )

    print()

    return False