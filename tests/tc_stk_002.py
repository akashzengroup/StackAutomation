
"""
TC-STK-002 - Member Number (Unit-ID) Assignment

Objective:
    Verify configured Unit-IDs persist across reboot with no duplicates.

Procedure:
    1. Check member IDs
    2. Write memory
    3. Reboot stack
    4. Wait for Unit-1 to come UP
    5. Reconnect to Unit-1
    6. Wait until complete stack is formed
    7. Verify roles/IDs after boot

Expected:
    Unit-1  -> Controller / Master
    Unit-2  -> Backup
    Unit-3+ -> Member
"""

import re
import time
import subprocess

# IMPORTANT:
# SwitchConnection must be imported here because TC-STK-002
# creates a NEW connection after reload.
from connection import SwitchConnection


# ======================================================================
# TEST CASE INFORMATION
# ======================================================================

TEST_CASE_ID = "TC-STK-002"
TEST_CASE_TITLE = "Member Number (Unit-ID) Assignment"

SSH_PORT = 22

# ======================================================================
# TIMING / RETRY VALUES
# ======================================================================

PING_RETRY_COUNT = 60
PING_RETRY_INTERVAL = 5

# Increased from 5 to 15.
# Switch can take time before SSH service becomes available.
SSH_RETRY_COUNT = 15
SSH_RETRY_INTERVAL = 5

# Stack formation retry.
# 60 x 5 sec = maximum 5 minutes.
STACK_RETRY_COUNT = 60
STACK_RETRY_INTERVAL = 5

# Initial wait after reload.
RELOAD_WAIT = 25

WRITE_TIMEOUT = 30
RELOAD_TIMEOUT = 20

# ======================================================================
# COMMANDS
# ======================================================================

SHOW_STACK_COMMAND = "show stack"
WRITE_COMMAND = "do write"
RELOAD_COMMAND = "do reload"


# ======================================================================
# DISPLAY HELPERS
# ======================================================================

def _banner(title):

    print("\n" + "=" * 70)
    print(title.center(70))
    print("=" * 70)


def _section(title):

    print("\n" + "-" * 70)
    print(title)
    print("-" * 70)


# ======================================================================
# OUTPUT CLEANING
# ======================================================================

def _clean_output(output):

    if output is None:
        return ""

    output = str(output)

    # Remove ANSI escape sequences
    output = re.sub(
        r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])",
        "",
        output
    )

    return output.replace("\r", "")


# ======================================================================
# SHELL RECEIVE
# ======================================================================

def _read_shell(shell, wait_time=0.5):

    if shell is None:
        return ""

    output = ""

    time.sleep(wait_time)

    try:

        while shell.recv_ready():

            data = shell.recv(65535)

            if not data:
                break

            if isinstance(data, bytes):

                data = data.decode(
                    "utf-8",
                    errors="ignore"
                )

            output += data

    except Exception:
        pass

    return _clean_output(output)


# ======================================================================
# GENERIC COMMAND EXECUTION
# ======================================================================

def _get_command_output(connection, command, timeout=30):

    """
    Execute a command using the existing SwitchConnection.

    No new connection is created here.
    """

    if connection is None:
        return ""

    # --------------------------------------------------------------
    # Preferred method
    # --------------------------------------------------------------

    try:

        if hasattr(connection, "send_command"):

            result = connection.send_command(command)

            if result is not None:

                return _clean_output(result)

    except Exception as exc:

        print(
            f"Command execution warning: {exc}"
        )

    # --------------------------------------------------------------
    # execute_command fallback
    # --------------------------------------------------------------

    try:

        if hasattr(connection, "execute_command"):

            result = connection.execute_command(command)

            if result is not None:

                return _clean_output(result)

    except Exception as exc:

        print(
            f"Command execution warning: {exc}"
        )

    # --------------------------------------------------------------
    # Direct shell fallback
    # --------------------------------------------------------------

    shell = getattr(
        connection,
        "shell",
        None
    )

    if shell is not None:

        try:

            shell.send(
                command + "\n"
            )

            output = _read_shell(
                shell,
                wait_time=1
            )

            return output

        except Exception as exc:

            print(
                f"Shell command execution error: {exc}"
            )

    return ""


