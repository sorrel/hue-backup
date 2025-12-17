# Device Inspection Commands - Refactoring Plan

## Current Duplication

### 1. Room Detection (repeated in switches, plugs, lights, other, all)
```python
room_name = 'Unassigned'
for room_data in rooms_list:
    children = room_data.get('children', [])
    if any(c.get('rid') == device_id for c in children):
        room_name = room_data.get('metadata', {}).get('name', 'Unknown')
        break
```

### 2. Room Filtering (repeated in all commands)
```python
if room and room.lower() not in room_name.lower():
    continue
```

### 3. Table Display Logic (near-identical in all commands)
- Calculate column widths (with display_width for emoji fields)
- Ensure minimum widths for headers
- Print header with cyan bold
- Print separator with dashes
- Print rows with room grouping (room name only on first row)

### 4. Summary Generation (similar pattern in all commands)
- Count totals
- Group by model/type
- Display with formatting

## Proposed Helper Functions

### 1. `find_device_room(device_id: str, rooms_list: list) -> str`
Returns room name for a device, or 'Unassigned'

### 2. `filter_by_room(room_name: str, filter_text: str | None) -> bool`
Returns True if device should be included (handles None filter)

### 3. `display_device_table(rows: list[dict], columns: list[dict], title: str, emoji_columns: list[str] = None)`
Generic table display with:
- rows: list of dicts with data
- columns: list of {'key': 'name', 'header': 'Switch Name', 'color': 'white', 'align': 'left'}
- title: "=== Switches ==="
- emoji_columns: list of column keys that contain emojis (use display_width)

### 4. `generate_model_summary(items: list[dict], model_key: str = 'model', type_name: str = 'device')`
Generates and displays model breakdown summary

## Commands to Refactor

1. switches_command (lines 331-469)
2. plugs_command (lines 1256-1452)
3. lights_command (lines 1456-1670)
4. other_command (lines 1674-1857)
5. all_devices_command (lines 1881-2109)

## Expected Reduction

Current: ~1,200 lines of duplicated code
After: ~300-400 lines (helper functions) + ~200-300 lines (simplified commands)
Savings: ~60-70% code reduction
