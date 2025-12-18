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
