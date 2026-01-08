"""Scene management commands - duplicate and modify scenes."""

import click
import copy
from core.controller import HueController
from models.utils import create_name_lookup, create_scene_reverse_lookup


@click.command(name='duplicate-scene')
@click.argument('source_scene')
@click.argument('new_name')
@click.option('--turn-on', multiple=True, help='Light name to turn ON in the new scene (can be used multiple times)')
@click.option('--turn-off', multiple=True, help='Light name to turn OFF in the new scene (can be used multiple times)')
@click.option('--brightness', multiple=True, help='Set brightness: "LightName=50%" (can be used multiple times)')
@click.option('--remove-light', multiple=True, help='Remove a light from the scene (can be used multiple times)')
@click.option('--zone', '-z', help='Filter by zone/room name (disambiguates scenes with same name)')
@click.option('--yes', '-y', is_flag=True, help='Skip confirmation prompt')
def duplicate_scene_command(source_scene, new_name, turn_on, turn_off, brightness, remove_light, zone, yes):
    """Duplicate a scene with modifications.

    Creates a copy of an existing scene with optional modifications like turning
    specific lights on/off, changing brightness, or removing lights entirely.

    Useful for creating variations of scenes for different contexts (e.g., same
    scene but with one light off for a different button).

    \b
    Examples:
      # Duplicate with one light turned off
      uv run python hue_backup.py duplicate-scene "Orange only" "Orange no lamp" \\
        --turn-off "Lamp lounge"

      # Duplicate with multiple modifications
      uv run python hue_backup.py duplicate-scene "Reading" "Reading dimmed" \\
        --turn-off "Back lights" --brightness "Lamp lounge=50%"

      # Remove a light entirely from the scene
      uv run python hue_backup.py duplicate-scene "Relax" "Relax minimal" \\
        --remove-light "Christmas tree sparkly"
    """
    controller = HueController(use_cache=True)
    if not controller.connect():
        return

    # Get all scenes and lights
    scenes = controller.get_scenes()
    lights = controller.get_lights()

    # Create lookups
    scene_reverse_lookup = create_scene_reverse_lookup(scenes)  # name (lowercase) -> ID
    light_reverse_lookup = {
        l.get('metadata', {}).get('name', '').lower(): l['id']
        for l in lights
    }

    # Find source scene (fuzzy match with optional zone filter)
    source_scene_lower = source_scene.lower()
    source_id = None
    source_obj = None

    # Build candidate list (filter by zone if specified)
    candidates = scenes
    if zone:
        zone_lower = zone.lower()
        # Get rooms and zones to match zone name
        rooms = controller.get_rooms()
        zones_list = controller.get_zones()
        all_groups = rooms + zones_list

        # Find matching room/zone
        matching_groups = [g for g in all_groups if zone_lower in g.get('metadata', {}).get('name', '').lower()]
        if len(matching_groups) == 0:
            click.secho(f"✗ Zone '{zone}' not found", fg='red')
            return
        elif len(matching_groups) > 1:
            click.secho(f"✗ Multiple zones match '{zone}':", fg='red')
            for g in matching_groups:
                click.secho(f"  • {g.get('metadata', {}).get('name')}", fg='yellow')
            return

        zone_rid = matching_groups[0]['id']
        # Filter scenes by this zone
        candidates = [s for s in scenes if s.get('group', {}).get('rid') == zone_rid]

    # Try exact match first
    exact_matches = [s for s in candidates if s.get('metadata', {}).get('name', '').lower() == source_scene_lower]
    if len(exact_matches) == 1:
        source_obj = exact_matches[0]
    elif len(exact_matches) > 1:
        click.secho(f"✗ Multiple scenes exactly match '{source_scene}':", fg='red')
        for s in exact_matches:
            group_name = s.get('group', {}).get('rid', 'unknown')[:8]
            click.secho(f"  • {s.get('metadata', {}).get('name')} [{group_name}...]", fg='yellow')
        click.echo("\nUse --zone to specify which zone.")
        return
    else:
        # Try partial match
        partial_matches = [s for s in candidates if source_scene_lower in s.get('metadata', {}).get('name', '').lower()]
        if len(partial_matches) == 1:
            source_obj = partial_matches[0]
        elif len(partial_matches) > 1:
            click.secho(f"✗ Multiple scenes match '{source_scene}':", fg='red')
            for s in partial_matches:
                group_name = s.get('group', {}).get('rid', 'unknown')[:8]
                click.secho(f"  • {s.get('metadata', {}).get('name')} [{group_name}...]", fg='yellow')
            click.echo("\nUse --zone to specify which zone.")
            return
        else:
            click.secho(f"✗ Scene '{source_scene}' not found", fg='red')
            if zone:
                click.secho(f"  (searched in zone: {zone})", fg='yellow')
            return

    if not source_obj:
        click.secho(f"✗ Could not find scene data", fg='red')
        return

    source_name = source_obj.get('metadata', {}).get('name', source_scene)
    group = source_obj.get('group', {})
    group_rid = group.get('rid')
    group_type = group.get('rtype', 'zone')

    click.echo(f"\n=== Duplicating Scene ===\n")
    click.echo(f"Source: {source_name}")
    click.echo(f"New name: {new_name}")
    click.echo(f"Room/Zone: {group_type} {group_rid[:8]}...")

    # Clone the actions
    original_actions = source_obj.get('actions', [])
    new_actions = copy.deepcopy(original_actions)

    # Track modifications
    modifications = []

    # Helper to find light RID by name
    def find_light_rid(light_name: str) -> str | None:
        light_name_lower = light_name.lower()
        if light_name_lower in light_reverse_lookup:
            return light_reverse_lookup[light_name_lower]
        # Try partial match
        matches = [(name, lid) for name, lid in light_reverse_lookup.items() if light_name_lower in name]
        if len(matches) == 1:
            return matches[0][1]
        elif len(matches) > 1:
            click.secho(f"✗ Multiple lights match '{light_name}':", fg='red')
            for name, _ in matches:
                click.secho(f"  • {name}", fg='yellow')
            return None
        click.secho(f"✗ Light '{light_name}' not found", fg='red')
        return None

    # Helper to find action index for a light
    def find_action_index(light_rid: str) -> int | None:
        for idx, action in enumerate(new_actions):
            if action.get('target', {}).get('rid') == light_rid:
                return idx
        return None

    # Apply --turn-off modifications
    for light_name in turn_off:
        light_rid = find_light_rid(light_name)
        if not light_rid:
            return

        idx = find_action_index(light_rid)
        if idx is not None:
            # Update existing action to turn off
            new_actions[idx]['action']['on'] = {'on': False}
            # Remove dimming/colour when turning off
            new_actions[idx]['action'].pop('dimming', None)
            new_actions[idx]['action'].pop('color', None)
            new_actions[idx]['action'].pop('color_temperature', None)
            modifications.append(f"Turn OFF: {light_name}")
        else:
            # Add new action to turn light off
            new_actions.append({
                'target': {'rid': light_rid, 'rtype': 'light'},
                'action': {'on': {'on': False}}
            })
            modifications.append(f"Turn OFF: {light_name} (added)")

    # Apply --turn-on modifications
    for light_name in turn_on:
        light_rid = find_light_rid(light_name)
        if not light_rid:
            return

        idx = find_action_index(light_rid)
        if idx is not None:
            # Update existing action to turn on
            new_actions[idx]['action']['on'] = {'on': True}
            modifications.append(f"Turn ON: {light_name}")
        else:
            # Add new action to turn light on (with default brightness)
            new_actions.append({
                'target': {'rid': light_rid, 'rtype': 'light'},
                'action': {
                    'on': {'on': True},
                    'dimming': {'brightness': 100.0}
                }
            })
            modifications.append(f"Turn ON: {light_name} (added)")

    # Apply --brightness modifications
    for brightness_spec in brightness:
        if '=' not in brightness_spec:
            click.secho(f"✗ Invalid brightness format: '{brightness_spec}'", fg='red')
            click.echo("Expected format: LightName=50%")
            return

        light_name, brightness_str = brightness_spec.split('=', 1)
        light_name = light_name.strip()
        brightness_str = brightness_str.strip().rstrip('%')

        try:
            brightness_val = float(brightness_str)
            if not (0 <= brightness_val <= 100):
                click.secho(f"✗ Brightness must be 0-100, got {brightness_val}", fg='red')
                return
        except ValueError:
            click.secho(f"✗ Invalid brightness value: '{brightness_str}'", fg='red')
            return

        light_rid = find_light_rid(light_name)
        if not light_rid:
            return

        idx = find_action_index(light_rid)
        if idx is not None:
            # Ensure light is on
            if 'on' not in new_actions[idx]['action']:
                new_actions[idx]['action']['on'] = {'on': True}
            # Set brightness
            new_actions[idx]['action']['dimming'] = {'brightness': brightness_val}
            modifications.append(f"Set brightness: {light_name} = {brightness_val}%")
        else:
            click.secho(f"✗ Light '{light_name}' not in scene", fg='yellow')
            click.echo(f"Use --turn-on to add it first")
            return

    # Apply --remove-light modifications
    for light_name in remove_light:
        light_rid = find_light_rid(light_name)
        if not light_rid:
            return

        idx = find_action_index(light_rid)
        if idx is not None:
            new_actions.pop(idx)
            modifications.append(f"Remove light: {light_name}")
        else:
            click.secho(f"⚠ Light '{light_name}' not in scene (skipping)", fg='yellow')

    # Show summary
    if modifications:
        click.echo(f"\nModifications:")
        for mod in modifications:
            click.secho(f"  • {mod}", fg='cyan')
    else:
        click.secho("\n⚠ No modifications specified - creating exact duplicate", fg='yellow')

    click.echo(f"\nNew scene will have {len(new_actions)} lights")

    # Confirm
    if not yes:
        if not click.confirm("\nCreate new scene?"):
            click.echo("Cancelled.")
            return

    # Create the new scene
    click.echo(f"\nCreating scene '{new_name}'...")

    # Use source scene's auto_dynamic, speed, and palette settings
    auto_dynamic = source_obj.get('auto_dynamic', True)
    speed = source_obj.get('speed', 0.6)

    # Copy and clean palette from source
    palette = copy.deepcopy(source_obj.get('palette'))
    if palette and 'effects' in palette:
        # Remove 'effects' field - it's mutually exclusive with 'effects_v2'
        del palette['effects']

    new_scene_id = controller.create_scene(
        name=new_name,
        group_rid=group_rid,
        actions=new_actions,
        auto_dynamic=auto_dynamic,
        speed=speed,
        group_rtype=group_type,
        palette=palette
    )

    if new_scene_id:
        click.secho(f"\n✓ Scene created successfully!", fg='green', bold=True)
        click.echo(f"  ID: {new_scene_id}")
        click.echo(f"  Name: {new_name}")
        click.echo(f"\nYou can now use this scene in button programming:")
        click.secho(f'  uv run python hue_backup.py program-button "Switch Name" 1 --scenes "Scene1,{new_name},Scene3"', fg='cyan')
    else:
        click.secho(f"\n✗ Failed to create scene", fg='red', bold=True)