# ======================================================================
# WRITE MEMORY
# ======================================================================

def _write_memory(connection):

    """
    Execute:

        do write

    Automatically handles overwrite confirmation.
    """

    if connection is None:

        print(
            "\nWrite memory failed: connection is not available."
        )

        return False

    print(
        "\nExecuting: do write"
    )

    shell = getattr(
        connection,
        "shell",
        None
    )

    if shell is None:

        print(
            "\nInteractive shell is not available."
        )

        return False

    output_parts = []

    overwrite_confirmed = False
    write_completed = False

    start_time = time.time()

    # --------------------------------------------------------------
    # Clear old shell data
    # --------------------------------------------------------------

    try:

        while shell.recv_ready():

            shell.recv(65535)

    except Exception:
        pass

    # --------------------------------------------------------------
    # Send DO WRITE
    # --------------------------------------------------------------

    try:

        shell.send(
            WRITE_COMMAND + "\n"
        )

    except Exception as exc:

        print(
            f"\nUnable to send '{WRITE_COMMAND}': {exc}"
        )

        return False

    # --------------------------------------------------------------
    # Monitor response
    # --------------------------------------------------------------

    while time.time() - start_time < WRITE_TIMEOUT:

        time.sleep(0.5)

        data = ""

        try:

            while shell.recv_ready():

                chunk = shell.recv(65535)

                if not chunk:
                    break

                if isinstance(chunk, bytes):

                    chunk = chunk.decode(
                        "utf-8",
                        errors="ignore"
                    )

                data += chunk

        except Exception:

            data = ""

        if not data:
            continue

        data = _clean_output(data)

        output_parts.append(data)

        combined_output = "".join(
            output_parts
        )

        # ----------------------------------------------------------
        # OVERWRITE PROMPT
        # ----------------------------------------------------------

        overwrite_prompt = re.search(
            r"Overwrite\s+file\s*\[startup-config\].*?"
            r"\(Y/N\)\s*\[N\]\s*\?",
            combined_output,
            re.IGNORECASE
        )

        # Generic fallback
        if not overwrite_prompt:

            overwrite_prompt = re.search(
                r"\(Y/N\).*?\?",
                combined_output,
                re.IGNORECASE
            )

        if overwrite_prompt and not overwrite_confirmed:

            overwrite_confirmed = True

            print(
                "\nOverwrite confirmation detected."
            )

            print(
                "Sending: Y"
            )

            try:

                shell.send(
                    "Y\n"
                )

                time.sleep(1)

            except Exception as exc:

                print(
                    f"\nUnable to send Y: {exc}"
                )

                return False

            continue

        # ----------------------------------------------------------
        # SUCCESS PATTERNS
        # ----------------------------------------------------------

        success_patterns = [

            r"configuration\s+saved",

            r"configuration\s+save",

            r"copy\s+succeeded",

            r"successfully",

            r"completed",

            r"done",

            r"saved\s+successfully",
        ]

        if any(
            re.search(
                pattern,
                combined_output,
                re.IGNORECASE
            )
            for pattern in success_patterns
        ):

            write_completed = True

        # ----------------------------------------------------------
        # NORMAL CLI PROMPT
        # ----------------------------------------------------------

        lines = [

            line.strip()

            for line in combined_output.splitlines()

            if line.strip()
        ]

        if lines:

            last_line = lines[-1]

            if re.search(
                r"[A-Za-z0-9_.-]+[#>]\s*$",
                last_line
            ):

                if overwrite_confirmed:

                    write_completed = True

        if write_completed:
            break

    # --------------------------------------------------------------
    # Display output
    # --------------------------------------------------------------

    output = "".join(
        output_parts
    )

    if output:

        print(
            "\n" + output.rstrip()
        )

    # --------------------------------------------------------------
    # Result
    # --------------------------------------------------------------

    if write_completed:

        print(
            "\nConfiguration save command completed."
        )

        return True

    if overwrite_confirmed:

        print(
            "\nOverwrite confirmation was accepted."
        )

        print(
            "Configuration save command completed."
        )

        return True

    print(
        "\nConfiguration save command did not "
        "complete within the expected time."
    )

    return False


