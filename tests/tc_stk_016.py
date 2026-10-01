import os
import re
import sys
import time
import subprocess
import platform
import inspect

try:
    from connection import SwitchConnection
except ImportError:
    SwitchConnection = None


# ======================================================================
# TC-STK-016 CONFIGURATION
# ======================================================================

TEST_CASE_ID = "TC-STK-016"
TEST_CASE_TITLE = "SNMP Configuration and SNMP Walk Verification"

SHOW_STACK_COMMAND = "do show stack"
SHOW_LOG_COMMAND = "show logging"

DEFAULT_SNMP_MASK = "255.255.255.0"

SNMP_WALK_REQUIRED_ENTRIES = 50

SNMP_WALK_MAX_WAIT = 180

SUPPORTED_SNMP_WALK_OS = ["Windows", "Linux"]


# ======================================================================
# COMMON DISPLAY FUNCTIONS
# ======================================================================

def _print_header(title):
    print()
    print("=" * 70)
    print(f"{title:^70}")
    print("=" * 70)


def _send_command(connection, command, delay=2):
    try:
        output = connection.send_command(command)
        time.sleep(delay)

        if output is None:
            return ""

        return str(output)

    except Exception as exc:
        print(f"Command failed: {command}")
        print(f"Error: {exc}")
        return ""


def _run_command(connection, command, delay=2):
    print()
    print(f"> {command}")

    output = _send_command(
        connection,
        command,
        delay=delay
    )

    if output:
        print(output)

    return output


# ======================================================================
# STACK PARSING
# ======================================================================

def _parse_stack_members(output):
    members = []

    if not output:
        return members

    lines = output.splitlines()

    for line in lines:
        line = line.strip()

        if not line:
            continue

        # Common formats:
        # Unit-1
        # 1 MASTER
        # 1   Controller
        # Unit ID 1

        match = re.search(
            r"(?:Unit[-\s]*ID|Unit)[-\s:]*(\d+)",
            line,
            re.IGNORECASE
        )

        if match:
            unit_id = int(match.group(1))

            role = ""

            upper_line = line.upper()

            if "MASTER" in upper_line:
                role = "MASTER"
            elif "CONTROLLER" in upper_line:
                role = "MASTER"
            elif "BACKUP" in upper_line:
                role = "BACKUP"

            if not any(
                member.get("unit_id") == unit_id
                for member in members
            ):
                members.append(
                    {
                        "unit_id": unit_id,
                        "role": role,
                        "line": line,
                    }
                )

    # Fallback parsing for table format
    if not members:
        for line in lines:
            match = re.match(
                r"^\s*(\d+)\s+.*",
                line
            )

            if not match:
                continue

            try:
                unit_id = int(match.group(1))
            except ValueError:
                continue

            upper_line = line.upper()

            role = ""

            if "MASTER" in upper_line:
                role = "MASTER"
            elif "CONTROLLER" in upper_line:
                role = "MASTER"
            elif "BACKUP" in upper_line:
                role = "BACKUP"

            if not any(
                member.get("unit_id") == unit_id
                for member in members
            ):
                members.append(
                    {
                        "unit_id": unit_id,
                        "role": role,
                        "line": line,
                    }
                )

    return sorted(
        members,
        key=lambda item: item["unit_id"]
    )


def _display_stack_members(members):
    if not members:
        print("No stack members detected.")
        return

    print()
    print("Current Stack Members")
    print("-" * 70)

    for member in members:
        role = member.get("role", "")

        if role:
            print(
                f"Unit-ID {member['unit_id']} : {role}"
            )
        else:
            print(
                f"Unit-ID {member['unit_id']}"
            )

    print("-" * 70)


# ======================================================================
# STACK VERIFICATION
# ======================================================================

def _verify_stack(connection):
    _print_header("VERIFYING STACK")

    output = _run_command(
        connection,
        SHOW_STACK_COMMAND,
        delay=3
    )

    members = _parse_stack_members(output)

    _display_stack_members(members)

    if not members:
        print()
        print("STACK VERIFICATION : FAIL")
        return False, members

    unit_1 = next(
        (
            member
            for member in members
            if member["unit_id"] == 1
        ),
        None
    )

    if not unit_1:
        print()
        print("Unit-ID 1 was not found.")
        print("STACK VERIFICATION : FAIL")
        return False, members

    role = unit_1.get("role", "").upper()

    if role and role not in (
        "MASTER",
        "CONTROLLER",
    ):
        print()
        print(
            "Unit-ID 1 is not the expected MASTER/CONTROLLER."
        )
        print("STACK VERIFICATION : FAIL")
        return False, members

    print()
    print("Unit-ID 1 is available as MASTER/CONTROLLER.")

    print()
    print("STACK VERIFICATION : PASS")

    return True, members


