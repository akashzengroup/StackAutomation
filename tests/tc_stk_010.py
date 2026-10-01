
import time
import re
from connection import SwitchConnection


TEST_CASE_ID = "TC-STK-010"
TEST_CASE_TITLE = "LAG Traffic Failover"

COMMAND_SHOW_STACK = "sh stack"
COMMAND_CONFIG = "config"
COMMAND_END = "end"
COMMAND_SHOW_PORT_CHANNEL = "do sh interface port-channel"

# One ping at a time.
# This allows the script to control exactly 50 pings.
PING_COMMAND_BEFORE = "ping 8.8.8.8 count 20"
PING_COMMAND_AFTER = "ping 8.8.8.8 count 30"

COMMAND_TIMEOUT = 30

TOTAL_PINGS = 40
PINGS_BEFORE_DISCONNECT = 10
PINGS_AFTER_DISCONNECT = TOTAL_PINGS - PINGS_BEFORE_DISCONNECT


# ============================================================================
# CONNECTION HELPERS
# ============================================================================

def _connection_is_usable(connection):
    if connection is None:
        return False

    shell = getattr(connection, "shell", None)

    if shell is None:
        shell = getattr(
            connection,
            "ssh_shell",
            None,
        )

    if shell is None:
        return False

    try:
        if getattr(shell, "closed", False):
            return False
    except Exception:
        pass

    return True


def _update_connection_object(
    old_connection,
    new_connection,
):
    if old_connection is None:
        return new_connection

    if new_connection is None:
        return old_connection

    try:
        old_connection.__dict__.update(
            new_connection.__dict__
        )

        return old_connection

    except Exception:
        return new_connection


def _connect_switch(
    ip,
    username,
    password,
    connection_type,
):
    connection = SwitchConnection(
        connection_type=connection_type,
        ip=ip,
        username=username,
        password=password,
    )

    connection.connect()

    return connection


def _ensure_master_connection(
    master_connection,
    master_ip,
    master_username,
    master_password,
    connection_type,
):
    print()
    print("=" * 70)
    print(
        "              MASTER CONNECTION CHECK"
    )
    print("=" * 70)

    if _connection_is_usable(
        master_connection
    ):
        try:
            print(
                f"Using existing MASTER connection : "
                f"{master_ip}"
            )

            _run_command(
                master_connection,
                COMMAND_SHOW_STACK,
                timeout=COMMAND_TIMEOUT,
                display=False,
            )

            print(
                "MASTER connection is active."
            )

            return master_connection

        except Exception:
            print(
                "Existing MASTER connection "
                "is not usable."
            )

            print(
                "Reconnecting..."
            )

    while True:
        try:
            print(
                f"Connecting to MASTER : "
                f"{master_ip}"
            )

            new_connection = _connect_switch(
                master_ip,
                master_username,
                master_password,
                connection_type,
            )

            print(
                "MASTER connection established."
            )

            return _update_connection_object(
                master_connection,
                new_connection,
            )

        except Exception as exc:
            print(
                f"MASTER connection failed: "
                f"{exc}"
            )

            print(
                "Retrying in 5 seconds..."
            )

            time.sleep(5)


# ============================================================================
# TERMINAL / OUTPUT HELPERS
# ============================================================================

def _remove_ansi(text):
    if not text:
        return ""

    return re.sub(
        r"\x1b\[[0-?]*[ -/]*[@-~]",
        "",
        text,
    )


def _remove_pager_prompt(text):
    if not text:
        return ""

    patterns = (
        r"More:\s*<space>.*",
        r"More:\s*.*",
        r"--More--.*",
        r"Press\s+SPACE.*",
        r"Press\s+Enter.*",
    )

    for pattern in patterns:
        text = re.sub(
            pattern,
            "",
            text,
            flags=re.IGNORECASE,
        )

    return text


def _print_clean_chunk(chunk):
    if not chunk:
        return

    clean = _remove_ansi(
        chunk
    )

    if not clean.strip():
        return

    print(
        clean,
        end="" if clean.endswith("\n") else "\n",
    )


def _send_raw(
    connection_or_shell,
    data,
):
    for method_name in (
        "send_raw",
        "write",
        "send",
    ):
        method = getattr(
            connection_or_shell,
            method_name,
            None,
        )

        if callable(method):
            try:
                method(data)
                return True

            except Exception:
                pass

    return False


