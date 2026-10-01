import re
import time

from connection import SwitchConnection


# =========================================================
# TEST CASE INFORMATION
# =========================================================

TEST_CASE_ID = "TC-STK-008"
TEST_CASE_TITLE = "STP Redundant Link Convergence"


# =========================================================
# COMMANDS
# =========================================================

COMMAND_SHOW_STACK = "sh stack"
COMMAND_ENABLE_STP = "spanning-tree"
COMMAND_SHOW_BLOCKED_PORTS = "sh spanning-tree blockedports"

COMMAND_CONFIG = "config"
COMMAND_END = "end"


# =========================================================
# TIMINGS
# =========================================================

COMMAND_TIMEOUT = 30
STP_CONVERGENCE_WAIT = 5
LOG_CAPTURE_TIME = 10
LOG_POLL_INTERVAL = 1


# =========================================================
# DISPLAY
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
# ANSI CLEANUP
# =========================================================

def _remove_ansi(text):

    if not text:
        return ""

    ansi_escape = re.compile(
        r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])"
    )

    return ansi_escape.sub("", text)


# =========================================================
# CONNECTION CHECK
# =========================================================

def _connection_is_usable(connection):

    if connection is None:
        return False

    try:

        shell = getattr(
            connection,
            "shell",
            None
        )

        if shell is None:
            return False

        return True

    except Exception:

        return False


# =========================================================
# UPDATE CONNECTION OBJECT
# =========================================================

def _update_connection_object(
    master_connection,
    new_connection
):

    if new_connection is None:
        return master_connection

    if master_connection is None:
        return new_connection

    try:

        master_connection.shell = (
            new_connection.shell
        )

        if hasattr(
            new_connection,
            "client"
        ):

            master_connection.client = (
                new_connection.client
            )

        if hasattr(
            new_connection,
            "tn"
        ):

            master_connection.tn = (
                new_connection.tn
            )

        return master_connection

    except Exception:

        return new_connection


# =========================================================
# RECONNECT MASTER
# =========================================================

def _reconnect_master(
    master_ip,
    master_username,
    master_password,
    connection_type
):

    print()
    print("=" * 70)
    print("RECONNECTING TO UNIT-1 / MASTER".center(70))
    print("=" * 70)

    print()
    print(
        f"MASTER IP : {master_ip}"
    )

    while True:

        try:

            connection = SwitchConnection(
                host=master_ip,
                username=master_username,
                password=master_password,
                connection_type=connection_type
            )

            connection.connect()

            if _connection_is_usable(
                connection
            ):

                print()
                print(
                    "Successfully connected to "
                    "Unit-1 / MASTER."
                )

                return connection

        except Exception as exc:

            print()
            print(
                f"Master connection failed: {exc}"
            )

        print()
        print(
            "Waiting 5 seconds before retry..."
        )

        time.sleep(5)


# =========================================================
# ENSURE MASTER CONNECTION
# =========================================================

def _ensure_master_connection(
    master_connection,
    master_ip,
    master_username,
    master_password,
    connection_type
):

    if _connection_is_usable(
        master_connection
    ):

        return master_connection

    print()
    print(
        "Existing MASTER connection is not usable."
    )

    return _reconnect_master(
        master_ip,
        master_username,
        master_password,
        connection_type
    )


# =========================================================
# CLEAR SHELL BUFFER
# =========================================================

def _clear_shell(shell):

    try:

        while shell.recv_ready():

            shell.recv(
                65535
            )

    except Exception:

        pass


# =========================================================
# REMOVE ONLY PAGER PROMPT
# =========================================================

def _remove_pager_prompt(text):

    if not text:
        return ""

    # Remove only the pager instruction.
    # Do NOT remove everything between two pager prompts.
    patterns = [

        r"More:\s*<space>,\s*Quit:\s*q\s*"
        r"or\s*CTRL\+Z,\s*One\s*line:\s*<return>",

        r"More:\s*<space>.*?"
        r"One\s*line:\s*<return>",

    ]

    cleaned = text

    for pattern in patterns:

        cleaned = re.sub(
            pattern,
            "",
            cleaned,
            flags=re.IGNORECASE
        )

    return cleaned


# =========================================================
# PRINT CHUNK WITHOUT PAGER PROMPT
# =========================================================

def _print_clean_chunk(chunk):

    if not chunk:
        return

    clean = _remove_ansi(
        chunk
    )

    clean = _remove_pager_prompt(
        clean
    )

    if clean:

        print(
            clean,
            end="",
            flush=True
        )


# =========================================================
# GET COMMAND OUTPUT
# =========================================================

