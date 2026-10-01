import subprocess
import time

from connection import SwitchConnection


TEST_CASE_ID = "TC-STK-003"
TEST_CASE_TITLE = "Controller Failure / Backup Switchover"


# =========================================================
# HEADER
# =========================================================

def _print_header(title):

    print()
    print("=" * 70)
    print(f"{title:^70}")
    print("=" * 70)


# =========================================================
# STEP
# =========================================================

def _print_step(step, title):

    print()
    print("-" * 70)
    print(f"STEP {step}: {title}")
    print("-" * 70)


# =========================================================
# PING
# =========================================================

def _ping(ip):

    try:

        result = subprocess.run(
            [
                "ping",
                "-n",
                "1",
                "-w",
                "1000",
                ip
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        return result.returncode == 0

    except Exception:

        return False


# =========================================================
# WAIT FOR UNIT-2
# =========================================================

def _wait_for_unit2(
    unit2_ip,
    timeout=180
):

    print()
    print(
        f"Waiting for Unit-2 / Backup "
        f"({unit2_ip}) to come UP..."
    )

    start_time = time.time()

    while time.time() - start_time < timeout:

        if _ping(unit2_ip):

            print()
            print(
                f"Unit-2 ({unit2_ip}) is UP!"
            )

            return True

        elapsed = int(
            time.time() - start_time
        )

        print(
            f"\rWaiting for Unit-2... "
            f"{elapsed:03d}s",
            end="",
            flush=True
        )

        time.sleep(2)

    print()

    return False


# =========================================================
# COMMAND
# =========================================================

def _get_command_output(
    connection,
    command,
    timeout=10
):

    try:

        shell = connection.shell

        if shell is None:

            print(
                "\nERROR: SSH shell is not available."
            )

            return None

        # -------------------------------------------------
        # Clear pending output
        # -------------------------------------------------

        while shell.recv_ready():

            try:

                shell.recv(65535)

            except Exception:

                break

        # -------------------------------------------------
        # Send command
        # -------------------------------------------------

        print()
        print(
            f"Executing: {command}"
        )

        shell.send(
            command + "\n"
        )

        output = ""

        start = time.time()

        last_data = start

        while True:

            if shell.recv_ready():

                data = shell.recv(65535)

                if data:

                    chunk = data.decode(
                        "utf-8",
                        errors="ignore"
                    )

                    output += chunk

                    last_data = time.time()

            else:

                time.sleep(0.1)

            # -------------------------------------------------
            # Stop after output becomes idle
            # -------------------------------------------------

            if output:

                if (
                    time.time() - last_data
                    >= 1.0
                ):

                    break

            # -------------------------------------------------
            # Safety timeout
            # -------------------------------------------------

            if (
                time.time() - start
                >= timeout
            ):

                break

        return output

    except Exception as e:

        print(
            f"\nCommand execution error: {e}"
        )

        return None


# =========================================================
# VERIFY INITIAL ROLES
# =========================================================

def _verify_initial_roles(
    output
):

    if not output:

        return (
            False,
            "No output received from 'show stack'."
        )

    text = output.lower()

    unit1_controller = False
    unit2_backup = False

    for line in text.splitlines():

        parts = line.strip().split()

        if not parts:

            continue

        # -------------------------------------------------
        # Unit-1
        # -------------------------------------------------

        if parts[0] == "1":

            if "controller" in line:

                unit1_controller = True

        # -------------------------------------------------
        # Unit-2
        # -------------------------------------------------

        if parts[0] == "2":

            if "backup" in line:

                unit2_backup = True

    if not unit1_controller:

        return (
            False,
            "Unit-1 is not Controller."
        )

    if not unit2_backup:

        return (
            False,
            "Unit-2 is not Backup."
        )

    return (
        True,
        "Unit-1 is Controller and Unit-2 is Backup."
    )


# =========================================================
# VERIFY UNIT-2 BECAME CONTROLLER
# =========================================================

def _verify_unit2_controller(
    output
):

    if not output:

        return (
            False,
            "No output received from Unit-2."
        )

    text = output.lower()

    unit2_found = False
    unit2_controller = False

    for line in text.splitlines():

        parts = line.strip().split()

        if not parts:

            continue

        if parts[0] == "2":

            unit2_found = True

            if "controller" in line:

                unit2_controller = True

            elif "master" in line:

                unit2_controller = True

            elif "active" in line:

                unit2_controller = True

    if not unit2_found:

        return (
            False,
            "Unit-2 was not found in 'show stack'."
        )

    if not unit2_controller:

        return (
            False,
            "Unit-2 did not become Controller/Master."
        )

    return (
        True,
        "Unit-2 successfully became Controller/Master."
    )


# =========================================================
# TC-STK-003
# =========================================================

def run_tc_stk_003(
    unit1_ip,
    unit1_username,
    unit1_password,
    unit2_ip,
    unit2_username,
    unit2_password,
    connection_type,
    master_connection=None,
    wait_timeout=180
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
        "Verify that Unit-2 takes over as Controller "
        "when Unit-1 / Active Controller is powered OFF."
    )

    print()
    print("Expected Result:")

    print(
        "  - Unit-1 is initially Controller"
    )

    print(
        "  - Unit-2 is initially Backup"
    )

    print(
        "  - Unit-1 is powered OFF"
    )

    print(
        "  - Unit-2 becomes Controller/Master"
    )

    print(
        "  - Stack remains operational"
    )

    # =====================================================
    # STEP 1
    # =====================================================

    _print_step(
        1,
        "VERIFY UNIT-1 CONTROLLER / UNIT-2 BACKUP"
    )

    print()
    print(
        "Checking current stack roles from "
        "Unit-1 / Controller..."
    )

    # -----------------------------------------------------
    # Use the existing master connection if available.
    # -----------------------------------------------------

    connection = master_connection

    temporary_connection = None

    if connection is None:

        temporary_connection = SwitchConnection(

            connection_type=connection_type,

            ip=unit1_ip,

            username=unit1_username,

            password=unit1_password
        )

        print()

        if not temporary_connection.connect():

            _print_header(
                f"{TEST_CASE_ID} RESULT"
            )

            print()
            print("FAIL")
            print()
            print(
                "Unable to connect to Unit-1."
            )

            return False

        connection = temporary_connection

    output = _get_command_output(
        connection,
        "show stack"
    )

    if output is None:

        _print_header(
            f"{TEST_CASE_ID} RESULT"
        )

        print()
        print("FAIL")
        print()
        print(
            "Unable to execute 'show stack'."
        )

        return False

    print()
    print("=" * 70)
    print("                         SHOW STACK")
    print("=" * 70)
    print(output)
    print("=" * 70)

    roles_ok, roles_message = _verify_initial_roles(
        output
    )

    print()
    print(
        f"Role Verification: {roles_message}"
    )

    if not roles_ok:

        _print_header(
            f"{TEST_CASE_ID} RESULT"
        )

        print()
        print("FAIL")
        print()
        print(
            roles_message
        )

        return False

    print()
    print(
        "✓ Unit-1 is Controller"
    )

    print(
        "✓ Unit-2 is Backup"
    )

    # =====================================================
    # STEP 2
    # =====================================================

    _print_step(
        2,
        "POWER OFF UNIT-1 / ACTIVE CONTROLLER"
    )

    print()
    print("USER ASSISTANCE")
    print()

    print(
        "Please POWER OFF Unit-1 / Active Controller."
    )

    print()

    print(
        "Unit-1 IP:"
    )

    print(
        f"  {unit1_ip}"
    )

    print()

    print(
        "Unit-2 / Backup IP:"
    )

    print(
        f"  {unit2_ip}"
    )

    input(
        "\nPress ENTER after Unit-1 has been "
        "powered OFF..."
    )

    # =====================================================
    # STEP 3
    # =====================================================

    _print_step(
        3,
        "OBSERVE BACKUP SWITCHOVER"
    )

    print()
    print(
        "Unit-1 has been powered OFF."
    )

    print()
    print(
        "Now monitoring Unit-2..."
    )

    print(
        "Unit-2 will be pinged continuously "
        "until it becomes reachable."
    )

    print()

    unit2_up = _wait_for_unit2(
        unit2_ip,
        timeout=wait_timeout
    )

    if not unit2_up:

        _print_header(
            f"{TEST_CASE_ID} RESULT"
        )

        print()
        print("FAIL")
        print()

        print(
            f"Unit-2 did not come UP within "
            f"{wait_timeout} seconds."
        )

        print()
        print(
            "Master connection remains active."
        )

        return False

    # -----------------------------------------------------
    # Give the switch a little time to finish
    # role election before SSH verification.
    # -----------------------------------------------------

    print()
    print(
        "Unit-2 is reachable."
    )

    print(
        "Waiting for Controller election to stabilize..."
    )

    for remaining in range(10, 0, -1):

        print(
            f"\rChecking after switchover in "
            f"{remaining:02d} seconds...",
            end="",
            flush=True
        )

        time.sleep(1)

    print()
    print()

    # =====================================================
    # CONNECT TO UNIT-2
    # =====================================================

    print("=" * 70)
    print("              CONNECTING TO UNIT-2")
    print("=" * 70)

    unit2_connection = SwitchConnection(

        connection_type=connection_type,

        ip=unit2_ip,

        username=unit2_username,

        password=unit2_password
    )

    if not unit2_connection.connect():

        _print_header(
            f"{TEST_CASE_ID} RESULT"
        )

        print()
        print("FAIL")
        print()

        print(
            "Unit-2 is ping reachable, but SSH "
            "connection could not be established."
        )

        print()
        print(
            "Master connection remains active."
        )

        return False

    print()
    print(
        "Unit-2 SSH connection successful."
    )

    # =====================================================
    # SHOW STACK ON UNIT-2
    # =====================================================

    output = _get_command_output(
        unit2_connection,
        "show stack"
    )

    if output is None:

        try:
            unit2_connection.close()
        except Exception:
            pass

        _print_header(
            f"{TEST_CASE_ID} RESULT"
        )

        print()
        print("FAIL")
        print()
        print(
            "Unable to execute 'show stack' "
            "on Unit-2."
        )

        return False

    print()
    print("=" * 70)
    print("              UNIT-2 SHOW STACK")
    print("=" * 70)
    print(output)
    print("=" * 70)

    # =====================================================
    # VERIFY UNIT-2 CONTROLLER
    # =====================================================

    switchover_ok, switchover_message = (
        _verify_unit2_controller(output)
    )

    print()
    print(
        f"Switchover Verification: "
        f"{switchover_message}"
    )

    # =====================================================
    # RESULT
    # =====================================================

    _print_header(
        f"{TEST_CASE_ID} RESULT"
    )

    if switchover_ok:

        print()
        print("PASS")
        print()

        print(
            f"{TEST_CASE_ID} - "
            f"{TEST_CASE_TITLE}"
        )

        print()

        print(
            "✓ Unit-1 was initially Controller"
        )

        print(
            "✓ Unit-2 was initially Backup"
        )

        print(
            "✓ Unit-1 was powered OFF"
        )

        print(
            "✓ Unit-2 became reachable"
        )

        print(
            "✓ Unit-2 became Controller/Master"
        )

        print()

        print(
            "Unit-2 connection remains active."
        )

        print(
            "Master connection remains active."
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

    print(
        f"✗ {switchover_message}"
    )

    print()

    print(
        "Master connection remains active."
    )

    return False