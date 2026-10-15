<<<<<<< HEAD
"""TC-STK-022: Startup Configuration Reset and Controller Election.

Workflow:
1. show startup-config
2. show running-config
3. delete startup-config; automatically answer Y if prompted
4. do reload; automatically answer Y/Yes if prompted
5. wait for the switch to go down and return, then reconnect SSH
6. verify startup-config and running-config

WARNING: This is destructive. Run only on a lab switch with a recoverable backup.
"""

import contextlib
import io
import re
import subprocess
import time
from datetime import datetime

from connection import SwitchConnection

TEST_CASE_ID = "TC-STK-022"
TEST_CASE_TITLE = "Startup Configuration Reset and Controller Election"
COMMAND_TIMEOUT = 30
REBOOT_TIMEOUT = 600
RECONNECT_INTERVAL = 5
DOWN_DETECT_TIMEOUT = 120
BOOT_STABILIZATION_SECONDS = 5
CONFIG_DB_READY_TIMEOUT = 300
CONFIG_DB_RETRY_INTERVAL = 5

# Credentials expected after startup-config is deleted and the switch reboots.
POST_REBOOT_USERNAME = "admin"
POST_REBOOT_PASSWORD = "Quantum"


def _strip_ansi(value):
    if value is None:
        return ""
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", str(value))


def _clean_output(value, command=None):
    """Clean command echo/ANSI without hiding an active pager prompt."""
    text = _strip_ansi(value)
    # Keep pager markers until _send_raw has drained every page. Removing them
    # too early leaves the switch waiting for a space and corrupts the next CLI command.
    text = re.sub(r"(?m)^\s*" + re.escape(command or "\0") + r"\s*$", "", text) if command else text
    return text.strip()


def _read_channel_until_ready(shell, timeout=COMMAND_TIMEOUT, confirmation_aware=True):
    """Read one CLI response from Paramiko's interactive shell without losing prompts."""
    deadline = time.monotonic() + timeout
    chunks = []
    last_data_at = time.monotonic()
    pager_count = 0
    saw_data = False

    confirmation_re = re.compile(
        r"(?:\(\s*y\s*/\s*n\s*\)|\[\s*y\s*/\s*n\s*\]|\[\s*n\s*\]|"
        r"\byes/no\b|\by/n\b|\bconfirm(?:ation)?\s*\?)",
        re.I,
    )
    # Device prompts can be immediately followed by a syslog message on the same
    # line (for example ``console#15-Oct... %FILE-I-DELETE``). Match the prompt
    # token itself, not only a clean line ending in ``console#``.
    cli_prompt_re = re.compile(r"(?:^|[\r\n])\s*(?:console|switch|[\w.-]+)[>#]\s*(?=$|[\r\n]|\d{1,2}-[A-Za-z]{3}-|\d{4}-\d{2}-)", re.I | re.M)
    prompt_token_re = re.compile(r"(?:console|switch|[\w.-]+)[>#]", re.I)
    pager_re = re.compile(r"More:\s*<space>|--More--|Press any key to continue", re.I)

    while time.monotonic() < deadline:
        try:
            if shell.recv_ready():
                data = shell.recv(65535)
                if data:
                    text = data.decode("utf-8", errors="ignore") if isinstance(data, bytes) else str(data)
                    chunks.append(text)
                    saw_data = True
                    last_data_at = time.monotonic()
                    combined = "".join(chunks)

                    # Handle the switch's pager at the channel level. Never send the
                    # next CLI command while a More prompt is still active.
                    if pager_re.search(combined):
                        pager_count += 1
                        if pager_count > 200:
                            return combined + "\nPAGER ERROR: stopped after 200 pages.", False
                        # Remove the already-handled pager marker so the same marker
                        # does not trigger repeated spaces before the next page arrives.
                        combined = pager_re.sub("", combined)
                        chunks = [combined, "\n"]
                        shell.send(" ")
                        last_data_at = time.monotonic()
                        continue

                    if confirmation_aware and confirmation_re.search(combined):
                        # Give the prompt a short moment to finish printing, then return
                        # control to the caller so it can answer Y/Yes immediately.
                        time.sleep(0.15)
                        while shell.recv_ready():
                            extra = shell.recv(65535)
                            if not extra:
                                break
                            chunks.append(extra.decode("utf-8", errors="ignore") if isinstance(extra, bytes) else str(extra))
                        return "".join(chunks), True

                    if (cli_prompt_re.search(combined) or prompt_token_re.search(combined)) and time.monotonic() - last_data_at >= 0.15:
                        return combined, True
            else:
                combined = "".join(chunks)
                idle = time.monotonic() - last_data_at
                if saw_data and idle >= 0.6:
                    # A quiet channel with a prompt token is complete. Some firmware
                    # prints a syslog event immediately after ``console#`` without a
                    # newline, so do not require the prompt to be the last text.
                    if cli_prompt_re.search(combined) or prompt_token_re.search(combined):
                        return combined, True
                    # A delete may complete asynchronously and emit a definitive
                    # FILE-I-DELETE event without a separately readable prompt.
                    if re.search(r"%FILE-I-DELETE:.*startup-config", combined, re.I):
                        return combined, True
                    if idle >= 1.2:
                        return combined, False
                time.sleep(0.05)
        except Exception as exc:
            combined = "".join(chunks)
            if combined:
                return combined + f"\nCHANNEL READ WARNING: {exc}", False
            raise

    return "".join(chunks) + "\nCOMMAND TIMEOUT: no CLI prompt received.", False


