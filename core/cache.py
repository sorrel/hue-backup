"""Cache management for Hue Bridge data.

This module handles persistent caching of bridge data including fetching,
validating cache freshness, and providing cache information.
"""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING
import click

from core.config import save_config, CONFIG_FILE

if TYPE_CHECKING:
    from hue_backup import HueController


def reload_cache(controller: 'HueController') -> bool:
    """Fetch all data from bridge and save to persistent cache.

    Args:
        controller: HueController instance with active connection

    Returns:
        True if cache reloaded successfully, False otherwise
    """
    if not controller.api_token:
        click.echo("Error: Not connected to bridge. Cannot reload cache.")
        return False

    click.echo("Fetching data from Hue Bridge...")

    # Delete persistent cache file to ensure completely fresh fetch
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()

    # Clear memory caches to force fresh fetches
    controller._lights_cache = None
    controller._rooms_cache = None
    controller._zones_cache = None
    controller._scenes_cache = None
    controller._devices_cache = None
    controller._buttons_cache = None
    controller._behaviour_instances_cache = None
    controller._device_power_cache = None

    try:
        # Fetch all resources
        lights = controller.get_lights()
        rooms = controller.get_rooms()
        zones = controller.get_zones()
        scenes = controller.get_scenes()
        devices = controller.get_devices()
        buttons = controller.get_buttons()
        behaviours = controller.get_behaviour_instances()
        device_power = controller.get_device_power()

        # Save to persistent cache
        controller.config['cache'] = {
            'last_updated': datetime.now().isoformat(),
            'lights': lights,
            'rooms': rooms,
            'zones': zones,
            'scenes': scenes,
            'devices': devices,
            'buttons': buttons,
            'behaviours': behaviours,
            'device_power': device_power,
        }

        save_config(controller.config)

        click.echo(f"✓ Cached {len(lights)} lights")
        click.echo(f"✓ Cached {len(rooms)} rooms")
        click.echo(f"✓ Cached {len(zones)} zones")
        click.echo(f"✓ Cached {len(scenes)} scenes")
        click.echo(f"✓ Cached {len(devices)} devices")
        click.echo(f"✓ Cached {len(buttons)} buttons")
        click.echo(f"✓ Cached {len(behaviours)} behaviour instances")
        click.echo(f"✓ Cached {len(device_power)} device power resources")
        click.echo(f"\nCache saved to {CONFIG_FILE}")

        return True

    except Exception as e:
        click.echo(f"Error reloading cache: {e}")
        return False


def is_cache_stale(controller: 'HueController', max_age_hours: int = 24) -> bool:
    """Check if cache is older than max_age_hours.

    Args:
        controller: HueController instance
        max_age_hours: Maximum age in hours before cache is considered stale

    Returns:
        True if cache is stale or doesn't exist, False if fresh
    """
    cache_data = controller.config.get('cache', {})
    last_updated = cache_data.get('last_updated')

    if not last_updated:
        return True  # No cache exists

    try:
        cache_time = datetime.fromisoformat(last_updated)
        age = datetime.now() - cache_time
        return age > timedelta(hours=max_age_hours)
    except (ValueError, TypeError):
        return True  # Invalid timestamp, treat as stale


def ensure_fresh_cache(controller: 'HueController', max_age_hours: int = 24) -> bool:
    """Ensure cache exists and is fresh. Auto-reload if stale.

    Args:
        controller: HueController instance
        max_age_hours: Maximum age in hours before cache is considered stale

    Returns:
        True if cache is fresh or successfully reloaded, False otherwise
    """
    if not controller.config.get('cache'):
        click.echo("No cache found. Fetching data from bridge...")
        if not controller.api_token:
            if not controller.connect():
                return False
        return reload_cache(controller)

    if is_cache_stale(controller, max_age_hours):
        cache_data = controller.config.get('cache', {})
        last_updated = cache_data.get('last_updated', 'unknown')
        click.echo(f"Cache is stale (last updated: {last_updated})")
        click.echo("Auto-reloading from bridge...")
        if not controller.api_token:
            if not controller.connect():
                return False
        return reload_cache(controller)

    return True


def get_cache_info(controller: 'HueController') -> dict:
    """Get information about the current cache.

    Args:
        controller: HueController instance

    Returns:
        Dictionary with cache information including exists, last_updated,
        age_hours, is_stale, and counts of cached resources
    """
    cache_data = controller.config.get('cache', {})

    if not cache_data:
        return {
            'exists': False,
            'last_updated': None,
            'age_hours': None,
            'is_stale': True,
            'counts': {}
        }

    last_updated_str = cache_data.get('last_updated')
    age_hours = None
    is_stale = True

    if last_updated_str:
        try:
            cache_time = datetime.fromisoformat(last_updated_str)
            age = datetime.now() - cache_time
            age_hours = age.total_seconds() / 3600
            is_stale = age > timedelta(hours=24)
        except (ValueError, TypeError):
            pass

    return {
        'exists': True,
        'last_updated': last_updated_str,
        'age_hours': age_hours,
        'is_stale': is_stale,
        'counts': {
            'lights': len(cache_data.get('lights', [])),
            'rooms': len(cache_data.get('rooms', [])),
            'scenes': len(cache_data.get('scenes', [])),
            'devices': len(cache_data.get('devices', [])),
            'buttons': len(cache_data.get('buttons', [])),
            'behaviours': len(cache_data.get('behaviours', [])),
            'device_power': len(cache_data.get('device_power', [])),
        }
    }
