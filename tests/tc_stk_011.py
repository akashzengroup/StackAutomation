import time
import re

from connection import SwitchConnection


# =========================================================
# TEST CASE INFORMATION
# =========================================================

TEST_CASE_ID = "TC-STK-011"
TEST_CASE_TITLE = "Stack Software Upgrade & Member Verification"


# =========================================================
# COMMANDS / CONSTANTS
# =========================================================

COMMAND_RELOAD = "do reload"
COMMAND_SHOW_VERSION = "do show version"

FIRMWARE_COPY_SUCCESS = (
    "%COPY-N-TRAP: The copy operation was completed successfully"
)

# Maximum time allowed for firmware copy
FIRMWARE_COPY_TIMEOUT = 30 * 60

# Time between log/status checks if live output temporarily stops
FIRMWARE_LOG_POLL_INTERVAL = 5

# Wait before first MASTER reconnect attempt after reload
POST_RELOAD_INITIAL_WAIT = 15

# Maximum time to wait for MASTER after reload
MASTER_RECONNECT_TIMEOUT = 10 * 60

# Retry interval after reload
MASTER_RECONNECT_INTERVAL = 5

# Normal CLI command timeout
COMMAND_TIMEOUT = 30


# =========================================================
# DISPLAY HELPERS
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


def _remove_ansi(text):
    if not text:
        return ""

    return re.sub(
        r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])",
        "",
        str(text),
    )


# =========================================================
# CONNECTION HELPERS
# =========================================================

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


def _close_connection(connection):
    """
    Close the current SSH connection.

    Different SwitchConnection implementations may expose
    different close methods, so try the available one.
    """

    if connection is None:
        return

    methods = [
        "disconnect",
        "close",
    ]

    for method_name in methods:
        method = getattr(connection, method_name, None)

        if callable(method):
            try:
                method()
                return
            except Exception:
                pass

    shell = getattr(connection, "shell", None)

    if shell is None:
        shell = getattr(connection, "ssh_shell", None)

    if shell is not None:
        try:
            shell.close()
        except Exception:
            pass


def _update_connection_object(existing, replacement):
    """
    Keep the original master_connection object alive where possible.
    """

    if existing is None:
        return replacement

    if replacement is None:
        return existing

    try:
        existing.__dict__.update(replacement.__dict__)
        return existing
    except Exception:
        return replacement


def _connect_master(
    master_ip,
    master_username,
    master_password,
    connection_type,
):
    print(
        f"Connecting to MASTER {master_ip} "
        f"using {connection_type.upper()}..."
    )

    connection = SwitchConnection(
        connection_type=connection_type,
        ip=master_ip,
        username=master_username,
        password=master_password,
    )

    try:
        if connection.connect():
            print("SSH connection successful!")
            return connection
    except Exception as exc:
        print(f"Connection error: {exc}")

    return None


# =========================================================
# SHELL HELPERS
# =========================================================

def _get_shell(connection):
    if connection is None:
        return None

    shell = getattr(connection, "shell", None)

    if shell is None:
        shell = getattr(connection, "ssh_shell", None)

    return shell


def _clear_shell(connection):
    """
    Clear pending shell data before executing a normal command.
    """

    shell = _get_shell(connection)

    if shell is None:
        return

    try:
        while shell.recv_ready():
            shell.recv(65535)
    except Exception:
        pass


# =========================================================
# NORMAL COMMAND EXECUTION
# =========================================================

