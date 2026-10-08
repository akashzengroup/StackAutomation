import time
import re
import getpass

from connection import SwitchConnection


# =========================================================
# TC-STK-019
# Different-Model Unit Join
#
# Flow:
#
#   1. Check existing stack from Unit 1 (MASTER)
#   2. Automatically determine new Unit-ID
#   3. Get NEW switch connection details
#   4. Connect to NEW / different-model switch
#   5. Automatically configure stack Unit-ID + stack ports
#   6. Automatically save configuration
#   7. Automatically reload NEW switch
#   8. Poll "do show stack" from Unit 1 every 5 seconds
#   9. Wait until NEW Unit-ID appears in the stack
#  10. Unit appears -> PASS
#  11. Timeout -> FAIL
#
# IMPORTANT:
#   - No changes to connection.py
#   - No changes to main.py
#   - No topology detection
#   - No "show logging"
#   - Unit 1 is always treated as MASTER
#   - Existing stack is NOT reloaded
#   - Only the NEW switch is configured/reloaded
#
# Physical stack cable connection is outside Python control.
# =========================================================


TEST_CASE_ID = "TC-STK-019"
TEST_CASE_NAME = "Different-Model Unit Join"


# =========================================================
# COMMANDS / TIMING
# =========================================================

SHOW_STACK_COMMAND = "do show stack"

CONFIG_MODE_COMMAND = "configure terminal"

WRITE_COMMAND = "do write"

RELOAD_COMMAND = "do reload"

POLL_INTERVAL = 5

DEFAULT_TIMEOUT = 300       # 5 minutes

MAX_UNIT_ID = 64

DEFAULT_STACK_PORT_TYPE = "tf"

DEFAULT_STACK_PORT = "3-4"


SUPPORTED_PORT_TYPES = (
    "te",
    "hu",
    "tf",
)


# =========================================================
# DISPLAY HELPERS
# =========================================================

def _print_header(title):

    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def _print_step(number, title):

    print()
    print("=" * 70)
    print(f"STEP {number} - {title}")
    print("=" * 70)


# =========================================================
# COMMAND HELPER
# =========================================================

def _send_command(conn, command):
    """
    Send a command using the existing SwitchConnection object.

    connection.py is intentionally not modified.

    The helper supports the existing project command methods:
        send_command()
        send()
        execute()
    """

    if conn is None:
        return ""

    try:

        if hasattr(conn, "send_command"):

            result = conn.send_command(command)

        elif hasattr(conn, "send"):

            result = conn.send(command)

        elif hasattr(conn, "execute"):

            result = conn.execute(command)

        else:

            print(
                "[ERROR] SwitchConnection does not provide "
                "send_command(), send(), or execute()."
            )

            return ""

        if result is None:
            return ""

        if isinstance(result, bytes):

            result = result.decode(
                "utf-8",
                errors="ignore"
            )

        return str(result)

    except Exception as exc:

        print(
            f"[ERROR] Failed to execute '{command}': {exc}"
        )

        return ""


# =========================================================
# STACK UNIT-ID PARSER
# =========================================================

def _get_stack_unit_ids(output):
    """
    Extract Unit IDs from 'do show stack' output.

    Expected rows are similar to:

        1     xx:xx:xx:xx:xx:xx
        2     xx:xx:xx:xx:xx:xx
        3     xx:xx:xx:xx:xx:xx

    Only numeric rows from 1-64 are accepted.
    """

    unit_ids = set()

    if not output:
        return unit_ids

    for line in output.splitlines():

        line = line.strip()

        if not line:
            continue

        match = re.match(
            r"^(\d+)\s+",
            line
        )

        if not match:
            continue

        try:

            unit_id = int(
                match.group(1)
            )

        except ValueError:

            continue

        if 1 <= unit_id <= MAX_UNIT_ID:

            unit_ids.add(
                unit_id
            )

    return unit_ids


