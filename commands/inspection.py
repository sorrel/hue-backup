"""
Inspection commands for viewing Hue setup - lights, scenes, switches, etc.

All inspection commands use cached data and can auto-reload stale cache.
"""

import click
import json
import traceback
from datetime import datetime
from models.utils import display_width, decode_button_event, create_name_lookup, get_cache_controller
from core.controller import HueController

# Button labels for wall controls (dimmers and dials)
BUTTON_LABELS = {
    1: 'ON',
    2: 'DIM UP',
    3: 'DIM DOWN',
    4: 'OFF',
    34: 'DIAL ROTATE',
    35: 'DIAL PRESS',
}

# Switch type emojis
SWITCH_EMOJIS = {
    'tap_dial': '🔘',   # Tap dial switch (rotary)
    'dimmer': '🎚️',    # Dimmer switch (rectangular, 4 buttons)
    'unknown': '🎛️',   # Unknown/generic switch
}


def get_switch_emoji(device_id: str, devices: list[dict]) -> str:
    """Get emoji for switch type based on device information.

    Args:
        device_id: Device ID to look up
        devices: List of device dictionaries from cache

    Returns:
        Emoji string for the switch type
    """
    if not device_id or not devices:
        return SWITCH_EMOJIS['unknown']

    # Find device by ID
    device = next((d for d in devices if d.get('id') == device_id), None)
    if not device:
        return SWITCH_EMOJIS['unknown']

    # Check product name or model ID
    product_data = device.get('product_data', {})
    product_name = product_data.get('product_name', '').lower()
    model_id = product_data.get('model_id', '')

    # Tap dial switch
    if 'tap dial' in product_name or model_id == 'RDM002':
        return SWITCH_EMOJIS['tap_dial']

    # Dimmer switch
    if 'dimmer' in product_name or model_id in ['RWL021', 'RWL022']:
        return SWITCH_EMOJIS['dimmer']

    # Unknown/generic
    return SWITCH_EMOJIS['unknown']


def format_timestamp(iso_timestamp: str) -> str:
    """Format ISO 8601 timestamp to UK format: DD/MM HH:MM"""
    if not iso_timestamp or iso_timestamp == 'N/A':
        return ''
    try:
        # Parse ISO 8601 format (e.g., "2025-12-17T14:30:45Z")
        dt = datetime.fromisoformat(iso_timestamp.replace('Z', '+00:00'))
        # Format as DD/MM HH:MM (24-hour clock, UK date format)
        return dt.strftime('%d/%m %H:%M')
    except (ValueError, AttributeError):
        return ''


@click.command()
@click.option('--room', '-r', help='Filter scenes by room name')
@click.option('--auto-reload/--no-auto-reload', default=True, help='Auto-reload stale cache (default: yes)')
def scene_details_command(room: str, auto_reload: bool):
    """Show detailed scene information from cache.

    Lists all scenes with their light configurations (brightness, colour
    temperature, on/off state). Uses cached data, automatically reloading
    if the cache is over 24 hours old.

    \b
    Examples:
      uv run python hue_backup.py scene-details              # All scenes
      uv run python hue_backup.py scene-details -r lounge    # Lounge scenes only
      uv run python hue_backup.py scene-details --no-auto-reload  # Don't auto-reload
    """
    cache_controller = get_cache_controller(auto_reload)
    if not cache_controller:
        return

    scenes = cache_controller.get_scenes()
    if not scenes:
        click.echo("No scenes found in cache. Run 'reload' to fetch data.")
        return

    # Get rooms and lights for lookups
    rooms_list = cache_controller.get_rooms()
    lights_list = cache_controller.get_lights()

    # Create lookups
    room_lookup = create_name_lookup(rooms_list)
    light_lookup = create_name_lookup(lights_list)

    # Get scene-to-switch mapping
    scene_mapping = cache_controller.get_scene_to_switch_mapping()

    # Filter by room if specified
    if room:
        room_lower = room.lower()
        filtered_scenes = []
        for scene in scenes:
            scene_room_rid = scene.get('group', {}).get('rid')
            scene_room_name = room_lookup.get(scene_room_rid, '')
            if room_lower in scene_room_name.lower():
                filtered_scenes.append(scene)
        scenes = filtered_scenes

    if not scenes:
        click.echo(f"No scenes found matching room '{room}'")
        return

    click.echo()
    click.secho(f"=== Scene Details ({len(scenes)} scenes) ===", fg='cyan', bold=True)
    if room:
        click.echo(f"Filtered by room: {room}")
    click.echo()

    for scene in scenes:
        scene_name = scene.get('metadata', {}).get('name', 'Unnamed')
        scene_room_rid = scene.get('group', {}).get('rid')
        scene_room = room_lookup.get(scene_room_rid, 'Unknown')

        click.secho(f"{scene_name} [{scene_room}]", fg='green', bold=True)
        scene_id = scene.get('id', 'Unknown')
        click.echo(f"  ID: {scene_id[:8]}...")

        # Show which switches this scene is programmed on
        if scene_id in scene_mapping:
            switch_assignments = scene_mapping[scene_id]
            click.secho(f"  Programmed on switches:", fg='bright_yellow')
            for assignment in switch_assignments:
                click.echo(f"    • {assignment['device_name']} - {assignment['button']} ({assignment['action']})")

        # Show actions (lights and their settings)
        actions = scene.get('actions', [])
        if actions:
            click.echo(f"  Lights ({len(actions)}):")
            for action in actions:
                light_rid = action.get('target', {}).get('rid')
                light_name = light_lookup.get(light_rid, 'Unknown')

                action_data = action.get('action', {})
                on_state = action_data.get('on', {}).get('on', None)
                brightness = action_data.get('dimming', {}).get('brightness', None)
                mirek = action_data.get('color_temperature', {}).get('mirek', None)
                colour = action_data.get('color', {})

                # Build action description
                desc_parts = []
                if on_state is not None:
                    desc_parts.append('ON' if on_state else 'OFF')
                if brightness is not None:
                    desc_parts.append(f"{brightness:.0f}%")
                if mirek is not None:
                    desc_parts.append(f"{mirek} mirek")
                if colour:
                    xy = colour.get('xy', {})
                    if xy:
                        desc_parts.append(f"colour xy({xy.get('x', 0):.2f}, {xy.get('y', 0):.2f})")

                desc = ', '.join(desc_parts) if desc_parts else 'No settings'
                click.echo(f"    • {light_name}: {desc}")
        else:
            click.echo("  No light actions defined")

        click.echo()


@click.command()
@click.option('--auto-reload/--no-auto-reload', default=True, help='Auto-reload stale cache (default: yes)')
def status_command(auto_reload: bool):
    """Get overall bridge status and configuration summary.

    Uses cached data, automatically reloading if the cache is over 24 hours old.
    """
    cache_controller = get_cache_controller(auto_reload)
    if not cache_controller:
        return

    try:
        click.echo("\n=== Bridge Status ===\n")

        # Count resources from cache
        lights = cache_controller.get_lights()
        rooms = cache_controller.get_rooms()
        scenes = cache_controller.get_scenes()
        devices = cache_controller.get_devices()

        # Count switch devices (devices with button services)
        switch_devices = [d for d in devices if any(s.get('rtype') == 'button' for s in d.get('services', []))]

        # Count smart plugs
        plug_devices = [
            d for d in devices
            if d.get('product_data', {}).get('product_name') == 'Hue smart plug'
        ]

        # Count light devices (bulbs, strips, etc.)
        light_devices = [
            d for d in devices
            if d.get('product_data', {}).get('product_name', '').lower() not in ['hue smart plug', 'unknown']
            and any(keyword in d.get('product_data', {}).get('product_name', '').lower()
                   for keyword in ['bulb', 'lamp', 'spot', 'strip', 'candle', 'filament', 'color', 'colour', 'white', 'ambiance', 'festavia', 'light'])
        ]

        # Count other devices
        other_devices = [
            d for d in devices
            if not any(keyword in d.get('product_data', {}).get('product_name', '').lower()
                      for keyword in [
                          'switch', 'dimmer', 'dial', 'smart plug',
                          'bulb', 'lamp', 'spot', 'strip', 'candle', 'filament',
                          'color', 'colour', 'white', 'ambiance', 'festavia', 'light'
                      ])
            and d.get('product_data', {}).get('product_name', '').lower() != 'unknown'
        ]

        lights_count = len(lights) if lights else 0
        rooms_count = len(rooms) if rooms else 0
        scenes_count = len(scenes) if scenes else 0
        switches_count = len(switch_devices)
        plugs_count = len(plug_devices)
        light_devices_count = len(light_devices)
        other_count = len(other_devices)

        click.echo(f"{light_devices_count} light devices")
        click.echo(f"{plugs_count} smart plugs")
        click.echo(f"{switches_count} switches")
        click.echo(f"{other_count} other devices")
        click.echo(f"{rooms_count} rooms")
        click.echo(f"{scenes_count} scenes")
        click.echo(f"{lights_count} light resources")
        click.echo()

    except Exception as e:
        click.echo(f"Error getting status: {e}")
        click.echo()


