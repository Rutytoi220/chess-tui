"""Tests for the chess-tui CLI subcommands."""

from __future__ import annotations

from pathlib import Path

from chess_tui.__main__ import main


def test_cli_account_lifecycle_and_config(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setenv("CHESS_TUI_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("CHESS_TUI_DATA_DIR", str(tmp_path / "data"))

    assert main(["config", "init"]) == 0
    assert (tmp_path / "cfg" / "config.toml").exists()

    assert main(["config", "themes"]) == 0
    out = capsys.readouterr().out
    assert "chesscom-green" in out
    assert "catppuccin-mocha" in out

    assert main(["account", "add", "my_alt"]) == 0
    assert main(["account", "list"]) == 0
    out = capsys.readouterr().out
    assert "my_alt" in out

    assert main(["account", "remove", "my_alt", "--purge"]) == 0
    assert main(["doctor"]) == 0
