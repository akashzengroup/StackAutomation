import time
import re


# =========================================================
# TC-STK-015
# Maximum Supported VLANs + Forwarding + Synchronization
# =========================================================

TEST_CASE_ID = "TC-STK-015"

SHOW_STACK_COMMAND = "do show stack"
SHOW_VLAN_COMMAND = "do show vlan"
SHOW_LOG_COMMAND = "show logging"

DEFAULT_VLAN_START = 1

# Maximum number of pager continuations allowed
MAX_PAGER_PAGES = 500


# =========================================================
# PRINT HEADER
# =========================================================

def _print_header(title):

    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


# =========================================================
# SEND COMMAND
# =========================================================

def _send_command(connection, command):

    try:

        if connection is None:
            return ""

        if hasattr(connection, "send_command"):

            output = connection.send_command(
                command
            )

            if output is None:
                return ""

            return str(output)

        if hasattr(connection, "send"):

            output = connection.send(
                command
            )

            if output is None:
                return ""

            return str(output)

        if hasattr(connection, "execute"):

            output = connection.execute(
                command
            )

            if output is None:
                return ""

            return str(output)

    except Exception as e:

        print(
            f"Command execution error: {e}"
        )

    return ""


# =========================================================
# RUN COMMAND
# =========================================================

def _run_command(connection, command):

    print()
    print(f"[>] {command}")
    print()

    output = _send_command(
        connection,
        command
    )

    if output:
        print(output)

    return output


# =========================================================
# RUN PAGED COMMAND
#
# Handles:
#
# More: <space>, Quit: q or CTRL+Z, One line: <return>
#
# The switch requires SPACE to display the next page.
# =========================================================

def _run_paged_command(
    connection,
    command
):

    print()
    print(f"[>] {command}")
    print()

    # -----------------------------------------------------
    # First page
    # -----------------------------------------------------

    output = _send_command(
        connection,
        command
    )

    if output is None:
        output = ""

    output = str(output)

    complete_output = output

    page_count = 1

    # -----------------------------------------------------
    # Continue while pager is displayed
    # -----------------------------------------------------

    while re.search(
        r"More:\s*<space>",
        complete_output,
        re.IGNORECASE
    ):

        if page_count >= MAX_PAGER_PAGES:

            print()
            print(
                "WARNING: Maximum pager page limit reached."
            )

            break

        page_count += 1

        # -------------------------------------------------
        # Send SPACE to continue the output
        # -------------------------------------------------

        try:

            next_page = _send_command(
                connection,
                " "
            )

        except Exception as e:

            print()
            print(
                f"Pager continuation error: {e}"
            )

            break

        if next_page is None:
            next_page = ""

        next_page = str(next_page)

        if not next_page:

            break

        complete_output += "\n" + next_page

        # -------------------------------------------------
        # Safety check:
        # If the returned page is exactly the same and
        # still contains More, stop to avoid infinite loop.
        # -------------------------------------------------

        if next_page.strip() == output.strip():

            print()
            print(
                "WARNING: Pager returned duplicate output."
            )

            break

        output = next_page

    # -----------------------------------------------------
    # Remove pager text from final output
    # -----------------------------------------------------

    complete_output = re.sub(
        r"\r?\n?More:\s*<space>,\s*Quit:\s*q\s*or\s*CTRL\+Z.*",
        "",
        complete_output,
        flags=re.IGNORECASE
    )

    # -----------------------------------------------------
    # Remove excessive blank lines
    # -----------------------------------------------------

    complete_output = re.sub(
        r"\n{3,}",
        "\n\n",
        complete_output
    )

    print(complete_output)

    print()
    print(
        f"VLAN table output pages received: {page_count}"
    )

    return complete_output


# =========================================================
# PARSE STACK
# =========================================================

def _parse_stack_members(output):

    members = []

    if not output:
        return members

    pattern = re.compile(
        r"^\s*"
        r"(\d+)"
        r"\s+"
        r"([0-9A-Fa-f:]{17})"
        r"\s+"
        r"([A-Za-z_-]+)"
        r"(?:\s+.*)?$",
        re.IGNORECASE
    )

    for line in output.splitlines():

        match = pattern.match(
            line.strip()
        )

        if not match:
            continue

        try:

            unit_id = int(
                match.group(1)
            )

        except ValueError:

            continue

        if unit_id < 1 or unit_id > 64:
            continue

        if any(
            item["unit_id"] == unit_id
            for item in members
        ):

            continue

        members.append({
            "unit_id": unit_id,
            "mac": match.group(2),
            "role": match.group(3).lower()
        })

    return sorted(
        members,
        key=lambda x: x["unit_id"]
    )


