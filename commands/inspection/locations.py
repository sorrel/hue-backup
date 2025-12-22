"""Location inspection commands - show rooms and zones with their lights and scenes."""

import click
from core.controller import HueController
from models.utils import find_similar_strings


@click.command(name='locations')
@click.option('--lights', is_flag=True, help='Show lights in each location')
@click.option('--scenes', is_flag=True, help='Show scenes in each location')
@click.option('-r', '--room', help='Filter by room/zone name (fuzzy match)')
def locations_command(lights, scenes, room):
    """Show all rooms and zones with optional lights and scenes.

    Displays all locations (rooms and zones) in your Hue setup. Use --lights
    to see which lights are in each location, and --scenes to see which scenes
    are programmed for each location.

    \b
    Examples:
      # List all rooms and zones
      uv run python hue_backup.py locations

      # Show rooms/zones with their lights
      uv run python hue_backup.py locations --lights

      # Show rooms/zones with their scenes
      uv run python hue_backup.py locations --scenes

      # Show everything for a specific location
      uv run python hue_backup.py locations --lights --scenes -r "Christmas"

      # Filter by name
      uv run python hue_backup.py locations -r "lounge"
    """
    controller = HueController(use_cache=True)
    if not controller.connect():
        return

    # Ensure cache is fresh (auto-reload if stale)
    if not controller.ensure_fresh_cache():
        click.echo("Failed to ensure fresh cache.")
        return

    # Get all data
    rooms = controller.get_rooms()
    zones = controller.get_zones()
    all_scenes = controller.get_scenes() if scenes else []
    all_lights = controller.get_lights() if lights else []

    # Combine rooms and zones
    all_locations = []

    for r in rooms:
        all_locations.append({
            'type': 'room',
            'id': r['id'],
            'name': r.get('metadata', {}).get('name', 'Unknown'),
            'children': r.get('children', [])
        })

    for z in zones:
        all_locations.append({
            'type': 'zone',
            'id': z['id'],
            'name': z.get('metadata', {}).get('name', 'Unknown'),
            'children': z.get('children', [])
        })

    # Filter by room name if specified (fuzzy match)
    if room:
        # Get all location names for fuzzy matching
        location_names = [loc['name'] for loc in all_locations]

        # Find similar names (returns up to 5 matches by default)
        similar_names = find_similar_strings(room, location_names, limit=10)

        if not similar_names:
            click.secho(f"✗ No rooms or zones match '{room}'", fg='red')
            return

        # Filter to only include matching locations
        all_locations = [loc for loc in all_locations if loc['name'] in similar_names]

    if not all_locations:
        click.echo("No rooms or zones found.")
        return

    # Sort by name
    all_locations.sort(key=lambda x: x['name'])

    # Display header
    click.echo()
    click.secho("=== Rooms & Zones ===", fg='cyan', bold=True)
    click.echo()

    if room:
        click.echo(f"Filtered by: {room}")
        click.echo()

    # Display each location
    for loc in all_locations:
        # Header with type indicator
        type_indicator = "[Room]" if loc['type'] == 'room' else "[Zone]"
        click.secho(f"{loc['name']} {type_indicator}", fg='green', bold=True)
        click.echo(f"  ID: {loc['id'][:8]}...")

        # Show lights if requested
        if lights:
            light_rids = [child['rid'] for child in loc['children'] if child.get('rtype') == 'light']
            if light_rids:
                click.echo(f"  Lights ({len(light_rids)}):")
                for light_rid in light_rids:
                    light_obj = next((l for l in all_lights if l['id'] == light_rid), None)
                    if light_obj:
                        light_name = light_obj.get('metadata', {}).get('name', 'Unknown')
                        on_state = light_obj.get('on', {}).get('on', False)
                        state_icon = "●" if on_state else "○"
                        click.echo(f"    {state_icon} {light_name}")
            else:
                click.echo("  Lights: None")

        # Show scenes if requested
        if scenes:
            # Find all scenes for this location
            location_scenes = [s for s in all_scenes if s.get('group', {}).get('rid') == loc['id']]
            if location_scenes:
                click.echo(f"  Scenes ({len(location_scenes)}):")
                for scene in sorted(location_scenes, key=lambda x: x.get('metadata', {}).get('name', '')):
                    scene_name = scene.get('metadata', {}).get('name', 'Unknown')
                    num_actions = len(scene.get('actions', []))
                    click.echo(f"    • {scene_name} ({num_actions} lights)")
            else:
                click.echo("  Scenes: None")

        click.echo()

    # Summary
    num_rooms = sum(1 for loc in all_locations if loc['type'] == 'room')
    num_zones = sum(1 for loc in all_locations if loc['type'] == 'zone')

    click.secho(f"Total: {num_rooms} rooms, {num_zones} zones", fg='cyan')