@click.command()
@click.option('--auto-reload/--no-auto-reload', default=True, help='Auto-reload stale cache (default: yes)')
def groups_command(auto_reload: bool):
    """List all groups/rooms.

    Uses cached data, automatically reloading if the cache is over 24 hours old.
    """
    cache_controller = get_cache_controller(auto_reload)
    if not cache_controller:
        return

    try:
        rooms = cache_controller.get_rooms()
        if not rooms:
            click.echo("No rooms found.")
            return

        click.echo(f"\nAvailable rooms ({len(rooms)}):\n")
        for room in rooms:
            name = room.get('metadata', {}).get('name', 'Unnamed')
            archetype = room.get('metadata', {}).get('archetype', 'Unknown')
            children = room.get('children', [])

            # Count actual light children (not other device types)
            light_count = sum(1 for child in children if child.get('rtype') == 'light')

            click.echo(f"  • {name}")
            click.echo(f"    Type: {archetype}")
            click.echo(f"    Lights: {light_count}")
            click.echo()
    except Exception as e:
        click.echo(f"Error listing rooms: {e}")


@click.command()
@click.option('--auto-reload/--no-auto-reload', default=True, help='Auto-reload stale cache (default: yes)')
def scenes_command(auto_reload: bool):
    """List all available scenes. Uses cached data."""
    cache_controller = get_cache_controller(auto_reload)
    if not cache_controller:
        return

    try:
        scenes_list = cache_controller.get_scenes()
        if not scenes_list:
            click.echo("No scenes found.")
            return

        # Get rooms for display
        rooms_list = cache_controller.get_rooms()
        room_lookup = create_name_lookup(rooms_list)

        click.echo(f"\nAvailable scenes ({len(scenes_list)}):\n")
        for scene in scenes_list:
            name = scene.get('metadata', {}).get('name', 'Unnamed')
            scene_id = scene.get('id', 'Unknown')
            actions = scene.get('actions', [])
            room_rid = scene.get('group', {}).get('rid')
            room_name = room_lookup.get(room_rid, 'N/A')

            click.echo(f"  • {name}")
            click.echo(f"    ID: {scene_id[:16]}...")
            click.echo(f"    Room: {room_name}")
            click.echo(f"    Lights: {len(actions)}")
            click.echo()
    except Exception as e:
        click.echo(f"Error listing scenes: {e}")


@click.command()
@click.option('--room', '-r', help='Filter switches by room name')
@click.option('--auto-reload/--no-auto-reload', default=True, help='Auto-reload stale cache (default: yes)')
def switches_command(room: str, auto_reload: bool):
    """Display switches with model information organised by room.

    Shows all switches (dimmers, tap dials) organised by room in a table format.

    Uses cached data, automatically reloading if the cache is over 24 hours old.

    \b
    Examples:
      uv run python hue_backup.py switches              # All switches
      uv run python hue_backup.py switches -r living    # Only living room switches
    """
    cache_controller = get_cache_controller(auto_reload)
    if not cache_controller:
        return

    try:
        devices = cache_controller.get_devices()
        sensors = cache_controller.get_sensors()
        rooms_list = cache_controller.get_rooms()

        # Get switches
        switches = {
            sid: data for sid, data in sensors.items()
            if 'Switch' in data.get('type', '') or 'Button' in data.get('type', '')
        }

        # Build list of switches with room and model info
        switch_items = []
        for sensor_id, sensor_data in switches.items():
            device_id = sensor_data.get('device_id', '')
            device = next((d for d in devices if d.get('id') == device_id), None)
            if not device:
                continue

            name = sensor_data.get('name', 'Unnamed')
            emoji = get_switch_emoji(device_id, devices)
            model_id = device.get('product_data', {}).get('model_id', 'Unknown')

            # Find room
            room_name = 'Unassigned'
            for room_data in rooms_list:
                children = room_data.get('children', [])
                if any(c.get('rid') == device_id for c in children):
                    room_name = room_data.get('metadata', {}).get('name', 'Unknown')
                    break

            # Apply room filter
            if room and room.lower() not in room_name.lower():
                continue

            switch_items.append({
                'room': room_name,
                'name': f"{emoji} {name}",
                'model': model_id
            })

        if not switch_items:
            if room:
                click.echo(f"No switches found in room '{room}'.")
            else:
                click.echo("No switches found.")
            return

        # Sort by room then name
        switch_items.sort(key=lambda x: (x['room'], x['name']))

        # Display in table format
        click.echo()
        click.secho("=== Switches ===", fg='cyan', bold=True)
        click.echo()

        # Calculate column widths
        col_room = max(len(item['room']) for item in switch_items)
        col_name = max(len(item['name']) for item in switch_items)
        col_model = max(len(item['model']) for item in switch_items)

        # Ensure minimum widths for headers
        col_room = max(col_room, len("Room"))
        col_name = max(col_name, len("Switch Name"))
        col_model = max(col_model, len("Model"))

        # Print header
        header = (
            f"{'Room'.ljust(col_room)} │ "
            f"{'Switch Name'.ljust(col_name)} │ "
            f"{'Model'.ljust(col_model)}"
        )
        click.secho(header, fg='cyan', bold=True)

        # Print separator
        separator = (
            "─" * col_room + "─┼─" +
            "─" * col_name + "─┼─" +
            "─" * col_model
        )
        click.secho(separator, fg='cyan')

        # Print rows with room name only on first row of each room group
        previous_room = None
        for item in switch_items:
            is_new_room = item['room'] != previous_room

            # Show room name only on first row of each room group
            if is_new_room:
                room_display = click.style(item['room'], fg='bright_blue')
                previous_room = item['room']
            else:
                room_display = ' ' * len(item['room'])

            row_str = (
                f"{room_display}{' ' * (col_room - len(item['room']))} │ "
                f"{click.style(item['name'], fg='white')}{' ' * (col_name - display_width(item['name']))} │ "
                f"{click.style(item['model'], fg='bright_black')}{' ' * (col_model - len(item['model']))}"
            )
            click.echo(row_str)

        click.echo()

        # Summary with model breakdown
        click.secho("Summary:", fg='cyan', bold=True)
        click.echo(f"  Total switches: {len(switch_items)}")

        # Model breakdown
        model_counts = {}
        for item in switch_items:
            model = item['model']
            model_counts[model] = model_counts.get(model, 0) + 1

        for model in sorted(model_counts.keys()):
            count = model_counts[model]
            plural = "switch" if count == 1 else "switches"
            click.echo(f"  {model}: {count} {plural}")

        click.echo()

    except Exception as e:
        click.echo(f"Error listing switches: {e}")


@click.command()
def debug_buttons_command():
    """Debug - show raw button configuration data."""
    controller = HueController()
    if not controller.connect():
        return

    click.echo("\n=== Raw Button Configuration Data ===\n")

    # Get all the relevant resources
    devices = controller.get_devices()
    behaviours = controller.get_behaviour_instances()
    buttons = controller.get_buttons()

    # Get rooms
    groups_response = controller._request('GET', '/resource/room')
    rooms = create_name_lookup(groups_response)

    click.echo(f"Found {len(devices)} devices")
    click.echo(f"Found {len(behaviours)} behaviour instances")
    click.echo(f"Found {len(buttons)} button resources")
    click.echo(f"Found {len(rooms)} rooms\n")

    # Show switch devices with their button services and room info
    for device in devices:
        button_services = [s for s in device.get('services', []) if s.get('rtype') == 'button']
        if button_services:
            device_name = device.get('metadata', {}).get('name', 'Unknown')

            # Show full device structure for first switch only
            if 'Sparkles' in device_name:
                click.echo(f"\n=== Full device structure for {device_name} ===")
                click.echo(json.dumps(device, indent=2))
                click.echo("=" * 80)

            owner = device.get('owner', {})
            owner_type = owner.get('rtype', 'none')
            owner_rid = owner.get('rid', '')
            room_name = rooms.get(owner_rid, 'Not found') if owner_type == 'room' else 'N/A'

            click.echo(f"\n{device_name} (ID: {device.get('id')})")
            click.echo(f"  Owner type: {owner_type}")
            if owner_type == 'room':
                click.echo(f"  Room: {room_name}")
            click.echo(f"  Button services: {len(button_services)}")
            for bs in button_services:
                click.echo(f"    - {bs.get('rtype')} (rid: {bs.get('rid')})")

    # Filter to button-triggered behaviours
    button_behaviours = [b for b in behaviours if 'device' in b.get('configuration', {})]
    click.echo(f"\n\nTotal behaviour instances: {len(behaviours)}")
    click.echo(f"Button-triggered behaviours: {len(button_behaviours)}\n")

    for i, behaviour in enumerate(button_behaviours):
        device_rid = behaviour.get('configuration', {}).get('device', {}).get('rid')
        # Find device name
        device_name = 'Unknown'
        for device in devices:
            if device.get('id') == device_rid:
                device_name = device.get('metadata', {}).get('name', 'Unknown')
                break

        click.echo(f"\nBehaviour {i+1} - Device: {device_name}")
        click.echo(json.dumps(behaviour.get('configuration', {}), indent=2))
        click.echo("=" * 80)


