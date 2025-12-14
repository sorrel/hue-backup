# Hue Control CLI

A Python CLI for programming Philips Hue switches and inspecting the Hue setup. Designed to be used by AI assistants (like Claude Code) as a local tool for home automation tasks, but can also be used directly on the command line.

**Primary use case:** Map button presses on physical Hue switches to scene activations, and query switch configurations. You can back-up and restore room configurations, so you can change the lights seasonally.

**Not a general light controller** - use the Hue app for that. This tool focuses on switch, zone and room programming, not day to day light controls.

## Quick Start

```bash
# Install dependencies (includes dev dependencies for testing)
uv sync --extra dev

# First-time setup (discovers bridge, creates API token)
uv run python hue_control.py configure

# Check your switches
uv run python hue_control.py switch-status

# See what's programmed into wall controls
uv run python hue_control.py button-data

# Programme a button (NEW!)
uv run python hue_control.py program-button "Office dimmer" 1 --scenes "Read,Relax"
```

## Key Commands

### Inspection (read-only)

```bash
button-data              # What's programmed into all wall controls (PRIMARY)
button-data -r "Living"  # Filter by room
switch-status            # All switches with battery, last event, mappings
scene-details            # Scenes with light configurations
scenes                   # List all scenes
switches                 # List all switches
status                   # Bridge overview
```

### Monitoring & Mapping

```bash
discover                 # Watch button presses (find event codes)
map <sensor> <event> <scene>  # Map button to scene
monitor                  # Run continuously, activate mapped scenes
```

### Programming Buttons (NEW)

```bash
# Scene cycle (2+ scenes)
program-button "Office dimmer" 1 --scenes "Read,Concentrate,Relax"

# Time-based schedule
program-button "Living dimmer" 1 --time-based \
  --slot 07:00="Morning" --slot 17:00="Evening" --slot 23:00="Night"

# Single scene
program-button "Bedroom dimmer" 4 --scene "Relax"

# Dimming actions
program-button "Office dimmer" 2 --dim-up
program-button "Office dimmer" 3 --dim-down

# Long press action
program-button "Office dimmer" 1 --scenes "Read,Relax" --long-press "All Off"
```

**Button numbers:** 1=ON, 2=DIM UP, 3=DIM DOWN, 4=OFF

**What it does:** Modifies bridge-native button configurations without using the Hue app. Perfect for seasonal programming workflows.

**Supported action types:**
- `--scenes` - Scene cycle (2+ scenes, rotates through on each press)
- `--time-based` with `--slot HH:MM="Scene"` - Time-based schedule (different scenes at different times)
- `--scene` - Single scene activation
- `--dim-up` / `--dim-down` - Dimming on hold/repeat
- `--long-press` - Action or scene for long press ("All Off", "Home Off", or scene name)

**Features:**
- Fuzzy matching for switch and scene names (partial matches work)
- Shows confirmation preview before applying
- Supports both old (button1/button2) and new (buttons dict) behaviour formats
- Write-through cache keeps local state synchronized
- Helpful error messages with suggestions

### Room Backups & Seasonal Workflow

```bash
# 1. Save current configuration
save-room "Living Room"

# 2. Programme buttons for seasonal theme
program-button "Living dimmer" 1 --scenes "Christmas,Xmas lights,Winter cosy"
program-button "Living dimmer" 4 --scene "Christmas relax"

# 3. Compare saved vs current (see what changed)
diff-room "Living" --reload -v

# 4. Later: restore original configuration
restore-room "Living"
```

**Commands:**
- `save-room <room>` - Save complete room config to timestamped file
- `diff-room <file|room> [-v] [--reload]` - Compare saved vs current state
- `restore-room <file|room> [-y]` - Restore saved configuration
- `program-button` - Modify individual button configurations

All room commands accept either full file path or room name excerpt (finds most recent backup automatically).

### Cache Management

```bash
reload                   # Refresh cache from bridge
cache-info               # Show cache age and stats
```

All commands support `-h` for help.

## Authentication

The tool tries these in order:

1. **1Password** - If `op` CLI available, reads from vault (see below)
2. **Local config** - `~/.hue_control/config.json`
3. **Interactive** - Prompts to run `configure`

### Option A: Interactive Setup (Recommended)

```bash
uv run python hue_control.py configure
```

Discovers your bridge, guides you through link button auth, saves credentials.

### Option B: 1Password

Add to your 1Password vault:
- **Item:** "Hue" (in "Private" vault)
- **Fields:** `bridge-ip` and `API-token`

Override defaults with environment variables:
```bash
export HUE_1PASSWORD_VAULT="Work"
export HUE_1PASSWORD_ITEM="MyBridge"
```

### Option C: Manual Config

```bash
mkdir -p ~/.hue_control
cat > ~/.hue_control/config.json << 'EOF'
{
  "bridge_ip": "192.168.1.100",
  "api_token": "your-api-token-here"
}
EOF
chmod 600 ~/.hue_control/config.json
```