def _send_raw(connection, command):
    """Send a single command through the interactive SSH shell and wait for its prompt.

    The project's generic send_command() only waits one second and cannot reliably
    handle interactive Y/N prompts. Use the underlying Paramiko shell when available.
    """
    shell = getattr(connection, "shell", None)
    if shell is not None and not getattr(shell, "closed", False):
        # Recover any leftover pager interaction before sending a new command.
        # If pending data contains a pager, advance it until the CLI prompt returns.
        try:
            pending = ""
            idle_start = time.monotonic()
            while time.monotonic() - idle_start < 0.25:
                if shell.recv_ready():
                    raw = shell.recv(65535)
                    if not raw:
                        break
                    pending += raw.decode("utf-8", errors="ignore") if isinstance(raw, bytes) else str(raw)
                    idle_start = time.monotonic()
                    if re.search(r"More:\s*<space>|--More--|Press any key to continue", pending, re.I):
                        shell.send(" ")
                        pending = ""
                else:
                    time.sleep(0.03)
            if pending and re.search(r"More:\s*<space>|--More--|Press any key to continue", pending, re.I):
                shell.send(" ")
                _read_channel_until_ready(shell, timeout=10)
        except Exception:
            # The actual command below will report a closed/broken channel.
            pass

        shell.send(command + "\n")
        raw_output, completed = _read_channel_until_ready(shell)
        output = _strip_ansi(raw_output)
        # Remove the command echo, but preserve configuration lines and any errors.
        output = re.sub(r"(?m)^\s*" + re.escape(command) + r"\s*$", "", output)
        output = "\n".join(line.rstrip() for line in output.splitlines()).strip()
        if not completed and "COMMAND TIMEOUT:" not in output and output:
            output += "\nCOMMAND INCOMPLETE: CLI prompt was not detected."
        if not output and completed:
            return "<CLI prompt returned; no command output>"
        return output

    # Compatibility fallback for non-SSH or older connection wrappers.
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured):
            try:
                returned = connection.send_command(command, timeout=COMMAND_TIMEOUT)
            except TypeError:
                returned = connection.send_command(command)
        output = _strip_ansi(returned) if returned is not None else _strip_ansi(captured.getvalue())
        return _clean_output(output, command)
    except Exception as exc:
        return f"COMMAND ERROR: {exc}"