def _get_command_output(
    connection,
    command,
    timeout=COMMAND_TIMEOUT
):
    """
    Execute CLI command and automatically
    press SPACE whenever the switch displays
    a pagination prompt.

    This is especially required for:

        sh spanning-tree blockedports
    """

    try:

        shell = getattr(
            connection,
            "shell",
            None
        )

        if shell is None:

            print()
            print(
                "ERROR: Master shell is not available."
            )

            return None

        # -------------------------------------------------
        # CLEAR OLD DATA
        # -------------------------------------------------

        _clear_shell(
            shell
        )

        print()
        print(
            f"Executing on Unit-1 / MASTER: {command}"
        )

        print(
            command
        )

        print()

        # -------------------------------------------------
        # SEND COMMAND
        # -------------------------------------------------

        shell.send(
            command + "\n"
        )

        raw_output = ""

        start_time = time.time()

        last_data_time = (
            start_time
        )

        pager_detected = False

        # Keep reading until command is completed.
        while (
            time.time() - start_time
            < timeout
        ):

            if shell.recv_ready():

                try:

                    data = shell.recv(
                        65535
                    )

                except Exception:

                    data = b""

                if not data:

                    time.sleep(0.1)

                    continue

                chunk = data.decode(
                    "utf-8",
                    errors="ignore"
                )

                # -----------------------------------------
                # KEEP RAW COMPLETE OUTPUT
                # -----------------------------------------

                raw_output += chunk

                last_data_time = (
                    time.time()
                )

                # -----------------------------------------
                # CLEAN DISPLAY COPY
                # -----------------------------------------

                clean_chunk = _remove_ansi(
                    chunk
                )

                # -----------------------------------------
                # CHECK PAGINATION
                # -----------------------------------------

                pager_match = re.search(
                    r"More:\s*<space>",
                    clean_chunk,
                    re.IGNORECASE
                )

                if pager_match:

                    pager_detected = True

                    # Print current page content
                    # without pager text.
                    _print_clean_chunk(
                        chunk
                    )

                    print(
                        "",
                        end="",
                        flush=True
                    )

                    # -------------------------------------
                    # AUTOMATIC SPACE
                    # -------------------------------------

                    try:

                        shell.send(
                            " "
                        )

                    except Exception as exc:

                        print()
                        print(
                            "ERROR: Unable to send "
                            f"SPACE for pagination: {exc}"
                        )

                        break

                    # Give switch a small amount
                    # of time to prepare next page.
                    time.sleep(
                        0.15
                    )

                    continue

                # -----------------------------------------
                # NORMAL OUTPUT
                # -----------------------------------------

                _print_clean_chunk(
                    chunk
                )

            else:

                time.sleep(
                    0.1
                )

            # -------------------------------------------------
            # CHECK IF CLI PROMPT RETURNED
            # -------------------------------------------------

            if raw_output:

                clean_recent = _remove_ansi(
                    raw_output[-3000:]
                )

                clean_recent = (
                    _remove_pager_prompt(
                        clean_recent
                    )
                )

                # Most QN switch prompts end with # or >
                # after command completion.
                #
                # Do not stop immediately after a pager.
                # Wait until output becomes idle.
                if (
                    time.time()
                    - last_data_time
                    >= 1.5
                ):

                    try:

                        if shell.recv_ready():

                            continue

                    except Exception:

                        pass

                    # If pager was used, this is still
                    # considered complete only after
                    # output becomes idle.
                    break

        # =================================================
        # FINAL READ
        # =================================================

        final_wait_start = time.time()

        while (
            time.time()
            - final_wait_start
            < 1.0
        ):

            if shell.recv_ready():

                try:

                    data = shell.recv(
                        65535
                    )

                except Exception:

                    data = b""

                if data:

                    chunk = data.decode(
                        "utf-8",
                        errors="ignore"
                    )

                    raw_output += chunk

                    _print_clean_chunk(
                        chunk
                    )

                    final_wait_start = (
                        time.time()
                    )

            else:

                time.sleep(
                    0.1
                )

        # =================================================
        # FINAL CLEANUP
        # =================================================

        output = _remove_ansi(
            raw_output
        )

        output = _remove_pager_prompt(
            output
        )

        return output

    except Exception as exc:

        print()
        print(
            f"Command execution error: {exc}"
        )

        return None


# =========================================================
# RUN COMMAND ON MASTER
# =========================================================

def _run_master_command(
    master_connection,
    command,
    timeout=COMMAND_TIMEOUT
):

    return _get_command_output(
        master_connection,
        command,
        timeout=timeout
    )


# =========================================================
# CAPTURE STP LOGS
# =========================================================

