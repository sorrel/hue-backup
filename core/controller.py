"""HueController class for managing Hue Bridge API interactions.

This module contains the main controller class that handles all communication
with the Philips Hue Bridge using API v2.
"""

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
import click
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from core.config import load_config, save_config, load_from_1password
from core.cache import reload_cache, is_cache_stale, ensure_fresh_cache, get_cache_info
from models.utils import create_name_lookup

# Button labels for wall controls
BUTTON_LABELS_EXTENDED = {
    1: 'ON',
    2: 'DIM UP',
    3: 'DIM DOWN',
    4: 'OFF',
    34: 'DIAL ROTATE',
    35: 'DIAL PRESS',
}

# Disable SSL warnings for self-signed certificate
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


class HueController:
    """Manages connection and operations with Philips Hue Bridge using API v2."""

    def __init__(self, use_cache: bool = False, bridge_ip: str | None = None,
                 api_token: str | None = None):
        """Initialise HueController.

        Args:
            use_cache: If True, use persistent cache for API requests
            bridge_ip: Bridge IP address (optional, loaded during connect() if not provided)
            api_token: API authentication token (optional, loaded during connect() if not provided)
        """
        self.bridge_ip = bridge_ip
        self.api_token = api_token
        self.base_url = f"https://{bridge_ip}/clip/v2" if bridge_ip else None
        self.config = load_config()
        self.button_mappings = self.config.get('button_mappings', {})
        self.last_button_states = {}
        self.session = requests.Session()
        self.session.verify = False  # Accept self-signed certificate
        self.use_cache = use_cache

        # Cache for v2 resources (memory)
        self._devices_cache = None
        self._buttons_cache = None
        self._scenes_cache = None
        self._behaviour_instances_cache = None
        self._lights_cache = None
        self._rooms_cache = None
        self._zones_cache = None
        self._device_power_cache = None

    def _get_cached_resource(self, resource_type: str, cache_key: str, endpoint: str) -> list[dict]:
        """Generic helper for fetching resources with cache support.

        Checks persistent cache first (if use_cache enabled), then memory cache,
        then fetches from API if needed.

        Args:
            resource_type: The memory cache attribute name (e.g., '_lights_cache')
            cache_key: The key in the persistent cache (e.g., 'lights')
            endpoint: The API endpoint to fetch from (e.g., '/resource/light')

        Returns:
            List of resource dictionaries
        """
        # Check persistent cache first if enabled
        if self.use_cache:
            cached = self.config.get('cache', {}).get(cache_key, [])
            if cached:
                return cached

        # Check memory cache
        memory_cache = getattr(self, resource_type, None)
        if memory_cache is not None:
            return memory_cache

        # Fetch from API
        if not self.api_token:
            return []
        result = self._request('GET', endpoint)
        setattr(self, resource_type, result if result else [])
        return getattr(self, resource_type)

    def _update_cache_entry(self, resource_type: str, resource_id: str, new_data: dict) -> bool:
        """Update a single entry in the persistent cache (write-through cache pattern).

        This implements the write-through cache strategy: when we modify a resource via
        the API, we immediately update the local cache to reflect the change. This avoids
        needing to reload the entire cache after each write operation.

        Args:
            resource_type: The cache key (e.g., 'lights', 'scenes', 'behaviours')
            resource_id: The ID of the resource to update
            new_data: The updated resource data (full resource object with 'id' field)

        Returns:
            True if cache was updated, False if cache doesn't exist or resource not found
        """
        if not self.use_cache:
            return False

        cache = self.config.get('cache', {})
        if not cache:
            return False

        items = cache.get(resource_type, [])
        if not items:
            return False

        # Find and update the resource
        updated = False
        for i, item in enumerate(items):
            if item.get('id') == resource_id:
                items[i] = new_data
                updated = True
                break

        if updated:
            cache[resource_type] = items
            self.config['cache'] = cache
            save_config(self.config)

        return updated

    def _add_cache_entry(self, resource_type: str, new_data: dict) -> bool:
        """Add a new entry to the persistent cache (for POST/create operations).

        Args:
            resource_type: The cache key (e.g., 'lights', 'scenes', 'behaviours')
            new_data: The new resource data (full resource object with 'id' field)

        Returns:
            True if cache was updated, False if cache doesn't exist
        """
        if not self.use_cache:
            return False

        cache = self.config.get('cache', {})
        if not cache:
            return False

        items = cache.get(resource_type, [])
        items.append(new_data)

        cache[resource_type] = items
        self.config['cache'] = cache
        save_config(self.config)

        return True

    def _remove_cache_entry(self, resource_type: str, resource_id: str) -> bool:
        """Remove an entry from the persistent cache (for DELETE operations).

        Args:
            resource_type: The cache key (e.g., 'lights', 'scenes', 'behaviours')
            resource_id: The ID of the resource to remove

        Returns:
            True if cache was updated, False if cache doesn't exist or resource not found
        """
        if not self.use_cache:
            return False

        cache = self.config.get('cache', {})
        if not cache:
            return False

        items = cache.get(resource_type, [])
        if not items:
            return False

        # Remove the resource
        original_length = len(items)
        items = [item for item in items if item.get('id') != resource_id]

        if len(items) < original_length:
            cache[resource_type] = items
            self.config['cache'] = cache
            save_config(self.config)
            return True

        return False

    def _request(self, method: str, endpoint: str, data: dict | None = None) -> dict | None:
        """Make a request to the Hue Bridge API v2."""
        if not self.base_url:
            click.echo("Error: Bridge URL not set. Call connect() first.", err=True)
            return None

        url = f"{self.base_url}{endpoint}"
        headers = {"hue-application-key": self.api_token}

        try:
            if method == 'GET':
                response = self.session.get(url, headers=headers, timeout=5)
            elif method == 'PUT':
                response = self.session.put(url, headers=headers, json=data, timeout=5)
            elif method == 'POST':
                response = self.session.post(url, headers=headers, json=data, timeout=5)
            elif method == 'DELETE':
                response = self.session.delete(url, headers=headers, timeout=5)
            else:
                return None

            response.raise_for_status()
            result = response.json()

            # v2 API returns {errors: [], data: [...]}
            if isinstance(result, dict) and 'data' in result:
                return result['data']
            return result
        except Exception as e:
            click.echo(f"API request error: {e}")
            # Show response body for debugging
            try:
                if hasattr(e, 'response') and e.response is not None:
                    error_body = e.response.text
                    click.echo(f"Response body: {error_body}", err=True)
            except:
                pass
            return None

    def connect(self, interactive: bool = True) -> bool:
        """Connect to the Hue Bridge using authentication priority system.

        Authentication priority:
        1. Use bridge_ip/api_token if provided to __init__()
        2. Try 1Password
        3. Try local config file (~/.hue_backup/config.json)
        4. Interactive setup (if interactive=True)

        Args:
            interactive: If True, prompt for interactive setup if other methods fail

        Returns:
            True if connected successfully, False otherwise
        """
        from core.auth import get_auth_credentials

        try:
            # If credentials already set (via __init__), use them
            if self.api_token and self.bridge_ip:
                click.echo(f"Using provided credentials for bridge {self.bridge_ip}")
            else:
                # Load credentials using priority system
                credentials = get_auth_credentials(interactive=interactive)

                if not credentials:
                    click.echo("Error: Could not obtain authentication credentials.")
                    click.echo("Run 'uv run python hue_backup.py configure' for interactive setup.")
                    return False

                self.bridge_ip = credentials['bridge_ip']
                self.api_token = credentials['api_token']

            # Update base_url with bridge IP
            self.base_url = f"https://{self.bridge_ip}/clip/v2"

            # Test connection by getting bridge resource
            result = self._request('GET', '/resource/bridge')

            if not result:
                click.echo(f"Error: Failed to connect to bridge at {self.bridge_ip}")
                click.echo("Check that the bridge IP and API token are correct.")
                return False

            # Success
            click.secho(f"✓ Connected to Hue Bridge at {self.bridge_ip}", fg='green')
            return True

        except requests.exceptions.RequestException as e:
            click.echo(f"Error connecting to bridge at {self.bridge_ip}: {e}")
            return False
        except Exception as e:
            click.echo(f"Unexpected error: {e}")
            return False

    def get_lights(self) -> list[dict]:
        """Get all lights with their current state (v2 API)."""
        return self._get_cached_resource('_lights_cache', 'lights', '/resource/light')

    def get_light_by_name(self, name: str) -> dict | None:
        """Get a light by name (case-insensitive). Returns light dict with id."""
        lights = self.get_lights()
        for light in lights:
            if light.get('metadata', {}).get('name', '').lower() == name.lower():
                return light
        return None

    def get_devices(self) -> list[dict]:
        """Get all devices (v2 API)."""
        return self._get_cached_resource('_devices_cache', 'devices', '/resource/device')

    def get_buttons(self) -> list[dict]:
        """Get all button resources (v2 API)."""
        return self._get_cached_resource('_buttons_cache', 'buttons', '/resource/button')

    def get_scenes(self) -> list[dict]:
        """Get all scenes (v2 API)."""
        return self._get_cached_resource('_scenes_cache', 'scenes', '/resource/scene')

    def get_behaviour_instances(self) -> list[dict]:
        """Get all behaviour instances - these contain button-to-scene mappings (v2 API)."""
        return self._get_cached_resource('_behaviour_instances_cache', 'behaviours', '/resource/behavior_instance')

    def get_device_power(self) -> list[dict]:
        """Get all device_power resources - contains battery level and state (v2 API)."""
        return self._get_cached_resource('_device_power_cache', 'device_power', '/resource/device_power')

    def get_rooms(self) -> list[dict]:
        """Get all rooms/groups (v2 API)."""
        return self._get_cached_resource('_rooms_cache', 'rooms', '/resource/room')

    def get_zones(self) -> list[dict]:
        """Get all zones (v2 API)."""
        return self._get_cached_resource('_zones_cache', 'zones', '/resource/zone')

    @staticmethod
    def _extract_where_lists_from_config(config: dict) -> list[list[dict]]:
        """Extract all 'where' lists from a behaviour configuration.

        Handles multiple locations where room info can be stored:
        - Top-level 'where' (new format)
        - 'button1.where' (old format)
        - 'rotary.where' (dial rotary)
        - 'buttons[rid].where' (new format with buttons dict)

        Returns:
            List of 'where' lists found in the config
        """
        where_lists = []

        # Top-level where (new format)
        if 'where' in config:
            where_lists.append(config['where'])

        # Old format: check button1.where
        if 'button1' in config and 'where' in config['button1']:
            where_lists.append(config['button1']['where'])

        # Dial rotary.where
        if 'rotary' in config and 'where' in config['rotary']:
            where_lists.append(config['rotary']['where'])

        # New format with buttons dict: check each button's where field
        if 'buttons' in config:
            for button_rid, button_config in config['buttons'].items():
                if 'where' in button_config:
                    where_lists.append(button_config['where'])

        return where_lists

    def _extract_rooms_from_where_lists(self, where_lists: list[list[dict]], room_lookup: dict[str, str]) -> list[str]:
        """Extract unique room names from where lists.

        Args:
            where_lists: List of 'where' lists from behaviour config
            room_lookup: dict mapping room IDs to names

        Returns:
            List of unique room names
        """
        room_names = []
        for where_list in where_lists:
            for location in where_list:
                room_rid = location.get('group', {}).get('rid')
                if room_rid:
                    room_name = room_lookup.get(room_rid, '')
                    if room_name and room_name not in room_names:
                        room_names.append(room_name)
        return room_names

    def reload_cache(self) -> bool:
        """Fetch all data from bridge and save to persistent cache."""
        return reload_cache(self)

    def is_cache_stale(self, max_age_hours: int = 24) -> bool:
        """Check if cache is older than max_age_hours."""
        return is_cache_stale(self, max_age_hours)

    def ensure_fresh_cache(self, max_age_hours: int = 24) -> bool:
        """Ensure cache is fresh, reload if stale."""
        return ensure_fresh_cache(self, max_age_hours)

    def get_sensors(self) -> dict:
        """Get all switch devices in v1-compatible format for backward compatibility."""
        # Convert v2 devices to v1-like structure
        devices = self.get_devices()
        sensors_dict = {}

        for device in devices:
            # Only include devices with buttons (switches)
            button_services = [s for s in device.get('services', []) if s.get('rtype') == 'button']
            if not button_services:
                continue

            # Extract id_v1 if available
            id_v1 = device.get('id_v1', '')
            if id_v1 and id_v1.startswith('/sensors/'):
                sensor_id = id_v1.split('/')[-1]
            else:
                sensor_id = device.get('id', '')

            # Get battery info from device_power service
            battery_level = None
            battery_state = None
            power_services = [s for s in device.get('services', []) if s.get('rtype') == 'device_power']
            if power_services:
                power_rid = power_services[0].get('rid')

                # Try cache first
                if self.use_cache:
                    device_power_cache = self.config.get('cache', {}).get('device_power', [])
                    for power_data in device_power_cache:
                        if power_data.get('id') == power_rid:
                            power_state = power_data.get('power_state', {})
                            battery_level = power_state.get('battery_level')
                            battery_state = power_state.get('battery_state')
                            break

                # Fall back to live fetch if not in cache
                if battery_level is None and self.api_token:
                    power_result = self._request('GET', f"/resource/device_power/{power_rid}")
                    if power_result and len(power_result) > 0:
                        power_state = power_result[0].get('power_state', {})
                        battery_level = power_state.get('battery_level')
                        battery_state = power_state.get('battery_state')

            # Get button state - find the most recently updated button
            buttonevent = None
            lastupdated = None
            buttons = self.get_buttons()

            # Map event names to v1 event codes
            event_code_map = {
                'initial_press': '000',
                'repeat': '001',
                'short_release': '002',
                'long_release': '003',
                'long_press': '004'
            }

            for button_service in button_services:
                button_rid = button_service.get('rid')
                # Find this button in the buttons list
                for btn in buttons:
                    if btn['id'] == button_rid:
                        control_id = btn.get('metadata', {}).get('control_id', 1)
                        last_event = btn.get('button', {}).get('last_event', '')
                        event_code = event_code_map.get(last_event, '002')

                        # Construct v1-style button event code: control_id + event_code
                        btn_event = int(f"{control_id}{event_code}")
                        btn_updated = btn.get('button', {}).get('button_report', {}).get('updated', '')

                        # Keep the most recent button event
                        if lastupdated is None or btn_updated > lastupdated:
                            buttonevent = btn_event
                            lastupdated = btn_updated

            # Build config with battery data
            config_data = {}
            if battery_level is not None:
                config_data['battery'] = battery_level
            if battery_state is not None:
                config_data['battery_state'] = battery_state

            sensors_dict[sensor_id] = {
                'name': device.get('metadata', {}).get('name', 'Unknown'),
                'type': 'ZLLSwitch',
                'state': {'buttonevent': buttonevent, 'lastupdated': lastupdated} if buttonevent else {},
                'config': config_data,
                'services': device.get('services', []),
                'device_id': device.get('id', '')  # Store device ID for room lookup
            }

        return sensors_dict

    def get_device_rooms(self) -> dict[str, list[str]]:
        """Get a mapping of device IDs to room names from behaviour instances."""
        behaviours = self.get_behaviour_instances()
        rooms_list = self.get_rooms()

        # Create room lookup
        room_lookup = create_name_lookup(rooms_list)

        # Map device_id -> list of room names
        device_rooms = {}

        for behaviour in behaviours:
            config = behaviour.get('configuration', {})
            device_rid = config.get('device', {}).get('rid')

            if not device_rid:
                continue

            # Extract rooms using helper methods
            where_lists = self._extract_where_lists_from_config(config)
            room_names = self._extract_rooms_from_where_lists(where_lists, room_lookup)

            # Add to device_rooms, avoiding duplicates
            if device_rid not in device_rooms:
                device_rooms[device_rid] = []
            for room_name in room_names:
                if room_name not in device_rooms[device_rid]:
                    device_rooms[device_rid].append(room_name)

        return device_rooms

    def get_scene_to_switch_mapping(self) -> dict[str, list[dict]]:
        """Get a mapping of scene IDs to switches/buttons they're programmed on.

        Returns dict: {scene_id: [{'device_name': str, 'button': str, 'action': str}, ...]}
        """
        devices = self.get_devices()
        behaviours = self.get_behaviour_instances()
        buttons = self.get_buttons()

        # Create device lookup
        device_lookup = create_name_lookup(devices)

        # Create button lookup by rid
        button_lookup = {b['id']: b for b in buttons}

        # Build the mapping
        scene_mapping = {}

        for behaviour in behaviours:
            config = behaviour.get('configuration', {})
            device_rid = config.get('device', {}).get('rid')

            if not device_rid:
                continue

            device_name = device_lookup.get(device_rid, 'Unknown')

            # Handle both new format ('buttons' dict) and old format ('button1', 'button2', etc.)
            button_list = []

            if 'buttons' in config:
                # New format: buttons is a dict with button rids as keys
                buttons_config = config.get('buttons', {})
                for button_rid, button_config in buttons_config.items():
                    button_res = button_lookup.get(button_rid, {})
                    control_id = button_res.get('metadata', {}).get('control_id', 999)
                    button_list.append((control_id, button_rid, button_config))
            else:
                # Old format: button1, button2, button3, button4 as separate keys
                for button_key in ['button1', 'button2', 'button3', 'button4']:
                    if button_key in config:
                        button_config = config[button_key]
                        control_id = int(button_key.replace('button', ''))
                        button_list.append((control_id, button_key, button_config))

            # Check rotary/dial buttons
            if 'rotary' in config:
                rotary_config = config['rotary']
                button_list.append((34, 'rotary', rotary_config))

            # Extract scenes from each button configuration
            for control_id, button_ref, button_config in button_list:
                button_label = BUTTON_LABELS_EXTENDED.get(control_id, f'Button {control_id}')

                # Check on_short_release actions
                if 'on_short_release' in button_config:
                    action = button_config['on_short_release']

                    # Scene cycle
                    if 'scene_cycle_extended' in action:
                        slots = action['scene_cycle_extended'].get('slots', [])
                        for slot in slots:
                            if slot and len(slot) > 0:
                                scene_rid = slot[0].get('action', {}).get('recall', {}).get('rid')
                                if scene_rid:
                                    if scene_rid not in scene_mapping:
                                        scene_mapping[scene_rid] = []
                                    scene_mapping[scene_rid].append({
                                        'device_name': device_name,
                                        'button': button_label,
                                        'action': 'Cycle (short press)'
                                    })

                    # Time-based scenes
                    elif 'time_based_extended' in action:
                        slots = action['time_based_extended'].get('slots', [])
                        for slot in slots:
                            actions = slot.get('actions', [])
                            if actions:
                                scene_rid = actions[0].get('action', {}).get('recall', {}).get('rid')
                                if scene_rid:
                                    start_time = slot.get('start_time', {})
                                    hour = start_time.get('hour', 0)
                                    minute = start_time.get('minute', 0)
                                    if scene_rid not in scene_mapping:
                                        scene_mapping[scene_rid] = []
                                    scene_mapping[scene_rid].append({
                                        'device_name': device_name,
                                        'button': button_label,
                                        'action': f'Time-based (short press, {hour:02d}:{minute:02d})'
                                    })

                    # Single recall
                    elif 'recall_single_extended' in action:
                        actions_list = action['recall_single_extended'].get('actions', [])
                        if actions_list:
                            scene_rid = actions_list[0].get('action', {}).get('recall', {}).get('rid')
                            if scene_rid:
                                if scene_rid not in scene_mapping:
                                    scene_mapping[scene_rid] = []
                                scene_mapping[scene_rid].append({
                                    'device_name': device_name,
                                    'button': button_label,
                                    'action': 'Single (short press)'
                                })

        return scene_mapping

    def activate_scene(self, scene_id: str) -> bool:
        """Activate a scene by its ID (v2 API - uses recall on scene)."""
        # In v2, we use PUT on the scene resource with recall action
        result = self._request('PUT', f'/resource/scene/{scene_id}', {'recall': {'action': 'active'}})
        return result is not None

    def set_light_state(self, light_id: str, state: dict) -> bool:
        """Set the state of a light (v2 API).

        Note: Light states change frequently, so we don't update the cache here.
        The cache is primarily for static configuration (scenes, devices, behaviours).
        Use 'reload' command if you need to sync light states.
        """
        # Convert v1-style state to v2 format
        v2_state = {}
        if 'on' in state:
            v2_state['on'] = {'on': state['on']}
        if 'bri' in state:
            v2_state['dimming'] = {'brightness': (state['bri'] / 254) * 100}
        if 'hue' in state or 'sat' in state:
            # Color in XY space for v2
            if 'hue' in state and 'sat' in state:
                # Simplified conversion - may need proper HSV to XY conversion
                v2_state['color'] = {'xy': {'x': 0.5, 'y': 0.5}}  # Placeholder
        if 'ct' in state:
            # Convert mireds to v2 format
            v2_state['color_temperature'] = {'mirek': state['ct']}

        result = self._request('PUT', f'/resource/light/{light_id}', v2_state)
        # Note: We don't update cache for light state as it changes frequently
        return result is not None

    def map_button_to_scene(self, sensor_id: str, button_event: int, scene_id: str):
        """Create a mapping from a button event to a scene."""
        mapping_key = f"{sensor_id}:{button_event}"
        self.button_mappings[mapping_key] = scene_id
        save_config(self.config)

    # ===== Write-Through Cache Examples for Future Development =====
    # These methods demonstrate the write-through cache pattern for modifying
    # bridge configuration (behaviour instances, scenes, etc.)

    def update_behaviour_instance(self, instance_id: str, config: dict) -> bool:
        """Update a behaviour instance configuration (write-through cache example).

        This demonstrates the write-through pattern: modify via API, then update cache.

        Args:
            instance_id: The behaviour instance ID
            config: The new configuration dict

        Returns:
            True if successful, False otherwise
        """
        # Make the API call
        result = self._request('PUT', f'/resource/behavior_instance/{instance_id}', config)

        if result and self.use_cache:
            # Get the full updated resource (API returns just the fields that changed)
            # In practice, we'd need to merge this with existing data
            updated_behaviour = self._request('GET', f'/resource/behavior_instance/{instance_id}')
            if updated_behaviour and len(updated_behaviour) > 0:
                self._update_cache_entry('behaviours', instance_id, updated_behaviour[0])

        return result is not None

    def create_behaviour_instance(self, config: dict) -> str | None:
        """Create a new behaviour instance (write-through cache example).

        Args:
            config: The behaviour configuration dict

        Returns:
            The new behaviour instance ID if successful, None otherwise
        """
        # Make the API call
        result = self._request('POST', '/resource/behavior_instance', config)

        if result and self.use_cache and len(result) > 0:
            # API returns the new resource with ID
            new_behaviour = result[0]
            self._add_cache_entry('behaviours', new_behaviour)
            return new_behaviour.get('id')

        return None

    def delete_behaviour_instance(self, instance_id: str) -> bool:
        """Delete a behaviour instance (write-through cache example).

        Args:
            instance_id: The behaviour instance ID to delete

        Returns:
            True if successful, False otherwise
        """
        # Make the API call
        result = self._request('DELETE', f'/resource/behavior_instance/{instance_id}')

        if result and self.use_cache:
            self._remove_cache_entry('behaviours', instance_id)

        return result is not None

    def update_scene_auto_dynamic(self, scene_id: str, auto_dynamic: bool) -> bool:
        """Update the auto_dynamic setting for a scene (write-through cache).

        Args:
            scene_id: The scene ID
            auto_dynamic: True to enable auto-dynamic, False to disable

        Returns:
            True if successful, False otherwise
        """
        # Make the API call to update the scene
        result = self._request('PUT', f'/resource/scene/{scene_id}', {'auto_dynamic': auto_dynamic})

        if result and self.use_cache:
            # Get the updated scene from the bridge
            updated_scene = self._request('GET', f'/resource/scene/{scene_id}')
            if updated_scene and len(updated_scene) > 0:
                self._update_cache_entry('scenes', scene_id, updated_scene[0])

        return result is not None

    def create_scene(self, name: str, group_rid: str, actions: list[dict],
                     auto_dynamic: bool = True, speed: float = 0.6, group_rtype: str = "zone") -> str | None:
        """Create a new scene (write-through cache).

        Args:
            name: Scene name
            group_rid: Zone or room resource ID
            actions: List of light actions [{"target": {"rid": "..."}, "action": {...}}]
            auto_dynamic: Enable auto-dynamic palette cycling (default: True)
            speed: Dynamic effect speed 0.0 - 1.0 (default: 0.6)
            group_rtype: Group type - 'zone' or 'room' (default: 'zone')

        Returns:
            New scene ID if successful, None if failed
        """
        # Build scene data structure
        scene_data = {
            "metadata": {"name": name},
            "group": {"rid": group_rid, "rtype": group_rtype},
            "actions": actions,
            "auto_dynamic": auto_dynamic,
            "speed": speed,
        }

        # Make the API call to create the scene
        result = self._request('POST', '/resource/scene', scene_data)

        if result and len(result) > 0:
            new_scene_id = result[0].get('rid')

            # Add to cache if enabled
            if new_scene_id and self.use_cache:
                # Fetch the complete scene data
                scene_details = self._request('GET', f'/resource/scene/{new_scene_id}')
                if scene_details and len(scene_details) > 0:
                    self._add_cache_entry('scenes', scene_details[0])

            return new_scene_id

        return None

    def delete_scene(self, scene_id: str) -> bool:
        """Delete a scene (write-through cache).

        Args:
            scene_id: Scene ID to delete

        Returns:
            True if successful, False otherwise
        """
        result = self._request('DELETE', f'/resource/scene/{scene_id}')

        if result is not None and self.use_cache:
            self._remove_cache_entry('scenes', scene_id)

        return result is not None

    def get_button_events(self) -> dict[str, dict]:
        """Get current button event states from all sensors."""
        sensors = self.get_sensors()
        events = {}

        for sensor_id, sensor_data in sensors.items():
            sensor_type = sensor_data.get('type', '')
            if 'Switch' in sensor_type or 'Button' in sensor_type:
                state = sensor_data.get('state', {})
                if 'buttonevent' in state and 'lastupdated' in state:
                    events[sensor_id] = {
                        'name': sensor_data.get('name'),
                        'buttonevent': state['buttonevent'],
                        'lastupdated': state['lastupdated']
                    }

        return events

    def monitor_buttons(self, callback):
        """Monitor button events and trigger callback on new events."""
        click.echo("Monitoring switches... (Press Ctrl+C to stop)\n")

        # Initialise last known states
        self.last_button_states = self.get_button_events()

        try:
            while True:
                time.sleep(0.5)  # Poll every 500ms
                current_events = self.get_button_events()

                for sensor_id, event_data in current_events.items():
                    last_data = self.last_button_states.get(sensor_id)

                    # Check if this is a new button event
                    if not last_data or event_data['lastupdated'] != last_data['lastupdated']:
                        callback(sensor_id, event_data)
                        self.last_button_states[sensor_id] = event_data

        except KeyboardInterrupt:
            click.echo("\n\nMonitoring stopped.")


