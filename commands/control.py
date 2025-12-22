"""
Control commands for direct manipulation of lights and scenes.

Includes power, brightness, colour, scene activation, and auto-dynamic control.
"""

import click
from core.controller import HueController
from models.utils import get_controller, get_cache_controller, create_name_lookup


@click.command()
@click.argument('light_name')
@click.option('--on/--off', default=True, help='Turn light on or off')
def power_command(light_name: str, on: bool):
    """Turn a light ON or OFF.

    \b
    Examples:
      uv run python hue_backup.py power "Bedroom" --on
      uv run python hue_backup.py power "Bedroom" --off
    """
    controller = get_controller()
    if not controller:
        return

    light = controller.get_light_by_name(light_name)
    if not light:
        click.echo(f"Error: Light '{light_name}' not found.")
        click.echo()
        return

    light_id, light_data = light
    if controller.set_light_state(light_id, {'on': on}):
        status = "ON" if on else "OFF"
        click.echo(f"✓ {light_data.get('name')} turned {status}")
    else:
        click.echo(f"✗ Failed to turn {light_data.get('name')} {status}")


@click.command()
@click.argument('light_name')
@click.argument('brightness', type=click.IntRange(0, 254))
def brightness_command(light_name: str, brightness: int):
    """Set brightness of a light (0-254).

    \b
    Examples:
      uv run python hue_backup.py brightness "Bedroom" 200
      uv run python hue_backup.py brightness "Bedroom" 50
    """
    controller = get_controller()
    if not controller:
        return

    light = controller.get_light_by_name(light_name)
    if not light:
        click.echo(f"Error: Light '{light_name}' not found.")
        click.echo()
        return

    light_id, light_data = light
    if controller.set_light_state(light_id, {'on': True, 'bri': brightness}):
        click.echo(f"✓ {light_data.get('name')} brightness set to {brightness}/254")
    else:
        click.echo(f"✗ Failed to set brightness")


@click.command()
@click.argument('light_name')
@click.option('--hue', '-u', type=click.IntRange(0, 65535), help='Hue value (0-65535)')
@click.option('--sat', '-s', type=click.IntRange(0, 254), help='Saturation (0-254)')
@click.option('--ct', '-t', type=click.IntRange(153, 500), help='Colour temperature (153-500 mireds)')
def colour_command(light_name: str, hue: int | None, sat: int | None, ct: int | None):
    """Set colour or temperature of a light.

    \b
    Examples:
      uv run python hue_backup.py colour "Bedroom" -u 10000 -s 254
      uv run python hue_backup.py colour "Bedroom" --ct 300
      uv run python hue_backup.py colour "Bedroom" -t 400
    """
    controller = get_controller()
    if not controller:
        return

    light = controller.get_light_by_name(light_name)
    if not light:
        click.echo(f"Error: Light '{light_name}' not found.")
        click.echo()
        return

    light_id, light_data = light
    state = {'on': True}

    if ct is not None:
        state['ct'] = ct
        if controller.set_light_state(light_id, state):
            click.echo(f"✓ {light_data.get('name')} colour temperature set to {ct} mireds")
        else:
            click.echo(f"✗ Failed to set colour temperature")
    elif hue is not None or sat is not None:
        if hue is not None:
            state['hue'] = hue
        if sat is not None:
            state['sat'] = sat
        if controller.set_light_state(light_id, state):
            click.echo(f"✓ {light_data.get('name')} colour updated")
        else:
            click.echo(f"✗ Failed to set colour")
    else:
        click.echo("Error: Please specify --hue/-u and --sat/-s, or --ct/-t")


@click.command()
@click.argument('scene_id')
def activate_scene_command(scene_id: str):
    """Activate a scene by its ID."""
    controller = get_controller()
    if not controller:
        return

    if controller.activate_scene(scene_id):
        click.echo(f"✓ Scene '{scene_id}' activated")
    else:
        click.echo(f"✗ Error activating scene '{scene_id}'")