# =========================================================
# GET MAX VLAN COUNT
# =========================================================

def _get_max_vlan_count():

    print()
    print("=" * 70)
    print("       MAXIMUM SUPPORTED VLAN COUNT")
    print("=" * 70)

    print()
    print(
        "Enter the maximum number of VLANs supported "
        "by your switch platform."
    )

    while True:

        value = input(
            "\nMaximum supported VLANs: "
        ).strip()

        try:

            count = int(value)

            if count <= 0:

                print(
                    "Enter a value greater than zero."
                )

                continue

            return count

        except ValueError:

            print(
                "Please enter a valid number."
            )


# =========================================================
# GET VLAN RANGE
# =========================================================

def _get_vlan_range(max_vlan_count):

    print()
    print("=" * 70)
    print("                  VLAN RANGE")
    print("=" * 70)

    print()
    print(
        "Enter the first VLAN ID."
    )

    while True:

        value = input(
            f"First VLAN ID [default {DEFAULT_VLAN_START}]: "
        ).strip()

        if not value:

            start_vlan = DEFAULT_VLAN_START

        else:

            try:

                start_vlan = int(value)

            except ValueError:

                print(
                    "Please enter a valid VLAN ID."
                )

                continue

        # -------------------------------------------------
        # VLAN ID validation
        # -------------------------------------------------

        if start_vlan < 1 or start_vlan > 4094:

            print(
                "VLAN ID must be between 1 and 4094."
            )

            continue

        end_vlan = (
            start_vlan
            + max_vlan_count
            - 1
        )

        if end_vlan > 4094:

            print()
            print(
                "The requested VLAN range exceeds VLAN ID 4094."
            )

            print(
                "Enter a lower starting VLAN ID."
            )

            continue

        return start_vlan, end_vlan


# =========================================================
# VERIFY VLAN IDS FROM OUTPUT
# =========================================================

def _vlan_present(output, vlan_id):

    if not output:
        return False

    # -----------------------------------------------------
    # VLAN table normally starts with:
    #
    # 1           1
    # 2           2
    # 3           3
    #
    # Match VLAN ID at the beginning of the line.
    # -----------------------------------------------------

    pattern = re.compile(
        rf"^\s*{vlan_id}\s+",
        re.IGNORECASE
    )

    for line in output.splitlines():

        if pattern.search(line):

            return True

    return False


# =========================================================
# ENTER CONFIGURATION MODE
# =========================================================

def _enter_config_mode(connection):

    print()
    print("[>] configure terminal")

    output = _send_command(
        connection,
        "configure terminal"
    )

    if output:

        print(output)

    if re.search(
        r"%\s*(unrecognized|invalid|incomplete)",
        output,
        re.IGNORECASE
    ):

        print()
        print(
            "Failed to enter configuration mode."
        )

        return False

    return True


# =========================================================
# CONFIGURE SINGLE VLAN
# =========================================================

def _configure_single_vlan(
    connection,
    vlan_id
):

    command = f"vlan {vlan_id}"

    output = _send_command(
        connection,
        command
    )

    if output:

        # -------------------------------------------------
        # VLAN 1 is internally reserved.
        # Do not treat this as a failure.
        # -------------------------------------------------

        if vlan_id == 1 and re.search(
            r"occupied\s+for\s+internal\s+usage",
            output,
            re.IGNORECASE
        ):

            print(
                " VLAN 1 is internally occupied; "
                "accepted."
            )

            return True

        # -------------------------------------------------
        # Detect command failure
        # -------------------------------------------------

        if re.search(
            r"%\s*(unrecognized|invalid|incomplete|error)",
            output,
            re.IGNORECASE
        ):

            print()
            print(output)

            return False

    return True


# =========================================================
# EXIT CONFIG MODE / SAVE
# =========================================================

