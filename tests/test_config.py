"""Tests for configuration loading, saving, dot-path mutations, presets, and themes."""

from __future__ import annotations

from pathlib import Path

from chess_tui.config.manager import ConfigManager
from chess_tui.config.themes import THEMES, resolve_theme


def test_config_roundtrip_and_dot_path_set(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    mgr = ConfigManager(config_path=cfg_path)
    mgr.ensure_exists()
    assert cfg_path.exists()

    mgr.set_by_path("theme", "catppuccin-mocha")
    mgr.set_by_path("hints.alphabet", "ASDFGHJKL")
    mgr.set_by_path("hints.min_length", "1")
    mgr.set_by_path("layout.zen_mode", "true")

    reloaded = ConfigManager(config_path=cfg_path)
    assert reloaded.config.theme == "catppuccin-mocha"
    assert reloaded.config.hints.alphabet == "ASDFGHJKL"
    assert reloaded.config.hints.min_length == 1
    assert reloaded.config.layout.zen_mode is True


def test_presets_save_and_load(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    mgr = ConfigManager(config_path=cfg_path)
    mgr.set_by_path("theme", "dracula")
    mgr.set_by_path("board.piece_style", "block")
    mgr.save_preset("my-preset")

    mgr.set_by_path("theme", "nord")
    assert mgr.config.theme == "nord"
    assert "my-preset" in mgr.list_presets()

    mgr.load_preset("my-preset")
    assert mgr.config.theme == "dracula"
    assert mgr.config.board.piece_style == "block"


def test_theme_resolution_and_overrides():
    assert len(THEMES) >= 14
    pal = resolve_theme("tokyo-night", {"hint_bg": "#123456"})
    assert pal.name == "tokyo-night"
    assert pal.hint_bg == "#123456"
    assert pal.light_square_bg == THEMES["tokyo-night"].light_square_bg
