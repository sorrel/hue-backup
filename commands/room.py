"""Room configuration CLI commands.

This module provides CLI commands for saving and comparing room configurations.
"""

import json
from pathlib import Path
import click

from models.room import (
    save_room_configuration,
    diff_room_configuration,
    restore_room_configuration,
    SAVED_ROOMS_DIR
)
from models.utils import get_cache_controller
from core.controller import HueController
from core.cache import reload_cache


def register_room_commands(cli):
    """Register room commands with the CLI group.

    Args:
        cli: Click group to register commands to
    """
    cli.add_command(save_room_command)
    cli.add_command(diff_room_command)
    cli.add_command(restore_room_command)


@click.command(name='save-room')
@click.argument('room_name')
@click.option('--auto-reload/--no-auto-reload', default=True, help='Auto-reload stale cache (default: yes)')
def save_room_command(room_name: str, auto_reload: bool):
    """Save complete configuration for a room.

    Saves lights, scenes, and switch programmes for the specified room
    to a timestamped JSON file in the saved-rooms directory.

    \b
    What gets saved:
      - Room metadata (name, archetype, devices)
      - All lights with their configurations
      - All scenes for the room (with auto_dynamic settings)
      - All behaviour instances (switch button programmes)

    \b
    Examples:
      uv run python hue_control.py save-room "Living"
      uv run python hue_control.py save-room "Bedroom D"

    Files are saved to: cache/saved-rooms/YYYY-MM-DD_HH-MM_RoomName.json
    """
    cache_controller = get_cache_controller(auto_reload)
    if not cache_controller:
        return

    click.echo()
    click.secho(f"=== Saving Room Configuration: {room_name} ===", fg='cyan', bold=True)
    click.echo()

    try:
        filepath = save_room_configuration(cache_controller, room_name)

        if filepath:
            # Get summary from the saved file
            with open(filepath, 'r') as f:
                saved_data = json.load(f)
                summary = saved_data.get('summary', {})

            click.secho("✓ Room configuration saved successfully", fg='green')
            click.echo()
            click.echo(f"Room:        {summary.get('room_name', 'Unknown')}")
            click.echo(f"Devices:     {summary.get('device_count', 0)}")
            click.echo(f"Lights:      {summary.get('light_count', 0)}")
            click.echo(f"Scenes:      {summary.get('scene_count', 0)}")
            click.echo(f"Programmes:  {summary.get('behaviour_count', 0)} switch button programmes")
            click.echo()
            click.echo(f"Saved to:    {filepath}")
            click.echo()
        else:
            click.secho("✗ Failed to save room configuration", fg='red')
            click.echo()

    except Exception as e:
        click.secho(f"✗ Error saving room: {e}", fg='red')
        click.echo()


