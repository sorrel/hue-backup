"""Cache management CLI commands.

This module provides CLI commands for reloading and inspecting the
persistent cache of Hue Bridge data.
"""

from datetime import datetime
import click

from core.cache import reload_cache, get_cache_info
from core.config import CONFIG_FILE
from models.utils import get_cache_controller


def register_cache_commands(cli):
    """Register cache management commands with the CLI group.

    Args:
        cli: Click group to register commands to
    """
    cli.add_command(reload_command)
    cli.add_command(cache_info_command)


@click.command(name='reload')
def reload_command():
    """Reload and cache all data from the Hue Bridge.

    Fetches lights, rooms, scenes, devices, buttons, and behaviour instances
    from the bridge and saves them to the local cache file. This cached data
    can be used offline to analyse scenes and programme switches without
    connecting to the bridge every time.
    """
    controller = get_cache_controller(auto_reload=False)

    if not controller.connect():
        return

    click.echo()
    click.secho("=== Reloading Hue Bridge Data ===", fg='cyan', bold=True)
    click.echo()

    if reload_cache(controller):
        click.echo()
        cache_info = controller.config.get('cache', {})
        last_updated = cache_info.get('last_updated', 'Unknown')
        click.secho(f"✓ Cache updated successfully", fg='green')
        click.echo(f"  Last updated: {last_updated}")
    else:
        click.secho("✗ Failed to reload cache", fg='red')

    click.echo()


@click.command(name='cache-info')
def cache_info_command():
    """Show cache status and information.

    Displays when the cache was last updated, how old it is, and whether
    it needs reloading. Also shows counts of cached resources.
    """
    controller = get_cache_controller(auto_reload=False)

    click.echo()
    click.secho("=== Cache Information ===", fg='cyan', bold=True)
    click.echo()

    info = get_cache_info(controller)

    if not info['exists']:
        click.secho("No cache found", fg='red')
        click.echo(f"Cache file: {CONFIG_FILE}")
        click.echo()
        click.echo("Run 'reload' to create the cache:")
        click.echo("  uv run python hue_backup.py reload")
        click.echo()
        return

    # Show last updated
    last_updated = info['last_updated']
    if last_updated:
        try:
            dt = datetime.fromisoformat(last_updated)
            formatted = dt.strftime('%d %b %Y at %H:%M:%S')
            click.echo(f"Last updated: {click.style(formatted, fg='green')}")
        except (ValueError, TypeError):
            click.echo(f"Last updated: {click.style(last_updated, fg='green')}")
    else:
        click.echo(f"Last updated: {click.style('Unknown', fg='yellow')}")

    # Show age
    age_hours = info['age_hours']
    if age_hours is not None:
        if age_hours < 1:
            age_str = f"{int(age_hours * 60)} minutes"
        elif age_hours < 24:
            age_str = f"{age_hours:.1f} hours"
        else:
            age_str = f"{age_hours / 24:.1f} days"

        age_colour = 'red' if info['is_stale'] else 'green'
        click.echo(f"Cache age:    {click.style(age_str, fg=age_colour)}")

        if info['is_stale']:
            click.echo(f"Status:       {click.style('STALE (>24 hours old)', fg='red')}")
            click.echo()
            click.echo("Run 'reload' to refresh the cache:")
            click.echo("  uv run python hue_backup.py reload")
        else:
            click.echo(f"Status:       {click.style('Fresh', fg='green')}")

    click.echo()

    # Show counts
    click.secho("Cached Resources:", fg='cyan')
    counts = info['counts']
    if counts:
        click.echo(f"  Lights:       {counts.get('lights', 0)}")
        click.echo(f"  Rooms:        {counts.get('rooms', 0)}")
        click.echo(f"  Zones:        {counts.get('zones', 0)}")
        click.echo(f"  Scenes:       {counts.get('scenes', 0)}")
        click.echo(f"  Devices:      {counts.get('devices', 0)}")
        click.echo(f"  Buttons:      {counts.get('buttons', 0)}")
        click.echo(f"  Behaviours:   {counts.get('behaviours', 0)}")
        click.echo(f"  Device Power: {counts.get('device_power', 0)}")

    click.echo()
    click.echo(f"Cache file: {CONFIG_FILE}")
    click.echo()
