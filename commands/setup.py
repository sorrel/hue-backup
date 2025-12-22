"""
Setup and help commands for Hue Backup CLI.

Contains custom Click group class for coloured help output and typo suggestions.
"""

import os
from dataclasses import dataclass
from pathlib import Path

import click
from core.config import CONFIG_FILE
from models.utils import similarity_score


@dataclass(frozen=True)
class CommandSection:
    """Represents a section in the help command."""
    name: str
    icon: str
    commands: list[tuple[str, str]]


class ColouredGroup(click.Group):
    """Custom Group class that adds colour to help output and suggests similar commands."""

    def resolve_command(self, ctx, args):
        """Resolve command with suggestions for typos."""
        # Try normal resolution first
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError as e:
            # If command not found, suggest similar commands
            if 'No such command' in str(e):
                cmd_name = args[0] if args else ''
                suggestions = self._get_suggestions(ctx, cmd_name)

                if suggestions:
                    error_msg = f"Error: No such command '{cmd_name}'.\n\n"
                    error_msg += click.style("Did you mean one of these?\n", fg='yellow')
                    for suggestion in suggestions:
                        error_msg += click.style(f"  • {suggestion}\n", fg='green')
                    raise click.UsageError(error_msg)
            raise

    def _get_suggestions(self, ctx, cmd_name, max_suggestions=3):
        """Get command suggestions based on similarity."""
        if not cmd_name:
            return []

        all_commands = self.list_commands(ctx)
        cmd_lower = cmd_name.lower()

        # Calculate similarity scores
        suggestions = []
        for command in all_commands:
            cmd_obj = self.get_command(ctx, command)
            if cmd_obj and not cmd_obj.hidden:
                score = self._similarity_score(cmd_lower, command.lower())
                if score > 0:
                    suggestions.append((score, command))

        # Sort by score (descending) and return top matches
        suggestions.sort(reverse=True, key=lambda x: x[0])
        return [cmd for score, cmd in suggestions[:max_suggestions]]

    def _similarity_score(self, s1, s2):
        """Calculate similarity score between two strings.

        This method delegates to the canonical similarity_score() function
        in models.utils to ensure consistent fuzzy matching across the application.
        """
        return similarity_score(s1, s2)

    def format_help(self, ctx, formatter):
        """Format help with colours."""
        self.format_usage(ctx, formatter)
        self.format_help_text(ctx, formatter)
        self.format_options(ctx, formatter)
        self.format_commands(ctx, formatter)

    def format_usage(self, ctx, formatter):
        """Format the usage line with colour."""
        formatter.write_paragraph()
        formatter.write_text(
            click.style('Usage: ', fg='cyan', bold=True) +
            click.style(f'{ctx.command_path} [OPTIONS] COMMAND [ARGS]...', fg='white')
        )

    def format_help_text(self, ctx, formatter):
        """Format the help text with colour."""
        if self.help:
            formatter.write_paragraph()
            lines = self.help.split('\n')
            for line in lines:
                if line.strip():
                    formatter.write_text(click.style(line, fg='white'))
                else:
                    formatter.write_paragraph()

    def format_options(self, ctx, formatter):
        """Format options with colour."""
        opts = []
        for param in self.get_params(ctx):
            rv = param.get_help_record(ctx)
            if rv is not None:
                opts.append(rv)

        if opts:
            formatter.write_paragraph()
            formatter.write_text(click.style('Options:', fg='yellow', bold=True))
            with formatter.indentation():
                for opt_name, opt_help in opts:
                    formatter.write_text(
                        click.style(opt_name, fg='green') + '  ' +
                        click.style(opt_help, fg='white')
                    )

    def format_commands(self, ctx, formatter):
        """Format commands with colour."""
        commands = []
        for subcommand in self.list_commands(ctx):
            cmd = self.get_command(ctx, subcommand)
            if cmd is None:
                continue
            if cmd.hidden:
                continue

            help_text = cmd.get_short_help_str(limit=500)  # Very large limit to prevent truncation
            commands.append((subcommand, help_text))

        if commands:
            formatter.write_paragraph()
            formatter.write_text(click.style('Commands:', fg='yellow', bold=True))

            # Calculate max width for alignment - pad to reasonable column width
            max_len = max(max(len(cmd[0]) for cmd in commands), 20)

            with formatter.indentation():
                for subcommand, help_text in commands:
                    # Pad command name for alignment
                    cmd_padded = subcommand.ljust(max_len)
                    formatter.write_text(
                        click.style(cmd_padded, fg='green') + '  ' +
                        click.style(help_text, fg='white', dim=True)
                    )


