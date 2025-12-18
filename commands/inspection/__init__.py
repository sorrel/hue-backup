"""
Inspection command module.

Provides commands for inspecting Hue devices, switches, and configurations.

Structure:
- helpers.py: Shared helper functions and constants
- scenes.py: Scene inspection commands (1 command)
- status.py: Status and overview commands (3 commands)
- devices.py: Device listing commands (4 commands)
- switches.py: Switch inspection commands (6 commands)
"""

# Scene commands
from .scenes import scene_details_command

# Status commands
from .status import (
    status_command,
    groups_command,
    scenes_command,
)

# Device commands
from .devices import (
    plugs_command,
    lights_command,
    other_command,
    all_devices_command,
)

# Switch commands
from .switches import (
    switches_command,
    debug_buttons_command,
    button_data_command,
    bridge_auto_command,
    switch_status_command,
    switch_info_command,
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
