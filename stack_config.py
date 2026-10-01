from config import SUPPORTED_PORT_TYPES


def configure_switch(
    connection,
    unit_id,
    port_type,
    stack_port
):

    print("\n" + "=" * 60)
    print(
        f"          CONFIGURING SWITCH {unit_id}"
    )
    print("=" * 60)

    # =====================================================
    # Validate port type
    # =====================================================

    port_type = port_type.lower().strip()

    if port_type not in SUPPORTED_PORT_TYPES:

        print(
            f"\nInvalid stack port type: {port_type}"
        )

        return False

    # =====================================================
    # Validate stack port
    # =====================================================

    stack_port = stack_port.strip()

    if not stack_port:

        stack_port = "1-2"

    # =====================================================
    # Generate stack command
    # =====================================================

    stack_command = (
        f"stack configuration "
        f"unit-id {unit_id} "
        f"links {port_type}{stack_port}"
    )

    commands = [
        "configure terminal",
        stack_command,
        "do write"
    ]

    # =====================================================
    # Display commands
    # =====================================================

    print("\nCommands:")

    for command in commands:

        print(
            f"  {command}"
        )

    # =====================================================
    # Execute
    # =====================================================

    try:

        connection.send_commands(
            commands
        )

        print(
            f"\nSwitch {unit_id} "
            "configuration completed."
        )

        return True

    except Exception as e:

        print(
            f"\nSwitch {unit_id} "
            f"configuration failed: {e}"
        )

        return False