@click.command(name='help')
def help_command():
    """Display help and common commands."""
    # Header
    click.secho("\n╔══════════════════════════════════════════════════════════════════════════════════╗", fg='cyan', bold=True)
    click.secho("║                       Hue Backup Control - Quick Reference                       ║", fg='cyan', bold=True)
    click.secho("╚══════════════════════════════════════════════════════════════════════════════════╝", fg='cyan', bold=True)
    click.echo()

    # Define command sections with icons and descriptions
    COMMAND_SECTIONS = [
        CommandSection(
            name="CACHE MANAGEMENT",
            icon="💾",
            commands=[
                ("reload", "Fetch fresh data from bridge and cache it"),
                ("cache-info", "Show cache status and age"),
                ("save-room <room>", "Save room config to timestamped file"),
                ("diff-room <file>", "Compare saved room with current state"),
                ("restore-room <file>", "Restore room config from saved backup"),
            ]
        ),
        CommandSection(
            name="STATUS & CONFIGURATION",
            icon="📋",
            commands=[
                ("setup", "Show bridge configuration and test connection"),
                ("status", "Bridge overview and statistics"),
            ]
        ),
        CommandSection(
            name="PHYSICAL DEVICES (Items)",
            icon="💡",
            commands=[
                ("switch-status", "View switches with battery level/state, mappings"),
                ("switch-status -t", "View switches in table format"),
                ("switches", "View switches with model info organised by room"),
                ("switches -r <room>", "View switches filtered by room"),
                ("plugs", "View smart plugs with status and model info"),
                ("plugs -r <room>", "View plugs filtered by room"),
                ("lights", "View light bulbs/fixtures with status and model"),
                ("lights -r <room>", "View lights filtered by room"),
                ("other", "View other devices (doorbell, chimes, bridge)"),
                ("other -r <room>", "View other devices filtered by room"),
                ("all", "View all devices in one unified view"),
                ("all -r <room>", "View all devices filtered by room"),
            ]
        ),
        CommandSection(
            name="LOGICAL GROUPS (Scenes & Rooms)",
            icon="🎭",
            commands=[
                ("button-data", "Show all wall control button programmes"),
                ("button-data -r <room>", "Show wall controls filtered by room"),
                ("locations", "Show all rooms/zones with lights and scenes"),
                ("locations --scenes -r <name>", "Show scenes in specific room/zone"),
                ("locations --lights", "Show lights in each room/zone"),
                ("scenes", "List all scenes"),
                ("scene-details", "Show scenes with light details"),
                ("scene-details -r <room>", "Show scenes filtered by room"),
                ("groups", "List all rooms/groups"),
                ("zones", "List all zones"),
                ("zones -v", "List zones with light details"),
                ("zones --multi-zone", "Show lights in multiple zones"),
                ("auto-dynamic", "View auto-dynamic status for all scenes"),
                ("auto-dynamic -r <room>", "View auto-dynamic filtered by room"),
                ("bridge-auto", "Show bridge automations (deprecated)"),
            ]
        ),
        CommandSection(
            name="PROGRAMMING",
            icon="🛠️",
            commands=[
                ("discover", "Press buttons to see event codes"),
                ("map <sensor> <btn> <scene>", "Create button → scene mapping"),
                ("mappings", "View all configured mappings"),
                ("program-button <switch> <btn>", "Programme button actions on switches (bridge-native)"),
                ("switch-info <sensor_id>", "Detailed info for one switch (cached)"),
            ]
        ),
        CommandSection(
            name="MONITORING & CONTROL",
            icon="🎯",
            commands=[
                ("monitor", "Run continuously to activate mappings"),
                ("activate-scene <scene_id>", "Activate a scene directly"),
                ("auto-dynamic --set on/off", "Enable/disable auto-dynamic for scenes"),
                ("auto-dynamic -s <name> --set", "Set auto-dynamic for specific scene"),
                ("power <light> [--on/--off]", "Turn light on/off"),
                ("brightness <light> <0-254>", "Set brightness"),
                ("colour <light> [options]", "Set colour/temperature"),
            ]
        ),
    ]

    # Print command sections
    for section in COMMAND_SECTIONS:
        click.secho(f"{section.icon} {section.name}", fg='yellow', bold=True)
        for cmd, desc in section.commands:
            # "  " (2 spaces) + cmd + padding to reach 42 chars + "  " + desc
            click.echo("  ", nl=False)
            click.secho(cmd, fg='green', nl=False)
            # Padding = 40 - len(cmd), then 2 more spaces before desc
            click.echo(" " * (40 - len(cmd)) + "  " + desc)
        click.echo()

    # Short flags
    click.secho("🔧 SHORT FLAGS (available where applicable)", fg='yellow', bold=True)
    flags = [
        ("-i, --bridge-ip", "Bridge IP address"),
        ("-u, --hue", "Hue value (0-65535)"),
        ("-s, --sat", "Saturation (0-254)"),
        ("-t, --ct", "Colour temperature (153-500)"),
    ]
    for flag, desc in flags:
        # "  " (2 spaces) + flag + padding to reach 42 chars + "  " + desc
        click.echo("  ", nl=False)
        click.secho(flag, fg='cyan', nl=False)
        # Padding = 40 - len(flag), then 2 more spaces before desc
        click.echo(" " * (40 - len(flag)) + "  " + desc)
    click.echo()

    # Footer
    click.secho("📖 For detailed help on any command:", fg='cyan')
    click.echo(f"  uv run python hue_backup.py {click.style('<command> -h', fg='white', bold=True)}")
    click.echo()


