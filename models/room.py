"""Room configuration operations.

This module handles saving, comparing, and (future) restoring room configurations.
Room configurations include metadata, lights, scenes, and behaviour instances.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
import click

if TYPE_CHECKING:
    from hue_backup import HueController

# Constants
SAVED_ROOMS_DIR = Path(__file__).parent.parent / 'cache' / 'saved-rooms'


def save_room_configuration(controller: 'HueController', room_name: str) -> str | None:
    """Save complete configuration for a room to a timestamped file.

    Extracts from cache:
    - Room metadata
    - All lights in the room with their current states
    - All scenes for the room
    - All behaviour instances (switch configurations) targeting the room

    Args:
        controller: HueController instance
        room_name: Name of the room to save (case-insensitive substring match)

    Returns:
        Path to saved file if successful, None otherwise
    """
    if not controller.use_cache:
        click.echo("Error: save_room_configuration requires cache to be loaded.")
        return None

    cache = controller.config.get('cache', {})
    if not cache:
        click.echo("Error: No cache data available.")
        return None

    # Find the room
    rooms = cache.get('rooms', [])
    matching_rooms = [r for r in rooms if room_name.lower() in r.get('metadata', {}).get('name', '').lower()]

    if not matching_rooms:
        click.echo(f"Error: No room found matching '{room_name}'.")
        return None

    if len(matching_rooms) > 1:
        click.echo(f"Error: Multiple rooms match '{room_name}':")
        for r in matching_rooms:
            click.echo(f"  - {r.get('metadata', {}).get('name', 'Unknown')}")
        return None

    room = matching_rooms[0]
    room_id = room['id']
    room_full_name = room.get('metadata', {}).get('name', 'Unknown')

    # Get device RIDs in this room
    device_rids = [c['rid'] for c in room.get('children', []) if c['rtype'] == 'device']

    # Extract lights for this room
    lights = cache.get('lights', [])
    room_lights = [l for l in lights if l.get('owner', {}).get('rid') in device_rids]

    # Extract scenes for this room
    scenes = cache.get('scenes', [])
    room_scenes = [s for s in scenes if s.get('group', {}).get('rid') == room_id]

    # Extract behaviours targeting this room
    behaviours = cache.get('behaviours', [])
    room_behaviours = []

    for b in behaviours:
        config = b.get('configuration', {})
        where_rids = []

        # Extract all 'where' references
        if 'where' in config:
            for w in config['where']:
                if w.get('group', {}).get('rtype') == 'room':
                    where_rids.append(w.get('group', {}).get('rid'))

        # Check button-specific where (old format)
        for key in ['button1', 'button2', 'button3', 'button4', 'rotary']:
            if key in config and 'where' in config[key]:
                for w in config[key]['where']:
                    if w.get('group', {}).get('rtype') == 'room':
                        where_rids.append(w.get('group', {}).get('rid'))

        # Check new format
        if 'buttons' in config:
            for button_rid, button_config in config['buttons'].items():
                if 'where' in button_config:
                    for w in button_config['where']:
                        if w.get('group', {}).get('rtype') == 'room':
                            where_rids.append(w.get('group', {}).get('rid'))

        # If this behaviour targets our room, include it
        if room_id in where_rids:
            room_behaviours.append(b)

    # Create saved configuration
    saved_config = {
        'saved_at': datetime.now().isoformat(),
        'room': room,
        'lights': room_lights,
        'scenes': room_scenes,
        'behaviours': room_behaviours,
        'summary': {
            'room_name': room_full_name,
            'light_count': len(room_lights),
            'scene_count': len(room_scenes),
            'behaviour_count': len(room_behaviours),
            'device_count': len(device_rids),
        }
    }

    # Create filename: YYYY-MM-DD_HH-MM_RoomName.json
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M')
    # Sanitise room name for filename
    safe_room_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in room_full_name)
    safe_room_name = safe_room_name.replace(' ', '_')
    filename = f"{timestamp}_{safe_room_name}.json"

    # Ensure directory exists
    SAVED_ROOMS_DIR.mkdir(parents=True, exist_ok=True)

    # Save to file
    filepath = SAVED_ROOMS_DIR / filename

    with open(filepath, 'w') as f:
        json.dump(saved_config, f, indent=2)

    return str(filepath)


def diff_room_configuration(controller: 'HueController', saved_file_path: str, verbose: bool = False) -> dict | None:
    """Compare saved room configuration with current cache.

    Performs section-by-section comparison:
    - Room metadata changes
    - Lights: added/removed (verbose: + state changes like on/off, brightness, colour temp)
    - Scenes: added/removed/changed (auto_dynamic, action count)
    - Behaviours: added/removed/changed (verbose: + detailed button configuration changes)

    Args:
        controller: HueController instance
        saved_file_path: Path to saved room JSON file
        verbose: If True, include ephemeral state changes and detailed configuration diffs

    Returns:
        Dict with diff results, or None if error
    """
    if not controller.use_cache:
        click.echo("Error: diff_room_configuration requires cache to be loaded.")
        return None

    try:
        # Load saved configuration
        with open(saved_file_path, 'r') as f:
            saved = json.load(f)

        # Get current configuration for the same room
        room_name = saved['summary']['room_name']
        cache = controller.config.get('cache', {})

        # Find the room in current cache
        rooms = cache.get('rooms', [])
        current_room = None
        for r in rooms:
            if r.get('metadata', {}).get('name', '') == room_name:
                current_room = r
                break

        if not current_room:
            return {
                'error': f"Room '{room_name}' not found in current cache",
                'room_deleted': True
            }

        room_id = current_room['id']
        device_rids = [c['rid'] for c in current_room.get('children', []) if c['rtype'] == 'device']

        # Get current data for comparison
        current_lights = [l for l in cache.get('lights', []) if l.get('owner', {}).get('rid') in device_rids]
        current_scenes = [s for s in cache.get('scenes', []) if s.get('group', {}).get('rid') == room_id]
        current_behaviours = []

        # Extract current behaviours for this room (same logic as save)
        for b in cache.get('behaviours', []):
            config = b.get('configuration', {})
            where_rids = []

            if 'where' in config:
                for w in config['where']:
                    if w.get('group', {}).get('rtype') == 'room':
                        where_rids.append(w.get('group', {}).get('rid'))

            for key in ['button1', 'button2', 'button3', 'button4', 'rotary']:
                if key in config and 'where' in config[key]:
                    for w in config[key]['where']:
                        if w.get('group', {}).get('rtype') == 'room':
                            where_rids.append(w.get('group', {}).get('rid'))

            if 'buttons' in config:
                for button_rid, button_config in config['buttons'].items():
                    if 'where' in button_config:
                        for w in button_config['where']:
                            if w.get('group', {}).get('rtype') == 'room':
                                where_rids.append(w.get('group', {}).get('rid'))

            if room_id in where_rids:
                current_behaviours.append(b)

        # Create scene ID -> name lookup for verbose output
        scene_lookup = {}
        all_scenes = cache.get('scenes', [])
        for scene in all_scenes:
            scene_id = scene.get('id', '')
            scene_name = scene.get('metadata', {}).get('name', 'Unknown')
            if scene_id:
                scene_lookup[scene_id] = scene_name

        # Compare sections
        diff = {
            'room_name': room_name,
            'saved_at': saved['saved_at'],
            'compared_at': datetime.now().isoformat(),
            'verbose': verbose,
            'room': _diff_room_metadata(saved['room'], current_room),
            'lights': _diff_lights(saved['lights'], current_lights, verbose),
            'scenes': _diff_scenes(saved['scenes'], current_scenes),
            'behaviours': _diff_behaviours(saved['behaviours'], current_behaviours, verbose, scene_lookup),
        }

        return diff

    except Exception as e:
        return {'error': str(e)}


def _diff_room_metadata(saved_room: dict, current_room: dict) -> dict:
    """Compare room metadata."""
    changes = []

    # Check basic metadata
    saved_meta = saved_room.get('metadata', {})
    current_meta = current_room.get('metadata', {})

    if saved_meta.get('name') != current_meta.get('name'):
        changes.append(f"Name: '{saved_meta.get('name')}' → '{current_meta.get('name')}'")

    if saved_meta.get('archetype') != current_meta.get('archetype'):
        changes.append(f"Archetype: '{saved_meta.get('archetype')}' → '{current_meta.get('archetype')}'")

    # Check device count
    saved_devices = len([c for c in saved_room.get('children', []) if c['rtype'] == 'device'])
    current_devices = len([c for c in current_room.get('children', []) if c['rtype'] == 'device'])

    if saved_devices != current_devices:
        changes.append(f"Device count: {saved_devices} → {current_devices}")

    return {
        'changed': len(changes) > 0,
        'changes': changes
    }


def _diff_lights(saved_lights: list[dict], current_lights: list[dict], verbose: bool = False) -> dict:
    """Compare lights - added, removed, and optionally state changes.

    Args:
        saved_lights: Saved light configurations
        current_lights: Current light configurations
        verbose: If True, include ephemeral state changes (on/off, brightness, colour temp)

    Returns:
        Dict with added, removed, changed lists and summary
    """
    # Create lookup by ID
    saved_by_id = {l['id']: l for l in saved_lights}
    current_by_id = {l['id']: l for l in current_lights}

    added = []
    removed = []
    changed = []

    # Find added lights
    for light_id, light in current_by_id.items():
        if light_id not in saved_by_id:
            added.append(light.get('metadata', {}).get('name', 'Unknown'))

    # Find removed and changed lights
    for light_id, saved_light in saved_by_id.items():
        if light_id not in current_by_id:
            removed.append(saved_light.get('metadata', {}).get('name', 'Unknown'))
        elif verbose:
            # Only compare state changes in verbose mode
            current_light = current_by_id[light_id]
            light_changes = []

            # Compare on/off
            saved_on = saved_light.get('on', {}).get('on')
            current_on = current_light.get('on', {}).get('on')
            if saved_on != current_on:
                light_changes.append(f"on: {saved_on} → {current_on}")

            # Compare brightness
            saved_bri = saved_light.get('dimming', {}).get('brightness')
            current_bri = current_light.get('dimming', {}).get('brightness')
            if saved_bri is not None and current_bri is not None:
                if abs(saved_bri - current_bri) > 0.5:  # Ignore tiny differences
                    light_changes.append(f"brightness: {saved_bri:.1f}% → {current_bri:.1f}%")

            # Compare colour temperature
            saved_ct = saved_light.get('color_temperature', {}).get('mirek')
            current_ct = current_light.get('color_temperature', {}).get('mirek')
            if saved_ct is not None and current_ct is not None:
                if saved_ct != current_ct:
                    light_changes.append(f"colour temp: {saved_ct} → {current_ct}")

            if light_changes:
                name = saved_light.get('metadata', {}).get('name', 'Unknown')
                changed.append({'name': name, 'changes': light_changes})

    return {
        'added': added,
        'removed': removed,
        'changed': changed,
        'summary': f"{len(added)} added, {len(removed)} removed" + (f", {len(changed)} changed" if verbose and changed else "")
    }


def _diff_scenes(saved_scenes: list[dict], current_scenes: list[dict]) -> dict:
    """Compare scenes - added, removed, and setting changes."""
    saved_by_id = {s['id']: s for s in saved_scenes}
    current_by_id = {s['id']: s for s in current_scenes}

    added = []
    removed = []
    changed = []

    # Find added scenes
    for scene_id, scene in current_by_id.items():
        if scene_id not in saved_by_id:
            added.append(scene.get('metadata', {}).get('name', 'Unknown'))

    # Find removed and changed scenes
    for scene_id, saved_scene in saved_by_id.items():
        if scene_id not in current_by_id:
            removed.append(saved_scene.get('metadata', {}).get('name', 'Unknown'))
        else:
            current_scene = current_by_id[scene_id]
            scene_changes = []

            # Compare auto_dynamic
            saved_auto = saved_scene.get('auto_dynamic', False)
            current_auto = current_scene.get('auto_dynamic', False)
            if saved_auto != current_auto:
                scene_changes.append(f"auto_dynamic: {saved_auto} → {current_auto}")

            # Compare action count
            saved_actions = len(saved_scene.get('actions', []))
            current_actions = len(current_scene.get('actions', []))
            if saved_actions != current_actions:
                scene_changes.append(f"light count: {saved_actions} → {current_actions}")

            # Compare speed
            saved_speed = saved_scene.get('speed')
            current_speed = current_scene.get('speed')
            if saved_speed is not None and current_speed is not None:
                if abs(saved_speed - current_speed) > 0.01:
                    scene_changes.append(f"speed: {saved_speed:.2f} → {current_speed:.2f}")

            if scene_changes:
                name = saved_scene.get('metadata', {}).get('name', 'Unknown')
                changed.append({'name': name, 'changes': scene_changes})

    return {
        'added': added,
        'removed': removed,
        'changed': changed,
        'summary': f"{len(added)} added, {len(removed)} removed, {len(changed)} changed"
    }


def _diff_button_configuration(saved_config: dict, current_config: dict, verbose: bool = False, scene_lookup: dict = None) -> list[str]:
    """Compare button configurations and return list of detailed changes.

    Handles both old format (button1/button2/button3/button4) and new format (buttons dict).

    Args:
        saved_config: Saved configuration
        current_config: Current configuration
        verbose: If True, include scene names/IDs in changes
        scene_lookup: Dict mapping scene IDs to names (for verbose output)
    """
    changes = []
    if scene_lookup is None:
        scene_lookup = {}

    # Check old format buttons (button1, button2, button3, button4)
    for button_key in ['button1', 'button2', 'button3', 'button4', 'rotary']:
        saved_button = saved_config.get(button_key, {})
        current_button = current_config.get(button_key, {})

        if saved_button != current_button:
            button_label = {
                'button1': 'Button 1 (ON)',
                'button2': 'Button 2 (DIM UP)',
                'button3': 'Button 3 (DIM DOWN)',
                'button4': 'Button 4 (OFF)',
                'rotary': 'Dial (ROTATE)'
            }.get(button_key, button_key)

            # Detect what changed
            button_changes = _describe_button_change(saved_button, current_button, verbose, scene_lookup)
            if button_changes:
                changes.append(f"{button_label}: {button_changes}")

    # Check new format buttons (buttons dict with button rids as keys)
    saved_buttons = saved_config.get('buttons', {})
    current_buttons = current_config.get('buttons', {})

    all_button_rids = set(saved_buttons.keys()) | set(current_buttons.keys())
    for button_rid in all_button_rids:
        saved_button = saved_buttons.get(button_rid, {})
        current_button = current_buttons.get(button_rid, {})

        if saved_button != current_button:
            # Try to get a descriptive label (Button 1, 2, 3, 4 based on position)
            button_changes = _describe_button_change(saved_button, current_button, verbose, scene_lookup)
            if button_changes:
                changes.append(f"Button: {button_changes}")

    return changes


def _describe_button_change(saved_button: dict, current_button: dict, verbose: bool = False, scene_lookup: dict = None) -> str:
    """Describe what changed in a button configuration.

    Args:
        saved_button: Saved button config
        current_button: Current button config
        verbose: If True, include scene names in output
        scene_lookup: Dict mapping scene IDs to names
    """
    if scene_lookup is None:
        scene_lookup = {}
    if not saved_button and current_button:
        return "added configuration"
    if saved_button and not current_button:
        return "removed configuration"

    # Check for action type changes
    # Old format: actions nested in 'when'
    # New format: actions directly on button (on_short_release, on_long_press, etc.)
    saved_when = saved_button.get('when', saved_button)  # Fall back to button itself for new format
    current_when = current_button.get('when', current_button)

    # Extract scene IDs from various button action formats
    def extract_scene_ids_from_action(action_config):
        """Extract scene IDs from button action configuration."""
        scene_ids = []

        # Format 1: scene_cycle with scene_ids
        if 'scene_cycle' in action_config:
            scene_refs = action_config['scene_cycle'].get('scene_ids', [])
            for ref in scene_refs:
                if isinstance(ref, dict):
                    scene_ids.append(ref.get('rid', ''))
                else:
                    scene_ids.append(ref)

        # Format 2: scene_cycle_extended with slots
        if 'scene_cycle_extended' in action_config:
            slots = action_config['scene_cycle_extended'].get('slots', [])
            for slot in slots:
                # Each slot is a list with action items
                for item in slot:
                    if (recall := item.get('action', {}).get('recall', {})).get('rtype') == 'scene':
                        if rid := recall.get('rid'):
                            scene_ids.append(rid)

        return [sid for sid in scene_ids if sid]  # Filter empty strings

    # Check on_short_release for scene cycles
    saved_short_release = saved_when.get('on_short_release', {})
    current_short_release = current_when.get('on_short_release', {})

    saved_scenes = extract_scene_ids_from_action(saved_short_release)
    current_scenes = extract_scene_ids_from_action(current_short_release)

    if saved_scenes or current_scenes:
        if saved_scenes != current_scenes:
            added = set(current_scenes) - set(saved_scenes)
            removed = set(saved_scenes) - set(current_scenes)

            if verbose:
                # Show actual scene names with bright yellow highlighting
                parts = []
                if removed:
                    removed_names = [click.style(scene_lookup.get(sid, sid), fg='bright_yellow') for sid in sorted(removed)]
                    removed_str = ', '.join(removed_names)
                    parts.append(f"removed: {removed_str}")
                if added:
                    added_names = [click.style(scene_lookup.get(sid, sid), fg='bright_yellow') for sid in sorted(added)]
                    added_str = ', '.join(added_names)
                    parts.append(f"added: {added_str}")
                return f"scene cycle modified ({'; '.join(parts)})"
            else:
                # Just show counts
                if added and removed:
                    return f"scene cycle modified ({len(removed)} removed, {len(added)} added)"
                elif added:
                    return f"scene cycle: added {len(added)} scene(s)"
                elif removed:
                    return f"scene cycle: removed {len(removed)} scene(s)"
                else:
                    # Scenes reordered or changed but same count
                    return f"scene cycle: scenes changed (count: {len(current_scenes)})"

    # Time-based schedule changes
    if 'time_based_light_scene' in saved_when or 'time_based_light_scene' in current_when:
        saved_slots = saved_when.get('time_based_light_scene', {}).get('schedule', {}).get('time_slots', [])
        current_slots = current_when.get('time_based_light_scene', {}).get('schedule', {}).get('time_slots', [])

        if saved_slots != current_slots:
            return f"time-based schedule modified ({len(saved_slots)} → {len(current_slots)} slots)"

    # Dimming changes
    if 'dimming' in saved_when or 'dimming' in current_when:
        if saved_when.get('dimming') != current_when.get('dimming'):
            return "dimming configuration changed"

    # Generic change if we can't determine specifics
    if saved_button != current_button:
        return "configuration changed"

    return ""


def _diff_behaviours(saved_behaviours: list[dict], current_behaviours: list[dict], verbose: bool = False, scene_lookup: dict = None) -> dict:
    """Compare behaviour instances - added, removed, and state changes.

    Args:
        saved_behaviours: Saved behaviour instances
        current_behaviours: Current behaviour instances
        verbose: If True, show detailed configuration differences
        scene_lookup: Dict mapping scene IDs to names (for verbose output)
    """
    if scene_lookup is None:
        scene_lookup = {}
    saved_by_id = {b['id']: b for b in saved_behaviours}
    current_by_id = {b['id']: b for b in current_behaviours}

    added = []
    removed = []
    changed = []

    # Find added behaviours
    for behav_id, behav in current_by_id.items():
        if behav_id not in saved_by_id:
            added.append(behav.get('metadata', {}).get('name', 'Unknown'))

    # Find removed and changed behaviours
    for behav_id, saved_behav in saved_by_id.items():
        if behav_id not in current_by_id:
            removed.append(saved_behav.get('metadata', {}).get('name', 'Unknown'))
        else:
            current_behav = current_by_id[behav_id]
            behav_changes = []

            # Compare enabled state
            saved_enabled = saved_behav.get('enabled', False)
            current_enabled = current_behav.get('enabled', False)
            if saved_enabled != current_enabled:
                behav_changes.append(f"enabled: {saved_enabled} → {current_enabled}")

            # Compare status
            saved_status = saved_behav.get('status', '')
            current_status = current_behav.get('status', '')
            if saved_status != current_status:
                behav_changes.append(f"status: {saved_status} → {current_status}")

            # Compare configuration (button mappings, scene lists, time-based schedules, etc.)
            saved_config = saved_behav.get('configuration', {})
            current_config = current_behav.get('configuration', {})

            if saved_config != current_config:
                # Always show button-level details (not just verbose)
                config_details = _diff_button_configuration(saved_config, current_config, verbose, scene_lookup)
                if config_details:
                    behav_changes.extend(config_details)
                else:
                    behav_changes.append("configuration: button programmes modified")

            if behav_changes:
                name = saved_behav.get('metadata', {}).get('name', 'Unknown')
                changed.append({'name': name, 'changes': behav_changes})

    return {
        'added': added,
        'removed': removed,
        'changed': changed,
        'summary': f"{len(added)} added, {len(removed)} removed, {len(changed)} changed"
    }


def restore_room_configuration(controller: 'HueController', saved_file_path: str, skip_confirmation: bool = False) -> bool:
    """Restore room configuration from a saved backup file.

    Applies all behaviour instances (switch programmes) from the saved backup to the bridge.
    This restores the button mappings for the room to the saved state.

    Args:
        controller: HueController instance
        saved_file_path: Path to saved room JSON file
        skip_confirmation: If True, skip confirmation prompt (use with caution!)

    Returns:
        True if successful, False otherwise
    """
    try:
        # Load saved configuration
        with open(saved_file_path, 'r') as f:
            saved = json.load(f)

        room_name = saved['summary']['room_name']
        behaviours = saved.get('behaviours', [])

        if not behaviours:
            click.echo(f"No behaviour instances to restore for '{room_name}'.")
            return False

        # Display what will be restored
        click.echo(f"\n=== Restoring Room Configuration: {room_name} ===\n")
        click.echo(f"Saved at:    {saved['saved_at']}")
        click.echo(f"Source file: {saved_file_path}\n")
        click.echo(f"Will restore {len(behaviours)} switch button programme(s):\n")

        for behav in behaviours:
            name = behav.get('metadata', {}).get('name', 'Unknown')
            enabled = behav.get('enabled', False)
            status = "✓ Enabled" if enabled else "✗ Disabled"
            click.echo(f"  • {name} ({status})")

        click.echo()

        # Ask for confirmation unless skipped
        if not skip_confirmation:
            if not click.confirm("Do you want to apply this configuration to the bridge?"):
                click.echo("Restore cancelled.")
                return False

        # Apply each behaviour instance
        success_count = 0
        fail_count = 0

        click.echo("\nApplying configurations...\n")

        for behav in behaviours:
            behav_id = behav['id']
            name = behav.get('metadata', {}).get('name', 'Unknown')

            # Extract the configuration part (the part that gets sent to the API)
            # The API expects just the configuration, not the full behaviour object
            config = {
                'enabled': behav.get('enabled', True),
                'configuration': behav.get('configuration', {}),
                'metadata': behav.get('metadata', {})
            }

            # Apply the configuration
            result = controller.update_behaviour_instance(behav_id, config)

            if result:
                click.echo(f"  ✓ {name}")
                success_count += 1
            else:
                click.echo(click.style(f"  ✗ {name} - Failed to update", fg='red'))
                fail_count += 1

        # Summary
        click.echo()
        if fail_count == 0:
            click.echo(click.style(f"✓ Successfully restored all {success_count} programme(s)", fg='green'))
            return True
        else:
            click.echo(click.style(f"⚠ Partial success: {success_count} restored, {fail_count} failed", fg='yellow'))
            return False

    except FileNotFoundError:
        click.echo(f"Error: File not found: {saved_file_path}")
        return False
    except json.JSONDecodeError:
        click.echo(f"Error: Invalid JSON in file: {saved_file_path}")
        return False
    except Exception as e:
        click.echo(f"Error restoring room configuration: {e}")
        return False