# ======================================================================
# STACK CONFIGURATION CHECK
# ======================================================================

def _stack_already_configured(connection):
    try:
        output = _send_command(
            connection,
            SHOW_STACK_COMMAND,
            delay=3
        )

        members = _parse_stack_members(output)

        return len(members) >= 2

    except Exception:
        return False


def _configure_stack_if_required(connection):
    if _stack_already_configured(connection):
        print()
        print("Existing stack detected.")
        print("Skipping stack creation/configuration.")
        return True

    print()
    print("No running stack detected.")

    print()
    print(
        "TC-STK-016 requires a running stack before "
        "SNMP verification."
    )

    print()
    answer = input(
        "Do you want to configure the stack now? (y/n): "
    ).strip().lower()

    if answer != "y":
        print()
        print("Stack configuration skipped.")
        return False

    print()
    print(
        "Please use the normal stack creation flow "
        "before running TC-STK-016."
    )

    input(
        "\nPress ENTER after the stack is configured and running..."
    )

    return _stack_already_configured(connection)


# ======================================================================
# CONFIG MODE
# ======================================================================

def _is_config_mode(connection):
    try:
        prompt = ""

        if hasattr(connection, "prompt"):
            prompt = str(
                getattr(connection, "prompt", "")
            )

        if hasattr(connection, "last_prompt"):
            prompt = str(
                getattr(connection, "last_prompt", "")
            )

        return (
            prompt.rstrip().endswith("(config)#")
            or
            "(config-" in prompt
        )

    except Exception:
        return False


def _connection_is_config_mode(connection):
    return _is_config_mode(connection)


def _ensure_config_mode(connection):
    if _connection_is_config_mode(connection):
        return True

    print()
    print("Entering configuration mode...")

    try:
        output = _send_command(
            connection,
            "configure terminal",
            delay=2
        )

        if output:
            print(output)

    except Exception as exc:
        print(f"Unable to enter configuration mode: {exc}")
        return False

    return True


# ======================================================================
# SNMP INPUT
# ======================================================================

def _get_snmp_community():
    while True:
        community = input(
            "\nEnter SNMP community: "
        ).strip()

        if community:
            return community

        print("SNMP community cannot be empty.")


def _valid_ipv4(ip):
    pattern = (
        r"^(25[0-5]|2[0-4]\d|"
        r"1\d\d|[1-9]?\d)"
        r"(\.(25[0-5]|2[0-4]\d|"
        r"1\d\d|[1-9]?\d)){3}$"
    )

    return bool(
        re.match(
            pattern,
            ip
        )
    )


def _get_snmp_ip():
    while True:
        ip = input(
            "\nEnter NMS / SNMP Manager IP: "
        ).strip()

        if _valid_ipv4(ip):
            return ip

        print("Invalid IPv4 address.")


def _get_snmp_mask():
    mask = input(
        f"\nEnter SNMP mask "
        f"[default {DEFAULT_SNMP_MASK}]: "
    ).strip()

    if not mask:
        mask = DEFAULT_SNMP_MASK

    while not _valid_ipv4(mask):
        print("Invalid IPv4 mask.")

        mask = input(
            f"Enter SNMP mask "
            f"[default {DEFAULT_SNMP_MASK}]: "
        ).strip()

        if not mask:
            mask = DEFAULT_SNMP_MASK

    return mask


# ======================================================================
# SNMP CONFIGURATION
# ======================================================================

def _configure_snmp(connection):
    _print_header("SNMP CONFIGURATION")

    community = _get_snmp_community()
    nms_ip = _get_snmp_ip()
    mask = _get_snmp_mask()

    command = (
        f"snmp-server community "
        f"{community} rw "
        f"{nms_ip} mask {mask} view all"
    )

    print()
    print("Applying SNMP configuration...")

    output = _run_command(
        connection,
        command,
        delay=3
    )

    return {
        "community": community,
        "nms_ip": nms_ip,
        "mask": mask,
        "output": output,
    }


