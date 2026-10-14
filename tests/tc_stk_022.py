"""TC-STK-022: Startup Configuration Reset and Controller Election.

WARNING: This test deletes the startup configuration and reloads the stack.
Run only in a lab environment after confirming that the configuration can be
restored if required.
"""

import re
import time
from datetime import datetime

from connection import SwitchConnection

TEST_CASE_ID = "TC-STK-022"
TEST_CASE_TITLE = "Startup Configuration Reset and Controller Election"
COMMAND_TIMEOUT = 20
RECONNECT_INTERVAL = 5
RECONNECT_TIMEOUT = 600
STACK_POLL_INTERVAL = 15
STACK_RECOVERY_TIMEOUT = 600


def _print_header(text):
    print("\n" + "=" * 76)
    print(text.center(76))
    print("=" * 76)


def _clean_output(value):
    if value is None:
        return ""
    text = str(value)
    # Strip common terminal ANSI escape sequences.
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text).strip()


def _send(connection, command, timeout=COMMAND_TIMEOUT):
    """Send a CLI command using the existing SwitchConnection interface."""
    try:
        result = connection.send_command(command, timeout=timeout)
    except TypeError:
        result = connection.send_command(command)
    return _clean_output(result)


def _run_show(connection, commands):
    last_output = ""
    for command in commands:
        try:
            output = _send(connection, command)
            last_output = output
            lowered = output.lower()
            if output and not any(
                marker in lowered
                for marker in (
                    "invalid command", "unknown command", "unrecognized command",
                    "incomplete command", "ambiguous command", "syntax error"
                )
            ):
                return command, output
        except Exception as exc:
            last_output = f"Command error: {exc}"
    return commands[-1], last_output


def _is_command_error(output):
    lowered = (output or "").lower()
    return any(
        marker in lowered
        for marker in (
            "invalid command", "unknown command", "unrecognized command",
            "incomplete command", "ambiguous command", "syntax error",
            "permission denied", "not authorized", "failed"
        )
    )


def _close(connection):
    if connection is None:
        return
    for method_name in ("disconnect", "close"):
        method = getattr(connection, method_name, None)
        if callable(method):
            try:
                method()
                return
            except Exception:
                pass


def _connect(ip, username, password, connection_type):
    connection = SwitchConnection(
        connection_type=connection_type,
        ip=ip,
        username=username,
        password=password,
    )
    result = connection.connect()
    if result is False:
        _close(connection)
        return None
    return connection


def _normalise_config(output):
    """Remove common display-only lines; preserve configuration commands."""
    ignored_exact = {
        "", "!", "#", "end", "building configuration...",
        "current configuration:", "startup configuration:",
        "running configuration:", "no configuration present",
        "startup-config is empty", "running-config is empty",
    }
    lines = []
    for raw_line in (output or "").splitlines():
        line = raw_line.strip()
        low = line.lower()
        if low in ignored_exact:
            continue
        if low.startswith(("! last configuration change", "! nvr", "! generated")):
            continue
        lines.append(line)
    return lines


def _config_looks_default(output):
    """Conservative check for explicit empty/default configuration responses."""
    low = (output or "").lower()
    explicit_empty_markers = (
        "no configuration present",
        "startup-config is empty",
        "running-config is empty",
        "configuration is empty",
        "no startup configuration",
        "no saved configuration",
    )
    if any(marker in low for marker in explicit_empty_markers):
        return True
    lines = _normalise_config(output)
    if not lines:
        return True
    # A running-config often contains platform defaults even after reset. Do not
    # claim it is default merely because it contains only a few lines.
    return False


def _parse_roles(output):
    roles = {}
    for line in (output or "").splitlines():
        # Accept tables such as: 1  ...  Controller, Master, Backup, Member.
        match = re.match(r"^\s*(\d+)\s+(.+?)\s*$", line)
        if not match:
            continue
        unit_id = int(match.group(1))
        rest = match.group(2)
        role_match = re.search(
            r"\b(controller|master|backup|standby|member|slave)\b",
            rest,
            re.IGNORECASE,
        )
        if role_match:
            roles[unit_id] = role_match.group(1).upper()
    return roles


def _print_config_snapshot(title, output):
    print(f"\n--- {title} ---")
    print(output if output else "<No output returned>")


def _reconnect_until_ready(ip, username, password, connection_type, timeout):
    start = time.monotonic()
    attempt = 0
    while time.monotonic() - start < timeout:
        attempt += 1
        try:
            connection = _connect(ip, username, password, connection_type)
            if connection is not None:
                try:
                    _, stack_output = _run_show(
                        connection, ["do show stack", "show stack"]
                    )
                    if stack_output and not _is_command_error(stack_output):
                        return connection, time.monotonic() - start
                except Exception:
                    pass
                _close(connection)
        except Exception:
            pass
        elapsed = int(time.monotonic() - start)
        print(
            f"  Management access not ready (attempt {attempt}, "
            f"{elapsed}s elapsed). Retrying in {RECONNECT_INTERVAL}s..."
        )
        time.sleep(RECONNECT_INTERVAL)
    return None, time.monotonic() - start


