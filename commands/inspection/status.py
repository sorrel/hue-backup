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
@click.option('-v', '--verbose', is_flag=True, help='Show lights in each zone')
@click.option('--multi-zone', is_flag=True, help='Show lights in multiple zones')
def zones_command(auto_reload: bool, verbose: bool, multi_zone: bool):
    """List all zones.

    Uses cached data, automatically reloading if the cache is over 24 hours old.
    Zones are groupings of lights. Use -v to see which lights are in each zone.
    """
    cache_controller = get_cache_controller(auto_reload)
    if not cache_controller:
        return

    # Check mutual exclusivity
    if verbose and multi_zone:
        click.echo("Error: Cannot use -v and --multi-zone together. Choose one mode.")
        return

    try:
        zones = cache_controller.get_zones()
        if not zones:
            click.echo("No zones found.")
            return

        # Get lights for lookups
        lights_list = cache_controller.get_lights()
        light_lookup = {light['id']: light.get('metadata', {}).get('name', 'Unnamed')
                        for light in lights_list}

        if multi_zone:
            _show_multi_zone_analysis(zones, light_lookup)
        elif verbose:
            _show_zones_verbose(zones, light_lookup)
        else:
            _show_zones_table(zones)

    except Exception as e:
        click.echo(f"Error listing zones: {e}")


def _show_zones_table(zones: list[dict]):
    """Display zones in table format (default mode)."""
    # Build list of zone items
    zone_items = []
    for zone in zones:
        name = zone.get('metadata', {}).get('name', 'Unnamed')
        archetype = zone.get('metadata', {}).get('archetype', 'Unknown')
        children = zone.get('children', [])

        # Count child lights only (zones don't contain rooms)
        light_count = sum(1 for child in children if child.get('rtype') == 'light')

        zone_items.append({
            'name': name,
            'type': archetype,
            'lights': light_count
        })

    # Sort by name
    zone_items.sort(key=lambda x: x['name'])

    click.secho(f"\n=== Zones ({len(zone_items)}) ===", fg='cyan', bold=True)
    click.echo()

    # Calculate column widths
    col_name = max((len(z['name']) for z in zone_items), default=0)
    col_type = max((len(z['type']) for z in zone_items), default=0)
    col_lights = max((len(str(z['lights'])) for z in zone_items), default=0)

    # Ensure minimum widths for headers
    col_name = max(col_name, len("Zone Name"))
    col_type = max(col_type, len("Type"))
    col_lights = max(col_lights, len("Lights"))

    # Print header
    header = f"  {'Zone Name':<{col_name}}  {'Type':<{col_type}}  {'Lights':>{col_lights}}"
    click.echo(click.style(header, fg='white', bold=True))
    click.echo(click.style("  " + "─" * (col_name + col_type + col_lights + 4), fg='white', dim=True))

    # Print rows
    for i, zone in enumerate(zone_items):
        row = f"  {zone['name']:<{col_name}}  {zone['type']:<{col_type}}  {zone['lights']:>{col_lights}}"
        if i == len(zone_items) - 1:
            click.echo(row + "\n")
        else:
            click.echo(row)


def _show_zones_verbose(zones: list[dict], light_lookup: dict):
    """Display zones with detailed light listings (verbose mode)."""
    # Sort zones by name
    zones_sorted = sorted(zones, key=lambda z: z.get('metadata', {}).get('name', 'Unnamed'))

    click.secho(f"\n=== Zones ({len(zones_sorted)}) ===", fg='cyan', bold=True)

    for zone in zones_sorted:
        name = zone.get('metadata', {}).get('name', 'Unnamed')
        archetype = zone.get('metadata', {}).get('archetype', 'Unknown')
        children = zone.get('children', [])

        # Get light IDs in this zone
        light_ids = [child['rid'] for child in children if child.get('rtype') == 'light']

        click.echo()
        click.secho(f"Zone: {name} ({archetype})", fg='bright_cyan')

        if light_ids:
            for light_id in light_ids:
                light_name = light_lookup.get(light_id, 'Unknown')
                click.echo(f"  • {light_name}")
            click.echo(f"  Lights: {len(light_ids)}")
        else:
            click.echo("  No lights")

    click.echo()