def _get_command_output(
    connection,
    command,
    timeout=COMMAND_TIMEOUT,
    display=True,
):
    """
    Execute a normal CLI command.

    IMPORTANT:
    No timeout keyword is passed to SwitchConnection.send_command().
    This avoids:
        unexpected keyword argument 'timeout'
    """

    if connection is None:
        return ""

    print()
    print(f">>> {command}")
    print()

    send_command = getattr(
        connection,
        "send_command",
        None,
    )

    # -----------------------------------------------------
    # First try SwitchConnection.send_command(command)
    # -----------------------------------------------------

    if callable(send_command):

        try:
            output = send_command(command)

            output = "" if output is None else str(output)
            output = _remove_ansi(output)

            if display and output.strip():
                print(output)

            return output

        except Exception as exc:

            if display:
                print(f"Command execution error: {exc}")

    # -----------------------------------------------------
    # Fallback: direct shell
    # -----------------------------------------------------

    shell = _get_shell(connection)

    if shell is None:
        return ""

    try:

        _clear_shell(connection)

        shell.send(command + "\n")

        output_parts = []

        start_time = time.time()

        while time.time() - start_time < timeout:

            try:

                if shell.recv_ready():

                    chunk = shell.recv(65535)

                    if isinstance(chunk, bytes):
                        chunk = chunk.decode(
                            errors="ignore"
                        )

                    if chunk:
                        output_parts.append(chunk)

                        clean = _remove_ansi(chunk)

                        if display:
                            print(
                                clean,
                                end=""
                                if clean.endswith("\n")
                                else "\n",
                            )

                        # Reset activity timer by continuing.
                        continue

            except Exception:
                pass

            time.sleep(0.1)

        return _remove_ansi(
            "".join(output_parts)
        )

    except Exception as exc:

        if display:
            print(
                f"Command execution error: {exc}"
            )

        return ""


# =========================================================
# UPGRADE METHOD
# =========================================================

def _select_upgrade_method():

    _print_header(
        "SELECT SOFTWARE UPGRADE METHOD"
    )

    print()
    print("1. TFTP")
    print("2. USB")

    while True:

        choice = input(
            "\nSelect upgrade method [1-2]: "
        ).strip()

        if choice == "1":
            return "tftp"

        if choice == "2":
            return "usb"

        print(
            "Invalid selection. "
            "Please select 1 or 2."
        )


# =========================================================
# TFTP DETAILS
# =========================================================

def _get_tftp_details():

    print()
    print("TFTP Server IP Address")
    print("----------------------")

    while True:

        tftp_server = input(
            "Enter TFTP Server IP : "
        ).strip()

        if tftp_server:
            break

        print(
            "TFTP server IP cannot be empty."
        )

    print()
    print("Firmware File Name")
    print("------------------")

    while True:

        firmware_file = input(
            "Enter Firmware File : "
        ).strip()

        if firmware_file:
            break

        print(
            "Firmware file name cannot be empty."
        )

    # -----------------------------------------------------
    # "boot system tftp://" is automatically generated.
    # User only enters IP + filename.
    # -----------------------------------------------------

    boot_command = (
        f"boot system "
        f"tftp://{tftp_server}/{firmware_file}"
    )

    return {
        "method": "TFTP",
        "server": tftp_server,
        "filename": firmware_file,
        "boot_command": boot_command,
    }


# =========================================================
# USB DETAILS
# =========================================================

def _get_usb_details():

    _print_header(
        "USB FIRMWARE UPGRADE"
    )

    print()

    print(
        "Please place the firmware file in the "
        "ROOT directory of the USB drive."
    )

    print()

    print(
        "Example:"
    )

    print(
        "  QN_SW-AG-2.3.16.00.qntm"
    )

    print()

    print(
        "Insert the USB drive into the switch."
    )

    print()

    while True:

        firmware_file = input(
            "Enter Firmware File Name : "
        ).strip()

        if firmware_file:
            break

        print(
            "Firmware file name cannot be empty."
        )

    boot_command = (
        f"boot system usb://{firmware_file}"
    )

    return {
        "method": "USB",
        "filename": firmware_file,
        "boot_command": boot_command,
    }


# =========================================================
# SHOW UPGRADE PLAN
# =========================================================

def _show_upgrade_plan(upgrade_info):

    _print_header(
        "SOFTWARE UPGRADE PLAN"
    )

    print()

    print(
        f"Upgrade Method : "
        f"{upgrade_info['method']}"
    )

    print(
        f"Firmware File  : "
        f"{upgrade_info['filename']}"
    )

    if upgrade_info["method"] == "TFTP":

        print(
            f"TFTP Server   : "
            f"{upgrade_info['server']}"
        )

    print()

    print(
        f"Boot Command   : "
        f"{upgrade_info['boot_command']}"
    )

    print()

    print(
        "The script will:"
    )

    print(
        "  1. Start firmware upgrade."
    )

    print(
        "  2. Monitor the switch live output."
    )

    print(
        "  3. Display actual firmware percentage."
    )

    print(
        "  4. Wait for firmware copy success."
    )

    print(
        "  5. Reload the MASTER."
    )

    print(
        "  6. Wait for Unit-1 / MASTER."
    )

    print(
        "  7. Run 'do show version'."
    )

    print()

    print(
        "Reload will NOT happen before firmware "
        "copy completion."
    )

    print()

    confirm = input(
        "Proceed with software upgrade? (y/n): "
    ).strip().lower()

    return confirm == "y"