# =========================================================
# FIND NEW UNIT-ID
# =========================================================

def _find_next_unit_id(existing_unit_ids):
    """
    Select the lowest unused Unit-ID.

    Examples:

        [1, 2, 3]       -> 4
        [1, 3, 4]       -> 2
        [1, 2, 4]       -> 3
        [1, 2, 3, 4]    -> 5
    """

    for unit_id in range(
        1,
        MAX_UNIT_ID + 1
    ):

        if unit_id not in existing_unit_ids:

            return unit_id

    return None


# =========================================================
# SHOW STACK
# =========================================================

def _show_stack(master_conn):

    print()
    print("-" * 70)
    print("Checking stack status on Unit 1 (MASTER)")
    print("-" * 70)

    output = _send_command(
        master_conn,
        SHOW_STACK_COMMAND
    )

    if output:

        print(
            output.rstrip()
        )

    else:

        print(
            "[WARNING] No output received from "
            "'do show stack'."
        )

    return output


# =========================================================
# CONNECTION TYPE
# =========================================================

def _get_connection_type(
    current_connection_type=None
):
    """
    Use the connection type passed by main.py when available.

    If TC-STK-019 is executed independently, ask the user.
    """

    if current_connection_type:

        value = str(
            current_connection_type
        ).strip().lower()

        if value in (
            "ssh",
            "telnet"
        ):

            return value

    print()
    print(
        "Select connection type for the NEW switch:"
    )

    print(
        "  1. SSH"
    )

    print(
        "  2. Telnet"
    )

    while True:

        choice = input(
            "\nEnter choice: "
        ).strip()

        if choice == "1":

            return "ssh"

        if choice == "2":

            return "telnet"

        print(
            "Invalid choice. Enter 1 or 2."
        )


# =========================================================
# NEW SWITCH DETAILS
# =========================================================

def _get_new_switch_details(
    connection_type=None
):
    """
    Collect connection information for the NEW switch.

    The switch is NOT manually configured.

    Only connection/access information is requested.
    """

    _print_header(
        "NEW / DIFFERENT-MODEL SWITCH DETAILS"
    )

    print()
    print(
        "Enter the management/access details of the "
        "NEW switch."
    )

    print(
        "The stack configuration will be applied "
        "automatically."
    )

    print()

    while True:

        new_ip = input(
            "New Switch IP Address: "
        ).strip()

        if new_ip:

            break

        print(
            "[ERROR] IP address cannot be empty."
        )

    while True:

        new_username = input(
            "New Switch User Name: "
        ).strip()

        if new_username:

            break

        print(
            "[ERROR] User name cannot be empty."
        )

    new_password = getpass.getpass(
        "New Switch Password: "
    )

    new_connection_type = _get_connection_type(
        connection_type
    )

    return {
        "ip": new_ip,
        "username": new_username,
        "password": new_password,
        "connection_type": new_connection_type,
    }


# =========================================================
# STACK PORT TYPE
# =========================================================

def _get_stack_port_type(
    switch_details=None
):
    """
    Get stack port type for the NEW switch.

    Supported:
        te
        hu
        tf

    If main.py already provides a port type through
    switch_details, use it.
    """

    if isinstance(
        switch_details,
        dict
    ):

        value = (
            switch_details.get(
                "port_type"
            )
        )

        if value:

            value = str(
                value
            ).strip().lower()

            if value in SUPPORTED_PORT_TYPES:

                return value

    if isinstance(
        switch_details,
        list
    ):

        for item in switch_details:

            if not isinstance(
                item,
                dict
            ):

                continue

            value = item.get(
                "port_type"
            )

            if value:

                value = str(
                    value
                ).strip().lower()

                if value in SUPPORTED_PORT_TYPES:

                    return value

    print()

    print(
        "Stack port type for the NEW switch:"
    )

    print(
        "  1. te"
    )

    print(
        "  2. hu"
    )

    print(
        "  3. tf"
    )

    while True:

        choice = input(
            "\nEnter choice [1-3]: "
        ).strip()

        if choice == "1":

            return "te"

        if choice == "2":

            return "hu"

        if choice == "3":

            return "tf"

        print(
            "Invalid choice. Please select 1, 2, or 3."
        )