def _print_command(step, total, command, title, output):
    print(f"\n[STEP {step}/{total}] {title}")
    print(f"[>] {command}")
    print(output if output else "<No output returned>")
    print("\n" + "-" * 76)


def _is_cli_error(output):
    text = (output or "").lower()
    return any(term in text for term in (
        "command error:", "invalid command", "unknown command",
        "unrecognized command", "incomplete command", "ambiguous command",
        "syntax error", "permission denied", "not authorized",
    ))


def _run_when_config_ready(connection, command, timeout=CONFIG_DB_READY_TIMEOUT):
    """Retry a read-only command while the switch configuration DB is locked.

    After SSH returns, Dsynch may still be initializing. A successful SSH login
    alone does not mean configuration commands are ready. Return the first
    response without the known database-lock message, or None on timeout.
    """
    deadline = time.monotonic() + timeout
    attempt = 0
    last_output = ""
    while time.monotonic() < deadline:
        attempt += 1
        try:
            output = _send_raw(connection, command)
        except Exception as exc:
            output = f"COMMAND ERROR: {exc}"
        last_output = output or ""
        if "configuration db locked by dsynch" not in last_output.lower():
            return last_output
        remaining = max(0, int(deadline - time.monotonic()))
        print(
            f"Configuration database is still locked by Dsynch; "
            f"retrying '{command}' in {CONFIG_DB_RETRY_INTERVAL}s "
            f"(attempt {attempt}, timeout in {remaining}s)."
        )
        time.sleep(min(CONFIG_DB_RETRY_INTERVAL, max(0, deadline - time.monotonic())))
    print(f"FAIL: Configuration database remained locked by Dsynch for {timeout}s.")
    print(f"Last response to '{command}': {last_output or '<no output>'}")
    return None


def _prepare_cli_for_long_output(connection):
    """Try common pager-disable commands before collecting long configurations.

    The switch CLI can leave the interactive channel at a pager prompt after
    show running-config. If that happens, the next command may be consumed as
    pager input (for example, producing ``console#startup-config``). Try the
    platform's common no-paging commands first; the first accepted command is
    enough. Unsupported variants are harmless and are not printed.
    """
    candidates = ("terminal length 0", "terminal datadump")
    for candidate in candidates:
        try:
            response = _send_raw(connection, candidate)
        except Exception:
            continue
        if response and not _is_cli_error(response):
            return candidate, response
    return None, "Could not confirm a supported pager-disable command."



def _looks_like_config_dump(output):
    """Return True when a command unexpectedly returned configuration lines.

    This is a strong sign that the previous long ``show running-config`` left
    the interactive CLI in its pager, so the next command was consumed as pager
    input rather than executed.
    """
    text = (output or "").lower()
    indicators = (
        "interface ", " ip address ", " no ip address", "hostname ",
        "vlan ", " spanning-tree", "router ", "snmp-server", "line ",
        "!\n", "version ", "boot system", "service ",
    )
    return sum(1 for marker in indicators if marker in text) >= 2


def _is_delete_confirmation(output):
    """Recognize the switch's optional/interactively formatted delete prompt."""
    text = (output or "").lower()
    return bool(
        re.search(r"delete\s+startup-config\s*\?", text)
        and re.search(r"(?:\(\s*y\s*/\s*n\s*\)|\[\s*y\s*/\s*n\s*\]|\[\s*n\s*\])", text)
    ) or bool(re.search(r"(?:y/n|yes/no).*?(?:startup|delete|configuration)|(?:startup|delete|configuration).*?(?:y/n|yes/no)", text, re.S))


def _drain_stale_cli_output(connection, max_pages=200):
    """Advance through any leftover pager output before retrying a command.

    A single space advances the switch's interactive ``More: <space>`` pager.
    Keep doing this only while the response still resembles configuration
    output; stop as soon as the pager has ended or the channel is quiet.
    """
    drained = []
    for _ in range(max_pages):
        try:
            page = _send_raw(connection, " ")
        except Exception:
            break
        if not page:
            break
        drained.append(page)
        if not _looks_like_config_dump(page):
            break
    return "\n".join(drained)


