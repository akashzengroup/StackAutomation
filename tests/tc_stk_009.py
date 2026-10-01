import time
import re

from connection import SwitchConnection


TEST_CASE_ID = "TC-STK-009"
TEST_CASE_TITLE = "LACP Port-Channel / LAG Across Stack Units"

COMMAND_SHOW_STACK = "sh stack"
COMMAND_CONFIG = "config"
COMMAND_END = "end"
COMMAND_EXIT = "exit"
COMMAND_CHANNEL_GROUP = "channel-group 1 mode auto"
COMMAND_PORT_CHANNEL = "interface Port-Channel1"
COMMAND_PORT_CHANNEL_TRUNK = "switchport mode trunk"
COMMAND_SHOW_PORT_CHANNEL = "do sh interface port-channel"
COMMAND_SHOW_LOGGING = "show logging"

COMMAND_TIMEOUT = 30
LAG_FORMATION_WAIT = 10

# User-requested port type menu.
# short_name is used for display/normalization.
# cli_name is used in the actual "interface" configuration command.
PORT_TYPE_OPTIONS = {
    "1": {
        "short_name": "gi",
        "display": "Gi1/0/1",
        "cli_name": "GigabitEthernet",
    },
    "2": {
        "short_name": "te",
        "display": "Te1/0/1",
        "cli_name": "TenGigabitEthernet",
    },
    "3": {
        "short_name": "tf",
        "display": "Tf1/0/1",
        "cli_name": "TwentyFiveGigabitEthernet",
    },
    "4": {
        "short_name": "two",
        "display": "Two1/0/1",
        "cli_name": "TwoHundredGigabitEthernet",
    },
    "5": {
        "short_name": "hu",
        "display": "Hu1/0/1",
        "cli_name": "HundredGigabitEthernet",
    },
}


# ---------------------------------------------------------------------------
# CONNECTION HELPERS
# ---------------------------------------------------------------------------

def _connection_is_usable(connection):
    if connection is None:
        return False

    shell = getattr(connection, "shell", None)
    if shell is None:
        shell = getattr(connection, "ssh_shell", None)

    if shell is None:
        return False

    try:
        if getattr(shell, "closed", False):
            return False
    except Exception:
        pass

    return True


def _update_connection_object(old_connection, new_connection):
    if old_connection is None or new_connection is None:
        return new_connection

    try:
        old_connection.__dict__.update(new_connection.__dict__)
        return old_connection
    except Exception:
        return new_connection


def _connect_switch(ip, username, password, connection_type):
    connection = SwitchConnection(
        connection_type=connection_type,
        ip=ip,
        username=username,
        password=password,
    )
    connection.connect()
    return connection


def _reconnect_master(
    master_connection,
    master_ip,
    master_username,
    master_password,
    connection_type,
):
    print()
    print("=" * 70)
    print("              MASTER CONNECTION CHECK")
    print("=" * 70)

    if _connection_is_usable(master_connection):
        try:
            print(f"Using existing MASTER connection : {master_ip}")
            master_connection.send_command(
                COMMAND_SHOW_STACK,
                timeout=COMMAND_TIMEOUT,
            )
            print("MASTER connection is active.")
            return master_connection
        except Exception:
            print("Existing MASTER connection is not usable.")
            print("Reconnecting...")

    while True:
        try:
            print(f"Connecting to MASTER : {master_ip}")

            new_connection = _connect_switch(
                master_ip,
                master_username,
                master_password,
                connection_type,
            )

            print("MASTER connection established.")
            return _update_connection_object(
                master_connection,
                new_connection,
            )

        except Exception as exc:
            print(f"MASTER connection failed: {exc}")
            print("Retrying in 5 seconds...")
            time.sleep(5)


def _ensure_master_connection(
    master_connection,
    master_ip,
    master_username,
    master_password,
    connection_type,
):
    return _reconnect_master(
        master_connection,
        master_ip,
        master_username,
        master_password,
        connection_type,
    )


# ---------------------------------------------------------------------------
# TERMINAL / OUTPUT HELPERS
# ---------------------------------------------------------------------------

def _remove_ansi(text):
    if not text:
        return ""
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)


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
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    return text


def _print_clean_chunk(chunk):
    if not chunk or not chunk.strip():
        return

    chunk = _remove_ansi(chunk)
    print(chunk, end="" if chunk.endswith("\n") else "\n")


