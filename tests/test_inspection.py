"""
Tests for inspection commands to ensure they use cache and handle v2 API format.

These tests verify that inspection commands properly use cache instead of making
direct API calls, and correctly handle v2 API list format (not dict).
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from click.testing import CliRunner
from commands.inspection import lights_command, groups_command, status_command, switch_info_command


class TestListCommand:
    """Test list lights command uses cache and handles v2 API format."""

    @patch('commands.inspection.devices.get_cache_controller')
    def test_list_uses_cache(self, mock_get_cache):
        """Test that list command uses cache controller.

        This test was added after fixing a bug where list command was
        calling HueController().connect() instead of using cache.
        """
        mock_controller = Mock()
        mock_controller.get_lights.return_value = []
        mock_get_cache.return_value = mock_controller

        runner = CliRunner()
        result = runner.invoke(lights_command, ['--no-auto-reload'])

        mock_get_cache.assert_called_once_with(False)
        mock_controller.get_lights.assert_called_once()
        assert result.exit_code == 0

    @patch('commands.inspection.devices.get_cache_controller')
    def test_list_handles_v2_list_format(self, mock_get_cache):
        """Test that list command handles v2 API list format (not dict).

        This test was added after fixing a bug where list command tried
        to call .items() on a list, causing AttributeError.
        """
        mock_controller = Mock()
        # v2 API returns a list, not a dict
        mock_controller.get_devices.return_value = [
            {
                'id': 'device1',
                'metadata': {'name': 'Test Light'},
                'product_data': {
                    'product_name': 'Hue white and colour ambiance bulb',
                    'model_id': 'LCA001'
                }
            },
            {
                'id': 'device2',
                'metadata': {'name': 'Test Light 2'},
                'product_data': {
                    'product_name': 'Hue white bulb',
                    'model_id': 'LWB010'
                }
            }
        ]
        mock_controller.get_lights.return_value = [
            {
                'id': 'light1',
                'owner': {'rid': 'device1'},
                'on': {'on': True}
            },
            {
                'id': 'light2',
                'owner': {'rid': 'device2'},
                'on': {'on': False}
            }
        ]
        mock_controller.get_rooms.return_value = []
        mock_get_cache.return_value = mock_controller

        runner = CliRunner()
        result = runner.invoke(lights_command, ['--no-auto-reload'])

        assert result.exit_code == 0
        assert 'Test Light' in result.output
        assert 'Test Light 2' in result.output
        assert 'ON' in result.output
        assert 'OFF' in result.output


class TestGroupsCommand:
    """Test groups command uses cache and handles v2 API format."""

    @patch('commands.inspection.status.get_cache_controller')
    def test_groups_uses_cache(self, mock_get_cache):
        """Test that groups command uses cache controller.

        This test was added after fixing a bug where groups command was
        making direct API calls instead of using cache.
        """
        mock_controller = Mock()
        mock_controller.get_rooms.return_value = []
        mock_get_cache.return_value = mock_controller

        runner = CliRunner()
        result = runner.invoke(groups_command, ['--no-auto-reload'])

        mock_get_cache.assert_called_once_with(False)
        mock_controller.get_rooms.assert_called_once()
        assert result.exit_code == 0

    @patch('commands.inspection.status.get_cache_controller')
    def test_groups_handles_v2_list_format(self, mock_get_cache):
        """Test that groups command handles v2 API list format."""
        mock_controller = Mock()
        # v2 API returns a list
        mock_controller.get_rooms.return_value = [
            {
                'id': 'room1',
                'metadata': {'name': 'Living Room', 'archetype': 'living_room'},
                'children': [
                    {'rtype': 'light', 'rid': 'light1'},
                    {'rtype': 'light', 'rid': 'light2'},
                    {'rtype': 'device', 'rid': 'device1'}  # Not a light
                ]
            }
        ]
        mock_get_cache.return_value = mock_controller

        runner = CliRunner()
        result = runner.invoke(groups_command, ['--no-auto-reload'])

        assert result.exit_code == 0
        assert 'Living Room' in result.output
        assert 'Lights: 2' in result.output  # Should count only lights


class TestStatusCommand:
    """Test status command uses cache."""

    @patch('commands.inspection.status.get_cache_controller')
    def test_status_uses_cache(self, mock_get_cache):
        """Test that status command uses cache controller.

        This test was added after fixing a bug where status command was
        making direct API calls instead of using cache.
        """
        mock_controller = Mock()
        mock_controller.get_lights.return_value = [{'id': 'light1'}]
        mock_controller.get_rooms.return_value = [{'id': 'room1'}]
        mock_controller.get_scenes.return_value = [{'id': 'scene1'}]
        mock_controller.get_devices.return_value = [
            {
                'id': 'device1',
                'product_data': {
                    'product_name': 'Hue white bulb'
                },
                'services': []
            }
        ]
        mock_controller.button_mappings = {}
        mock_get_cache.return_value = mock_controller

        runner = CliRunner()
        result = runner.invoke(status_command, ['--no-auto-reload'])

        mock_get_cache.assert_called_once_with(False)
        assert result.exit_code == 0
        assert '1 light devices' in result.output
        assert '1 light resources' in result.output
        assert '1 rooms' in result.output
        assert '1 scenes' in result.output


class TestSwitchInfoCommand:
    """Test switch-info command with fuzzy matching."""

    @patch('commands.inspection.switches.get_cache_controller')
    def test_exact_id_match(self, mock_get_cache):
        """Test switch-info with exact sensor ID match."""
        mock_controller = Mock()
        mock_controller.get_sensors.return_value = {
            '18': {
                'name': 'Office dimmer',
                'type': 'ZLLSwitch',
                'state': {'buttonevent': 1002},
                'config': {'battery': 90}
            }
        }
        mock_controller.button_mappings = {}
        mock_controller.get_scenes.return_value = []
        mock_get_cache.return_value = mock_controller

        runner = CliRunner()
        result = runner.invoke(switch_info_command, ['18', '--no-auto-reload'])

        assert result.exit_code == 0
        assert 'Office dimmer' in result.output
        assert 'ID: 18' in result.output

    @patch('commands.inspection.switches.get_cache_controller')
    def test_fuzzy_match_device_name(self, mock_get_cache):
        """Test switch-info with fuzzy match on device name.

        This test was added after implementing fuzzy matching to allow
        searching by device name or room name, not just sensor ID.
        """
        mock_controller = Mock()
        mock_controller.get_sensors.return_value = {
            '18': {
                'name': 'Office dimmer',
                'type': 'ZLLSwitch',
                'device_id': 'device1',
                'state': {'buttonevent': 1002},
                'config': {'battery': 90}
            },
            '79': {
                'name': 'Living dimmer',
                'type': 'ZLLSwitch',
                'device_id': 'device2',
                'state': {},
                'config': {}
            }
        }
        mock_controller.get_device_rooms.return_value = {
            'device1': ['Office upstairs'],
            'device2': ['Living room']
        }
        mock_controller.button_mappings = {}
        mock_controller.get_scenes.return_value = []
        mock_get_cache.return_value = mock_controller

        runner = CliRunner()
        result = runner.invoke(switch_info_command, ['office', '--no-auto-reload'])

        assert result.exit_code == 0
        assert 'Office dimmer' in result.output
        assert 'ID: 18' in result.output
        assert 'Living dimmer' not in result.output

    @patch('commands.inspection.switches.get_cache_controller')
    def test_fuzzy_match_room_name(self, mock_get_cache):
        """Test switch-info with fuzzy match on room name."""
        mock_controller = Mock()
        mock_controller.get_sensors.return_value = {
            '18': {
                'name': 'Office dimmer',
                'type': 'ZLLSwitch',
                'device_id': 'device1',
                'state': {},
                'config': {}
            }
        }
        mock_controller.get_device_rooms.return_value = {
            'device1': ['Office upstairs']
        }
        mock_controller.button_mappings = {}
        mock_controller.get_scenes.return_value = []
        mock_get_cache.return_value = mock_controller

        runner = CliRunner()
        result = runner.invoke(switch_info_command, ['upstairs', '--no-auto-reload'])

        assert result.exit_code == 0
        assert 'Office dimmer' in result.output

    @patch('commands.inspection.switches.get_cache_controller')
    def test_fuzzy_match_multiple_results(self, mock_get_cache):
        """Test switch-info shows all matches when multiple devices match."""
        mock_controller = Mock()
        mock_controller.get_sensors.return_value = {
            '63': {
                'name': 'B bedroom dimmer',
                'type': 'ZLLSwitch',
                'device_id': 'device1',
                'state': {},
                'config': {}
            },
            '79': {
                'name': 'D bedroom dimmer',
                'type': 'ZLLSwitch',
                'device_id': 'device2',
                'state': {},
                'config': {}
            }
        }
        mock_controller.get_device_rooms.return_value = {
            'device1': ['Bedroom B'],
            'device2': ['Bedroom D']
        }
        mock_controller.button_mappings = {}
        mock_controller.get_scenes.return_value = []
        mock_get_cache.return_value = mock_controller

        runner = CliRunner()
        result = runner.invoke(switch_info_command, ['bedroom', '--no-auto-reload'])

        assert result.exit_code == 0
        assert 'Found 2 switches' in result.output
        assert 'B bedroom dimmer' in result.output
        assert 'D bedroom dimmer' in result.output

    @patch('commands.inspection.switches.get_cache_controller')
    def test_no_match_shows_helpful_message(self, mock_get_cache):
        """Test switch-info shows helpful message when no matches found."""
        mock_controller = Mock()
        mock_controller.get_sensors.return_value = {
            '18': {
                'name': 'Office dimmer',
                'type': 'ZLLSwitch',
                'device_id': 'device1',
                'state': {},
                'config': {}
            }
        }
        mock_controller.get_device_rooms.return_value = {'device1': []}
        mock_get_cache.return_value = mock_controller

        runner = CliRunner()
        result = runner.invoke(switch_info_command, ['nonexistent', '--no-auto-reload'])

        assert result.exit_code == 0
        assert "No switches found matching 'nonexistent'" in result.output
        assert 'sensor ID' in result.output
        assert 'device name' in result.output


class TestBatteryDisplay:
    """Test battery level and state display in inspection commands."""

    @patch('commands.inspection.switches.get_cache_controller')
    def test_switch_info_battery_normal(self, mock_get_cache):
        """Test switch-info displays battery with normal state."""
        mock_controller = Mock()
        mock_controller.get_sensors.return_value = {
            '18': {
                'name': 'Office dimmer',
                'type': 'ZLLSwitch',
                'state': {'buttonevent': 1002},
                'config': {
                    'battery': 85,
                    'battery_state': 'normal'
                }
            }
        }
        mock_controller.button_mappings = {}
        mock_controller.get_scenes.return_value = []
        mock_get_cache.return_value = mock_controller

        runner = CliRunner()
        result = runner.invoke(switch_info_command, ['18', '--no-auto-reload'])

        assert result.exit_code == 0
        assert 'Battery: 85% (normal)' in result.output

    @patch('commands.inspection.switches.get_cache_controller')
    def test_switch_info_battery_low(self, mock_get_cache):
        """Test switch-info displays battery with low state."""
        mock_controller = Mock()
        mock_controller.get_sensors.return_value = {
            '18': {
                'name': 'Office dimmer',
                'type': 'ZLLSwitch',
                'state': {},
                'config': {
                    'battery': 25,
                    'battery_state': 'low'
                }
            }
        }
        mock_controller.button_mappings = {}
        mock_controller.get_scenes.return_value = []
        mock_get_cache.return_value = mock_controller

        runner = CliRunner()
        result = runner.invoke(switch_info_command, ['18', '--no-auto-reload'])

        assert result.exit_code == 0
        assert 'Battery: 25% (low)' in result.output

    @patch('commands.inspection.switches.get_cache_controller')
    def test_switch_info_battery_critical(self, mock_get_cache):
        """Test switch-info displays battery with critical state."""
        mock_controller = Mock()
        mock_controller.get_sensors.return_value = {
            '18': {
                'name': 'Office dimmer',
                'type': 'ZLLSwitch',
                'state': {},
                'config': {
                    'battery': 5,
                    'battery_state': 'critical'
                }
            }
        }
        mock_controller.button_mappings = {}
        mock_controller.get_scenes.return_value = []
        mock_get_cache.return_value = mock_controller

        runner = CliRunner()
        result = runner.invoke(switch_info_command, ['18', '--no-auto-reload'])

        assert result.exit_code == 0
        assert 'Battery: 5% (critical)' in result.output

    @patch('commands.inspection.switches.get_cache_controller')
    def test_switch_info_no_battery(self, mock_get_cache):
        """Test switch-info with device that has no battery."""
        mock_controller = Mock()
        mock_controller.get_sensors.return_value = {
            '18': {
                'name': 'Wall switch',
                'type': 'ZLLSwitch',
                'state': {},
                'config': {}  # No battery data
            }
        }
        mock_controller.button_mappings = {}
        mock_controller.get_scenes.return_value = []
        mock_get_cache.return_value = mock_controller

        runner = CliRunner()
        result = runner.invoke(switch_info_command, ['18', '--no-auto-reload'])

        assert result.exit_code == 0
        # Should not show battery section at all
        assert 'Battery:' not in result.output