def _delete_startup_config_robustly(connection, startup_before=None):
    """Delete startup-config and handle confirmation only when the device asks.

    On this switch, the confirmation prompt is optional. Successful deletion can
    instead be reported asynchronously as ``%FILE-I-DELETE``. That event is treated
    as success even if the SSH wrapper does not separately return a clean prompt.
    """
    delete_output = _send_raw(connection, "delete startup-config")
    combined = delete_output or ""
    confirmation_re = re.compile(
        r"(?:delete\s+startup-config\s*\?|\(\s*y\s*/\s*n\s*\)|"
        r"\[\s*y\s*/\s*n\s*\]|\[\s*n\s*\]|\byes/no\b|\by/n\b|"
        r"are you sure|confirm(?:ation)?\s*\?|proceed\?)",
        re.I,
    )

    # Answer any number of actual prompts, but never send Y merely because the
    # command returned without one.
    response_to_check = delete_output or ""
    for _ in range(3):
        if not confirmation_re.search(response_to_check):
            break
        answer_output = _send_raw(connection, "Y")
        response_to_check = answer_output or ""
        combined += "\n" + response_to_check

    if _is_cli_error(combined) and not re.search(r"%FILE-I-DELETE:.*startup-config", combined, re.I):
        return False, delete_output, combined[len(delete_output):].strip(), "The delete command returned a CLI error."

    # The file-delete event is the authoritative success signal for the firmware
    # that emits it, even if the CLI prompt and event share a line.
    if re.search(r"%FILE-I-DELETE:.*startup-config", combined, re.I):
        _settle_cli_channel(connection, settle_seconds=0.5, max_wait=2.0)
        return True, delete_output, combined[len(delete_output):].strip(), "Switch confirmed deletion with %FILE-I-DELETE; no confirmation prompt was required (or any prompt was answered)."

    if "COMMAND TIMEOUT:" in combined or "COMMAND INCOMPLETE:" in combined:
        # Re-evaluate the live channel briefly: prompt/event can arrive after the
        # first quiet period. Do not resend the destructive command.
        late_output = _settle_cli_channel(connection, settle_seconds=0.5, max_wait=3.0)
        if late_output:
            combined += "\n" + late_output
            if re.search(r"%FILE-I-DELETE:.*startup-config", combined, re.I):
                return True, delete_output, combined[len(delete_output):].strip(), "Switch confirmed deletion with %FILE-I-DELETE after waiting for the asynchronous response."
            if _is_delete_confirmation(late_output):
                answer_output = _send_raw(connection, "Y")
                combined += "\n" + (answer_output or "")
                if re.search(r"%FILE-I-DELETE:.*startup-config", combined, re.I):
                    return True, delete_output, combined[len(delete_output):].strip(), "Delete confirmation answered and deletion event received."
        return False, delete_output, combined[len(delete_output):].strip(), "Delete command did not produce a success event or recoverable CLI prompt."

    if _is_delete_confirmation(combined):
        return False, delete_output, combined[len(delete_output):].strip(), "Confirmation prompt remained active after automatic Y handling."

    # For firmware that does not emit a delete event, require the command to
    # return to a prompt. Do not use show output as proof of deletion because it
    # may be stale output from the prior running-config command.
    if "<CLI prompt returned; no command output>" in combined or not combined.strip():
        return True, delete_output, "", "No confirmation prompt appeared; CLI returned to the prompt."
    if re.search(r"(?:^|[\r\n])\s*(?:console|switch|[\w.-]+)[>#]", combined, re.I):
        return True, delete_output, combined[len(delete_output):].strip(), "No confirmation prompt appeared; CLI prompt was recovered."
    return False, delete_output, combined[len(delete_output):].strip(), "Could not confirm delete completion from the CLI response."