@click.command()
@click.option('--room', '-r', help='Filter by room/location (case-insensitive substring match)')
@click.option('--auto-reload/--no-auto-reload', default=True, help='Auto-reload stale cache (default: yes)')
def button_data_command(room: str, auto_reload: bool):
    """Show programmed wall controls (dimmers and dials).

    This shows the bridge-configured button automations from the Hue Bridge itself,
    not the local mappings from this CLI tool. Includes both dimmer switches and tap dials.
    Uses cached data, automatically reloading if the cache is over 24 hours old.

    \b
    Examples:
      uv run python hue_backup.py button-data              # Show all wall controls
      uv run python hue_backup.py button-data -r lounge    # Only lounge controls
      uv run python hue_backup.py button-data -r bed       # All bedroom controls
    """
    cache_controller = get_cache_controller(auto_reload)
    if not cache_controller:
        return

    try:
        devices = cache_controller.get_devices()
        behaviours = cache_controller.get_behaviour_instances()
        scenes = cache_controller.get_scenes()
        buttons = cache_controller.get_buttons()

        # Get rooms/groups for location filtering
        rooms_response = cache_controller.get_rooms()
        rooms = create_name_lookup(rooms_response)

        # Create scene lookup by id
        scene_lookup = create_name_lookup(scenes)

        # Create button lookup by rid (to get control_id for display)
        button_lookup = {b['id']: b for b in buttons}

        # Filter to button-triggered behaviours (includes both dimmers and dials)
        # Check for both 'buttons' and 'button1/button2' formats
        button_behaviours = []
        for b in behaviours:
            config = b.get('configuration', {})
            if 'buttons' in config:
                button_behaviours.append(b)
            elif any(key.startswith('button') for key in config.keys()):
                button_behaviours.append(b)

        if room:
            click.echo(f"\n=== Wall Controls (Dimmers & Dials) - Filtered: '{room}' ===\n")
        else:
            click.echo("\n=== Wall Controls (Dimmers & Dials) ===\n")

        click.echo(f"(Found {len(button_behaviours)} wall control behaviours)\n")

        matches_found = 0

        for behaviour in button_behaviours:
            config = behaviour.get('configuration', {})
            device_rid = config.get('device', {}).get('rid')

            # Find device name and room
            device_name = 'Unknown'
            device_id_v1 = ''
            switch_rooms = []

            for device in devices:
                if device.get('id') == device_rid:
                    device_name = device.get('metadata', {}).get('name', 'Unknown')
                    device_id_v1 = device.get('id_v1', '')
                    if device_id_v1.startswith('/sensors/'):
                        device_id_v1 = device_id_v1.split('/')[-1]
                    break

            # Get room(s) from the behaviour configuration using helper methods
            where_lists = cache_controller._extract_where_lists_from_config(config)
            switch_rooms = cache_controller._extract_rooms_from_where_lists(where_lists, rooms)

            # Filter by room if specified - check both device name and room name
            if room:
                room_lower = room.lower()
                name_match = room_lower in device_name.lower()
                room_match = any(room_lower in r.lower() for r in switch_rooms)
                if not (name_match or room_match):
                    continue

            matches_found += 1

            # Display device with room information
            room_display = f" [{', '.join(switch_rooms)}]" if switch_rooms else ""
            click.secho(f"\n{device_name} (ID: {device_id_v1}){room_display}", fg='cyan', bold=True)
            click.echo("─" * 80)

            # Handle both new format ('buttons' dict) and old format ('button1', 'button2', etc.)
            button_list = []

            if 'buttons' in config:
                # New format: buttons is a dict with button rids as keys
                buttons_config = config.get('buttons', {})
                for button_rid, button_config in buttons_config.items():
                    button_res = button_lookup.get(button_rid, {})
                    control_id = button_res.get('metadata', {}).get('control_id', 999)
                    button_list.append((control_id, button_rid, button_config))
            else:
                # Old format: button1, button2, button3, button4 as separate keys
                for button_key in ['button1', 'button2', 'button3', 'button4']:
                    if button_key in config:
                        button_config = config[button_key]
                        control_id = int(button_key.replace('button', ''))
                        button_list.append((control_id, button_key, button_config))

            # Sort by control_id (1, 2, 3, 4)
            button_list.sort(key=lambda x: x[0])

            for control_id, button_ref, button_config in button_list:
                button_label = BUTTON_LABELS.get(control_id, '')
                button_display = f"Button {control_id}"
                if button_label:
                    button_display += f" ({button_label})"

                click.secho(f"\n  {button_display}:", fg='green', bold=True)

                # Parse button actions
                if 'on_short_release' in button_config:
                    action = button_config['on_short_release']
                    click.echo(f"    Short press:", nl=False)

                    # Scene cycle
                    if 'scene_cycle_extended' in action:
                        slots = action['scene_cycle_extended'].get('slots', [])
                        scene_names = []
                        for slot in slots:
                            if slot and len(slot) > 0:
                                scene_rid = slot[0].get('action', {}).get('recall', {}).get('rid')
                                if scene_rid:
                                    scene_names.append(scene_lookup.get(scene_rid, scene_rid[:8]))
                        if scene_names:
                            click.echo(f" Cycle through {len(scene_names)} scenes")
                            for i, name in enumerate(scene_names, 1):
                                click.echo(f"                  {i}. {name}")

                    # Time-based
                    elif 'time_based_extended' in action:
                        slots = action['time_based_extended'].get('slots', [])
                        click.echo(f" Time-based - {len(slots)} time slots")
                        for slot in slots:
                            start_time = slot.get('start_time', {})
                            hour = start_time.get('hour', 0)
                            minute = start_time.get('minute', 0)
                            actions = slot.get('actions', [])
                            if actions:
                                scene_rid = actions[0].get('action', {}).get('recall', {}).get('rid')
                                scene_name = scene_lookup.get(scene_rid, 'Unknown')
                                click.echo(f"                  {hour:02d}:{minute:02d} → {scene_name}")

                    # Single recall
                    elif 'recall_single_extended' in action:
                        actions_list = action['recall_single_extended'].get('actions', [])
                        if actions_list:
                            scene_rid = actions_list[0].get('action', {}).get('recall', {}).get('rid')
                            scene_name = scene_lookup.get(scene_rid, 'Unknown')
                            click.echo(f" Activate scene: {scene_name}")

                if 'on_long_press' in button_config:
                    action_type = button_config['on_long_press'].get('action', 'Unknown')
                    action_display = action_type.replace('_', ' ').title()
                    click.echo(f"    Long press:  {action_display}")

                if 'on_repeat' in button_config:
                    action_type = button_config['on_repeat'].get('action', 'Unknown')
                    action_display = action_type.replace('_', ' ').title()
                    click.echo(f"    Hold/repeat: {action_display}")

        if room and matches_found == 0:
            click.echo(f"No switches found matching '{room}'")

        click.echo()

    except Exception as e:
        click.echo(f"Error getting button programs: {e}")
        traceback.print_exc()


@click.command()
@click.option('--table', '-t', is_flag=True, help='Display in table format')
@click.option('--auto-reload/--no-auto-reload', default=True, help='Auto-reload stale cache (default: yes)')
def bridge_auto_command(table: bool, auto_reload: bool):
    """Show bridge-configured button automations (old format).

    This displays the button configurations from the Hue Bridge itself,
    not the local mappings from this CLI tool. Uses cached data.

    DEPRECATED: Use 'button-data' instead for better output.
    """
    cache_controller = get_cache_controller(auto_reload)
    if not cache_controller:
        return

    try:
        devices = cache_controller.get_devices()
        behaviours = cache_controller.get_behaviour_instances()
        scenes = cache_controller.get_scenes()

        # Create scene lookup by id
        scene_lookup = create_name_lookup(scenes)

        # Map devices to their behaviour instances
        device_behaviours = {}

        for behaviour in behaviours:
            config = behaviour.get('configuration', {})
            device_ref = config.get('device', {})
            device_rid = device_ref.get('rid')

            if not device_rid:
                continue

            # Find the device
            device_name = None
            device_id_v1 = None
            for device in devices:
                if device['id'] == device_rid:
                    device_name = device.get('metadata', {}).get('name', 'Unknown')
                    device_id_v1 = device.get('id_v1', '')
                    if device_id_v1.startswith('/sensors/'):
                        device_id_v1 = device_id_v1.split('/')[-1]
                    break

            if not device_name:
                continue

            if device_rid not in device_behaviours:
                device_behaviours[device_rid] = {
                    'name': device_name,
                    'id_v1': device_id_v1,
                    'buttons': []
                }

            # Parse button configurations
            for button_key in ['button1', 'button2', 'button3', 'button4']:
                if button_key not in config:
                    continue

                button_config = config[button_key]
                button_num = button_key.replace('button', '')

                # Check for short release actions
                if 'on_short_release' in button_config:
                    action = button_config['on_short_release']
                    action_desc = []

                    # Scene cycle
                    if 'scene_cycle_extended' in action:
                        slots = action['scene_cycle_extended'].get('slots', [])
                        scene_names = []
                        for slot in slots[:5]:  # Show first 5
                            if slot and len(slot) > 0:
                                scene_rid = slot[0].get('action', {}).get('recall', {}).get('rid')
                                if scene_rid:
                                    scene_names.append(scene_lookup.get(scene_rid, scene_rid[:8]))
                        if scene_names:
                            action_desc.append(f"Cycle: {' → '.join(scene_names)}")
                            if len(slots) > 5:
                                action_desc.append(f"(+{len(slots)-5} more)")

                    # Time-based
                    if 'time_based_extended' in action:
                        action_desc.append("Time-based scenes")

                    # Single recall
                    if 'recall_single_extended' in action:
                        actions_list = action['recall_single_extended'].get('actions', [])
                        if actions_list and len(actions_list) > 0:
                            scene_rid = actions_list[0].get('action', {}).get('recall', {}).get('rid')
                            if scene_rid:
                                action_desc.append(f"Scene: {scene_lookup.get(scene_rid, scene_rid[:8])}")

                    if action_desc:
                        device_behaviours[device_rid]['buttons'].append({
                            'button': f'Button {button_num} (short)',
                            'action': ' | '.join(action_desc)
                        })

                # Check for long press
                if 'on_long_press' in button_config:
                    action = button_config['on_long_press'].get('action', '')
                    if action:
                        device_behaviours[device_rid]['buttons'].append({
                            'button': f'Button {button_num} (long)',
                            'action': action.replace('_', ' ').title()
                        })

        # Display results
        if not device_behaviours:
            click.echo("No button-based automations found.")
            return

        if table:
            click.echo()
            click.secho("Bridge-Configured Button Automations (v2 API)", fg='cyan', bold=True)
            click.echo()

            for device_rid, data in sorted(device_behaviours.items(), key=lambda x: x[1]['name']):
                click.secho(f"{data['name']} (ID: {data['id_v1']})", fg='green', bold=True)
                click.echo("─" * 100)

                for btn_config in data['buttons']:
                    click.echo(f"  {btn_config['button']:20} → {btn_config['action']}")

                click.echo()
        else:
            click.echo("\n=== Bridge-Configured Button Automations (v2 API) ===\n")

            for device_rid, data in sorted(device_behaviours.items(), key=lambda x: x[1]['name']):
                click.secho(f"• {data['name']} (ID: {data['id_v1']})", fg='green')

                for btn_config in data['buttons']:
                    click.echo(f"    {btn_config['button']} → {btn_config['action']}")

                click.echo()

    except Exception as e:
        click.echo(f"Error getting bridge automations: {e}")
        traceback.print_exc()


