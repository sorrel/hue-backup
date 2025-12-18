"""
Device listing commands.

Commands for viewing different types of devices (plugs, lights, other, all).
"""

import click
from models.utils import display_width, get_cache_controller
from .helpers import (
    get_switch_emoji,
    find_device_room,
    should_include_device,
    display_device_table,
)
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

        # Find all smart plug devices
        plug_devices = [
            d for d in devices
            if d.get('product_data', {}).get('product_name') == 'Hue smart plug'
        ]

        if not plug_devices:
            click.echo("No smart plugs found.")
            return

        # Build list of plugs with room, status, and model info
        plug_items = []
        for device in plug_devices:
            device_id = device.get('id')
            device_name = device.get('metadata', {}).get('name', 'Unnamed')
            model_id = device.get('product_data', {}).get('model_id', 'Unknown')

            # Find the corresponding light resource for this device
            light = next((l for l in lights if l.get('owner', {}).get('rid') == device_id), None)
            if not light:
                continue

            # Get on/off state
            is_on = light.get('on', {}).get('on', False)

            # Find room and apply filter - USING HELPERS
            room_name = find_device_room(device_id, rooms_list)
            if not should_include_device(room_name, room):
                continue

            plug_items.append({
                'room': room_name,
                'name': f"🔌 {device_name}",
                'on': is_on,
                'model': model_id
            })

        if not plug_items:
            if room:
                click.echo(f"No smart plugs found matching room '{room}'.")
            else:
                click.echo("No smart plugs found.")
            return

        # Sort by room then name
        plug_items.sort(key=lambda x: (x['room'], x['name']))

        # Display table with status column
        click.echo()
        click.secho("=== Smart Plugs ===", fg='cyan', bold=True)
        click.echo()

        # Calculate column widths
        col_room = max((len(p['room']) for p in plug_items), default=0)
        col_name = max((display_width(p['name']) for p in plug_items), default=0)
        col_status = 6  # "⚫ OFF" = emoji (2) + space (1) + "OFF" (3) = 6
        col_model = max((len(p['model']) for p in plug_items), default=0)

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

        # Print rows with room grouping
        previous_room = None
        for plug in plug_items:
            is_new_room = plug['room'] != previous_room

            # Status with icon and colour
            if plug['on']:
                status_icon = "🔌"
                status_text = click.style("ON", fg='green', bold=True)
                status_width = 5  # emoji (2) + space (1) + "ON" (2)
            else:
                status_icon = "⚫"
                status_text = click.style("OFF", fg='red')
                status_width = 6  # emoji (2) + space (1) + "OFF" (3)

            status_display = status_icon + " " + status_text

            # Room grouping
            if is_new_room:
                room_display = click.style(plug['room'], fg='bright_blue')
                previous_room = plug['room']
            else:
                room_display = ' ' * len(plug['room'])

            row_str = (
                f"{room_display}{' ' * (col_room - len(plug['room']))} │ "
                f"{click.style(plug['name'], fg='white')}{' ' * (col_name - display_width(plug['name']))} │ "
                f"{status_display}{' ' * (col_status - status_width)} │ "
                f"{click.style(plug['model'], fg='yellow')}{' ' * (col_model - len(plug['model']))}"
            )
            click.echo(row_str)

        click.echo()

        # Summary
        total_plugs = len(plug_items)
        total_on = sum(1 for p in plug_items if p['on'])
        total_off = total_plugs - total_on

        click.secho("Summary:", fg='cyan', bold=True)
        click.echo(f"  Total plugs: {total_plugs}")
        click.echo(f"  {click.style('●', fg='green')} ON: {total_on}  {click.style('●', fg='red')} OFF: {total_off}")
        click.echo()

        # Model summary - USING HELPER
        click.secho("Models:", fg='cyan', bold=True)
        unique_models = {}
        for plug in plug_items:
            model = plug['model']
            unique_models[model] = unique_models.get(model, 0) + 1

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

        # Build list of lights with room, status, model, and type info
        light_items = []
        for device in light_devices:
            device_id = device.get('id')
            device_name = device.get('metadata', {}).get('name', 'Unnamed')
            model_id = device.get('product_data', {}).get('model_id', 'Unknown')
            product_name = device.get('product_data', {}).get('product_name', 'Unknown').replace('color', 'colour')

            # Find the corresponding light resource for this device
            light = next((l for l in lights if l.get('owner', {}).get('rid') == device_id), None)
            if not light:
                continue

            # Get on/off state
            is_on = light.get('on', {}).get('on', False)

            # Find room and apply filter - USING HELPERS
            room_name = find_device_room(device_id, rooms_list)
            if not should_include_device(room_name, room):
                continue

            light_items.append({
                'room': room_name,
                'name': f"💡 {device_name}",
                'on': is_on,
                'model': model_id,
                'type': product_name
            })

        if not light_items:
            if room:
                click.echo(f"No lights found matching room '{room}'.")
            else:
                click.echo("No lights found.")
            return

        # Sort by room then name
        light_items.sort(key=lambda x: (x['room'], x['name']))

        # Display table with status column
        click.echo()
        click.secho("=== Lights ===", fg='cyan', bold=True)
        click.echo()

        # Calculate column widths
        col_room = max((len(l['room']) for l in light_items), default=0)
        col_name = max((display_width(l['name']) for l in light_items), default=0)
        col_status = 6  # "⚫ OFF" = emoji (2) + space (1) + "OFF" (3) = 6
        col_model = max((len(l['model']) for l in light_items), default=0)
        col_type = max((len(l['type']) for l in light_items), default=0)

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

        # Print rows with room grouping
        previous_room = None
        for light in light_items:
            is_new_room = light['room'] != previous_room

            # Status with icon and colour
            if light['on']:
                status_icon = "💡"
                status_text = click.style("ON", fg='green', bold=True)
                status_width = 5  # emoji (2) + space (1) + "ON" (2)
            else:
                status_icon = "⚫"
                status_text = click.style("OFF", fg='red')
                status_width = 6  # emoji (2) + space (1) + "OFF" (3)

            status_display = status_icon + " " + status_text

            # Room grouping
            if is_new_room:
                room_display = click.style(light['room'], fg='bright_blue')
                previous_room = light['room']
            else:
                room_display = ' ' * len(light['room'])

            row_str = (
                f"{room_display}{' ' * (col_room - len(light['room']))} │ "
                f"{click.style(light['name'], fg='white')}{' ' * (col_name - display_width(light['name']))} │ "
                f"{status_display}{' ' * (col_status - status_width)} │ "
                f"{click.style(light['model'], fg='yellow')}{' ' * (col_model - len(light['model']))} │ "
                f"{click.style(light['type'], fg='bright_black')}{' ' * (col_type - len(light['type']))}"
            )
            click.echo(row_str)

        click.echo()

        # Summary
        total_lights = len(light_items)
        total_on = sum(1 for l in light_items if l['on'])
        total_off = total_lights - total_on

        click.secho("Summary:", fg='cyan', bold=True)
        click.echo(f"  Total lights: {total_lights}")
        click.echo(f"  {click.style('●', fg='green')} ON: {total_on}  {click.style('●', fg='red')} OFF: {total_off}")
        click.echo()

        # Model summary with type names
        click.secho("Models:", fg='cyan', bold=True)
        unique_models = {}
        for light in light_items:
            model = light['model']
            product_type = light['type']
            if model not in unique_models:
                unique_models[model] = {'count': 0, 'type': product_type}
            unique_models[model]['count'] += 1

        # Calculate column widths for alignment
        max_model_width = max(len(model) for model in unique_models.keys())
        max_type_width = max(len(info['type']) for info in unique_models.values())

        for model, info in sorted(unique_models.items()):
            count = info['count']
            type_name = info['type']
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

        # Build list of devices with room, model, and type info
        device_items = []
        for device in other_devices:
            device_id = device.get('id')
            device_name = device.get('metadata', {}).get('name', 'Unnamed')
            model_id = device.get('product_data', {}).get('model_id', 'Unknown')
            product_name = device.get('product_data', {}).get('product_name', 'Unknown')

            # Determine emoji based on device type
            product_name_lower = product_name.lower()
            if 'doorbell' in product_name_lower or 'camera' in product_name_lower:
                type_emoji = '📷'
            elif 'chime' in product_name_lower or 'ding' in product_name_lower:
                type_emoji = '🔔'
            elif 'bridge' in product_name_lower:
                type_emoji = '🌉'
            else:
                type_emoji = '🔧'

            # Find room and apply filter - USING HELPERS
            room_name = find_device_room(device_id, rooms_list)
            if not should_include_device(room_name, room):
                continue

            device_items.append({
                'room': room_name,
                'name': f"{type_emoji} {device_name}",
                'model': model_id,
                'type': product_name
            })

        if not device_items:
            if room:
                click.echo(f"No other devices found matching room '{room}'.")
            else:
                click.echo("No other devices found.")
            return

        # Sort by room then name
        device_items.sort(key=lambda x: (x['room'], x['name']))

        # Display table - USING HELPER
        columns = [
            {'key': 'room', 'header': 'Room'},
            {'key': 'name', 'header': 'Device Name'},
            {'key': 'model', 'header': 'Model', 'color': 'yellow'},
            {'key': 'type', 'header': 'Type', 'color': 'bright_black'}
        ]
        display_device_table(device_items, columns, "=== Other Devices ===", emoji_columns=['name'])

        # Summary with model breakdown
        click.secho("\nSummary:", fg='cyan', bold=True)
        click.echo(f"  Total devices: {len(device_items)}")
        click.echo()

        # Model summary with type names
        click.secho("Models:", fg='cyan', bold=True)
        unique_models = {}
        for device in device_items:
            model = device['model']
            product_type = device['type']
            if model not in unique_models:
                unique_models[model] = {'count': 0, 'type': product_type}
            unique_models[model]['count'] += 1

        # Calculate column widths for alignment
        max_model_width = max(len(model) for model in unique_models.keys())
        max_type_width = max(len(info['type']) for info in unique_models.values())

        for model, info in sorted(unique_models.items()):
            count = info['count']
            type_name = info['type']
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
    total_devices = f"Total devices"
    cache_controller = get_cache_controller(auto_reload)
    if not cache_controller:
        return

    try:
        # Get all data
        devices = cache_controller.get_devices()
        sensors = cache_controller.get_sensors()
        rooms_list = cache_controller.get_rooms()

        # Build a unified list of all devices with their types
        all_items = []

        # Add switches - USING HELPERS
        switches = {
            sid: data for sid, data in sensors.items()
            if 'Switch' in data.get('type', '') or 'Button' in data.get('type', '')
        }

        for sensor_id, sensor_data in switches.items():
            device_id = sensor_data.get('device_id', '')
            device = next((d for d in devices if d.get('id') == device_id), None)
            if not device:
                continue

            name = sensor_data.get('name', 'Unnamed')
            emoji = get_switch_emoji(device_id, devices)
            model_id = device.get('product_data', {}).get('model_id', 'Unknown')

            # Find room and apply filter - USING HELPERS
            room_name = find_device_room(device_id, rooms_list)
            if not should_include_device(room_name, room):
                continue

            all_items.append({
                'room': room_name,
                'name': f"{emoji} {name}",
                'type': 'Switch',
                'model': model_id
            })

        # Add smart plugs - USING HELPERS
        plug_devices = [
            d for d in devices
            if d.get('product_data', {}).get('product_name') == 'Hue smart plug'
        ]

        for device in plug_devices:
            device_id = device.get('id')
            device_name = device.get('metadata', {}).get('name', 'Unnamed')
            model_id = device.get('product_data', {}).get('model_id', 'Unknown')

            # Find room and apply filter - USING HELPERS
            room_name = find_device_room(device_id, rooms_list)
            if not should_include_device(room_name, room):
                continue

            all_items.append({
                'room': room_name,
                'name': f"🔌 {device_name}",
                'type': 'Plug',
                'model': model_id
            })

        # Add lights - USING HELPERS
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

            # Find room and apply filter - USING HELPERS
            room_name = find_device_room(device_id, rooms_list)
            if not should_include_device(room_name, room):
                continue

            all_items.append({
                'room': room_name,
                'name': f"💡 {device_name}",
                'type': 'Light',
                'model': model_id
            })

        # Add other devices - USING HELPERS
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

            # Find room and apply filter - USING HELPERS
            room_name = find_device_room(device_id, rooms_list)
            if not should_include_device(room_name, room):
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

        # Display table - USING HELPER
        columns = [
            {'key': 'room', 'header': 'Room'},
            {'key': 'name', 'header': 'Device Name'},
            {'key': 'type_display', 'header': 'Type', 'color': 'yellow'},
            {'key': 'model', 'header': 'Model', 'color': 'bright_black'}
        ]
        display_device_table(all_items, columns, "=== All Devices ===", emoji_columns=['name', 'type_display'])

        # Summary
        type_counts = {}
        for item in all_items:
            device_type = item['type']
            type_counts[device_type] = type_counts.get(device_type, 0) + 1

        click.secho("\nSummary:", fg='cyan', bold=True)
        click.echo(f"  Total devices : {len(all_items)}\n")

        items = []
        for device_type in sorted(type_counts.keys()):
            count = type_counts[device_type]

            # Proper pluralisation
            plural_type = device_type + 'es' if device_type == 'Switch' else device_type + 's'
            items.append((plural_type, count))
            
        # Work out longest label and widest number
        max_label_len = max(len(total_devices), *(len(label) for label, _ in items))
        max_num_len = max(len(str(value)) for _, value in items)
        
        # Print aligned output
        for label, value in items:
            click.echo(f"  {label:<{max_label_len}} : {value:>{max_num_len}}")
        click.echo()

    except Exception as e:
        click.echo(f"Error getting all devices: {e}")
