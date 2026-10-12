"""
core package - Core desktop system integration for Sentinel AI.
"""
from .autostart import (
    disable_autostart,
    enable_autostart,
    is_autostart_enabled,
    toggle_autostart,
)
from .game_mode import (
    GameModeManager,
    GamingSessionSummary,
    KNOWN_GAME_PROCESSES,
)
from .utilities import (
    clean_ram,
    clean_disk_temp,
    relaunch_as_admin,
)
from .driver_manager import DriverManager

__all__ = [
    "is_autostart_enabled",
    "enable_autostart",
    "disable_autostart",
    "toggle_autostart",
    "GameModeManager",
    "GamingSessionSummary",
    "KNOWN_GAME_PROCESSES",
    "clean_ram",
    "clean_disk_temp",
    "relaunch_as_admin",
    "DriverManager",
]