@click.command()
@click.option('--room', '-r', help='Filter by room or zone name (case-insensitive substring match)')
@click.option('--set', type=click.Choice(['on', 'off']), help='Set auto-dynamic on/off for matching scenes')
@click.option('--scene', '-s', help='Filter by scene name (case-insensitive substring match)')
@click.option('--yes', '-y', is_flag=True, help='Skip confirmation prompt')
@click.option('--auto-reload/--no-auto-reload', default=True, help='Auto-reload stale cache (default: yes)')
def auto_dynamic_command(room: str, set: str, scene: str, yes: bool, auto_reload: bool):
    """View or modify auto-dynamic settings for scenes.

    Auto-dynamic scenes automatically start their dynamic effect when activated.

    \b
    Examples:
      # View all auto-dynamic settings
      uv run python hue_backup.py auto-dynamic

      # View auto-dynamic settings for Living room
      uv run python hue_backup.py auto-dynamic -r "Living"

      # Disable auto-dynamic for all Living room scenes
      uv run python hue_backup.py auto-dynamic -r "Living" --set off

      # Enable auto-dynamic for a specific scene
      uv run python hue_backup.py auto-dynamic -s "Golden star" --set on

      # Disable auto-dynamic for all scenes (careful!)
      uv run python hue_backup.py auto-dynamic --set off
    """
    # Use cache for reading, but connect to bridge for writing
    cache_controller = get_cache_controller(auto_reload)
    if not cache_controller:
        return

    try:
        scenes_list = cache_controller.get_scenes()
        if not scenes_list:
            click.echo("No scenes found.")
            return

        rooms_list = cache_controller.get_rooms()
        zones_list = cache_controller.get_zones()
        # Combine room and zone lookups since scenes can belong to either
        room_lookup = {r['id']: r.get('metadata', {}).get('name', 'Unknown') for r in rooms_list}
        zone_lookup = {z['id']: z.get('metadata', {}).get('name', 'Unknown') for z in zones_list}
        group_lookup = {**room_lookup, **zone_lookup}

        # Filter scenes by room and/or scene name
        filtered_scenes = []
        for s in scenes_list:
            scene_name = s.get('metadata', {}).get('name', 'Unknown')
            room_rid = s.get('group', {}).get('rid')
            room_name = group_lookup.get(room_rid, 'Unknown Room')

            # Apply filters
            if room and room.lower() not in room_name.lower():
                continue
            if scene and scene.lower() not in scene_name.lower():
                continue

            filtered_scenes.append({
                'id': s.get('id'),
                'name': scene_name,
                'room': room_name,
                'auto_dynamic': s.get('auto_dynamic', False),
                'speed': s.get('speed', 0)
            })

        if not filtered_scenes:
            click.echo("No scenes match the filters.")
            return

        # If --set is specified, modify the scenes
        if set:
            target_value = (set == 'on')

            # Show what will be changed
            to_change = [s for s in filtered_scenes if s['auto_dynamic'] != target_value]

            if not to_change:
                click.echo(f"All {len(filtered_scenes)} matching scenes already have auto_dynamic = {set}.")
                return

            click.echo(f"\nWill set auto_dynamic = {set} for {len(to_change)} scene(s):")
            for s in to_change:
                click.echo(f"  • {s['name']} [{s['room']}]")

            # Confirm (unless --yes flag is set)
            if not yes:
                if not click.confirm(f"\nProceed with updating {len(to_change)} scene(s)?", default=True):
                    click.echo("Cancelled.")
                    return

            # Connect to bridge for writes
            write_controller = HueController(use_cache=True)
            if not write_controller.connect():
                return

            # Update each scene
            success_count = 0
            fail_count = 0

            click.echo()
            for s in to_change:
                scene_id = s['id']
                scene_name = s['name']

                if write_controller.update_scene_auto_dynamic(scene_id, target_value):
                    click.echo(f"✓ {scene_name}")
                    success_count += 1
                else:
                    click.echo(f"✗ {scene_name} - Failed")
                    fail_count += 1

            click.echo(f"\n✓ Updated {success_count} scene(s)")
            if fail_count > 0:
                click.echo(f"✗ Failed to update {fail_count} scene(s)")

        else:
            # Just display the current status
            # Group by room
            by_room = {}
            for s in filtered_scenes:
                if s['room'] not in by_room:
                    by_room[s['room']] = []
                by_room[s['room']].append(s)

            # Count totals
            total_on = sum(1 for s in filtered_scenes if s['auto_dynamic'])
            total_off = len(filtered_scenes) - total_on

            click.echo(f"\nAuto-Dynamic Status ({len(filtered_scenes)} scenes)")
            click.echo(f"  ON: {total_on}  |  OFF: {total_off}")
            click.echo()

            for room_name in sorted(by_room.keys()):
                room_scenes = by_room[room_name]
                click.echo(f"{room_name}:")

                for s in sorted(room_scenes, key=lambda x: x['name']):
                    status = click.style('ON ', fg='green') if s['auto_dynamic'] else click.style('OFF', fg='red')
                    click.echo(f"  [{status}] {s['name']}")

                click.echo()

    except Exception as e:
        click.echo(f"Error: {e}")