def _save_configuration(connection):

    print()
    print(
        "[>] do write"
    )

    output = _send_command(
        connection,
        "do write"
    )

    if output:

        print(output)

    if re.search(
        r"%\s*(unrecognized|invalid|incomplete|error)",
        output,
        re.IGNORECASE
    ):

        print(
            "Configuration save FAILED."
        )

        return False

    print(
        "Configuration saved successfully."
    )

    print()
    print(
        "[>] end"
    )

    end_output = _send_command(
        connection,
        "end"
    )

    if end_output:

        print(end_output)

    return True


# =========================================================
# CONFIGURE MAXIMUM VLANS
# =========================================================

def _configure_maximum_vlans(
    connection,
    start_vlan,
    end_vlan
):

    total = (
        end_vlan
        - start_vlan
        + 1
    )

    print()
    print(
        f"Total VLANs to configure: {total}"
    )

    # =====================================================
    # ENTER CONFIG MODE ONLY ONCE
    # =====================================================

    if not _enter_config_mode(
        connection
    ):

        return False

    print()
    print(
        "Configuration mode entered."
    )

    print(
        "Configuring VLANs..."
    )

    completed = 0

    # =====================================================
    # CONFIGURE VLANs
    #
    # IMPORTANT:
    # configure terminal is NOT repeated.
    # =====================================================

    for vlan_id in range(
        start_vlan,
        end_vlan + 1
    ):

        print(
            f"\rConfiguring VLAN "
            f"{vlan_id} "
            f"({completed + 1}/{total})...",
            end="",
            flush=True
        )

        if not _configure_single_vlan(
            connection,
            vlan_id
        ):

            print()
            print()
            print(
                f"VLAN {vlan_id} configuration FAILED."
            )

            _save_configuration(
                connection
            )

            return False

        completed += 1

    print()

    print()
    print(
        "All requested VLANs processed successfully."
    )

    # =====================================================
    # SAVE CONFIGURATION
    # =====================================================

    print()
    print(
        "Saving configuration..."
    )

    if not _save_configuration(
        connection
    ):

        return False

    return True


# =========================================================
# VERIFY VLAN SYNC
# =========================================================

def _verify_vlan_sync(
    connection,
    vlan_ids
):

    print()
    print("=" * 70)
    print("              VERIFY VLAN SYNCHRONIZATION")
    print("=" * 70)

    print()
    print(
        "Reading complete VLAN table..."
    )

    print(
        "Pager handling is enabled."
    )

    # =====================================================
    # IMPORTANT:
    #
    # Use paged command handler so:
    #
    # More: <space>, Quit: q or CTRL+Z
    #
    # is automatically continued with SPACE.
    # =====================================================

    output = _run_paged_command(
        connection,
        SHOW_VLAN_COMMAND
    )

    if not output:

        print()
        print(
            "Unable to read VLAN table."
        )

        return False

    # =====================================================
    # VERIFY VLANs
    # =====================================================

    missing = []

    for vlan_id in vlan_ids:

        # -------------------------------------------------
        # VLAN 1 is internally reserved.
        # -------------------------------------------------

        if vlan_id == 1:

            if _vlan_present(
                output,
                vlan_id
            ):

                continue

            # VLAN 1 may be internally handled by the
            # switch, so do not mark it as missing.

            continue

        if not _vlan_present(
            output,
            vlan_id
        ):

            missing.append(
                vlan_id
            )

    # =====================================================
    # RESULT
    # =====================================================

    if missing:

        print()
        print(
            f"Missing VLANs: {len(missing)}"
        )

        if len(missing) <= 50:

            print(
                "Missing IDs:",
                ", ".join(
                    str(v)
                    for v in missing
                )
            )

        else:

            print(
                "First 50 missing IDs:",
                ", ".join(
                    str(v)
                    for v in missing[:50]
                )
            )

        return False

    print()
    print(
        "All configured VLAN IDs are "
        "present in the complete VLAN table."
    )

    print()
    print(
        f"Verified VLAN count: {len(vlan_ids)}"
    )

    return True


# =========================================================
# ASK FOR FORWARDING TEST
# =========================================================

