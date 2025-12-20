# Zone Programming Guide

## Overview

This guide documents how to programme Hue switches/dials to control only lights within a specific zone, with zone-filtered scenes that are set to auto-dynamic.

## What It Does

The `program-zone-switch` command:
1. Takes original scenes (e.g., "CL01", "Relax")
2. Creates zone-filtered versions (e.g., "CL01 (lounge)")
3. Only includes lights from the specified zone
4. Lights not in the original scene are turned ON by default
5. Excluded lights (e.g., "Back lights") are turned OFF
6. All created scenes are set to auto-dynamic
7. Updates the switch buttons to use the new zone-filtered scenes

## Critical Implementation Details

### Zone Scene Requirement

**IMPORTANT**: The Hue API requires zone-based scenes to include actions for ALL lights in the zone. You cannot create partial scenes.

**Solution**: Include all zone lights in every scene:
- Lights from the original scene: Use their original settings
- Lights not in original scene: Turn ON (default for zone lights)
- Excluded lights: Turn OFF (via `--exclude-button`)

This is implemented in `models/zone_utils.py` in the `filter_scene_actions_for_zone()` function.

### Scene Naming Convention

- Zone scenes: `"SceneName (zone-short-name)"` (e.g., "CL01 (lounge)")
- With exclusions: `"SceneName (zone-short-name) -X"` (e.g., "CL01 (lounge) -X")
- Maximum length: 32 characters (Hue API limit)
- Zone name shortening: "Combined lounge" → "lounge"

### Button Configuration Format

The Hue API has two formats for button configuration:
- **Old format**: `button1`, `button2`, `button3`, `button4` keys
- **New format**: `buttons` dict with button RIDs as keys

The command handles both formats and creates/updates the appropriate structure.

## Usage Examples

### Basic Usage

Programme a dial to control only zone lights:

```bash
uv run python hue_backup.py program-zone-switch \
  "Combined lounge" "The Sparkles" \
  -b 1 -b 2 \
  --scenes "CL01,CL14,CL12,Relax,Nightlight,CL16,CL15,CL13" \
  -y
```

### With Excluded Lights

Programme button 2 to exclude specific lights:

```bash
uv run python hue_backup.py program-zone-switch \
  "Combined lounge" "The Sparkles" \
  -b 1 -b 2 \
  --scenes "CL01,CL14,CL12,Relax,Nightlight,CL16,CL15,CL13" \
  --exclude-button "2:Back lights" \
  -y
```

### Dry Run

Preview what will be created without making changes:

```bash
uv run python hue_backup.py program-zone-switch \
  "Combined lounge" "The Sparkles" \
  -b 1 -b 2 \
  --scenes "CL01,CL14,CL12,Relax,Nightlight" \
  --exclude-button "2:Back lights" \
  --dry-run
```

## Implementation Files

### Core Files

- **`commands/zone_programming.py`** - Main command implementation (350+ lines)
- **`models/zone_utils.py`** - Zone filtering utilities (190+ lines)
- **`core/controller.py`** - Scene creation and deletion methods

### Key Functions

**`create_scene(name, group_rid, actions, auto_dynamic, speed)`** (controller.py)
- POST to `/resource/scene`
- Write-through cache pattern
- Returns new scene ID

**`delete_scene(scene_id)`** (controller.py)
- DELETE from `/resource/scene/{id}`
- Updates cache

**`filter_scene_actions_for_zone(scene, zone_lights, exclude_lights)`** (zone_utils.py)
- Filters scene actions to zone lights
- **Critical**: Includes ALL zone lights (with some set to OFF)
- Logic:
  1. If light is excluded → OFF
  2. If light in original scene → use original action
  3. If light in zone but not in scene → ON (default)

**`generate_zone_scene_name(original, zone, excluded_lights, light_lookup)`** (zone_utils.py)
- Generates unique scene names
- Handles 32-character limit
- Shortens zone names
- Uses "-X" suffix for exclusions

## Workflow

1. **Find zone and switch** - Fuzzy name matching
2. **Parse scene names** - From `--scenes` parameter
3. **Build exclusion map** - Parse `--exclude-button` options
4. **For each button**:
   - For each scene name:
     - Find original scene
     - Filter actions to zone lights
     - Apply button-specific exclusions
     - Check if zone scene already exists
     - Create new scene or reuse existing
     - Set auto-dynamic
     - Collect scene ID
   - Build button configuration with scene cycle
5. **Update behaviour instance** - Write-through cache pattern

## Common Issues and Solutions

### Issue: Scenes Already Exist

**Solution**: The command automatically reuses existing zone scenes if they match the naming pattern. Delete old scenes first if you need to regenerate them.

### Issue: Behaviour Instance Deleted

**Symptom**: Error "No instance exists with id: ..."

**Cause**: Deleting scenes that are referenced by a behaviour instance will delete the behaviour instance.

**Solution**:
1. Recreate the switch programming in the Hue app (any scenes)
2. Run `reload` to update the cache
3. Re-run the zone programming command

### Issue: Cache Stale

**Symptom**: Command references deleted scenes or old IDs

**Solution**:
```bash
# Delete cache and reload
rm cache/hue_data.json
uv run python hue_backup.py reload
```

### Issue: Scene Names Too Long

**Symptom**: API error with `maxLength` keyword

**Solution**: The command now automatically:
- Shortens zone names ("Combined lounge" → "lounge")
- Uses "-X" suffix instead of listing excluded light names
- Truncates to 32 characters if needed

## Testing Checklist

Before using on the physical dial:

1. ✅ Run with `--dry-run` to preview
2. ✅ Check scene count is correct
3. ✅ Verify zone light filtering
4. ✅ Confirm exclusions are applied
5. ✅ Back up the room first: `uv run python hue_backup.py save-room "Room Name"`
6. ✅ Execute the command
7. ✅ Verify scenes with `scenes` command
8. ✅ Test on physical dial

## Restore If Needed

If something goes wrong:

```bash
# Restore from backup
uv run python hue_backup.py restore-room "Living room" -y

# Or restore from specific file
uv run python hue_backup.py restore-room cache/saved-rooms/2025-12-19_13-25_Living_room.json -y
```

## Example Session

```bash
# 1. Back up current state
uv run python hue_backup.py save-room "Living room"

# 2. Preview the changes
uv run python hue_backup.py program-zone-switch \
  "Combined lounge" "The Sparkles" \
  -b 1 -b 2 \
  --scenes "CL01,CL14,CL12,Relax,Nightlight,CL16,CL15,CL13" \
  --exclude-button "2:Back lights" \
  --dry-run

# 3. Execute
uv run python hue_backup.py program-zone-switch \
  "Combined lounge" "The Sparkles" \
  -b 1 -b 2 \
  --scenes "CL01,CL14,CL12,Relax,Nightlight,CL16,CL15,CL13" \
  --exclude-button "2:Back lights" \
  -y

# 4. Verify scenes were created
uv run python hue_backup.py reload
uv run python hue_backup.py scenes | grep lounge

# 5. Test the dial!
# Button 1: Should control all 5 Combined lounge lights
# Button 2: Should control same lights but Back lights stay OFF

# 6. If needed, restore
# uv run python hue_backup.py restore-room "Living" -y
```

## Date Created

2025-12-20

## Author

Generated by Claude Code during zone programming implementation
