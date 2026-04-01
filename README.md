# Hue Backup CLI

A Python CLI for programming Philips Hue switches and inspecting the Hue setup. Designed to be used by AI assistants (like Claude Code) as a local tool for home automation, but also useful on the command line.

**Primary use case:** Back-up and restore room configurations, so you can change the lights seasonally.

**Not a general light controller** - use the Hue app for that. This tool focuses on switch, zone and room programming, not light on/off. Think of it as a terraform for the Hue lighting system.

## Quick Start

Note: this was written for CLI use on a Mac; it is untested on other systems.

```bash
# Install dependencies (includes dev dependencies for testing)
uv sync --extra dev

# First-time setup (discovers bridge, creates API token)
uv run python hue_backup.py configure

# Check your switches
uv run python hue_backup.py switch-status

# See what's programmed into wall controls
uv run python hue_backup.py button-data

# Programme a button
uv run python hue_backup.py program-button "<switch name>" 1 --scenes "Read,Relax"
```

---

> **💡 Tab Completion Available!**
>
> Get command and option auto-completion in your shell:
> ```bash
> uv run python hue_backup.py install-completion
> source ~/.zshrc  # or ~/.bashrc for bash
> ```
> This creates a convenient `hue` command that works from any directory, so instead of typing `uv run python hue_backup.py`, you can just type:
> ```bash
> hue button-data
> hue switch-status
> hue <TAB>  # See all commands!
> ```
> Supports zsh, bash, and fish. Re-run `install-completion` after adding new commands to update tab completion.

---

## Key Commands

### Inspection

```bash
button-data              # What's programmed into all wall controls (PRIMARY)
button-data -r "Living"  # Filter by room
switch-status            # All switches with battery, last event, mappings
plugs                    # Smart plugs with status and model info (table view)
plugs -r "Living"        # Filter plugs by room
lights                   # Light bulbs/fixtures with status and model info (table view)
lights -r "Living"       # Filter lights by room
other                    # Other devices (doorbell, chimes, bridge, etc.)
other -r "Hallway"       # Filter other devices by room
all                      # All devices in one unified view
all -r "Living"          # Filter all devices by room
scene-details            # Scenes with light configurations
scenes                   # List all scenes
groups                   # List all rooms/groups
zones                    # List all zones (table view)
zones -v                 # List zones with detailed light listings
zones --multi-zone       # Show lights that appear in multiple zones
switches                 # List all switches
status                   # Bridge overview
```

### Programming Buttons

```bash
# Scene cycle (2+ scenes)
program-button "Office dimmer" 1 --scenes "Read,Concentrate,Relax"

# Time-based schedule
program-button "<switch name>" 1 --time-based \
  --slot 07:00="Morning" --slot 17:00="Evening" --slot 23:00="Night"

# Single scene
program-button "<switch name>" 4 --scene "Relax"

# Long press action
program-button "<switch name>" 1 --scenes "Read,Relax" --long-press "All Off"
```

**Supported action types:**
- `--scenes` - Scene cycle (2+ scenes, rotates through on each press)
- `--time-based` with `--slot HH:MM="Scene"` - Time-based schedule (different scenes at different times)
- `--scene` - Single scene activation
- `--dim-up` / `--dim-down` - Dimming on hold/repeat
- `--long-press` - Action or scene for long press ("All Off", "Home Off", or scene name)

**Features:**
- Fuzzy matching for switch, room/zone and scenes (partial matches work)
- Shows confirmation preview before applying
- Supports both old (button1/button2) and new (buttons dict) behaviour formats
- Write-through cache keeps local state synchronized
- Helpful error messages with suggestions

### Room Backups & Seasonal Workflow

```bash
# 1. Save current configuration
save-room "<room name>"

# 2. Programme buttons for seasonal theme
program-button "<room name>" 1 --scenes "Christmas,Xmas lights,Winter cosy"
program-button "<room name>"4 --scene "Christmas"

# 3. Compare saved vs current (see what changed)
diff-room "<room name>" --reload -v

# 4. Later: restore original configuration
restore-room "<room name>"
```

**Commands:**
- `save-room <room>` - Save complete room config to timestamped file
- `diff-room <file|room> [-v] [--reload]` - Compare saved vs current state
- `restore-room <file|room> [-y]` - Restore saved configuration
- `program-button` - Modify individual button configurations

All room commands accept either full file path or room name excerpt (finds most recent backup automatically).

### Scene Duplication

Create variations of scenes with modifications - useful for creating button-specific scene sets:

```bash
# Duplicate a scene with one light turned off
duplicate-scene "Reading" "Reading no lamp" --turn-off "Lamp lounge" -y

# Multiple modifications
duplicate-scene "Relax" "Relax dimmed" \
  --turn-off "Back lights" \
  --brightness "Main light=50%"

# Remove a light entirely
duplicate-scene "Christmas" "Christmas minimal" --remove-light "Tree lights"

# Turn a light on (add to scene if not present)
duplicate-scene "Evening" "Evening bright" --turn-on "Desk lamp"
```

**Common workflow:**
1. Check scenes on a button: `button-data -r "<room/zone name>"`
2. Duplicate all scenes with modifications (e.g., turn off one light for each)
3. Programme new scenes onto a different button: `program-button "<room/zone name>" 4 --scenes "Scene1 no lamp,Scene2 no lamp,Scene3 no lamp"`

**Options:**
- `--turn-on LIGHT` - Turn specific light ON
- `--turn-off LIGHT` - Turn specific light OFF
- `--brightness "LIGHT=50%"` - Change brightness (0-100%)
- `--remove-light LIGHT` - Remove light entirely from scene
- `-y` - Skip confirmation