def _clear_shell(connection):
    for method_name in (
        "clear_buffer",
        "clear_shell",
        "flush",
    ):
        method = getattr(
            connection,
            method_name,
            None,
        )

        if callable(method):
            try:
                method()
                return

            except Exception:
                pass


def _get_command_output(
    connection,
    command,
    timeout=COMMAND_TIMEOUT,
    display=True,
):
    if connection is None:
        raise RuntimeError(
            "Switch connection is not available."
        )

    print(
        f">>> {command}"
    )

    send_command = getattr(
        connection,
        "send_command",
        None,
    )

    if callable(send_command):
        try:
            output = send_command(
                command,
                timeout=timeout,
            )

            output = (
                ""
                if output is None
                else str(output)
            )

            output = _remove_ansi(
                output
            )

            if display:
                _print_clean_chunk(
                    output
                )

            return output

        except TypeError:
            pass

        except Exception:
            pass

    shell = getattr(
        connection,
        "shell",
        None,
    )

    if shell is None:
        shell = getattr(
            connection,
            "ssh_shell",
            None,
        )

    if shell is None:
        raise RuntimeError(
            "SwitchConnection does not provide "
            "a supported command execution method."
        )

    _clear_shell(
        connection
    )

    shell.send(
        command + "\n"
    )

    output_parts = []

    start_time = time.time()

    while (
        time.time() - start_time
        < timeout
    ):
        try:
            if (
                hasattr(
                    shell,
                    "recv_ready",
                )
                and shell.recv_ready()
            ):
                chunk = shell.recv(
                    65535
                )

                if isinstance(
                    chunk,
                    bytes,
                ):
                    chunk = chunk.decode(
                        errors="ignore"
                    )

                if chunk:
                    output_parts.append(
                        chunk
                    )

                    clean = _remove_ansi(
                        chunk
                    )

                    if display:
                        _print_clean_chunk(
                            clean
                        )

                    if re.search(
                        r"More:\s*<space>|"
                        r"--More--|"
                        r"Press\s+SPACE",
                        clean,
                        re.I,
                    ):
                        _send_raw(
                            shell,
                            " ",
                        )

                    continue

        except Exception:
            pass

        time.sleep(
            0.1
        )

    return _remove_pager_prompt(
        _remove_ansi(
            "".join(
                output_parts
            )
        )
    )


def _run_command(
    connection,
    command,
    timeout=COMMAND_TIMEOUT,
    display=True,
):
    return _get_command_output(
        connection,
        command,
        timeout=timeout,
        display=display,
    )


# ============================================================================
# USER ASSIST
# ============================================================================

def _user_assist(message):
    print()
    print("=" * 70)
    print(
        "                         USER ASSIST"
    )
    print("=" * 70)

    print(
        message.strip()
    )

    input(
        "\nAfter completing the above step, "
        "press ENTER to continue..."
    )

    print()


# ============================================================================
# STACK HELPERS
# ============================================================================

def _get_stack_unit_ids(
    stack_output,
):
    unit_ids = []

    for raw_line in (
        stack_output or ""
    ).splitlines():

        line = _remove_ansi(
            raw_line
        ).strip()

        match = re.match(
            r"^(\d+)\s+",
            line,
        )

        if match:
            unit_id = int(
                match.group(1)
            )

            if 1 <= unit_id <= 64:
                unit_ids.append(
                    unit_id
                )

    return sorted(
        set(unit_ids)
    )


def _controller_found(
    stack_output,
):
    for raw_line in (
        stack_output or ""
    ).splitlines():

        line = _remove_ansi(
            raw_line
        ).strip()

        match = re.match(
            r"^1\s+(.+)$",
            line,
            re.I,
        )

        if match:
            role_text = (
                match.group(1)
                .lower()
            )

            if any(
                role in role_text
                for role in (
                    "controller",
                    "master",
                    "active",
                )
            ):
                return True

    return False


def _verify_running_stack(
    master_connection,
    expected_members,
):
    print()
    print("=" * 70)
    print(
        "                 VERIFY RUNNING STACK"
    )
    print("=" * 70)

    output = _run_command(
        master_connection,
        COMMAND_SHOW_STACK,
        timeout=COMMAND_TIMEOUT,
        display=True,
    )

    unit_ids = _get_stack_unit_ids(
        output
    )

    print()
    print(
        f"Detected Stack Unit IDs : "
        f"{unit_ids}"
    )

    if not unit_ids:
        print(
            "FAIL: No stack members detected."
        )

        return False

    missing = [
        unit_id
        for unit_id in range(
            1,
            expected_members + 1,
        )
        if unit_id not in unit_ids
    ]

    if missing:
        print(
            "FAIL: Missing expected "
            f"Unit-ID(s): {missing}"
        )

        return False

    if not _controller_found(
        output
    ):
        print(
            "FAIL: Unit-1 Controller/Master "
            "was not detected."
        )

        return False

    print(
        "PASS: Running stack verified."
    )

    return True


