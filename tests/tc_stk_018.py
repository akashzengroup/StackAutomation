import time
import re


# =========================================================
# TC-STK-018
# Multiple Stack Link Failure / Recovery
#
# IMPORTANT:
#   - Does NOT use "show logging"
#   - Does NOT use old log comparison
#   - Does NOT use date/time filtering
#   - Does NOT detect topology
#   - Does NOT select any cable
#   - Uses the existing MASTER connection
#   - Reads live output sent by the switch
# =========================================================

TEST_CASE_ID = "TC-STK-018"
TEST_CASE_NAME = "Multiple Stack Link Failure / Recovery"

SHOW_STACK_LINK_COMMAND = "do show stack links"

# How long to listen for switch-generated event messages
LIVE_LOG_WAIT = 30

# Small delay between live-buffer reads
LIVE_READ_INTERVAL = 0.2


# =========================================================
# COMMAND HELPER
# =========================================================

def _send_command(connection, command, delay=2):
    """
    Use the existing connection object.

    No changes are made to connection.py.
    """

    if connection is None:
        print("[ERROR] Connection object is None.")
        return ""

    try:
        if hasattr(connection, "send_command"):
            output = connection.send_command(command)

        elif hasattr(connection, "execute"):
            output = connection.execute(command)

        elif hasattr(connection, "send"):
            output = connection.send(command)

        else:
            raise AttributeError(
                "Existing connection object does not support "
                "send_command(), execute(), or send()."
            )

        if output is None:
            output = ""

        if not isinstance(output, str):
            output = str(output)

        if delay:
            time.sleep(delay)

        return output

    except Exception as exc:
        print(f"[ERROR] Command failed: {command}")
        print(f"[ERROR] {exc}")
        return ""


# =========================================================
# SHOW STACK LINKS
# =========================================================

def _show_stack_links(connection, title):
    """
    Run do show stack links.

    No topology parsing is performed.
    """

    print()
    print("=" * 78)
    print(title)
    print("=" * 78)

    output = _send_command(
        connection,
        SHOW_STACK_LINK_COMMAND,
        delay=2
    )

    if output:
        print(output.rstrip())
    else:
        print("[WARNING] No output received.")

    print("=" * 78)
    print()


# =========================================================
# GET POSSIBLE LIVE CHANNEL
# =========================================================

def _get_live_channel(connection):
    """
    Try to locate an already-existing Paramiko-style
    SSH channel from the existing connection object.

    This does NOT create a new connection.
    """

    if connection is None:
        return None

    # Common direct channel attributes
    possible_names = [
        "channel",
        "ssh_channel",
        "shell",
        "shell_channel",
        "client_channel",
        "_channel",
        "_ssh_channel",
    ]

    for name in possible_names:

        try:
            channel = getattr(connection, name, None)

            if channel is None:
                continue

            if hasattr(channel, "recv_ready") and hasattr(
                channel, "recv"
            ):
                return channel

        except Exception:
            continue

    # Sometimes the SSH client owns the channel.
    possible_client_names = [
        "client",
        "ssh_client",
        "ssh",
        "_client",
        "_ssh",
    ]

    for client_name in possible_client_names:

        try:
            client = getattr(
                connection,
                client_name,
                None
            )

            if client is None:
                continue

            # Direct channel
            if (
                hasattr(client, "recv_ready")
                and hasattr(client, "recv")
            ):
                return client

            # Look for common shell/channel attributes
            for channel_name in possible_names:

                channel = getattr(
                    client,
                    channel_name,
                    None
                )

                if (
                    channel is not None
                    and hasattr(channel, "recv_ready")
                    and hasattr(channel, "recv")
                ):
                    return channel

        except Exception:
            continue

    return None


# =========================================================
# READ LIVE OUTPUT
# =========================================================

def _read_live_output(connection, wait_time=LIVE_LOG_WAIT):
    """
    Read unsolicited output already being sent by the switch.

    No "show logging" command is executed.

    The function only reads data that is already available
    on the existing connection/channel.
    """

    channel = _get_live_channel(connection)

    if channel is None:
        print()
        print(
            "[WARNING] Could not find a live SSH channel "
            "on the existing MASTER connection."
        )
        print(
            "[WARNING] No new switch output can be read "
            "without changing the existing connection."
        )
        print()
        return ""

    collected = []

    start_time = time.time()

    while (time.time() - start_time) < wait_time:

        try:
            if channel.recv_ready():

                data = channel.recv(65535)

                if not data:
                    break

                if isinstance(data, bytes):
                    data = data.decode(
                        "utf-8",
                        errors="replace"
                    )

                collected.append(data)

                # Print immediately exactly as received.
                print(data, end="", flush=True)

                # Continue listening.
                continue

        except Exception as exc:
            print()
            print(
                f"[WARNING] Error while reading live "
                f"switch output: {exc}"
            )
            break

        time.sleep(LIVE_READ_INTERVAL)

    return "".join(collected)


# =========================================================
# REMOVE ONLY OBVIOUS TERMINAL NOISE
# =========================================================

def _display_live_output(title, output):
    """
    Display the switch-generated output.

    The actual switch log text is not interpreted.

    This function is mainly useful when output was captured
    before it could be printed immediately.
    """

    print()
    print("=" * 78)
    print(title)
    print("=" * 78)

    if output:
        print(output.rstrip())

    else:
        print(
            "[INFO] No unsolicited switch output "
            "was received during the wait period."
        )

    print("=" * 78)
    print()


