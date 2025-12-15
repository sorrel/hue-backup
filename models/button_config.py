"""Button configuration helpers for program-button command.

This module provides all the business logic for programming button configurations
on Philips Hue switches, including:
- Switch and button lookup with fuzzy matching
- Scene name resolution
- Configuration builders for different action types
- Argument validation
"""

import click
import copy

from models.types import SwitchBehaviour


# ===== Switch & Button Lookup =====

def find_switch_behaviour(switch_name: str, controller) -> SwitchBehaviour | None:
    """Find behaviour instance by switch/device name with fuzzy matching.

    Args:
        switch_name: Human-readable switch name (e.g., "Office dimmer")
        controller: HueController instance with cache

    Returns:
        SwitchBehaviour dict if found, None otherwise
    """
    devices = controller.get_devices()
    behaviours = controller.get_behaviour_instances()

    # Create device lookup
    device_lookup = {d['id']: d for d in devices}

    # Find button-triggered behaviours
    button_behaviours = []
    for b in behaviours:
        config = b.get('configuration', {})
        # Check for button configuration (both formats)
        if 'buttons' in config or any(key.startswith('button') and key[6:].isdigit()
                                      for key in config.keys()):
            device_rid = config.get('device', {}).get('rid')
            if device_rid and device_rid in device_lookup:
                device = device_lookup[device_rid]
                device_name = device.get('metadata', {}).get('name', '')
                button_behaviours.append((b, device_name, device))

    # Fuzzy match on device name
    switch_lower = switch_name.lower()
    matches = [
        (b, name, device)
        for b, name, device in button_behaviours
        if switch_lower in name.lower()
    ]

    if len(matches) == 0:
        return None
    elif len(matches) == 1:
        behaviour, device_name, device = matches[0]
        return SwitchBehaviour(
            behaviour=behaviour,
            device_name=device_name,
            device=device
        )
    else:
        # Multiple matches - return None and let caller handle error
        return None


def get_all_switch_names(controller) -> list[str]:
    """Get all switch/dimmer device names for error messages.

    Args:
        controller: HueController instance with cache

    Returns:
        Sorted list of switch/dimmer names
    """
    devices = controller.get_devices()
    behaviours = controller.get_behaviour_instances()
    device_lookup = {d['id']: d for d in devices}

    switch_names = []
    for b in behaviours:
        config = b.get('configuration', {})
        if 'buttons' in config or any(key.startswith('button') and key[6:].isdigit()
                                      for key in config.keys()):
            device_rid = config.get('device', {}).get('rid')
            if device_rid and device_rid in device_lookup:
                device_name = device_lookup[device_rid].get('metadata', {}).get('name', '')
                if device_name:
                    switch_names.append(device_name)

    return sorted(switch_names)


def find_button_rid_for_control_id(behaviour: dict, control_id: int,
                                    button_lookup: dict[str, dict]) -> str | None:
    """Find button RID for a given control_id in new format behaviour.

    Args:
        behaviour: Behaviour instance dict
        control_id: Control ID (1-4) to find
        button_lookup: Dict mapping button IDs to button resources

    Returns:
        Button RID if found, None otherwise (or if old format)
    """
    config = behaviour.get('configuration', {})

    if 'buttons' not in config:
        return None  # Old format

    buttons_config = config['buttons']

    for button_rid in buttons_config.keys():
        if button_rid in button_lookup:
            button_res = button_lookup[button_rid]
            if button_res.get('metadata', {}).get('control_id') == control_id:
                return button_rid

    return None


# ===== Scene Resolution =====

def resolve_scene_names(scene_names: list[str], scenes: list[dict]) -> list[str] | None:
    """Resolve scene names to scene IDs with fuzzy matching.

    Args:
        scene_names: List of human-readable scene names
        scenes: List of scene dicts from cache

    Returns:
        List of scene IDs if all resolved successfully, None otherwise
    """
    from models.utils import create_scene_reverse_lookup

    scene_reverse = create_scene_reverse_lookup(scenes)
    scene_ids = []

    for scene_name in scene_names:
        scene_id = fuzzy_match_scene(scene_name, scene_reverse, scenes)
        if not scene_id:
            click.secho(f"✗ Scene '{scene_name}' not found", fg='red')
            # Show similar scenes
            similar = find_similar_scenes(scene_name, scene_reverse)
            if similar:
                click.echo("\nDid you mean one of these?")
                for similar_name in similar:
                    click.secho(f"  • {similar_name}", fg='green')
            return None
        scene_ids.append(scene_id)

    return scene_ids


