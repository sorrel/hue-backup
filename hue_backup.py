#!/usr/bin/env python3
"""
Hue Backup CLI
Back up and restore Philips Hue switch configurations and room settings.
"""

import click
import os
import sys
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
    groups_command,
    zones_command,
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
    all_devices_command
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
from commands.zone_programming import (
    program_zone_switch_command
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
@click.version_option(version='0.1.0', prog_name='Hue Backup')
def cli():
    """Hue Backup CLI - Back up and restore Philips Hue switch configurations.

Main focus: Programme scenes into switches and save/restore room configurations.

Authentication: 1Password → Local config (~/.hue_backup/config.json) → Interactive setup
Run 'configure' for first-time setup or 'setup' to check configuration.

Use 'help' for a quick reference of all commands.
Use 'COMMAND -h' or 'COMMAND --help' for detailed help on a specific command."""
    pass


@cli.command(name='install-completion')
@click.option('--shell', type=click.Choice(['bash', 'zsh', 'fish']), default=None,
              help='Shell type (auto-detected if not specified)')
def install_completion_command(shell):
    """Install shell completion for this tool.

    Creates a 'hue' command that works from any directory and enables tab-completion.
    Run this once after installation. Re-run to update when commands change.

    \b
    Examples:
      uv run python hue_backup.py install-completion        # Auto-detect shell
      uv run python hue_backup.py install-completion --shell zsh

    \b
    After installation:
      hue button-data           # Works from anywhere
      hue <TAB>                 # Tab-completion for all commands
    """
    # Auto-detect shell if not specified
    if shell is None:
        shell_env = os.environ.get('SHELL', '')
        if 'zsh' in shell_env:
            shell = 'zsh'
        elif 'bash' in shell_env:
            shell = 'bash'
        elif 'fish' in shell_env:
            shell = 'fish'
        else:
            click.echo("Could not detect shell type. Please specify with --shell option.")
            return

    script_path = os.path.abspath(__file__)
    script_dir = os.path.dirname(script_path)

    # Generate static completion script
    if shell == 'zsh':
        config_file = os.path.expanduser('~/.zshrc')
        completion_dir = os.path.expanduser('~/.hue_backup_completion')
        completion_file = os.path.join(completion_dir, '_hue_backup')

        # Create completion directory
        os.makedirs(completion_dir, exist_ok=True)

        # Generate zsh completion script that works for both alias and full command
        completion_script = f'''#compdef hue

_hue_commands() {{
    local -a commands
    commands=(
        'help:Display help and common commands'
        'setup:Show current bridge configuration and test connection'
        'configure:Interactive bridge configuration and authentication setup'
        'reload:Reload and cache all data from the Hue Bridge'
        'cache-info:Show cache status and information'
        'save-room:Save complete configuration for a room'
        'diff-room:Compare saved room configuration with current state'
        'restore-room:Restore room configuration from a saved backup'
        'scene-details:Show detailed scene information from cache'
        'status:Get overall bridge status and configuration summary'
        'groups:List all groups/rooms'
        'scenes:List all available scenes'
        'switches:List all switches and sensors'
        'debug-buttons:Debug - show raw button configuration data'
        'button-data:Show programmed wall controls (dimmers and dials)'
        'bridge-auto:Show bridge-configured button automations'
        'switch-status:Display switch status with CLI mappings'
        'switch-info:Get detailed information about switches'
        'plugs:Display smart plug status (on/off by room)'
        'lights:Display light bulbs and fixtures (on/off by room)'
        'other:Display other devices (doorbell, chimes, bridge)'
        'all:Display all devices in one view (switches, plugs, lights, other)'
        'power:Turn a light ON or OFF'
        'brightness:Set brightness of a light'
        'colour:Set colour or temperature of a light'
        'activate-scene:Activate a scene by its ID'
        'auto-dynamic:View or modify auto-dynamic settings for scenes'
        'map:Map a button event to a scene'
        'mappings:List all current button-to-scene mappings'
        'discover:Discover button events by pressing buttons'
        'monitor:Monitor switches and activate mapped scenes'
        'program-button:Programme a button on a Hue switch'
        'install-completion:Install shell completion'
        'show-completion:Show completion script'
    )

    _describe 'command' commands
}}

_hue() {{
    _hue_commands
}}

# Completion only for 'hue' command
compdef _hue hue
'''

        # Write completion file
        with open(completion_file, 'w') as f:
            f.write(completion_script)

        # Source lines to add to zshrc (function + completion)
        # Use a function instead of alias so we can cd first
        alias_line = f'hue() {{ (builtin cd {script_dir} && uv run python {script_path} "$@"); }}'
        source_line = f'fpath=({completion_dir} $fpath) && autoload -Uz compinit && compinit'

    elif shell == 'bash':
        config_file = os.path.expanduser('~/.bashrc')
        completion_dir = os.path.expanduser('~/.hue_backup_completion')
        completion_file = os.path.join(completion_dir, 'hue_backup.bash')

        # Create completion directory
        os.makedirs(completion_dir, exist_ok=True)

        # Generate bash completion script
        completion_script = '''_hue_completion() {
    local cur prev commands
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    commands="help setup configure reload cache-info save-room diff-room restore-room scene-details status groups scenes switches debug-buttons button-data bridge-auto switch-status switch-info plugs lights other all power brightness colour activate-scene auto-dynamic map mappings discover monitor program-button install-completion show-completion"

    if [[ ${COMP_CWORD} == 1 ]]; then
        COMPREPLY=( $(compgen -W "${commands}" -- ${cur}) )
    fi
}
complete -F _hue_completion hue
'''

        # Write completion file
        with open(completion_file, 'w') as f:
            f.write(completion_script)

        # Use a function instead of alias so we can cd first
        alias_line = f'hue() {{ (builtin cd {script_dir} && uv run python {script_path} "$@"); }}'
        source_line = f'source {completion_file}'

    else:
        click.echo(f"Unsupported shell: {shell}")
        return

    # Check if already installed
    try:
        with open(config_file, 'r') as f:
            content = f.read()
            if 'hue_backup_completion' in content or completion_dir in content:
                click.secho(f"✓ Completion already installed in {config_file}", fg='green')
                click.echo(f"\nCompletion file: {completion_file}")
                click.echo(f"\nReload your shell with: source {config_file}")
                return
    except FileNotFoundError:
        pass

    # Add alias and completion to config file
    try:
        with open(config_file, 'a') as f:
            f.write(f'\n# Hue Backup alias and tab completion\n')
            f.write(f'{alias_line}\n')
            f.write(f'{source_line}\n')

        click.secho(f"✓ Completion installed successfully!", fg='green', bold=True)
        click.echo(f"\nFunction created: 'hue' (runs from project directory)")
        click.echo(f"Completion file: {completion_file}")
        click.echo(f"Configuration added to: {config_file}")
        click.echo(f"\nReload your shell with: source {config_file}")
        click.echo(f"\nNow you can use: hue <TAB>")
    except Exception as e:
        click.secho(f"Error installing completion: {e}", fg='red')


@cli.command(name='show-completion')
@click.option('--shell', type=click.Choice(['bash', 'zsh', 'fish']), default=None,
              help='Shell type (auto-detected if not specified)')
def show_completion_command(shell):
    """Show the completion script for manual installation.

    Displays the completion script that would be generated.
    Useful for manual installation or troubleshooting.
    """
    # Auto-detect shell if not specified
    if shell is None:
        shell_env = os.environ.get('SHELL', '')
        if 'zsh' in shell_env:
            shell = 'zsh'
        elif 'bash' in shell_env:
            shell = 'bash'
        elif 'fish' in shell_env:
            shell = 'fish'
        else:
            click.echo("Could not detect shell type. Please specify with --shell option.")
            return

    script_path = os.path.abspath(__file__)
    script_dir = os.path.dirname(script_path)
    completion_dir = os.path.expanduser('~/.hue_backup_completion')

    if shell == 'zsh':
        config_file = '~/.zshrc'
        completion_file = os.path.join(completion_dir, '_hue_backup')
        alias_line = f'hue() {{ (builtin cd {script_dir} && uv run python {script_path} "$@"); }}'
        source_line = f'fpath=({completion_dir} $fpath) && autoload -Uz compinit && compinit'

        click.secho(f"\n1. Completion file location:", fg='cyan', bold=True)
        click.echo(f"   {completion_file}")
        click.echo()
        click.secho(f"2. Add these lines to {config_file}:", fg='cyan', bold=True)
        click.echo(f"   {alias_line}")
        click.echo(f"   {source_line}")
        click.echo()
        click.secho(f"3. Then use:", fg='cyan', bold=True)
        click.echo(f"   hue <TAB>")

    elif shell == 'bash':
        config_file = '~/.bashrc'
        completion_file = os.path.join(completion_dir, 'hue_backup.bash')
        alias_line = f'hue() {{ (builtin cd {script_dir} && uv run python {script_path} "$@"); }}'
        source_line = f'source {completion_file}'

        click.secho(f"\n1. Completion file location:", fg='cyan', bold=True)
        click.echo(f"   {completion_file}")
        click.echo()
        click.secho(f"2. Add these lines to {config_file}:", fg='cyan', bold=True)
        click.echo(f"   {alias_line}")
        click.echo(f"   {source_line}")
        click.echo()
        click.secho(f"3. Then use:", fg='cyan', bold=True)
        click.echo(f"   hue <TAB>")

    else:
        click.echo(f"Unsupported shell: {shell}")
        return

    click.echo()


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
cli.add_command(groups_command, name='groups')
cli.add_command(zones_command, name='zones')
cli.add_command(scenes_command, name='scenes')
cli.add_command(switches_command, name='switches')
cli.add_command(debug_buttons_command, name='debug-buttons')
cli.add_command(button_data_command, name='button-data')
cli.add_command(bridge_auto_command, name='bridge-auto')
cli.add_command(switch_status_command, name='switch-status')
cli.add_command(switch_info_command, name='switch-info')
cli.add_command(plugs_command, name='plugs')
cli.add_command(lights_command, name='lights')
cli.add_command(other_command, name='other')
cli.add_command(all_devices_command, name='all')

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

# Zone programming commands
cli.add_command(program_zone_switch_command, name='program-zone-switch')


if __name__ == '__main__':
    cli()