# =========================================================
# PROCESS ONE CABLE ACTION
# =========================================================

def _process_cable_action(
    connection,
    action_prompt,
    log_title,
    links_title
):
    """
    Process one cable disconnect/reconnect.

    Flow:

        User performs action
              ↓
        Existing MASTER connection
              ↓
        Read live switch output
              ↓
        Print it immediately
              ↓
        Show stack links
    """

    print()
    print("-" * 78)
    print(action_prompt)
    print("-" * 78)

    input(
        "Press ENTER immediately after completing "
        "the cable action..."
    )

    print()
    print(
        "[INFO] Listening for switch-generated "
        "messages..."
    )
    print()

    # -----------------------------------------------------
    # IMPORTANT:
    # No "show logging" here.
    # No timestamp comparison.
    # No old-log processing.
    # -----------------------------------------------------

    live_output = _read_live_output(
        connection,
        wait_time=LIVE_LOG_WAIT
    )

    # If output was already printed live, this section
    # only displays a status heading when necessary.
    if not live_output:
        _display_live_output(
            log_title,
            live_output
        )
    else:
        print()
        print("=" * 78)
        print(log_title)
        print("=" * 78)
        print("[INFO] Switch event output captured above.")
        print("=" * 78)

    # -----------------------------------------------------
    # Show current stack links
    # -----------------------------------------------------

    _show_stack_links(
        connection,
        links_title
    )

    return live_output


# =========================================================
# MAIN TEST CASE
# =========================================================

def run_tc_stk_018(
    master_connection=None,
    connection=None,
    master_username=None,
    master_password=None,
    username=None,
    password=None,
    connection_type=None,
    expected_members=4,
    **kwargs
):
    """
    TC-STK-018
    Multiple Stack Link Failure / Recovery

    No changes to connection.py are required.
    No changes to main.py are required.
    """

    print()
    print("=" * 78)
    print(f"{TEST_CASE_ID} - {TEST_CASE_NAME}")
    print("=" * 78)

    # =====================================================
    # CONNECTION
    # =====================================================

    test_connection = (
        master_connection
        or connection
    )

    if test_connection is None:
        print()
        print("[FAIL] No MASTER switch connection available.")
        print()
        return False

    print()
    print("[INFO] Using existing MASTER connection.")
    print("[INFO] No additional connection will be created.")
    print()

    # =====================================================
    # STEP 1
    # INITIAL STACK LINKS
    # =====================================================

    print("=" * 78)
    print("STEP 1 - INITIAL STACK LINK STATUS")
    print("=" * 78)

    _show_stack_links(
        test_connection,
        "INITIAL STACK LINKS"
    )

    # =====================================================
    # STEP 2
    # FIRST CABLE DISCONNECT
    # =====================================================

    print("=" * 78)
    print("STEP 2 - FIRST STACK CABLE DISCONNECT")
    print("=" * 78)

    _process_cable_action(
        connection=test_connection,

        action_prompt=(
            "Please disconnect ANY ONE stack cable."
        ),

        log_title=(
            "LIVE SWITCH OUTPUT - FIRST CABLE DISCONNECT"
        ),

        links_title=(
            "STACK LINKS AFTER FIRST CABLE DISCONNECT"
        )
    )

    # =====================================================
    # STEP 3
    # SECOND CABLE DISCONNECT
    # =====================================================

    print("=" * 78)
    print("STEP 3 - SECOND STACK CABLE DISCONNECT")
    print("=" * 78)

    _process_cable_action(
        connection=test_connection,

        action_prompt=(
            "Please disconnect ANY ONE remaining "
            "stack cable."
        ),

        log_title=(
            "LIVE SWITCH OUTPUT - SECOND CABLE DISCONNECT"
        ),

        links_title=(
            "STACK LINKS AFTER SECOND CABLE DISCONNECT"
        )
    )

    # =====================================================
    # STEP 4
    # FIRST CABLE RECONNECT
    # =====================================================

    print("=" * 78)
    print("STEP 4 - FIRST STACK CABLE RECONNECT")
    print("=" * 78)

    _process_cable_action(
        connection=test_connection,

        action_prompt=(
            "Please reconnect ANY ONE disconnected "
            "stack cable."
        ),

        log_title=(
            "LIVE SWITCH OUTPUT - FIRST CABLE RECONNECT"
        ),

        links_title=(
            "STACK LINKS AFTER FIRST CABLE RECONNECT"
        )
    )

    # =====================================================
    # STEP 5
    # REMAINING CABLE RECONNECT
    # =====================================================

    print("=" * 78)
    print("STEP 5 - REMAINING STACK CABLE RECONNECT")
    print("=" * 78)

    _process_cable_action(
        connection=test_connection,

        action_prompt=(
            "Please reconnect the remaining "
            "disconnected stack cable."
        ),

        log_title=(
            "LIVE SWITCH OUTPUT - REMAINING CABLE RECONNECT"
        ),

        links_title=(
            "FINAL STACK LINKS AFTER RECOVERY"
        )
    )

    # =====================================================
    # FINAL RESULT
    # =====================================================

    print()
    print("=" * 78)
    print(f"{TEST_CASE_ID} - TEST COMPLETED")
    print("=" * 78)

    print()
    print(
        "[PASS] Multiple stack link failure/recovery "
        "process completed."
    )
    print()

    return True


# =========================================================
# OPTIONAL ALIAS
# =========================================================

run_test = run_tc_stk_018