def _send_raw(connection_or_shell, data):
    for method_name in ("send_raw", "write", "send"):
        method = getattr(connection_or_shell, method_name, None)

        if callable(method):
            try:
                method(data)
                return True
            except Exception:
                pass

    return False


def _clear_shell(connection):
    for method_name in ("clear_buffer", "clear_shell", "flush"):
        method = getattr(connection, method_name, None)

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
        raise RuntimeError("Switch connection is not available.")

    print(f">>> {command}")

    send_command = getattr(connection, "send_command", None)

    if callable(send_command):
        try:
            output = send_command(command, timeout=timeout)
            output = "" if output is None else _remove_ansi(str(output))

            if display:
                _print_clean_chunk(output)

            return output

        except TypeError:
            pass
        except Exception:
            pass

    shell = getattr(connection, "shell", None)
    if shell is None:
        shell = getattr(connection, "ssh_shell", None)

    if shell is None:
        raise RuntimeError(
            "SwitchConnection does not provide a supported command execution method."
        )

    _clear_shell(connection)

    shell.send(command + "\n")

    output_parts = []
    start = time.time()

    while time.time() - start < timeout:
        try:
            if hasattr(shell, "recv_ready") and shell.recv_ready():
                chunk = shell.recv(65535)

                if isinstance(chunk, bytes):
                    chunk = chunk.decode(errors="ignore")

                if chunk:
                    output_parts.append(chunk)

                    clean = _remove_ansi(chunk)

                    if display:
                        _print_clean_chunk(clean)

                    if re.search(
                        r"More:\s*<space>|--More--|Press\s+SPACE",
                        clean,
                        re.I,
                    ):
                        _send_raw(shell, " ")

                    continue

        except Exception:
            pass

        time.sleep(0.1)

    return _remove_pager_prompt(
        _remove_ansi("".join(output_parts))
    )


def _run_command(connection, command, timeout=COMMAND_TIMEOUT, display=True):
    return _get_command_output(
        connection,
        command,
        timeout=timeout,
        display=display,
    )


# ---------------------------------------------------------------------------
# USER ASSIST
# ---------------------------------------------------------------------------

def _user_assist(message):
    print()
    print("=" * 70)
    print("                    USER ASSIST")
    print("=" * 70)
    print(message)
    input("\nAfter completing the above step, press ENTER to continue...")
    print()


# ---------------------------------------------------------------------------
# STACK HELPERS
# ---------------------------------------------------------------------------

def _get_stack_unit_ids(stack_output):
    unit_ids = []

    for raw_line in (stack_output or "").splitlines():
        line = _remove_ansi(raw_line).strip()

        match = re.match(r"^(\d+)\s+", line)

        if match:
            unit_id = int(match.group(1))

            if 1 <= unit_id <= 64:
                unit_ids.append(unit_id)

    return sorted(set(unit_ids))


def _controller_found(stack_output):
    for raw_line in (stack_output or "").splitlines():
        line = _remove_ansi(raw_line).strip()

        match = re.match(r"^1\s+(.+)$", line, re.I)

        if match:
            role_text = match.group(1).lower()

            if any(
                role in role_text
                for role in ("controller", "master", "active")
            ):
                return True

    return False


def _verify_running_stack(master_connection, expected_members):
    print()
    print("=" * 70)
    print("                 VERIFY RUNNING STACK")
    print("=" * 70)

    output = _run_command(
        master_connection,
        COMMAND_SHOW_STACK,
        timeout=COMMAND_TIMEOUT,
        display=True,
    )

    unit_ids = _get_stack_unit_ids(output)

    print(f"\nDetected Stack Unit IDs : {unit_ids}")

    if not unit_ids:
        print("FAIL: No stack members detected.")
        return False

    missing = [
        unit_id
        for unit_id in range(1, expected_members + 1)
        if unit_id not in unit_ids
    ]

    if missing:
        print(f"FAIL: Missing expected Unit-ID(s): {missing}")
        return False

    if not _controller_found(output):
        print("FAIL: Unit-1 Controller/Master was not detected.")
        return False

    print("PASS: Running stack verified.")
    return True


# ---------------------------------------------------------------------------
# PORT SELECTION
# ---------------------------------------------------------------------------