def _save_snmp_configuration(connection):
    _print_header("SAVING SNMP CONFIGURATION")

    print()
    print("Saving configuration...")

    output = _run_command(
        connection,
        "do write",
        delay=4
    )

    print()
    print("SNMP configuration save completed.")

    return output


# ======================================================================
# SNMP WALK MACHINE SELECTION
# ======================================================================

def _select_snmp_walk_machine():
    _print_header("SNMP WALK MACHINE")

    print()
    print("Select the machine from which SNMP Walk will run:")
    print()
    print("  1. Windows")
    print("  2. Linux")

    while True:
        choice = input(
            "\nEnter choice [1/2]: "
        ).strip()

        if choice == "1":
            return "Windows"

        if choice == "2":
            return "Linux"

        print("Invalid choice. Please enter 1 or 2.")


# ======================================================================
# SNMP WALK INPUT
# ======================================================================

def _get_walk_ip(default_ip=None):
    print()

    if default_ip:
        ip = input(
            f"Enter switch IP for SNMP Walk "
            f"[default {default_ip}]: "
        ).strip()

        if not ip:
            ip = default_ip
    else:
        ip = input(
            "Enter switch IP for SNMP Walk: "
        ).strip()

    while not _valid_ipv4(ip):
        print("Invalid IPv4 address.")

        ip = input(
            "Enter switch IP for SNMP Walk: "
        ).strip()

    return ip


def _get_walk_community(default_community=None):
    print()

    if default_community:
        community = input(
            "Enter SNMP community "
            f"[default {default_community}]: "
        ).strip()

        if not community:
            community = default_community

    else:
        community = input(
            "Enter SNMP community: "
        ).strip()

    while not community:
        print("Community cannot be empty.")

        community = input(
            "Enter SNMP community: "
        ).strip()

    return community


# ======================================================================
# LINUX SNMP WALK
# ======================================================================

def _run_linux_snmpwalk(default_ip=None, default_community=None):
    _print_header("LINUX SNMP WALK")

    ip = _get_walk_ip(default_ip)
    community = _get_walk_community(
        default_community
    )

    command = (
        f"snmpwalk -v 2c "
        f"-c {community} "
        f"{ip}"
    )

    print()
    print("SNMP Walk command:")
    print()
    print(command)

    print()
    print("=" * 70)
    print("                 RUN SNMP WALK")
    print("=" * 70)

    print()
    print(
        "Run the above command on the Linux machine."
    )

    print()
    input(
        "Press ENTER after SNMP Walk has completed..."
    )

    print()
    result = input(
        "Did SNMP Walk return valid OID responses? (y/n): "
    ).strip().lower()

    if result == "y":
        print()
        print("SNMP WALK : PASS")
        return True

    print()
    print("SNMP WALK : FAIL")
    return False


# ======================================================================
# WINDOWS SNMP WALK PATH
# ======================================================================

def _get_snmpwalk_windows_path():
    _print_header("WINDOWS SNMP WALK")

    print()
    print(
        "Enter the folder where SnmpWalk.exe is installed."
    )

    print()
    print(
        r"Example:"
    )
    print(
        r"C:\Users\Admin\Downloads\Downloads\SnmpWalk"
    )

    while True:
        path = input(
            "\nSnmpWalk folder path: "
        ).strip().strip('"')

        if not path:
            print("Path cannot be empty.")
            continue

        path = os.path.abspath(
            os.path.expandvars(path)
        )

        exe_path = os.path.join(
            path,
            "SnmpWalk.exe"
        )

        if not os.path.isdir(path):
            print()
            print(f"Folder not found: {path}")
            continue

        if not os.path.isfile(exe_path):
            print()
            print(
                f"SnmpWalk.exe not found in:\n{path}"
            )
            continue

        print()
        print(
            f"SnmpWalk.exe found:\n{exe_path}"
        )

        return path, exe_path


# ======================================================================
# WINDOWS SNMP WALK
#
# IMPORTANT:
# - No CMD window
# - No PowerShell
# - No output file
# - SnmpWalk.exe runs directly from Python
# - stdout/stderr are captured and displayed here
# ======================================================================

