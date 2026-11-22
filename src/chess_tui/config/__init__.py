"""Configuration package for chess-tui."""

from .manager import ConfigManager, default_config_dir, default_data_dir
from .schema import (
    BoardConfig,
    BridgeConfig,
    ChessTuiConfig,
    HintConfig,
    InputConfig,
    LayoutConfig,
)
from .themes import (
    BLOCK_SPRITES_5X3,
    BLOCK_SPRITES_7X3,
    PIECE_GLYPHS,
    THEMES,
    ThemePalette,
    resolve_theme,
)

__all__ = [
    "BLOCK_SPRITES_5X3",
    "BLOCK_SPRITES_7X3",
    "PIECE_GLYPHS",
    "THEMES",
    "BoardConfig",
    "BridgeConfig",
    "ChessTuiConfig",
    "ConfigManager",
    "HintConfig",
    "InputConfig",
    "LayoutConfig",
    "ThemePalette",
    "default_config_dir",
    "default_data_dir",
    "resolve_theme",
]
