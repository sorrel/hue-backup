"""
Authentication module for Hue Bridge.

Handles bridge discovery, link button authentication, and credential management
from multiple sources (1Password, local config file, interactive setup).
"""

import os
import json
import subprocess
from pathlib import Path

import click
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning

from models.types import AuthCredentials, DiscoveredBridge

# Disable SSL warnings for self-signed certificate
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# User configuration file location
USER_CONFIG_FILE = Path.home() / '.hue_backup' / 'config.json'


def discover_bridges() -> list[DiscoveredBridge]:
    """Discover Hue bridges on the network using N-UPnP.

    Uses the Philips discovery service at https://discovery.meethue.com/
    to find bridges on the same network.

    Returns:
        List of bridge dicts with keys: id, internalipaddress, name, macaddress
        Empty list if discovery fails or no bridges found
    """
    try:
        response = requests.get('https://discovery.meethue.com/', timeout=5)
        response.raise_for_status()
        bridges = response.json()

        # Sort by IP address for consistency
        return sorted(bridges, key=lambda b: b.get('internalipaddress', ''))

    except requests.exceptions.HTTPError as e:
        if '429' in str(e):
            click.secho("⚠ Philips discovery service rate limit reached", fg='yellow')
            click.echo("This is normal - Philips limits discovery requests.")
            click.echo("You can enter your bridge IP manually instead.")
        else:
            click.echo(f"Bridge discovery failed: {e}", err=True)
        return []
    except requests.exceptions.RequestException as e:
        click.echo(f"Bridge discovery failed: {e}", err=True)
        return []
    except (ValueError, KeyError) as e:
        click.echo(f"Failed to parse discovery response: {e}", err=True)
        return []


def select_bridge_interactive(bridges: list[dict]) -> str | None:
    """Display interactive menu to select a bridge from discovered list.

    Args:
        bridges: List of bridge dicts from discover_bridges()

    Returns:
        Selected bridge IP address, or None if cancelled/invalid
    """
    if not bridges:
        return None

    click.echo()
    click.secho(f"Found {len(bridges)} Hue bridge{'s' if len(bridges) > 1 else ''}:", fg='cyan', bold=True)
    click.echo()

    for i, bridge in enumerate(bridges, 1):
        name = bridge.get('name', 'Philips hue')
        ip = bridge.get('internalipaddress', 'Unknown')
        mac = bridge.get('macaddress', 'Unknown')

        click.echo(f"  {click.style(str(i), fg='green', bold=True)}. {name} ({ip}) - MAC: {mac}")

    click.echo()

    # Prompt for selection
    try:
        choice = click.prompt(
            f"Select bridge [1-{len(bridges)}] or 'q' to cancel",
            type=str,
            default='1'
        )

        if choice.lower() == 'q':
            return None

        # Validate selection
        index = int(choice) - 1
        if 0 <= index < len(bridges):
            return bridges[index].get('internalipaddress')
        else:
            click.echo(f"Invalid selection: {choice}", err=True)
            return None

    except (ValueError, KeyboardInterrupt):
        click.echo("\nSelection cancelled.", err=True)
        return None