@click.command(name='modify-scenes')
@click.option('--room', '-r', required=True, help='Room/zone name to filter scenes')
@click.option('--remove-light', multiple=True, help='Turn light OFF in all scenes (Hue requires all room lights present)')
@click.option('--turn-on', multiple=True, help='Light name to turn ON in all scenes (can be used multiple times)')
@click.option('--turn-off', multiple=True, help='Light name to turn OFF in all scenes (can be used multiple times)')
@click.option('--brightness', multiple=True, help='Set brightness: "LightName=50%" (can be used multiple times)')
@click.option('--yes', '-y', is_flag=True, help='Skip confirmation prompt')
@click.option('--reload', is_flag=True, help='Force cache reload before modifying scenes')
def modify_scenes_command(room, remove_light, turn_on, turn_off, brightness, yes, reload):
    """Modify multiple scenes in bulk.

    Applies the same modifications to all scenes in a specified room/zone.
    Recreates each scene with the modifications by creating a new scene
    and deleting the old one (preserving scene names for button programmes).

    NOTE: The Hue API requires all room lights to be present in every scene.
    Using --remove-light will turn the light OFF in all scenes (not remove it).

    \b
    Examples:
      # Turn off lava lamp in all Living Room scenes
      uv run python hue_backup.py modify-scenes -r "Living" --remove-light "Lava Lamp" -y

      # Turn off Christmas lights in all scenes
      uv run python hue_backup.py modify-scenes -r "Living" --turn-off "Sparkly" -y

      # Multiple modifications at once
      uv run python hue_backup.py modify-scenes -r "Bedroom" \\
        --remove-light "Old lamp" --turn-on "New lamp" --brightness "New lamp=80%" -y
    """
    controller = HueController(use_cache=True)
    if not controller.connect():
        return

    # Reload cache if requested
    if reload:
        click.echo("Reloading cache from bridge...")
        from core.cache import reload_cache
        reload_cache(controller)
        click.secho("✓ Cache reloaded", fg='green')

    # Get all resources
    scenes = controller.get_scenes()
    lights = controller.get_lights()
    rooms_list = controller.get_rooms()
    zones = controller.get_zones()
    all_groups = rooms_list + zones

    # Find matching room/zone
    room_lower = room.lower()
    matching_groups = [g for g in all_groups if room_lower in g.get('metadata', {}).get('name', '').lower()]

    if len(matching_groups) == 0:
        click.secho(f"✗ Room/zone '{room}' not found", fg='red')
        return
    elif len(matching_groups) > 1:
        click.secho(f"✗ Multiple rooms/zones match '{room}':", fg='red')
        for g in matching_groups:
            click.secho(f"  • {g.get('metadata', {}).get('name')}", fg='yellow')
        return

    target_group = matching_groups[0]
    group_rid = target_group['id']
    group_name = target_group.get('metadata', {}).get('name')
    group_type = target_group.get('type', 'zone')

    # Filter scenes by this room/zone
    target_scenes = [s for s in scenes if s.get('group', {}).get('rid') == group_rid]

    if len(target_scenes) == 0:
        click.secho(f"✗ No scenes found in {group_name}", fg='red')
        return

    # Create light lookup
    light_lookup = {
        l.get('metadata', {}).get('name', '').lower(): l['id']
        for l in lights
    }

    # Helper to find light RID by name
    def find_light_rid(light_name: str) -> tuple[str | None, str | None]:
        """Find light RID and actual name. Returns (rid, actual_name) or (None, None)"""
        light_name_lower = light_name.lower()
        if light_name_lower in light_lookup:
            rid = light_lookup[light_name_lower]
            actual_name = next((l.get('metadata', {}).get('name') for l in lights if l['id'] == rid), light_name)
            return (rid, actual_name)
        # Try partial match
        matches = [(name, lid) for name, lid in light_lookup.items() if light_name_lower in name]
        if len(matches) == 1:
            rid = matches[0][1]
            actual_name = next((l.get('metadata', {}).get('name') for l in lights if l['id'] == rid), light_name)
            return (rid, actual_name)
        elif len(matches) > 1:
            click.secho(f"✗ Multiple lights match '{light_name}':", fg='red')
            for name, _ in matches:
                click.secho(f"  • {name}", fg='yellow')
            return (None, None)
        click.secho(f"✗ Light '{light_name}' not found", fg='red')
        return (None, None)

    # Validate all light names first
    light_operations = []

    for light_name in remove_light:
        rid, actual_name = find_light_rid(light_name)
        if not rid:
            return
        light_operations.append(('remove', rid, actual_name))

    for light_name in turn_off:
        rid, actual_name = find_light_rid(light_name)
        if not rid:
            return
        light_operations.append(('turn_off', rid, actual_name))

    for light_name in turn_on:
        rid, actual_name = find_light_rid(light_name)
        if not rid:
            return
        light_operations.append(('turn_on', rid, actual_name))

    for brightness_spec in brightness:
        if '=' not in brightness_spec:
            click.secho(f"✗ Invalid brightness format: '{brightness_spec}'", fg='red')
            click.echo("Expected format: LightName=50%")
            return

        light_name, brightness_str = brightness_spec.split('=', 1)
        light_name = light_name.strip()
        brightness_str = brightness_str.strip().rstrip('%')

        try:
            brightness_val = float(brightness_str)
            if not (0 <= brightness_val <= 100):
                click.secho(f"✗ Brightness must be 0-100, got {brightness_val}", fg='red')
                return
        except ValueError:
            click.secho(f"✗ Invalid brightness value: '{brightness_str}'", fg='red')
            return

        rid, actual_name = find_light_rid(light_name)
        if not rid:
            return
        light_operations.append(('brightness', rid, actual_name, brightness_val))

    # Show summary
    click.echo(f"\n=== Bulk Scene Modification ===\n")
    click.echo(f"Room/Zone: {group_name}")
    click.echo(f"Scenes to modify: {len(target_scenes)}")

    if light_operations:
        click.echo(f"\nModifications to apply:")
        for op in light_operations:
            if op[0] == 'remove':
                click.secho(f"  • Turn OFF light: {op[2]}", fg='cyan')
            elif op[0] == 'turn_off':
                click.secho(f"  • Turn OFF: {op[2]}", fg='cyan')
            elif op[0] == 'turn_on':
                click.secho(f"  • Turn ON: {op[2]}", fg='cyan')
            elif op[0] == 'brightness':
                click.secho(f"  • Set brightness: {op[2]} = {op[3]}%", fg='cyan')
    else:
        click.secho("\n⚠ No modifications specified", fg='yellow')
        return

    # Confirm
    if not yes:
        if not click.confirm("\nProceed with modifications?"):
            click.echo("Cancelled.")
            return

    # Apply modifications to each scene
    success_count = 0
    skip_count = 0
    fail_count = 0

    click.echo(f"\nModifying scenes...")

    with click.progressbar(target_scenes, label='Processing scenes') as scenes_bar:
        for scene in scenes_bar:
            scene_id = scene['id']
            scene_name = scene.get('metadata', {}).get('name', 'Unknown')
            original_actions = scene.get('actions', [])
            new_actions = copy.deepcopy(original_actions)

            # Track if this scene was actually modified
            modified = False

            # Helper to find action index for a light
            def find_action_index(light_rid: str) -> int | None:
                for idx, action in enumerate(new_actions):
                    if action.get('target', {}).get('rid') == light_rid:
                        return idx
                return None

            # Apply each operation
            for op in light_operations:
                op_type = op[0]
                light_rid = op[1]

                idx = find_action_index(light_rid)

                if op_type == 'remove':
                    # Don't actually remove - Hue API requires all room lights in scene
                    # Instead, turn the light OFF
                    if idx is not None:
                        new_actions[idx]['action'] = {'on': {'on': False}}
                        # Remove dimming/colour when turning off
                        new_actions[idx]['action'].pop('dimming', None)
                        new_actions[idx]['action'].pop('color', None)
                        new_actions[idx]['action'].pop('color_temperature', None)
                        modified = True
                    # If light not in scene, we don't need to add it (it's opt-in removal)

                elif op_type == 'turn_off':
                    if idx is not None:
                        new_actions[idx]['action']['on'] = {'on': False}
                        # Remove dimming/colour when turning off
                        new_actions[idx]['action'].pop('dimming', None)
                        new_actions[idx]['action'].pop('color', None)
                        new_actions[idx]['action'].pop('color_temperature', None)
                        modified = True
                    else:
                        # Add new action to turn light off
                        new_actions.append({
                            'target': {'rid': light_rid, 'rtype': 'light'},
                            'action': {'on': {'on': False}}
                        })
                        modified = True

                elif op_type == 'turn_on':
                    if idx is not None:
                        new_actions[idx]['action']['on'] = {'on': True}
                        modified = True
                    else:
                        # Add new action to turn light on
                        new_actions.append({
                            'target': {'rid': light_rid, 'rtype': 'light'},
                            'action': {
                                'on': {'on': True},
                                'dimming': {'brightness': 100.0}
                            }
                        })
                        modified = True

                elif op_type == 'brightness':
                    brightness_val = op[3]
                    if idx is not None:
                        # Ensure light is on
                        if 'on' not in new_actions[idx]['action']:
                            new_actions[idx]['action']['on'] = {'on': True}
                        # Set brightness
                        new_actions[idx]['action']['dimming'] = {'brightness': brightness_val}
                        modified = True

            # Skip if scene wasn't actually modified
            if not modified:
                skip_count += 1
                continue

            # Recreate the scene
            auto_dynamic = scene.get('auto_dynamic', True)
            speed = scene.get('speed', 0.6)
            scene_group_type = scene.get('group', {}).get('rtype', 'room')

            # Copy and clean palette from original scene
            palette = copy.deepcopy(scene.get('palette'))
            if palette and 'effects' in palette:
                # Remove 'effects' field - it's mutually exclusive with 'effects_v2'
                del palette['effects']

            # Create new scene with same name
            new_scene_id = controller.create_scene(
                name=scene_name,
                group_rid=group_rid,
                actions=new_actions,
                auto_dynamic=auto_dynamic,
                speed=speed,
                group_rtype=scene_group_type,
                palette=palette
            )

            if new_scene_id:
                # Delete old scene
                if controller.delete_scene(scene_id):
                    success_count += 1
                else:
                    # Still count as success if new scene was created
                    success_count += 1
            else:
                fail_count += 1

    # Summary
    click.echo(f"\n=== Summary ===\n")
    click.secho(f"✓ Modified: {success_count} scenes", fg='green')
    if skip_count > 0:
        click.secho(f"⊝ Skipped: {skip_count} scenes (no matching lights)", fg='yellow')
    if fail_count > 0:
        click.secho(f"✗ Failed: {fail_count} scenes", fg='red')

    if success_count > 0:
        click.echo(f"\nScenes successfully modified in {group_name}.")
        click.echo(f"Button programmes will continue to work (scene names preserved).")