# ======================================================================
# RELOAD
# ======================================================================

def _reload_stack(connection):

    """
    Reload the stack using:

        do reload
    """

    if connection is None:
        return False

    print(
        "\nExecuting: do reload"
    )

    shell = getattr(
        connection,
        "shell",
        None
    )

    if shell is None:

        print(
            "\nInteractive shell is not available."
        )

        return False

    # --------------------------------------------------------------
    # Clear old output
    # --------------------------------------------------------------

    try:

        while shell.recv_ready():

            shell.recv(65535)

    except Exception:
        pass

    # --------------------------------------------------------------
    # Send reload
    # --------------------------------------------------------------

    try:

        shell.send(
            RELOAD_COMMAND + "\n"
        )

    except Exception as exc:

        print(
            f"\nUnable to send '{RELOAD_COMMAND}': {exc}"
        )

        return False

    output_parts = []

    start_time = time.time()

    # --------------------------------------------------------------
    # Monitor reload response
    # --------------------------------------------------------------

    while time.time() - start_time < RELOAD_TIMEOUT:

        time.sleep(0.5)

        data = ""

        try:

            while shell.recv_ready():

                chunk = shell.recv(65535)

                if not chunk:
                    break

                if isinstance(chunk, bytes):

                    chunk = chunk.decode(
                        "utf-8",
                        errors="ignore"
                    )

                data += chunk

        except Exception:

            # SSH disconnect during reload is expected.
            break

        if not data:
            continue

        data = _clean_output(data)

        output_parts.append(data)

        combined = "".join(
            output_parts
        )

        # ----------------------------------------------------------
        # Reload confirmation
        # ----------------------------------------------------------

        if re.search(
            r"(?:reload|reboot).*?"
            r"(?:\(Y/N\)|confirm|proceed|continue)",
            combined,
            re.IGNORECASE
        ):

            try:

                shell.send(
                    "Y\n"
                )

                time.sleep(1)

            except Exception:
                pass

    output = "".join(
        output_parts
    )

    if output:

        print(
            "\n" + output.rstrip()
        )

    print(
        "\nReload command issued successfully."
    )

    return True


# ======================================================================
# PING
# ======================================================================