@click.command()
@click.option('--table', '-t', is_flag=True, help='Display in table format instead of boxes')
@click.option('--room', '-r', help='Filter switches by room/location (case-insensitive substring match)')
@click.option('--auto-reload/--no-auto-reload', default=True, help='Auto-reload stale cache (default: yes)')
def switch_status_command(table: bool, room: str, auto_reload: bool):
    """Display switch status with CLI mappings (for monitor command).

    Shows battery, last event, and local CLI mappings configured with 'map'.
    For bridge-configured programmes, use 'button-data' instead.

    Uses cached data, automatically reloading if the cache is over 24 hours old.

    \b
    Examples:
      uv run python hue_backup.py switch-status          # Box format, all switches
      uv run python hue_backup.py switch-status -t       # Table format
      uv run python hue_backup.py switch-status -r lounge  # Only lounge switches
    """
    cache_controller = get_cache_controller(auto_reload)
    if not cache_controller:
        return

    try:
        sensors = cache_controller.get_sensors()
        scenes = cache_controller.get_scenes()
        devices = cache_controller.get_devices()

        # Filter to only switches/buttons
        switches = {
            sid: data for sid, data in sensors.items()
            if 'Switch' in data.get('type', '') or 'Button' in data.get('type', '')
        }

        # Apply room filter if specified
        if room:
            # Get device to room mapping
            device_rooms = cache_controller.get_device_rooms()
            room_lower = room.lower()

            filtered_switches = {}
            for sid, data in switches.items():
                # Check if room matches device name (fallback)
                name_match = room_lower in data.get('name', '').lower()

                # Check if room matches actual room assignment
                device_id = data.get('device_id', '')
                room_names = device_rooms.get(device_id, [])
                room_match = any(room_lower in r.lower() for r in room_names)

                if name_match or room_match:
                    filtered_switches[sid] = data

            switches = filtered_switches

        if not switches:
            if room:
                click.echo(f"No switches found matching room '{room}'.")
            else:
                click.echo("No switches found.")
            return

        if table:
            # Table format
            click.echo()

            # Prepare data for table
            rows = []
            for sensor_id, sensor_data in switches.items():
                # Get switch emoji based on device type
                device_id = sensor_data.get('device_id', '')
                emoji = get_switch_emoji(device_id, devices)

                name = sensor_data.get('name', 'Unnamed')
                name_with_emoji = f"{emoji} {name}"

                state = sensor_data.get('state', {})
                config = sensor_data.get('config', {})

                # Battery
                battery_level = config.get('battery')
                battery_state = config.get('battery_state', '').lower()

                if battery_level is not None:
                    battery = f"{battery_level}%"
                    if battery_state:
                        battery += f" ({battery_state})"
                else:
                    battery = "N/A"

                # Last event
                last_event_raw = state.get('buttonevent')
                last_updated = state.get('lastupdated', '')
                if last_event_raw and last_event_raw != 'N/A':
                    timestamp_str = format_timestamp(last_updated)
                    timestamp_display = f" ({timestamp_str})" if timestamp_str else ""
                    last_event = f"{decode_button_event(last_event_raw, compact=True)}{timestamp_display}"
                else:
                    last_event = 'N/A'

                # Find configured mappings for this switch
                switch_mappings = []
                for mapping_key, scene_id in cache_controller.button_mappings.items():
                    if mapping_key.startswith(f"{sensor_id}:"):
                        _, button_event = mapping_key.split(':')
                        scene_name = scenes.get(scene_id, {}).get('name', 'Unknown')
                        switch_mappings.append(f"{button_event}→{scene_name}")

                mappings_str = ", ".join(switch_mappings) if switch_mappings else ""

                rows.append({
                    'name': name_with_emoji,
                    'id': sensor_id,
                    'battery': battery,
                    'last_event': str(last_event),
                    'mappings': mappings_str
                })

            # Calculate column widths using display_width (accounts for emojis)
            col_name = max(display_width(r['name']) for r in rows)
            col_id = max(len(r['id']) for r in rows)
            col_battery = max(len(r['battery']) for r in rows)
            col_event = max(len(r['last_event']) for r in rows)
            col_mappings = max(len(r['mappings']) for r in rows)

            # Ensure minimum widths for headers
            col_name = max(col_name, len("Switch Name"))
            col_id = max(col_id, len("ID"))
            col_battery = max(col_battery, len("Battery"))
            col_event = max(col_event, len("Last Event"))
            col_mappings = max(col_mappings, len("CLI Mappings (monitor)"))

            # Print header
            header = (
                f"{'Switch Name'.ljust(col_name)} │ "
                f"{'ID'.ljust(col_id)} │ "
                f"{'Battery'.ljust(col_battery)} │ "
                f"{'Last Event'.ljust(col_event)} │ "
                f"{'CLI Mappings (monitor)'.ljust(col_mappings)}"
            )
            click.secho(header, fg='cyan', bold=True)

            # Print separator
            separator = (
                "─" * col_name + "─┼─" +
                "─" * col_id + "─┼─" +
                "─" * col_battery + "─┼─" +
                "─" * col_event + "─┼─" +
                "─" * col_mappings
            )
            click.secho(separator, fg='cyan')

            # Print rows
            for row in rows:
                # Style text only, then add plain spaces for padding to avoid ANSI alignment issues
                # Use display_width for name (accounts for emoji)
                row_str = (
                    f"{click.style(row['name'], fg='green')}{' ' * (col_name - display_width(row['name']))} │ "
                    f"{click.style(row['id'], fg='white')}{' ' * (col_id - len(row['id']))} │ "
                    f"{click.style(row['battery'], fg='yellow')}{' ' * (col_battery - len(row['battery']))} │ "
                    f"{click.style(row['last_event'], fg='white')}{' ' * (col_event - len(row['last_event']))} │ "
                    f"{click.style(row['mappings'], fg='blue')}{' ' * (col_mappings - len(row['mappings']))}"
                )
                click.echo(row_str)

            click.echo()
            # Show legend
            click.secho("Event codes: ", fg='cyan', nl=False)
            click.echo("IP=Initial Press, H=Hold, SR=Short Release, LR=Long Release")
            click.echo()
        else:
            # Box format (original)
            click.echo()

            for sensor_id, sensor_data in switches.items():
                # Get switch emoji based on device type
                device_id = sensor_data.get('device_id', '')
                emoji = get_switch_emoji(device_id, devices)

                name = sensor_data.get('name', 'Unnamed')
                state = sensor_data.get('state', {})
                config = sensor_data.get('config', {})

                # Build box content
                box_lines = []
                box_lines.append(f"  {emoji} {name}  ")
                box_lines.append(f"  ID: {sensor_id}  ")

                # Battery if available
                battery_level = config.get('battery')
                if battery_level is not None:
                    # Choose icon based on battery_state from API
                    battery_state = config.get('battery_state', '').lower()
                    if battery_state == 'critical':
                        battery_icon = "🪫"  # Empty battery - urgent
                    elif battery_state == 'low':
                        battery_icon = "⚠️"  # Warning triangle - attention needed
                    else:
                        battery_icon = "🔋"  # Full battery - normal

                    battery_text = f"{battery_level}%"
                    if battery_state:
                        battery_text += f" ({battery_state})"

                    box_lines.append(f"  {battery_icon} Battery: {battery_text}  ")

                # Last button event
                if 'buttonevent' in state:
                    event_code = state['buttonevent']
                    decoded = decode_button_event(event_code, compact=True)
                    last_updated = state.get('lastupdated', '')
                    timestamp_str = format_timestamp(last_updated)
                    timestamp_display = f" ({timestamp_str})" if timestamp_str else ""
                    box_lines.append(f"  Last event: {decoded}{timestamp_display}  ")

                # Find configured mappings for this switch
                switch_mappings = []
                for mapping_key, scene_id in cache_controller.button_mappings.items():
                    if mapping_key.startswith(f"{sensor_id}:"):
                        _, button_event = mapping_key.split(':')
                        scene_name = scenes.get(scene_id, {}).get('name', 'Unknown')
                        switch_mappings.append((button_event, scene_name))

                if switch_mappings:
                    box_lines.append("  ")
                    box_lines.append("  CLI mappings (for monitor):  ")
                    for btn_event, scene_name in sorted(switch_mappings, key=lambda x: x[0]):
                        box_lines.append(f"    {btn_event} → {scene_name}  ")

                # Calculate box width using display width (accounts for emojis)
                max_width = max(display_width(line) for line in box_lines)

                # Draw box
                top_border = "┌" + "─" * max_width + "┐"
                bottom_border = "└" + "─" * max_width + "┘"

                click.echo(top_border)
                for line in box_lines:
                    line_width = display_width(line)
                    padded_line = line + " " * (max_width - line_width)
                    click.echo(f"│{padded_line}│")
                click.echo(bottom_border)
                click.echo()

            # Show legend
            click.secho("Event codes: ", fg='cyan', nl=False)
            click.echo("IP=Initial Press, H=Hold, SR=Short Release, LR=Long Release")
            click.echo()

    except Exception as e:
        click.echo(f"Error getting switch status: {e}")


