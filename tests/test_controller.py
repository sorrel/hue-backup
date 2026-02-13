"""
Tests for HueController delegation methods and utility imports.

These tests verify that HueController methods properly delegate to
the corresponding functions in core modules, and that required
utilities are properly imported.
"""

import pytest
from unittest.mock import patch, MagicMock
from core.controller import HueController, BUTTON_LABELS_EXTENDED


class TestImports:
    """Test that required utilities are properly imported."""

    def test_create_name_lookup_imported(self):
        """Test that create_name_lookup is imported from models.utils.

        This test was added after fixing a bug where scene-details failed
        because create_name_lookup was used but not imported.
        """
        from core.controller import create_name_lookup
        assert callable(create_name_lookup)

    def test_button_labels_defined(self):
        """Test that BUTTON_LABELS_EXTENDED is defined.

        This test was added after fixing a bug where get_scene_to_switch_mapping
        referenced BUTTON_LABELS_EXTENDED which was not defined.
        """
        assert isinstance(BUTTON_LABELS_EXTENDED, dict)
        assert 1 in BUTTON_LABELS_EXTENDED
        assert BUTTON_LABELS_EXTENDED[1] == 'ON'
        assert 34 in BUTTON_LABELS_EXTENDED  # Dial rotate
        assert 35 in BUTTON_LABELS_EXTENDED  # Dial press


class TestCacheDelegation:
    """Test that HueController cache methods delegate correctly."""

    @patch('core.controller.reload_cache')
    def test_reload_cache_delegates(self, mock_reload):
        """Test reload_cache() delegates to core.cache.reload_cache()."""
        mock_reload.return_value = True
        controller = HueController()

        result = controller.reload_cache()

        assert result is True
        mock_reload.assert_called_once_with(controller)

    @patch('core.controller.is_cache_stale')
    def test_is_cache_stale_delegates(self, mock_stale):
        """Test is_cache_stale() delegates to core.cache.is_cache_stale()."""
        mock_stale.return_value = True
        controller = HueController()

        result = controller.is_cache_stale(max_age_hours=12)

        assert result is True
        mock_stale.assert_called_once_with(controller, 12)

    @patch('core.controller.ensure_fresh_cache')
    def test_ensure_fresh_cache_delegates(self, mock_ensure):
        """Test ensure_fresh_cache() delegates to core.cache.ensure_fresh_cache().

        This test was added after fixing a bug where ensure_fresh_cache()
        had incorrect code that tried to reference undefined variables.
        """
        mock_ensure.return_value = True
        controller = HueController()

        result = controller.ensure_fresh_cache(max_age_hours=24)

        assert result is True
        mock_ensure.assert_called_once_with(controller, 24)