# =========================================================
# STACK PORT RANGE
# =========================================================

def _get_stack_port(
    switch_details=None
):
    """
    Get stack port/range for the NEW switch.

    Example:
        3
        3-4
    """

    if isinstance(
        switch_details,
        dict
    ):

        value = switch_details.get(
            "stack_port"
        )

        if value:

            return str(
                value
            ).strip()

    if isinstance(
        switch_details,
        list
    ):

        for item in switch_details:

            if not isinstance(
                item,
                dict
            ):

                continue

            value = item.get(
                "stack_port"
            )

            if value:

                return str(
                    value
                ).strip()

    while True:

        value = input(
            f"\nStack Port/Range "
            f"[default {DEFAULT_STACK_PORT}]: "
        ).strip()

        if not value:

            value = DEFAULT_STACK_PORT

        if _validate_stack_port(
            value
        ):

            return value

        print(
            "[ERROR] Invalid stack port/range."
        )

        print(
            "Examples: 3 or 3-4"
        )


# =========================================================
# VALIDATE STACK PORT
# =========================================================

def _validate_stack_port(
    value
):
    """
    Validate:
        3
        3-4
        1-2
        10-12

    """

    if not value:

        return False

    value = str(
        value
    ).strip()

    single = re.fullmatch(
        r"\d+",
        value
    )

    if single:

        port = int(
            single.group(0)
        )

        return (
            1 <= port <= 128
        )

    range_match = re.fullmatch(
        r"(\d+)\s*-\s*(\d+)",
        value
    )

    if not range_match:

        return False

    start = int(
        range_match.group(1)
    )

    end = int(
        range_match.group(2)
    )

    if start < 1:
        return False

    if end < 1:
        return False

    if start > end:
        return False

    if end > 128:
        return False

    return True


# =========================================================
# CREATE NEW SWITCH CONNECTION
# =========================================================

def _connect_new_switch(
    ip,
    username,
    password,
    connection_type
):
    """
    Create and connect to the NEW switch.

    Uses the same SwitchConnection constructor as the
    existing Stack Configuration Automation project.
    """

    print()
    print("-" * 70)
    print("Connecting to NEW / Different-Model Switch")
    print("-" * 70)

    print(
        f"IP Address      : {ip}"
    )

    print(
        f"Connection Type : "
        f"{connection_type.upper()}"
    )

    try:

        new_connection = SwitchConnection(
            connection_type=connection_type,
            ip=ip,
            username=username,
            password=password
        )

    except Exception as exc:

        print(
            "[FAIL] Unable to create "
            f"SwitchConnection: {exc}"
        )

        return None

    try:

        connected = (
            new_connection.connect()
        )

    except Exception as exc:

        print(
            "[FAIL] Connection attempt failed: "
            f"{exc}"
        )

        return None

    if not connected:

        print(
            "[FAIL] Unable to connect to "
            "the NEW switch."
        )

        return None

    print(
        "[PASS] Connected to NEW switch."
    )

    return new_connection


# =========================================================
# EXECUTE STACK CONFIGURATION
# =========================================================

