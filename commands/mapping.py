"""
Button mapping commands for switch-to-scene mappings and monitoring.

These commands manage local button-to-scene mappings configured in this CLI tool.
"""

import click
import time
from core.controller import HueController


@click.command()
@click.argument('sensor_id')
@click.argument('button_event', type=int)
@click.argument('scene_id')
def map_command(sensor_id: str, button_event: int, scene_id: str):
    """Map a button event to a scene.

    \b
    Examples:
      uv run python hue_backup.py map 2 1002 abc123
      This maps button event 1002 on sensor 2 to scene abc123.

    \b
    To find values:
      - Use 'switches' to see sensor IDs
      - Use 'discover' to find button event codes
      - Use 'scenes' to see scene IDs
    """
    controller = HueController()
    if not controller.connect():
        return

    # Verify sensor exists
    sensors = controller.get_sensors()
    if sensor_id not in sensors:
        click.echo(f"Error: Sensor ID '{sensor_id}' not found.")
        click.echo("Use 'switches' command to see available sensors.")
        click.echo()
        return

    # Verify scene exists
    scenes = controller.get_scenes()
    if scene_id not in scenes:
        click.echo(f"Error: Scene ID '{scene_id}' not found.")
        click.echo("Use 'scenes' command to see available scenes.")
        click.echo()
        return

    # Create mapping
    controller.map_button_to_scene(sensor_id, button_event, scene_id)

    sensor_name = sensors[sensor_id].get('name', 'Unknown')
    scene_name = scenes[scene_id].get('name', 'Unknown')

    click.echo(f"\n✓ Mapping created:")
    click.echo(f"  Switch: {sensor_name} (ID: {sensor_id})")
    click.echo(f"  Button event: {button_event}")
    click.echo(f"  Scene: {scene_name} (ID: {scene_id})")
    click.echo(f"\nRun 'monitor' to activate this mapping.")


@click.command()
def mappings_command():
    """List all current button-to-scene mappings."""
    controller = HueController()
    if not controller.connect():
        return

    if not controller.button_mappings:
        click.echo("No button mappings configured yet.")
        click.echo("\nUse 'map' command to create mappings.")
        click.echo()
        return

    sensors = controller.get_sensors()
    scenes = controller.get_scenes()

    click.echo("\nConfigured button mappings:\n")
    for mapping_key, scene_id in controller.button_mappings.items():
        sensor_id, button_event = mapping_key.split(':')

        sensor_name = sensors.get(sensor_id, {}).get('name', 'Unknown')
        scene_name = scenes.get(scene_id, {}).get('name', 'Unknown')

        click.echo(f"  • {sensor_name} (ID: {sensor_id})")
        click.echo(f"    Button event: {button_event}")
        click.echo(f"    → Scene: {scene_name} (ID: {scene_id})")
        click.echo()


@click.command()
def discover_command():
    """Discover button events by pressing buttons on your switches.

    This helps you find out which button event codes are generated
    when you press different buttons on your switches.
    """
    controller = HueController()
    if not controller.connect():
        return

    click.echo("Press buttons on your switches to see their event codes...\n")

    def on_button_event(sensor_id, event_data):
        click.echo(f"Button pressed!")
        click.echo(f"  Switch: {event_data['name']} (ID: {sensor_id})")
        click.echo(f"  Event code: {event_data['buttonevent']}")
        click.echo()

    controller.monitor_buttons(on_button_event)


