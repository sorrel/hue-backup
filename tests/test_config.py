"""Tests for configuration functions in core/config.py

NOTE: These are READ-ONLY tests only, following the refactoring testing policy.
No actual file writes are made during testing.
"""

import pytest
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.config import (
    CONFIG_FILE,
    USER_CONFIG_FILE,
    load_config,
    save_config
)


class TestConstants:
    """Test that constants are properly defined."""

    def test_config_file_path(self):
        """CONFIG_FILE should point to cache/hue_data.json."""
        assert isinstance(CONFIG_FILE, Path)
        assert CONFIG_FILE.name == 'hue_data.json'
        assert 'cache' in str(CONFIG_FILE)

    def test_user_config_file_path(self):
        """USER_CONFIG_FILE should point to ~/.hue_backup/config.json."""
        assert isinstance(USER_CONFIG_FILE, Path)
        assert USER_CONFIG_FILE.name == 'config.json'
        assert '.hue_backup' in str(USER_CONFIG_FILE)


class TestLoadConfig:
    """Test configuration file loading (mocked, no actual file reads)."""

    @patch('pathlib.Path.exists')
    def test_config_file_not_exists(self, mock_exists):
        """When config file doesn't exist, should return default dict."""
        mock_exists.return_value = False
        result = load_config()
        assert isinstance(result, dict)
        assert 'button_mappings' in result
        assert result['button_mappings'] == {}

    @patch('pathlib.Path.exists')
    @patch('builtins.open', create=True)
    def test_config_file_exists_valid_json(self, mock_open, mock_exists):
        """When config file exists with valid JSON, should parse it."""
        mock_exists.return_value = True
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = '{"button_mappings": {"1002": "scene-id"}}'
        mock_open.return_value = mock_file

        import json
        with patch('json.load') as mock_json_load:
            mock_json_load.return_value = {"button_mappings": {"1002": "scene-id"}}
            result = load_config()

        assert 'button_mappings' in result
        assert '1002' in result['button_mappings']


class TestSaveConfig:
    """Test configuration file saving (mocked, no actual writes)."""

    @patch('pathlib.Path.mkdir')
    @patch('builtins.open', create=True)
    @patch('json.dump')
    def test_save_creates_directory(self, mock_json_dump, mock_open, mock_mkdir):
        """Verify that save_config creates cache directory if needed."""
        test_config = {'button_mappings': {}}

        save_config(test_config)

        # Verify directory creation was attempted
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    @patch('pathlib.Path.mkdir')
    @patch('builtins.open', create=True)
    @patch('json.dump')
    def test_save_writes_json(self, mock_json_dump, mock_open, mock_mkdir):
        """Verify that save_config writes JSON with correct formatting."""
        test_config = {'button_mappings': {'1002': 'test-scene'}}

        save_config(test_config)

        # Verify json.dump was called with indent=2
        mock_json_dump.assert_called_once()
        call_args = mock_json_dump.call_args
        assert call_args[1]['indent'] == 2
        assert call_args[0][0] == test_config
