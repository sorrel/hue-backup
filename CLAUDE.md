# CLAUDE.md — hue-control

Moved here from the workspace-level `scripts/CLAUDE.md` (2 November 2026), which now holds only the conventions shared by every project.

## Project Overview

A Python CLI tool for programming and monitoring Philips Hue switches. Built using Click framework and the Hue Bridge API v2.

**Main purpose:** Map button presses on physical Hue switches to scene activations, monitor switches continuously to respond to button presses, and inspect/debug the Hue setup.

**NOT a general light controller** - This tool is specifically for switch programming and monitoring, not for turning lights on/off (though some basic light control commands exist as utilities).

## CRITICAL SAFETY RULE

**⚠️ NEVER write changes to the Hue setup without explicit user permission.**

- **Read-only commands are always safe:** `button-data`, `switch-status`, `status`, `scenes`, `cache-info`, `save-room`, `diff-room`, etc.
- **Write commands require permission:** Any command that modifies bridge configuration (changing button programmes, restoring rooms, activating scenes, changing lights) MUST have explicit user approval before execution.
- **When implementing new write commands:** Always confirm with the user before running commands that modify the Hue bridge state.
- **Testing write operations:** Ask the user first before testing any commands that make changes to their physical setup.

This is a live home automation system. Unexpected changes can be disruptive.

## Running Commands

Always use `uv` for running this project:

```bash
# Run the CLI (automatically handles dependencies)
uv run python hue_backup.py <command>

# Examples:
uv run python hue_backup.py setup
uv run python hue_backup.py button-data
uv run python hue_backup.py monitor

# Install dependencies if needed
uv sync
```

Using `uv run python hue_backup.py` ensures all dependencies are up to date without requiring a separate install step.

**Alternative short command:** After running `uv pip install -e .` once, you can use `uv run hue <command>`, but this is optional. The direct execution method above is preferred.

## Architecture

### Core Components

**HueController class** (core/controller.py)

- Main controller managing all Hue Bridge interactions via API v2
- Uses a fully-verified requests session: TLS is pinned to the Hue Bridge root CA with the bridge ID asserted as the certificate identity (see `core/tls.py`)
- Implements resource caching for devices, buttons, scenes, and behaviour instances
- Maintains button state for change detection during monitoring

**Authentication flow (priority order):**

1. **1Password Environments** - Environment variables via mounted .env file
   - Variables: `HUE_BRIDGE_IP` and `HUE_API_TOKEN`
   - Mounted by 1Password desktop app (Developer → Environments → local .env file destination)
   - `.env` file path: `./env` (gitignored, never committed)
2. **Interactive setup** - Run `configure` command for guided setup with bridge discovery
   - Discovers bridge, creates API token, displays credentials for 1Password setup
3. Button mappings (local CLI feature) stored in project cache: `./cache/hue_data.json`

**Configuration files:**
- **User auth:** `.env` file (1Password mounted, contains HUE_BRIDGE_IP and HUE_API_TOKEN) - gitignored
- **Project cache:** `./cache/hue_data.json` (button mappings, bridge data cache) - gitignored, project-specific

**First-time setup:**
1. Run `uv run python hue_backup.py configure` to create credentials
2. Add credentials to 1Password Environment
3. Mount .env file destination to project directory
4. Run `uv run python hue_backup.py setup` to test connection

### API v2 Structure

The tool uses Hue Bridge API v2 which has a different resource model than v1:

- **Resources:** `/resource/{type}` endpoints (light, scene, device, button, etc.)
- **Devices:** Physical hardware with multiple services (buttons, power, etc.)
- **Buttons:** Individual button resources referenced by device services
- **Behaviour instances:** Bridge-native button-to-scene mappings
- **Scenes:** Activated via PUT with `recall` action, not v1-style activation

**Important v1 compatibility layer:**

- `get_sensors()` converts v2 devices to v1-like structure
- Uses `id_v1` field from v2 resources when available
- Maps v2 button events to v1-style event codes (e.g., "short_release" → "002")

