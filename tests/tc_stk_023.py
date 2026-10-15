"""TC-STK-023: Repeated Reload and Stack Unit-ID/Role Verification.

Reload the switch five times. After each reboot, verify the stack membership
and role using ``show stack`` and inspect ``show logging`` for boot evidence.
"""

import re
import time
from datetime import datetime

from tests.tc_stk_022 import (
    _close_connection,
    _connect_ssh,
    _is_cli_error,
    _ping,
    _send_raw,
    _try_reload,
)

TEST_CASE_ID = "TC-STK-023"
TEST_CASE_TITLE = "Repeated Reload and Stack Role Verification"
RELOAD_CYCLES = 5
REBOOT_TIMEOUT = 600
DOWN_DETECT_TIMEOUT = 120
RECONNECT_INTERVAL = 5
BOOT_STABILIZATION_SECONDS = 5
STACK_RECOVERY_TIMEOUT = 300
STACK_POLL_INTERVAL = 5


def _command_ok(output):
    return bool(output and not _is_cli_error(output) and "COMMAND TIMEOUT:" not in output
                and "COMMAND INCOMPLETE:" not in output and "PAGER ERROR:" not in output)


def _parse_stack_roles(output):
    """Extract Unit-ID -> role pairs from common show-stack table formats."""
    roles = {}
    if not output:
        return roles
    role_re = re.compile(r"\b(master|controller|backup|standby|member|active|slave)\b", re.I)
    for line in output.splitlines():
        # Unit IDs are normally printed as a leading numeric column or Unit <n>.
        unit_match = re.search(r"\bunit\s*[- ]?\s*(\d+)\b", line, re.I)
        if not unit_match:
            unit_match = re.match(r"\s*(\d+)\s+(?=\S)", line)
        if not unit_match:
            continue
        unit_id = int(unit_match.group(1))
        role_match = role_re.search(line)
        if role_match:
            role = role_match.group(1).lower()
            if role in ("controller", "active"):
                role = "master"
            elif role in ("standby", "slave"):
                role = "backup"
            roles[unit_id] = role
    return roles



def _wait_for_complete_stack(connection, expected_unit_ids, expected_roles, expected_count):
    """Poll show stack until every expected unit/role is visible or timeout."""
    deadline = time.monotonic() + STACK_RECOVERY_TIMEOUT
    last_output = ""
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        output = _send_raw(connection, "show stack")
        last_output = output or ""
        roles = _parse_stack_roles(last_output)
        ids = set(roles)
        count_ok = len(ids) == expected_count
        ids_ok = ids == expected_unit_ids
        roles_ok = roles == expected_roles
        print(
            f"Stack recovery poll {attempt}: units={sorted(ids)} "
            f"({len(ids)}/{expected_count}), roles={roles}"
        )
        if _command_ok(last_output) and count_ok and ids_ok and roles_ok:
            print("All expected stack members and roles are visible.")
            return last_output, roles, None
        print(
            f"Stack is not fully recovered yet; retrying in "
            f"{STACK_POLL_INTERVAL}s..."
        )
        time.sleep(STACK_POLL_INTERVAL)
    return last_output, _parse_stack_roles(last_output), (
        f"All expected stack members/roles did not appear within "
        f"{STACK_RECOVERY_TIMEOUT}s."
    )

def _boot_log_evidence(output):
    """Return matching real switch log lines that indicate a boot/restart."""
    if not output:
        return []
    patterns = re.compile(
        r"\b(boot(?:ing|ed)?|reboot(?:ing|ed)?|system\s+up|startup|initiali[sz](?:e|ation|ing)|"
        r"cold.?start|warm.?start|reset(?:ting)?|power.?on)\b",
        re.I,
    )
    return [line.strip() for line in output.splitlines() if patterns.search(line)]


def _print_command(label, command, output):
    print(f"\n[{label}] $ {command}")
    print(output if output else "<No output>")


def _wait_for_reboot_and_reconnect(ip, username, password, connection_type="ssh"):
    """Require an observed down state and then reconnect after the switch returns."""
    deadline = time.monotonic() + REBOOT_TIMEOUT
    down_deadline = min(deadline, time.monotonic() + DOWN_DETECT_TIMEOUT)
    down_seen = False
    while time.monotonic() < down_deadline:
        if not _ping(ip):
            down_seen = True
            print("Reboot detected: management IP is unreachable.")
            break
        print("Waiting for the switch to go down...")
        time.sleep(1)
    if not down_seen:
        return None, f"Switch did not become unreachable within {DOWN_DETECT_TIMEOUT}s."

    while time.monotonic() < deadline:
        if _ping(ip):
            print(f"Management IP is reachable; waiting {BOOT_STABILIZATION_SECONDS}s for services.")
            time.sleep(BOOT_STABILIZATION_SECONDS)
            # Try both supported default credentials on every SSH reconnect.
            # Order matters: admin/admin first, then admin/Quantum.
            credentials = [("admin", "admin"), ("admin", "Quantum")]
            errors = []
            for login_username, login_password in credentials:
                connection, error = _connect_ssh(ip, login_username, login_password)
                if connection is not None:
                    print(
                        f"SSH connection successful using username '{login_username}' "
                        f"and the {'admin' if login_password == 'admin' else 'Quantum'} password."
                    )
                    return connection, None
                errors.append(f"{login_username}/{'admin' if login_password == 'admin' else 'Quantum'}: {error}")
            print("SSH is not ready or authentication failed; " + " | ".join(errors))
        else:
            print("Waiting for the switch to return...")
        time.sleep(RECONNECT_INTERVAL)
    return None, f"Switch did not return with SSH access within {REBOOT_TIMEOUT}s."


