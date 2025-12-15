"""Type definitions for Hue Backup CLI.

This module provides TypedDict definitions for structured data types used across
the application, improving type safety and IDE autocompletion.
"""

from typing import TypedDict


class AuthCredentials(TypedDict):
    """Authentication credentials for Hue Bridge."""
    bridge_ip: str
    api_token: str


class DiscoveredBridge(TypedDict):
    """Bridge information from N-UPnP discovery."""
    id: str
    internalipaddress: str
    name: str | None


class SwitchBehaviour(TypedDict):
    """Switch behaviour lookup result.

    Returned by find_switch_behaviour() instead of a tuple for better type safety.
    """
    behaviour: dict
    device_name: str
    device: dict