### Button Event System

**Event codes (4 digits):** `XYYY` format

- X = button number (1=On, 2=Dim Up, 3=Dim Down, 4=Off, 5=Special)
- YYY = event type (000=Initial Press, 001=Hold, 002=Short Release, 003=Long Release)
- Special handling for tap dial: 34xxx (rotate), 35xxx (press)

**Monitoring loop:**
- Polls every 500ms via `get_button_events()`

- Detects new events by comparing `lastupdated` timestamps
- Triggers callback with sensor_id and event_data
- Local mappings checked and scenes activated

### Wall Controls (Dimmers & Dials)

**button-data command implementation:**

- Enumerates all bridge-configured button programmes for wall controls
- Supports both old format (button1/button2/button3/button4) and new format (buttons dict with button rids)
- Shows button labels: 1=ON, 2=DIM UP, 3=DIM DOWN, 4=OFF, 34=DIAL ROTATE, 35=DIAL PRESS
- Displays room assignments in square brackets after device name
- Filter by room with `-r <room>` - matches device name OR room name (case-insensitive substring)

**Room detection logic:**
Room information is extracted from behaviour configuration `where` fields. Checks multiple locations:

1. Top-level `config['where']` (some devices)
2. Old format: `config['button1']['where']` (devices using button1/button2 format)
3. Dial rotary: `config['rotary']['where']` (tap dials)
4. New format: `config['buttons'][button_rid]['where']` (devices using buttons dict format)

**Action types displayed:**

- **Short press:** Scene cycle (with scene list), time-based scenes (with time slots), single scene activation
- **Long press:** All Off, Home Off, etc.
- **Hold/repeat:** Dim Up, Dim Down

### CLI Structure

Built with Click using custom `ColouredGroup` class for coloured help output.

**Primary workflow commands (core functionality):**

1. **Inspection:** `button-data`, `switch-status`, `plugs`, `lights`, `other`, `all`, `status`, `switches`, `switch-info` - View switch configurations, smart plug status, light bulb status, other devices (doorbell, chimes), all devices in one view, and bridge state
2. **Discovery:** `discover` - Interactive button press detector to find event codes
3. **Mapping:** `map`, `mappings` - Create and view button-to-scene mappings
4. **Monitoring:** `monitor` - Main runtime command that watches buttons and activates mapped scenes

**Utility commands (secondary):**

- `setup` - Shows config and tests connection
- `scenes`, `scene-details`, `groups`, `zones` - Inspect scenes, groups, and zones
- `locations [-r <room>] [--lights] [--scenes]` - Show all rooms and zones with optional light and scene listings
- `activate-scene`, `power`, `brightness`, `colour` - Direct control (utility features, not main purpose)
- `auto-dynamic` - View/modify auto-dynamic settings for scenes (scenes that auto-play their dynamic effect)
- `save-room` - Save complete room configuration (lights, scenes, switch programmes) to timestamped file
- `diff-room` - Compare saved room file with current cache state, section by section
- `modify-scenes [-r <room>] [options]` - Bulk-modify multiple scenes (turn on/off lights, change brightness, remove lights)
- `program-zone-switch <zone> <switch> [options]` - Programme a switch with zone-filtered auto-dynamic scene variants
- `debug-buttons` - Debug command showing raw button configuration data

**Most important commands:**