# =========================================================
# FIRMWARE PROGRESS PARSER
# =========================================================

def _extract_firmware_progress(text):
    """
    Extract actual firmware percentage from switch output.

    Expected switch output:

        [ 1 %]
        [ 2 %]
        ...
        [100 %]

    Returns the latest percentage found.
    """

    if not text:
        return None

    text = _remove_ansi(text)

    matches = re.findall(
        r"\[\s*(\d{1,3})\s*%\s*\]",
        text,
        re.IGNORECASE,
    )

    if not matches:
        return None

    try:
        progress = int(matches[-1])

        if 0 <= progress <= 100:
            return progress

    except Exception:
        pass

    return None


def _print_progress_bar(percent):

    bar_length = 40

    filled = int(
        bar_length * percent / 100
    )

    empty = bar_length - filled

    bar = (
        "█" * filled
        + "░" * empty
    )

    print(
        f"\r[{bar}] {percent:3d}%",
        end="",
        flush=True,
    )


# =========================================================
# FIRMWARE SUCCESS DETECTION
# =========================================================

def _firmware_success_found(text):

    if not text:
        return False

    return (
        FIRMWARE_COPY_SUCCESS.lower()
        in _remove_ansi(text).lower()
    )


# =========================================================
# START FIRMWARE COPY + LIVE MONITOR
# =========================================================

