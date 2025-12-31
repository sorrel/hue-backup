"""
Authentication module for Hue Bridge.

Handles bridge discovery, link button authentication, and credential management
from 1Password Environments via .env file (mounted by 1Password desktop app).
"""

import os
import json
from pathlib import Path

import click
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning

from models.types import AuthCredentials, DiscoveredBridge

# Disable SSL warnings for self-signed certificate
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


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






def load_auth_from_environment() -> AuthCredentials | None:
    """Load bridge IP and API token from environment variables.

    Designed to work with 1Password Environments via `op run`.
    Checks for HUE_BRIDGE_IP and HUE_API_TOKEN environment variables.

    Returns:
        Dict with 'bridge_ip' and 'api_token', or None if not found
    """
    bridge_ip = os.getenv('HUE_BRIDGE_IP')
    api_token = os.getenv('HUE_API_TOKEN')

    if bridge_ip and api_token:
        return {
            'bridge_ip': bridge_ip,
            'api_token': api_token
        }

    return None


def get_auth_credentials(interactive: bool = True) -> AuthCredentials | None:
    """Get authentication credentials using priority system.

    Priority order:
    1. Environment variables (HUE_BRIDGE_IP, HUE_API_TOKEN) - for 1Password Environments
    2. Interactive setup (if interactive=True)

    Args:
        interactive: If True, prompt for interactive setup if other methods fail

    Returns:
        Dict with 'bridge_ip' and 'api_token', or None if all methods fail
    """
    # Priority 1: Try environment variables (1Password Environments)
    credentials = load_auth_from_environment()
    if credentials:
        click.echo(f"✓ Loaded credentials from environment variables")
        return credentials

    # Priority 2: Interactive setup (if allowed)
    if not interactive:
        return None

    click.echo()
    click.secho("No authentication credentials found.", fg='yellow', bold=True)
    click.echo()
    click.echo("Would you like to create authentication credentials?")
    click.echo("This will:")
    click.echo("  • Discover your Hue bridge automatically")
    click.echo("  • Guide you through link button authentication")
    click.echo("  • Provide credentials to add to your 1Password Environment")
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

    # Step 3: Show credentials for 1Password Environment setup
    click.echo()
    click.secho("✓ Successfully created API credentials!", fg='green', bold=True)
    click.echo()
    click.secho("═══════════════════════════════════════════════════", fg='cyan', bold=True)
    click.secho("  Add these to your 1Password Environment:", fg='cyan', bold=True)
    click.secho("═══════════════════════════════════════════════════", fg='cyan', bold=True)
    click.echo()
    click.echo(f"  {click.style('HUE_BRIDGE_IP', fg='yellow', bold=True)} = {click.style(bridge_ip, fg='green')}")
    click.echo(f"  {click.style('HUE_API_TOKEN', fg='yellow', bold=True)} = {click.style(api_token, fg='green')}")
    click.echo()
    click.secho("Steps to add to 1Password Environment:", fg='cyan')
    click.echo("  1. Open 1Password desktop app")
    click.echo("  2. Go to Developer → View Environments")
    click.echo("  3. Create or open 'Hue Control' environment")
    click.echo("  4. Add the two variables above")
    click.echo("  5. Go to Destinations → Configure local .env file")
    click.echo(f"  6. Set path: {Path.cwd()}/.env")
    click.echo("  7. Click 'Mount .env file'")
    click.echo()
    click.secho("After adding to 1Password, run 'setup' to test connection.", fg='cyan')
    click.echo()

    # Return None since credentials aren't loaded in environment yet
    return None