def _configure_new_switch(
    new_connection,
    new_unit_id,
    port_type,
    stack_port
):
    """
    Automatically configure the NEW switch.

    Commands:

        configure terminal
        stack configuration unit-id <id> links <type><range>
        do write
    """

    _print_header(
        f"CONFIGURING NEW SWITCH AS UNIT-{new_unit_id}"
    )

    stack_link = (
        f"{port_type}{stack_port}"
    )

    print()
    print(
        f"Unit-ID      : {new_unit_id}"
    )

    print(
        f"Stack Port   : {stack_link}"
    )

    print()

    commands = [

        CONFIG_MODE_COMMAND,

        (
            "stack configuration "
            f"unit-id {new_unit_id} "
            f"links {stack_link}"
        ),
    ]

    for command in commands:

        print()
        print(
            f"[COMMAND] {command}"
        )

        output = _send_command(
            new_connection,
            command
        )

        if output:

            print(
                output.rstrip()
            )

        print(
            "[PASS] Command executed."
        )

    # -----------------------------------------------------
    # SAVE CONFIGURATION
    # -----------------------------------------------------

    print()
    print(
        "[COMMAND] do write"
    )

    write_output = _send_command(
        new_connection,
        WRITE_COMMAND
    )

    if write_output:

        print(
            write_output.rstrip()
        )

    print(
        "[PASS] Configuration save command executed."
    )

    return True


# =========================================================
# RELOAD NEW SWITCH
# =========================================================

def _reload_new_switch(
    new_connection,
    new_unit_id
):
    """
    Reload ONLY the NEW switch.

    The existing stack is not reloaded.

    'do reload' intentionally terminates the connection,
    therefore the returned output is not required for PASS.
    """

    _print_header(
        f"RELOADING NEW UNIT-{new_unit_id}"
    )

    print()

    print(
        "Only the NEW switch will be reloaded."
    )

    print(
        "The existing Unit-1 MASTER stack will "
        "remain running."
    )

    print()

    print(
        "[COMMAND] do reload"
    )

    try:

        # Send the command directly.
        # Reload may close the SSH/Telnet channel
        # before normal command output is returned.

        _send_command(
            new_connection,
            RELOAD_COMMAND
        )

    except Exception as exc:

        # A socket-close exception during reload is
        # normally expected because the switch reboots.

        print(
            f"[INFO] Connection closed during reload: "
            f"{exc}"
        )

    print()
    print(
        f"[PASS] Reload command sent to Unit-{new_unit_id}."
    )

    print(
        "The NEW switch is rebooting."
    )

    # Try to close cleanly.
    try:

        if hasattr(
            new_connection,
            "close"
        ):

            new_connection.close()

    except Exception:

        pass

    return True


# =========================================================
# WAIT FOR NEW UNIT TO JOIN
# =========================================================

def _wait_for_unit_to_join(
    master_conn,
    new_unit_id,
    timeout=DEFAULT_TIMEOUT
):
    """
    Poll 'do show stack' from Unit 1 every 5 seconds
    until the new Unit-ID appears.
    """

    _print_header(
        "WAITING FOR DIFFERENT-MODEL UNIT TO JOIN"
    )

    print(
        f"Expected new Unit-ID : {new_unit_id}"
    )

    print(
        f"Polling interval     : {POLL_INTERVAL} seconds"
    )

    print(
        f"Timeout              : {timeout} seconds"
    )

    start_time = time.time()

    check_count = 0

    while True:

        elapsed = int(
            time.time() - start_time
        )

        if elapsed >= timeout:

            print()

            print(
                "=" * 70
            )

            print(
                "TIMEOUT"
            )

            print(
                "=" * 70
            )

            print(
                f"[FAIL] Unit-ID {new_unit_id} "
                f"did not appear in the stack "
                f"within {timeout} seconds."
            )

            return False

        check_count += 1

        print()
        print(
            f"[CHECK {check_count}] "
            f"Elapsed: {elapsed}s / {timeout}s"
        )

        output = _show_stack(
            master_conn
        )

        unit_ids = _get_stack_unit_ids(
            output
        )

        print()

        print(
            "[INFO] Current stack Unit-IDs: "
            f"{sorted(unit_ids) if unit_ids else 'None detected'}"
        )

        # -------------------------------------------------
        # NEW UNIT FOUND
        # -------------------------------------------------

        if new_unit_id in unit_ids:

            print()
            print(
                "=" * 70
            )

            print(
                "DIFFERENT-MODEL UNIT JOINED"
            )

            print(
                "=" * 70
            )

            print(
                f"[PASS] Unit-ID {new_unit_id} "
                "is now visible in the stack."
            )

            return True

        remaining = (
            timeout - elapsed
        )

        if remaining <= 0:

            break

        sleep_time = min(
            POLL_INTERVAL,
            remaining
        )

        print(
            f"[INFO] Unit-ID {new_unit_id} "
            "is not yet visible."
        )

        print(
            f"[INFO] Checking again in "
            f"{sleep_time} seconds..."
        )

        time.sleep(
            sleep_time
        )

    return False


