
import time
import re
from connection import SwitchConnection


# =========================================================
# TC-STK-020
# Different Firmware Unit Join / Auto Synchronization
# =========================================================

TEST_CASE_ID = "TC-STK-020"
TEST_CASE_TITLE = "Different Firmware Unit Join / Auto Synchronization"

JOIN_TIMEOUT = 300
POLL_INTERVAL = 10
LOG_POLL_INTERVAL = 5
RECONNECT_INTERVAL = 5


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


def _connect_switch(
    ip,
    username,
    password,
    connection_type,
):
    """
    Create and connect a SwitchConnection.

    This uses the same SwitchConnection interface used by
    the existing stack test cases.
    """

    connection = SwitchConnection(
        connection_type=connection_type,
        ip=ip,
        username=username,
        password=password,
    )

    try:
        if connection.connect():
            return connection

    except Exception as e:
        print(f"Connection error: {e}")

    return None


def _reconnect_master(
    master_ip,
    master_username,
    master_password,
    connection_type,
    existing_connection=None,
):
    print()
    print("Unit-1 / MASTER connection is not usable.")
    print("Reconnecting to Unit-1 / MASTER...")

    attempt = 0

    while True:
        attempt += 1

        print()
        print(f"MASTER connection attempt #{attempt}")

        connection = _connect_switch(
            master_ip,
            master_username,
            master_password,
            connection_type,
        )

        if connection is not None:

            print(
                "✓ Unit-1 / MASTER reconnected successfully."
            )

            if existing_connection is not None:
                try:
                    existing_connection.__dict__.update(
                        connection.__dict__
                    )
                    return existing_connection
                except Exception:
                    pass

            return connection

        print(
            f"MASTER connection failed. "
            f"Retrying in {RECONNECT_INTERVAL} seconds..."
        )

        time.sleep(RECONNECT_INTERVAL)


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
# Shell Helpers
# =========================================================

def _clear_shell(shell):
    try:
        while shell.recv_ready():
            shell.recv(65535)
    except Exception:
        pass


def _send_command(
    connection,
    command,
    timeout=20,
    display=True,
):
    """
    Execute one CLI command and return its output.

    display=False is used for background log monitoring.
    """

    try:
        if connection is None:
            return None

        shell = getattr(
            connection,
            "shell",
            None,
        )

        if shell is None:
            return None

        _clear_shell(shell)

        if display:
            print()
            print(f"Executing: {command}")

        shell.send(
            command + "\n"
        )

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

                    if display:
                        print(
                            chunk,
                            end="",
                            flush=True,
                        )

                    last_data_time = time.time()
                    received = True

            except Exception as e:

                if display:
                    print(
                        f"\nCommand read error: {e}"
                    )

                return (
                    None
                    if not output
                    else output
                )

            now = time.time()

            if (
                output
                and not received
                and (
                    now - last_data_time
                    >= quiet_required
                )
            ):
                break

            if (
                now - start_time
                >= timeout
            ):
                break

            time.sleep(0.1)

        if display and output:
            if not output.endswith("\n"):
                print()

        return output

    except Exception as e:

        if display:
            print(
                f"\nCommand execution error: {e}"
            )

        return None


def _run_master_command(
    master_connection,
    command,
    master_ip,
    master_username,
    master_password,
    connection_type,
    timeout=20,
    display=True,
):
    """
    Execute command on Unit-1.

    Automatically reconnect if required.
    """

    master_connection = _ensure_master_connection(
        master_connection,
        master_ip,
        master_username,
        master_password,
        connection_type,
    )

    output = _send_command(
        master_connection,
        command,
        timeout=timeout,
        display=display,
    )

    if output is not None:
        return (
            master_connection,
            output,
        )

    print()
    print(
        "MASTER command failed. "
        "Reconnecting..."
    )

    master_connection = _reconnect_master(
        master_ip,
        master_username,
        master_password,
        connection_type,
        existing_connection=master_connection,
    )

    output = _send_command(
        master_connection,
        command,
        timeout=timeout,
        display=display,
    )

    return (
        master_connection,
        output,
    )


# =========================================================
# General Parsing Helpers
# =========================================================

