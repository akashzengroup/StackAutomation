import re
import time

from connection import SwitchConnection


TEST_CASE_ID = "TC-STK-007"
TEST_CASE_TITLE = "Host Connectivity Through Stack Members"
COMMAND_SHOW_STACK = "sh stack"
COMMAND_PING = "ping"
COMMAND_TIMEOUT = 15


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


def _connect_switch(ip, username, password, connection_type, retries=3):
    for attempt in range(1, retries + 1):
        connection = SwitchConnection(
            connection_type=connection_type,
            ip=ip,
            username=username,
            password=password,
        )
        try:
            if connection.connect():
                return connection
        except Exception as exc:
            print(f"Connection attempt #{attempt} failed: {exc}")
        if attempt < retries:
            time.sleep(3)
    return None


def _clear_shell(shell):
    try:
        while shell.recv_ready():
            shell.recv(65535)
    except Exception:
        pass


def _get_command_output(connection, command, timeout=COMMAND_TIMEOUT):
    try:
        shell = getattr(connection, "shell", None)
        if shell is None:
            print("\nERROR: Master shell is not available.")
            return None

        _clear_shell(shell)
        print(f"\nExecuting on Unit-1 / MASTER: {command}")
        shell.send(command + "\n")

        output = ""
        start = time.time()
        last_data = start
        while time.time() - start < timeout:
            if shell.recv_ready():
                data = shell.recv(65535)
                if data:
                    chunk = data.decode("utf-8", errors="ignore")
                    output += chunk
                    print(chunk, end="", flush=True)
                    last_data = time.time()
            else:
                time.sleep(0.1)

            if output and time.time() - last_data >= 1.5:
                break

        return output
    except Exception as exc:
        print(f"\nCommand execution error: {exc}")
        return None


def _run_master_command(master_connection, command):
    output = _get_command_output(master_connection, command)
    if output is not None:
        return output
    return None


def _ping_passed(output):
    if not output:
        return False
    text = output.lower()
    if any(x in text for x in ("unreachable", "timeout", "timed out", "unknown host", "no route")):
        return False
    # Accept common QN/Linux-style successful ping indicators.
    return bool(re.search(r"(success|reply|bytes from|ttl=|0% packet loss|received\s*[1-9])", text))


def _ask_host_ip(test_name):
    while True:
        ip = input(f"Enter the host IP obtained/configured for {test_name}: ").strip()
        if ip:
            return ip
        print("Please enter a valid host IP address.")


def _user_assist(title, instructions):
    print()
    print("+" + "-" * 68 + "+")
    print(f"| USER ASSIST: {title:<54}|")
    print("+" + "-" * 68 + "+")
    for index, line in enumerate(instructions, 1):
        print(f"  {index}. {line}")
    input("\nPress ENTER after completing the above steps...")


def _verify_host_from_master(master_connection, host_ip, label):
    print(f"\nVerifying connectivity from Unit-1 / MASTER to {host_ip}...")
    output = _run_master_command(master_connection, f"{COMMAND_PING} {host_ip}")
    passed = _ping_passed(output)
    print()
    print(f"{label}: {'PASS' if passed else 'FAIL'}")
    print(f"Ping source: Unit-1 / MASTER")
    print(f"Ping destination: {host_ip}")
    return passed