def _forwarding_test():

    print()
    print("=" * 70)
    print("             VLAN FORWARDING TEST")
    print("=" * 70)

    print()
    print(
        "The script does not configure the Windows/Linux "
        "host NIC automatically."
    )

    print()
    print(
        "Connect the test hosts according to your "
        "stack/VLAN test topology."
    )

    print()
    print(
        "Verify that traffic can pass through the "
        "configured VLAN across the stack members."
    )

    print()

    result = input(
        "Did VLAN forwarding work successfully? (y/n): "
    ).strip().lower()

    return result in (
        "y",
        "yes"
    )


# =========================================================
# TC-STK-015
# =========================================================

def run_tc_stk_015(
    master_connection=None,
    connection=None,
    expected_members=None,
    member_count=None,
    **kwargs
):

    active_connection = (
        master_connection
        if master_connection is not None
        else connection
    )

    if active_connection is None:

        print()
        print(
            "ERROR: Unit-ID 1 / MASTER connection "
            "is not available."
        )

        return False

    _print_header(
        "       TC-STK-015 - MAXIMUM VLANS + FORWARDING"
    )

    # =====================================================
    # STEP 1
    # =====================================================

    print()
    print("STEP 1: Verify stack")

    stack_output = _run_command(
        active_connection,
        SHOW_STACK_COMMAND
    )

    stack_members = _parse_stack_members(
        stack_output
    )

    if not stack_members:

        print()
        print(
            "ERROR: Stack could not be detected."
        )

        return False

    print()
    print(
        f"Detected stack members: "
        f"{len(stack_members)}"
    )

    # =====================================================
    # STEP 2
    # =====================================================

    max_vlan_count = _get_max_vlan_count()

    start_vlan, end_vlan = _get_vlan_range(
        max_vlan_count
    )

    vlan_ids = list(
        range(
            start_vlan,
            end_vlan + 1
        )
    )

    # =====================================================
    # STEP 3
    # =====================================================

    print()
    print("=" * 70)
    print("STEP 3: Configure maximum supported VLANs")
    print("=" * 70)

    print()
    print(
        f"First VLAN : {start_vlan}"
    )

    print(
        f"Last VLAN  : {end_vlan}"
    )

    print(
        f"Total VLANs: {len(vlan_ids)}"
    )

    print()
    print(
        "The script will enter configuration mode only once."
    )

    print(
        "VLAN commands will then be entered directly."
    )

    print()
    print(
        "VLAN 1 is internally reserved by the switch "
        "and will be accepted as already present."
    )

    input(
        "\nPress ENTER to start VLAN configuration..."
    )

    configure_pass = _configure_maximum_vlans(
        active_connection,
        start_vlan,
        end_vlan
    )

    if not configure_pass:

        print()
        print(
            "TC-STK-015 : FAIL"
        )

        return False

    # =====================================================
    # STEP 4
    # =====================================================

    print()
    print("=" * 70)
    print("STEP 4: Verify VLAN synchronization")
    print("=" * 70)

    input(
        "\nPress ENTER after the stack has synchronized..."
    )

    sync_pass = _verify_vlan_sync(
        active_connection,
        vlan_ids
    )

    # =====================================================
    # STEP 5
    # =====================================================

    print()
    print("=" * 70)
    print("STEP 5: Verify VLAN forwarding")
    print("=" * 70)

    forwarding_pass = _forwarding_test()

    # =====================================================
    # STEP 6 - FINAL
    # =====================================================

    print()
    print("=" * 70)
    print("             TC-STK-015 RESULT")
    print("=" * 70)

    result = (
        configure_pass
        and sync_pass
        and forwarding_pass
    )

    print()

    print(
        "Maximum VLAN Configuration : "
        + (
            "PASS"
            if configure_pass
            else "FAIL"
        )
    )

    print(
        "VLAN Synchronization       : "
        + (
            "PASS"
            if sync_pass
            else "FAIL"
        )
    )

    print(
        "VLAN Forwarding            : "
        + (
            "PASS"
            if forwarding_pass
            else "FAIL"
        )
    )

    print()

    print(
        "TC-STK-015                 : "
        + (
            "PASS"
            if result
            else "FAIL"
        )
    )

    print()

    print(
        "Unit-ID 1 / MASTER connection "
        "remains active."
    )

    return result