@click.command(name='diff-room')
@click.argument('saved_file')
@click.option('--verbose', '-v', is_flag=True, help='Show ephemeral state changes (light levels, on/off)')
@click.option('--reload', '-r', is_flag=True, help='Force cache reload before comparing (ensures live comparison)')
@click.option('--auto-reload/--no-auto-reload', default=True, help='Auto-reload stale cache (default: yes)')
def diff_room_command(saved_file: str, verbose: bool, reload: bool, auto_reload: bool):
    """Compare saved room configuration with current state.

    Shows section-by-section differences between a saved room backup
    and the current configuration in the cache.

    Use --reload to force a fresh cache reload before comparing, ensuring
    you're comparing against the live bridge state (recommended before restoring).

    \b
    Compares:
      - Room metadata (name, archetype, device count)
      - Lights (added/removed, on/off, brightness, colour temp)
      - Scenes (added/removed, auto_dynamic, light count, speed)
      - Behaviour instances (added/removed, enabled state, status)

    \b
    Examples:
      # Compare with specific file
      uv run python hue_control.py diff-room cache/saved-rooms/2025-12-10_13-46_Living_room.json

      # Use room name - finds most recent backup for that room
      uv run python hue_control.py diff-room "Living"
      uv run python hue_control.py diff-room "Office upstairs"

      # Force reload to compare against live bridge state
      uv run python hue_control.py diff-room "Living" --reload

      # Most recent file of any room
      uv run python hue_control.py diff-room $(ls -t cache/saved-rooms/*.json | head -1)
    """
    # Force reload if requested
    if reload:
        click.echo("Reloading cache from bridge...")
        # Create a live controller to reload cache
        temp_controller = HueController()
        if not temp_controller.connect():
            click.secho("✗ Failed to connect to bridge", fg='red')
            return
        if not reload_cache(temp_controller):
            click.secho("✗ Failed to reload cache", fg='red')
            return
        click.echo()

    cache_controller = get_cache_controller(auto_reload)
    if not cache_controller:
        return

    # Check if saved_file is a path or a room name
    saved_path = Path(saved_file)

    # If it's not an existing file, try to find saved files by room name
    if not saved_path.exists():
        # Ensure saved-rooms directory exists
        if not SAVED_ROOMS_DIR.exists():
            click.secho(f"✗ No saved rooms found in {SAVED_ROOMS_DIR}", fg='red')
            return

        # Find all saved files matching the room name
        matching_files = []
        room_name_lower = saved_file.lower()

        for saved_file_path in SAVED_ROOMS_DIR.glob('*.json'):
            # Extract room name from filename: YYYY-MM-DD_HH-MM_RoomName.json
            filename = saved_file_path.stem  # Remove .json
            # Split by timestamp pattern, room name is after second underscore
            parts = filename.split('_')
            if len(parts) >= 3:
                # Room name starts from index 2 (after date and time)
                room_part = '_'.join(parts[2:])
                if room_name_lower in room_part.lower():
                    matching_files.append(saved_file_path)

        if not matching_files:
            click.secho(f"✗ No saved room files found matching '{saved_file}'", fg='red')
            click.echo(f"\nAvailable saved rooms in {SAVED_ROOMS_DIR}:")
            all_files = sorted(SAVED_ROOMS_DIR.glob('*.json'), key=lambda x: x.stat().st_mtime, reverse=True)
            if all_files:
                for f in all_files[:10]:  # Show up to 10 most recent
                    timestamp = f.stem.split('_')[:2]
                    room_name = '_'.join(f.stem.split('_')[2:])
                    click.echo(f"  {' '.join(timestamp)} - {room_name}")
                if len(all_files) > 10:
                    click.echo(f"  ... and {len(all_files) - 10} more")
            else:
                click.echo("  (none)")
            return

        # Sort by modification time (most recent first)
        matching_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        saved_path = matching_files[0]

        # Show which file we're using
        if len(matching_files) > 1:
            click.echo(f"Found {len(matching_files)} saved files matching '{saved_file}'")
            click.echo(f"Using most recent: {click.style(saved_path.name, fg='cyan')}")
            click.echo()
        else:
            click.echo(f"Using: {click.style(saved_path.name, fg='cyan')}")
            click.echo()

    click.echo()
    if verbose:
        click.secho(f"=== Room Configuration Diff (Verbose) ===", fg='cyan', bold=True)
    else:
        click.secho(f"=== Room Configuration Diff ===", fg='cyan', bold=True)
    click.echo()

    try:
        diff = diff_room_configuration(cache_controller, str(saved_path), verbose=verbose)

        if not diff:
            click.secho("✗ Failed to generate diff", fg='red')
            return

        if 'error' in diff:
            click.secho(f"✗ Error: {diff['error']}", fg='red')
            if diff.get('room_deleted'):
                click.echo("The room may have been deleted from the bridge.")
            return

        # Display diff results
        click.echo(f"Room:        {diff['room_name']}")
        click.echo(f"Saved at:    {diff['saved_at']}")
        click.echo(f"Compared at: {diff['compared_at']}")
        click.echo()

        # Room metadata section
        room_diff = diff['room']
        if room_diff['changed']:
            click.secho("ROOM METADATA:", fg='yellow', bold=True)
            for change in room_diff['changes']:
                click.echo(f"  • {change}")
            click.echo()
        else:
            click.secho("ROOM METADATA: No changes", fg='green')
            click.echo()

        # Lights section
        lights_diff = diff['lights']
        click.secho(f"LIGHTS: {lights_diff['summary']}", fg='yellow' if (lights_diff['added'] or lights_diff['removed'] or lights_diff['changed']) else 'green', bold=True)

        if lights_diff['added']:
            click.echo(f"  Added ({len(lights_diff['added'])}):")
            for name in lights_diff['added']:
                click.echo(f"    + {click.style(name, fg='green')}")

        if lights_diff['removed']:
            click.echo(f"  Removed ({len(lights_diff['removed'])}):")
            for name in lights_diff['removed']:
                click.echo(f"    - {click.style(name, fg='red')}")

        if lights_diff['changed']:
            click.echo(f"  Changed ({len(lights_diff['changed'])}):")
            for light in lights_diff['changed']:
                click.echo(f"    ~ {light['name']}")
                for change in light['changes']:
                    click.echo(f"        {change}")

        click.echo()

        # Scenes section
        scenes_diff = diff['scenes']
        click.secho(f"SCENES: {scenes_diff['summary']}", fg='yellow' if (scenes_diff['added'] or scenes_diff['removed'] or scenes_diff['changed']) else 'green', bold=True)

        if scenes_diff['added']:
            click.echo(f"  Added ({len(scenes_diff['added'])}):")
            for name in scenes_diff['added']:
                click.echo(f"    + {click.style(name, fg='green')}")

        if scenes_diff['removed']:
            click.echo(f"  Removed ({len(scenes_diff['removed'])}):")
            for name in scenes_diff['removed']:
                click.echo(f"    - {click.style(name, fg='red')}")

        if scenes_diff['changed']:
            click.echo(f"  Changed ({len(scenes_diff['changed'])}):")
            for scene in scenes_diff['changed']:
                click.echo(f"    ~ {scene['name']}")
                for change in scene['changes']:
                    click.echo(f"        {change}")

        click.echo()

        # Behaviours section
        behaviours_diff = diff['behaviours']
        click.secho(f"BEHAVIOUR INSTANCES: {behaviours_diff['summary']}", fg='yellow' if (behaviours_diff['added'] or behaviours_diff['removed'] or behaviours_diff['changed']) else 'green', bold=True)

        if behaviours_diff['added']:
            click.echo(f"  Added ({len(behaviours_diff['added'])}):")
            for name in behaviours_diff['added']:
                click.echo(f"    + {click.style(name, fg='green')}")

        if behaviours_diff['removed']:
            click.echo(f"  Removed ({len(behaviours_diff['removed'])}):")
            for name in behaviours_diff['removed']:
                click.echo(f"    - {click.style(name, fg='red')}")

        if behaviours_diff['changed']:
            click.echo(f"  Changed ({len(behaviours_diff['changed'])}):")
            for behav in behaviours_diff['changed']:
                click.echo(f"    ~ {behav['name']}")
                for change in behav['changes']:
                    click.echo(f"        {change}")

        click.echo()

    except Exception as e:
        click.secho(f"✗ Error comparing room: {e}", fg='red')
        import traceback
        traceback.print_exc()
        click.echo()