def _capture_stp_logs(
    master_connection,
    duration=LOG_CAPTURE_TIME
):

    print()
    print(
        f"Capturing switch-generated STP logs "
        f"for {duration} seconds..."
    )

    logs = ""

    start_time = time.time()

    while (
        time.time() - start_time
        < duration
    ):

        try:

            shell = getattr(
                master_connection,
                "shell",
                None
            )

            if shell is None:
                break

            if shell.recv_ready():

                data = shell.recv(
                    65535
                )

                if data:

                    chunk = data.decode(
                        "utf-8",
                        errors="ignore"
                    )

                    logs += chunk

                    clean = _remove_ansi(
                        chunk
                    )

                    if clean.strip():

                        print(
                            clean,
                            end="",
                            flush=True
                        )

            else:

                time.sleep(
                    LOG_POLL_INTERVAL
                )

        except Exception as exc:

            print()
            print(
                f"Log capture warning: {exc}"
            )

            break

    return logs


# =========================================================
# USER ASSIST
# =========================================================

def _user_assist(message):

    print()
    print("=" * 70)
    print("USER ASSIST".center(70))
    print("=" * 70)

    print()
    print(message)

    print()
    input(
        "Press ENTER after completing the above action..."
    )


# =========================================================
# SELECT SECOND LINK UNIT
# =========================================================

def _select_second_link_unit(
    expected_members
):

    print()
    print(
        "Which stack member should receive "
        "the SECOND redundant link?"
    )

    print()

    for unit_id in range(
        2,
        expected_members + 1
    ):

        print(
            f"  Unit-{unit_id}"
        )

    print()

    while True:

        value = input(
            "Enter Unit-ID: "
        ).strip()

        try:

            unit_id = int(
                value
            )

        except ValueError:

            print(
                "Please enter a valid numeric Unit-ID."
            )

            continue

        if (
            2
            <= unit_id
            <= expected_members
        ):

            return unit_id

        print(
            f"Please enter Unit-ID between "
            f"2 and {expected_members}."
        )


# =========================================================
# PARSE STACK UNIT IDS
# =========================================================

def _get_stack_unit_ids(
    output
):

    if not output:
        return []

    clean = _remove_ansi(
        output
    )

    unit_ids = set()

    for line in clean.splitlines():

        line = line.strip()

        if not line:
            continue

        # Expected stack output normally
        # starts with numeric Unit-ID.
        match = re.match(
            r"^(\d+)\s+",
            line
        )

        if match:

            try:

                unit_id = int(
                    match.group(1)
                )

                if (
                    1
                    <= unit_id
                    <= 64
                ):

                    unit_ids.add(
                        unit_id
                    )

            except ValueError:

                pass

    return sorted(
        unit_ids
    )


# =========================================================
# CHECK STACK IS RUNNING
# =========================================================

def _verify_running_stack(
    output,
    expected_members
):

    if not output:

        return False

    unit_ids = _get_stack_unit_ids(
        output
    )

    expected_ids = list(
        range(
            1,
            expected_members + 1
        )
    )

    missing = [
        unit_id
        for unit_id in expected_ids
        if unit_id not in unit_ids
    ]

    if missing:

        print()
        print(
            "ERROR: Expected Unit-ID(s) "
            f"not found: {missing}"
        )

        print()
        print(
            f"Detected Unit-IDs: {unit_ids}"
        )

        return False

    return True


# =========================================================
# FIND CONTROLLER
# =========================================================

def _controller_found(
    output
):

    if not output:
        return False

    clean = _remove_ansi(
        output
    ).lower()

    patterns = [
        r"\bcontroller\b",
        r"\bmaster\b",
        r"\bactive\b"
    ]

    for pattern in patterns:

        if re.search(
            pattern,
            clean,
            re.IGNORECASE
        ):

            return True

    return False


# =========================================================
# FIND ACTUAL BLOCKED / ALTERNATE INTERFACE
# =========================================================

