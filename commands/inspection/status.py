"""
Status and overview commands.

Commands for viewing bridge status, rooms, and scene lists.
"""

import click
from models.utils import create_name_lookup, get_cache_controller


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
        click.secho("\n=== Bridge Status ===\n", fg='cyan', bold=True)

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

        # Prepare items as (label, value) pairs
        items = [("light devices", light_devices_count),
                 ("smart plugs", plugs_count),
                 ("switches", switches_count),
                 ("other devices", other_count),
                 ("rooms", rooms_count),
                 ("scenes", scenes_count),
                 ("light resources", lights_count),]
                 
        # Work out the longest label and widest number
        max_label_len = max(len(label) for label, _ in items)
        max_num_len = max(len(str(value)) for _, value in items)
        
        # Print with proper alignment
        for label, value in items:
            click.echo(f"  {label:<{max_label_len}} : {value:>{max_num_len}}")
        click.echo()

    except Exception as e:
        click.echo(f"Error getting status: {e}\n")


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

        # Build list of room items
        room_items = []
        for room in rooms:
            name = room.get('metadata', {}).get('name', 'Unnamed')
            archetype = room.get('metadata', {}).get('archetype', 'Unknown')
            children = room.get('children', [])

            # Count actual light children (not other device types)
            light_count = sum(1 for child in children if child.get('rtype') == 'light')

            room_items.append({
                'name': name,
                'type': archetype,
                'lights': light_count
            })

        # Sort by name
        room_items.sort(key=lambda x: x['name'])

        click.secho(f"\n=== Rooms ({len(room_items)}) ===", fg='cyan', bold=True)
        click.echo()

        # Calculate column widths
        col_name = max((len(r['name']) for r in room_items), default=0)
        col_type = max((len(r['type']) for r in room_items), default=0)
        col_lights = max((len(str(r['lights'])) for r in room_items), default=0)

        # Ensure minimum widths for headers
        col_name = max(col_name, len("Room Name"))
        col_type = max(col_type, len("Type"))
        col_lights = max(col_lights, len("Lights"))

        # Print header
        header = f"  {'Room Name':<{col_name}}  {'Type':<{col_type}}  {'Lights':>{col_lights}}"
        click.echo(click.style(header, fg='white', bold=True))
        click.echo(click.style("  " + "─" * (col_name + col_type + col_lights + 4), fg='white', dim=True))

        # Print rows
        for i, room in enumerate(room_items):
            row = f"  {room['name']:<{col_name}}  {room['type']:<{col_type}}  {room['lights']:>{col_lights}}"
            if i == len(room_items) - 1:
                click.echo(row + "\n")
            else:
                click.echo(row)

    except Exception as e:
        click.echo(f"Error listing rooms: {e}")


@click.command()
@click.option('--auto-reload/--no-auto-reload', default=True, help='Auto-reload stale cache (default: yes)')
def zones_command(auto_reload: bool):
    """List all zones.

    Uses cached data, automatically reloading if the cache is over 24 hours old.
    Zones are hierarchical groupings that can contain multiple rooms.
    """
    cache_controller = get_cache_controller(auto_reload)
    if not cache_controller:
        return

    try:
        zones = cache_controller.get_zones()
        if not zones:
            click.echo("No zones found.")
            return

        # Build list of zone items
        zone_items = []
        for zone in zones:
            name = zone.get('metadata', {}).get('name', 'Unnamed')
            archetype = zone.get('metadata', {}).get('archetype', 'Unknown')
            children = zone.get('children', [])

            # Count child rooms and lights
            room_count = sum(1 for child in children if child.get('rtype') == 'room')
            light_count = sum(1 for child in children if child.get('rtype') == 'light')

            zone_items.append({
                'name': name,
                'type': archetype,
                'rooms': room_count,
                'lights': light_count
            })

        # Sort by name
        zone_items.sort(key=lambda x: x['name'])

        click.secho(f"\n=== Zones ({len(zone_items)}) ===", fg='cyan', bold=True)
        click.echo()

        # Calculate column widths
        col_name = max((len(z['name']) for z in zone_items), default=0)
        col_type = max((len(z['type']) for z in zone_items), default=0)
        col_rooms = max((len(str(z['rooms'])) for z in zone_items), default=0)
        col_lights = max((len(str(z['lights'])) for z in zone_items), default=0)

        # Ensure minimum widths for headers
        col_name = max(col_name, len("Zone Name"))
        col_type = max(col_type, len("Type"))
        col_rooms = max(col_rooms, len("Rooms"))
        col_lights = max(col_lights, len("Lights"))

        # Print header
        header = f"  {'Zone Name':<{col_name}}  {'Type':<{col_type}}  {'Rooms':>{col_rooms}}  {'Lights':>{col_lights}}"
        click.echo(click.style(header, fg='white', bold=True))
        click.echo(click.style("  " + "─" * (col_name + col_type + col_rooms + col_lights + 6), fg='white', dim=True))

        # Print rows
        for i, zone in enumerate(zone_items):
            row = f"  {zone['name']:<{col_name}}  {zone['type']:<{col_type}}  {zone['rooms']:>{col_rooms}}  {zone['lights']:>{col_lights}}"
            if i == len(zone_items) - 1:
                click.echo(row + "\n")
            else:
                click.echo(row)

    except Exception as e:
        click.echo(f"Error listing zones: {e}")


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

        # Build list of scene items
        scene_items = []
        for scene in scenes_list:
            name = scene.get('metadata', {}).get('name', 'Unnamed')
            actions = scene.get('actions', [])
            room_rid = scene.get('group', {}).get('rid')
            room_name = room_lookup.get(room_rid, 'N/A')

            scene_items.append({
                'name': name,
                'room': room_name,
                'lights': len(actions)
            })

        # Sort by room then name
        scene_items.sort(key=lambda x: (x['room'], x['name']))

        click.secho(f"\n=== Scenes ({len(scene_items)}) ===", fg='cyan', bold=True)
        click.echo()

        # Calculate column widths
        col_name = max((len(s['name']) for s in scene_items), default=0)
        col_room = max((len(s['room']) for s in scene_items), default=0)
        col_lights = max((len(str(s['lights'])) for s in scene_items), default=0)

        # Ensure minimum widths for headers
        col_name = max(col_name, len("Scene Name"))
        col_room = max(col_room, len("Room"))
        col_lights = max(col_lights, len("Lights"))

        # Print header
        header = f"  {'Scene Name':<{col_name}}  {'Room':<{col_room}}  {'Lights':>{col_lights}}"
        click.echo(click.style(header, fg='white', bold=True))
        click.echo(click.style("  " + "─" * (col_name + col_room + col_lights + 4), fg='white', dim=True))

        # Print rows with room grouping
        last_room = None
        for i, scene in enumerate(scene_items):
            # Show room name only on first occurrence
            room_display = scene['room'] if scene['room'] != last_room else ""

            # Format with proper padding first, then apply colour
            if room_display:
                room_part = click.style(f"{room_display:<{col_room}}", fg='bright_blue')
            else:
                room_part = " " * col_room

            row = f"  {scene['name']:<{col_name}}  {room_part}  {scene['lights']:>{col_lights}}"
            if i == len(scene_items) - 1:
                click.echo(row + "\n")
            else:
                click.echo(row)
            last_room = scene['room']

    except Exception as e:
        click.echo(f"Error listing scenes: {e}")
