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
from .helpers import (
    BUTTON_LABELS,
    SWITCH_EMOJIS,
    get_switch_emoji,
    format_timestamp,
    find_device_room,
    should_include_device,
    display_device_table,
    generate_model_summary,
)


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

            # Find room and apply filter
            room_name = find_device_room(device_id, rooms_list)
            if not should_include_device(room_name, room):
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

        # Display table
        columns = [
            {'key': 'room', 'header': 'Room'},
            {'key': 'name', 'header': 'Switch Name'},
            {'key': 'model', 'header': 'Model', 'color': 'bright_black'}
        ]
        display_device_table(switch_items, columns, "=== Switches ===", emoji_columns=['name'])

        # Display summary
        generate_model_summary(switch_items, model_key='model', type_name='switch')

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


