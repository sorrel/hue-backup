"""
Inspection command module.

Provides commands for inspecting Hue devices, switches, and configurations.

Structure:
- helpers.py: Shared helper functions and constants
- commands.py: All inspection command implementations
"""

from .commands import (
    scene_details_command,
    status_command,
    groups_command,
    scenes_command,
    switches_command,
    debug_buttons_command,
    button_data_command,
    bridge_auto_command,
    switch_status_command,
    switch_info_command,
    plugs_command,
    lights_command,
    other_command,
    all_devices_command,
)

# Re-export helpers
from .helpers import (
    BUTTON_LABELS,
    SWITCH_EMOJIS,
    get_switch_emoji,
    format_timestamp,
    find_device_room,
    should_include_device,
    display_device_table,
    generate_model_summary,
)

# Re-export utils for test compatibility
from models.utils import get_cache_controller

__all__ = [
    # Helper functions
    'BUTTON_LABELS',
    'SWITCH_EMOJIS',
    'get_switch_emoji',
    'format_timestamp',
    'find_device_room',
    'should_include_device',
    'display_device_table',
    'generate_model_summary',

    # Scene commands
    'scene_details_command',

    # Status commands
    'status_command',
    'groups_command',
    'scenes_command',

    # Switch commands
    'switches_command',
    'debug_buttons_command',
    'button_data_command',
    'bridge_auto_command',
    'switch_status_command',
    'switch_info_command',

    # Device commands
    'plugs_command',
    'lights_command',
    'other_command',
    'all_devices_command',
]