def _select_port_type(unit_label):
    print(f"\nSelect port type for {unit_label}:")
    print("1. Gi1/0/1")
    print("2. Te1/0/1")
    print("3. Tf1/0/1")
    print("4. Two1/0/1")
    print("5. Hu1/0/1")

    while True:
        choice = input(
            f"Enter port type for {unit_label} [1-5]: "
        ).strip()

        if choice in PORT_TYPE_OPTIONS:
            return PORT_TYPE_OPTIONS[choice]

        print("Invalid selection. Please select 1 to 5.")


def _get_port_numbers(unit_label):
    """
    Accept a single port or a port range.

    Examples:
        1       -> [1]
        1-3     -> [1, 2, 3]
        3-5     -> [3, 4, 5]
    """
    while True:
        value = input(
            f"Enter LACP port number(s) for {unit_label} "
            f"(example: 1 or 1-3): "
        ).strip()

        if value.isdigit() and int(value) >= 1:
            return [int(value)]

        match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", value)
        if match:
            first = int(match.group(1))
            last = int(match.group(2))

            if first >= 1 and last >= first:
                return list(range(first, last + 1))

        print(
            "Invalid port number/range. Please enter a number "
            "such as 1 or a range such as 1-3."
        )


def _build_interface(
    port_info,
    unit_id,
    port_number,
):
    return (
        f"{port_info['cli_name']}"
        f"{unit_id}/0/{port_number}"
    )


def _build_display_interface(
    port_info,
    unit_id,
    port_number,
):
    return (
        f"{port_info['display'].split('1/0/')[0]}"
        f"{unit_id}/0/{port_number}"
    )


def _normalize_interface_name(name):
    if not name:
        return ""

    value = name.strip().lower()

    replacements = {
        "gigabitethernet": "gi",
        "tengigabitethernet": "te",
        "twentyfivegigabitethernet": "tf",
        "twohundredgigabitethernet": "two",
        "hundredgigabitethernet": "hu",
    }

    for long_name, short_name in replacements.items():
        value = value.replace(long_name, short_name)

    return value


# ---------------------------------------------------------------------------
# ENDPOINT SELECTION
# ---------------------------------------------------------------------------

def _ask_use_unit(unit_id, stack_name):
    while True:
        answer = input(
            f"Use {stack_name} Unit-{unit_id} for LACP? [Y/N]: "
        ).strip().lower()

        if answer in ("y", "yes"):
            return True

        if answer in ("n", "no"):
            return False

        print("Please enter Y or N.")


def _collect_stack_lacp_ports(
    stack_name,
    unit_count,
    allow_empty=False,
):
    selected_ports = []

    print()
    print("=" * 70)
    print(f"       SELECT LACP PORTS - {stack_name}")
    print("=" * 70)

    for unit_id in range(1, unit_count + 1):
        use_unit = _ask_use_unit(unit_id, stack_name)

        if not use_unit:
            continue

        port_info = _select_port_type(
            f"{stack_name} Unit-{unit_id}"
        )

        port_numbers = _get_port_numbers(
            f"{stack_name} Unit-{unit_id}"
        )

        for port_number in port_numbers:
            selected_ports.append(
                {
                    "stack_name": stack_name,
                    "unit_id": unit_id,
                    "port_info": port_info,
                    "port_number": port_number,
                    "interface": _build_interface(
                        port_info,
                        unit_id,
                        port_number,
                    ),
                    "display_interface": _build_display_interface(
                        port_info,
                        unit_id,
                        port_number,
                    ),
                }
            )

    if not selected_ports and not allow_empty:
        print(
            f"\nAt least one LACP port must be selected from {stack_name}."
        )

    return selected_ports


def _ask_other_switch_type():
    print()
    print("=" * 70)
    print("                 SECOND SWITCH TYPE")
    print("=" * 70)
    print("Is the second switch also a stack?")
    print("1. Yes - Stack")
    print("2. No  - Standalone")

    while True:
        choice = input("Select [1-2]: ").strip()

        if choice == "1":
            return True

        if choice == "2":
            return False

        print("Invalid selection. Please select 1 or 2.")