def _run_windows_snmpwalk(
    default_ip=None,
    default_community=None
):
    _print_header("WINDOWS SNMP WALK")

    path, exe_path = _get_snmpwalk_windows_path()

    ip = _get_walk_ip(default_ip)

    community = _get_walk_community(
        default_community
    )

    command_display = (
        "SnmpWalk.exe "
        f"-r:{ip} "
        f'-c:"{community}"'
    )

    print()
    print("SNMP Walk command:")
    print()
    print(command_display)

    print()
    print(
        f"Working directory: {path}"
    )

    print()
    print("=" * 70)
    print("              STARTING SNMP WALK")
    print("=" * 70)

    print()
    print(
        "SNMP Walk output will appear below."
    )

    print(
        f"Waiting for first "
        f"{SNMP_WALK_REQUIRED_ENTRIES} "
        f"valid OID responses..."
    )

    print()

    # --------------------------------------------------------------
    # Run SnmpWalk.exe directly.
    #
    # DO NOT use:
    #   cmd.exe
    #   /K
    #   /C
    #   PowerShell
    #   Tee-Object
    #   output redirection
    #   separate console
    #
    # This keeps the output inside the current Python console.
    # --------------------------------------------------------------

    arguments = [
        exe_path,
        f"-r:{ip}",
        f"-c:{community}",
    ]

    try:
        process = subprocess.Popen(
            arguments,
            cwd=path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

    except FileNotFoundError:
        print()
        print(
            "SnmpWalk.exe could not be started."
        )
        print(
            f"Executable: {exe_path}"
        )
        print()
        print("SNMP WALK : FAIL")
        return False

    except Exception as exc:
        print()
        print(
            "Unable to start SnmpWalk.exe."
        )
        print(
            f"Error: {exc}"
        )
        print()
        print("SNMP WALK : FAIL")
        return False

    # --------------------------------------------------------------
    # Patterns
    # --------------------------------------------------------------

    oid_pattern = re.compile(
        r"^\s*OID\s*=\s*[^,\s]+",
        re.IGNORECASE
    )

    timeout_pattern = re.compile(
        r"failed\s+to\s+get\s+value\s+of\s+SNMP\s+variable"
        r".*timeout",
        re.IGNORECASE
    )

    oid_count = 0

    monitor_start = time.time()

    max_wait = SNMP_WALK_MAX_WAIT

    passed = False

    # --------------------------------------------------------------
    # Read output live
    # --------------------------------------------------------------

    while True:

        elapsed = time.time() - monitor_start

        if elapsed > max_wait:
            print()
            print()
            print(
                "SNMP Walk monitoring timeout reached."
            )

            print(
                f"Required OID entries : "
                f"{SNMP_WALK_REQUIRED_ENTRIES}"
            )

            print(
                f"Received OID entries : "
                f"{oid_count}"
            )

            try:
                process.terminate()

                try:
                    process.wait(
                        timeout=3
                    )
                except subprocess.TimeoutExpired:
                    process.kill()

            except Exception:
                pass

            break

        try:
            line = process.stdout.readline()

        except Exception:
            line = ""

        # ----------------------------------------------------------
        # EOF
        # ----------------------------------------------------------

        if line == "":
            if process.poll() is not None:
                break

            time.sleep(0.05)
            continue

        line = line.rstrip(
            "\r\n"
        )

        # Show original SnmpWalk output
        print(
            line,
            flush=True
        )

        # ----------------------------------------------------------
        # Valid OID response
        # ----------------------------------------------------------

        if oid_pattern.match(
            line.strip()
        ):
            oid_count += 1

            print(
                f"SNMP OID responses received: "
                f"{oid_count}/"
                f"{SNMP_WALK_REQUIRED_ENTRIES}",
                flush=True
            )

            # ------------------------------------------------------
            # PASS immediately after 50 valid OIDs
            # ------------------------------------------------------

            if (
                oid_count
                >= SNMP_WALK_REQUIRED_ENTRIES
            ):
                passed = True

                print()
                print("=" * 70)
                print("       SNMP WALK VERIFICATION")
                print("=" * 70)

                print()
                print(
                    f"Required OID entries : "
                    f"{SNMP_WALK_REQUIRED_ENTRIES}"
                )

                print(
                    f"Received OID entries : "
                    f"{oid_count}"
                )

                print()
                print(
                    "First 50 valid SNMP OID "
                    "responses received successfully."
                )

                print()
                print(
                    "SNMP WALK : PASS"
                )

                # --------------------------------------------------
                # Testcase is already passed.
                #
                # SnmpWalk may continue running, so stop it.
                # Any later timeout is intentionally ignored.
                # --------------------------------------------------

                try:
                    process.terminate()

                    try:
                        process.wait(
                            timeout=3
                        )
                    except subprocess.TimeoutExpired:
                        process.kill()

                except Exception:
                    pass

                return True

        # ----------------------------------------------------------
        # Timeout before 50 OIDs
        # ----------------------------------------------------------

        if timeout_pattern.search(line):

            if (
                oid_count
                < SNMP_WALK_REQUIRED_ENTRIES
            ):
                print()
                print("=" * 70)
                print("       SNMP WALK VERIFICATION")
                print("=" * 70)

                print()
                print(
                    f"Required OID entries : "
                    f"{SNMP_WALK_REQUIRED_ENTRIES}"
                )

                print(
                    f"Received OID entries : "
                    f"{oid_count}"
                )

                print()
                print(
                    "SNMP Walk timeout occurred "
                    "before receiving 50 valid OID responses."
                )

                print()
                print(
                    "SNMP WALK : FAIL"
                )

                try:
                    process.terminate()

                    try:
                        process.wait(
                            timeout=3
                        )
                    except subprocess.TimeoutExpired:
                        process.kill()

                except Exception:
                    pass

                return False

    # ------------------------------------------------------------------
    # Process ended before 50 OID entries.
    # ------------------------------------------------------------------

    if not passed:
        print()
        print("=" * 70)
        print("       SNMP WALK VERIFICATION")
        print("=" * 70)

        print()
        print(
            f"Required OID entries : "
            f"{SNMP_WALK_REQUIRED_ENTRIES}"
        )

        print(
            f"Received OID entries : "
            f"{oid_count}"
        )

        if oid_count < SNMP_WALK_REQUIRED_ENTRIES:
            print()
            print(
                "SNMP Walk ended before "
                "50 valid OID responses were received."
            )

        print()
        print(
            "SNMP WALK : FAIL"
        )

        return False

    return True


# ======================================================================
# SNMP WALK CONTROLLER
# ======================================================================

def _run_snmp_walk(
    default_ip=None,
    default_community=None
):
    machine = _select_snmp_walk_machine()

    if machine == "Windows":
        return _run_windows_snmpwalk(
            default_ip=default_ip,
            default_community=default_community
        )

    if machine == "Linux":
        return _run_linux_snmpwalk(
            default_ip=default_ip,
            default_community=default_community
        )

    return False


# ======================================================================
# STACK OBSERVATION
# ======================================================================

def _observe_stack(
    connection,
    observation_seconds=60,
    interval=10
):
    _print_header("STACK OBSERVATION")

    print()
    print(
        f"Observing stack for "
        f"{observation_seconds} seconds..."
    )

    start_time = time.time()

    last_members = []

    while (
        time.time() - start_time
        < observation_seconds
    ):
        output = _send_command(
            connection,
            SHOW_STACK_COMMAND,
            delay=2
        )

        members = _parse_stack_members(
            output
        )

        if members:
            last_members = members

            print()
            print(
                f"Stack members detected: "
                f"{len(members)}"
            )

            for member in members:
                role = member.get(
                    "role",
                    ""
                )

                if role:
                    print(
                        f"  Unit-ID "
                        f"{member['unit_id']} "
                        f"- {role}"
                    )
                else:
                    print(
                        f"  Unit-ID "
                        f"{member['unit_id']}"
                    )

        remaining = (
            observation_seconds
            - (time.time() - start_time)
        )

        if remaining <= 0:
            break

        sleep_time = min(
            interval,
            max(0, remaining)
        )

        time.sleep(
            sleep_time
        )

    return last_members


# ======================================================================
# MAIN TC-STK-016
# ======================================================================

def run_tc_stk_016(
    connection=None,
    master_connection=None,
    master_ip=None,
    master_username=None,
    master_password=None,
    connection_type=None,
    **kwargs
):
    """
    TC-STK-016

    Flow:
        1. Verify existing stack / prepare stack
        2. Verify Unit-ID 1 MASTER
        3. Configure SNMP
        4. Save configuration
        5. Run SNMP Walk
        6. Observe stack
        7. Return PASS/FAIL
    """

    _print_header(
        f"{TEST_CASE_ID} - "
        f"{TEST_CASE_TITLE}"
    )

    # ------------------------------------------------------------------
    # Select connection object
    # ------------------------------------------------------------------

    if connection is None:
        connection = master_connection

    if connection is None:
        print()
        print(
            "No switch connection was provided."
        )
        print(
            "TC-STK-016 : FAIL"
        )
        return False

    # ------------------------------------------------------------------
    # STACK CHECK
    # ------------------------------------------------------------------

    print()
    print(
        "Checking current stack status..."
    )

    stack_ready = _configure_stack_if_required(
        connection
    )

    if not stack_ready:
        print()
        print(
            "Running stack was not available."
        )
        print(
            "TC-STK-016 : FAIL"
        )
        return False

    # ------------------------------------------------------------------
    # VERIFY STACK
    # ------------------------------------------------------------------

    stack_ok, members = _verify_stack(
        connection
    )

    if not stack_ok:
        print()
        print(
            "TC-STK-016 : FAIL"
        )
        return False

    # ------------------------------------------------------------------
    # ENSURE CONFIG MODE
    # ------------------------------------------------------------------

    _print_header(
        "PREPARING SNMP CONFIGURATION"
    )

    if not _ensure_config_mode(
        connection
    ):
        print()
        print(
            "Unable to enter configuration mode."
        )
        print(
            "TC-STK-016 : FAIL"
        )
        return False

    # ------------------------------------------------------------------
    # SNMP CONFIGURATION
    # ------------------------------------------------------------------

    snmp_config = _configure_snmp(
        connection
    )

    if not snmp_config:
        print()
        print(
            "SNMP configuration failed."
        )
        print(
            "TC-STK-016 : FAIL"
        )
        return False

    snmp_community = snmp_config.get(
        "community"
    )

    snmp_ip = snmp_config.get(
        "nms_ip"
    )

    # ------------------------------------------------------------------
    # SAVE CONFIGURATION
    # ------------------------------------------------------------------

    _save_snmp_configuration(
        connection
    )

    # ------------------------------------------------------------------
    # SNMP WALK
    # ------------------------------------------------------------------

    _print_header(
        "SNMP WALK VERIFICATION"
    )

    snmp_walk_ok = _run_snmp_walk(
        default_ip=snmp_ip,
        default_community=snmp_community
    )

    if not snmp_walk_ok:
        print()
        print(
            "SNMP Walk verification failed."
        )

        print()
        print(
            "TC-STK-016 : FAIL"
        )

        return False

    # ------------------------------------------------------------------
    # STACK OBSERVATION
    # ------------------------------------------------------------------

    _observe_stack(
        connection,
        observation_seconds=60,
        interval=10
    )

    # ------------------------------------------------------------------
    # FINAL RESULT
    # ------------------------------------------------------------------

    _print_header(
        "TC-STK-016 RESULT"
    )

    print()
    print(
        "SNMP configuration completed."
    )

    print(
        "SNMP Walk verification completed."
    )

    print(
        f"At least "
        f"{SNMP_WALK_REQUIRED_ENTRIES} "
        f"valid OID responses were received."
    )

    print()
    print(
        "TC-STK-016 : PASS"
    )

    return True


# ======================================================================
# SAFE TESTCASE ENTRY POINT
# ======================================================================

def run_test_case(
    connection=None,
    master_connection=None,
    **kwargs
):
    return run_tc_stk_016(
        connection=connection,
        master_connection=master_connection,
        **kwargs
    )


# ======================================================================
# DIRECT EXECUTION
# ======================================================================

if __name__ == "__main__":
    print()
    print("=" * 70)
    print(
        "TC-STK-016 - SNMP CONFIGURATION AND SNMP WALK"
        .center(70)
    )
    print("=" * 70)

    print()
    print(
        "This testcase is normally executed from main.py."
    )

    print(
        "A valid switch connection is required."
    )