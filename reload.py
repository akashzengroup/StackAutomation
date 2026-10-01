import threading
import time


# =========================================================
# SEND RELOAD TO ONE SWITCH
# =========================================================

def send_reload(connection, switch_number):

    try:

        print(
            f"\nSwitch {switch_number}: "
            "Sending 'do reload'..."
        )

        connection.shell.send(
            "do reload\n"
        )

        print(
            f"Switch {switch_number}: "
            "Reload command sent."
        )

        return True

    except Exception as e:

        print(
            f"Switch {switch_number}: "
            f"Reload failed: {e}"
        )

        return False


# =========================================================
# RELOAD ALL SWITCHES
# =========================================================

def reload_all_switches(switches):

    threads = []

    results = []

    lock = threading.Lock()

    def reload_worker(
        connection,
        switch_number
    ):

        result = send_reload(
            connection,
            switch_number
        )

        with lock:

            results.append(result)

    # -----------------------------------------------------
    # Start reload simultaneously
    # -----------------------------------------------------

    for index, connection in enumerate(
        switches,
        start=1
    ):

        thread = threading.Thread(

            target=reload_worker,

            args=(
                connection,
                index
            )
        )

        thread.start()

        threads.append(thread)

    # -----------------------------------------------------
    # Wait for all reload commands to be sent
    # -----------------------------------------------------

    for thread in threads:

        thread.join()

    # -----------------------------------------------------
    # Check result
    # -----------------------------------------------------

    return all(results)


# =========================================================
# WAIT AFTER RELOAD
# =========================================================

def wait_for_reboot(seconds):

    print(
        f"\nWaiting {seconds} seconds "
        "before checking Unit-ID 1..."
    )

    for remaining in range(
        seconds,
        0,
        -1
    ):

        print(
            f"\rWaiting: {remaining:02d} seconds",
            end="",
            flush=True
        )

        time.sleep(1)

    print(
        "\n"
    )