@click.command()
@click.argument('sensor_id', required=False)
@click.option('--room', '-r', help='Show info for all switches in room (case-insensitive substring match)')
@click.option('--auto-reload/--no-auto-reload', default=True, help='Auto-reload stale cache (default: yes)')
def switch_info_command(sensor_id: str, room: str, auto_reload: bool):
    """Get detailed information about switch(es). Uses cached data.

    Supports fuzzy matching - can search by sensor ID, device name, or room name.

    \b
    Examples:
      uv run python hue_backup.py switch-info 2           # Info for sensor ID 2
      uv run python hue_backup.py switch-info office      # Fuzzy match on name/room
      uv run python hue_backup.py switch-info -r lounge   # All lounge switches
    """
    # Validate arguments
    if not sensor_id and not room:
        click.echo("Error: Must specify either sensor_id/name or --room/-r option")
        return

    cache_controller = get_cache_controller(auto_reload)
    if not cache_controller:
        return

    try:
        sensors = cache_controller.get_sensors()

        # Filter switches based on arguments
        if room:
            # Show all switches in room (explicit --room flag)
            # Get device to room mapping
            device_rooms = cache_controller.get_device_rooms()
            room_lower = room.lower()

            switches_to_show = {}
            for sid, data in sensors.items():
                # Only include switches
                if not ('Switch' in data.get('type', '') or 'Button' in data.get('type', '')):
                    continue

                # Check if room matches device name (fallback)
                name_match = room_lower in data.get('name', '').lower()

                # Check if room matches actual room assignment
                device_id = data.get('device_id', '')
                room_names = device_rooms.get(device_id, [])
                room_match = any(room_lower in r.lower() for r in room_names)

                if name_match or room_match:
                    switches_to_show[sid] = data

            if not switches_to_show:
                click.echo(f"No switches found matching room '{room}'.")
                return
        elif sensor_id:
            # Try exact ID match first
            if sensor_id in sensors:
                switches_to_show = {sensor_id: sensors[sensor_id]}
            else:
                # Fuzzy match on device name or room name
                device_rooms = cache_controller.get_device_rooms()
                search_term = sensor_id.lower()

                switches_to_show = {}
                for sid, data in sensors.items():
                    # Only include switches
                    if not ('Switch' in data.get('type', '') or 'Button' in data.get('type', '')):
                        continue

                    # Check if search term matches device name
                    device_name = data.get('name', '').lower()
                    name_match = search_term in device_name

                    # Check if search term matches room name
                    device_id = data.get('device_id', '')
                    room_names = device_rooms.get(device_id, [])
                    room_match = any(search_term in r.lower() for r in room_names)

                    if name_match or room_match:
                        switches_to_show[sid] = data

                if not switches_to_show:
                    click.echo(f"No switches found matching '{sensor_id}'.")
                    click.echo("Try: sensor ID (e.g., '2'), device name (e.g., 'dimmer'), or room (e.g., 'office')")
                    return
                elif len(switches_to_show) > 1:
                    click.echo(f"Found {len(switches_to_show)} switches matching '{sensor_id}':\n")
        else:
            return

        # Display info for each switch
        for sid, sensor_data in switches_to_show.items():
            state = sensor_data.get('state', {})
            config = sensor_data.get('config', {})

            click.echo(f"\n=== {sensor_data.get('name', 'Unnamed')} ===\n")
            click.echo(f"ID: {sid}")
            click.echo(f"Type: {sensor_data.get('type', 'Unknown')}")
            click.echo(f"Model: {sensor_data.get('modelid', 'Unknown')}")
            click.echo(f"Manufacturer: {sensor_data.get('manufacturername', 'Unknown')}")

            click.echo(f"\nState:")
            if 'buttonevent' in state:
                click.echo(f"  Last button event: {state['buttonevent']}")
            if 'lastupdated' in state:
                click.echo(f"  Last updated: {state['lastupdated']}")

            # Battery information
            battery_level = config.get('battery')
            if battery_level is not None:
                battery_text = f"{battery_level}%"
                battery_state = config.get('battery_state', '').lower()
                if battery_state:
                    battery_text += f" ({battery_state})"
                click.echo(f"\nBattery: {battery_text}")

            # Check for CLI mappings (for monitor command)
            click.echo(f"\nCLI mappings (for monitor command):")
            has_mappings = False
            for mapping_key, scene_id in cache_controller.button_mappings.items():
                if mapping_key.startswith(f"{sid}:"):
                    scenes_list = cache_controller.get_scenes()
                    _, button_event = mapping_key.split(':')
                    # Find scene name from v2 format
                    scene_name = 'Unknown'
                    for scene in scenes_list:
                        if scene.get('id') == scene_id:
                            scene_name = scene.get('metadata', {}).get('name', 'Unknown')
                            break
                    click.echo(f"  Button {button_event} → {scene_name}")
                    has_mappings = True

            if not has_mappings:
                click.echo("  None (use 'map' command to configure)")

    except Exception as e:
        click.echo(f"Error getting switch info: {e}")


