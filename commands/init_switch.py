"""Initialise a new switch with scene-cycle configuration.

Commands for creating initial button configurations on switches that haven't been programmed yet.
"""

import click
import json
from models.utils import get_cache_controller


@click.command()
@click.argument('switch_name')
@click.option('-y', '--yes', is_flag=True, help='Skip confirmation prompts')
def init_switch_command(switch_name, yes):
    """Initialise a switch with basic scene-cycle configuration on all buttons.

    This creates the initial behaviour instance for a switch that hasn't been
    configured yet. Each button (1-4) will be set to scene-cycle mode with
    empty scene lists, ready for programming.

    Examples:
        uv run python hue_backup.py init-switch "The Sparkles"
    """
    controller = get_cache_controller()

    if not controller.connect():
        return

    click.secho(f"\n=== Initialising Switch ===\n", fg='cyan', bold=True)

    # Step 1: Find the device
    click.echo(f"Looking for switch: {switch_name}")
    devices = controller.get_devices()

    target_device = None
    for device in devices:
        device_name = device.get('metadata', {}).get('name', '')
        if switch_name.lower() in device_name.lower():
            target_device = device
            break

    if not target_device:
        click.secho(f"✗ Switch '{switch_name}' not found", fg='red')
        return

    device_id = target_device['id']
    device_name = target_device.get('metadata', {}).get('name', switch_name)
    model_id = target_device.get('product_data', {}).get('model_id', '')

    click.secho(f"✓ Found device: {device_name} ({model_id})", fg='green')

    # Step 2: Check if device already has a behaviour instance
    behaviours = controller.get_behaviour_instances()
    existing_behaviour = None
    for behaviour in behaviours:
        config = behaviour.get('configuration', {})
        if config.get('device', {}).get('rid') == device_id:
            existing_behaviour = behaviour
            break

    if existing_behaviour:
        click.secho(f"⚠ Switch already has a behaviour instance!", fg='yellow')
        click.echo(f"  Behaviour ID: {existing_behaviour['id']}")
        click.echo(f"  Name: {existing_behaviour.get('metadata', {}).get('name', 'Unknown')}")
        click.echo()
        click.echo("Use 'program-button' command to modify existing configuration.")
        return

    # Step 3: Get button service RIDs
    button_services = []
    for service in target_device.get('services', []):
        if service.get('rtype') == 'button':
            button_services.append(service['rid'])

    if len(button_services) < 4:
        click.secho(f"✗ Device has {len(button_services)} buttons, expected 4", fg='red')
        return

    click.echo(f"  Found {len(button_services)} button services")

    # Step 4: Find a room/zone for the 'where' field
    # Try to find what room the device is in
    rooms = controller.get_rooms()
    zones = controller.get_zones()

    device_room = None
    # Check rooms first
    for room in rooms:
        for service in room.get('services', []):
            if service.get('rid') == device_id:
                device_room = room
                break
        if device_room:
            break

    # If not in a room, check zones
    if not device_room:
        for zone in zones:
            for service in zone.get('services', []):
                if service.get('rid') == device_id:
                    device_room = zone
                    break
            if device_room:
                break

    if device_room:
        where_rid = device_room['id']
        where_rtype = device_room['type']
        where_name = device_room.get('metadata', {}).get('name', 'Unknown')
        click.echo(f"  Location: {where_name}")
    else:
        # Default to bridge_home if we can't find the room
        click.secho(f"  ⚠ Could not determine room, using bridge_home", fg='yellow')
        # We'll need to get bridge_home RID
        bridge_home_rid = None
        # Try to find bridge_home from existing behaviours
        for behaviour in behaviours:
            config = behaviour.get('configuration', {})
            where = config.get('where', [])
            if where and len(where) > 0:
                group = where[0].get('group', {})
                if group.get('rtype') == 'bridge_home':
                    bridge_home_rid = group.get('rid')
                    break

        if bridge_home_rid:
            where_rid = bridge_home_rid
            where_rtype = 'bridge_home'
        else:
            click.secho(f"✗ Could not determine location for switch", fg='red')
            return

    # Step 5: Build the behaviour instance configuration
    # Use the standard button control script ID
    script_id = "67d9395b-4403-42cc-b5f0-740b699d67c6"

    # Build buttons configuration - new format with button RIDs
    buttons_config = {}
    for i, button_rid in enumerate(button_services[:4], 1):
        # Create minimal scene-cycle configuration
        buttons_config[button_rid] = {
            "on_short_release": {
                "scene_cycle_extended": {
                    "slots": [],  # Empty slots - ready for scenes
                    "with_off": {
                        "enabled": False
                    }
                }
            },
            "where": [
                {
                    "group": {
                        "rid": where_rid,
                        "rtype": where_rtype
                    }
                }
            ]
        }

    # Build full behaviour configuration
    behaviour_config = {
        "script_id": script_id,
        "enabled": True,
        "configuration": {
            "device": {
                "rid": device_id,
                "rtype": "device"
            },
            "model_id": model_id,
            "where": [
                {
                    "group": {
                        "rid": where_rid,
                        "rtype": where_rtype
                    }
                }
            ],
            "buttons": buttons_config
        },
        "metadata": {
            "name": device_name
        }
    }

    # Step 6: Show summary and confirm
    click.echo(f"\n=== Summary ===\n")
    click.echo(f"Switch:   {device_name}")
    click.echo(f"Buttons:  {len(button_services)}")
    click.echo(f"Location: {where_name if device_room else 'Bridge Home'}")
    click.echo(f"\nEach button will be configured with:")
    click.echo(f"  • Scene cycle mode (empty, ready for programming)")

    if not yes:
        if not click.confirm("\nCreate initial switch configuration?"):
            click.echo("Cancelled.")
            return

    # Step 7: Create the behaviour instance
    click.echo(f"\nCreating behaviour instance...")

    new_behaviour_id = controller.create_behaviour_instance(behaviour_config)

    if new_behaviour_id:
        click.secho(f"\n✓ Switch initialised successfully!", fg='green', bold=True)
        click.echo(f"  Behaviour ID: {new_behaviour_id}")
        click.echo(f"\nNext steps:")
        click.echo(f"  1. Use 'program-button' to add scenes to each button")
        click.echo(f"  2. Use 'button-data' to verify configuration")
    else:
        click.secho(f"\n✗ Failed to create behaviour instance", fg='red', bold=True)
