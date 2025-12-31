"""Clone switch configuration from one switch to another.

Commands for copying button configuration structure from an existing switch to a new one.
"""

import click
from core.controller import HueController


@click.command()
<parameter name="source_switch">SOURCE_SWITCH