@click.command()
@click.option('--reconfigure', is_flag=True, help='Force reconfiguration even if credentials exist')
def configure_command(reconfigure):
    """Interactive bridge configuration and authentication setup.

    This command helps you:
    - Use 1Password for credentials (if available)
    - OR discover Hue bridges on your network
    - Create API credentials via link button
    - Save credentials to local config file

    Run this if you're setting up the tool for the first time,
    or if you need to reconfigure for a different bridge.
    """
    from core.auth import (
        discover_bridges,
        select_bridge_interactive,
        create_user_via_link_button,
        save_auth_to_user_config,
        load_auth_from_user_config,
        load_auth_from_1password
    )
    from core.config import is_op_available

    click.secho("\n╔══════════════════════════════════════════════════════════╗", fg='cyan', bold=True)
    click.secho("║          Hue Backup - Bridge Configuration               ║", fg='cyan', bold=True)
    click.secho("╚══════════════════════════════════════════════════════════╝", fg='cyan', bold=True)
    click.echo()

    # Check if already configured
    if not reconfigure:
        existing = load_auth_from_user_config()
        if existing:
            click.echo(f"✓ Credentials already configured for bridge {existing['bridge_ip']}")
            click.echo()
            if not click.confirm("Reconfigure anyway?", default=False):
                click.echo()
                return
            click.echo()

    # Ask about 1Password preference first
    vault = os.getenv('HUE_1PASSWORD_VAULT', 'Private')
    item = os.getenv('HUE_1PASSWORD_ITEM', 'Hue')

    use_1password = click.confirm("Do you want to use 1Password for credential storage?", default=True)
    click.echo()

    if use_1password:
        # Check if 1Password CLI is available
        if not is_op_available():
            click.secho("✗ 1Password CLI not installed", fg='red')
            click.echo()
            click.echo("To use 1Password, you need to install the CLI:")
            click.echo(click.style("  brew install --cask 1password-cli", fg='cyan'))
            click.echo()
            click.echo("After installing, run this command again.")
            click.echo()
            return

        # Check if already configured
        op_creds = load_auth_from_1password()
        if op_creds:
            click.secho(f"✓ 1Password already configured for bridge {op_creds['bridge_ip']}", fg='green')
            click.echo()
            click.echo("Your 1Password configuration is working correctly.")
            click.echo("No further setup needed unless you want to use a different bridge.")
            click.echo()
            return

        click.secho("✓ 1Password CLI detected", fg='green')
        click.echo()

    # Step 1: Discover bridges
    click.echo("Step 1: Discovering Hue bridges...")
    bridges = discover_bridges()

    bridge_ip = None

    if not bridges:
        click.echo("\nYou can find your bridge IP by:")
        click.echo("  • Check your router's DHCP client list")
        click.echo("  • Look for a device named 'Philips hue'")
        click.echo("  • Or use the Hue app: Settings → Hue Bridges → (i) icon")
        click.echo()
        if click.confirm("Enter bridge IP manually?", default=True):
            bridge_ip = click.prompt("Bridge IP address", type=str)
        else:
            click.echo("Configuration cancelled.")
            click.echo()
            return
    elif len(bridges) == 1:
        bridge_ip = bridges[0]['internalipaddress']
        bridge_name = bridges[0].get('name', 'Philips hue')
        click.secho(f"✓ Found 1 bridge: {bridge_name} ({bridge_ip})", fg='green')
    else:
        # Multiple bridges - interactive selection
        bridge_ip = select_bridge_interactive(bridges)
        if not bridge_ip:
            click.echo("Configuration cancelled.")
            click.echo()
            return

    click.echo()

    # Step 2: Create API credentials
    click.echo("Step 2: Creating API credentials...")
    click.echo()
    api_token = create_user_via_link_button(bridge_ip)

    if not api_token:
        click.secho("✗ Failed to create API credentials", fg='red')
        click.echo("Please check your network connection and try again.")
        click.echo()
        return

    click.echo()

    # Step 3: Save credentials
    config_path = Path.home() / '.hue_backup' / 'config.json'

    if use_1password:
        # Show 1Password instructions
        click.secho("Listen carefully, I will say this only once...", fg='cyan', bold=True)
        click.echo()
        click.echo("Add these credentials to your 1Password item:")
        click.echo(f"  Vault: {click.style(vault, fg='cyan')}")
        click.echo(f"  Item:  {click.style(item, fg='cyan')}")
        click.echo()
        click.echo(f"  {click.style('bridge-ip', fg='yellow')} → {click.style(bridge_ip, fg='green', bold=True)}")
        click.echo(f"  {click.style('API-token', fg='yellow')} → {click.style(api_token, fg='green', bold=True)}")
        click.echo()

        # Ask if they also want local backup
        if click.confirm("Also save to local config file for backup?", default=False):
            click.echo()
            if save_auth_to_user_config(bridge_ip, api_token):
                click.secho(f"✓ Also saved to {config_path}", fg='green')
                click.echo()
    else:
        # Save to local config only
        click.echo("Step 3: Saving credentials to local config...")
        if save_auth_to_user_config(bridge_ip, api_token):
            click.secho(f"✓ Configuration saved to {config_path}", fg='green')
            click.echo()
        else:
            click.secho(f"✗ Failed to save to {config_path}", fg='red')
            click.echo()

    click.secho("╔══════════════════════════════════════════════════════════╗", fg='green', bold=True)
    click.secho("║          Configuration complete!                         ║", fg='green', bold=True)
    click.secho("╚══════════════════════════════════════════════════════════╝", fg='green', bold=True)

    click.echo()