- `button-data [-r <room>]`: **PRIMARY COMMAND** - Shows what's programmed into all wall controls (dimmers and dials) with room assignments. Filter by room name or device name with `-r`. Shows button mappings (scene cycles, time-based scenes, single scenes, long press, hold/repeat actions). Handles both old format (button1/button2) and new format (buttons dict).
- `switch-status [-t]`: Shows all switches with battery, last event, and CLI-configured mappings (box or table format)
- `plugs [-r <room>]`: Shows all smart plugs organised by room with on/off status and model information in table format. Filter by room with `-r`. Summary includes model breakdown (e.g., LOM009: 10 plugs, LOM003: 1 plug).
- `lights [-r <room>]`: Shows all light bulbs and fixtures (excludes smart plugs) organised by room with on/off status, model ID, and product type in table format. Filter by room with `-r`. Summary includes model breakdown (e.g., LCT015: 3 lights, LWA001: 2 lights). Shows bulbs, spots, candles, strips, filament bulbs, etc.
- `other [-r <room>]`: Shows other devices that aren't switches, plugs, or lights (doorbell cameras, chimes, Hue Bridge, etc.) organised by room with model ID and product type in table format. Filter by room with `-r`. Summary includes model breakdown.
- `all [-r <room>]`: Shows all devices (switches, plugs, lights, and other) in one unified view organised by room. Displays device name, type, and model information in table format. Filter by room with `-r`. Summary shows counts by device type.
- `auto-dynamic [-r <room>] [-s <scene>] [--set on/off] [-y]`: View or modify auto-dynamic settings for scenes. Supports filtering by room or scene name. Use `--set on/off` to enable/disable auto-dynamic. Use `-y` to skip confirmation.
- `save-room <room>`: Save complete room configuration to `cache/saved-rooms/YYYY-MM-DD_HH-MM_RoomName.json`. Includes room metadata, lights (with states), scenes (with auto_dynamic), and behaviour instances (switch programmes). For future restoration.
- `diff-room <file|room> [-v] [--reload]`: Compare saved room backup with current cache. Accepts either a file path or a room name excerpt (automatically finds most recent backup for that room). Default mode shows button-level changes (scene cycles, time-based schedules). Use `-v/--verbose` to show actual scene names in bright yellow. Use `--reload/-r` to force fresh cache reload before comparing (ensures live comparison). Uses colour coding (green=added, red=removed, yellow=changed). Examples: `diff-room "Living" --reload -v` shows live state with scene names.
- `restore-room <file|room> [-y]`: Restore room configuration from saved backup. Applies all behaviour instances (switch button programmes) to bridge. Accepts either file path or room name excerpt (finds most recent). Shows what will be restored and prompts for confirmation (skip with `-y`). Uses write-through cache. Example: `restore-room "Living"` restores most recent backup.
- `program-button <switch> <button> [options]`: Programme individual button actions on switches. Supports scene cycles (--scenes), time-based schedules (--time-based with --slot), single scenes (--scene), dimming (--dim-up/--dim-down with optional --where to specify zone/room), and long press actions (--long-press). Examples: `program-button "Office dimmer" 2 --dim-up --where "Upstairs"` sets button 2 to dim all lights in Upstairs zone. `program-button "Office dimmer" 1 --scenes "Read,Concentrate,Relax"` creates scene cycle on button 1.
- `duplicate-scene <source> <new_name> [options]`: Duplicate a scene with modifications. Create variations of existing scenes for different contexts. Options: `--turn-on LIGHT` turns a specific light on, `--turn-off LIGHT` turns it off, `--brightness "LIGHT=50%"` changes brightness, `--remove-light LIGHT` removes it entirely. Useful workflow: duplicate all scenes from one button with modifications (e.g., turn off one light), then programme the new scenes onto a different button. Example: `duplicate-scene "Reading" "Reading no lamp" --turn-off "Lamp lounge" -y` creates a copy without the lamp.
- `locations [-r <room>] [--lights] [--scenes]`: Show all rooms and zones. Add `--lights` to list lights per location, `--scenes` to list scenes. Filter with `-r`.
- `modify-scenes [-r <room>] [--turn-on LIGHT] [--turn-off LIGHT] [--brightness "LIGHT=50%"] [--remove-light LIGHT] [-y]`: Bulk-modify all scenes in a room. Applies the same light modification to every matching scene. Useful for adding/removing a light from all scenes at once.
- `program-zone-switch <zone> <switch> [-b BUTTON] [--scenes ...] [--exclude-button BUTTON:LIGHT] [--dry-run] [-y]`: Programme a switch with zone-specific scene variants that only affect lights in the target zone. All created scenes are set to auto-dynamic. Use `--dry-run` to preview changes.
- `discover`: Interactive button press detector
- `monitor`: Main runtime command that watches buttons and activates mapped scenes