@click.command()
@click.option('--room', '-r', help='Filter plugs by room name')
@click.option('--auto-reload/--no-auto-reload', default=True, help='Auto-reload stale cache (default: yes)')
def plugs_command(room: str, auto_reload: bool):
    """Display smart plug status (on/off state by room).

    Shows all Hue smart plugs with their on/off state, organised by room.
    Uses cached data, automatically reloading if the cache is over 24 hours old.

    \b
    Examples:
      uv run python hue_backup.py plugs              # All plugs
      uv run python hue_backup.py plugs -r lounge    # Only lounge plugs
    """
    cache_controller = get_cache_controller(auto_reload)
    if not cache_controller:
        return

    try:
        # Get all devices and lights
        devices = cache_controller.get_devices()
        lights = cache_controller.get_lights()
        rooms_list = cache_controller.get_rooms()

        # Create room lookup
        room_lookup = create_name_lookup(rooms_list)

        # Find all smart plug devices
        plug_devices = [
            d for d in devices
            if d.get('product_data', {}).get('product_name') == 'Hue smart plug'
        ]

        if not plug_devices:
            click.echo("No smart plugs found.")
            return

        # Organise plugs by room
        plugs_by_room = {}

        for device in plug_devices:
            device_id = device.get('id')
            device_name = device.get('metadata', {}).get('name', 'Unnamed')

            # Get product information
            product_data = device.get('product_data', {})
            model_id = product_data.get('model_id', 'Unknown')
            manufacturer = product_data.get('manufacturer_name', 'Unknown')
            product_name = product_data.get('product_name', 'Unknown')

            # Find the corresponding light resource for this device
            light = next((l for l in lights if l.get('owner', {}).get('rid') == device_id), None)
            if not light:
                continue

            # Get on/off state
            is_on = light.get('on', {}).get('on', False)

            # Find room assignment - rooms contain device IDs in children, not light IDs
            room_name = 'Unassigned'
            for room_data in rooms_list:
                children = room_data.get('children', [])
                # Check if device_id is in the room's children
                if any(c.get('rid') == device_id for c in children):
                    room_name = room_data.get('metadata', {}).get('name', 'Unknown')
                    break

            # Apply room filter if specified
            if room and room.lower() not in room_name.lower():
                continue

            # Add to room group
            if room_name not in plugs_by_room:
                plugs_by_room[room_name] = []

            plugs_by_room[room_name].append({
                'name': device_name,
                'on': is_on,
                'model_id': model_id,
                'manufacturer': manufacturer,
                'product_name': product_name
            })

        if not plugs_by_room:
            if room:
                click.echo(f"No smart plugs found matching room '{room}'.")
            else:
                click.echo("No smart plugs found.")
            return

        # Display plugs in table format
        click.echo()
        click.secho("=== Smart Plugs ===", fg='cyan', bold=True)
        click.echo()

        # Prepare table rows
        rows = []
        for room_name in sorted(plugs_by_room.keys()):
            plugs = plugs_by_room[room_name]
            for plug in sorted(plugs, key=lambda p: p['name']):
                rows.append({
                    'room': room_name,
                    'name': f"🔌 {plug['name']}",
                    'status': 'ON' if plug['on'] else 'OFF',
                    'on': plug['on'],
                    'model': plug['model_id']
                })

        # Calculate column widths using display_width for emoji-containing fields
        col_room = max(len(r['room']) for r in rows)
        col_name = max(display_width(r['name']) for r in rows)
        # Status column: "⚫ OFF" = emoji (2) + space (1) + "OFF" (3) = 6 display cols
        col_status = 6
        col_model = max(len(r['model']) for r in rows)

        # Ensure minimum widths for headers
        col_room = max(col_room, len("Room"))
        col_name = max(col_name, len("Plug Name"))
        col_model = max(col_model, len("Model"))

        # Print header
        header = (
            f"{'Room'.ljust(col_room)} │ "
            f"{'Plug Name'.ljust(col_name)} │ "
            f"{'Status'.ljust(col_status)} │ "
            f"{'Model'.ljust(col_model)}"
        )
        click.secho(header, fg='cyan', bold=True)

        # Print separator
        separator = (
            "─" * col_room + "─┼─" +
            "─" * col_name + "─┼─" +
            "─" * col_status + "─┼─" +
            "─" * col_model
        )
        click.secho(separator, fg='cyan')

        # Print rows with room name only on first row of each room group
        previous_room = None
        for row in rows:
            # Check if this is a new room
            is_new_room = row['room'] != previous_room

            # Status with icon and colour
            if row['on']:
                status_icon = "🔌"
                status_text = click.style("ON", fg='green', bold=True)
                status_display_width = 2 + 1 + 2  # emoji (2) + space (1) + "ON" (2)
            else:
                status_icon = "⚫"
                status_text = click.style("OFF", fg='red')
                status_display_width = 2 + 1 + 3  # emoji (2) + space (1) + "OFF" (3)

            status_display = status_icon + " " + status_text

            # Show room name only on first row of each room group
            if is_new_room:
                room_display = click.style(row['room'], fg='bright_blue')
                previous_room = row['room']
            else:
                room_display = ' ' * len(row['room'])  # Blank space matching room name length

            row_str = (
                f"{room_display}{' ' * (col_room - len(row['room']))} │ "
                f"{click.style(row['name'], fg='white')}{' ' * (col_name - display_width(row['name']))} │ "
                f"{status_display}{' ' * (col_status - status_display_width)} │ "
                f"{click.style(row['model'], fg='yellow')}{' ' * (col_model - len(row['model']))}"
            )
            click.echo(row_str)

        click.echo()

        # Summary
        total_plugs = sum(len(plugs) for plugs in plugs_by_room.values())
        total_on = sum(1 for plugs in plugs_by_room.values() for p in plugs if p['on'])
        total_off = total_plugs - total_on

        # Get unique models
        all_plugs = [p for plugs in plugs_by_room.values() for p in plugs]
        unique_models = {}
        for plug in all_plugs:
            model = plug['model_id']
            if model not in unique_models:
                unique_models[model] = 0
            unique_models[model] += 1

        click.secho("Summary:", fg='cyan', bold=True)
        click.echo(f"  Total plugs: {total_plugs}")
        click.echo(f"  {click.style('●', fg='green')} ON: {total_on}  {click.style('●', fg='red')} OFF: {total_off}")
        click.echo()
        click.secho("Models:", fg='cyan', bold=True)
        for model, count in sorted(unique_models.items()):
            click.echo(f"  {model}: {count} plug{'s' if count != 1 else ''}")
        click.echo()

    except Exception as e:
        click.echo(f"Error getting plug status: {e}")


@click.command()
@click.option('--room', '-r', help='Filter lights by room name')
@click.option('--auto-reload/--no-auto-reload', default=True, help='Auto-reload stale cache (default: yes)')
def lights_command(room: str, auto_reload: bool):
    """Display light bulbs and fixtures with status and model info.

    Shows all Hue lights (bulbs, spots, candles, strips, etc.) with their
    on/off state and model information, organised by room.
    Excludes smart plugs (use 'plugs' command for those).

    Uses cached data, automatically reloading if the cache is over 24 hours old.

    \b
    Examples:
      uv run python hue_backup.py lights              # All lights
      uv run python hue_backup.py lights -r lounge    # Only lounge lights
    """
    cache_controller = get_cache_controller(auto_reload)
    if not cache_controller:
        return

    try:
        # Get all devices and lights
        devices = cache_controller.get_devices()
        lights = cache_controller.get_lights()
        rooms_list = cache_controller.get_rooms()

        # Filter to actual light devices (not smart plugs)
        light_devices = [
            d for d in devices
            if d.get('product_data', {}).get('product_name', '').lower() not in ['hue smart plug', 'unknown']
            and any(keyword in d.get('product_data', {}).get('product_name', '').lower()
                   for keyword in ['bulb', 'lamp', 'spot', 'strip', 'candle', 'filament', 'color', 'colour', 'white', 'ambiance', 'festavia', 'light'])
        ]

        if not light_devices:
            click.echo("No lights found.")
            return

        # Organise lights by room
        lights_by_room = {}

        for device in light_devices:
            device_id = device.get('id')
            device_name = device.get('metadata', {}).get('name', 'Unnamed')

            # Get product information
            product_data = device.get('product_data', {})
            model_id = product_data.get('model_id', 'Unknown')
            product_name = product_data.get('product_name', 'Unknown')

            # Find the corresponding light resource for this device
            light = next((l for l in lights if l.get('owner', {}).get('rid') == device_id), None)
            if not light:
                continue

            # Get on/off state
            is_on = light.get('on', {}).get('on', False)

            # Find room assignment - rooms contain device IDs in children
            room_name = 'Unassigned'
            for room_data in rooms_list:
                children = room_data.get('children', [])
                # Check if device_id is in the room's children
                if any(c.get('rid') == device_id for c in children):
                    room_name = room_data.get('metadata', {}).get('name', 'Unknown')
                    break

            # Apply room filter if specified
            if room and room.lower() not in room_name.lower():
                continue

            # Add to room group
            if room_name not in lights_by_room:
                lights_by_room[room_name] = []

            lights_by_room[room_name].append({
                'name': device_name,
                'on': is_on,
                'model_id': model_id,
                'product_name': product_name.replace('color', 'colour')
            })

        if not lights_by_room:
            if room:
                click.echo(f"No lights found matching room '{room}'.")
            else:
                click.echo("No lights found.")
            return

        # Display lights in table format
        click.echo()
        click.secho("=== Lights ===", fg='cyan', bold=True)
        click.echo()

        # Prepare table rows
        rows = []
        for room_name in sorted(lights_by_room.keys()):
            room_lights = lights_by_room[room_name]
            for light in sorted(room_lights, key=lambda l: l['name']):
                rows.append({
                    'room': room_name,
                    'name': f"💡 {light['name']}",
                    'status': 'ON' if light['on'] else 'OFF',
                    'on': light['on'],
                    'model': light['model_id'],
                    'type': light['product_name']
                })

        # Calculate column widths using display_width for emoji-containing fields
        col_room = max(len(r['room']) for r in rows)
        col_name = max(display_width(r['name']) for r in rows)
        # Status column: "💡 ON" = emoji (2) + space (1) + "ON" (2) = 5 display cols
        col_status = 6
        col_model = max(len(r['model']) for r in rows)
        col_type = max(len(r['type']) for r in rows)

        # Ensure minimum widths for headers
        col_room = max(col_room, len("Room"))
        col_name = max(col_name, len("Light Name"))
        col_model = max(col_model, len("Model"))
        col_type = max(col_type, len("Type"))

        # Print header
        header = (
            f"{'Room'.ljust(col_room)} │ "
            f"{'Light Name'.ljust(col_name)} │ "
            f"{'Status'.ljust(col_status)} │ "
            f"{'Model'.ljust(col_model)} │ "
            f"{'Type'.ljust(col_type)}"
        )
        click.secho(header, fg='cyan', bold=True)

        # Print separator
        separator = (
            "─" * col_room + "─┼─" +
            "─" * col_name + "─┼─" +
            "─" * col_status + "─┼─" +
            "─" * col_model + "─┼─" +
            "─" * col_type
        )
        click.secho(separator, fg='cyan')

        # Print rows with room name only on first row of each room group
        previous_room = None
        for i, row in enumerate(rows):
            # Check if this is a new room
            is_new_room = row['room'] != previous_room

            # Status with icon and colour
            if row['on']:
                status_icon = "💡"
                status_text = click.style("ON", fg='green', bold=True)
                status_display_width = 2 + 1 + 2  # emoji (2) + space (1) + "ON" (2)
            else:
                status_icon = "⚫"
                status_text = click.style("OFF", fg='red')
                status_display_width = 2 + 1 + 3  # emoji (2) + space (1) + "OFF" (3)

            status_display = status_icon + " " + status_text

            # Show room name only on first row of each room group
            if is_new_room:
                room_display = click.style(row['room'], fg='bright_blue')
                previous_room = row['room']
            else:
                room_display = ' ' * len(row['room'])  # Blank space matching room name length

            # Print row
            row_str = (
                f"{room_display}{' ' * (col_room - len(row['room']))} │ "
                f"{click.style(row['name'], fg='white')}{' ' * (col_name - display_width(row['name']))} │ "
                f"{status_display}{' ' * (col_status - status_display_width)} │ "
                f"{click.style(row['model'], fg='yellow')}{' ' * (col_model - len(row['model']))} │ "
                f"{click.style(row['type'], fg='bright_black')}{' ' * (col_type - len(row['type']))}"
            )
            click.echo(row_str)

        click.echo()

        # Summary
        total_lights = sum(len(room_lights) for room_lights in lights_by_room.values())
        total_on = sum(1 for room_lights in lights_by_room.values() for l in room_lights if l['on'])
        total_off = total_lights - total_on

        # Get unique models with product type names
        all_lights = [l for room_lights in lights_by_room.values() for l in room_lights]
        unique_models = {}
        for light in all_lights:
            model = light['model_id']
            product_type = light['product_name']
            if model not in unique_models:
                unique_models[model] = {'count': 0, 'type': product_type}
            unique_models[model]['count'] += 1

        click.secho("Summary:", fg='cyan', bold=True)
        click.echo(f"  Total lights: {total_lights}")
        click.echo(f"  {click.style('●', fg='green')} ON: {total_on}  {click.style('●', fg='red')} OFF: {total_off}")
        click.echo()
        click.secho("Models:", fg='cyan', bold=True)

        # Calculate column widths for alignment
        max_model_width = max(len(model) for model in unique_models.keys())
        max_type_width = max(len(info['type']) for info in unique_models.values())

        for model, info in sorted(unique_models.items()):
            count = info['count']
            type_name = info['type']
            # Align model codes and type names
            model_padded = model.ljust(max_model_width)
            type_padded = type_name.ljust(max_type_width)
            click.echo(f"  {model_padded} ({type_padded}): {count} light{'s' if count != 1 else ''}")
        click.echo()

    except Exception as e:
        click.echo(f"Error getting light status: {e}")


