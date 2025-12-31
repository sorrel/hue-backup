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
    - Discover Hue bridges on your network
    - Create API credentials via link button authentication
    - Provides credentials to add to your 1Password Environment

    Run this if you're setting up the tool for the first time,
    or if you need to reconfigure for a different bridge.

    After configuration, add the credentials to your 1Password Environment
    and mount the .env file destination to complete setup.
    """
    from core.auth import (
        discover_bridges,
        select_bridge_interactive,
        create_user_via_link_button,
        load_auth_from_environment
    )

    click.secho("\n╔══════════════════════════════════════════════════════════╗", fg='cyan', bold=True)
    click.secho("║          Hue Backup - Bridge Configuration               ║", fg='cyan', bold=True)
    click.secho("╚══════════════════════════════════════════════════════════╝", fg='cyan', bold=True)
    click.echo()

    # Check if environment variables are already set (1Password Environments)
    env_creds = load_auth_from_environment()
    if env_creds and not reconfigure:
        click.secho(f"✓ Environment variables already configured for bridge {env_creds['bridge_ip']}", fg='green')
        click.echo()
        click.echo("Your 1Password Environment configuration is working correctly.")
        click.echo()
        if not click.confirm("Reconfigure anyway?", default=False):
            return
        click.echo()

    # Show 1Password Environment setup instructions
    click.echo("To use 1Password Environments:")
    click.echo("  1. Open 1Password desktop app")
    click.echo("  2. Go to Developer → View Environments")
    click.echo("  3. Create/open your 'Hue Control' environment")
    click.echo("  4. Add variables: HUE_BRIDGE_IP and HUE_API_TOKEN")
    click.echo("  5. Go to Destinations tab → Configure local .env file")
    click.echo(f"  6. Set path to: {Path.cwd()}/.env")
    click.echo("  7. Click 'Mount .env file'")
    click.echo()

    if not click.confirm("Do you need to generate new bridge credentials?", default=True):
        click.echo()
        click.echo("Setup cancelled. If you already have credentials, add them to")
        click.echo("your 1Password Environment and run 'setup' to test connection.")
        click.echo()
        return

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

    # Step 3: Show credentials for 1Password Environment
    click.echo()
    click.secho("Step 3: Add credentials to 1Password Environment", fg='cyan', bold=True)
    click.echo()
    click.secho("═══════════════════════════════════════════════════", fg='yellow', bold=True)
    click.secho("  Copy these credentials (displayed once only):", fg='yellow', bold=True)
    click.secho("═══════════════════════════════════════════════════", fg='yellow', bold=True)
    click.echo()
    click.echo(f"  {click.style('HUE_BRIDGE_IP', fg='cyan', bold=True)} = {click.style(bridge_ip, fg='green', bold=True)}")
    click.echo(f"  {click.style('HUE_API_TOKEN', fg='cyan', bold=True)} = {click.style(api_token, fg='green', bold=True)}")
    click.echo()
    click.secho("Add these to your 1Password Environment:", fg='cyan')
    click.echo("  1. Open 1Password desktop app")
    click.echo("  2. Go to Developer → View Environments")
    click.echo("  3. Open your 'Hue Control' environment")
    click.echo("  4. Add/update the two variables above")
    click.echo("  5. Ensure .env file destination is mounted")
    click.echo()

    click.secho("╔══════════════════════════════════════════════════════════╗", fg='green', bold=True)
    click.secho("║  Configuration complete! Run 'setup' to test connection  ║", fg='green', bold=True)
    click.secho("╚══════════════════════════════════════════════════════════╝", fg='green', bold=True)

    click.echo()


@click.command()
def setup_command():
    """Show current bridge configuration and test connection.

    Configuration sources (priority order):
    1. Environment variables (HUE_BRIDGE_IP, HUE_API_TOKEN) - 1Password Environments
    2. Interactive setup (run 'configure' command)
    """
    from core.controller import HueController
    from core.auth import load_auth_from_environment

    click.echo()
    click.secho("=== Hue Bridge Configuration ===", fg='cyan', bold=True)
    click.echo()

    # Check environment variables (1Password Environments)
    click.echo(click.style("1. Environment Variables (1Password Environments)", fg='cyan', bold=True))
    env_creds = load_auth_from_environment()
    if env_creds:
        click.echo(f"   Status:      {click.style('✓ Configured', fg='green')}")
        click.echo(f"   Variables:   HUE_BRIDGE_IP, HUE_API_TOKEN")
        click.echo(f"   Bridge IP:   {env_creds['bridge_ip']}")
        click.echo(f"   Source:      .env file (1Password mounted)")
    else:
        click.echo(f"   Status:      {click.style('✗ Not configured', fg='yellow')}")
        click.echo(f"   Note:        Set up via 1Password Environments → local .env file")
    click.echo()

    # Project cache
    click.echo(click.style("2. Project Cache", fg='cyan', bold=True))
    click.echo(f"   Path:        {CONFIG_FILE}")
    click.echo(f"   Purpose:     Button mappings and bridge data cache")
    click.echo()

    # Test connection
    if not env_creds:
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