## Development Notes

### Language and Style Conventions

**ALWAYS use British English** in all:

- Code comments
- Variable names and function names (e.g., `colour` not `color`)
- CLI output messages
- Documentation
- Commit messages

**Use English idioms** in speech and comments where appropriate.

### Development Philosophy

**Always try the simple approach first** - Don't overcomplicate solutions. Start with the straightforward implementation and only add complexity if needed.

### Git Workflow

**"Release" means the whole process: commit → push → PR → merge.** When Duncan
says "release it" (or "release the update"), do all four steps, not just the
commit.

**IMPORTANT: Never commit directly to the main branch.**

Always work on a feature branch:

1. **Create a feature branch** for your work:
   ```bash
   git checkout -b feature/descriptive-name
   # or
   git checkout -b bugfix/issue-description
   ```

2. **Make your commits** on the feature branch

3. **When ready**, create a pull request or merge to main

**Examples:**
- `git checkout -b feature/add-restore-command`
- `git checkout -b bugfix/cache-staleness-check`
- `git checkout -b refactor/split-commands`

**Never do:**
- `git commit` whilst on main branch
- Direct pushes to main

This keeps main clean and allows for proper code review before merging.

### Dependencies

- `click>=8.0.0` - CLI framework
- `requests>=2.28.0` - HTTP client for API calls
- `python-dotenv>=1.0.0` - .env file loading for 1Password Environments integration
- `pygments>=2.20.0` - Syntax highlighting (also required for security reasons)

### File Structure

**Entry Point:**
- `hue_backup.py` - Main CLI entry point - Imports and registers all commands

**Core Modules:**
- `core/auth.py` - Authentication and bridge discovery
- `core/controller.py` - HueController class for API interaction
- `core/cache.py` - Cache management functions
- `core/config.py` - Configuration management

**Data Models:**
- `models/room.py` - Room operations: save/diff/restore
- `models/utils.py` - Utility functions
- `models/button_config.py` - Button configuration helpers (find switches, build configs, validate args)
- `models/types.py` - TypedDict type definitions (AuthCredentials, DiscoveredBridge, SwitchBehaviour)
- `models/zone_utils.py` - Zone utility functions (get zone lights, filter scene actions for zone)

**CLI Commands:**
- `commands/setup.py` - Setup, configure, help, and ColouredGroup class
- `commands/cache.py` - Cache management commands
- `commands/room.py` - Room backup/diff commands
- `commands/scene_management.py` - Scene duplication and bulk modification (duplicate-scene, modify-scenes)
- `commands/zone_programming.py` - Zone-specific switch programming (program-zone-switch)
- `commands/inspection/` - Inspection commands (modular structure):
  - `helpers.py` - Shared helper functions and constants
  - `scenes.py` - Scene details command (scene-details, 1 command)
  - `status.py` - Status and overview commands (status, groups, zones, scenes — 4 commands)
  - `devices.py` - Device listing commands (plugs, lights, other, all — 4 commands)
  - `switches.py` - Switch inspection commands (switches, switch-status, switch-info, button-data, debug-buttons — 5 commands)
  - `locations.py` - Location inspection command (locations — 1 command)
- `commands/control.py` - Light/scene control commands
- `commands/mapping.py` - Button mapping and monitoring commands

**Data:**
- `.env` - User authentication (1Password mounted, HUE_BRIDGE_IP and HUE_API_TOKEN)
- `cache/hue_data.json` - Cached bridge data (lights, rooms, scenes, devices, buttons, behaviours)
- `cache/saved-rooms/` - Timestamped room backup files