@click.command()
def setup_command():
    """Show current bridge configuration and test connection.

    Configuration sources (priority order):
    1. 1Password (env: HUE_1PASSWORD_VAULT, HUE_1PASSWORD_ITEM)
    2. Local config file (~/.hue_backup/config.json)
    3. Interactive setup (run 'configure' command)
    """
    from core.controller import HueController
    from core.auth import load_auth_from_1password, load_auth_from_user_config
    from core.config import is_op_available

    click.echo()
    click.secho("=== Hue Bridge Configuration ===", fg='cyan', bold=True)
    click.echo()

    # Check 1Password
    click.echo(click.style("1. 1Password", fg='cyan', bold=True))
    vault = os.getenv('HUE_1PASSWORD_VAULT', 'Private')
    item = os.getenv('HUE_1PASSWORD_ITEM', 'Hue')

    if not is_op_available():
        click.echo(f"   Status:      {click.style('✗ CLI not installed', fg='yellow')}")
        click.echo(f"   Note:        Install 1Password CLI ('op') to use this option")
    else:
        op_creds = load_auth_from_1password()
        if op_creds:
            click.echo(f"   Status:      {click.style('✓ Configured', fg='green')}")
            click.echo(f"   Vault:       {vault}")
            click.echo(f"   Item:        {item}")
            click.echo(f"   Bridge IP:   {op_creds['bridge_ip']}")
        else:
            click.echo(f"   Status:      {click.style('⚠ CLI available, credentials not found', fg='yellow')}")
            click.echo(f"   Vault:       {vault} (set HUE_1PASSWORD_VAULT to override)")
            click.echo(f"   Item:        {item} (set HUE_1PASSWORD_ITEM to override)")
            click.echo(f"   Note:        Add 'bridge-ip' and 'API-token' fields to your 1Password item")
    click.echo()

    # Check local config
    click.echo(click.style("2. Local Configuration", fg='cyan', bold=True))
    config_path = Path.home() / '.hue_backup' / 'config.json'
    local_creds = load_auth_from_user_config()
    if local_creds:
        click.echo(f"   Status:      {click.style('✓ Available', fg='green')}")
        click.echo(f"   Path:        {config_path}")
        click.echo(f"   Bridge IP:   {local_creds['bridge_ip']}")
    else:
        click.echo(f"   Status:      {click.style('✗ Not configured', fg='yellow')}")
        click.echo(f"   Path:        {config_path} (does not exist)")
    click.echo()

    # Project cache
    click.echo(click.style("3. Project Cache", fg='cyan', bold=True))
    click.echo(f"   Path:        {CONFIG_FILE}")
    click.echo(f"   Purpose:     Button mappings and bridge data cache")
    click.echo()

    # Test connection
    if not op_creds and not local_creds:
        click.secho("⚠ No authentication configured", fg='yellow', bold=True)
        click.echo()
        click.echo("Run this command to set up authentication:")
        click.echo(click.style("  uv run python hue_backup.py configure", fg='green', bold=True))
        click.echo()
        return

    # Attempt connection
    click.echo(click.style("Connection Test", fg='cyan', bold=True))
    click.echo("Testing connection to bridge...")

    controller = HueController()
    if controller.connect(interactive=False):
        click.secho(f"✓ Successfully connected to bridge at {controller.bridge_ip}!", fg='green', bold=True)

        # Show bridge info
        try:
            bridge_data = controller._request('GET', '/resource/bridge')
            if bridge_data and len(bridge_data) > 0:
                bridge = bridge_data[0]
                click.echo(f"  Bridge ID:  {bridge.get('id', 'Unknown')}")
                click.echo(f"  Model ID:   {bridge.get('bridge_id', 'Unknown')}")
        except Exception:
            pass
    else:
        click.secho("✗ Connection failed", fg='red', bold=True)
        click.echo()
        click.echo("Try reconfiguring:")
        click.echo(click.style("  uv run python hue_backup.py configure --reconfigure", fg='green', bold=True))

    click.echo()