def run_tc_stk_007(
    master_connection,
    master_ip,
    master_username,
    master_password,
    connection_type,
    expected_members=2,
    **kwargs,
):
    _print_header(f"{TEST_CASE_ID} - {TEST_CASE_TITLE}")

    print("\nObjective:")
    print("  1. Connect a host to a data port on the Master and verify DHCP + ping.")
    print("  2. Connect the same host to a data port on the Backup/Last Unit and verify DHCP + ping.")
    print("  3. Repeat the connectivity test using a Static IP.")
    print("\nImportant: The ping is always performed FROM Unit-1 / MASTER TO THE HOST.")

    # STEP 1
    _print_step(1, "VERIFY RUNNING STACK")
    stack_output = _run_master_command(master_connection, COMMAND_SHOW_STACK)
    if stack_output is None:
        _print_header(f"{TEST_CASE_ID} RESULT")
        print("FAIL\n✗ Unable to verify the running stack from Unit-1 / MASTER.")
        return False

    if not re.search(r"\b1\b.*(?:controller|master|active)", stack_output, re.IGNORECASE | re.DOTALL):
        print("\nWarning: Unit-1 Controller/Master was not clearly detected in output.")

    # STEP 2
    _print_step(2, "DHCP TEST - MASTER UNIT")
    _user_assist(
        "DHCP - MASTER PORT",
        [
            "Connect the host Ethernet cable to a DATA port on Master / Unit-1.",
            "Configure the host network adapter for DHCP / Obtain IP automatically.",
            "Confirm that the host has received an IP address.",
        ],
    )
    master_dhcp_ip = _ask_host_ip("DHCP on Master port")
    master_dhcp_ok = _verify_host_from_master(
        master_connection, master_dhcp_ip, "DHCP - Master Port"
    )

    # STEP 3
    _print_step(3, "DHCP TEST - BACKUP / LAST UNIT")
    _user_assist(
        "DHCP - BACKUP / LAST UNIT PORT",
        [
            "Disconnect the host Ethernet cable from the Master.",
            "Connect the same host cable to a DATA port on the Backup / Last Unit.",
            "Keep the host configured for DHCP and renew the DHCP address if required.",
            "Confirm that the host has received an IP address.",
        ],
    )
    backup_dhcp_ip = _ask_host_ip("DHCP on Backup/Last Unit port")
    backup_dhcp_ok = _verify_host_from_master(
        master_connection, backup_dhcp_ip, "DHCP - Backup/Last Unit Port"
    )

    # STEP 4
    _print_step(4, "STATIC IP TEST - MASTER UNIT")
    _user_assist(
        "STATIC IP - MASTER PORT",
        [
            "Connect the host Ethernet cable to a DATA port on Master / Unit-1.",
            "Configure the host with the required Static IP, subnet mask and gateway.",
            "Confirm that the static IP configuration is applied.",
        ],
    )
    master_static_ip = _ask_host_ip("Static IP on Master port")
    master_static_ok = _verify_host_from_master(
        master_connection, master_static_ip, "Static IP - Master Port"
    )

    # STEP 5
    _print_step(5, "STATIC IP TEST - BACKUP / LAST UNIT")
    _user_assist(
        "STATIC IP - BACKUP / LAST UNIT PORT",
        [
            "Disconnect the host Ethernet cable from the Master.",
            "Connect the same host cable to a DATA port on the Backup / Last Unit.",
            "Keep the same Static IP configuration on the host.",
        ],
    )
    backup_static_ip = _ask_host_ip("Static IP on Backup/Last Unit port")
    backup_static_ok = _verify_host_from_master(
        master_connection, backup_static_ip, "Static IP - Backup/Last Unit Port"
    )

    results = [
        master_dhcp_ok,
        backup_dhcp_ok,
        master_static_ok,
        backup_static_ok,
    ]

    _print_header(f"{TEST_CASE_ID} RESULT")
    print(f"DHCP - Master Port           : {'PASS' if master_dhcp_ok else 'FAIL'}")
    print(f"DHCP - Backup/Last Port      : {'PASS' if backup_dhcp_ok else 'FAIL'}")
    print(f"Static IP - Master Port       : {'PASS' if master_static_ok else 'FAIL'}")
    print(f"Static IP - Backup/Last Port  : {'PASS' if backup_static_ok else 'FAIL'}")
    print()
    print(f"Overall Result                : {'PASS' if all(results) else 'FAIL'}")
    print("\nMaster connection remains active.")
    return all(results)