def create_user_via_link_button(bridge_ip: str, app_name: str = "hue_backup#cli") -> str | None:
    """Create new API user via link button authentication.

    Requires the user to press the physical link button on the Hue bridge
    to authorise the application. Retries up to 3 times if button not pressed.

    Args:
        bridge_ip: Bridge IP address
        app_name: Application identifier (devicetype)

    Returns:
        API token/username if successful, None otherwise
    """
    url = f"https://{bridge_ip}/api"
    payload = {"devicetype": app_name}

    max_attempts = 3

    for attempt in range(1, max_attempts + 1):
        try:
            click.echo()
            click.secho("╔═══════════════════════════════════════════════════════╗", fg='yellow', bold=True)
            click.secho("║  Press the LINK BUTTON on your Hue Bridge             ║", fg='yellow', bold=True)
            click.secho("║  You have 30 seconds after pressing the button        ║", fg='yellow', bold=True)
            click.secho("╚═══════════════════════════════════════════════════════╝", fg='yellow', bold=True)
            click.echo()

            # Wait for user confirmation
            click.pause("Press Enter when ready...")

            click.echo(f"Waiting for button press... (attempt {attempt}/{max_attempts})")

            # Make POST request
            response = requests.post(
                url,
                json=payload,
                verify=False,  # Self-signed certificate
                timeout=35  # Allow time for button press
            )

            data = response.json()

            # Check response
            if isinstance(data, list) and len(data) > 0:
                if 'success' in data[0]:
                    token = data[0]['success']['username']
                    click.echo()
                    click.secho("✓ Successfully created API token!", fg='green', bold=True)
                    return token

                elif 'error' in data[0]:
                    error = data[0]['error']
                    error_type = error.get('type')
                    error_desc = error.get('description', 'Unknown error')

                    if error_type == 101:  # Link button not pressed
                        if attempt < max_attempts:
                            click.secho(f"✗ Link button not pressed. Please try again.", fg='red')
                            continue
                        else:
                            click.secho(f"✗ Failed after {max_attempts} attempts.", fg='red')
                            click.echo("Please ensure you press the link button before pressing Enter.")
                            return None
                    else:
                        click.echo(f"Error: {error_desc}", err=True)
                        return None

        except requests.exceptions.Timeout:
            click.echo("Connection timed out. Please check your network.", err=True)
            if attempt < max_attempts:
                continue
            return None

        except requests.exceptions.RequestException as e:
            click.echo(f"Connection error: {e}", err=True)
            return None

        except (ValueError, KeyError) as e:
            click.echo(f"Failed to parse response: {e}", err=True)
            return None

    return None


def load_auth_from_user_config() -> AuthCredentials | None:
    """Load bridge IP and API token from user config file.

    Returns:
        Dict with 'bridge_ip' and 'api_token', or None if not found
    """
    try:
        if not USER_CONFIG_FILE.exists():
            return None

        with open(USER_CONFIG_FILE, 'r') as f:
            config = json.load(f)

        bridge_ip = config.get('bridge_ip')
        api_token = config.get('api_token')

        # Validate both values exist and are non-empty strings
        if bridge_ip and api_token and isinstance(bridge_ip, str) and isinstance(api_token, str):
            return {
                'bridge_ip': bridge_ip,
                'api_token': api_token
            }

        return None

    except (json.JSONDecodeError, IOError) as e:
        click.echo(f"Warning: Failed to load config from {USER_CONFIG_FILE}: {e}", err=True)
        return None


def save_auth_to_user_config(bridge_ip: str, api_token: str) -> bool:
    """Save bridge IP and API token to user config file.

    Creates the config directory if it doesn't exist and sets secure
    file permissions (600 - user read/write only).

    Args:
        bridge_ip: Bridge IP address
        api_token: API token/username

    Returns:
        True if saved successfully, False otherwise
    """
    try:
        # Create directory if needed
        USER_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Load existing config or create new
        config = {}
        if USER_CONFIG_FILE.exists():
            try:
                with open(USER_CONFIG_FILE, 'r') as f:
                    config = json.load(f)
            except (json.JSONDecodeError, IOError):
                # If existing file is corrupt, start fresh
                pass

        # Update auth credentials
        config['bridge_ip'] = bridge_ip
        config['api_token'] = api_token

        # Write config file
        with open(USER_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)

        # Set secure file permissions (user read/write only)
        os.chmod(USER_CONFIG_FILE, 0o600)

        return True

    except (IOError, OSError) as e:
        click.echo(f"Error: Failed to save config to {USER_CONFIG_FILE}: {e}", err=True)
        return False


def load_auth_from_1password() -> AuthCredentials | None:
    """Load bridge IP and API token from 1Password vault.

    Reads vault and item names from environment variables:
    - HUE_1PASSWORD_VAULT (default: "Private")
    - HUE_1PASSWORD_ITEM (default: "Hue")

    Expects two fields in the 1Password item:
    - "bridge-ip": Bridge IP address
    - "API-token": API authentication token

    Returns:
        Dict with 'bridge_ip' and 'api_token', or None if not available
    """
    from core.config import is_op_available

    # Check if 1Password CLI is available
    if not is_op_available():
        return None

    # Get vault and item names from environment
    vault = os.getenv('HUE_1PASSWORD_VAULT', 'Private')
    item = os.getenv('HUE_1PASSWORD_ITEM', 'Hue')

    try:
        # Fetch bridge IP
        result_ip = subprocess.run(
            ['op', 'item', 'get', item,
             '--vault', vault,
             '--fields', 'bridge-ip',
             '--reveal'],
            capture_output=True,
            text=True,
            timeout=10
        )

        # Fetch API token
        result_token = subprocess.run(
            ['op', 'item', 'get', item,
             '--vault', vault,
             '--fields', 'API-token',
             '--reveal'],
            capture_output=True,
            text=True,
            timeout=10
        )

        # Check both commands succeeded
        if result_ip.returncode == 0 and result_token.returncode == 0:
            bridge_ip = result_ip.stdout.strip()
            api_token = result_token.stdout.strip()

            if bridge_ip and api_token:
                return {
                    'bridge_ip': bridge_ip,
                    'api_token': api_token
                }

        return None

    except (subprocess.TimeoutExpired, Exception) as e:
        click.echo(f"Warning: Failed to load from 1Password: {e}", err=True)
        return None


