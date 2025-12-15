"""Test that the refactored structure is correct."""

from pathlib import Path


def test_directories_exist(project_root):
    """Test that all expected directories exist."""
    assert (project_root / "core").exists()
    assert (project_root / "models").exists()
    assert (project_root / "commands").exists()
    assert (project_root / "tests").exists()
    assert (project_root / "cache").exists()


def test_init_files_exist(project_root):
    """Test that all __init__.py files exist."""
    assert (project_root / "core" / "__init__.py").exists()
    assert (project_root / "models" / "__init__.py").exists()
    assert (project_root / "commands" / "__init__.py").exists()
    assert (project_root / "tests" / "__init__.py").exists()


def test_main_script_exists(project_root):
    """Test that main entry point exists."""
    assert (project_root / "hue_backup.py").exists()


def test_cache_structure(cache_dir, saved_rooms_dir):
    """Test that cache directories exist."""
    assert cache_dir.exists()
    assert saved_rooms_dir.exists()
