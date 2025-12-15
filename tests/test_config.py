"""Tests for configuration functions in core/config.py

NOTE: These are READ-ONLY tests only, following the refactoring testing policy.
No actual file writes or 1Password calls are made during testing.
"""

import pytest
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.config import (
    CONFIG_FILE,
    USER_CONFIG_FILE,
    is_op_available,
    load_from_1password,
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


class TestIsOpAvailable:
    """Test 1Password CLI availability check."""

    @patch('subprocess.run')
    def test_op_available_success(self, mock_run):
        """When op CLI exists and works, should return True."""
        mock_run.return_value = MagicMock(returncode=0)
        result = is_op_available()
        assert result is True
        mock_run.assert_called_once()
        # Verify it calls 'op --version'
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == 'op'
        assert '--version' in call_args

    @patch('subprocess.run')
    def test_op_not_found(self, mock_run):
        """When op CLI doesn't exist, should return False."""
        mock_run.side_effect = FileNotFoundError()
        result = is_op_available()
        assert result is False

    @patch('subprocess.run')
    def test_op_timeout(self, mock_run):
        """When op CLI times out, should return False."""
        from subprocess import TimeoutExpired
        mock_run.side_effect = TimeoutExpired('op', 2)
        result = is_op_available()
        assert result is False

    @patch('subprocess.run')
    def test_op_error_returncode(self, mock_run):
        """When op CLI returns error code, should return False."""
        mock_run.return_value = MagicMock(returncode=1)
        result = is_op_available()
        assert result is False


class TestLoadFromOnePassword:
    """Test 1Password token loading (mocked, no actual calls)."""

    @patch('core.config.is_op_available')
    def test_op_not_available(self, mock_is_available):
        """When 1Password CLI not available, should return None."""
        mock_is_available.return_value = False
        result = load_from_1password()
        assert result is None

    @patch('core.config.is_op_available')
    @patch('subprocess.run')
    def test_successful_token_load(self, mock_run, mock_is_available):
        """When token loads successfully, should return token string."""
        mock_is_available.return_value = True
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='test-api-token-12345\n'
        )
        result = load_from_1password()
        assert result == 'test-api-token-12345'

    @patch('core.config.is_op_available')
    @patch('subprocess.run')
    def test_op_command_failure(self, mock_run, mock_is_available):
        """When op command fails, should return None."""
        mock_is_available.return_value = True
        mock_run.return_value = MagicMock(returncode=1)
        result = load_from_1password()
        assert result is None

    @patch('core.config.is_op_available')
    @patch('subprocess.run')
    def test_op_timeout_during_load(self, mock_run, mock_is_available):
        """When op times out during load, should return None."""
        from subprocess import TimeoutExpired
        mock_is_available.return_value = True
        mock_run.side_effect = TimeoutExpired('op', 10)
        result = load_from_1password()
        assert result is None

    @patch('core.config.is_op_available')
    @patch('subprocess.run')
    def test_correct_op_command_format(self, mock_run, mock_is_available):
        """Verify correct 1Password CLI command is constructed with defaults."""
        mock_is_available.return_value = True
        mock_run.return_value = MagicMock(returncode=0, stdout='token')

        load_from_1password()

        # Check the command arguments use defaults from environment
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == 'op'
        assert 'item' in call_args
        assert 'get' in call_args
        # Should use default vault/item names (can be overridden by env vars)
        assert 'Hue' in call_args  # Default item name
        assert 'Private' in call_args  # Default vault name

    @patch.dict(os.environ, {'HUE_1PASSWORD_VAULT': 'Work', 'HUE_1PASSWORD_ITEM': 'MyBridge'})
    @patch('core.config.is_op_available')
    @patch('subprocess.run')
    def test_uses_environment_variables(self, mock_run, mock_is_available):
        """Verify that environment variables override defaults."""
        mock_is_available.return_value = True
        mock_run.return_value = MagicMock(returncode=0, stdout='token')

        load_from_1password()

        # Check the command arguments use environment variables (not defaults)
        call_args = mock_run.call_args[0][0]
        assert 'MyBridge' in call_args  # From HUE_1PASSWORD_ITEM
        assert 'Work' in call_args  # From HUE_1PASSWORD_VAULT
        assert 'Hue' not in call_args  # Should not use default
        assert 'Private' not in call_args  # Should not use default
        assert '--vault' in call_args
        assert '--fields' in call_args
        assert 'API-token' in call_args


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