**Tests:**
- `tests/test_structure.py` - Structure validation
- `tests/test_utils.py` - Display width, button event decoding, name lookups
- `tests/test_config.py` - Configuration tests
- `tests/test_cache.py` - Cache management tests
- `tests/test_controller.py` - Controller delegation tests
- `tests/test_inspection.py` - Inspection command tests
- `tests/test_button_config.py` - Button configuration helper tests
- `tests/test_tls.py` - Bridge CA pinning and certificate identity tests
- `tests/test_auth_env.py` - Bounded `.env` read (1Password FIFO)
- Total: 166 tests, all passing

### Common Patterns

**Connecting to bridge:**

```python
if not controller.connect():
    return
```

**API requests:**

```python
result = controller._request('GET', '/resource/{type}')
# Returns data array from {'data': [...], 'errors': [...]}
```

**Button event decoding:**
Use `decode_button_event(event_code)` to convert numeric codes to human-readable format.

**Programming switch buttons:**

Always backup first:
```bash
uv run python hue_backup.py save-room "Room Name"
```

Programme buttons with `program-button`:
```bash
# Scene cycle on button 1
uv run python hue_backup.py program-button "Office dimmer" 1 --scenes "Read,Concentrate,Relax" -y

# Time-based schedule on button 1 (custom slots)
uv run python hue_backup.py program-button "Office dimmer" 1 --time-based \
  --slot 07:00="Energise" --slot 20:00="Relax" --slot 23:00="Nightlight" -y

# Time-based schedule with default (07:00=Energise, 10:00=Concentrate, 17:00=Read, 20:00=Relax, 23:00=Nightlight)
uv run python hue_backup.py program-button "Office dimmer" 1 --time-based -y

# Single scene on button 4
uv run python hue_backup.py program-button "Office dimmer" 4 --scene "Relax" -y

# Dim buttons (default - controls switch's room)
# Action is auto-detected for buttons 2 and 3
uv run python hue_backup.py program-button "Office dimmer" 2 -y
uv run python hue_backup.py program-button "Office dimmer" 3 -y

# Dim buttons with zone/room control (changes which lights they control)
uv run python hue_backup.py program-button "Office dimmer" 2 --where "Upstairs" -y
uv run python hue_backup.py program-button "Office dimmer" 3 --where "Upstairs" -y

# Long press action
uv run python hue_backup.py program-button "Office dimmer" 1 \
  --scenes "Scene1,Scene2" --long-press "All Off" -y
```

Button numbers: 1=ON (top), 2=DIM UP, 3=DIM DOWN, 4=OFF (bottom)

**Default time-based schedule:**
When using `--time-based` without `--slot` parameters, the system uses the schedule from Office Dimmer button 1:
- 07:00 → Energise
- 10:00 → Concentrate
- 17:00 → Read
- 20:00 → Relax
- 23:00 → Nightlight

This requires these scenes to exist in the target room. Provide custom slots to override.

The `--where` parameter (for dim buttons only):
- Specifies which zone or room the dim buttons control
- Searches zones first, then rooms
- Prefers exact matches over substring matches
- Example: `--where "Upstairs"` matches "Upstairs" zone exactly, not "Upstairs Hallway"

Restore original configuration:
```bash
uv run python hue_backup.py restore-room "cache/saved-rooms/YYYY-MM-DD_HH-MM_RoomName.json" -y
```

**Terminal output alignment (CRITICAL):**
When formatting terminal output with columns or boxes:

- **NEVER use `len()` on strings containing emojis or Unicode symbols** - they display as 2 columns but `len()` counts them as 1
- **Always use the `display_width()` helper function** for width calculations
- **Apply ANSI colour codes AFTER calculating padding**, not before
- Characters that take 2 display columns: 🔋 🪫 → and most emojis (Unicode > 0x1F300)
- Pattern: `click.style(text, fg='colour') + ' ' * (width - len(text))` - style first, then pad with plain spaces

### Testing

**Automated Tests:**