def _find_blocked_interface(
    output
):

    if not output:
        return None

    clean = _remove_ansi(
        output
    )

    lines = clean.splitlines()

    in_interfaces_section = False

    for line in lines:

        stripped = line.strip()

        if not stripped:
            continue

        # -------------------------------------------------
        # Find Interfaces section
        # -------------------------------------------------

        if stripped.lower() == "interfaces":

            in_interfaces_section = True

            continue

        if not in_interfaces_section:
            continue

        # -------------------------------------------------
        # Ignore pagination / prompts
        # -------------------------------------------------

        if re.search(
            r"More:\s*<space>",
            stripped,
            re.IGNORECASE
        ):

            continue

        # -------------------------------------------------
        # Parse actual interface table
        #
        # Example:
        #
        # gi1/0/33 enabled 128.33 20000 Dscr Altn No P2P (RSTP)
        #
        # We mainly need:
        #   interface
        #   state
        #   status
        #   role
        # -------------------------------------------------

        match = re.match(
            r"^(\S+)\s+"
            r"(\S+)\s+"
            r"(\S+)\s+"
            r"(\S+)\s+"
            r"(\S+)\s+"
            r"(\S+)\s+"
            r"(\S+)\s+"
            r"(.+)$",
            stripped
        )

        if not match:
            continue

        interface = match.group(1)
        state = match.group(2)
        priority = match.group(3)
        cost = match.group(4)
        status = match.group(5)
        role = match.group(6)
        portfast = match.group(7)
        port_type = match.group(8)

        # -------------------------------------------------
        # Ignore header-like rows
        # -------------------------------------------------

        if interface.lower() in (
            "name",
            "interface",
            "port"
        ):

            continue

        # -------------------------------------------------
        # ACTUAL ALTERNATE / BLOCKED PORT
        # -------------------------------------------------

        if role.lower() in (
            "altn",
            "alternate",
            "alt"
        ):

            return {
                "interface": interface,
                "state": state,
                "priority": priority,
                "cost": cost,
                "status": status,
                "role": role,
                "portfast": portfast,
                "type": port_type
            }

        # -------------------------------------------------
        # Some software versions may show
        # blocked/discarding directly.
        # -------------------------------------------------

        if (
            role.lower()
            in (
                "block",
                "blocked",
                "discard",
                "discarding"
            )
        ):

            return {
                "interface": interface,
                "state": state,
                "priority": priority,
                "cost": cost,
                "status": status,
                "role": role,
                "portfast": portfast,
                "type": port_type
            }

        if (
            status.lower()
            in (
                "block",
                "blocked",
                "discard",
                "discarding"
            )
        ):

            return {
                "interface": interface,
                "state": state,
                "priority": priority,
                "cost": cost,
                "status": status,
                "role": role,
                "portfast": portfast,
                "type": port_type
            }

    return None


# =========================================================
# DISPLAY BLOCKED INTERFACE RESULT
# =========================================================

def _display_blocked_interface(
    blocked_interface
):

    if not blocked_interface:

        print()
        print(
            "No blocked / alternate interface "
            "was detected."
        )

        return

    print()
    print("=" * 70)
    print(
        "BLOCKED / ALTERNATE INTERFACE DETECTED"
        .center(70)
    )
    print("=" * 70)

    print()

    print(
        f"Interface : "
        f"{blocked_interface['interface']}"
    )

    print(
        f"State     : "
        f"{blocked_interface['state']}"
    )

    print(
        f"Status    : "
        f"{blocked_interface['status']}"
    )

    print(
        f"Role      : "
        f"{blocked_interface['role']}"
    )

    print(
        f"Cost      : "
        f"{blocked_interface['cost']}"
    )

    print(
        f"PortFast  : "
        f"{blocked_interface['portfast']}"
    )

    print(
        f"Type      : "
        f"{blocked_interface['type']}"
    )

    print()


# =========================================================
# MAIN TEST CASE
# =========================================================