def fuzzy_match_scene(scene_name: str, scene_reverse_lookup: dict[str, str],
                      scenes: list[dict]) -> str | None:
    """Fuzzy match scene name to scene ID.

    Args:
        scene_name: Human-readable scene name
        scene_reverse_lookup: Dict mapping lowercase scene names to IDs
        scenes: List of scene dicts (for getting original case names)

    Returns:
        Scene ID if found, None otherwise
    """
    # Exact match first (case-insensitive)
    scene_name_lower = scene_name.lower()
    if scene_name_lower in scene_reverse_lookup:
        return scene_reverse_lookup[scene_name_lower]

    # Partial match
    matches = [
        (name, scene_id)
        for name, scene_id in scene_reverse_lookup.items()
        if scene_name_lower in name
    ]

    if len(matches) == 1:
        return matches[0][1]  # Single match
    elif len(matches) > 1:
        # Multiple matches - show suggestions
        click.secho(f"✗ Multiple scenes match '{scene_name}':", fg='red')
        for name, scene_id in matches:
            # Get original case from scene list
            original_name = next(
                (s.get('metadata', {}).get('name', '')
                 for s in scenes if s['id'] == scene_id),
                name
            )
            click.secho(f"  • {original_name}", fg='yellow')
        click.echo("\nPlease be more specific.")
        return None

    return None  # No matches


def find_similar_scenes(scene_name: str, scene_reverse_lookup: dict[str, str],
                       limit: int = 5) -> list[str]:
    """Find similar scene names for error suggestions.

    Args:
        scene_name: Scene name to match against
        scene_reverse_lookup: Dict mapping lowercase scene names to IDs
        limit: Maximum number of suggestions

    Returns:
        List of similar scene names (original case)
    """
    from models.utils import find_similar_strings

    # Get all scene names (original case)
    all_names = list(scene_reverse_lookup.keys())
    return find_similar_strings(scene_name.lower(), all_names, limit=limit)


# ===== Configuration Builders =====

def build_scene_cycle_config(scene_ids: list[str]) -> dict:
    """Build scene_cycle_extended configuration.

    CRITICAL: Slots must be a list of lists - each scene wrapped in array.

    Args:
        scene_ids: List of scene IDs to cycle through (2+ required)

    Returns:
        Configuration dict for on_short_release
    """
    return {
        'on_short_release': {
            'scene_cycle_extended': {
                'repeat_timeout': {'seconds': 3},
                'slots': [
                    [{'action': {'recall': {'rid': scene_id, 'rtype': 'scene'}}}]
                    for scene_id in scene_ids
                ],
                'with_off': {'enabled': False}
            }
        }
    }


def build_time_based_config(time_slots: list[tuple[int, int, str]]) -> dict:
    """Build time_based_extended configuration.

    CRITICAL: Slots is a list of objects with start_time and actions.

    Args:
        time_slots: List of (hour, minute, scene_id) tuples

    Returns:
        Configuration dict for on_short_release
    """
    # Sort by time
    sorted_slots = sorted(time_slots, key=lambda x: (x[0], x[1]))

    return {
        'on_short_release': {
            'time_based_extended': {
                'repeat_timeout': {'seconds': 3},
                'slots': [
                    {
                        'start_time': {'hour': hour, 'minute': minute},
                        'actions': [{'action': {'recall': {'rid': scene_id, 'rtype': 'scene'}}}]
                    }
                    for hour, minute, scene_id in sorted_slots
                ],
                'with_off': {'enabled': True}
            }
        }
    }


def build_single_scene_config(scene_id: str) -> dict:
    """Build recall_single_extended configuration.

    Args:
        scene_id: Scene ID to activate

    Returns:
        Configuration dict for on_short_release
    """
    return {
        'on_short_release': {
            'recall_single_extended': {
                'actions': [{'action': {'recall': {'rid': scene_id, 'rtype': 'scene'}}}]
            }
        }
    }


def build_dimming_config(direction: str) -> dict:
    """Build dimming configuration for on_repeat.

    Args:
        direction: 'dim_up' or 'dim_down'

    Returns:
        Configuration dict for on_repeat
    """
    return {
        'on_repeat': {
            'action': direction
        }
    }


def build_long_press_config(action: str, scene_id: str | None = None) -> dict:
    """Build long press configuration.

    Args:
        action: Action name ('all_off', 'home_off') or scene name
        scene_id: Scene ID if action is a scene

    Returns:
        Configuration dict for on_long_press
    """
    if scene_id:
        return {
            'on_long_press': {
                'recall': {'rid': scene_id, 'rtype': 'scene'}
            }
        }
    else:
        return {
            'on_long_press': {
                'action': action.lower().replace(' ', '_')
            }
        }