def _collect_standalone_lacp_port():
    print()
    print("=" * 70)
    print("          SELECT LACP PORT - STANDALONE SWITCH")
    print("=" * 70)

    port_info = _select_port_type("Standalone Switch")
    port_numbers = _get_port_numbers("Standalone Switch")

    selected_ports = []

    for port_number in port_numbers:
        selected_ports.append(
            {
                "stack_name": "Standalone",
                "unit_id": 1,
                "port_info": port_info,
                "port_number": port_number,
                "interface": _build_interface(
                    port_info,
                    1,
                    port_number,
                ),
                "display_interface": _build_display_interface(
                    port_info,
                    1,
                    port_number,
                ),
            }
        )

    return selected_ports


def _get_second_switch_credentials(connection_type):
    print()
    print("=" * 70)
    print("             SECOND SWITCH CONNECTION")
    print("=" * 70)

    ip = input("Second switch IP : ").strip()
    username = input("Username         : ").strip()
    password = input("Password         : ").strip()

    return {
        "ip": ip,
        "username": username,
        "password": password,
        "connection_type": connection_type,
    }


def _connect_second_switch(info):
    print(f"\nConnecting to second switch : {info['ip']}")

    while True:
        try:
            connection = _connect_switch(
                info["ip"],
                info["username"],
                info["password"],
                info["connection_type"],
            )

            print("Second switch connection established.")
            return connection

        except Exception as exc:
            print(f"Second switch connection failed: {exc}")
            retry = input("Retry connection? [Y/N]: ").strip().lower()

            if retry not in ("y", "yes"):
                return None


# ---------------------------------------------------------------------------
# LACP CONFIGURATION
# ---------------------------------------------------------------------------

def _configure_lacp_ports(connection, selected_ports, endpoint_name):
    if not selected_ports:
        return False

    print()
    print("=" * 70)
    print(f"CONFIGURING LACP - {endpoint_name}")
    print("=" * 70)

    # All requested commands are executed from config mode.
    _run_command(connection, COMMAND_CONFIG)

    for item in selected_ports:
        interface_name = item["interface"]

        print(f"\nConfiguring interface : {interface_name}")

        _run_command(
            connection,
            f"interface {interface_name}",
        )

        _run_command(
            connection,
            COMMAND_CHANNEL_GROUP,
        )

        _run_command(
            connection,
            COMMAND_EXIT,
        )

    _run_command(
        connection,
        COMMAND_PORT_CHANNEL,
    )

    _run_command(
        connection,
        COMMAND_PORT_CHANNEL_TRUNK,
    )

    _run_command(
        connection,
        COMMAND_END,
    )

    print(
        f"\nPASS: LACP configuration sent for {endpoint_name}."
    )

    return True


# ---------------------------------------------------------------------------
# LOG / PORT-CHANNEL VERIFICATION
# ---------------------------------------------------------------------------