def _settle_cli_channel(connection, settle_seconds=0.5, max_wait=2.0):
    """Collect delayed CLI/syslog text without sending a new command."""
    shell = getattr(connection, "shell", None)
    if shell is None or getattr(shell, "closed", False):
        return ""
    chunks = []
    deadline = time.monotonic() + max_wait
    last_data_at = time.monotonic()
    while time.monotonic() < deadline:
        try:
            if shell.recv_ready():
                data = shell.recv(65535)
                if not data:
                    break
                chunks.append(data.decode("utf-8", errors="ignore") if isinstance(data, bytes) else str(data))
                last_data_at = time.monotonic()
            elif time.monotonic() - last_data_at >= settle_seconds:
                break
            else:
                time.sleep(0.05)
        except Exception:
            break
    return _strip_ansi("".join(chunks)).strip()

def _ping(ip):
    try:
        result = subprocess.run(
            ["ping", "-n", "1", "-w", "1000", ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        return result.returncode == 0
    except Exception:
        return False


def _close_connection(connection):
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


def _connect_ssh(ip, username, password):
    """Create a fresh SSH connection using the project's SwitchConnection API."""
    last_error = None
    try:
        new_connection = SwitchConnection(
            connection_type="ssh",
            ip=ip,
            username=username,
            password=password,
        )
        result = new_connection.connect()
        if result is False:
            raise ConnectionError("SwitchConnection.connect() returned False")
        return new_connection, None
    except Exception as exc:
        last_error = exc
        return None, str(last_error)


def _try_reload(connection):
    """Issue reload and automatically answer Y/Yes only when prompted."""
    output = _send_raw(connection, "do reload")
    combined = output or ""
    confirmation_re = re.compile(
        r"(?:are you sure|confirm(?:ation)?|continue\?|\[\s*y\s*/\s*n\s*\]|"
        r"\(\s*y\s*/\s*n\s*\)|yes/no|proceed\?|reload\s+\?)",
        re.I,
    )
    response_to_check = output or ""
    for _ in range(3):
        if not confirmation_re.search(response_to_check):
            break
        response_to_check = _send_raw(connection, "Y") or ""
        combined += "\n" + response_to_check
        if _is_cli_error(response_to_check):
            break
    _settle_cli_channel(connection, settle_seconds=0.4, max_wait=1.5)
    return combined

def run_tc_stk_022(
    master_connection=None,
    connection=None,
    master_ip=None,
    master_username=None,
    master_password=None,
    connection_type=None,
    expected_members=None,
    switch_details=None,
    username=None,
    password=None,
    **kwargs,
):
    """Execute the startup-config reset, reload, and post-reboot verification."""
    active_connection = master_connection or connection
    ip = master_ip or kwargs.get("ip")
    ssh_username = master_username or username or kwargs.get("ssh_username")
    ssh_password = master_password or password or kwargs.get("ssh_password")

    print("\n" + "=" * 76)
    print(f"{TEST_CASE_ID}: {TEST_CASE_TITLE}".center(76))
    print("=" * 76)
    print("WARNING: THIS TEST DELETES STARTUP CONFIGURATION AND RELOADS THE SWITCH.")
    print("Make sure this is a lab switch and that its configuration can be restored.")

    if active_connection is None:
        print("FAIL: No active switch connection was provided.")
        return False
    if not ip or not ssh_username or ssh_password is None:
        print("FAIL: Management IP and SSH username/password are required for reconnection.")
        return False

    confirm = input("Type DELETE-STARTUP-CONFIG to confirm this destructive test: ").strip()
    if confirm != "DELETE-STARTUP-CONFIG":
        print("CANCELLED: No switch command was executed.")
        return False

    # Step 1: startup-config first, as requested.
    startup_before = _send_raw(active_connection, "show startup-config")
    _print_command(1, 6, "show startup-config", "Startup configuration before reset", startup_before)
    if not startup_before or _is_cli_error(startup_before):
        print("FAIL: Could not capture startup-config. Startup configuration was not deleted.")
        return False

    # Step 2: capture the complete running-config; _send_raw drains pager pages.
    running_before = _send_raw(active_connection, "show running-config")
    _print_command(2, 6, "show running-config", "Running configuration before reset", running_before)
    if not running_before or _is_cli_error(running_before) or "PAGER ERROR:" in running_before:
        print("FAIL: Could not capture the complete running-config. Startup configuration was not deleted.")
        print("The CLI output may still be paginated or the session may be out of sync. No delete or reload command was sent.")
        return False

    # Step 3: delete startup configuration. The prompt is optional on some
    # firmware builds, and stale pager output can hide it. Synchronize the CLI,
    # answer Y only when a prompt is detected (or use the safe no-prompt probe),
    # and require a clean verification before proceeding to reload.
    print("\n[STEP 3/6] Delete startup configuration")
    print("[>] delete startup-config")
    delete_ok, delete_output, delete_answer_output, delete_note = _delete_startup_config_robustly(
        active_connection, startup_before
    )
    print(delete_output if delete_output else "<No initial response; checking optional confirmation flow>")
    if delete_answer_output:
        print("[>] Confirmation/synchronization response")
        print(delete_answer_output)
    print(delete_note)
    print("\n" + "-" * 76)
    if not delete_ok:
        print("FAIL: Startup-config deletion could not be confirmed safely. Reload was not attempted.")
        print("The testcase stopped before reboot monitoring to avoid issuing reload in an unsynchronized CLI session.")
        return False

    # Step 4: reload. Timestamp immediately before issuing the reload command.
    reload_started = time.monotonic()
    reload_wall_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[STEP 4/6] Reload switch (started at {reload_wall_time})")
    print("[>] do reload")
    try:
        reload_output = _try_reload(active_connection)
    except Exception as exc:
        # A dropped SSH session during reload is normal, but only after the
        # switch accepted the reload. Other errors must stop the reboot wait.
        reload_output = f"SSH session closed while issuing reload: {exc}"
    print(reload_output if reload_output else "<No reload response returned>")
    if _is_cli_error(reload_output) or "COMMAND ERROR:" in (reload_output or ""):
        print("FAIL: The switch did not accept 'do reload'. Reboot monitoring was not started.")
        return active_connection
    if "SSH session closed while issuing reload:" in (reload_output or ""):
        # A connection drop can be the expected effect of an accepted reload.
        # Proceed to verify that the switch actually goes down.
        pass

    # Step 5: explicitly observe the switch go DOWN, then wait for it to come
    # UP before attempting SSH. This prevents an immediate SSH success from
    # being mistaken for a completed reboot.
    print(f"\n[STEP 5/6] Waiting for switch {ip} to go down and return (timeout {REBOOT_TIMEOUT}s)")
    _close_connection(active_connection)

    down_deadline = min(time.monotonic() + DOWN_DETECT_TIMEOUT, time.monotonic() + REBOOT_TIMEOUT)
    down_seen = False
    down_attempt = 0
    while time.monotonic() < down_deadline:
        down_attempt += 1
        if not _ping(ip):
            down_seen = True
            print(f"Switch is unreachable (reboot detected) after {time.monotonic() - reload_started:.1f}s.")
            break
        print(f"Waiting for switch to go down... check {down_attempt}: ping still UP.")
        time.sleep(1)

    if not down_seen:
        print(f"FAIL: Switch {ip} did not become unreachable within {DOWN_DETECT_TIMEOUT}s after reload.")
        print("SSH reconnection and post-reboot checks were not attempted because the reboot-down state was not observed.")
        return False

    reboot_deadline = reload_started + REBOOT_TIMEOUT
    up_attempt = 0
    while time.monotonic() < reboot_deadline and _ping(ip):
        up_attempt += 1
        print(f"Waiting for switch to come back... check {up_attempt}: ping still down.")
        time.sleep(RECONNECT_INTERVAL)

    if time.monotonic() >= reboot_deadline:
        print(f"FAIL: Switch did not become reachable within {REBOOT_TIMEOUT}s.")
        return False

    print(f"Ping response detected after {time.monotonic() - reload_started:.1f}s; allowing {BOOT_STABILIZATION_SECONDS}s for services to initialize.")
    time.sleep(BOOT_STABILIZATION_SECONDS)

    replacement = None
    last_connect_error = "not attempted yet"
    attempt = 0
    while time.monotonic() < reboot_deadline:
        attempt += 1
        if not _ping(ip):
            print(f"Post-boot check {attempt}: ping dropped again; waiting for the switch to stabilize.")
            time.sleep(RECONNECT_INTERVAL)
            continue
        print(f"Post-boot check {attempt}: ping UP; attempting SSH reconnect...")
        # Deleting startup-config restores the platform's default login. Use
        # these credentials for every post-reboot SSH attempt, not the pre-reset
        # password supplied by main.py.
        replacement, last_connect_error = _connect_ssh(
            ip, POST_REBOOT_USERNAME, POST_REBOOT_PASSWORD
        )
        if replacement is not None:
            break
        print(f"SSH not ready yet: {last_connect_error}")
        time.sleep(RECONNECT_INTERVAL)

    boot_seconds = time.monotonic() - reload_started
    print(f"Measured time from reload command to successful SSH reconnection: {boot_seconds:.1f} seconds")
    if replacement is None:
        print(f"FAIL: Switch did not return with usable SSH access within {REBOOT_TIMEOUT}s.")
        print(f"Last SSH error: {last_connect_error}")
        return False

    active_connection = replacement
    print(
        f"SSH reconnection successful using post-reboot credentials "
        f"{POST_REBOOT_USERNAME}/<password hidden>; post-reboot CLI checks can now begin."
    )

    # Step 6 is the SSH reconnection, reported explicitly after the wait loop.
    print("\n[STEP 5/6] Reconnected to switch over SSH")
    print(f"Management IP: {ip}")

    # Step 7: Dsynch can lock the configuration database after SSH becomes
    # available. Retry the read-only command until the lock clears, and print
    # only the successful response (never the transient lock messages as the
    # final configuration result).
    print(
        f"Waiting up to {CONFIG_DB_READY_TIMEOUT}s for the configuration "
        "database to become available..."
    )
    startup_after = _run_when_config_ready(active_connection, "show startup-config")
    if startup_after is None or not startup_after or _is_cli_error(startup_after):
        print("FAIL: Could not verify startup-config after reboot; configuration DB was not ready or CLI returned an error.")
        return active_connection
    _print_command(6, 6, "show startup-config", "Startup configuration after reboot", startup_after)

    # Step 8: apply the same readiness retry to running-config, as Dsynch may
    # re-lock the database between the two commands.
    running_after = _run_when_config_ready(active_connection, "show running-config")
    if running_after is None or not running_after or _is_cli_error(running_after) or "PAGER ERROR:" in running_after:
        print("FAIL: Could not verify running-config after reboot; configuration DB was not ready or CLI returned an error.")
        return active_connection
    _print_command(6, 6, "show running-config", "Running configuration after reboot", running_after)

    print("\n--- TC-STK-022 SUMMARY ---")
    print(f"Reload-to-SSH-ready time: {boot_seconds:.1f} seconds")
    print("Post-reboot startup-config: captured; review output for expected default state.")
    print("Post-reboot running-config: captured; review output for expected default state.")
    print("Controller election: record/verify using the platform's stack status command if this is a stack.")
    print("TC-STK-022 RESULT: PASS (reload, SSH recovery, and both post-reboot reads completed).")
    # Returning the live connection lets main.py retain the recovered SSH session.
    return active_connection