@click.command()
def monitor_command():
    """Monitor switches and activate mapped scenes when buttons are pressed.

    This is the main runtime command that watches for button presses
    and triggers the scenes you've configured with the 'map' command.
    """
    controller = HueController()
    if not controller.connect():
        return

    if not controller.button_mappings:
        click.echo("No button mappings configured.")
        click.echo("Use 'map' command to set up mappings first.")
        click.echo()
        return

    click.echo("Active mappings:")
    sensors = controller.get_sensors()
    scenes = controller.get_scenes()

    for mapping_key, scene_id in controller.button_mappings.items():
        sensor_id, button_event = mapping_key.split(':')
        sensor_name = sensors.get(sensor_id, {}).get('name', 'Unknown')
        scene_name = scenes.get(scene_id, {}).get('name', 'Unknown')
        click.echo(f"  • {sensor_name} button {button_event} → {scene_name}")

    click.echo()

    def on_button_event(sensor_id, event_data):
        button_event = event_data['buttonevent']
        mapping_key = f"{sensor_id}:{button_event}"

        if mapping_key in controller.button_mappings:
            scene_id = controller.button_mappings[mapping_key]
            scene_name = scenes.get(scene_id, {}).get('name', 'Unknown')

            click.echo(f"[{time.strftime('%H:%M:%S')}] {event_data['name']} → Activating '{scene_name}'")

            if not controller.activate_scene(scene_id):
                click.echo(f"  Error: Failed to activate scene")

    controller.monitor_buttons(on_button_event)


