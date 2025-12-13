# Hue Control CLI

A Python CLI for programming Philips Hue switches and inspecting the Hue setup. Designed to be used by AI assistants (like Claude Code) as a local tool for home automation tasks, but can also be used directly on the command line.

**Primary use case:** Map button presses on physical Hue switches to scene activations, and query switch configurations. You can back-up and restore room configurations, so you can change the lights seasonally.

**Not a general light controller** - use the Hue app for that. This tool focuses on switch, zone and room programming, not day to day light controls.

## Quick Start

```bash
# Install dependencies
uv sync

# First-time setup (discovers bridge, creates API token)
uv run python hue_control.py configure

# Check your switches
uv run python hue_control.py switch-status

# See what's programmed into wall controls
uv run python hue_control.py button-data
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

### Room Backups

```bash
save-room "Living Room"  # Save room config to timestamped file
diff-room "Living Room"  # Compare saved vs current state
```

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
models/                  # Room operations, utilities
commands/                # CLI commands (setup, inspection, control, etc.)
tests/                   # 71 tests, all mocked
cache/                   # Local cache (gitignored)
```

## Development

```bash
# Run tests
uv run pytest -v
```

## Button Event Codes

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

## Notes

- API keys don't expire (one-time setup)
- Cache auto-refreshes after 24 hours
- SSL warnings suppressed (bridges use self-signed certs)
- Local API only (no cloud/remote API), apart from the inital bridge finder API.
