"""Configuration management and 1Password integration.

This module handles:
- Loading/saving configuration files
- 1Password CLI integration for API token retrieval
- Button mapping persistence
"""

import json
import subprocess
from pathlib import Path

# Configuration file paths
CONFIG_FILE = Path(__file__).parent.parent / 'cache' / 'hue_data.json'
USER_CONFIG_FILE = Path.home() / '.hue_backup' / 'config.json'


def is_op_available() -> bool:
    """Check if 1Password CLI is available."""
    try:
        result = subprocess.run(['op', '--version'],
                              capture_output=True,
                              timeout=2)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def load_from_1password() -> str | None:
    """Load API token from 1Password vault.

    DEPRECATED: Use core.auth.load_auth_from_1password() instead,
    which returns both bridge_ip and api_token.

    This function is kept for backward compatibility with existing code.

    Uses environment variables for configuration:
    - HUE_1PASSWORD_VAULT (default: "Private")
    - HUE_1PASSWORD_ITEM (default: "Hue")

    Returns:
        API token string, or None if not available
    """
    import os

    if not is_op_available():
        return None

    # Get vault and item names from environment
    vault = os.getenv('HUE_1PASSWORD_VAULT', 'Private')
    item = os.getenv('HUE_1PASSWORD_ITEM', 'Hue')

    try:
        # Get API token
        result = subprocess.run(
            ['op', 'item', 'get', item,
             '--vault', vault,
             '--fields', 'API-token',
             '--reveal'],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            return result.stdout.strip()

        return None

    except (subprocess.TimeoutExpired, Exception):
        return None


def load_config() -> dict:
    """Load configuration from local file (button mappings and cache).

    Returns:
        Dict with 'button_mappings' and optionally 'cache' keys
    """
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {'button_mappings': {}}


def save_config(config: dict):
    """Save configuration to file.

    Args:
        config: Configuration dict to save
    """
    # Create cache directory if it doesn't exist
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Save to local file
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)