- 166 tests across 9 test files (all passing)
- Run with: `uv run python -m pytest -v`
- Also run in CI on every push to main and every pull request (`.github/workflows/tests.yml`)
- Test modules:
  - `test_structure.py` - Directory and file structure validation
  - `test_utils.py` - Display width, button event decoding, name lookups
  - `test_config.py` - Configuration loading
  - `test_cache.py` - Cache management (reload, staleness, freshness)
  - `test_controller.py` - Controller delegation tests
  - `test_inspection.py` - Inspection command tests
  - `test_button_config.py` - Button configuration helper tests
  - `test_tls.py` - Bridge CA pinning and certificate identity
  - `test_auth_env.py` - Bounded `.env` read (1Password FIFO: no blocking, no leaked threads)
- All tests use mocks - no actual file writes or API calls during testing

**Manual Testing Workflow:**

1. Run `setup` to verify connection
2. Use `discover` to test button detection
3. Create test mapping with `map`
4. Run `monitor` to verify scene activation

## 1Password Environments Integration

**Setup:**

1. **1Password desktop app** (Mac/Linux) with Environments feature enabled
   - Go to Settings → Developer → Enable "1Password Developer"

2. **Create environment:**
   - Open 1Password → Developer → View Environments
   - Create new environment named "Hue Control"
   - Add two variables:
     - `HUE_BRIDGE_IP` - Your bridge IP address (e.g., "192.168.1.100")
     - `HUE_API_TOKEN` - Your API authentication token

3. **Mount .env file destination:**
   - In the environment, go to Destinations tab
   - Configure "Local .env file"
   - Set path to: `/path/to/hue-control/.env`
   - Click "Mount .env file"

**How it works:**

- 1Password mounts the `.env` file using UNIX named pipes (never written to disk as plaintext)
- `python-dotenv` loads variables at startup
- Environment variables are only exposed when the application runs
- More secure than CLI calls - only exposes specific variables you configure
- No subprocess calls that could be intercepted or modified

**Security benefits:**

- Secrets never touch disk as plaintext files
- Scoped to only the variables you configure (not entire vault access)
- No CLI subprocess calls that could request arbitrary fields
- Prevents malicious code modifications from accessing other credentials

## Cache Architecture & State Management

The cache acts as a local "state file" (similar to Terraform) - a snapshot of the bridge configuration that avoids repeated API calls.

### Current Implementation

- **Read operations:** Use cache (via `use_cache=True`)
- **Full refresh:** `reload` command fetches everything from bridge
- **Auto-refresh:** Cache auto-reloads if >24 hours old

### Write-Through Cache Strategy (Implemented)

When modifying bridge configuration, update the local cache immediately after a successful API call. This avoids full cache reloads after each change.

**Implementation (core/controller.py):**

Three helper methods for cache updates:

- `_update_cache_entry(resource_type, resource_id, new_data)` - Update existing resource (PUT operations)
- `_add_cache_entry(resource_type, new_data)` - Add new resource (POST operations)
- `_remove_cache_entry(resource_type, resource_id)` - Remove resource (DELETE operations)

**Example methods demonstrating the pattern (core/controller.py):**

- `update_behaviour_instance()` - Update button programme configuration
- `create_behaviour_instance()` - Create new button programme
- `delete_behaviour_instance()` - Delete button programme

These example methods show the correct pattern for future modification commands.

**Usage pattern:**

```python
def update_behaviour_instance(self, instance_id: str, config: dict) -> bool:
    # 1. Make the API call
    result = self._request('PUT', f'/resource/behavior_instance/{instance_id}', config)

    # 2. Update cache on success
    if result and self.use_cache:
        updated = self._request('GET', f'/resource/behavior_instance/{instance_id}')
        if updated:
            self._update_cache_entry('behaviours', instance_id, updated[0])

    return result is not None
```

**What gets cached:**