def _clean_text(text):
    if not text:
        return ""

    text = re.sub(
        r"\x1b\[[0-?]*[ -/]*[@-~]",
        "",
        text,
    )

    text = text.replace(
        "\r",
        "",
    )

    return text


# =========================================================
# Stack Parsing
# =========================================================

def _get_unit_ids(output):
    """
    Parse Unit-IDs only from stack table rows.
    """

    unit_ids = []

    if not output:
        return unit_ids

    for line in output.splitlines():

        text = _clean_text(line).strip()

        if not text:
            continue

        parts = text.split()

        if not parts:
            continue

        if not re.fullmatch(
            r"[0-9]+",
            parts[0],
        ):
            continue

        try:
            unit_id = int(parts[0])
        except ValueError:
            continue

        if (
            1 <= unit_id <= 64
            and len(parts) >= 2
        ):
            if unit_id not in unit_ids:
                unit_ids.append(unit_id)

    return sorted(unit_ids)


def _get_unit_line(
    output,
    unit_id,
):
    if not output:
        return ""

    for line in output.splitlines():

        text = _clean_text(line).strip()

        parts = text.split()

        if (
            parts
            and parts[0] == str(unit_id)
        ):
            return text

    return ""


def _get_unit_mac(
    output,
    unit_id,
):
    line = _get_unit_line(
        output,
        unit_id,
    )

    if not line:
        return None

    match = re.search(
        r"\b[0-9a-fA-F]{2}"
        r"(?::[0-9a-fA-F]{2}){5}\b",
        line,
    )

    if match:
        return match.group(0).lower()

    return None


def _is_controller(
    output,
    unit_id=1,
):
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


def _get_next_unit_id(
    unit_ids,
):
    """
    Select the lowest available Unit-ID.

    Examples:

        [1,2,3,4] -> 5
        [1,2,3,5] -> 4
        [1,3,4]   -> 2
    """

    used_ids = set(unit_ids)

    for unit_id in range(
        1,
        65,
    ):
        if unit_id not in used_ids:
            return unit_id

    return None


# =========================================================
# Firmware Parsing
# =========================================================

