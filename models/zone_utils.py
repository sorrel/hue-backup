"""Zone utilities for zone-specific scene programming.

This module contains helper functions for working with zones and filtering
scene actions to only include lights within specific zones.
"""

from models.utils import find_similar_strings

# Hue API limits
MAX_SCENE_NAME_LENGTH = 32  # Maximum characters for scene names


def get_zone_lights(zone: dict) -> list[str]:
    """Get light RIDs in a zone.

    Args:
        zone: Zone dictionary from Hue API

    Returns:
        List of light resource IDs
    """
    return [child['rid'] for child in zone.get('children', [])
            if child.get('rtype') == 'light']


def find_zone_by_name(zones: list[dict], name: str) -> tuple[dict | None, list[str]]:
    """Find zone by name using fuzzy matching.

    Args:
        zones: List of zone dictionaries
        name: Zone name to search for

    Returns:
        Tuple of (zone_dict, suggestions) where suggestions is list of similar names
        If exact/close match found, zone_dict is the match and suggestions is empty
        If no match found, zone_dict is None and suggestions contains similar names
    """
    zone_names = [z.get('metadata', {}).get('name', '') for z in zones]

    # Try exact match first (case-insensitive)
    for zone in zones:
        zone_name = zone.get('metadata', {}).get('name', '')
        if zone_name.lower() == name.lower():
            return zone, []

    # Try fuzzy matching
    matches = find_similar_strings(name, zone_names, threshold=0.6)

    if matches:
        # Return the best match
        best_match_name = matches[0]
        for zone in zones:
            if zone.get('metadata', {}).get('name') == best_match_name:
                return zone, []

    # No good match - return suggestions
    suggestions = find_similar_strings(name, zone_names, threshold=0.3)
    return None, suggestions


def filter_scene_actions_for_zone(scene: dict, zone_lights: list[str],
                                   exclude_lights: list[str] | None = None) -> list[dict]:
    """Extract scene actions for zone lights, with excluded lights turned off.

    For zone-based scenes, the Hue API requires actions for ALL lights in the zone.
    Excluded lights are included in the actions but with {"on": {"on": false}}.

    Args:
        scene: Scene dictionary from Hue API
        zone_lights: List of light RIDs in the zone
        exclude_lights: Optional list of light RIDs to turn off

    Returns:
        List of action dictionaries for all zone lights
    """
    actions = scene.get('actions', [])
    excluded_set = set(exclude_lights or [])
    zone_set = set(zone_lights)

    # Build lookup of existing actions by light RID
    action_lookup = {}
    for action in actions:
        light_rid = action.get('target', {}).get('rid')
        if light_rid in zone_set:
            action_lookup[light_rid] = action

    # Build final actions list for all zone lights
    final_actions = []

    for light_rid in zone_lights:
        if light_rid in excluded_set:
            # Excluded light - add action to turn it off
            final_actions.append({
                "target": {
                    "rid": light_rid,
                    "rtype": "light"
                },
                "action": {
                    "on": {"on": False}
                }
            })
        elif light_rid in action_lookup:
            # Light has an action in the source scene - use it
            final_actions.append(action_lookup[light_rid])
        else:
            # Light is in zone but not in source scene - turn it off
            final_actions.append({
                "target": {
                    "rid": light_rid,
                    "rtype": "light"
                },
                "action": {
                    "on": {"on": False}
                }
            })

    return final_actions


def find_lights_by_name(lights: list[dict], name_pattern: str) -> list[str]:
    """Find light RIDs matching a name pattern.

    Args:
        lights: List of light dictionaries from Hue API
        name_pattern: Light name or pattern to search for

    Returns:
        List of matching light RIDs
    """
    matches = []
    pattern_lower = name_pattern.lower()

    for light in lights:
        light_name = light.get('metadata', {}).get('name', '')
        if pattern_lower in light_name.lower():
            matches.append(light['id'])

    return matches


def get_light_names_in_zone(zone: dict, lights_list: list[dict]) -> dict[str, str]:
    """Get {light_rid: light_name} mapping for lights in zone.

    Args:
        zone: Zone dictionary from Hue API
        lights_list: List of all light dictionaries

    Returns:
        Dictionary mapping light RID to light name
    """
    zone_light_rids = get_zone_lights(zone)
    light_lookup = {}

    for light in lights_list:
        if light['id'] in zone_light_rids:
            light_name = light.get('metadata', {}).get('name', 'Unknown')
            light_lookup[light['id']] = light_name

    return light_lookup


def generate_zone_scene_name(original_name: str, zone_name: str,
                              excluded_lights: list[str] | None = None,
                              light_lookup: dict[str, str] | None = None) -> str:
    """Generate a unique name for a zone-filtered scene.

    Args:
        original_name: Original scene name
        zone_name: Zone name
        excluded_lights: Optional list of excluded light RIDs
        light_lookup: Optional dict mapping light RID to name

    Returns:
        Generated scene name following convention:
        - "Bright (Combined lounge)" for zone-filtered (max 32 chars)
        - "Bright (Combined lounge) -X" with exclusions (X suffix for excluded)
    """
    # Shorten zone name if needed
    zone_short = zone_name.replace("Combined ", "").replace("combined ", "")

    base_name = f"{original_name} ({zone_short})"

    if excluded_lights:
        # Just add a suffix indicating exclusions, don't list the light names
        base_name = f"{base_name} -X"

    # Truncate if needed (Hue API limit)
    if len(base_name) > MAX_SCENE_NAME_LENGTH:
        base_name = base_name[:MAX_SCENE_NAME_LENGTH]

    return base_name
