"""Test that the refactored structure is correct."""

def test_directories_exist(project_root):
    """Test that all expected directories exist."""
    assert (project_root / "core").exists()
    assert (project_root / "models").exists()
    assert (project_root / "commands").exists()
    assert (project_root / "tests").exists()


def test_init_files_exist(project_root):
    """Test that all __init__.py files exist."""
    assert (project_root / "core" / "__init__.py").exists()
    assert (project_root / "models" / "__init__.py").exists()
    assert (project_root / "commands" / "__init__.py").exists()
    assert (project_root / "tests" / "__init__.py").exists()


def test_main_script_exists(project_root):
    """Test that main entry point exists."""
    assert (project_root / "hue_backup.py").exists()


def test_cache_paths_point_inside_the_project(cache_dir, saved_rooms_dir):
    """The cache and saved-rooms paths are the project-local ones.

    Both directories are gitignored runtime state, created on demand, so a
    fresh clone (or CI) will not have them. Assert where they are configured
    to be, not that this machine happens to have them already.
    """
    from core.config import CONFIG_FILE
    from models.room import SAVED_ROOMS_DIR

    assert CONFIG_FILE.parent == cache_dir
    assert SAVED_ROOMS_DIR == saved_rooms_dir


def test_saving_config_creates_the_cache_directory(tmp_path, monkeypatch):
    """save_config() makes its own directory rather than assuming one."""
    from core import config

    monkeypatch.setattr(
        config, "CONFIG_FILE", tmp_path / "cache.nosync" / "hue_data.json"
    )
    config.save_config({"button_mappings": {}})

    assert (tmp_path / "cache.nosync").is_dir()
    assert (tmp_path / "cache.nosync" / "hue_data.json").exists()