@click.command(name='restore-room')
@click.argument('saved_file')
@click.option('--yes', '-y', is_flag=True, help='Skip confirmation prompt')
def restore_room_command(saved_file: str, yes: bool):
    """Restore room configuration from a saved backup.

    Applies all behaviour instances (switch button programmes) from the saved
    backup to the bridge, restoring the room to the saved state.

    \b
    What gets restored:
      - All behaviour instances (switch button programmes)
      - Button configurations (scene cycles, time-based schedules, etc.)

    \b
    What does NOT get restored:
      - Light states (on/off, brightness, colour)
      - Scene definitions (use the Hue app to manage scenes)

    \b
    Examples:
      # Restore with specific file
      uv run python hue_control.py restore-room cache/saved-rooms/2025-12-13_16-13_Living_room.json

      # Use room name - finds most recent backup for that room
      uv run python hue_control.py restore-room "Living"
      uv run python hue_control.py restore-room "Office upstairs"

      # Skip confirmation prompt
      uv run python hue_control.py restore-room "Living" --yes

    \b
    WARNING: This will modify your Hue bridge configuration!
    Always verify with 'diff-room' first to see what will change.
    """
    # Create a live controller (not cache-based) for write operations
    controller = HueController()
    if not controller.connect():
        click.secho("✗ Failed to connect to bridge", fg='red')
        return

    # Check if saved_file is a path or a room name
    saved_path = Path(saved_file)

    # If it's not an existing file, try to find saved files by room name
    if not saved_path.exists():
        # Ensure saved-rooms directory exists
        if not SAVED_ROOMS_DIR.exists():
            click.secho(f"✗ No saved rooms found in {SAVED_ROOMS_DIR}", fg='red')
            return

        # Find all saved files matching the room name
        matching_files = []
        room_name_lower = saved_file.lower()

        for saved_file_path in SAVED_ROOMS_DIR.glob('*.json'):
            # Extract room name from filename: YYYY-MM-DD_HH-MM_RoomName.json
            filename = saved_file_path.stem  # Remove .json
            # Split by timestamp pattern, room name is after second underscore
            parts = filename.split('_')
            if len(parts) >= 3:
                # Room name starts from index 2 (after date and time)
                room_part = '_'.join(parts[2:])
                if room_name_lower in room_part.lower():
                    matching_files.append(saved_file_path)

        if not matching_files:
            click.secho(f"✗ No saved room files found matching '{saved_file}'", fg='red')
            click.echo(f"\nAvailable saved rooms in {SAVED_ROOMS_DIR}:")
            all_files = sorted(SAVED_ROOMS_DIR.glob('*.json'), key=lambda x: x.stat().st_mtime, reverse=True)
            if all_files:
                for f in all_files[:10]:  # Show up to 10 most recent
                    timestamp = f.stem.split('_')[:2]
                    room_name = '_'.join(f.stem.split('_')[2:])
                    click.echo(f"  {' '.join(timestamp)} - {room_name}")
                if len(all_files) > 10:
                    click.echo(f"  ... and {len(all_files) - 10} more")
            else:
                click.echo("  (none)")
            return

        # Sort by modification time (most recent first)
        matching_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        saved_path = matching_files[0]

        # Show which file we're using
        if len(matching_files) > 1:
            click.echo(f"\nFound {len(matching_files)} saved files matching '{saved_file}'")
            click.echo(f"Using most recent: {click.style(saved_path.name, fg='cyan')}")
        else:
            click.echo(f"\nUsing: {click.style(saved_path.name, fg='cyan')}")

    # Call the restore function
    try:
        success = restore_room_configuration(controller, str(saved_path), skip_confirmation=yes)

        if not success:
            click.echo()
            click.secho("⚠ Restore incomplete or cancelled", fg='yellow')

    except Exception as e:
        click.echo()
        click.secho(f"✗ Error restoring room: {e}", fg='red')
        import traceback
        traceback.print_exc()