## Using with AI Assistants

This CLI is designed for AI-driven automation. The structured output and caching make it efficient for AI agents to:

- Query switch configurations without hammering the bridge
- Inspect scene assignments across rooms
- Monitor and respond to button presses
- Track configuration changes over time

Example workflow with Claude Code:

```bash
# "What scenes are on my living room dimmer?"
uv run python hue_control.py button-data -r "Living"

# "Save the current bedroom setup"
uv run python hue_control.py save-room "Bedroom"

# "What changed since I saved it?"
uv run python hue_control.py diff-room "Bedroom"
```

## Project Structure

```
hue_control.py           # Entry point
core/                    # Controller, auth, cache, config
models/                  # Room operations, button config, utilities
  └── button_config.py   # Button programming business logic (NEW)
commands/                # CLI commands (setup, inspection, control, mapping)
  └── mapping.py         # Includes program-button command (NEW)
tests/                   # 115 tests, all mocked
  ├── test_button_config.py  # 33 new tests for button configuration
  └── test_utils.py      # 11 additional tests for utilities
cache/                   # Local cache (gitignored)
  └── saved-rooms/       # Timestamped room backups
```

## Development

```bash
# Install dependencies with dev extras (includes pytest)
uv sync --extra dev

# Run all tests (115 total, all passing)
uv run pytest -v

# Run specific test file
uv run pytest tests/test_button_config.py -v
```

**Test Coverage:**
- 115 total tests (71 original + 44 new)
- All tests use mocks (no actual API calls or file writes)
- Test files:
  - `test_structure.py` - Directory and file structure
  - `test_utils.py` - Display width, button events, lookups (now 22 tests)
  - `test_config.py` - Configuration loading, 1Password
  - `test_cache.py` - Cache management
  - `test_controller.py` - Controller delegation
  - `test_inspection.py` - Inspection commands
  - `test_button_config.py` - Button programming logic (NEW, 33 tests)

## Technical Details

### Behaviour Instance Formats

The `program-button` command supports both Hue API formats:

**Old format** (button1/button2/button3/button4):
```json
{
  "configuration": {
    "button1": { "on_short_release": {...} },
    "button2": { "on_short_release": {...} },
    "device": {"rid": "device-id", "rtype": "device"}
  }
}
```

**New format** (buttons dict with button RIDs):
```json
{
  "configuration": {
    "buttons": {
      "button-rid-1": { "on_short_release": {...} },
      "button-rid-2": { "on_short_release": {...} }
    },
    "device": {"rid": "device-id", "rtype": "device"}
  }
}
```

The command automatically detects which format your bridge uses and handles both transparently.

### Configuration Structures

**Scene Cycle** (scene_cycle_extended):
- Slots must be **list of lists**: `[[{action}], [{action}]]`
- Each scene wrapped in its own array

**Time-Based** (time_based_extended):
- Slots are **list of objects** with `start_time` and `actions`
- Automatically sorted by time (hour, minute)

**Write-Through Cache:**
- API call updates bridge first
- On success, immediately syncs local cache
- No extra API calls needed
- Cache stays synchronized with bridge state

### Button Event Codes

Hue Dimmer Switch buttons generate 4-digit codes: `XYYY`

- **X** = button (1=On, 2=Dim Up, 3=Dim Down, 4=Off)
- **YYY** = event (000=press, 001=hold, 002=short release, 003=long release)

Example: `1002` = On button, short release

Use `discover` to find your specific event codes. This area not developed/used.

## Troubleshooting

**Can't connect?**
```bash
uv run python hue_control.py setup  # Shows auth status
uv run python hue_control.py configure --reconfigure  # Start fresh
```

**Stale data?**
```bash
uv run python hue_control.py reload  # Force cache refresh
```

**1Password not working?**
Falls back to local config automatically. Check `op signin` if you want 1Password.

## Recent Updates

### 2025-12-14: Button Programming Command

- **NEW: `program-button` command** - Programmatically modify button configurations
- **Complete seasonal workflow** - save → programme → diff → restore
- **All action types supported** - Scene cycles, time-based schedules, single scenes, dimming, long press
- **Fuzzy matching** - Partial switch/scene names work automatically
- **Dual format support** - Handles both old (button1/button2) and new (buttons dict) API formats
- **Write-through cache** - Local state stays synchronized after modifications
- **44 new tests** - 115 total tests, all passing
- **3 new modules** - `models/button_config.py`, `tests/test_button_config.py`, enhanced utilities

See "Programming Buttons" section above for usage examples.

## Notes

- API keys don't expire (one-time setup)
- Cache auto-refreshes after 24 hours
- SSL warnings suppressed (bridges use self-signed certs)
- Local API only (no cloud/remote API), apart from the initial bridge finder API
- All write operations require explicit confirmation (use `-y` flag to skip)
- Bridge-native configurations are preserved during restore operations