# ============================================================================
# PORT-CHANNEL PARSER
# ============================================================================

def _normalize_interface_name(
    name,
):
    if not name:
        return ""

    value = (
        name.strip()
        .lower()
    )

    replacements = {
        "gigabitethernet": "gi",
        "tengigabitethernet": "te",
        "twentyfivegigabitethernet": "tf",
        "twohundredgigabitethernet": "two",
        "hundredgigabitethernet": "hu",
    }

    for long_name, short_name in (
        replacements.items()
    ):
        value = value.replace(
            long_name,
            short_name,
        )

    return value


def _extract_po1_members(output):
    """
    Extract ONLY active Po1 member interfaces.

    Example supported output:

        Po1      Active: gi1/0/1,gi3/0/1 Non-candidate: gi2/0/1

    Result:

        gi1/0/1
        gi3/0/1

    IMPORTANT:
        Interfaces listed under "Non-candidate" are NOT treated
        as active Po1 members.
    """

    members = []

    interface_prefixes = (
        r"gi|"
        r"te|"
        r"tf|"
        r"two|"
        r"hu|"
        r"gigabitethernet|"
        r"tengigabitethernet|"
        r"twentyfivegigabitethernet|"
        r"twohundredgigabitethernet|"
        r"hundredgigabitethernet"
    )

    interface_pattern = re.compile(
        rf"\b({interface_prefixes})"
        rf"(\d+)/(\d+)/(\d+)"
        rf"(?:-(\d+))?\b",
        re.I,
    )

    clean_output = _remove_pager_prompt(
        _remove_ansi(output or "")
    )

    in_po1 = False

    for raw_line in clean_output.splitlines():

        line = raw_line.strip()

        if not line:
            continue

        # --------------------------------------------------------------
        # Find Po1 line
        # --------------------------------------------------------------
        po_match = re.match(
            r"^Po1\b(.*)$",
            line,
            re.I,
        )

        if po_match:
            in_po1 = True
            search_text = po_match.group(1)

        elif (
            in_po1
            and re.match(
                r"^Po\d+\b",
                line,
                re.I,
            )
        ):
            # Next Port-Channel found.
            break

        elif in_po1:
            search_text = line

        else:
            continue

        # --------------------------------------------------------------
        # ONLY process the ACTIVE section.
        #
        # Example:
        #
        # Active: gi1/0/1,gi3/0/1 Non-candidate: gi2/0/1
        #
        # We keep:
        #   gi1/0/1
        #   gi3/0/1
        #
        # We IGNORE:
        #   gi2/0/1
        # --------------------------------------------------------------

        active_match = re.search(
            r"\bActive\s*:\s*(.*?)(?=\bNon-candidate\s*:|$)",
            search_text,
            re.I,
        )

        if active_match:
            active_text = active_match.group(1)

        else:
            # Support multiline output where the line itself may
            # contain only active interfaces.
            #
            # But NEVER parse a line containing Non-candidate as
            # active member information unless Active: is present.
            if re.search(
                r"\bNon-candidate\s*:",
                search_text,
                re.I,
            ):
                continue

            active_text = search_text

        # --------------------------------------------------------------
        # Extract interfaces from ACTIVE text only
        # --------------------------------------------------------------
        for match in interface_pattern.finditer(active_text):

            prefix = match.group(1)
            slot = match.group(2)
            subslot = match.group(3)

            first_port = int(
                match.group(4)
            )

            last_port = match.group(5)

            if last_port:
                last_port = int(last_port)
            else:
                last_port = first_port

            normalized_prefix = _normalize_interface_name(
                prefix
            )

            # Expand ranges:
            #
            # gi1/0/1-3
            #
            # becomes:
            #
            # gi1/0/1
            # gi1/0/2
            # gi1/0/3
            #
            for port_number in range(
                first_port,
                last_port + 1,
            ):

                normalized = (
                    f"{normalized_prefix}"
                    f"{slot}/{subslot}/"
                    f"{port_number}"
                )

                if normalized not in members:
                    members.append(normalized)

    return members