def run_tc_stk_008(
    master_connection,
    master_ip,
    master_username,
    master_password,
    connection_type,
    expected_members=2,
    **kwargs
):

    _print_header(
        f"{TEST_CASE_ID} - {TEST_CASE_TITLE}"
    )

    # =====================================================
    # STEP 1
    # =====================================================

    _print_step(
        1,
        "VERIFY RUNNING STACK"
    )

    master_connection = _ensure_master_connection(
        master_connection,
        master_ip,
        master_username,
        master_password,
        connection_type
    )

    if not master_connection:

        print()
        print(
            "FAIL: Unable to connect to Unit-1 / MASTER."
        )

        return False

    stack_output = _run_master_command(
        master_connection,
        COMMAND_SHOW_STACK
    )

    if not stack_output:

        print()
        print(
            "FAIL: No output received from "
            "show stack."
        )

        return False

    stack_ok = _verify_running_stack(
        stack_output,
        expected_members
    )

    if not stack_ok:

        print()
        print(
            "FAIL: Running stack verification failed."
        )

        return False

    print()
    print(
        "PASS: Running stack verified."
    )

    # =====================================================
    # STEP 2
    # =====================================================

    _print_step(
        2,
        "ENABLE STP"
    )

    print()
    print(
        "Executing on Unit-1 / MASTER:"
    )

    print()
    print(
        "config"
    )

    config_output = _run_master_command(
        master_connection,
        COMMAND_CONFIG
    )

    if config_output is None:

        print()
        print(
            "FAIL: Unable to enter configuration mode."
        )

        return False

    print()
    print(
        "Executing:"
    )

    print()
    print(
        "spanning-tree"
    )

    stp_output = _run_master_command(
        master_connection,
        COMMAND_ENABLE_STP
    )

    if stp_output is None:

        print()
        print(
            "FAIL: Unable to enable STP."
        )

        return False

    print()
    print(
        "PASS: STP enable command executed."
    )

    print()
    print(
        "Returning to normal CLI..."
    )

    _run_master_command(
        master_connection,
        COMMAND_END
    )

    # =====================================================
    # STEP 3
    # =====================================================

    _print_step(
        3,
        "SELECT SECOND REDUNDANT LINK DESTINATION"
    )

    try:

        expected_members = int(
            expected_members
        )

    except Exception:

        expected_members = 2

    if expected_members < 2:

        expected_members = 2

    second_link_unit = _select_second_link_unit(
        expected_members
    )

    print()
    print(
        f"Selected destination: Unit-{second_link_unit}"
    )

    # =====================================================
    # STEP 4
    # =====================================================

    _print_step(
        4,
        "CONNECT SECOND REDUNDANT STACK LINK"
    )

    _user_assist(
        f"""
Already has the first stack link.

Now physically connect the SECOND stack link.

IMPORTANT:

1. Do NOT disconnect the existing first link.
2. Keep the first stack link connected.
3. Connect only the additional redundant link.
4. After the cable is connected, press ENTER.
"""
    )

    # =====================================================
    # STEP 5
    # =====================================================

    _print_step(
        5,
        "WAIT FOR STP CONVERGENCE"
    )

    print()
    print(
        f"Waiting {STP_CONVERGENCE_WAIT} seconds "
        "for STP convergence..."
    )

    for remaining in range(
        STP_CONVERGENCE_WAIT,
        0,
        -1
    ):

        print(
            f"\rSTP convergence wait: "
            f"{remaining:02d} seconds",
            end="",
            flush=True
        )

        time.sleep(1)

    print()
    print(
        "STP convergence wait completed."
    )

    # =====================================================
    # STEP 6
    # =====================================================

    _print_step(
        6,
        "CAPTURE SWITCH-GENERATED STP LOGS"
    )

    print()
    print(
        "Monitoring switch output for "
        f"{LOG_CAPTURE_TIME} seconds..."
    )

    logs = _capture_stp_logs(
        master_connection,
        LOG_CAPTURE_TIME
    )

    print()

    if logs:

        print(
            "STP log/output captured."
        )

    else:

        print(
            "No asynchronous STP log output captured."
        )

    # =====================================================
    # STEP 7
    # =====================================================

    _print_step(
        7,
        "SHOW STP BLOCKED / ALTERNATE PORT"
    )

    print()
    print(
        "Executing on Unit-1 / MASTER:"
    )

    print()
    print(
        COMMAND_SHOW_BLOCKED_PORTS
    )

    print()

    print(
        "Checking complete STP interface table..."
    )

    print(
        "Pagination is handled automatically."
    )

    print()

    blocked_ports_output = _run_master_command(
        master_connection,
        COMMAND_SHOW_BLOCKED_PORTS,
        timeout=60
    )

    if not blocked_ports_output:

        print()
        print(
            "FAIL: No output received from "
            "STP blocked-ports command."
        )

        return False

    # =====================================================
    # PARSE ACTUAL INTERFACE
    # =====================================================

    blocked_interface = _find_blocked_interface(
        blocked_ports_output
    )

    _display_blocked_interface(
        blocked_interface
    )

    # =====================================================
    # FINAL RESULT
    # =====================================================

    print()
    print("=" * 70)
    print(
        "TEST RESULT".center(70)
    )
    print("=" * 70)

    print()

    if (
        stack_ok
        and stp_output is not None
        and blocked_ports_output
        and blocked_interface
    ):

        print(
            "PASS: STP redundant link convergence "
            "verified."
        )

        print()
        print(
            "A real alternate / blocked interface "
            "was detected."
        )

        print()
        print(
            f"Interface : "
            f"{blocked_interface['interface']}"
        )

        print(
            f"Role      : "
            f"{blocked_interface['role']}"
        )

        print(
            f"Status    : "
            f"{blocked_interface['status']}"
        )

        print()

        return True

    print(
        "FAIL: STP redundant link convergence "
        "could not be verified."
    )

    if not blocked_interface:

        print()
        print(
            "Reason: No actual Altn / blocked / "
            "discarding interface was detected."
        )

    print()

    return False