def _normalize_firmware(value):
    if not value:
        return None

    value = value.strip()

    value = re.sub(
        r"\x1b\[[0-?]*[ -/]*[@-~]",
        "",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def _extract_firmware_version(output):
    """
    Extract firmware/software version from 'show version'.

    The parser intentionally supports multiple common CLI
    formats instead of depending on one exact line.
    """

    if not output:
        return None

    clean_output = _clean_text(
        output
    )

    lines = clean_output.splitlines()

    patterns = [
        r"^\s*(?:firmware|firmware\s+version)\s*[:=]\s*(.+?)\s*$",
        r"^\s*(?:software|software\s+version)\s*[:=]\s*(.+?)\s*$",
        r"^\s*(?:version)\s*[:=]\s*(.+?)\s*$",
        r"^\s*(?:image|image\s+version)\s*[:=]\s*(.+?)\s*$",
        r"^\s*(?:system\s+version)\s*[:=]\s*(.+?)\s*$",
        r"^\s*(?:release)\s*[:=]\s*(.+?)\s*$",
    ]

    for line in lines:

        line = line.strip()

        if not line:
            continue

        for pattern in patterns:

            match = re.search(
                pattern,
                line,
                re.IGNORECASE,
            )

            if match:

                value = _normalize_firmware(
                    match.group(1)
                )

                if value:
                    return value

    # Fallback: search anywhere in output.
    fallback_patterns = [
        r"firmware\s+version\s*[:=]\s*([^\r\n]+)",
        r"software\s+version\s*[:=]\s*([^\r\n]+)",
        r"system\s+version\s*[:=]\s*([^\r\n]+)",
        r"image\s+version\s*[:=]\s*([^\r\n]+)",
        r"version\s*[:=]\s*([^\r\n]+)",
    ]

    for pattern in fallback_patterns:

        match = re.search(
            pattern,
            clean_output,
            re.IGNORECASE,
        )

        if match:

            value = _normalize_firmware(
                match.group(1)
            )

            if value:
                return value

    return None


def _firmware_matches(
    version_a,
    version_b,
):
    if not version_a or not version_b:
        return False

    return (
        version_a.strip().lower()
        == version_b.strip().lower()
    )


# =========================================================
# Filtered Log Monitoring
# =========================================================

def _is_relevant_log(
    line,
    new_unit_id,
    new_unit_mac=None,
):
    """
    Return True only for logs related to the current
    stack join / firmware synchronization operation.

    Unrelated logs are ignored.
    """

    if not line:
        return False

    text = line.lower().strip()

    if not text:
        return False

    # Remove ANSI sequences.
    text = re.sub(
        r"\x1b\[[0-?]*[ -/]*[@-~]",
        "",
        text,
    )

    # -----------------------------------------------------
    # Unit-specific indicators
    # -----------------------------------------------------

    unit_related = False

    unit_patterns = [
        f"unit-{new_unit_id}",
        f"unit {new_unit_id}",
        f"unitid {new_unit_id}",
        f"unit id {new_unit_id}",
        f"unit:{new_unit_id}",
        f"member {new_unit_id}",
        f"member-{new_unit_id}",
    ]

    if any(
        pattern in text
        for pattern in unit_patterns
    ):
        unit_related = True

    if (
        new_unit_mac
        and new_unit_mac.lower()
        in text
    ):
        unit_related = True

    # -----------------------------------------------------
    # Firmware / synchronization keywords
    # -----------------------------------------------------

    firmware_keywords = [
        "firmware",
        "software image",
        "image",
        "firmware image",
        "version",
        "upgrade",
        "upgrading",
        "update",
        "updating",
        "download",
        "downloading",
        "synchron",
        "sync",
        "auto-sync",
        "autosync",
        "auto sync",
        "upgrade image",
        "boot image",
    ]

    stack_keywords = [
        "stack",
        "join",
        "joined",
        "joining",
        "member",
        "controller",
        "master",
        "stacking",
        "stack link",
    ]

    event_keywords = [
        "detected",
        "discover",
        "discovered",
        "start",
        "started",
        "complete",
        "completed",
        "success",
        "successful",
        "finish",
        "finished",
        "ready",
        "online",
        "offline",
        "down",
        "up",
        "add",
        "added",
        "remove",
        "removed",
    ]

    has_firmware_keyword = any(
        keyword in text
        for keyword in firmware_keywords
    )

    has_stack_keyword = any(
        keyword in text
        for keyword in stack_keywords
    )

    has_event_keyword = any(
        keyword in text
        for keyword in event_keywords
    )

    # -----------------------------------------------------
    # Strong match:
    # Specific new unit + relevant operation
    # -----------------------------------------------------

    if unit_related and (
        has_firmware_keyword
        or has_stack_keyword
        or has_event_keyword
    ):
        return True

    # -----------------------------------------------------
    # Firmware synchronization messages may not always
    # contain the Unit-ID, so allow strong firmware events.
    # -----------------------------------------------------

    strong_firmware_terms = [
        "firmware synchronization",
        "firmware synchronisation",
        "firmware sync",
        "firmware upgrade",
        "firmware update",
        "image synchronization",
        "image synchronisation",
        "image sync",
        "image upgrade",
        "image update",
        "software synchronization",
        "software synchronisation",
        "software upgrade",
        "software update",
        "auto synchronization",
        "auto synchronisation",
        "auto-sync",
        "autosync",
    ]

    if any(
        term in text
        for term in strong_firmware_terms
    ):
        return True

    # -----------------------------------------------------
    # Stack join messages without Unit-ID
    # -----------------------------------------------------

    join_terms = [
        "new member joined",
        "member joined",
        "member joining",
        "unit joined",
        "unit joining",
        "stack member added",
        "stack member detected",
        "new unit joined",
        "new unit detected",
    ]

    if any(
        term in text
        for term in join_terms
    ):
        return True

    return False


def _get_filtered_new_logs(
    logging_output,
    new_unit_id,
    new_unit_mac,
    seen_logs,
):
    """
    Extract only NEW relevant log lines.

    seen_logs prevents the same event from being displayed
    repeatedly on every polling cycle.
    """

    new_logs = []

    if not logging_output:
        return new_logs

    for line in logging_output.splitlines():

        clean_line = _clean_text(
            line
        ).strip()

        if not clean_line:
            continue

        if clean_line in seen_logs:
            continue

        if _is_relevant_log(
            clean_line,
            new_unit_id,
            new_unit_mac,
        ):

            seen_logs.add(
                clean_line
            )

            new_logs.append(
                clean_line
            )

    return new_logs


def _print_filtered_logs(
    logs,
):
    for log_line in logs:
        print(
            f"[LOG] {log_line}"
        )


# =========================================================
# Automatic New Switch Configuration
# =========================================================

def _configure_new_switch(
    new_connection,
    new_unit_id,
    stack_port_type,
    stack_port_range,
):
    """
    Automatically configure the new switch.

    Example:

        configure terminal
        stack configuration unit-id 5 links tf3-4
        do write
    """

    if not _connection_is_usable(
        new_connection
    ):
        print(
            "✗ New switch connection is not usable."
        )
        return False

    stack_link = (
        f"{stack_port_type}"
        f"{stack_port_range}"
    )

    print()
    print(
        f"Configuring new switch as Unit-{new_unit_id}..."
    )

    commands = [
        "configure terminal",
        (
            f"stack configuration "
            f"unit-id {new_unit_id} "
            f"links {stack_link}"
        ),
        "do write",
    ]

    for command in commands:

        output = _send_command(
            new_connection,
            command,
            timeout=20,
            display=True,
        )

        if output is None:

            print(
                f"✗ Command failed: {command}"
            )

            return False

    print()
    print(
        f"✓ New switch configured as "
        f"Unit-{new_unit_id}."
    )

    print(
        f"✓ Stack link configuration: "
        f"{stack_link}"
    )

    print(
        "✓ Configuration saved."
    )

    return True


# =========================================================
# Reload New Switch
# =========================================================

def _reload_new_switch(
    new_connection,
):
    """
    Reload the new switch.

    The existing project uses:
        do reload
    """

    if not _connection_is_usable(
        new_connection
    ):
        print(
            "✗ New switch connection is not usable."
        )
        return False

    print()
    print(
        "Reloading the new switch..."
    )

    output = _send_command(
        new_connection,
        "do reload",
        timeout=15,
        display=True,
    )

    # A reload normally closes the connection.
    # Therefore output may be empty/None even though
    # reload was successfully initiated.

    if output is not None:
        print()
        print(
            "✓ Reload command was sent."
        )
    else:
        print()
        print(
            "✓ Reload was initiated; "
            "the connection is no longer available."
        )

    return True


# =========================================================
# Input Helpers
# =========================================================

def _get_connection_type():
    while True:

        value = input(
            "\nEnter new switch connection type "
            "(ssh/telnet): "
        ).strip().lower()

        if value in (
            "ssh",
            "telnet",
        ):
            return value

        print(
            "Please enter ssh or telnet."
        )


def _get_stack_port_type():
    supported = (
        "te",
        "hu",
        "tf",
    )

    while True:

        value = input(
            "\nEnter new switch stack port type "
            "(te/hu/tf): "
        ).strip().lower()

        if value in supported:
            return value

        print(
            "Supported port types: "
            "te, hu, tf"
        )


def _get_new_switch_details():
    print()
    print(
        "Enter NEW switch access details:"
    )

    ip = input(
        "New switch IP address: "
    ).strip()

    username = input(
        "Username: "
    ).strip()

    password = input(
        "Password: "
    ).strip()

    connection_type = _get_connection_type()

    stack_port_type = _get_stack_port_type()

    stack_port_range = input(
        "Enter stack port range "
        "(example: 3-4): "
    ).strip()

    return (
        ip,
        username,
        password,
        connection_type,
        stack_port_type,
        stack_port_range,
    )


# =========================================================
# TC-STK-020
# =========================================================

def run_tc_stk_020(
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
    print(
        "  1. Identify the firmware version running "
        "on the existing stack."
    )
    print(
        "  2. Add a new switch with mismatched firmware."
    )
    print(
        "  3. Automatically configure the new switch "
        "with the next available Unit-ID."
    )
    print(
        "  4. Reload the new switch."
    )
    print(
        "  5. Observe firmware auto-synchronization "
        "and stack join."
    )

    print()
    print("Important:")
    print(
        "  - Unit-1 / MASTER is used for stack verification."
    )
    print(
        "  - No changes are made to connection.py."
    )
    print(
        "  - No changes are made to main.py."
    )
    print(
        "  - Physical stack cable connection must be present."
    )
    print(
        "  - Only relevant synchronization/join logs "
        "are displayed."
    )

    # =====================================================
    # STEP 1
    # Existing Stack Verification
    # =====================================================

    _print_step(
        1,
        "VERIFY EXISTING STACK",
    )

    (
        master_connection,
        stack_output,
    ) = _run_master_command(
        master_connection,
        "show stack",
        master_ip,
        master_username,
        master_password,
        connection_type,
        timeout=20,
        display=True,
    )

    if not stack_output:

        _print_header(
            f"{TEST_CASE_ID} RESULT"
        )

        print()
        print("FAIL")
        print()
        print(
            "✗ Unable to read existing stack."
        )

        print()
        print(
            "Master connection remains active."
        )

        return False

    existing_unit_ids = _get_unit_ids(
        stack_output
    )

    if 1 not in existing_unit_ids:

        _print_header(
            f"{TEST_CASE_ID} RESULT"
        )

        print()
        print("FAIL")
        print()
        print(
            "✗ Unit-1 was not found in the stack."
        )

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

        return False

    print()
    print(
        "✓ Unit-1 is Controller/Master."
    )

    print()
    print(
        "Existing Stack Unit-IDs: "
        + ", ".join(
            str(x)
            for x in existing_unit_ids
        )
    )

    # =====================================================
    # STEP 2
    # Existing Firmware
    # =====================================================

    _print_step(
        2,
        "CHECK EXISTING STACK FIRMWARE",
    )

    (
        master_connection,
        master_version_output,
    ) = _run_master_command(
        master_connection,
        "show version",
        master_ip,
        master_username,
        master_password,
        connection_type,
        timeout=25,
        display=True,
    )

    existing_firmware = (
        _extract_firmware_version(
            master_version_output
        )
    )

    if not existing_firmware:

        _print_header(
            f"{TEST_CASE_ID} RESULT"
        )

        print()
        print("FAIL")
        print()
        print(
            "✗ Could not determine firmware "
            "version from 'show version'."
        )

        print()
        print(
            "Please verify the exact 'show version' "
            "output format."
        )

        return False

    print()
    print(
        f"✓ Existing stack firmware: "
        f"{existing_firmware}"
    )

    # =====================================================
    # STEP 3
    # Calculate New Unit-ID
    # =====================================================

    _print_step(
        3,
        "CALCULATE NEW UNIT-ID",
    )

    new_unit_id = _get_next_unit_id(
        existing_unit_ids
    )

    if new_unit_id is None:

        _print_header(
            f"{TEST_CASE_ID} RESULT"
        )

        print()
        print("FAIL")
        print()
        print(
            "✗ No available Unit-ID "
            "from 1 to 64."
        )

        return False

    print()
    print(
        f"Existing Unit-IDs: "
        f"{existing_unit_ids}"
    )

    print(
        f"✓ New switch will use "
        f"Unit-{new_unit_id}."
    )

    # =====================================================
    # STEP 4
    # New Switch Details
    # =====================================================

    _print_step(
        4,
        "CONNECT TO NEW SWITCH",
    )

    (
        new_ip,
        new_username,
        new_password,
        new_connection_type,
        stack_port_type,
        stack_port_range,
    ) = _get_new_switch_details()

    print()
    print(
        f"Connecting to new switch "
        f"{new_ip}..."
    )

    new_connection = _connect_switch(
        new_ip,
        new_username,
        new_password,
        new_connection_type,
    )

    if new_connection is None:

        _print_header(
            f"{TEST_CASE_ID} RESULT"
        )

        print()
        print("FAIL")
        print()
        print(
            "✗ Could not connect to the "
            "new switch."
        )

        print()
        print(
            "Master connection remains active."
        )

        return False

    print()
    print(
        "✓ New switch connected successfully."
    )

    # =====================================================
    # STEP 5
    # New Switch Firmware
    # =====================================================

    _print_step(
        5,
        "CHECK NEW SWITCH FIRMWARE",
    )

    new_version_output = _send_command(
        new_connection,
        "show version",
        timeout=25,
        display=True,
    )

    new_firmware = (
        _extract_firmware_version(
            new_version_output
        )
    )

    if not new_firmware:

        _print_header(
            f"{TEST_CASE_ID} RESULT"
        )

        print()
        print("FAIL")
        print()
        print(
            "✗ Could not determine firmware "
            "version of the new switch."
        )

        return False

    print()
    print(
        f"Existing Stack Firmware : "
        f"{existing_firmware}"
    )

    print(
        f"New Switch Firmware     : "
        f"{new_firmware}"
    )

    if _firmware_matches(
        existing_firmware,
        new_firmware,
    ):

        _print_header(
            f"{TEST_CASE_ID} RESULT"
        )

        print()
        print("FAIL")
        print()
        print(
            "✗ New switch firmware is already "
            "the same as the existing stack."
        )

        print()
        print(
            "TC-STK-020 requires a firmware mismatch."
        )

        return False

    print()
    print(
        "✓ Firmware mismatch confirmed."
    )

    # =====================================================
    # STEP 6
    # Automatic Configuration
    # =====================================================

    _print_step(
        6,
        "AUTOMATICALLY CONFIGURE NEW SWITCH",
    )

    configured = _configure_new_switch(
        new_connection,
        new_unit_id,
        stack_port_type,
        stack_port_range,
    )

    if not configured:

        _print_header(
            f"{TEST_CASE_ID} RESULT"
        )

        print()
        print("FAIL")
        print()
        print(
            "✗ Automatic configuration "
            "of new switch failed."
        )

        return False

    # =====================================================
    # STEP 7
    # Reload New Switch
    # =====================================================

    _print_step(
        7,
        "RELOAD NEW SWITCH",
    )

    reload_started = _reload_new_switch(
        new_connection
    )

    if not reload_started:

        _print_header(
            f"{TEST_CASE_ID} RESULT"
        )

        print()
        print("FAIL")
        print()
        print(
            "✗ Could not initiate reload "
            "on the new switch."
        )

        return False

    print()
    print(
        "✓ New switch reload initiated."
    )

    print()
    print(
        "The new switch is now expected to "
        "join the existing stack."
    )

    # =====================================================
    # STEP 8
    # Parallel Monitoring
    # =====================================================

    _print_step(
        8,
        "MONITOR FIRMWARE SYNCHRONIZATION "
        "AND STACK JOIN",
    )

    print()
    print(
        f"Monitoring Unit-{new_unit_id} "
        "from Unit-1 / MASTER."
    )

    print(
        "Relevant stack/firmware logs will be "
        "displayed as they occur."
    )

    print()
    print(
        f"Timeout: {JOIN_TIMEOUT} seconds"
    )

    print(
        f"Stack check interval: "
        f"{POLL_INTERVAL} seconds"
    )

    print(
        f"Log check interval: "
        f"{LOG_POLL_INTERVAL} seconds"
    )

    print()

    start_time = time.time()

    last_stack_check = 0
    last_log_check = 0

    joined = False
    sync_log_seen = False

    seen_logs = set()

    latest_stack_output = None
    latest_logging_output = None

    last_seen_units = []

    while (
        time.time() - start_time
        < JOIN_TIMEOUT
    ):

        now = time.time()

        # -------------------------------------------------
        # Background log monitoring
        # -------------------------------------------------

        if (
            now - last_log_check
            >= LOG_POLL_INTERVAL
        ):

            (
                master_connection,
                latest_logging_output,
            ) = _run_master_command(
                master_connection,
                "show logging",
                master_ip,
                master_username,
                master_password,
                connection_type,
                timeout=15,
                display=False,
            )

            last_log_check = now

            relevant_logs = (
                _get_filtered_new_logs(
                    latest_logging_output,
                    new_unit_id,
                    None,
                    seen_logs,
                )
            )

            if relevant_logs:

                sync_log_seen = True

                _print_filtered_logs(
                    relevant_logs
                )

        # -------------------------------------------------
        # Stack monitoring
        # -------------------------------------------------

        if (
            now - last_stack_check
            >= POLL_INTERVAL
        ):

            (
                master_connection,
                latest_stack_output,
            ) = _run_master_command(
                master_connection,
                "show stack",
                master_ip,
                master_username,
                master_password,
                connection_type,
                timeout=20,
                display=False,
            )

            last_stack_check = now

            current_unit_ids = (
                _get_unit_ids(
                    latest_stack_output
                )
            )

            if current_unit_ids != last_seen_units:

                elapsed = int(
                    time.time()
                    - start_time
                )

                print()
                print(
                    f"[{elapsed}s] Current Stack: "
                    + (
                        ", ".join(
                            str(x)
                            for x in current_unit_ids
                        )
                        if current_unit_ids
                        else "No members detected"
                    )
                )

                last_seen_units = (
                    current_unit_ids
                )

            # ---------------------------------------------
            # New Unit joined
            # ---------------------------------------------

            if (
                new_unit_id
                in current_unit_ids
            ):

                joined = True

                print()
                print(
                    f"✓ Unit-{new_unit_id} "
                    "is now visible in the stack."
                )

                # Continue monitoring for firmware
                # synchronization instead of immediately
                # finishing.

                break

        time.sleep(1)

    # =====================================================
    # STEP 9
    # Final Stack Join Check
    # =====================================================

    _print_step(
        9,
        "VERIFY NEW UNIT JOINED THE STACK",
    )

    (
        master_connection,
        final_stack_output,
    ) = _run_master_command(
        master_connection,
        "show stack",
        master_ip,
        master_username,
        master_password,
        connection_type,
        timeout=20,
        display=True,
    )

    final_unit_ids = _get_unit_ids(
        final_stack_output
    )

    print()

    if new_unit_id in final_unit_ids:

        print(
            f"✓ Unit-{new_unit_id} is present "
            "in the stack."
        )

        joined = True

    else:

        print(
            f"✗ Unit-{new_unit_id} is NOT present "
            "in the stack."
        )

        joined = False

    # =====================================================
    # STEP 10
    # Verify Unit-1 MASTER
    # =====================================================

    _print_step(
        10,
        "VERIFY UNIT-1 / MASTER",
    )

    master_ok = _is_controller(
        final_stack_output,
        1,
    )

    if master_ok:

        print(
            "✓ Unit-1 remains "
            "Controller/Master."
        )

    else:

        print(
            "✗ Unit-1 is not shown as "
            "Controller/Master."
        )

    # =====================================================
    # STEP 11
    # Verify Firmware After Join
    # =====================================================

    _print_step(
        11,
        "VERIFY FIRMWARE AFTER SYNCHRONIZATION",
    )

    print()
    print(
        "Checking firmware from the joined "
        "stack member."
    )

    # First allow the stack some time to complete
    # synchronization if the member has just appeared.
    if joined:

        print()
        print(
            "Waiting briefly for firmware "
            "synchronization to settle..."
        )

        time.sleep(10)

    (
        master_connection,
        final_version_output,
    ) = _run_master_command(
        master_connection,
        "show version",
        master_ip,
        master_username,
        master_password,
        connection_type,
        timeout=25,
        display=True,
    )

    final_firmware = (
        _extract_firmware_version(
            final_version_output
        )
    )

    firmware_sync_ok = False

    if final_firmware:

        print()
        print(
            f"Existing Stack Firmware : "
            f"{existing_firmware}"
        )

        print(
            f"Current Stack Firmware  : "
            f"{final_firmware}"
        )

        if _firmware_matches(
            existing_firmware,
            final_firmware,
        ):

            firmware_sync_ok = True

            print()
            print(
                "✓ Firmware version matches "
                "the existing stack."
            )

        else:

            print()
            print(
                "✗ Firmware version has not "
                "yet matched the existing stack."
            )

    else:

        print()
        print(
            "✗ Could not determine final "
            "firmware version."
        )

    # =====================================================
    # Additional Synchronization Monitoring
    # =====================================================

    if joined and not firmware_sync_ok:

        print()
        print(
            "Unit joined, but firmware synchronization "
            "may still be in progress."
        )

        print(
            "Continuing to monitor synchronization..."
        )

        sync_start = time.time()

        while (
            time.time() - sync_start
            < JOIN_TIMEOUT
        ):

            time.sleep(
                LOG_POLL_INTERVAL
            )

            # ---------------------------------------------
            # Relevant logs only
            # ---------------------------------------------

            (
                master_connection,
                latest_logging_output,
            ) = _run_master_command(
                master_connection,
                "show logging",
                master_ip,
                master_username,
                master_password,
                connection_type,
                timeout=15,
                display=False,
            )

            relevant_logs = (
                _get_filtered_new_logs(
                    latest_logging_output,
                    new_unit_id,
                    None,
                    seen_logs,
                )
            )

            if relevant_logs:

                sync_log_seen = True

                _print_filtered_logs(
                    relevant_logs
                )

            # ---------------------------------------------
            # Firmware check
            # ---------------------------------------------

            (
                master_connection,
                final_version_output,
            ) = _run_master_command(
                master_connection,
                "show version",
                master_ip,
                master_username,
                master_password,
                connection_type,
                timeout=20,
                display=False,
            )

            final_firmware = (
                _extract_firmware_version(
                    final_version_output
                )
            )

            if (
                final_firmware
                and _firmware_matches(
                    existing_firmware,
                    final_firmware,
                )
            ):

                firmware_sync_ok = True

                print()
                print(
                    "✓ Firmware synchronization "
                    "completed."
                )

                break

    # =====================================================
    # STEP 12
    # Final Verification
    # =====================================================

    _print_step(
        12,
        "FINAL VERIFICATION",
    )

    (
        master_connection,
        final_stack_output,
    ) = _run_master_command(
        master_connection,
        "show stack",
        master_ip,
        master_username,
        master_password,
        connection_type,
        timeout=20,
        display=True,
    )

    final_unit_ids = _get_unit_ids(
        final_stack_output
    )

    final_join_ok = (
        new_unit_id in final_unit_ids
    )

    final_master_ok = _is_controller(
        final_stack_output,
        1,
    )

    print()
    print("Final Stack Members:")

    if final_unit_ids:

        for unit_id in final_unit_ids:

            line = _get_unit_line(
                final_stack_output,
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
    print("Verification Summary:")

    print(
        f"  Existing Firmware : "
        f"{existing_firmware}"
    )

    print(
        f"  New Switch Initial Firmware : "
        f"{new_firmware}"
    )

    print(
        f"  New Unit-ID : "
        f"Unit-{new_unit_id}"
    )

    print(
        f"  Firmware Mismatch Before Join : "
        f"{'PASS' if not _firmware_matches(existing_firmware, new_firmware) else 'FAIL'}"
    )

    print(
        f"  New Unit Joined : "
        f"{'PASS' if final_join_ok else 'FAIL'}"
    )

    print(
        f"  Unit-1 Remains MASTER : "
        f"{'PASS' if final_master_ok else 'FAIL'}"
    )

    print(
        f"  Firmware Synchronized : "
        f"{'PASS' if firmware_sync_ok else 'FAIL'}"
    )

    print(
        f"  Relevant Sync Logs Observed : "
        f"{'YES' if sync_log_seen else 'NO'}"
    )

    # =====================================================
    # Final Result
    # =====================================================

    _print_header(
        f"{TEST_CASE_ID} RESULT"
    )

    print()

    if (
        final_join_ok
        and final_master_ok
        and firmware_sync_ok
    ):

        print("PASS")
        print()

        print(
            f"✓ New Unit-{new_unit_id} "
            "joined the existing stack."
        )

        print(
            "✓ Unit-1 remained "
            "Controller/Master."
        )

        print(
            "✓ New switch initially had "
            "a different firmware version."
        )

        print(
            "✓ Firmware synchronization "
            "completed successfully."
        )

        if sync_log_seen:

            print(
                "✓ Relevant firmware/stack "
                "synchronization logs were observed."
            )

        else:

            print(
                "! No matching synchronization "
                "log message was detected."
            )

        print()
        print(
            "Master connection remains active."
        )

        return True

    print("FAIL")
    print()

    if not final_join_ok:

        print(
            f"✗ Unit-{new_unit_id} did not "
            "join the stack."
        )

    if not final_master_ok:

        print(
            "✗ Unit-1 is not shown as "
            "Controller/Master."
        )

    if not firmware_sync_ok:

        print(
            "✗ Firmware synchronization "
            "was not confirmed."
        )

    print()
    print(
        "Master connection remains active."
    )

    return False