# ===== Time Slot Parsing =====

def parse_time_slot(slot_str: str) -> tuple[int, int, str]:
    """Parse time slot string in format HH:MM=SceneName.

    Args:
        slot_str: Time slot string (e.g., "07:00=Morning")

    Returns:
        Tuple of (hour, minute, scene_name)

    Raises:
        ValueError: If format is invalid
    """
    if '=' not in slot_str:
        raise ValueError(f"Invalid slot format: '{slot_str}'. Expected HH:MM=SceneName")

    time_part, scene_name = slot_str.split('=', 1)

    if ':' not in time_part:
        raise ValueError(f"Invalid time format: '{time_part}'. Expected HH:MM")

    hour_str, minute_str = time_part.split(':', 1)

    try:
        hour = int(hour_str)
        minute = int(minute_str)
    except ValueError:
        raise ValueError(f"Invalid time values: '{time_part}'. Hour and minute must be integers")

    if not (0 <= hour <= 23):
        raise ValueError(f"Invalid hour: {hour}. Must be 0-23")

    if not (0 <= minute <= 59):
        raise ValueError(f"Invalid minute: {minute}. Must be 0-59")

    return (hour, minute, scene_name.strip())


# ===== Button Configuration Update =====

def update_button_configuration(behaviour: dict, button_number: int,
                               new_config: dict, button_lookup: dict[str, dict]) -> dict:
    """Update button configuration in behaviour instance (handles both formats).

    Args:
        behaviour: Existing behaviour instance
        button_number: Button number (1-4)
        new_config: New button configuration dict with on_short_release/on_long_press/on_repeat
        button_lookup: Button RID to resource mapping

    Returns:
        Updated configuration dict ready for API call

    Raises:
        ValueError: If button not found in switch configuration
    """
    existing_config = behaviour.get('configuration', {})

    # Deep copy to avoid mutating original
    config = copy.deepcopy(existing_config)

    # Detect format
    if 'buttons' in config:
        # New format - find button RID for control_id
        button_rid = find_button_rid_for_control_id(behaviour, button_number, button_lookup)

        if not button_rid:
            raise ValueError(f"Could not find button {button_number} in switch configuration")

        # Update button config (merge with existing)
        if button_rid not in config['buttons']:
            config['buttons'][button_rid] = {}

        config['buttons'][button_rid].update(new_config)

    else:
        # Old format - use button{N} key
        button_key = f'button{button_number}'

        if button_key not in config:
            # Button doesn't exist - create it
            config[button_key] = {}

        config[button_key].update(new_config)

    # Return wrapped configuration for API call
    return {
        'configuration': config,
        'enabled': behaviour.get('enabled', True),
        'metadata': behaviour.get('metadata', {})
    }


# ===== Argument Validation =====

def validate_program_button_args(scenes, time_based, slot, scene, dim_up, dim_down, long_press):
    """Validate command arguments for conflicts and requirements.

    Args:
        scenes: --scenes option value
        time_based: --time-based flag value
        slot: --slot option values (tuple)
        scene: --scene option value
        dim_up: --dim-up flag value
        dim_down: --dim-down flag value
        long_press: --long-press option value

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check slot/time-based dependency first (before counting actions)
    if slot and not time_based:
        return False, "--slot requires --time-based flag"

    if time_based and not slot:
        return False, "--time-based requires at least one --slot HH:MM=SceneName"

    # Check for dim up/down conflict
    if dim_up and dim_down:
        return False, "Cannot specify both --dim-up and --dim-down"

    # Count how many short-press actions are specified
    short_press_actions = sum([
        bool(scenes),
        bool(time_based),
        bool(scene),
        bool(dim_up),
        bool(dim_down)
    ])

    # Validation rules
    if short_press_actions == 0 and not long_press:
        return False, "Must specify at least one action (--scenes, --scene, --dim-up, --dim-down, or --long-press)"

    if short_press_actions > 1:
        return False, "Cannot specify multiple short-press actions. Choose one: --scenes, --time-based, --scene, --dim-up, or --dim-down"

    if scenes:
        scene_list = [s.strip() for s in scenes.split(',')]
        if len(scene_list) < 2:
            return False, "--scenes requires at least 2 comma-separated scene names (use --scene for single scene)"

    return True, None