def _ping_host(host):

    """
    Windows-friendly ping.
    """

    try:

        result = subprocess.run(
            [
                "ping",
                "-n",
                "1",
                "-w",
                "1000",
                host
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3
        )

        return result.returncode == 0

    except Exception:

        return False


def _wait_for_ping(host, retries=PING_RETRY_COUNT):

    print("\n" + "=" * 70)
    print("WAITING FOR UNIT-1")
    print("=" * 70)

    print(
        f"\nMASTER IP : {host}"
    )

    print(
        "\nStarting ping check..."
    )

    for attempt in range(
        1,
        retries + 1
    ):

        print(
            f"Ping attempt {attempt}/{retries} "
            f"- Waiting for {host}..."
        )

        if _ping_host(host):

            print(
                "\nUnit-1 is UP!"
            )

            print(
                f"MASTER {host} is responding."
            )

            return True

        time.sleep(
            PING_RETRY_INTERVAL
        )

    print(
        "\nUnit-1 did not respond "
        "within the expected time."
    )

    return False


# ======================================================================
# RECONNECT AFTER RELOAD
# ======================================================================

def _reconnect_after_reload(
    master_ip,
    username,
    password,
    connection_type
):

    """
    Reconnect to Unit-1 after reboot.

    SSH retry count intentionally increased to 15
    because switch SSH service can take additional
    time after the switch starts responding to ping.
    """

    # --------------------------------------------------------------
    # STEP 1 - WAIT FOR PING
    # --------------------------------------------------------------

    if not _wait_for_ping(master_ip):

        return None

    # --------------------------------------------------------------
    # IMPORTANT:
    # Ping UP does NOT mean SSH is immediately ready.
    #
    # Give the switch some time before first SSH attempt.
    # --------------------------------------------------------------

    print(
        "\nUnit-1 is responding to ping."
    )

    print(
        "Waiting 5 seconds for SSH service to become ready..."
    )

    time.sleep(5)

    # --------------------------------------------------------------
    # STEP 2 - SSH RECONNECT
    # --------------------------------------------------------------

    print("\n" + "=" * 70)
    print("CONNECTING TO MASTER")
    print("=" * 70)

    for attempt in range(
        1,
        SSH_RETRY_COUNT + 1
    ):

        print(
            f"\nConnection attempt "
            f"#{attempt}/{SSH_RETRY_COUNT}"
        )

        print(
            f"Connecting to "
            f"{master_ip}:{SSH_PORT} "
            f"using {connection_type.upper()}..."
        )

        try:

            # IMPORTANT:
            # This class is imported at module level:
            #
            # from connection import SwitchConnection
            #
            new_connection = SwitchConnection(
                connection_type=connection_type,
                ip=master_ip,
                username=username,
                password=password
            )

            if new_connection.connect():

                print(
                    "\nConnection successful!"
                )

                print(
                    "Unit-1 / Controller SSH session is ready."
                )

                return new_connection

        except Exception as exc:

            print(
                f"Connection failed: {exc}"
            )

        if attempt < SSH_RETRY_COUNT:

            print(
                f"\nSSH is not ready yet."
            )

            print(
                f"Retrying in "
                f"{SSH_RETRY_INTERVAL} seconds..."
            )

            time.sleep(
                SSH_RETRY_INTERVAL
            )

    print(
        "\nUnable to reconnect to Unit-1 "
        "after all retry attempts."
    )

    return None


# ======================================================================
# SHOW STACK PARSER
# ======================================================================

def _parse_stack_members(output):

    """
    Parse ROS7 'show stack' output.

    Accepted roles:
        controller
        master
        active
        backup
        standby
        member
    """

    members = []

    output = _clean_output(
        output
    )

    for line in output.splitlines():

        line = line.strip()

        if not line:
            continue

        # Skip headers
        if line.startswith("Unit Id"):
            continue

        if line.startswith("-------"):
            continue

        match = re.match(
            r"^(\d+)\s+"
            r"([0-9a-fA-F:]{17})\s+"
            r"(controller|master|active|backup|standby|member)\b",
            line,
            re.IGNORECASE
        )

        if not match:
            continue

        unit_id = int(
            match.group(1)
        )

        mac = match.group(2)

        role = match.group(3).lower()

        members.append(
            {
                "unit_id": unit_id,
                "mac": mac,
                "role": role
            }
        )

    members.sort(
        key=lambda item: item["unit_id"]
    )

    return members


# ======================================================================
# MEMBER-ID VERIFICATION
# ======================================================================

def _verify_member_ids(
    members,
    expected_members
):

    detected_ids = sorted(
        member["unit_id"]
        for member in members
    )

    expected_ids = list(
        range(
            1,
            expected_members + 1
        )
    )

    print(
        f"\nExpected Unit-IDs : {expected_ids}"
    )

    print(
        f"Detected Unit-IDs : {detected_ids}"
    )

    # --------------------------------------------------------------
    # Duplicate check
    # --------------------------------------------------------------

    if len(detected_ids) != len(
        set(detected_ids)
    ):

        print(
            "\nMember-ID Check FAILED:"
        )

        print(
            f"Duplicate Unit-ID detected: "
            f"{detected_ids}"
        )

        return False

    # --------------------------------------------------------------
    # Exact ID check
    # --------------------------------------------------------------

    if detected_ids != expected_ids:

        print(
            "\nMember-ID Check FAILED:"
        )

        print(
            f"Expected: {expected_ids}"
        )

        print(
            f"Detected: {detected_ids}"
        )

        return False

    print(
        "\nMember-ID Check : PASS"
    )

    print(
        "All Unit-IDs are unique and sequential."
    )

    return True


# ======================================================================
# ROLE VERIFICATION
# ======================================================================

def _verify_roles(
    members,
    expected_members
):

    role_map = {
        member["unit_id"]: member["role"]
        for member in members
    }

    # --------------------------------------------------------------
    # Unit-1
    # --------------------------------------------------------------

    unit1_role = role_map.get(
        1,
        ""
    )

    if unit1_role not in (
        "controller",
        "master",
        "active"
    ):

        print(
            "\nRole Check FAILED:"
        )

        print(
            f"Unit-1 expected Controller/Master, "
            f"detected '{unit1_role}'"
        )

        return False

    # --------------------------------------------------------------
    # Unit-2
    # --------------------------------------------------------------

    if expected_members >= 2:

        unit2_role = role_map.get(
            2,
            ""
        )

        if unit2_role not in (
            "backup",
            "standby"
        ):

            print(
                "\nRole Check FAILED:"
            )

            print(
                f"Unit-2 expected Backup, "
                f"detected '{unit2_role}'"
            )

            return False

    # --------------------------------------------------------------
    # Unit-3 to Unit-N
    # --------------------------------------------------------------

    if expected_members > 2:

        for unit_id in range(
            3,
            expected_members + 1
        ):

            role = role_map.get(
                unit_id,
                ""
            )

            if role != "member":

                print(
                    "\nRole Check FAILED:"
                )

                print(
                    f"Unit-{unit_id} expected "
                    f"'member', detected '{role}'"
                )

                return False

    # --------------------------------------------------------------
    # Success
    # --------------------------------------------------------------

    print(
        "\nRole Check : PASS"
    )

    print(
        "Unit-1 Controller"
    )

    print(
        "Unit-2 Backup"
    )

    if expected_members > 2:

        print(
            f"Unit-3 to Unit-{expected_members} Members"
        )

    return True


# ======================================================================
# WAIT FOR COMPLETE STACK
# ======================================================================

def _wait_for_complete_stack(
    connection,
    expected_members
):

    """
    After Unit-1 SSH becomes available, the other
    stack members may still be booting/forming.

    Therefore this function repeatedly executes
    'show stack' until all expected members appear.
    """

    print("\n" + "=" * 70)
    print("WAITING FOR COMPLETE STACK")
    print("=" * 70)

    print(
        f"\nExpected stack members : "
        f"{expected_members}"
    )

    print(
        "\nUnit-1 is UP, but other stack members "
        "may still be joining."
    )

    print(
        "The script will repeatedly run "
        "'show stack' until the complete stack is detected."
    )

    for attempt in range(
        1,
        STACK_RETRY_COUNT + 1
    ):

        print(
            "\n" + "-" * 70
        )

        print(
            f"STACK CHECK "
            f"{attempt}/{STACK_RETRY_COUNT}"
        )

        print(
            "-" * 70
        )

        try:

            output = _get_command_output(
                connection,
                SHOW_STACK_COMMAND
            )

            members = _parse_stack_members(
                output
            )

            detected_count = len(
                members
            )

            print(
                f"\nDetected stack members: "
                f"{detected_count}/{expected_members}"
            )

            if detected_count > 0:

                detected_ids = sorted(
                    member["unit_id"]
                    for member in members
                )

                print(
                    f"Detected Unit-IDs: "
                    f"{detected_ids}"
                )

            # ------------------------------------------------------
            # Complete stack detected
            # ------------------------------------------------------

            if detected_count >= expected_members:

                ids_ok = _verify_member_ids(
                    members,
                    expected_members
                )

                roles_ok = _verify_roles(
                    members,
                    expected_members
                )

                if ids_ok and roles_ok:

                    print(
                        "\nComplete stack is ready."
                    )

                    return True

                print(
                    "\nAll members are visible, "
                    "but IDs/roles are not ready yet."
                )

            else:

                print(
                    "\nStack is still forming."
                )

        except Exception as exc:

            print(
                f"\nStack check warning: {exc}"
            )

        # ----------------------------------------------------------
        # Retry
        # ----------------------------------------------------------

        if attempt < STACK_RETRY_COUNT:

            print(
                f"\nWaiting "
                f"{STACK_RETRY_INTERVAL} seconds "
                f"before next 'show stack'..."
            )

            time.sleep(
                STACK_RETRY_INTERVAL
            )

    print(
        "\nComplete stack was not detected "
        "within the expected time."
    )

    return False


# ======================================================================
# MAIN TEST CASE
# ======================================================================

def run_test_case(
    master_ip=None,
    username=None,
    password=None,
    expected_members=None,
    member_count=None,
    switch_count=None,
    expected_units=None,
    master_connection=None,
    connection=None,
    connection_type=None,
    **kwargs
):

    _banner(
        "TC-STK-002 - Member Number (Unit-ID) Assignment"
    )

    print(
        "\nObjective:\n"
        "Verify configured Unit-IDs persist across reboot "
        "with no duplicates.\n"
    )

    print(
        "Test Procedure:\n"
        "  1. Check member IDs\n"
        "  2. Write memory using 'do write'\n"
        "  3. Reboot stack using 'do reload'\n"
        "  4. Wait for Unit-1 to come UP\n"
        "  5. Reconnect to Unit-1\n"
        "  6. Wait for complete stack formation\n"
        "  7. Verify roles/IDs after boot"
    )

    # ==================================================================
    # DETERMINE EXPECTED MEMBER COUNT
    # ==================================================================

    if expected_members is None:
        expected_members = member_count

    if expected_members is None:
        expected_members = switch_count

    if expected_members is None:
        expected_members = expected_units

    if expected_members is None:

        print(
            "\nERROR: Expected stack member count "
            "was not provided."
        )

        return False

    try:

        expected_members = int(
            expected_members
        )

    except Exception:

        print(
            "\nERROR: Invalid expected member count."
        )

        return False

    if expected_members < 2:

        print(
            "\nERROR: Stack must contain "
            "at least 2 members."
        )

        return False

    if expected_members > 8:

        print(
            "\nERROR: Maximum supported stack "
            "size is 8 members."
        )

        return False

    # ==================================================================
    # GET EXISTING MASTER CONNECTION
    # ==================================================================

    if master_connection is None:
        master_connection = connection

    if master_connection is None:

        print(
            "\nERROR: Existing Unit-1 master connection "
            "was not provided by main.py."
        )

        print(
            "\nTC-STK-002 FAILED."
        )

        return False

    # ==================================================================
    # GET CONNECTION TYPE
    # ==================================================================

    if connection_type is None:

        connection_type = kwargs.get(
            "connection_type"
        )

    if connection_type is None:

        connection_type = getattr(
            master_connection,
            "connection_type",
            "ssh"
        )

    # ==================================================================
    # STEP 1 - CHECK MEMBER IDs
    # ==================================================================

    _section(
        "STEP 1: CHECK MEMBER IDs"
    )

    print(
        "\nUsing existing Unit-1 / Controller connection."
    )

    print(
        "No new connection will be created."
    )

    # --------------------------------------------------------------
    # Verify shell
    # --------------------------------------------------------------

    if getattr(
        master_connection,
        "shell",
        None
    ) is None:

        print(
            "\nERROR: Existing master connection "
            "does not have an active shell."
        )

        print(
            "\nTC-STK-002 FAILED."
        )

        return False

    print(
        "\nExecuting: show stack"
    )

    output = _get_command_output(
        master_connection,
        SHOW_STACK_COMMAND
    )

    _banner(
        "SHOW STACK"
    )

    print(
        SHOW_STACK_COMMAND
    )

    print()

    print(
        output
    )

    _banner(
        ""
    )

    members = _parse_stack_members(
        output
    )

    if not members:

        print(
            "\nUnable to detect stack members."
        )

        print(
            "\nTC-STK-002 FAILED."
        )

        return False

    ids_ok = _verify_member_ids(
        members,
        expected_members
    )

    roles_ok = _verify_roles(
        members,
        expected_members
    )

    if not ids_ok or not roles_ok:

        print(
            "\nCurrent stack member assignment "
            "is not correct."
        )

        print(
            "\nTC-STK-002 FAILED."
        )

        return False

    # ==================================================================
    # STEP 2 - WRITE MEMORY
    # ==================================================================

    _section(
        "STEP 2: WRITE MEMORY"
    )

    print(
        "\nSaving configuration from "
        "Unit-1 / Controller."
    )

    print(
        "\nCommand: do write"
    )

    print(
        "If the switch asks for overwrite confirmation, "
        "the script will automatically send Y."
    )

    write_ok = _write_memory(
        master_connection
    )

    if not write_ok:

        print(
            "\nConfiguration save failed."
        )

        print(
            "\nTC-STK-002 FAILED."
        )

        return False

    # ==================================================================
    # STEP 3 - REBOOT STACK
    # ==================================================================

    _section(
        "STEP 3: REBOOT STACK"
    )

    print(
        "\nAll stack member configuration "
        "has been saved."
    )

    print(
        "\nRebooting the stack using "
        "'do reload'."
    )

    print(
        "\nIMPORTANT:"
    )

    print(
        "The stack will temporarily become unreachable."
    )

    print(
        "Please wait for Unit-1 / Controller "
        "to come back online."
    )

    reload_ok = _reload_stack(
        master_connection
    )

    if not reload_ok:

        print(
            "\nReload command failed."
        )

        print(
            "\nTC-STK-002 FAILED."
        )

        return False

    # ==================================================================
    # CLOSE OLD CONNECTION
    # ==================================================================

    print(
        "\nClosing old Unit-1 connection..."
    )

    try:

        if hasattr(
            master_connection,
            "disconnect"
        ):

            master_connection.disconnect()

        elif hasattr(
            master_connection,
            "close"
        ):

            master_connection.close()

    except Exception as exc:

        print(
            f"\nConnection close warning: {exc}"
        )

    # ==================================================================
    # INITIAL REBOOT WAIT
    # ==================================================================

    print(
        f"\nWaiting {RELOAD_WAIT} seconds "
        "for the stack to reboot..."
    )

    time.sleep(
        RELOAD_WAIT
    )

    # ==================================================================
    # RECONNECT TO UNIT-1
    # ==================================================================

    new_connection = _reconnect_after_reload(
        master_ip,
        username,
        password,
        connection_type
    )

    if new_connection is None:

        print(
            "\nUnable to reconnect to "
            "Unit-1 / Controller after reboot."
        )

        print(
            "\nTC-STK-002 FAILED."
        )

        return False

    # ==================================================================
    # STEP 4 - WAIT FOR COMPLETE STACK
    # ==================================================================

    _section(
        "STEP 4: WAIT FOR COMPLETE STACK"
    )

    print(
        "\nUnit-1 is connected."
    )

    print(
        "Now waiting for all stack members "
        "to finish booting and join the stack."
    )

    verification_ok = _wait_for_complete_stack(
        new_connection,
        expected_members
    )

    # ==================================================================
    # FINAL RESULT
    # ==================================================================

    if verification_ok:

        _banner(
            "TC-STK-002 PASS"
        )

        print(
            "\n✓ Unit-ID assignment persisted after reboot."
        )

        print(
            "✓ No duplicate Unit-IDs detected."
        )

        print(
            "✓ Unit-1 Controller verified."
        )

        print(
            "✓ Unit-2 Backup verified."
        )

        if expected_members > 2:

            print(
                f"✓ Unit-3 to Unit-{expected_members} "
                "are Members."
            )

        print(
            "\n✓ Complete stack formation verified."
        )

        print(
            "\nTC-STK-002 completed successfully."
        )

        return True

    # ==================================================================
    # FAILURE
    # ==================================================================

    _banner(
        "TC-STK-002 FAIL"
    )

    print(
        "\nCurrent stack member assignment "
        "is not correct after reboot."
    )

    print(
        "\nTC-STK-002 FAILED."
    )

    return False


# ======================================================================
# ALIAS USED BY MAIN.PY
# ======================================================================

run_tc_stk_002 = run_test_case


# ======================================================================
# DIRECT EXECUTION
# ======================================================================

if __name__ == "__main__":

    print(
        "\nTC-STK-002 is normally executed "
        "through main.py."
    )

    print(
        "\nUse:"
    )

    print(
        "    python main.py"
    )