def _extract_load_balancing(
    output,
):
    match = re.search(
        r"Load balancing\s*:\s*(.+)",
        _remove_ansi(
            output or ""
        ),
        re.I,
    )

    if match:
        return (
            match.group(1)
            .strip()
        )

    return None


# ============================================================================
# SHOW PORT-CHANNEL
# ============================================================================

def _show_port_channel(
    master_connection,
    title,
):
    print()
    print("=" * 70)
    print(
        f"                  {title}"
    )
    print("=" * 70)

    _run_command(
        master_connection,
        COMMAND_CONFIG,
        timeout=COMMAND_TIMEOUT,
        display=True,
    )

    output = _run_command(
        master_connection,
        COMMAND_SHOW_PORT_CHANNEL,
        timeout=COMMAND_TIMEOUT,
        display=True,
    )

    _run_command(
        master_connection,
        COMMAND_END,
        timeout=COMMAND_TIMEOUT,
        display=True,
    )

    return output


# ============================================================================
# PING HELPERS
# ============================================================================

def _ping_is_success(
    output,
):
    text = _remove_ansi(
        output or ""
    ).lower()

    success_patterns = (
        r"reply from",
        r"bytes from",
        r"icmp_seq=.*time=",
        r"time[=<]\s*\d+",
        r"ttl=",
        r"success",
    )

    return any(
        re.search(
            pattern,
            text,
            re.I,
        )
        for pattern in success_patterns
    )


def _ping_is_failure(
    output,
):
    text = _remove_ansi(
        output or ""
    ).lower()

    failure_patterns = (
        "request timed out",
        "timeout",
        "unreachable",
        "100% packet loss",
        "no route",
        "unknown host",
        "failed",
    )

    return any(
        pattern in text
        for pattern in failure_patterns
    )


def _run_ping_batch(
    connection,
    command,
    expected_count,
    label,
):
    print()
    print(f"{label}")
    print()
    print(f">>> {command}")

    try:
        output = _run_command(
            connection,
            command,
            timeout=COMMAND_TIMEOUT,
            display=True,
        )

        text = _remove_ansi(
            output or ""
        ).lower()

        # Try to get actual received packet count.
        received = 0

        match = re.search(
            r"(\d+)\s+packets?\s+received",
            text,
            re.I,
        )

        if match:
            received = int(
                match.group(1)
            )
        else:
            match = re.search(
                r"(\d+)\s+packets?\s+received",
                text,
                re.I,
            )
            if match:
                received = int(
                    match.group(1)
                )

        # Fallback: count successful ICMP replies.
        if received == 0:
            received = len(
                re.findall(
                    r"bytes from",
                    text,
                    re.I,
                )
            )

        failed = expected_count - received

        if failed < 0:
            failed = 0

        print()
        print(
            f"{label} SUMMARY"
        )
        print(
            f"  Packets sent     : {expected_count}"
        )
        print(
            f"  Successful      : {received}"
        )
        print(
            f"  Failed/Timeout  : {failed}"
        )

        return received, failed, output

    except Exception as exc:
        print()
        print(
            f"{label} ERROR : {exc}"
        )
        return 0, expected_count, ""


# ============================================================================
# TC-STK-010
# ============================================================================