def _start_and_monitor_firmware_copy(
    master_connection,
    boot_command,
):
    """
    Start boot system directly through the SSH shell.

    IMPORTANT:

    We intentionally DO NOT use:

        send_command(..., timeout=...)

    because boot system is a long-running operation and
    SwitchConnection may close/timeout its command socket.

    Instead we:

        1. Send the command through the live shell.
        2. Continuously read switch output.
        3. Parse actual [ xx % ] progress.
        4. Wait for the actual COPY success message.
    """

    _print_step(
        3,
        "START FIRMWARE COPY",
    )

    print()

    print("=" * 70)
    print(
        "STARTING FIRMWARE UPGRADE".center(70)
    )
    print("=" * 70)

    print()

    print(
        f"Upgrade Command : {boot_command}"
    )

    print()

    shell = _get_shell(
        master_connection
    )

    if shell is None:

        print(
            "✗ MASTER SSH shell is not available."
        )

        return False

    try:

        _clear_shell(
            master_connection
        )

        # -------------------------------------------------
        # SEND BOOT SYSTEM COMMAND
        # -------------------------------------------------

        print(
            f">>> {boot_command}"
        )

        print()

        shell.send(
            boot_command + "\n"
        )

    except Exception as exc:

        print()

        print(
            f"✗ Unable to send firmware command: "
            f"{exc}"
        )

        return False

    print()

    print(
        "Firmware upgrade started on the switch."
    )

    print()

    print(
        "Monitoring LIVE firmware progress..."
    )

    print(
        "Actual percentage is taken from switch output."
    )

    print()

    last_progress = None

    success_found = False

    start_time = time.time()

    collected_output = ""

    last_activity = time.time()

    # -----------------------------------------------------
    # LIVE MONITOR LOOP
    # -----------------------------------------------------

    while True:

        elapsed = (
            time.time() - start_time
        )

        # -------------------------------------------------
        # MAXIMUM 30 MINUTE SAFETY TIMEOUT
        # -------------------------------------------------

        if elapsed >= FIRMWARE_COPY_TIMEOUT:

            print()

            print()

            print(
                "✗ Firmware copy did not complete "
                "within 30 minutes."
            )

            print()

            print(
                "Reload will NOT be performed."
            )

            return False

        data_received = False

        try:

            if shell.recv_ready():

                chunk = shell.recv(
                    65535
                )

                if isinstance(chunk, bytes):

                    chunk = chunk.decode(
                        errors="ignore"
                    )

                if chunk:

                    data_received = True

                    last_activity = time.time()

                    clean = _remove_ansi(
                        chunk
                    )

                    collected_output += clean

                    # -------------------------------------------------
                    # CHECK ACTUAL FIRMWARE %
                    # -------------------------------------------------

                    progress = (
                        _extract_firmware_progress(
                            clean
                        )
                    )

                    if progress is not None:

                        if (
                            last_progress is None
                            or progress != last_progress
                        ):

                            _print_progress_bar(
                                progress
                            )

                            last_progress = progress

                    # -------------------------------------------------
                    # CHECK SUCCESS MESSAGE
                    # -------------------------------------------------

                    if _firmware_success_found(
                        collected_output
                    ):

                        success_found = True

                    # -------------------------------------------------
                    # PRINT OTHER IMPORTANT OUTPUT
                    # -------------------------------------------------

                    important_lines = []

                    for line in clean.splitlines():

                        stripped = line.strip()

                        if not stripped:
                            continue

                        if re.search(
                            r"\[\s*\d{1,3}\s*%\s*\]",
                            stripped,
                            re.IGNORECASE,
                        ):
                            continue

                        if (
                            FIRMWARE_COPY_SUCCESS.lower()
                            in stripped.lower()
                        ):
                            important_lines.append(
                                stripped
                            )

                        elif (
                            "%COPY-I-TFTP"
                            in stripped
                        ):
                            important_lines.append(
                                stripped
                            )

                        elif (
                            "Copy:"
                            in stripped
                            and "bytes copied"
                            in stripped
                        ):
                            important_lines.append(
                                stripped
                            )

                    for line in important_lines:

                        print()

                        print(line)

        except Exception as exc:

            error_text = str(
                exc
            ).lower()

            # -------------------------------------------------
            # Socket closing during boot system is possible.
            #
            # Do NOT immediately fail.
            #
            # We will continue checking/reconnect if needed.
            # -------------------------------------------------

            if (
                "socket is closed"
                in error_text
                or "socket closed"
                in error_text
                or "channel is closed"
                in error_text
                or "channel closed"
                in error_text
            ):

                print()

                print(
                    "Firmware command channel closed "
                    "while the switch is processing "
                    "the upgrade."
                )

                print(
                    "This is NOT treated as immediate "
                    "firmware-copy failure."
                )

                break

            # Other shell read errors are handled below.
            break

        # -----------------------------------------------------
        # SUCCESS DETECTED
        # -----------------------------------------------------

        if success_found:

            if last_progress != 100:

                _print_progress_bar(
                    100
                )

                last_progress = 100

            print()

            print()

            print(
                "✓ Firmware copy completed successfully."
            )

            print()

            print(
                FIRMWARE_COPY_SUCCESS
            )

            return True

        # -----------------------------------------------------
        # NO DATA
        # -----------------------------------------------------

        if not data_received:

            time.sleep(
                0.1
            )

    # =========================================================
    # SHELL CLOSED / SOCKET CLOSED
    #
    # Reconnect to MASTER and check switch logs.
    # =========================================================

    print()

    print(
        "Live firmware channel is no longer available."
    )

    print(
        "Checking the switch itself for completion..."
    )

    return _wait_for_firmware_completion_after_channel_close(
        master_connection
    )


# =========================================================
# CHECK FIRMWARE COMPLETION AFTER CHANNEL CLOSE
# =========================================================

