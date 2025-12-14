#!/usr/bin/env python3
"""
Hue Lights Control CLI
Control Philips Hue lights, brightness, colours, scenes, and switches.
"""

import click
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning

# Import utility functions from models
from models.utils import display_width, decode_button_event, create_name_lookup, get_cache_controller

# Import configuration functions from core
from core.config import (
    CONFIG_FILE,
    load_config,
    save_config,
    load_from_1password
)

# Import cache management functions from core
from core.cache import (
    reload_cache,
    is_cache_stale,
    ensure_fresh_cache,
    get_cache_info
)

# Import HueController from core
from core.controller import HueController

# Import room management functions
from models.room import (
    save_room_configuration,
    diff_room_configuration,
    SAVED_ROOMS_DIR
)

# Import commands from command modules
from commands.setup import ColouredGroup, help_command, setup_command, configure_command
from commands.cache import reload_command, cache_info_command
from commands.room import save_room_command, diff_room_command, restore_room_command
from commands.inspection import (
    scene_details_command,
    status_command,
    list_lights_command,
    groups_command,
    scenes_command,
    switches_command,
    debug_buttons_command,
    button_data_command,
    bridge_auto_command,
    switch_status_command,
    switch_info_command
)
from commands.control import (
    power_command,
    brightness_command,
    colour_command,
    activate_scene_command,
    auto_dynamic_command
)
from commands.mapping import (
    map_command,
    mappings_command,
    discover_command,
    monitor_command,
    program_button_command
)

# Disable SSL warnings for self-signed certificate
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


@click.group(
    cls=ColouredGroup,
    context_settings={
        'help_option_names': ['-h', '--help'],
        'max_content_width': 999  # Very wide to prevent wrapping on wide terminals
    }
)
@click.version_option(version='0.1.0', prog_name='Hue Control')
def cli():
    """Hue Lights Control CLI - Manage your Philips Hue lights and switches.

Main focus: Programme scenes into switches and monitor button presses.

Authentication: 1Password → Local config (~/.hue_control/config.json) → Interactive setup
Run 'configure' for first-time setup or 'setup' to check configuration.

Use 'help' for a quick reference of all commands.
Use 'COMMAND -h' or 'COMMAND --help' for detailed help on a specific command."""
    pass


# Register setup and help commands
cli.add_command(help_command)
cli.add_command(setup_command, name='setup')
cli.add_command(configure_command, name='configure')

# Register cache commands
cli.add_command(reload_command)
cli.add_command(cache_info_command)

# Register room commands
cli.add_command(save_room_command)
cli.add_command(diff_room_command)
cli.add_command(restore_room_command)

# Register inspection commands
cli.add_command(scene_details_command, name='scene-details')
cli.add_command(status_command, name='status')
cli.add_command(list_lights_command)  # Uses 'list' name defined in decorator
cli.add_command(groups_command, name='groups')
cli.add_command(scenes_command, name='scenes')
cli.add_command(switches_command, name='switches')
cli.add_command(debug_buttons_command, name='debug-buttons')
cli.add_command(button_data_command, name='button-data')
cli.add_command(bridge_auto_command, name='bridge-auto')
cli.add_command(switch_status_command, name='switch-status')
cli.add_command(switch_info_command, name='switch-info')

# Register control commands
cli.add_command(power_command, name='power')
cli.add_command(brightness_command, name='brightness')
cli.add_command(colour_command, name='colour')
cli.add_command(activate_scene_command, name='activate-scene')
cli.add_command(auto_dynamic_command, name='auto-dynamic')

# Register mapping commands
cli.add_command(map_command, name='map')
cli.add_command(mappings_command, name='mappings')
cli.add_command(discover_command, name='discover')
cli.add_command(monitor_command, name='monitor')
cli.add_command(program_button_command, name='program-button')


if __name__ == '__main__':
    cli()