def get_auth_credentials(interactive: bool = True) -> AuthCredentials | None:
    """Get authentication credentials using priority system.

    Priority order:
    1. 1Password (if available and configured)
    2. Local config file (~/.hue_backup/config.json)
    3. Interactive setup (if interactive=True)

    Args:
        interactive: If True, prompt for interactive setup if other methods fail

    Returns:
        Dict with 'bridge_ip' and 'api_token', or None if all methods fail
    """
    # Priority 1: Try 1Password
    credentials = load_auth_from_1password()
    if credentials:
        click.echo(f"✓ Loaded credentials from 1Password")
        return credentials

    # Priority 2: Try local config file
    credentials = load_auth_from_user_config()
    if credentials:
        click.echo(f"✓ Loaded credentials from {USER_CONFIG_FILE}")
        return credentials

    # Priority 3: Interactive setup (if allowed)
    if not interactive:
        return None

    click.echo()
    click.secho("No authentication credentials found.", fg='yellow', bold=True)
    click.echo()
    click.echo("Would you like to set up authentication now?")
    click.echo("This will:")
    click.echo("  • Discover your Hue bridge automatically")
    click.echo("  • Guide you through link button authentication")
    click.echo(f"  • Save credentials to {USER_CONFIG_FILE}")
    click.echo()

    if not click.confirm("Continue with setup?", default=True):
        return None

    # Step 1: Discover bridges
    click.echo("\nDiscovering Hue bridges...")
    bridges = discover_bridges()

    bridge_ip = None

    if not bridges:
        click.secho("⚠ No bridges found via automatic discovery", fg='yellow')
        click.echo()
        if click.confirm("Enter bridge IP manually?", default=True):
            bridge_ip = click.prompt("Bridge IP address", type=str)
        else:
            click.echo("Setup cancelled.")
            return None

    elif len(bridges) == 1:
        # Single bridge - auto-select with confirmation
        bridge_ip = bridges[0]['internalipaddress']
        bridge_name = bridges[0].get('name', 'Philips hue')
        click.secho(f"✓ Found 1 bridge: {bridge_name} ({bridge_ip})", fg='green')
        click.echo()
        if not click.confirm("Use this bridge?", default=True):
            click.echo("Setup cancelled.")
            return None

    else:
        # Multiple bridges - interactive selection
        bridge_ip = select_bridge_interactive(bridges)
        if not bridge_ip:
            click.echo("Setup cancelled.")
            return None

    # Step 2: Create API credentials via link button
    api_token = create_user_via_link_button(bridge_ip)

    if not api_token:
        click.secho("✗ Failed to create API credentials", fg='red')
        return None

    # Step 3: Save credentials
    click.echo()
    click.echo("Saving credentials...")

    if save_auth_to_user_config(bridge_ip, api_token):
        click.secho(f"✓ Configuration saved to {USER_CONFIG_FILE}", fg='green')
        return {
            'bridge_ip': bridge_ip,
            'api_token': api_token
        }
    else:
        click.secho("✗ Failed to save configuration", fg='red')
        click.echo("\nYou can manually create the config file:")
        click.echo(f"  mkdir -p {USER_CONFIG_FILE.parent}")
        click.echo(f"  cat > {USER_CONFIG_FILE} << 'EOF'")
        click.echo(f'  {{"bridge_ip": "{bridge_ip}", "api_token": "{api_token}"}}')
        click.echo(f"  EOF")
        click.echo(f"  chmod 600 {USER_CONFIG_FILE}")

        # Return credentials even if save failed
        return {
            'bridge_ip': bridge_ip,
            'api_token': api_token
        }