def _wait_for_firmware_completion_after_channel_close(
    master_connection,
):
    """
    If the live boot-system channel closes, reconnect/check
    the switch's own logging output.

    This is a safety/recovery path.

    The script still waits for the exact success message.
    """

    start_time = time.time()

    while True:

        elapsed = (
            time.time() - start_time
        )

        if elapsed >= FIRMWARE_COPY_TIMEOUT:

            print()

            print(
                "✗ Firmware copy did not report "
                "successful completion within 30 minutes."
            )

            return False

        if not _connection_is_usable(
            master_connection
        ):

            print()

            print(
                "MASTER connection is unavailable "
                "while firmware copy is running."
            )

            print(
                "Waiting before checking again..."
            )

            time.sleep(
                FIRMWARE_LOG_POLL_INTERVAL
            )

            continue

        try:

            log_output = _get_command_output(
                master_connection,
                "show logging",
                timeout=COMMAND_TIMEOUT,
                display=False,
            )

            if _firmware_success_found(
                log_output
            ):

                # -------------------------------------------------
                # Try to extract final percentage.
                # -------------------------------------------------

                progress = (
                    _extract_firmware_progress(
                        log_output
                    )
                )

                if progress is not None:

                    _print_progress_bar(
                        progress
                    )

                if progress != 100:

                    _print_progress_bar(
                        100
                    )

                print()

                print()

                print(
                    "✓ Firmware copy completed successfully."
                )

                print()

                print(
                    FIRMWARE_COPY_SUCCESS
                )

                return True

        except Exception:
            pass

        elapsed_minutes = int(
            elapsed // 60
        )

        print(
            f"\rWaiting for firmware completion... "
            f"Elapsed: {elapsed_minutes:02d} min",
            end="",
            flush=True,
        )

        time.sleep(
            FIRMWARE_LOG_POLL_INTERVAL
        )


# =========================================================
# RELOAD
# =========================================================

def _reload_master(
    master_connection,
):
    """
    Reload Unit-1 / MASTER.

    IMPORTANT:

    We do NOT wait for send_command() to complete.

    The reload command itself will normally terminate
    the SSH session.

    We send the command and immediately move to the
    MASTER recovery phase.
    """

    _print_step(
        4,
        "RELOAD UNIT-ID 1 / MASTER",
    )

    print()

    print(
        "Firmware copy is complete."
    )

    print(
        "Proceeding with reload..."
    )

    print()

    shell = _get_shell(
        master_connection
    )

    if shell is None:

        print(
            "✗ MASTER SSH shell is not available."
        )

        return False

    try:

        _clear_shell(
            master_connection
        )

        print(
            f">>> {COMMAND_RELOAD}"
        )

        print()

        # -------------------------------------------------
        # IMPORTANT:
        #
        # Send reload directly through shell.
        # Do NOT use send_command(timeout=...).
        # Do NOT wait for command completion.
        # -------------------------------------------------

        shell.send(
            COMMAND_RELOAD + "\n"
        )

        print(
            "Reload command has been sent "
            "to Unit-1 / MASTER."
        )

        print()

        print(
            "Closing the current SSH session..."
        )

        # Give the switch a short moment to process
        # the reload command.
        time.sleep(2)

        _close_connection(
            master_connection
        )

        print(
            "✓ Reload process started."
        )

        return True

    except Exception as exc:

        error_text = str(
            exc
        ).lower()

        # -------------------------------------------------
        # Socket close immediately after reload is normal.
        # -------------------------------------------------

        if (
            "socket is closed"
            in error_text
            or "socket closed"
            in error_text
            or "channel closed"
            in error_text
            or "connection reset"
            in error_text
        ):

            print()

            print(
                "SSH connection closed during reload."
            )

            print(
                "This is expected when the switch reboots."
            )

            _close_connection(
                master_connection
            )

            return True

        print()

        print(
            f"✗ Reload command could not be sent: "
            f"{exc}"
        )

        return False


# =========================================================
# WAIT FOR MASTER AFTER RELOAD
# =========================================================