def _extract_po1_members(output):
    """
    Extract actual member interfaces shown under Po1.

    Supports:
        gi1/0/1
        gi1/0/1-3
        gi1/0/1-3,gi1/0/5-6
        Te2/0/1-4
        GigabitEthernet1/0/1-3

    A range such as gi1/0/1-3 is expanded to:
        gi1/0/1
        gi1/0/2
        gi1/0/3
    """

    members = []

    interface_prefixes = (
        r"gi|te|tf|two|hu|"
        r"gigabitethernet|"
        r"tengigabitethernet|"
        r"twentyfivegigabitethernet|"
        r"twohundredgigabitethernet|"
        r"hundredgigabitethernet"
    )

    interface_pattern = re.compile(
        rf"\b({interface_prefixes})(\d+)/(\d+)/(\d+)(?:-(\d+))?\b",
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

        # Start of Po1 line
        po_match = re.match(
            r"^Po1\b(.*)$",
            line,
            re.I,
        )

        if po_match:
            in_po1 = True
            search_text = po_match.group(1)

        # Stop when another Port-Channel starts
        elif in_po1 and re.match(
            r"^Po\d+\b",
            line,
            re.I,
        ):
            break

        elif in_po1:
            search_text = line

        else:
            continue

        # Find interfaces and expand ranges
        for match in interface_pattern.finditer(search_text):

            prefix = match.group(1)
            slot = match.group(2)
            subslot = match.group(3)
            first_port = int(match.group(4))
            last_port = match.group(5)

            if last_port:
                last_port = int(last_port)
            else:
                last_port = first_port

            # Normalize long interface name
            normalized_prefix = _normalize_interface_name(prefix)

            # Expand interface range
            for port_number in range(first_port, last_port + 1):

                normalized = (
                    f"{normalized_prefix}"
                    f"{slot}/{subslot}/{port_number}"
                )

                if normalized not in members:
                    members.append(normalized)

    return members


def _extract_load_balancing(output):
    match = re.search(
        r"Load balancing\s*:\s*(.+)",
        _remove_ansi(output or ""),
        re.I,
    )

    return match.group(1).strip() if match else None


def _extract_lacp_status_lines(output):
    lines = []

    for raw_line in _remove_ansi(output or "").splitlines():
        line = raw_line.strip()

        if not line:
            continue

        lower = line.lower()

        if (
            "po1" in lower
            or "port-channel1" in lower
            or "up" in lower
            or "down" in lower
            or "lacp" in lower
        ):
            lines.append(line)

    return lines


def _show_logs(connection, endpoint_name):
    print()
    print("=" * 70)
    print(f"                 {endpoint_name} LOGS")
    print("=" * 70)

    try:
        output = _run_command(
            connection,
            COMMAND_SHOW_LOGGING,
            timeout=COMMAND_TIMEOUT,
            display=True,
        )

        if not output.strip():
            print("No log output received.")

        return output

    except Exception as exc:
        print(f"Unable to retrieve logs from {endpoint_name}: {exc}")
        return ""


def _verify_port_channel(
    connection,
    expected_ports,
    endpoint_name,
):
    print()
    print("=" * 70)
    print(f"        VERIFY PORT-CHANNEL - {endpoint_name}")
    print("=" * 70)

    # Verification command is also executed from config mode.
    _run_command(
        connection,
        COMMAND_CONFIG,
    )

    output = _run_command(
        connection,
        COMMAND_SHOW_PORT_CHANNEL,
        timeout=COMMAND_TIMEOUT,
        display=True,
    )

    _run_command(
        connection,
        COMMAND_END,
    )

    load_balancing = _extract_load_balancing(output)
    actual_members = _extract_po1_members(output)

    expected = [
        _normalize_interface_name(item["interface"])
        for item in expected_ports
    ]

    print(
        f"\nLoad Balancing : "
        f"{load_balancing or 'Not detected'}"
    )

    print("\nActual Po1 member ports:")
    if actual_members:
        for port in actual_members:
            print(f"  - {port}")
    else:
        print("  No member ports detected under Po1.")

    print("\nExpected Po1 member ports:")
    for port in expected:
        print(f"  - {port}")

    missing = [
        port
        for port in expected
        if port not in actual_members
    ]

    if missing:
        print("\nFAIL: Expected port(s) are missing from Po1:")
        for port in missing:
            print(f"  - {port}")
        return False

    if not actual_members:
        print(
            "\nFAIL: No actual member ports were detected under Po1."
        )
        return False

    if not load_balancing:
        print(
            "\nWARNING: Load balancing information was not detected."
        )

    print(
        f"\nPASS: Po1 member verification passed for {endpoint_name}."
    )

    if load_balancing:
        print(
            f"PASS: Load balancing : {load_balancing}"
        )

    return True


# ---------------------------------------------------------------------------
# CONFIGURATION PLAN DISPLAY
# ---------------------------------------------------------------------------

def _display_lacp_plan(stack_ports, second_stack_ports):
    print()
    print("=" * 70)
    print("                  LACP CONFIGURATION PLAN")
    print("=" * 70)

    print("\nFIRST STACK LACP PORTS:")

    for item in stack_ports:
        print(
            f"  Unit-{item['unit_id']:<3} : "
            f"{item['display_interface']}"
        )

    print("\nSECOND SWITCH LACP PORTS:")

    for item in second_stack_ports:
        if item["stack_name"] == "Standalone":
            print(
                f"  Standalone : "
                f"{item['display_interface']}"
            )
        else:
            print(
                f"  Unit-{item['unit_id']:<3} : "
                f"{item['display_interface']}"
            )

    print("\nPort-Channel : Po1")
    print("LACP Mode    : auto")
    print("Port Mode    : trunk")


# ---------------------------------------------------------------------------
# MAIN TEST CASE
# ---------------------------------------------------------------------------

def run_tc_stk_009(
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
    print(f"              {TEST_CASE_ID}")
    print(f"              {TEST_CASE_TITLE}")
    print("=" * 70)

    # ------------------------------------------------------------------
    # STEP 1 - Verify running stack
    # ------------------------------------------------------------------
    print("\nSTEP 1 : Verify running stack")

    master_connection = _ensure_master_connection(
        master_connection,
        master_ip,
        master_username,
        master_password,
        connection_type,
    )

    if not _verify_running_stack(
        master_connection,
        expected_members,
    ):
        print("\nTC-STK-009 RESULT : FAIL")
        return False

    # ------------------------------------------------------------------
    # STEP 2 - Select LACP ports from the existing stack
    # ------------------------------------------------------------------
    print(
        "\nSTEP 2 : Select LACP ports from the existing stack"
    )

    print(
        f"\nYour current stack contains "
        f"{expected_members} units."
    )

    print(
        "For every Unit-ID, the script will ask whether "
        "that unit should participate in LACP."
    )

    stack_ports = _collect_stack_lacp_ports(
        "Current Stack",
        expected_members,
    )

    # ------------------------------------------------------------------
    # STEP 3 - Second switch: stack or standalone
    # ------------------------------------------------------------------
    print(
        "\nSTEP 3 : Select the second switch type"
    )

    second_switch_is_stack = _ask_other_switch_type()

    # ------------------------------------------------------------------
    # STEP 4 - Collect second switch connection details
    # ------------------------------------------------------------------
    print(
        "\nSTEP 4 : Enter second switch connection details"
    )

    second_switch_info = _get_second_switch_credentials(
        connection_type
    )

    second_connection = _connect_second_switch(
        second_switch_info
    )

    if second_connection is None:
        print("\nTC-STK-009 RESULT : FAIL")
        return False

    # ------------------------------------------------------------------
    # STEP 5 - Select LACP ports on second switch
    # ------------------------------------------------------------------
    if second_switch_is_stack:
        print(
            "\nSTEP 5 : Verify second switch stack"
        )

        second_stack_output = _run_command(
            second_connection,
            COMMAND_SHOW_STACK,
            timeout=COMMAND_TIMEOUT,
            display=True,
        )

        second_unit_ids = _get_stack_unit_ids(
            second_stack_output
        )

        if not second_unit_ids:
            print(
                "\nFAIL: Second switch was selected as STACK, "
                "but no stack units were detected."
            )

            try:
                second_connection.close()
            except Exception:
                pass

            print("\nTC-STK-009 RESULT : FAIL")
            return False

        print(
            f"\nSecond Stack Unit IDs : {second_unit_ids}"
        )

        print(
            "\nSTEP 6 : Select LACP ports on second stack"
        )

        second_stack_ports = _collect_stack_lacp_ports(
            "Second Stack",
            len(second_unit_ids),
        )

        # Replace generated 1..N assumption with actual detected IDs.
        # This is important if a stack has non-contiguous configured IDs.
        for index, item in enumerate(second_stack_ports):
            selected_unit_id = item["unit_id"]

            if selected_unit_id <= len(second_unit_ids):
                actual_unit_id = second_unit_ids[
                    selected_unit_id - 1
                ]

                item["unit_id"] = actual_unit_id

                item["interface"] = _build_interface(
                    item["port_info"],
                    actual_unit_id,
                    item["port_number"],
                )

                item["display_interface"] = _build_display_interface(
                    item["port_info"],
                    actual_unit_id,
                    item["port_number"],
                )

    else:
        print(
            "\nSTEP 5 : Select LACP port on standalone switch"
        )

        second_stack_ports = _collect_standalone_lacp_port()

    # ------------------------------------------------------------------
    # Validate total number of LACP links
    # ------------------------------------------------------------------
    total_ports = len(stack_ports) + len(second_stack_ports)

    if total_ports < 2:
        print()
        print(
            "FAIL: At least 2 physical links are required "
            "for this LACP test."
        )

        try:
            second_connection.close()
        except Exception:
            pass

        print("\nTC-STK-009 RESULT : FAIL")
        return False

    # ------------------------------------------------------------------
    # STEP 7 - Show complete plan
    # ------------------------------------------------------------------
    print("\nSTEP 7 : Review LACP configuration plan")

    _display_lacp_plan(
        stack_ports,
        second_stack_ports,
    )

    # ------------------------------------------------------------------
    # STEP 8 - Configure first/current stack
    # ------------------------------------------------------------------
    print(
        "\nSTEP 8 : Configure LACP on current stack"
    )

    if not _configure_lacp_ports(
        master_connection,
        stack_ports,
        "CURRENT STACK",
    ):
        try:
            second_connection.close()
        except Exception:
            pass

        print("\nTC-STK-009 RESULT : FAIL")
        return False

    # ------------------------------------------------------------------
    # STEP 9 - Configure second switch
    # ------------------------------------------------------------------
    print(
        "\nSTEP 9 : Configure LACP on second switch"
    )

    if not _configure_lacp_ports(
        second_connection,
        second_stack_ports,
        "SECOND SWITCH",
    ):
        try:
            second_connection.close()
        except Exception:
            pass

        print("\nTC-STK-009 RESULT : FAIL")
        return False

    # ------------------------------------------------------------------
    # STEP 10 - Physical cable connection
    # ------------------------------------------------------------------
    print(
        "\nSTEP 10 : Connect physical LACP cables"
    )

    first_lines = "\n".join(
        f"  Unit-{item['unit_id']} : "
        f"{item['display_interface']}"
        for item in stack_ports
    )

    if second_switch_is_stack:
        second_lines = "\n".join(
            f"  Unit-{item['unit_id']} : "
            f"{item['display_interface']}"
            for item in second_stack_ports
        )
    else:
        second_lines = "\n".join(
            f"  Standalone : "
            f"{item['display_interface']}"
            for item in second_stack_ports
        )

    _user_assist(
        f"""
LACP configuration has been completed on both switches.

Connect the physical LACP cables as follows:

CURRENT STACK:
{first_lines}

SECOND SWITCH:
{second_lines}

IMPORTANT:
1. Connect each selected LACP port to the corresponding port
   on the second switch.
2. Do NOT disconnect the existing stack cables.
3. Do NOT power off any switch.
4. Make sure every selected LACP link is physically connected.
"""
    )

    # ------------------------------------------------------------------
    # STEP 11 - Wait for LACP formation
    # ------------------------------------------------------------------
    print("\nSTEP 11 : Waiting for LACP formation")

    for remaining in range(LAG_FORMATION_WAIT, 0, -1):
        print(
            f"\rWaiting {remaining:02d} seconds...",
            end="",
            flush=True,
        )
        time.sleep(1)

    print("\nLACP formation wait completed.")

    # ------------------------------------------------------------------
    # STEP 12 - Show switch-generated logs
    # ------------------------------------------------------------------
    print(
        "\nSTEP 12 : Collect LACP / Port-Channel logs"
    )

    first_logs = _show_logs(
        master_connection,
        "CURRENT STACK",
    )

    second_logs = _show_logs(
        second_connection,
        "SECOND SWITCH",
    )

    print("\nLACP / Port-Channel related log lines:")

    found_log = False

    for endpoint_name, log_output in (
        ("CURRENT STACK", first_logs),
        ("SECOND SWITCH", second_logs),
    ):
        for line in _extract_lacp_status_lines(log_output):
            lower = line.lower()

            if (
                "po1" in lower
                or "port-channel1" in lower
                or "lacp" in lower
            ):
                print(f"[{endpoint_name}] {line}")
                found_log = True

    if not found_log:
        print(
            "No specific Po1/LACP log line was detected."
        )

    # ------------------------------------------------------------------
    # STEP 13 - Verify current stack Po1
    # ------------------------------------------------------------------
    print(
        "\nSTEP 13 : Verify Po1 on current stack"
    )

    first_result = _verify_port_channel(
        master_connection,
        stack_ports,
        "CURRENT STACK",
    )

    # ------------------------------------------------------------------
    # STEP 14 - Verify second switch Po1
    # ------------------------------------------------------------------
    print(
        "\nSTEP 14 : Verify Po1 on second switch"
    )

    second_result = _verify_port_channel(
        second_connection,
        second_stack_ports,
        "SECOND SWITCH",
    )

    result = first_result and second_result

    print()
    print("=" * 70)
    print(
        f"{TEST_CASE_ID} RESULT : "
        f"{'PASS' if result else 'FAIL'}"
    )
    print("=" * 70)

    # The MASTER connection intentionally remains active.
    # The second switch connection is only used by this test case.
    try:
        second_connection.close()
    except Exception:
        pass

    return result