All modifications support fuzzy matching for light names. The new scene is created in the same room/zone as the original with all other settings preserved (auto-dynamic, speed, colours, etc.).

### Cache Management

```bash
reload                   # Refresh cache from bridge
cache-info               # Show cache age and stats
```

All commands support `-h` for help.

## Authentication

Credentials are managed via **1Password Environments** for maximum security.

### Setup Steps

1. **Create API credentials** (first time only):
   ```bash
   uv run python hue_backup.py configure
   ```
   This discovers your bridge, guides you through link button auth, and displays credentials.

2. **Add to 1Password Environment:**
   - Open 1Password desktop app
   - Go to **Developer** → **View Environments**
   - Create/open "Hue Control" environment
   - Add two variables:
     - `HUE_BRIDGE_IP` = your bridge IP (e.g., 192.168.1.100)
     - `HUE_API_TOKEN` = your API token from step 1
   - Go to **Destinations** tab → **Configure local .env file**
   - Set path to: `/path/to/hue-control/.env`
   - Click **Mount .env file**

3. **Test connection:**
   ```bash
   uv run python hue_backup.py setup
   ```

### Why 1Password Environments?

- **Secure:** Secrets never written to disk as plaintext (mounted via UNIX pipes)
- **Scoped:** Only exposes the specific variables you configure
- **Simple:** No CLI subprocess calls that could be intercepted
- **Team-friendly:** Share environments with collaborators

### How It Works

- The `.env` file is mounted by 1Password (not a real file on disk)
- `python-dotenv` loads variables at startup
- Your credentials are automatically available
- `.env` file is gitignored to prevent accidental commits

## Using with AI Assistants

This CLI is designed for AI-driven automation. The structured output and caching make it efficient for AI agents to:

- Query switch configurations without hammering the bridge
- Inspect scene assignments across rooms
- Track configuration changes over time

Example workflow with Claude Code:

```bash
# "What scenes are on my living room dimmer?"
uv run python hue_backup.py button-data -r "Living"

# "Save the current bedroom setup"
uv run python hue_backup.py save-room "Bedroom"

# "What changed since I saved it?"
uv run python hue_backup.py diff-room "Bedroom"
```

## Project Structure

```
hue_backup.py            # Entry point
core/                    # Controller, auth, cache, config
models/                  # Room operations, button config, utilities
  └── button_config.py   # Button programming business logic
commands/                # CLI commands
  ├── setup.py           # Configuration and help
  ├── cache.py           # Cache management
  ├── room.py            # Room backup/restore
  ├── control.py         # Light/scene control
  ├── mapping.py         # Button mapping and monitoring
  └── inspection/        # Device inspection (modular structure)
      ├── helpers.py     # Shared utilities (259 lines)
      ├── scenes.py      # Scene inspection (1 command)
      ├── status.py      # Status/overview (3 commands)
      ├── devices.py     # Device listing (4 commands)
      └── switches.py    # Switch inspection (5 commands)
tests/                   # 144 tests, all mocked
  ├── test_button_config.py  # Button configuration tests
  ├── test_inspection.py     # Inspection command tests
  └── test_utils.py      # Utility function tests
cache/                   # Local cache (gitignored)
  └── saved-rooms/       # Timestamped room backups
```

## Development

```bash
# Install dependencies with dev extras (includes pytest)
uv sync --extra dev

# Run all tests (140 total, all passing)
uv run pytest -v

# Run specific test file
uv run pytest tests/test_button_config.py -v
uv run pytest tests/test_inspection.py -v
```

**Test Coverage:**
- 140 tests
- All tests use mocks (no actual API calls or file writes)
- Test files:
  - `test_structure.py` - Directory and file structure
  - `test_utils.py` - Display width, button events, lookups
  - `test_config.py` - Configuration loading
  - `test_cache.py` - Cache management
  - `test_controller.py` - Controller delegation
  - `test_inspection.py` - Inspection commands
  - `test_button_config.py` - Button programming logic

## Technical Details

### Behaviour Instance Formats

The `program-button` command supports both Hue API formats, but prefers the new. The command automatically detects which format your bridge uses and handles both transparently.

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
Use `discover` to find your specific event codes. This area not developed/used currently, but could be later.

### Battery Status Display

Getting `hue switch-status` shows battery level (percentage) and state from the individual switches:

**Battery States & Icons:**
- 🔋 **Normal** - Battery healthy (green)
- ⚠️ **Low** - Replace soon (yellow warning)
- 🪫 **Critical** - Replace urgently (red)

Battery data is:
- **Cached** during `reload` for offline inspection
- **Not compared** in room diffs (ephemeral data)
- **Shown in:** `switch-status`, `switch-info`, and table formats
```

## Troubleshooting

**Can't connect?**
```bash
uv run python hue_backup.py setup  # Shows auth status
uv run python hue_backup.py configure --reconfigure  # Start fresh
```

**Stale data?**
```bash
uv run python hue_backup.py reload  # Force cache refresh
```

**1Password Environment not loading?**
- Verify .env file is mounted in 1Password desktop app
- Check variables are named correctly: `HUE_BRIDGE_IP` and `HUE_API_TOKEN`
- Ensure .env file path matches your project directory

## Notes

- Hue API keys don't expire (one-time setup)
- Cache auto-refreshes after 24 hours (when next run)
- SSL warnings suppressed (bridges use self-signed certs)
- Local API only (no cloud/remote API), apart from the initial bridge finder API
- All write operations require explicit confirmation (use `-y` flag to skip)
- Bridge-native configurations are preserved during restore operations