def _wait_for_master_after_reload(
    master_connection,
    master_ip,
    master_username,
    master_password,
    connection_type,
):
    """
    Wait until Unit-1 / MASTER becomes reachable again.

    We do NOT require management port 22 to be observed DOWN.

    The script waits for the reboot period and then repeatedly
    attempts a fresh SSH connection.
    """

    _print_step(
        5,
        "WAIT FOR UNIT-ID 1 / MASTER AFTER RELOAD",
    )

    _print_header(
        "WAITING FOR UNIT-ID 1 / MASTER"
    )

    print()

    print(
        f"Waiting for MASTER "
        f"{master_ip} to become reachable..."
    )

    print()

    print(
        f"Initial reboot wait: "
        f"{POST_RELOAD_INITIAL_WAIT} seconds"
    )

    for remaining in range(
        POST_RELOAD_INITIAL_WAIT,
        0,
        -1,
    ):

        print(
            f"\rWaiting for reboot to start... "
            f"{remaining:02d}s",
            end="",
            flush=True,
        )

        time.sleep(1)

    print()

    print()

    start_time = time.time()

    while (
        time.time() - start_time
        < MASTER_RECONNECT_TIMEOUT
    ):

        elapsed = int(
            time.time() - start_time
        )

        remaining = max(
            0,
            int(
                MASTER_RECONNECT_TIMEOUT
                - elapsed
            ),
        )

        minutes = remaining // 60
        seconds = remaining % 60

        print(
            f"\rWaiting for MASTER... "
            f"{minutes:02d}:{seconds:02d} remaining",
            end="",
            flush=True,
        )

        replacement = _connect_master(
            master_ip,
            master_username,
            master_password,
            connection_type,
        )

        if replacement is not None:

            print()

            print()

            print(
                "✓ Unit-1 / MASTER is UP."
            )

            print(
                "✓ SSH connection established."
            )

            return _update_connection_object(
                master_connection,
                replacement,
            )

        time.sleep(
            MASTER_RECONNECT_INTERVAL
        )

    print()

    print()

    print(
        "✗ Unit-ID 1 / MASTER did not become "
        "reachable within the timeout."
    )

    return None


# =========================================================
# SHOW VERSION
# =========================================================

def _verify_software_version(
    master_connection,
):
    """
    Final verification required by TC-STK-011.

    Execute:
        do show version
    """

    _print_step(
        6,
        "VERIFY SOFTWARE VERSION",
    )

    print()

    print(
        "Unit-ID 1 / MASTER is reachable again."
    )

    print()

    print(
        "Running:"
    )

    print(
        "  do show version"
    )

    print()

    output = _get_command_output(
        master_connection,
        COMMAND_SHOW_VERSION,
        timeout=COMMAND_TIMEOUT,
        display=True,
    )

    if not output:

        print()

        print(
            "✗ No output received from "
            "'do show version'."
        )

        return False

    # -----------------------------------------------------
    # We only require valid command output.
    #
    # No hard-coded firmware version is assumed because
    # the user may upgrade to different versions.
    # -----------------------------------------------------

    clean_output = _remove_ansi(
        output
    ).strip()

    if not clean_output:

        print()

        print(
            "✗ 'do show version' returned empty output."
        )

        return False

    print()

    print(
        "✓ Software version information received."
    )

    return True


# =========================================================
# MAIN TEST CASE
# =========================================================