class TestBatteryData:
    """Test battery level and state handling in get_sensors()."""

    def test_get_sensors_includes_battery_state_from_cache(self):
        """Test that get_sensors() includes battery_state when available in cache."""
        controller = HueController(use_cache=True)
        controller.config = {
            'cache': {
                'devices': [
                    {
                        'id': 'device1',
                        'id_v1': '/sensors/18',
                        'metadata': {'name': 'Office dimmer'},
                        'services': [
                            {'rtype': 'button', 'rid': 'button1'},
                            {'rtype': 'device_power', 'rid': 'power1'}
                        ]
                    }
                ],
                'buttons': [
                    {
                        'id': 'button1',
                        'metadata': {'control_id': 1},
                        'button': {
                            'last_event': 'short_release',
                            'button_report': {'updated': '2024-12-17T08:00:00Z'}
                        }
                    }
                ],
                'device_power': [
                    {
                        'id': 'power1',
                        'power_state': {
                            'battery_level': 85,
                            'battery_state': 'normal'
                        }
                    }
                ]
            }
        }

        sensors = controller.get_sensors()

        assert '18' in sensors
        assert sensors['18']['config']['battery'] == 85
        assert sensors['18']['config']['battery_state'] == 'normal'

    def test_get_sensors_battery_state_low(self):
        """Test get_sensors() with low battery state."""
        controller = HueController(use_cache=True)
        controller.config = {
            'cache': {
                'devices': [
                    {
                        'id': 'device1',
                        'id_v1': '/sensors/18',
                        'metadata': {'name': 'Office dimmer'},
                        'services': [
                            {'rtype': 'button', 'rid': 'button1'},
                            {'rtype': 'device_power', 'rid': 'power1'}
                        ]
                    }
                ],
                'buttons': [
                    {
                        'id': 'button1',
                        'metadata': {'control_id': 1},
                        'button': {
                            'last_event': 'short_release',
                            'button_report': {'updated': '2024-12-17T08:00:00Z'}
                        }
                    }
                ],
                'device_power': [
                    {
                        'id': 'power1',
                        'power_state': {
                            'battery_level': 25,
                            'battery_state': 'low'
                        }
                    }
                ]
            }
        }

        sensors = controller.get_sensors()

        assert sensors['18']['config']['battery'] == 25
        assert sensors['18']['config']['battery_state'] == 'low'

    def test_get_sensors_battery_state_critical(self):
        """Test get_sensors() with critical battery state."""
        controller = HueController(use_cache=True)
        controller.config = {
            'cache': {
                'devices': [
                    {
                        'id': 'device1',
                        'id_v1': '/sensors/18',
                        'metadata': {'name': 'Office dimmer'},
                        'services': [
                            {'rtype': 'button', 'rid': 'button1'},
                            {'rtype': 'device_power', 'rid': 'power1'}
                        ]
                    }
                ],
                'buttons': [
                    {
                        'id': 'button1',
                        'metadata': {'control_id': 1},
                        'button': {
                            'last_event': 'short_release',
                            'button_report': {'updated': '2024-12-17T08:00:00Z'}
                        }
                    }
                ],
                'device_power': [
                    {
                        'id': 'power1',
                        'power_state': {
                            'battery_level': 5,
                            'battery_state': 'critical'
                        }
                    }
                ]
            }
        }

        sensors = controller.get_sensors()

        assert sensors['18']['config']['battery'] == 5
        assert sensors['18']['config']['battery_state'] == 'critical'

    @patch('core.controller.HueController._request')
    def test_get_sensors_battery_fallback_to_api(self, mock_request):
        """Test get_sensors() falls back to API when battery not in cache."""
        controller = HueController(use_cache=False)
        controller.api_token = 'test-token'
        controller.base_url = 'https://bridge/clip/v2'

        # Mock API response for device_power
        mock_request.return_value = [
            {
                'power_state': {
                    'battery_level': 90,
                    'battery_state': 'normal'
                }
            }
        ]

        controller._devices_cache = [
            {
                'id': 'device1',
                'id_v1': '/sensors/18',
                'metadata': {'name': 'Office dimmer'},
                'services': [
                    {'rtype': 'button', 'rid': 'button1'},
                    {'rtype': 'device_power', 'rid': 'power1'}
                ]
            }
        ]

        controller._buttons_cache = [
            {
                'id': 'button1',
                'metadata': {'control_id': 1},
                'button': {
                    'last_event': 'short_release',
                    'button_report': {'updated': '2024-12-17T08:00:00Z'}
                }
            }
        ]

        sensors = controller.get_sensors()

        # Verify API was called for battery data
        mock_request.assert_called_with('GET', '/resource/device_power/power1')
        assert sensors['18']['config']['battery'] == 90
        assert sensors['18']['config']['battery_state'] == 'normal'

    def test_get_sensors_no_battery_data(self):
        """Test get_sensors() when device has no battery (mains powered)."""
        controller = HueController(use_cache=True)
        controller.config = {
            'cache': {
                'devices': [
                    {
                        'id': 'device1',
                        'id_v1': '/sensors/18',
                        'metadata': {'name': 'Wall switch'},
                        'services': [
                            {'rtype': 'button', 'rid': 'button1'}
                            # No device_power service
                        ]
                    }
                ],
                'buttons': [
                    {
                        'id': 'button1',
                        'metadata': {'control_id': 1},
                        'button': {
                            'last_event': 'short_release',
                            'button_report': {'updated': '2024-12-17T08:00:00Z'}
                        }
                    }
                ],
                'device_power': []
            }
        }

        sensors = controller.get_sensors()

        assert '18' in sensors
        # Config should be empty dict when no battery
        assert sensors['18']['config'] == {}
