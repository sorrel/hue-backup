"""Zone-specific scene programming commands.

Commands for automatically programming switches with zone-filtered scenes.
"""

import click
from models.utils import get_cache_controller
from models.zone_utils import (
    get_zone_lights, find_zone_by_name, filter_scene_actions_for_zone,
    find_lights_by_name, get_light_names_in_zone, generate_zone_scene_name
)


@click.command()
@click.argument('zone_name')
@click.argument('switch_name')
@click.option('--button', '-b', multiple=True, type=int, help='Button numbers to program (e.g., -b 1 -b 2)')
@click.option('--scenes', 'scene_names_str', help='Comma-separated scene names to use (overrides current button scenes)')
@click.option('--exclude-button', multiple=True, help='Button and light to exclude (format: "BUTTON:LIGHT_NAME")')
@click.option('--dry-run', is_flag=True, help='Show what would be done without making changes')
@click.option('-y', '--yes', is_flag=True, help='Skip confirmation prompts')
def program_zone_switch_command(zone_name, switch_name, button, scene_names_str, exclude_button, dry_run, yes):
    """Program a switch with zone-specific auto-dynamic scenes.

    Takes existing scenes from specified buttons and creates zone-filtered versions
    that only control lights in the target zone. All created scenes are set to
    auto-dynamic.

    Examples:

        # Program buttons 1 and 2 for Combined lounge zone
        program-zone-switch "Combined lounge" "The Sparkles" -b 1 -b 2

        # Exclude Back lights from button 2
        program-zone-switch "Combined lounge" "The Sparkles" -b 1 -b 2 \\
            --exclude-button "2:Back lights"
    """
    controller = get_cache_controller()

    if not controller.connect():
        return

    # Validate buttons specified
    if not button:
        click.echo("Error: Must specify at least one button with -b/--button")
        return

    click.secho(f"\n=== Programming Zone Switch ===\n", fg='cyan', bold=True)

    # Step 1: Find zone
    click.echo(f"Looking for zone: {zone_name}")
    zones = controller.get_zones()
    zone, suggestions = find_zone_by_name(zones, zone_name)

    if not zone:
        click.secho(f"✗ Zone '{zone_name}' not found", fg='red')
        if suggestions:
            click.echo("Did you mean one of these?")
            for suggestion in suggestions[:5]:
                click.echo(f"  - {suggestion}")
        return

    zone_id = zone['id']
    zone_display_name = zone.get('metadata', {}).get('name', zone_name)
    click.secho(f"✓ Found zone: {zone_display_name}", fg='green')

    # Step 2: Get zone lights
    zone_lights = get_zone_lights(zone)
    lights_list = controller.get_lights()
    light_lookup = get_light_names_in_zone(zone, lights_list)

    click.echo(f"  Zone has {len(zone_lights)} lights:")
    for light_rid, light_name in light_lookup.items():
        click.echo(f"    • {light_name}")

    # Step 3: Find switch/device
    click.echo(f"\nLooking for switch: {switch_name}")
    behaviours = controller.get_behaviour_instances()
    devices = controller.get_devices()
    switch_behaviour = None

    # First try to find by behaviour name
    for behaviour in behaviours:
        behaviour_name = behaviour.get('metadata', {}).get('name', '')
        if switch_name.lower() in behaviour_name.lower():
            switch_behaviour = behaviour
            break

    # If not found by name, try to find device by name, then find its behaviour
    if not switch_behaviour:
        click.echo(f"  Not found by behaviour name, searching devices...")
        target_device = None
        for device in devices:
            device_name = device.get('metadata', {}).get('name', '')
            if switch_name.lower() in device_name.lower():
                target_device = device
                click.echo(f"  Found device: {device_name}")
                break

        if target_device:
            device_id = target_device.get('id')
            # Find behaviour that references this device
            for behaviour in behaviours:
                config = behaviour.get('configuration', {})
                if config.get('device', {}).get('rid') == device_id:
                    switch_behaviour = behaviour
                    click.echo(f"  Found behaviour for device: {behaviour.get('metadata', {}).get('name', 'Unknown')}")
                    break

    if not switch_behaviour:
        click.secho(f"✗ Switch '{switch_name}' not found", fg='red')
        return

    switch_display_name = switch_behaviour.get('metadata', {}).get('name', switch_name)
    switch_id = switch_behaviour['id']
    click.secho(f"✓ Found switch: {switch_display_name}", fg='green')

    # Step 4: Parse exclusion rules
    exclusions = {}  # {button_num: [light_rid, ...]}
    for exclusion in exclude_button:
        if ':' not in exclusion:
            click.secho(f"✗ Invalid exclusion format: '{exclusion}' (use BUTTON:LIGHT_NAME)", fg='red')
            return

        button_num, light_name = exclusion.split(':', 1)
        button_num = int(button_num)

        # Find light RID by name
        matching_lights = find_lights_by_name(lights_list, light_name)
        if not matching_lights:
            click.secho(f"✗ Light '{light_name}' not found", fg='red')
            return

        if button_num not in exclusions:
            exclusions[button_num] = []
        exclusions[button_num].extend(matching_lights)

    # Step 5: Process each button
    click.echo(f"\nProcessing buttons: {', '.join(str(b) for b in button)}")

    scenes = controller.get_scenes()
    scene_lookup = {s['id']: s for s in scenes}

    # Get current button configuration
    config = switch_behaviour.get('configuration', {})

    button_configs = {}  # Store new configurations
    created_scenes = []  # Track created scenes

    # If --scenes provided, use those instead of reading from buttons
    if scene_names_str:
        # Parse comma-separated scene names
        scene_names = [s.strip() for s in scene_names_str.split(',')]
        click.echo(f"\nUsing provided scenes: {', '.join(scene_names)}")

        # Find scene IDs by name
        provided_scene_ids = []
        for scene_name in scene_names:
            matching = [s for s in scene_lookup.values() if s.get('metadata', {}).get('name') == scene_name]
            if matching:
                provided_scene_ids.append(matching[0]['id'])
            else:
                click.secho(f"  ⚠ Scene '{scene_name}' not found", fg='yellow')
    else:
        provided_scene_ids = None

    for button_num in sorted(button):
        click.echo(f"\n--- Button {button_num} ---")

        button_key = f'button{button_num}'

        # Get current scenes for this button (or use provided scenes)
        if provided_scene_ids:
            current_scene_ids = provided_scene_ids
            click.echo(f"  Using {len(current_scene_ids)} provided scenes")
        else:
            if button_key not in config:
                click.secho(f"✗ Button {button_num} not found in switch configuration", fg='red')
                continue

            button_config = config[button_key]

            # Detect button type
            button_type = None
            if 'on_short_release' in button_config:
                on_short = button_config['on_short_release']
                if 'scene_cycle_extended' in on_short:
                    button_type = 'scene_cycle'
                elif 'scene' in on_short:
                    button_type = 'single_scene'
                elif 'time_based_light_scene_extended' in on_short:
                    button_type = 'time_based'

            if button_type:
                click.echo(f"  Current type: {button_type}")

            # Extract scene IDs from button configuration
            current_scene_ids = []

            # Check for scene_cycle_extended format (new format)
            if 'on_short_release' in button_config:
                on_short = button_config['on_short_release']
                if 'scene_cycle_extended' in on_short:
                    slots = on_short['scene_cycle_extended'].get('slots', [])
                    for slot in slots:
                        # Slot can be either a list or a dict
                        if isinstance(slot, list):
                            # If it's a list, get the first element
                            if slot and len(slot) > 0:
                                slot_dict = slot[0]
                            else:
                                continue
                        else:
                            slot_dict = slot

                        action = slot_dict.get('action', {})
                        recall = action.get('recall', {})
                        scene_ref = recall.get('rid') or recall
                        if isinstance(scene_ref, dict):
                            scene_id = scene_ref.get('rid')
                        else:
                            scene_id = scene_ref
                        if scene_id:
                            current_scene_ids.append(scene_id)

            if not current_scene_ids:
                click.secho(f"  No scenes found on button {button_num}", fg='yellow')
                continue

        click.echo(f"  Current scenes: {len(current_scene_ids)}")
        for scene_id in current_scene_ids:
            scene = scene_lookup.get(scene_id)
            if scene:
                scene_name = scene.get('metadata', {}).get('name', 'Unknown')
                click.echo(f"    • {scene_name}")

        # Determine exclusions for this button
        button_exclusions = exclusions.get(button_num, [])
        if button_exclusions:
            excluded_names = [light_lookup.get(rid, rid) for rid in button_exclusions]
            click.echo(f"  Excluding lights: {', '.join(excluded_names)}")

        # Create zone-filtered versions of each scene
        new_scene_ids = []

        for scene_id in current_scene_ids:
            scene = scene_lookup.get(scene_id)
            if not scene:
                click.secho(f"  ✗ Scene {scene_id} not found in cache", fg='yellow')
                continue

            original_name = scene.get('metadata', {}).get('name', 'Unknown')

            # Filter actions to zone lights
            filtered_actions = filter_scene_actions_for_zone(
                scene, zone_lights, button_exclusions
            )

            if not filtered_actions:
                click.secho(f"  ✗ Scene '{original_name}' has no lights in zone", fg='yellow')
                continue

            # Generate zone-specific scene name
            zone_scene_name = generate_zone_scene_name(
                original_name, zone_display_name, button_exclusions, light_lookup
            )

            # Check if zone scene already exists
            existing_zone_scene = None
            for s in scenes:
                if s.get('metadata', {}).get('name') == zone_scene_name:
                    existing_zone_scene = s
                    break

            if existing_zone_scene:
                click.echo(f"  ✓ Reusing existing scene: {zone_scene_name}")
                new_scene_id = existing_zone_scene['id']
            else:
                if dry_run:
                    click.echo(f"  → Would create: {zone_scene_name} ({len(filtered_actions)} lights)")
                    new_scene_id = f"DRY_RUN_{scene_id}"
                else:
                    click.echo(f"  → Creating: {zone_scene_name} ({len(filtered_actions)} lights)")
                    new_scene_id = controller.create_scene(
                        name=zone_scene_name,
                        group_rid=zone_id,
                        actions=filtered_actions,
                        auto_dynamic=True,
                        speed=scene.get('speed', 0.6)
                    )

                    if new_scene_id:
                        click.secho(f"    ✓ Created scene: {new_scene_id}", fg='green')
                        created_scenes.append((new_scene_id, zone_scene_name))
                    else:
                        click.secho(f"    ✗ Failed to create scene", fg='red')
                        continue

            new_scene_ids.append(new_scene_id)

        # Store new button configuration
        # Get original button config if it exists, or create minimal one
        if provided_scene_ids:
            # When using provided scenes, always create scene_cycle_extended structure
            # Start with existing button config (keeps where, on_long_press, etc.)
            import copy
            original_button_config = copy.deepcopy(config.get(button_key, {}))
            # Replace on_short_release with scene_cycle_extended format
            original_button_config['on_short_release'] = {
                'scene_cycle_extended': {
                    'slots': [],
                    'with_off': {
                        'enabled': False
                    }
                }
            }
        else:
            original_button_config = button_config

        button_configs[button_num] = {
            'scene_ids': new_scene_ids,
            'original_config': original_button_config
        }

    # Step 6: Show summary and confirm
    click.echo(f"\n=== Summary ===\n")
    click.echo(f"Zone:   {zone_display_name} ({len(zone_lights)} lights)")
    click.echo(f"Switch: {switch_display_name}")
    click.echo(f"Buttons to program: {', '.join(str(b) for b in button)}")

    if created_scenes:
        click.echo(f"\nCreated {len(created_scenes)} new scenes:")
        for scene_id, scene_name in created_scenes:
            click.echo(f"  • {scene_name}")

    if dry_run:
        click.secho("\n[DRY RUN - No changes made]", fg='yellow', bold=True)
        return

    if not yes:
        if not click.confirm("\nProceed with programming the switch?"):
            click.echo("Cancelled.")
            return

    # Step 7: Update behaviour instance
    click.echo(f"\nUpdating switch configuration...")

    # Build new configuration with deep copy
    import copy
    new_config = copy.deepcopy(config)

    for button_num, button_data in button_configs.items():
        button_key = f'button{button_num}'
        original = button_data['original_config']
        new_scene_ids = button_data['scene_ids']

        # Always use the original_config which has been properly formatted
        new_config[button_key] = copy.deepcopy(original)

        # Update the configuration with new scene IDs
        if 'on_short_release' in original:
            if 'scene_cycle_extended' in original['on_short_release']:
                # Build new slots with new scene IDs
                # Match the original format: each slot is a list containing one dict
                new_slots = []
                for scene_id in new_scene_ids:
                    new_slots.append([{
                        'action': {
                            'recall': {
                                'rid': scene_id,
                                'rtype': 'scene'
                            }
                        }
                    }])

                new_config[button_key]['on_short_release']['scene_cycle_extended']['slots'] = new_slots

    # Update the behaviour instance using DELETE + POST approach
    # (PUT cannot change button action types, only update existing scene-cycles)
    click.echo(f"\nUpdating switch configuration...")

    # Get current behaviour instance for script_id and metadata
    current_behaviour = controller._request('GET', f'/resource/behavior_instance/{switch_id}')
    if not current_behaviour:
        click.secho("\n✗ Failed to get current behaviour instance", fg='red', bold=True)
        return

    behaviour_data = current_behaviour[0]

    # DELETE current instance
    delete_result = controller._request('DELETE', f'/resource/behavior_instance/{switch_id}')
    if not delete_result:
        click.secho("\n✗ Failed to delete behaviour instance", fg='red', bold=True)
        return

    # POST new instance with updated configuration
    post_payload = {
        "script_id": behaviour_data['script_id'],
        "enabled": True,
        "configuration": new_config,
        "metadata": behaviour_data['metadata']
    }

    post_result = controller._request('POST', '/resource/behavior_instance', post_payload)
    success = post_result is not None and len(post_result) > 0

    if success:
        click.secho(f"\n✓ Switch programming updated successfully!", fg='green', bold=True)
        click.echo(f"\nButtons {', '.join(str(b) for b in button)} now control {zone_display_name} lights only")
        click.echo("All scenes set to auto-dynamic")
    else:
        click.secho(f"\n✗ Failed to update switch configuration", fg='red', bold=True)