- ✅ **Behaviour instances** - Button programmes (static, rarely changed externally)
- ✅ **Scenes** - Scene definitions (static)
- ✅ **Devices/Buttons** - Hardware configuration (static)
- ❌ **Light states** - Changes constantly, not cached on write (use `reload` if needed)

**Benefits:**

- No extra API calls after writes
- Local state always matches what we just told the bridge
- Fast - no network round-trip to verify
- Predictable - we know exactly what's in the cache

**For external changes** (someone uses the Hue app), run `reload` to sync up - same as Terraform's `terraform refresh`.

### Alternative Approaches (Not Implemented)

**Selective Refresh:** Re-fetch only the modified resource type

```python
def refresh_behaviours(self):
    behaviours = self._request('GET', '/resource/behavior_instance')
    if behaviours:
        self.config['cache']['behaviours'] = behaviours
        self._save_config()
```

**EventStream (SSE):** Subscribe to `/eventstream/clip/v2` for real-time updates from the bridge. More complex but would catch external changes automatically.

## Important Notes

- **Authentication:** Uses 1Password Environments via .env file (HUE_BRIDGE_IP and HUE_API_TOKEN)
- **Bridge discovery:** Automatic via N-UPnP (https://discovery.meethue.com/)
- **Configuration:** User credentials in `.env` (1Password mounted), project cache in `./cache/hue_data.json`
- **API v2 only:** TLS fully verified by pinning the Hue Bridge root CA and asserting the bridge ID (see `core/tls.py`); the bridge ID is learned from the certificate on first connect and cached
- **Button mappings:** Local to this tool, separate from bridge-native automations
- **British English spelling** preferred throughout (see ~/.claude/CLAUDE.md)
- **Wall controls:** Include both dimmers (4 buttons) and tap dials (rotate + press buttons)
- **No hardcoded credentials:** Codebase is fully shareable
- **Security:** Secrets never written to disk - mounted via 1Password UNIX pipes

## Changelog

### 31 December 2025 - Migration to 1Password Environments

**Authentication overhaul:**
- Migrated from 1Password CLI (`op item get`) to 1Password Environments (mounted .env file)
- Removed `load_auth_from_1password()` and `save_auth_to_user_config()` functions
- Removed `is_op_available()` from `core/config.py`
- Removed local config file fallback (`~/.hue_backup/config.json`)
- Added `load_auth_from_environment()` to read `HUE_BRIDGE_IP` and `HUE_API_TOKEN`
- Added `python-dotenv>=1.0.0` dependency for .env file loading

**Security improvements:**
- Credentials never written to disk as plaintext (1Password uses UNIX pipes)
- Scoped access - only exposes configured environment variables
- Eliminates risk of code modification requesting arbitrary vault fields
- No subprocess calls that could be intercepted

**Updated documentation:**
- README.md - New authentication section with setup steps
- CLAUDE.md - Updated architecture and 1Password integration sections
- Help command and `configure` command updated

**Configuration changes:**
- Authentication priority: Environment variables → Interactive setup
- `.env` file added to `.gitignore`
- Removed 4 tests related to `is_op_available()`

**Tests:** 140 tests, all passing

### 28 December 2025 - Code Review & Cleanup

**Dead code removed (~300 lines):**
- Removed deprecated `load_from_1password()` function from `core/config.py`
- Removed deprecated `bridge_auto` command from `switches.py` (~140 lines) - use `button-data` instead
- Cleaned up unused imports in `hue_backup.py`

**Code improvements:**
- Added `extract_room_rids_from_behaviour()` helper to `models/utils.py` - unified extraction of room RIDs from behaviour configs (replaced ~50 lines of duplicated code across 3 files)
- Added `get_resource_name()` helper to `models/utils.py` - canonical way to extract names from resources
- Added `_get_cache_items()` helper to `core/controller.py` - reduces boilerplate in cache entry methods
- Fixed SSL certificate verification to work on macOS by explicitly passing `verify=False` to requests

**Tests:** 144 tests, all passing