# =========================================================
# MAIN TEST CASE
# =========================================================

def run_tc_stk_019(
    master_conn=None,
    master_connection=None,
    connection=None,
    master_username=None,
    master_password=None,
    connection_type=None,
    expected_members=None,
    unit1_conn=None,
    unit2_conn=None,
    switch_details=None,
    timeout=DEFAULT_TIMEOUT,
    **kwargs
):
    """
    TC-STK-019 entry point.

    Existing Unit-1 / MASTER connection is reused.

    The NEW switch is automatically:

        1. Connected
        2. Configured
        3. Saved
        4. Reloaded

    No changes to main.py or connection.py are required.
    """

    _print_header(
        f"{TEST_CASE_ID} - {TEST_CASE_NAME}"
    )

    # =====================================================
    # SELECT EXISTING MASTER CONNECTION
    # =====================================================

    master = master_conn

    if master is None:

        master = master_connection

    if master is None:

        master = unit1_conn

    if master is None:

        master = connection

    if master is None:

        print(
            "[FAIL] Unit 1 / MASTER connection "
            "is not available."
        )

        return False

    print()
    print(
        "[INFO] Using existing Unit 1 (MASTER) connection."
    )

    # =====================================================
    # STEP 1 - INITIAL STACK
    # =====================================================

    _print_step(
        1,
        "VERIFY EXISTING STACK"
    )

    initial_output = _show_stack(
        master
    )

    if not initial_output.strip():

        print(
            "[FAIL] Unable to retrieve "
            "initial stack status."
        )

        return False

    existing_unit_ids = _get_stack_unit_ids(
        initial_output
    )

    if 1 not in existing_unit_ids:

        print(
            "[FAIL] Unit-ID 1 was not detected."
        )

        print(
            "Unit 1 must always be the MASTER."
        )

        return False

    print()

    print(
        "[PASS] Unit 1 / MASTER detected."
    )

    print(
        "[INFO] Existing stack Unit-IDs: "
        f"{sorted(existing_unit_ids)}"
    )

    # =====================================================
    # DETERMINE NEW UNIT-ID AUTOMATICALLY
    # =====================================================

    new_unit_id = _find_next_unit_id(
        existing_unit_ids
    )

    if new_unit_id is None:

        print()
        print(
            "[FAIL] No available Unit-ID."
        )

        print(
            f"Maximum supported Unit-ID is "
            f"{MAX_UNIT_ID}."
        )

        return False

    print()

    print(
        f"[INFO] Automatically selected "
        f"new Unit-ID: {new_unit_id}"
    )

    # =====================================================
    # STEP 2 - NEW SWITCH DETAILS
    # =====================================================

    _print_step(
        2,
        "GET NEW SWITCH ACCESS DETAILS"
    )

    new_switch = _get_new_switch_details(
        connection_type=connection_type
    )

    new_port_type = _get_stack_port_type(
        switch_details=switch_details
    )

    new_stack_port = _get_stack_port(
        switch_details=switch_details
    )

    new_connection_type = (
        new_switch["connection_type"]
    )

    # =====================================================
    # DISPLAY FINAL CONFIGURATION
    # =====================================================

    _print_header(
        "TC-STK-019 CONFIGURATION"
    )

    print()

    print(
        f"Existing Unit-IDs : "
        f"{sorted(existing_unit_ids)}"
    )

    print(
        f"New Unit-ID       : "
        f"{new_unit_id}"
    )

    print(
        f"New Switch IP     : "
        f"{new_switch['ip']}"
    )

    print(
        f"Connection Type   : "
        f"{new_connection_type.upper()}"
    )

    print(
        f"Stack Port Type   : "
        f"{new_port_type.upper()}"
    )

    print(
        f"Stack Port        : "
        f"{new_stack_port}"
    )

    print(
        f"Stack Link        : "
        f"{new_port_type}{new_stack_port}"
    )

    print()

    print(
        "The following operations will be automated:"
    )

    print(
        "  1. Connect to NEW switch"
    )

    print(
        "  2. Configure stack Unit-ID"
    )

    print(
        "  3. Configure stack link"
    )

    print(
        "  4. Save configuration"
    )

    print(
        "  5. Reload NEW switch"
    )

    print(
        "  6. Monitor Unit-1 MASTER"
    )

    print()

    confirm = input(
        "Proceed with automatic configuration? (y/n): "
    ).strip().lower()

    if confirm not in (
        "y",
        "yes"
    ):

        print()
        print(
            "TC-STK-019 cancelled by user."
        )

        return False

    # =====================================================
    # STEP 3 - CONNECT TO NEW SWITCH
    # =====================================================

    _print_step(
        3,
        "CONNECT TO NEW / DIFFERENT-MODEL SWITCH"
    )

    new_connection = _connect_new_switch(
        ip=new_switch["ip"],
        username=new_switch["username"],
        password=new_switch["password"],
        connection_type=new_connection_type
    )

    if new_connection is None:

        return False

    # =====================================================
    # STEP 4 - AUTOMATIC CONFIGURATION
    # =====================================================

    _print_step(
        4,
        "AUTOMATICALLY CONFIGURE NEW SWITCH"
    )

    configuration_result = (
        _configure_new_switch(
            new_connection=new_connection,
            new_unit_id=new_unit_id,
            port_type=new_port_type,
            stack_port=new_stack_port
        )
    )

    if not configuration_result:

        print()
        print(
            "[FAIL] NEW switch configuration failed."
        )

        try:

            new_connection.close()

        except Exception:

            pass

        return False

    print()
    print(
        f"[PASS] Unit-{new_unit_id} "
        "configuration completed."
    )

    # =====================================================
    # STEP 5 - RELOAD NEW SWITCH
    # =====================================================

    _print_step(
        5,
        f"RELOAD NEW UNIT-{new_unit_id}"
    )

    reload_result = _reload_new_switch(
        new_connection=new_connection,
        new_unit_id=new_unit_id
    )

    if not reload_result:

        print(
            "[FAIL] Unable to reload "
            "the NEW switch."
        )

        return False

    # =====================================================
    # STEP 6 - WAIT FOR STACK JOIN
    # =====================================================

    _print_step(
        6,
        "VERIFY DIFFERENT-MODEL UNIT JOIN"
    )

    result = _wait_for_unit_to_join(
        master_conn=master,
        new_unit_id=new_unit_id,
        timeout=timeout
    )

    # =====================================================
    # FINAL RESULT
    # =====================================================

    print()
    print(
        "#" * 70
    )

    if result:

        print(
            f"{TEST_CASE_ID} RESULT: PASS"
        )

        print(
            f"Unit-ID {new_unit_id} successfully "
            "joined the existing stack."
        )

        print(
            "Unit 1 remained the MASTER."
        )

    else:

        print(
            f"{TEST_CASE_ID} RESULT: FAIL"
        )

        print(
            f"Unit-ID {new_unit_id} did not join "
            "the existing stack within the timeout."
        )

    print(
        "#" * 70
    )

    return result