@click.command()
@click.option('--room', '-r', help='Filter devices by room name')
@click.option('--auto-reload/--no-auto-reload', default=True, help='Auto-reload stale cache (default: yes)')
def other_command(room: str, auto_reload: bool):
    """Display other devices (doorbell, chimes, bridge, etc.).

    Shows devices that aren't switches, plugs, or lights - things like
    the Hue Bridge, doorbell cameras, chimes, and other accessories.

    Uses cached data, automatically reloading if the cache is over 24 hours old.

    \b
    Examples:
      uv run python hue_backup.py other              # All other devices
      uv run python hue_backup.py other -r hallway   # Filter by room
    """
    cache_controller = get_cache_controller(auto_reload)
    if not cache_controller:
        return

    try:
        # Get all devices
        devices = cache_controller.get_devices()
        rooms_list = cache_controller.get_rooms()

        # Filter to devices that aren't switches, plugs, or lights
        # Exclude switches/dimmers/dials
        # Exclude smart plugs
        # Exclude lights (bulbs, lamps, etc.)
        other_devices = [
            d for d in devices
            if not any(keyword in d.get('product_data', {}).get('product_name', '').lower()
                      for keyword in [
                          # Switches
                          'switch', 'dimmer', 'dial',
                          # Plugs
                          'smart plug',
                          # Lights
                          'bulb', 'lamp', 'spot', 'strip', 'candle', 'filament',
                          'color', 'colour', 'white', 'ambiance', 'festavia', 'light'
                      ])
            and d.get('product_data', {}).get('product_name', '').lower() != 'unknown'
        ]

        if not other_devices:
            click.echo("No other devices found.")
            return

        # Organise devices by room
        devices_by_room = {}

        for device in other_devices:
            device_id = device.get('id')
            device_name = device.get('metadata', {}).get('name', 'Unnamed')

            # Get product information
            product_data = device.get('product_data', {})
            model_id = product_data.get('model_id', 'Unknown')
            product_name = product_data.get('product_name', 'Unknown')

            # Find room assignment - rooms contain device IDs in children
            room_name = 'Unassigned'
            for room_data in rooms_list:
                children = room_data.get('children', [])
                # Check if device_id is in the room's children
                if any(c.get('rid') == device_id for c in children):
                    room_name = room_data.get('metadata', {}).get('name', 'Unknown')
                    break

            # Apply room filter if specified
            if room and room.lower() not in room_name.lower():
                continue

            # Add to room group
            if room_name not in devices_by_room:
                devices_by_room[room_name] = []

            devices_by_room[room_name].append({
                'name': device_name,
                'model_id': model_id,
                'product_name': product_name
            })

        if not devices_by_room:
            if room:
                click.echo(f"No other devices found matching room '{room}'.")
            else:
                click.echo("No other devices found.")
            return

        # Display devices in table format
        click.echo()
        click.secho("=== Other Devices ===", fg='cyan', bold=True)
        click.echo()

        # Prepare table rows
        rows = []
        for room_name in sorted(devices_by_room.keys()):
            room_devices = devices_by_room[room_name]
            for device in sorted(room_devices, key=lambda d: d['name']):
                # Determine emoji based on device type
                product_name_lower = device['product_name'].lower()
                if 'doorbell' in product_name_lower or 'camera' in product_name_lower:
                    type_emoji = '📷'
                elif 'chime' in product_name_lower or 'ding' in product_name_lower:
                    type_emoji = '🔔'
                elif 'bridge' in product_name_lower:
                    type_emoji = '🌉'
                else:
                    type_emoji = '🔧'

                rows.append({
                    'room': room_name,
                    'name': f"{type_emoji} {device['name']}",
                    'model': device['model_id'],
                    'type': device['product_name']
                })

        # Calculate column widths using display_width for emoji-containing fields
        col_room = max(len(r['room']) for r in rows)
        col_name = max(display_width(r['name']) for r in rows)
        col_model = max(len(r['model']) for r in rows)
        col_type = max(len(r['type']) for r in rows)

        # Ensure minimum widths for headers
        col_room = max(col_room, len("Room"))
        col_name = max(col_name, len("Device Name"))
        col_model = max(col_model, len("Model"))
        col_type = max(col_type, len("Type"))

        # Print header
        header = (
            f"{'Room'.ljust(col_room)} │ "
            f"{'Device Name'.ljust(col_name)} │ "
            f"{'Model'.ljust(col_model)} │ "
            f"{'Type'.ljust(col_type)}"
        )
        click.secho(header, fg='cyan', bold=True)

        # Print separator
        separator = (
            "─" * col_room + "─┼─" +
            "─" * col_name + "─┼─" +
            "─" * col_model + "─┼─" +
            "─" * col_type
        )
        click.secho(separator, fg='cyan')

        # Print rows with room name only on first row of each room group
        previous_room = None
        for i, row in enumerate(rows):
            # Check if this is a new room
            is_new_room = row['room'] != previous_room

            # Show room name only on first row of each room group
            if is_new_room:
                room_display = click.style(row['room'], fg='bright_blue')
                previous_room = row['room']
            else:
                room_display = ' ' * len(row['room'])  # Blank space matching room name length

            # Print row
            row_str = (
                f"{room_display}{' ' * (col_room - len(row['room']))} │ "
                f"{click.style(row['name'], fg='white')}{' ' * (col_name - display_width(row['name']))} │ "
                f"{click.style(row['model'], fg='yellow')}{' ' * (col_model - len(row['model']))} │ "
                f"{click.style(row['type'], fg='bright_black')}{' ' * (col_type - len(row['type']))}"
            )
            click.echo(row_str)

        click.echo()

        # Summary
        total_devices = sum(len(room_devices) for room_devices in devices_by_room.values())

        # Get unique models with product type names
        all_devices = [d for room_devices in devices_by_room.values() for d in room_devices]
        unique_models = {}
        for device in all_devices:
            model = device['model_id']
            product_type = device['product_name']
            if model not in unique_models:
                unique_models[model] = {'count': 0, 'type': product_type}
            unique_models[model]['count'] += 1

        click.secho("Summary:", fg='cyan', bold=True)
        click.echo(f"  Total devices: {total_devices}")
        click.echo()
        click.secho("Models:", fg='cyan', bold=True)

        # Calculate column widths for alignment
        max_model_width = max(len(model) for model in unique_models.keys())
        max_type_width = max(len(info['type']) for info in unique_models.values())

        for model, info in sorted(unique_models.items()):
            count = info['count']
            type_name = info['type']
            # Align model codes and type names
            model_padded = model.ljust(max_model_width)
            type_padded = type_name.ljust(max_type_width)
            click.echo(f"  {model_padded} ({type_padded}): {count} device{'s' if count != 1 else ''}")
        click.echo()

    except Exception as e:
        click.echo(f"Error getting other devices: {e}")


