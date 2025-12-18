"""
Helper functions for inspection commands.

Shared utilities used across multiple inspection commands:
- Device emoji selection
- Room detection and filtering
- Generic table display
- Model summary generation
"""

import click
from datetime import datetime
from models.utils import display_width


# Button labels for wall controls (dimmers and dials)
BUTTON_LABELS = {
    1: 'ON',
    2: 'DIM UP',
    3: 'DIM DOWN',
    4: 'OFF',
    34: 'DIAL ROTATE',
    35: 'DIAL PRESS',
}

# Switch type emojis
SWITCH_EMOJIS = {
    'tap_dial': '🔘',   # Tap dial switch (rotary)
    'dimmer': '🎚️',    # Dimmer switch (rectangular, 4 buttons)
    'unknown': '🎛️',   # Unknown/generic switch
}


def get_switch_emoji(device_id: str, devices: list[dict]) -> str:
    """Get emoji for switch type based on device information.

    Args:
        device_id: Device ID to look up
        devices: List of device dictionaries from cache

    Returns:
        Emoji string for the switch type
    """
    if not device_id or not devices:
        return SWITCH_EMOJIS['unknown']

    # Find device by ID
    device = next((d for d in devices if d.get('id') == device_id), None)
    if not device:
        return SWITCH_EMOJIS['unknown']

    # Check product name or model ID
    product_data = device.get('product_data', {})
    product_name = product_data.get('product_name', '').lower()
    model_id = product_data.get('model_id', '')

    # Tap dial switch
    if 'tap dial' in product_name or model_id == 'RDM002':
        return SWITCH_EMOJIS['tap_dial']

    # Dimmer switch
    if 'dimmer' in product_name or model_id in ['RWL021', 'RWL022']:
        return SWITCH_EMOJIS['dimmer']

    # Unknown/generic
    return SWITCH_EMOJIS['unknown']


def format_timestamp(iso_timestamp: str) -> str:
    """Format ISO 8601 timestamp to UK format: DD/MM HH:MM"""
    if not iso_timestamp or iso_timestamp == 'N/A':
        return ''
    try:
        # Parse ISO 8601 format (e.g., "2025-12-17T14:30:45Z")
        dt = datetime.fromisoformat(iso_timestamp.replace('Z', '+00:00'))
        # Format as DD/MM HH:MM (24-hour clock, UK date format)
        return dt.strftime('%d/%m %H:%M')
    except (ValueError, AttributeError):
        return ''


def find_device_room(device_id: str, rooms_list: list) -> str:
    """Find the room assignment for a device.

    Args:
        device_id: Device ID to look up
        rooms_list: List of room dictionaries from cache

    Returns:
        Room name or 'Unassigned' if not found
    """
    for room_data in rooms_list:
        children = room_data.get('children', [])
        if any(c.get('rid') == device_id for c in children):
            return room_data.get('metadata', {}).get('name', 'Unknown')
    return 'Unassigned'


def should_include_device(room_name: str, room_filter: str | None) -> bool:
    """Check if device should be included based on room filter.

    Args:
        room_name: Name of the room the device is in
        room_filter: Room filter string (case-insensitive substring match), or None

    Returns:
        True if device should be included, False otherwise
    """
    if not room_filter:
        return True
    return room_filter.lower() in room_name.lower()


def display_device_table(
    rows: list[dict],
    columns: list[dict],
    title: str,
    emoji_columns: list[str] | None = None
) -> None:
    """Display a table of devices with room grouping.

    Args:
        rows: List of dicts containing row data (must include 'room' key)
        columns: List of column definitions with keys:
            - 'key': field name in row dict
            - 'header': column header text
            - 'color': click color name (default: 'white')
        title: Table title (e.g., "=== Switches ===")
        emoji_columns: List of column keys that contain emojis (uses display_width)

    Example:
        columns = [
            {'key': 'room', 'header': 'Room'},
            {'key': 'name', 'header': 'Device Name'},
            {'key': 'model', 'header': 'Model', 'color': 'bright_black'}
        ]
    """
    if not rows:
        return

    emoji_columns = emoji_columns or []

    # Calculate column widths
    col_widths = {}
    for col in columns:
        key = col['key']
        header = col['header']

        # Use display_width for emoji columns, len for others
        if key in emoji_columns:
            max_data = max(display_width(str(row.get(key, ''))) for row in rows)
        else:
            max_data = max(len(str(row.get(key, ''))) for row in rows)

        col_widths[key] = max(max_data, len(header))

    # Print title
    click.echo()
    click.secho(title, fg='cyan', bold=True)
    click.echo()

    # Print header
    header_parts = []
    for col in columns:
        key = col['key']
        header_parts.append(col['header'].ljust(col_widths[key]))
    click.secho(' │ '.join(header_parts), fg='cyan', bold=True)

    # Print separator
    separator_parts = ['─' * col_widths[col['key']] for col in columns]
    click.secho('─┼─'.join(separator_parts), fg='cyan')

    # Print rows with room grouping (room name only on first row)
    previous_room = None
    for row in rows:
        is_new_room = row['room'] != previous_room
        row_parts = []

        for col in columns:
            key = col['key']
            value = str(row.get(key, ''))
            color = col.get('color', 'white')
            width = col_widths[key]

            # Special handling for room column (only show on first row of group)
            if key == 'room':
                if is_new_room:
                    display_value = click.style(value, fg='bright_blue')
                    previous_room = row['room']
                else:
                    display_value = ' ' * len(value)
                    value = ' ' * len(value)  # For padding calculation
            else:
                display_value = click.style(value, fg=color)

            # Calculate padding
            if key in emoji_columns:
                padding = width - display_width(value)
            else:
                padding = width - len(value)

            row_parts.append(display_value + ' ' * padding)

        click.echo(' │ '.join(row_parts))


def generate_model_summary(
    items: list[dict],
    model_key: str = 'model',
    type_name: str = 'device',
    product_key: str | None = None
) -> None:
    """Generate and display a summary with model breakdown.

    Args:
        items: List of item dicts
        model_key: Key for model ID in item dict
        type_name: Singular name for item type (e.g., 'switch', 'plug')
        product_key: Optional key for product type/name to display alongside model
    """
    total = len(items)

    # Count by model
    model_counts = {}
    for item in items:
        model = item.get(model_key, 'Unknown')
        product = item.get(product_key, '') if product_key else ''

        if model not in model_counts:
            model_counts[model] = {'count': 0, 'product': product}
        model_counts[model]['count'] += 1

    click.echo()
    click.secho("Summary:", fg='cyan', bold=True)

    # Proper pluralization for total
    if type_name.endswith('s'):
        plural_total = type_name + 'es'
    elif type_name == 'switch':
        plural_total = 'switches'
    else:
        plural_total = type_name + 's'

    click.echo(f"  Total {plural_total}: {total}")

    if len(model_counts) > 1 or product_key:
        click.echo()
        click.secho("Models:", fg='cyan', bold=True)
        for model in sorted(model_counts.keys()):
            count = model_counts[model]['count']
            product = model_counts[model]['product']
            plural = type_name if count == 1 else f"{type_name}s"

            if product:
                click.echo(f"  {model} ({product}): {count} {plural}")
            else:
                click.echo(f"  {model}: {count} {plural}")

    click.echo()