def run_tc_stk_022(
    master_connection=None,
    connection=None,
    master_ip=None,
    master_username=None,
    master_password=None,
    connection_type=None,
    expected_members=None,
    switch_details=None,
    **kwargs,
):
    """Delete startup config, reload, verify defaults, and record election."""
    active_connection = master_connection or connection

    _print_header(f"{TEST_CASE_ID}: {TEST_CASE_TITLE}")
    print("WARNING: THIS TEST DELETES THE STARTUP CONFIGURATION AND RELOADS THE STACK.")
    print("Ensure this is a lab stack and that you can restore its configuration.")

    if active_connection is None:
        print("FAIL: No active MASTER connection was provided.")
        return False
    if not all((master_ip, master_username, master_password, connection_type)):
        print("FAIL: Missing Unit-1 management connection details.")
        return False

    confirm = input(
        "Type DELETE-STARTUP-CONFIG to confirm this destructive test: "
    ).strip()
    if confirm != "DELETE-STARTUP-CONFIG":
        print("Test cancelled. No configuration was changed.")
        return False

    # Step 1: Capture and compare the pre-test configuration snapshots.
    print("\n[STEP 1/5] Capture running-config and startup-config before reset")
    _, running_before = _run_show(
        active_connection,
        ["do show running-config", "show running-config"],
    )
    _, startup_before = _run_show(
        active_connection,
        ["do show startup-config", "show startup-config"],
    )
    _print_config_snapshot("RUNNING CONFIGURATION BEFORE RESET", running_before)
    _print_config_snapshot("STARTUP CONFIGURATION BEFORE RESET", startup_before)

    if not running_before or _is_command_error(running_before):
        print("FAIL: Could not reliably read running-config; refusing to delete startup-config.")
        return False
    if not startup_before or _is_command_error(startup_before):
        print("FAIL: Could not reliably read startup-config; refusing to continue.")
        return False

    running_lines = _normalise_config(running_before)
    startup_lines = _normalise_config(startup_before)
    configs_match = running_lines == startup_lines
    print("\nPre-test running-config/startup-config comparison: " +
          ("MATCH" if configs_match else "DIFFERENT"))
    if not configs_match:
        print("NOTE: The configurations differ. The captured outputs above are retained in this console for review.")
        proceed = input("Continue with destructive reset anyway? Type CONTINUE: ").strip()
        if proceed != "CONTINUE":
            print("Test cancelled before deleting startup-config.")
            return False

    # Step 2: Delete startup config. Abort if command fails.
    print("\n[STEP 2/5] Delete startup-config")
    try:
        delete_output = _send(active_connection, "delete startup-config")
        print(delete_output or "Command sent; switch returned no text.")
        if re.search(r"\b(confirm|continue|sure)\b|\[y/n\]|\(y/n\)|yes/no", delete_output, re.IGNORECASE):
            answer = _send(active_connection, "y")
            print(answer or "Confirmation response sent.")
            delete_output += "\n" + answer
    except Exception as exc:
        print(f"FAIL: Unable to execute delete startup-config: {exc}")
        return False

    if _is_command_error(delete_output):
        print("FAIL: Switch reported an error while deleting startup-config. Reload was not started.")
        return False

    delete_confirm = input(
        "If the switch confirms startup-config was deleted, type DELETED to reload: "
    ).strip()
    if delete_confirm != "DELETED":
        print("Reload cancelled. Please inspect the switch configuration manually.")
        return False

    # Step 3: Reload and time until management is available again.
    print("\n[STEP 3/5] Reload the stack and measure boot time")
    reload_start = time.monotonic()
    reload_wall_start = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Reload command start: {reload_wall_start}")
    try:
        reload_output = _send(active_connection, "do reload", timeout=COMMAND_TIMEOUT)
        print(reload_output or "Reload command sent; connection may close as reboot starts.")
        if _is_command_error(reload_output):
            # Some CLIs accept reload without the 'do' prefix from exec mode.
            print("'do reload' reported an error; trying 'reload'.")
            reload_output = _send(active_connection, "reload", timeout=COMMAND_TIMEOUT)
            print(reload_output or "Reload command sent.")
            if _is_command_error(reload_output):
                print("FAIL: Reload command failed. Check the switch manually.")
                return False
    except Exception as exc:
        # A dropped connection is expected when the switch starts rebooting.
        print(f"Connection/command ended during reload (may be expected): {exc}")

    _close(active_connection)
    print(f"Waiting for management access at {master_ip}...")
    recovered_connection, reconnect_elapsed = _reconnect_until_ready(
        master_ip,
        master_username,
        master_password,
        connection_type,
        RECONNECT_TIMEOUT,
    )
    boot_elapsed = time.monotonic() - reload_start
    print(f"\nMeasured time to successful management access: {boot_elapsed:.1f} seconds")
    if recovered_connection is None:
        print(f"FAIL: Could not reconnect within {RECONNECT_TIMEOUT} seconds.")
        print("Boot time: NOT MEASURED (management access did not recover).")
        return False

    # Step 4: Verify startup and running config after reboot.
    print("\n[STEP 4/5] Verify startup-config and running-config after reboot")
    _, startup_after = _run_show(
        recovered_connection,
        ["do show startup-config", "show startup-config"],
    )
    _, running_after = _run_show(
        recovered_connection,
        ["do show running-config", "show running-config"],
    )
    _print_config_snapshot("STARTUP CONFIGURATION AFTER RESET", startup_after)
    _print_config_snapshot("RUNNING CONFIGURATION AFTER RESET", running_after)

    startup_default = _config_looks_default(startup_after)
    running_default = _config_looks_default(running_after)
    print("\nStartup configuration explicit empty/default indication: " +
          ("YES" if startup_default else "NOT CONFIRMED"))
    print("Running configuration explicit empty/default indication: " +
          ("YES" if running_default else "NOT CONFIRMED"))
    print(
        "NOTE: Some switch OS versions display built-in defaults instead of an empty config. "
        "Review the full outputs above before confirming either state."
    )
    if not startup_default:
        startup_check = input(
            "After reviewing startup-config above, type DEFAULT if it is empty/default: "
        ).strip()
        startup_default = startup_check == "DEFAULT"
    if not running_default:
        running_check = input(
            "After reviewing running-config above, type DEFAULT if it is empty/default: "
        ).strip()
        running_default = running_check == "DEFAULT"

    # Step 5: Record the actual election and observe stack recovery.
    print("\n[STEP 5/5] Record controller election and stack recovery")
    stack_start = time.monotonic()
    stack_output = ""
    roles = {}
    expected = int(expected_members or len(switch_details or []) or 1)
    recovered = False
    while time.monotonic() - stack_start <= STACK_RECOVERY_TIMEOUT:
        _, stack_output = _run_show(
            recovered_connection,
            ["do show stack", "show stack"],
        )
        print("\n--- Current show stack output ---")
        print(stack_output or "<No output returned>")
        roles = _parse_roles(stack_output)
        if roles:
            print("Parsed role summary:")
            for unit_id in sorted(roles):
                print(f"  Unit {unit_id}: {roles[unit_id]}")
        if len(roles) >= expected and expected > 0:
            recovered = True
            break
        elapsed = int(time.monotonic() - stack_start)
        if elapsed + STACK_POLL_INTERVAL > STACK_RECOVERY_TIMEOUT:
            break
        print(f"Stack not yet fully visible. Checking again in {STACK_POLL_INTERVAL}s...")
        time.sleep(STACK_POLL_INTERVAL)

    controller_units = [
        unit_id for unit_id, role in roles.items()
        if role in ("CONTROLLER", "MASTER")
    ]
    backup_units = [
        unit_id for unit_id, role in roles.items()
        if role in ("BACKUP", "STANDBY")
    ]
    print("\nACTUAL ELECTION RESULT")
    print(f"Controller/Master Unit-ID(s): {controller_units or 'Not identified from output'}")
    print(f"Backup/Standby Unit-ID(s): {backup_units or 'Not identified from output'}")
    print(f"Units with parsed roles: {sorted(roles) if roles else 'No roles parsed'}")
    print(f"Expected stack members: {expected}")
    print(f"Stack recovery detected: {'YES' if recovered else 'NO'}")
    print(f"Stack observation time: {time.monotonic() - stack_start:.1f} seconds")

    # Return the newly established connection so main.py can keep it active.
    # The main menu's result consumer recognizes SwitchConnection instances.
    passed = bool(
        configs_match
        and startup_default
        and running_default
        and recovered
        and controller_units
    )
    if not configs_match:
        print("FAIL reason: Running-config and startup-config did not match before reset.")
    if not startup_default or not running_default:
        print("FAIL reason: Empty/default state could not be positively confirmed by command output.")
    if not recovered:
        print("FAIL reason: Expected stack members did not all return within the timeout.")
    if not controller_units:
        print("FAIL reason: Controller/Master election result could not be parsed.")
    print(f"\n{TEST_CASE_ID} RESULT: {'PASS' if passed else 'FAIL'}")
    # main.py treats a returned connection as successful; therefore return the
    # connection only when the testcase passed. On a failed test, close it and
    # return False; main.py will recover the management connection next cycle.
    if passed:
        return recovered_connection
    _close(recovered_connection)
    return False