@click.command(name='program-button')
@click.argument('switch_name')
@click.argument('button_number', type=click.IntRange(1, 4))
@click.option('--scenes', '-s', help='Comma-separated scene names for scene cycle (e.g., "Read,Concentrate,Relax")')
@click.option('--time-based', is_flag=True, help='Enable time-based schedule mode (uses default schedule if --slot not specified)')
@click.option('--slot', multiple=True, help='Time slot: HH:MM=SceneName (requires --time-based, can be used multiple times). Omit to use default schedule.')
@click.option('--scene', help='Single scene to activate on button press')
@click.option('--dim-up', is_flag=True, help='Configure button for dim up (hold/repeat action)')
@click.option('--dim-down', is_flag=True, help='Configure button for dim down (hold/repeat action)')
@click.option('--where', help='Zone or room name to control (for dim-up/dim-down buttons)')
@click.option('--long-press', help='Scene name or action for long press (e.g., "All Off", "Home Off", or scene name)')
@click.option('--yes', '-y', is_flag=True, help='Skip confirmation prompt')
@click.option('--auto-reload/--no-auto-reload', default=True, help='Auto-reload stale cache (default: yes)')
def program_button_command(switch_name, button_number, scenes, time_based, slot,
                           scene, dim_up, dim_down, where, long_press, yes, auto_reload):
    """Programme a button on a Hue switch to perform an action.

    This modifies the bridge-native button configuration (not local CLI mappings).
    Use for seasonal programming workflows: save → modify → restore.

    \b
    BUTTON NUMBERS:
      1 = ON button
      2 = DIM UP button
      3 = DIM DOWN button
      4 = OFF button

    \b
    Examples:
      # Scene cycle
      uv run python hue_backup.py program-button "Office dimmer" 1 \\
        --scenes "Read,Concentrate,Relax"

      # Time-based schedule (custom slots)
      uv run python hue_backup.py program-button "Living dimmer" 1 --time-based \\
        --slot 07:00="Morning" --slot 17:00="Evening" --slot 23:00="Night"

      # Time-based schedule (default: 07:00=Energise, 10:00=Concentrate, 17:00=Read, 20:00=Relax, 23:00=Nightlight)
      uv run python hue_backup.py program-button "Living dimmer" 1 --time-based

      # Single scene
      uv run python hue_backup.py program-button "Bedroom dimmer" 4 \\
        --scene "Relax"

      # Dimming actions (--dim-up/--dim-down are optional, auto-detected for buttons 2/3)
      uv run python hue_backup.py program-button "Office dimmer" 2
      uv run python hue_backup.py program-button "Office dimmer" 3

      # Dimming with zone control (change which lights the dim buttons control)
      uv run python hue_backup.py program-button "Office dimmer" 2 --where "Upstairs"
      uv run python hue_backup.py program-button "Office dimmer" 3 --where "Upstairs"

      # Long press
      uv run python hue_backup.py program-button "Office dimmer" 1 \\
        --scenes "Read,Relax" --long-press "All Off"
    """
    from models.button_config import (
        validate_program_button_args, find_switch_behaviour, get_all_switch_names,
        resolve_scene_names, parse_time_slot, build_scene_cycle_config,
        build_time_based_config, build_single_scene_config, build_dimming_config,
        build_long_press_config, update_button_configuration
    )
    from models.utils import find_similar_strings

    # 1. Auto-detect dim action for buttons 2 and 3 if not specified
    if button_number == 2 and not any([scenes, time_based, scene, dim_up, dim_down]):
        dim_up = True
    elif button_number == 3 and not any([scenes, time_based, scene, dim_up, dim_down]):
        dim_down = True

    # 2. Validate arguments
    is_valid, error_msg = validate_program_button_args(
        button_number, scenes, time_based, slot, scene, dim_up, dim_down, long_press
    )
    if not is_valid:
        click.secho(f"✗ {error_msg}", fg='red')
        click.echo("\nRun 'program-button --help' for usage information")
        return

    # 3. Connect to bridge (cache for reading)
    cache_controller = HueController(use_cache=True)
    if auto_reload:
        if not cache_controller.ensure_fresh_cache():
            click.echo("Failed to ensure fresh cache.")
            return

    # 4. Find switch behaviour instance
    if (result := find_switch_behaviour(switch_name, cache_controller)) is None:
        # Check if no matches or multiple matches
        all_switches = get_all_switch_names(cache_controller)

        if not any(switch_name.lower() in s.lower() for s in all_switches):
            # No programmed switches match
            click.secho(f"✗ Switch '{switch_name}' not found", fg='red')

            # Check if it exists as an unprogrammed device
            devices = cache_controller.get_devices()
            matching_devices = [
                d for d in devices
                if switch_name.lower() in d.get('metadata', {}).get('name', '').lower()
            ]

            if matching_devices:
                device_name = matching_devices[0].get('metadata', {}).get('name', '')
                click.echo(f"\n'{device_name}' exists but hasn't been programmed yet.")
                click.echo("Please use the Hue app to set up initial button configuration, then use this tool to modify it.")
                return

            # No unprogrammed device either - show similar switches
            similar = find_similar_strings(switch_name, all_switches, limit=3)
            if similar:
                click.echo("\nDid you mean one of these?")
                for name in similar:
                    click.secho(f"  • {name}", fg='green')
            else:
                click.echo("\nAvailable switches:")
                for name in all_switches[:10]:
                    click.secho(f"  • {name}", fg='green')
                if len(all_switches) > 10:
                    click.echo(f"  ... and {len(all_switches) - 10} more")
            return
        else:
            # Multiple programmed switches match
            matches = [s for s in all_switches if switch_name.lower() in s.lower()]
            click.secho(f"✗ Multiple switches match '{switch_name}':", fg='red')
            for name in matches:
                click.secho(f"  • {name}", fg='yellow')
            click.echo("\nPlease be more specific.")
            return

    # Extract from SwitchBehaviour TypedDict
    behaviour = result['behaviour']
    device_name = result['device_name']
    device = result['device']
    instance_id = behaviour['id']

    # 5. Build button configuration based on action type
    button_config = {}
    short_press_desc = None
    long_press_desc = None

    all_scenes = cache_controller.get_scenes()

    # Handle short press action
    if scenes:
        # Scene cycle
        scene_names = [s.strip() for s in scenes.split(',')]
        scene_ids = resolve_scene_names(scene_names, all_scenes)
        if not scene_ids:
            return  # Error already shown

        button_config.update(build_scene_cycle_config(scene_ids))
        short_press_desc = f"Cycle through {len(scene_names)} scenes: {', '.join(scene_names)}"

    elif time_based:
        # Time-based schedule
        from models.button_config import DEFAULT_TIME_SLOTS

        # Use default slots if none specified
        slots_to_use = slot if slot else DEFAULT_TIME_SLOTS

        time_slots_parsed = []
        for slot_str in slots_to_use:
            try:
                hour, minute, scene_name = parse_time_slot(slot_str)
                time_slots_parsed.append((hour, minute, scene_name))
            except ValueError as e:
                click.secho(f"✗ {e}", fg='red')
                click.echo("\nExpected format: HH:MM=SceneName")
                click.echo("Example: --slot 07:00=\"Morning\" --slot 20:00=\"Evening\"")
                return

        # Resolve scene names in time slots
        time_scene_names = [ts[2] for ts in time_slots_parsed]
        time_scene_ids = resolve_scene_names(time_scene_names, all_scenes)
        if not time_scene_ids:
            return

        # Replace scene names with IDs
        time_slots_with_ids = [
            (hour, minute, scene_id)
            for (hour, minute, _), scene_id in zip(time_slots_parsed, time_scene_ids)
        ]

        button_config.update(build_time_based_config(time_slots_with_ids))
        if slot:
            short_press_desc = f"Time-based schedule ({len(time_slots_with_ids)} slots)"
        else:
            short_press_desc = f"Time-based schedule (default: {len(time_slots_with_ids)} slots)"

    elif scene:
        # Single scene
        scene_ids = resolve_scene_names([scene], all_scenes)
        if not scene_ids:
            return

        button_config.update(build_single_scene_config(scene_ids[0]))
        short_press_desc = f"Activate scene: {scene}"

    elif dim_up:
        # Resolve zone/room for dimming if specified
        where_rid, where_rtype, where_name = None, None, None
        if where:
            # Try zones first - prefer exact matches
            zones = cache_controller.get_zones()
            exact_match = None
            substring_match = None

            for zone in zones:
                zone_name = zone.get('metadata', {}).get('name', '')
                if where.lower() == zone_name.lower():
                    exact_match = (zone['id'], 'zone', zone_name)
                    break
                elif where.lower() in zone_name.lower() and not substring_match:
                    substring_match = (zone['id'], 'zone', zone_name)

            if exact_match:
                where_rid, where_rtype, where_name = exact_match
            elif substring_match:
                where_rid, where_rtype, where_name = substring_match

            # Try rooms if not found in zones
            if not where_rid:
                rooms = cache_controller.get_rooms()
                exact_match = None
                substring_match = None

                for room in rooms:
                    room_name = room.get('metadata', {}).get('name', '')
                    if where.lower() == room_name.lower():
                        exact_match = (room['id'], 'room', room_name)
                        break
                    elif where.lower() in room_name.lower() and not substring_match:
                        substring_match = (room['id'], 'room', room_name)

                if exact_match:
                    where_rid, where_rtype, where_name = exact_match
                elif substring_match:
                    where_rid, where_rtype, where_name = substring_match

            if not where_rid:
                click.secho(f"✗ Zone/room '{where}' not found", fg='red')
                return

        button_config.update(build_dimming_config('dim_up', where_rid, where_rtype))
        short_press_desc = f"Dim up (hold to brighten){f' - {where_name}' if where_name else ''}"

    elif dim_down:
        # Resolve zone/room for dimming if specified
        where_rid, where_rtype, where_name = None, None, None
        if where:
            # Try zones first - prefer exact matches
            zones = cache_controller.get_zones()
            exact_match = None
            substring_match = None

            for zone in zones:
                zone_name = zone.get('metadata', {}).get('name', '')
                if where.lower() == zone_name.lower():
                    exact_match = (zone['id'], 'zone', zone_name)
                    break
                elif where.lower() in zone_name.lower() and not substring_match:
                    substring_match = (zone['id'], 'zone', zone_name)

            if exact_match:
                where_rid, where_rtype, where_name = exact_match
            elif substring_match:
                where_rid, where_rtype, where_name = substring_match

            # Try rooms if not found in zones
            if not where_rid:
                rooms = cache_controller.get_rooms()
                exact_match = None
                substring_match = None

                for room in rooms:
                    room_name = room.get('metadata', {}).get('name', '')
                    if where.lower() == room_name.lower():
                        exact_match = (room['id'], 'room', room_name)
                        break
                    elif where.lower() in room_name.lower() and not substring_match:
                        substring_match = (room['id'], 'room', room_name)

                if exact_match:
                    where_rid, where_rtype, where_name = exact_match
                elif substring_match:
                    where_rid, where_rtype, where_name = substring_match

            if not where_rid:
                click.secho(f"✗ Zone/room '{where}' not found", fg='red')
                return

        button_config.update(build_dimming_config('dim_down', where_rid, where_rtype))
        short_press_desc = f"Dim down (hold to dim){f' - {where_name}' if where_name else ''}"

    # Handle long press action
    if long_press:
        valid_actions = ['all off', 'home off', 'all_off', 'home_off']
        if long_press.lower() in valid_actions:
            button_config.update(build_long_press_config(long_press, None))
            long_press_desc = long_press.title()
        else:
            # Assume it's a scene name
            lp_scene_ids = resolve_scene_names([long_press], all_scenes)
            if not lp_scene_ids:
                return

            button_config.update(build_long_press_config(long_press, lp_scene_ids[0]))
            long_press_desc = f"Activate scene: {long_press}"

    # 6. Show confirmation preview
    button_labels = {1: 'ON', 2: 'DIM UP', 3: 'DIM DOWN', 4: 'OFF'}
    button_label = button_labels.get(button_number, str(button_number))

    click.echo()
    click.secho("=== Button Programme Configuration ===", fg='cyan', bold=True)
    click.echo()
    click.echo(f"Switch:  {click.style(device_name, fg='green')}")
    click.echo(f"Button:  {click.style(f'{button_number} ({button_label})', fg='yellow')}")
    click.echo()

    if short_press_desc:
        click.echo(f"Short press:  {short_press_desc}")
        if time_based:
            # Show time slots
            for hour, minute, scene_id in sorted(time_slots_with_ids, key=lambda x: (x[0], x[1])):
                scene_name = next((s.get('metadata', {}).get('name', 'Unknown')
                                  for s in all_scenes if s['id'] == scene_id), 'Unknown')
                click.echo(f"              {hour:02d}:{minute:02d} → {scene_name}")

    if long_press_desc:
        click.echo(f"Long press:   {long_press_desc}")

    click.echo()

    if not yes:
        if not click.confirm("Proceed with programming this button?", default=True):
            click.echo("Cancelled.")
            return

    # 7. Update behaviour instance with write-through cache
    write_controller = HueController()  # Non-cache for writes
    if not write_controller.connect():
        return

    # Get button resources for RID lookup
    buttons = write_controller.get_buttons()
    button_lookup = {b['id']: b for b in buttons}

    try:
        updated_config = update_button_configuration(
            behaviour, button_number, button_config, button_lookup
        )
    except ValueError as e:
        click.secho(f"✗ {e}", fg='red')
        click.echo(f"\nUse 'button-data -r \"{device_name}\"' to see available buttons.")
        return

    # Apply changes via write-through cache
    if write_controller.update_behaviour_instance(instance_id, updated_config):
        click.echo()
        click.secho(f"✓ Button configuration updated successfully", fg='green')
        click.echo()
        click.echo(f"Switch:  {device_name}")
        click.echo(f"Button:  {button_number} - {button_label}")
        if short_press_desc:
            click.echo(f"Action:  {short_press_desc}")
        if long_press_desc:
            click.echo(f"Long:    {long_press_desc}")
        click.echo()
        click.echo("Press the button on your physical switch to test the new configuration.")
    else:
        click.secho(f"✗ Failed to update button configuration", fg='red')
        click.echo("\nPossible reasons:")
        click.echo("  • Bridge connection lost")
        click.echo("  • Invalid configuration (check logs)")
        click.echo("  • Scene IDs no longer valid")