def _show_multi_zone_analysis(zones: list[dict], light_lookup: dict):
    """Display lights that appear in multiple zones."""
    # Build reverse mapping: light_id -> [zone_names]
    light_to_zones = {}
    for zone in zones:
        zone_name = zone.get('metadata', {}).get('name', 'Unnamed')
        children = zone.get('children', [])

        for child in children:
            if child.get('rtype') == 'light':
                light_id = child.get('rid')
                light_to_zones.setdefault(light_id, []).append(zone_name)

    # Filter to lights in 2+ zones
    multi_zone_lights = {lid: znames for lid, znames in light_to_zones.items() if len(znames) > 1}

    if not multi_zone_lights:
        click.echo("\nNo lights found in multiple zones.\n")
        return

    # Build display items
    items = []
    for light_id, zone_names in multi_zone_lights.items():
        light_name = light_lookup.get(light_id, 'Unknown')
        items.append({
            'name': light_name,
            'zones': ', '.join(sorted(zone_names)),
            'count': len(zone_names)
        })

    # Sort by count descending, then name
    items.sort(key=lambda x: (-x['count'], x['name']))

    click.secho(f"\n=== Lights in Multiple Zones ===", fg='cyan', bold=True)
    click.echo()

    # Calculate column widths
    col_name = max((len(item['name']) for item in items), default=0)
    col_zones = max((len(item['zones']) for item in items), default=0)
    col_count = max((len(str(item['count'])) for item in items), default=0)

    # Ensure minimum widths
    col_name = max(col_name, len("Light Name"))
    col_zones = max(col_zones, len("Zones"))
    col_count = max(col_count, len("Count"))

    # Print header
    header = f"  {'Light Name':<{col_name}}  {'Zones':<{col_zones}}  {'Count':>{col_count}}"
    click.echo(click.style(header, fg='white', bold=True))
    click.echo(click.style("  " + "─" * (col_name + col_zones + col_count + 4), fg='white', dim=True))

    # Print rows
    for i, item in enumerate(items):
        # Use bright yellow for lights in 3+ zones
        if item['count'] >= 3:
            name_display = click.style(item['name'], fg='bright_yellow')
            zones_display = click.style(item['zones'], fg='bright_yellow')
            count_display = click.style(str(item['count']), fg='bright_yellow')
        else:
            name_display = item['name']
            zones_display = item['zones']
            count_display = str(item['count'])

        # Need to handle padding with styled text
        row = f"  {name_display}{' ' * (col_name - len(item['name']))}  {zones_display}{' ' * (col_zones - len(item['zones']))}  {' ' * (col_count - len(str(item['count'])))}{count_display}"

        if i == len(items) - 1:
            click.echo(row + "\n")
        else:
            click.echo(row)

    # Show summary
    total_lights = len(light_to_zones)
    percentage = (len(multi_zone_lights) / total_lights * 100) if total_lights > 0 else 0
    click.echo(f"  Total: {len(multi_zone_lights)} lights in multiple zones ({percentage:.0f}% of {total_lights} lights)\n")


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

        # Get rooms and zones for display
        rooms_list = cache_controller.get_rooms()
        zones_list = cache_controller.get_zones()
        # Combine room and zone lookups since scenes can belong to either
        room_lookup = create_name_lookup(rooms_list)
        zone_lookup = create_name_lookup(zones_list)
        group_lookup = {**room_lookup, **zone_lookup}

        # Build list of scene items
        scene_items = []
        for scene in scenes_list:
            name = scene.get('metadata', {}).get('name', 'Unnamed')
            actions = scene.get('actions', [])
            room_rid = scene.get('group', {}).get('rid')
            room_name = group_lookup.get(room_rid, 'N/A')

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
        col_room = max(col_room, len("Room/Zone"))
        col_lights = max(col_lights, len("Lights"))

        # Print header
        header = f"  {'Scene Name':<{col_name}}  {'Room/Zone':<{col_room}}  {'Lights':>{col_lights}}"
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