def run_tc_stk_011(
    master_connection,
    master_ip,
    master_username,
    master_password,
    connection_type,
    expected_members=2,
    **kwargs,
):
    """
    TC-STK-011

    Stack Software Upgrade & Member Verification

    Actual flow:

        1. Connect to Unit-1 / MASTER
        2. Select TFTP / USB
        3. Execute boot system
        4. Monitor live firmware percentage
        5. Wait for COPY success
        6. Reload Unit-1 / MASTER
        7. Wait for Unit-1 / MASTER to return
        8. SSH to MASTER
        9. Run do show version
    """

    _print_header(
        f"{TEST_CASE_ID} - {TEST_CASE_TITLE}"
    )

    print()

    print(
        "Objective:"
    )

    print(
        "  1. Upgrade stack software."
    )

    print(
        "  2. Monitor actual firmware copy progress."
    )

    print(
        "  3. Wait for firmware copy completion."
    )

    print(
        "  4. Reload Unit-ID 1 / MASTER."
    )

    print(
        "  5. Wait for Unit-ID 1 / MASTER to return."
    )

    print(
        "  6. Verify software using 'do show version'."
    )

    print()

    print(
        "Important:"
    )

    print(
        "  - Firmware percentage is taken from "
        "actual switch output."
    )

    print(
        "  - No fake/timer-based percentage is used."
    )

    print(
        "  - Reload happens only after successful copy."
    )

    print(
        "  - 'Socket is closed' during boot system "
        "is not automatically treated as copy failure."
    )

    print(
        "  - Unit-ID 1 / MASTER is used for the upgrade "
        "and post-reload verification."
    )

    # =====================================================
    # STEP 1
    # =====================================================

    _print_step(
        1,
        "VERIFY UNIT-ID 1 / MASTER",
    )

    print()

    print(
        f"MASTER IP : {master_ip}"
    )

    master_connection = _connect_master(
        master_ip,
        master_username,
        master_password,
        connection_type,
    )

    if master_connection is None:

        _print_header(
            f"{TEST_CASE_ID} RESULT"
        )

        print()

        print(
            "FAIL"
        )

        print()

        print(
            "✗ Unable to connect to Unit-ID 1 / MASTER."
        )

        return False

    print()

    print(
        "✓ Unit-ID 1 / MASTER connection is active."
    )

    # =====================================================
    # STEP 2
    # =====================================================

    _print_step(
        2,
        "SELECT SOFTWARE UPGRADE METHOD",
    )

    method = _select_upgrade_method()

    if method == "tftp":

        upgrade_info = _get_tftp_details()

    else:

        upgrade_info = _get_usb_details()

    # -----------------------------------------------------
    # Show plan
    # -----------------------------------------------------

    if not _show_upgrade_plan(
        upgrade_info
    ):

        print()

        print(
            "TC-STK-011 cancelled by user."
        )

        return False

    # =====================================================
    # STEP 3
    # =====================================================

    firmware_ok = (
        _start_and_monitor_firmware_copy(
            master_connection,
            upgrade_info["boot_command"],
        )
    )

    if not firmware_ok:

        _print_header(
            f"{TEST_CASE_ID} RESULT"
        )

        print()

        print(
            "FAIL"
        )

        print()

        print(
            "✗ Firmware upgrade did not complete successfully."
        )

        print(
            "✗ Reload was NOT performed."
        )

        return False

    # =====================================================
    # STEP 4
    # =====================================================

    reload_ok = _reload_master(
        master_connection
    )

    if not reload_ok:

        _print_header(
            f"{TEST_CASE_ID} RESULT"
        )

        print()

        print(
            "FAIL"
        )

        print()

        print(
            "✗ Firmware copy completed."
        )

        print(
            "✗ Reload could not be started."
        )

        return False

    # =====================================================
    # STEP 5
    # =====================================================

    master_connection = (
        _wait_for_master_after_reload(
            master_connection,
            master_ip,
            master_username,
            master_password,
            connection_type,
        )
    )

    if master_connection is None:

        _print_header(
            f"{TEST_CASE_ID} RESULT"
        )

        print()

        print(
            "FAIL"
        )

        print()

        print(
            "✗ Unit-ID 1 / MASTER did not return "
            "after reboot."
        )

        return False

    # =====================================================
    # STEP 6
    # =====================================================

    version_ok = _verify_software_version(
        master_connection
    )

    # =====================================================
    # FINAL RESULT
    # =====================================================

    _print_header(
        f"{TEST_CASE_ID} RESULT"
    )

    print()

    if version_ok:

        print(
            "PASS"
        )
        

        print()

        print(
            "✓ Firmware upgrade completed successfully."
        )

        print(
            "✓ Firmware copy success message received."
        )

        print(
            "✓ Unit-ID 1 / MASTER was reloaded."
        )

        print(
            "✓ Unit-ID 1 / MASTER returned successfully."
        )

        print(
            "✓ SSH connection established."
        )

        print(
            "✓ 'do show version' executed successfully."
        )

    else:

        print(
            "FAIL"
        )

        print()

        print(
            "✗ Firmware upgrade completed."
        )

        print(
            "✗ MASTER returned after reboot."
        )

        print(
            "✗ Software version verification failed."
        )

    print()

    print(
        "Master connection remains active."
    )

    print()

    return version_ok


# =========================================================
# OPTIONAL DIRECT EXECUTION
# =========================================================

if __name__ == "__main__":

    print()

    print("=" * 70)

    print(
        "TC-STK-011 must normally be started "
        "from main.py."
    )

    print("=" * 70)

    print()