def run_tc_stk_023(
    master_connection=None,
    connection=None,
    master_ip=None,
    master_username=None,
    master_password=None,
    connection_type="ssh",
    expected_members=None,
    switch_details=None,
    **kwargs,
):
    active = master_connection or connection
    ip = master_ip or kwargs.get("ip")
    username = master_username or kwargs.get("username") or kwargs.get("ssh_username")
    password = master_password if master_password is not None else kwargs.get("password", kwargs.get("ssh_password"))

    print("\n" + "=" * 76)
    print(f"{TEST_CASE_ID}: {TEST_CASE_TITLE}".center(76))
    print("=" * 76)
    print(f"This test performs {RELOAD_CYCLES} consecutive switch reloads.")
    print("After every boot, it verifies 'show stack' and checks 'show logging' for boot evidence.")

    if active is None or not ip or not username or password is None:
        print("FAIL: An active switch connection, management IP, username, and password are required.")
        return False
    if str(connection_type).lower() != "ssh":
        print("FAIL: TC-STK-023 currently requires SSH so it can reconnect after each reboot.")
        return False

    baseline_output = _send_raw(active, "show stack")
    _print_command("BASELINE", "show stack", baseline_output)
    if not _command_ok(baseline_output):
        print("FAIL: Unable to capture the initial stack state; no reload was performed.")
        return False
    baseline_roles = _parse_stack_roles(baseline_output)
    if not baseline_roles:
        print("FAIL: Could not identify Unit-ID/role rows in the initial 'show stack' output.")
        return False
    expected_roles = dict(baseline_roles)
    expected_unit_ids = set(baseline_roles)
    try:
        expected_count = int(expected_members) if expected_members is not None else len(expected_unit_ids)
    except (TypeError, ValueError):
        expected_count = len(expected_unit_ids)
    if expected_count < 1:
        expected_count = len(expected_unit_ids)
    if len(expected_unit_ids) != expected_count:
        print(
            f"WARNING: Baseline parsed {len(expected_unit_ids)} unit roles, "
            f"but expected_members={expected_count}. The test will use the "
            "baseline Unit-ID/role map and will require that exact set after boot."
        )
        expected_count = len(expected_unit_ids)
    print(f"Expected stack member count: {expected_count}")
    print(f"Baseline Unit-IDs detected: {sorted(expected_unit_ids)}")
    print(f"Baseline roles detected: {expected_roles}")

    results = []
    for cycle in range(1, RELOAD_CYCLES + 1):
        print("\n" + "-" * 76)
        print(f"RELOAD CYCLE {cycle}/{RELOAD_CYCLES} - {datetime.now():%Y-%m-%d %H:%M:%S}")
        reload_started = time.monotonic()
        try:
            reload_output = _try_reload(active)
        except Exception as exc:
            reload_output = f"SSH session closed while issuing reload: {exc}"
        _print_command(f"CYCLE {cycle}", "do reload", reload_output)

        if _is_cli_error(reload_output) or "COMMAND ERROR:" in (reload_output or ""):
            print(f"CYCLE {cycle}: FAIL - switch rejected the reload command.")
            results.append(False)
            break

        _close_connection(active)
        active = None
        active, reconnect_error = _wait_for_reboot_and_reconnect(ip, username, password)
        if active is None:
            print(f"CYCLE {cycle}: FAIL - {reconnect_error}")
            results.append(False)
            break

        print(
            f"Waiting for all {expected_count} expected stack members to appear "
            "in 'show stack' before continuing..."
        )
        stack_after, roles_after, stack_recovery_error = _wait_for_complete_stack(
            active, expected_unit_ids, expected_roles, expected_count
        )
        _print_command(f"CYCLE {cycle}", "show stack (final recovery state)", stack_after)
        stack_ok = stack_recovery_error is None and _command_ok(stack_after)
        ids_ok = set(roles_after) == expected_unit_ids and len(roles_after) == expected_count
        roles_ok = roles_after == expected_roles
        if stack_recovery_error:
            print(f"STACK RECOVERY FAIL: {stack_recovery_error}")
            print("Boot-log verification and further reloads are skipped for this cycle.")
            results.append(False)
            break

        log_after = _send_raw(active, "show logging")
        _print_command(f"CYCLE {cycle}", "show logging", log_after)
        log_ok = _command_ok(log_after)
        boot_lines = _boot_log_evidence(log_after)
        boot_ok = bool(boot_lines)
        if boot_lines:
            print("Boot/restart log evidence:")
            for line in boot_lines[-10:]:
                print(f"  {line}")
        else:
            print("No boot/restart evidence was found in 'show logging'.")

        elapsed = time.monotonic() - reload_started
        cycle_ok = stack_ok and ids_ok and roles_ok and log_ok and boot_ok
        print(f"Unit-ID set check : {'PASS' if ids_ok else 'FAIL'} (expected {sorted(expected_unit_ids)}, got {sorted(roles_after)})")
        print(f"Role check        : {'PASS' if roles_ok else 'FAIL'} (expected {expected_roles}, got {roles_after})")
        print(f"Boot log check    : {'PASS' if boot_ok else 'FAIL'}")
        print(f"Cycle duration    : {elapsed:.1f}s")
        print(f"CYCLE {cycle} RESULT: {'PASS' if cycle_ok else 'FAIL'}")
        results.append(cycle_ok)
        if not cycle_ok:
            break

    passed = len(results) == RELOAD_CYCLES and all(results)
    print("\n" + "=" * 76)
    print(f"{TEST_CASE_ID} SUMMARY")
    print(f"Passed cycles: {sum(results)}/{RELOAD_CYCLES}")
    print(f"{TEST_CASE_ID} RESULT: {'PASS' if passed else 'FAIL'}")
    print("=" * 76)
    # Return the replacement connection so main.py can retain the live session.
    return active if passed and active is not None else False