def run_tc_stk_010(
    master_connection,
    master_ip,
    master_username,
    master_password,
    connection_type,
    expected_members=2,
    **kwargs,
):
    print()
    print("=" * 70)
    print(
        f"              {TEST_CASE_ID}"
    )
    print(
        f"              {TEST_CASE_TITLE}"
    )
    print("=" * 70)

    # ------------------------------------------------------------------
    # STEP 1 - Verify running stack
    # ------------------------------------------------------------------

    print()
    print(
        "STEP 1 : Verify running stack"
    )

    master_connection = (
        _ensure_master_connection(
            master_connection,
            master_ip,
            master_username,
            master_password,
            connection_type,
        )
    )

    if not _verify_running_stack(
        master_connection,
        expected_members,
    ):
        print()
        print(
            f"{TEST_CASE_ID} RESULT : FAIL"
        )

        return False

    # ------------------------------------------------------------------
    # STEP 2 - Verify Port-Channel BEFORE traffic
    # ------------------------------------------------------------------

    print()
    print(
        "STEP 2 : Verify initial "
        "Port-Channel"
    )

    initial_output = (
        _show_port_channel(
            master_connection,
            "VERIFY PORT-CHANNEL - BEFORE TRAFFIC",
        )
    )

    initial_members = (
        _extract_po1_members(
            initial_output
        )
    )

    initial_load_balancing = (
        _extract_load_balancing(
            initial_output
        )
    )

    print()
    print(
        "Initial Po1 member ports:"
    )

    if initial_members:
        for port in initial_members:
            print(
                f"  - {port}"
            )

    else:
        print(
            "  No Po1 member ports detected."
        )

    if not initial_members:
        print()
        print(
            "FAIL: Po1 has no active "
            "member ports."
        )

        print()
        print(
            f"{TEST_CASE_ID} RESULT : FAIL"
        )

        return False

    if len(initial_members) < 2:
        print()
        print(
            "FAIL: At least 2 active "
            "Po1 members are required "
            "for this failover test."
        )

        print()
        print(
            f"{TEST_CASE_ID} RESULT : FAIL"
        )

        return False

    print()
    print(
        "Initial Load Balancing : "
        f"{initial_load_balancing or 'Not detected'}"
    )

    # ------------------------------------------------------------------
    # STEP 3 - Select member to disconnect
    # ------------------------------------------------------------------

    print()
    print(
        "STEP 3 : Select one LAG member "
        "for failure test"
    )

    print()
    print("=" * 70)
    print(
        "             SELECT LAG MEMBER TO DISCONNECT"
    )
    print("=" * 70)

    for index, port in enumerate(
        initial_members,
        start=1,
    ):
        print(
            f"{index}. {port}"
        )

    while True:
        choice = input(
            "\nSelect member to disconnect "
            f"[1-{len(initial_members)}]: "
        ).strip()

        if (
            choice.isdigit()
            and 1 <= int(choice) <= len(initial_members)
        ):
            failed_member = (
                initial_members[
                    int(choice) - 1
                ]
            )

            break

        print(
            "Invalid selection."
        )

    remaining_expected = [
        port
        for port in initial_members
        if port != failed_member
    ]

    print()
    print(
        f"Selected LAG member : "
        f"{failed_member}"
    )

    # ------------------------------------------------------------------
    # STEP 4 - Start traffic from Stack MASTER
    # ------------------------------------------------------------------

    print()
    print(
        "STEP 4 : Start traffic test"
    )

    print()
    print("=" * 70)
    print(
        "                 TRAFFIC TEST"
    )
    print("=" * 70)

    print(
        "Traffic source : Stack MASTER / Unit-ID 1"
    )

    print(
        "Destination     : 8.8.8.8"
    )

    print(
        f"Total pings     : {TOTAL_PINGS}"
    )

    print(
        f"Before failure  : "
        f"{PINGS_BEFORE_DISCONNECT} pings"
    )

    print(
        f"After failure   : "
        f"{PINGS_AFTER_DISCONNECT} pings"
    )

    print()
    print(
        "IMPORTANT:"
    )

    print(
        "The ping traffic is generated "
        "FROM THE STACK MASTER."
    )

    print(
        "The PC running this automation "
        "script is NOT used for traffic."
    )

    # ------------------------------------------------------------------
    # STEP 5 - First 10 pings
    # ------------------------------------------------------------------

    print()
    print("=" * 70)
    print(
        "       TRAFFIC OBSERVATION - BEFORE DISCONNECT"
    )
    print("=" * 70)

    before_success, before_failed, _ = _run_ping_batch(
        master_connection,
        PING_COMMAND_BEFORE,
        PINGS_BEFORE_DISCONNECT,
        "FIRST 10 PINGS - BEFORE DISCONNECT",
    )

    print()
    print(
        "Before-disconnect traffic summary:"
    )

    print(
        f"  Successful : "
        f"{before_success}/{PINGS_BEFORE_DISCONNECT}"
    )

    print(
        f"  Failed     : "
        f"{before_failed}/{PINGS_BEFORE_DISCONNECT}"
    )

    # ------------------------------------------------------------------
    # STEP 6 - User Assist
    # ------------------------------------------------------------------

    _user_assist(
        f"""
Continuous traffic test is running from
the Stack MASTER / Unit-ID 1.

Selected LAG member for failure:

    {failed_member}

Please now DISCONNECT / POWER OFF this ONE
physical LAG member.

Do NOT disconnect the stack cable.
Do NOT power off the complete switch.

Only the selected LAG member should be
disconnected:

    {failed_member}

After the cable is disconnected and the link
is physically DOWN, press ENTER.

The script will then continue with the
remaining {PINGS_AFTER_DISCONNECT} pings to
8.8.8.8.
"""
    )

    # ------------------------------------------------------------------
    # STEP 7 - Remaining 30 pings
    # ------------------------------------------------------------------

    print()
    print("=" * 70)
    print(
        "        TRAFFIC OBSERVATION - AFTER DISCONNECT"
    )
    print("=" * 70)

    print(
        f"Failed member : "
        f"{failed_member}"
    )

    print(
        "Continuing traffic from "
        "Stack MASTER / Unit-ID 1..."
    )

    after_success, after_failed, _ = _run_ping_batch(
        master_connection,
        PING_COMMAND_AFTER,
        PINGS_AFTER_DISCONNECT,
        "REMAINING 30 PINGS - AFTER DISCONNECT",
    )

    print()
    print(
        "After-disconnect traffic summary:"
    )

    print(
        f"  Successful : "
        f"{after_success}/{PINGS_AFTER_DISCONNECT}"
    )

    print(
        f"  Failed     : "
        f"{after_failed}/{PINGS_AFTER_DISCONNECT}"
    )

    # ------------------------------------------------------------------
    # STEP 8 - Final Port-Channel verification
    # ------------------------------------------------------------------

    print()
    print(
        "STEP 8 : Verify final "
        "Port-Channel"
    )

    final_output = (
        _show_port_channel(
            master_connection,
            "VERIFY PORT-CHANNEL - AFTER CABLE DISCONNECT",
        )
    )

    final_members = (
        _extract_po1_members(
            final_output
        )
    )

    final_load_balancing = (
        _extract_load_balancing(
            final_output
        )
    )

    print()
    print(
        "Final Po1 member ports:"
    )

    if final_members:
        for port in final_members:
            print(
                f"  - {port}"
            )

    else:
        print(
            "  No Po1 member ports detected."
        )

    print()
    print(
        "Final Load Balancing : "
        f"{final_load_balancing or 'Not detected'}"
    )

    # ------------------------------------------------------------------
    # STEP 9 - Evaluate result
    # ------------------------------------------------------------------

    print()
    print("=" * 70)
    print(
        "                    TEST RESULT"
    )
    print("=" * 70)

    failed_member_removed = (
        failed_member
        not in final_members
    )

    remaining_members_active = all(
        port in final_members
        for port in remaining_expected
    )

    traffic_continued = (
        after_success > 0
    )

    print(
        f"Selected failed member     : "
        f"{failed_member}"
    )

    print(
        f"Failed member removed      : "
        f"{'YES' if failed_member_removed else 'NO'}"
    )

    print(
        f"Remaining LAG members UP   : "
        f"{'YES' if remaining_members_active else 'NO'}"
    )

    print(
        f"Traffic received after fail: "
        f"{'YES' if traffic_continued else 'NO'}"
    )

    print(
        f"After-disconnect ping      : "
        f"{after_success}/{PINGS_AFTER_DISCONNECT} "
        f"successful"
    )

    # --------------------------------------------------------------
    # Final PASS condition
    #
    # 1. Selected member must disappear from Po1.
    # 2. Remaining members must stay active.
    # 3. At least one ping must succeed after failure.
    #
    # A short timeout during LAG convergence is acceptable.
    # --------------------------------------------------------------

    result = (
        failed_member_removed
        and remaining_members_active
        and traffic_continued
    )

    print()
    print("=" * 70)

    if result:
        print(
            f"{TEST_CASE_ID} RESULT : PASS"
        )

        print()
        print(
            "LAG failover verified successfully."
        )

        print(
            "Traffic continued through the "
            "remaining LAG member(s)."
        )

    else:
        print(
            f"{TEST_CASE_ID} RESULT : FAIL"
        )

        if not failed_member_removed:
            print(
                "FAIL: Selected failed member "
                "is still present in Po1."
            )

        if not remaining_members_active:
            print(
                "FAIL: One or more remaining "
                "LAG members are not active."
            )

        if not traffic_continued:
            print(
                "FAIL: No successful traffic "
                "was observed after member failure."
            )

    print("=" * 70)

    # Keep MASTER connection active for the
    # next test case.
    return result

