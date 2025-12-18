"""
Scene inspection commands.

Commands for viewing detailed scene information and configurations.
"""

import click
from models.utils import create_name_lookup, get_cache_controller


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
