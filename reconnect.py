import time

from connection import SwitchConnection


# =========================================================
# RECONNECT SINGLE SWITCH
# =========================================================

def reconnect_switch(
    switch_info,
    connection_type,
    switch_number,
    retries=5,
    retry_delay=10
):

    ip = switch_info["ip"]
    username = switch_info["username"]
    password = switch_info["password"]

    print("\n" + "=" * 60)
    print(
        f"              RECONNECT SWITCH {switch_number}"
    )
    print("=" * 60)

    for attempt in range(1, retries + 1):

        print(
            f"\nSwitch {switch_number} "
            f"({ip})"
        )

        print(
            f"Reconnect attempt "
            f"{attempt}/{retries}"
        )

        connection = SwitchConnection(
            connection_type=connection_type,
            ip=ip,
            username=username,
            password=password
        )

        if connection.connect():

            print(
                f"\nSwitch {switch_number} "
                "reconnected successfully."
            )

            return connection

        print(
            f"Switch {switch_number} "
            "is not reachable yet."
        )

        if attempt < retries:

            print(
                f"Waiting {retry_delay} seconds "
                "before next attempt..."
            )

            time.sleep(retry_delay)

    print("\n" + "-" * 60)

    print(
        f"Switch {switch_number} "
        "RECONNECT FAILED"
    )

    print("-" * 60)

    return None


# =========================================================
# RECONNECT ALL SWITCHES
# =========================================================

def reconnect_all_switches(
    switch_details,
    connection_type
):

    print("\n" + "=" * 60)
    print(
        "              RECONNECT PHASE"
    )
    print("=" * 60)

    reconnected_switches = []

    for switch_number, switch_info in enumerate(
        switch_details,
        start=1
    ):

        connection = reconnect_switch(
            switch_info=switch_info,
            connection_type=connection_type,
            switch_number=switch_number
        )

        if connection is None:

            print(
                f"\nSwitch {switch_number}: FAIL"
            )

            # Stop if one switch cannot reconnect

            return None

        reconnected_switches.append(
            connection
        )

        print(
            f"\nSwitch {switch_number}: PASS"
        )

    print("\n" + "=" * 60)
    print(
        "        ALL SWITCHES RECONNECTED"
    )
    print("=" * 60)

    return reconnected_switches