@click.command()
@click.option('--room', '-r', help='Filter devices by room name')
@click.option('--auto-reload/--no-auto-reload', default=True, help='Auto-reload stale cache (default: yes)')
def all_devices_command(room: str, auto_reload: bool):
    """Display all devices (switches, plugs, lights, other) in one view.

    Shows switches, smart plugs, lights, and other devices organised by room
    in a compact table format. Each device type is clearly labelled.

    Uses cached data, automatically reloading if the cache is over 24 hours old.

    \b
    Examples:
      uv run python hue_backup.py all              # All devices
      uv run python hue_backup.py all -r living    # Only living room devices
    """
    cache_controller = get_cache_controller(auto_reload)
    if not cache_controller:
        return

    try:
        # Get all data
        devices = cache_controller.get_devices()
        lights = cache_controller.get_lights()
        sensors = cache_controller.get_sensors()
        rooms_list = cache_controller.get_rooms()

        # Build a unified list of all devices with their types
        all_items = []

        # Add switches
        switches = {
            sid: data for sid, data in sensors.items()
            if 'Switch' in data.get('type', '') or 'Button' in data.get('type', '')
        }
        device_rooms = cache_controller.get_device_rooms() if hasattr(cache_controller, 'get_device_rooms') else {}

        for sensor_id, sensor_data in switches.items():
            device_id = sensor_data.get('device_id', '')
            device = next((d for d in devices if d.get('id') == device_id), None)
            if not device:
                continue

            name = sensor_data.get('name', 'Unnamed')
            emoji = get_switch_emoji(device_id, devices)

            # Find room
            room_name = 'Unassigned'
            for room_data in rooms_list:
                children = room_data.get('children', [])
                if any(c.get('rid') == device_id for c in children):
                    room_name = room_data.get('metadata', {}).get('name', 'Unknown')
                    break

            # Apply room filter
            if room and room.lower() not in room_name.lower():
                continue

            all_items.append({
                'room': room_name,
                'name': f"{emoji} {name}",
                'type': 'Switch',
                'model': device.get('product_data', {}).get('model_id', 'Unknown')
            })

        # Add smart plugs
        plug_devices = [
            d for d in devices
            if d.get('product_data', {}).get('product_name') == 'Hue smart plug'
        ]

        for device in plug_devices:
            device_id = device.get('id')
            device_name = device.get('metadata', {}).get('name', 'Unnamed')
            model_id = device.get('product_data', {}).get('model_id', 'Unknown')

            # Find room
            room_name = 'Unassigned'
            for room_data in rooms_list:
                children = room_data.get('children', [])
                if any(c.get('rid') == device_id for c in children):
                    room_name = room_data.get('metadata', {}).get('name', 'Unknown')
                    break

            # Apply room filter
            if room and room.lower() not in room_name.lower():
                continue

            all_items.append({
                'room': room_name,
                'name': f"🔌 {device_name}",
                'type': 'Plug',
                'model': model_id
            })

        # Add lights
        light_devices = [
            d for d in devices
            if d.get('product_data', {}).get('product_name', '').lower() not in ['hue smart plug', 'unknown']
            and any(keyword in d.get('product_data', {}).get('product_name', '').lower()
                   for keyword in ['bulb', 'lamp', 'spot', 'strip', 'candle', 'filament', 'color', 'colour', 'white', 'ambiance', 'festavia', 'light'])
        ]

        for device in light_devices:
            device_id = device.get('id')
            device_name = device.get('metadata', {}).get('name', 'Unnamed')
            model_id = device.get('product_data', {}).get('model_id', 'Unknown')

            # Find room
            room_name = 'Unassigned'
            for room_data in rooms_list:
                children = room_data.get('children', [])
                if any(c.get('rid') == device_id for c in children):
                    room_name = room_data.get('metadata', {}).get('name', 'Unknown')
                    break

            # Apply room filter
            if room and room.lower() not in room_name.lower():
                continue

            all_items.append({
                'room': room_name,
                'name': f"💡 {device_name}",
                'type': 'Light',
                'model': model_id
            })

        # Add other devices
        other_devices = [
            d for d in devices
            if not any(keyword in d.get('product_data', {}).get('product_name', '').lower()
                      for keyword in [
                          'switch', 'dimmer', 'dial', 'smart plug',
                          'bulb', 'lamp', 'spot', 'strip', 'candle', 'filament',
                          'color', 'colour', 'white', 'ambiance', 'festavia', 'light'
                      ])
            and d.get('product_data', {}).get('product_name', '').lower() != 'unknown'
        ]

        for device in other_devices:
            device_id = device.get('id')
            device_name = device.get('metadata', {}).get('name', 'Unnamed')
            model_id = device.get('product_data', {}).get('model_id', 'Unknown')
            product_name = device.get('product_data', {}).get('product_name', '').lower()

            # Determine emoji based on device type
            if 'doorbell' in product_name or 'camera' in product_name:
                type_emoji = '📷'
            elif 'chime' in product_name or 'ding' in product_name:
                type_emoji = '🔔'
            elif 'bridge' in product_name:
                type_emoji = '🌉'
            else:
                type_emoji = '🔧'

            # Find room
            room_name = 'Unassigned'
            for room_data in rooms_list:
                children = room_data.get('children', [])
                if any(c.get('rid') == device_id for c in children):
                    room_name = room_data.get('metadata', {}).get('name', 'Unknown')
                    break

            # Apply room filter
            if room and room.lower() not in room_name.lower():
                continue

            all_items.append({
                'room': room_name,
                'name': f"{type_emoji} {device_name}",
                'type': 'Other',
                'model': model_id
            })

        if not all_items:
            if room:
                click.echo(f"No devices found matching room '{room}'.")
            else:
                click.echo("No devices found.")
            return

        # Add emojis to types
        type_emojis = {
            'Light': '💡',
            'Switch': '🎛️',
            'Plug': '🔌',
            'Other': '🔧'
        }

        for item in all_items:
            emoji = type_emojis.get(item['type'], '')
            item['type_display'] = f"{emoji} {item['type']}"

        # Sort by room then type then name
        all_items.sort(key=lambda x: (x['room'], x['type'], x['name']))

        # Display in table format
        click.echo()
        click.secho("=== All Devices ===", fg='cyan', bold=True)
        click.echo()

        # Calculate column widths using display_width for emoji-containing fields
        col_room = max(len(item['room']) for item in all_items)
        col_name = max(display_width(item['name']) for item in all_items)
        col_type = max(display_width(item['type_display']) for item in all_items)
        col_model = max(len(item['model']) for item in all_items)

        # Ensure minimum widths for headers
        col_room = max(col_room, len("Room"))
        col_name = max(col_name, len("Device Name"))
        col_type = max(col_type, len("Type"))
        col_model = max(col_model, len("Model"))

        # Print header
        header = (
            f"{'Room'.ljust(col_room)} │ "
            f"{'Device Name'.ljust(col_name)} │ "
            f"{'Type'.ljust(col_type)} │ "
            f"{'Model'.ljust(col_model)}"
        )
        click.secho(header, fg='cyan', bold=True)

        # Print separator
        separator = (
            "─" * col_room + "─┼─" +
            "─" * col_name + "─┼─" +
            "─" * col_type + "─┼─" +
            "─" * col_model
        )
        click.secho(separator, fg='cyan')

        # Print rows with room name only on first row of each room group
        previous_room = None
        for item in all_items:
            is_new_room = item['room'] != previous_room

            # Show room name only on first row of each room group
            if is_new_room:
                room_display = click.style(item['room'], fg='bright_blue')
                previous_room = item['room']
            else:
                room_display = ' ' * len(item['room'])

            row_str = (
                f"{room_display}{' ' * (col_room - len(item['room']))} │ "
                f"{click.style(item['name'], fg='white')}{' ' * (col_name - display_width(item['name']))} │ "
                f"{click.style(item['type_display'], fg='yellow')}{' ' * (col_type - display_width(item['type_display']))} │ "
                f"{click.style(item['model'], fg='bright_black')}{' ' * (col_model - len(item['model']))}"
            )
            click.echo(row_str)

        click.echo()

        # Summary
        type_counts = {}
        for item in all_items:
            device_type = item['type']
            if device_type not in type_counts:
                type_counts[device_type] = 0
            type_counts[device_type] += 1

        click.secho("Summary:", fg='cyan', bold=True)
        click.echo(f"  Total devices: {len(all_items)}")
        for device_type in sorted(type_counts.keys()):
            count = type_counts[device_type]
            # Proper pluralization
            plural_type = device_type + 'es' if device_type == 'Switch' else device_type + 's'
            click.echo(f"  {plural_type}: {count}")
        click.echo()

    except Exception as e:
        click.echo(f"Error getting all devices: {e}")
