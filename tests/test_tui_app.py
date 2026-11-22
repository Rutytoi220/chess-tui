"""End-to-end Textual async pilot tests for Vimium moves, customization, and modals."""

from __future__ import annotations

from pathlib import Path

import chess

from chess_tui.chesscom.accounts import AccountManager
from chess_tui.config.manager import ConfigManager
from chess_tui.tui.app import ChessTuiApp
from chess_tui.tui.screens import (
    AccountsScreen,
    ArchiveScreen,
    HelpScreen,
    PlayScreen,
    SettingsScreen,
)
from chess_tui.tui.widgets import BoardWidget


def _make_app(tmp_path: Path) -> ChessTuiApp:
    cfg_mgr = ConfigManager(config_path=tmp_path / "config.toml")
    cfg_mgr.config.bridge.extension_auto_start = False
    cfg_mgr.config.hints.mode = "static"
    cfg_mgr.config.hints.alphabet = "ABCDEFGH"
    cfg_mgr.config.hints.custom_square_map = {"e2": "AB", "e4": "BC"}
    cfg_mgr.save()

    acc_mgr = AccountManager(data_dir=tmp_path / "data")
    return ChessTuiApp(config_manager=cfg_mgr, account_manager=acc_mgr)


async def test_vimium_ab_then_bc_makes_chess_move(tmp_path: Path):
    app = _make_app(tmp_path)
    async with app.run_test(size=(120, 42)) as pilot:
        await pilot.pause()
        # Verify AB maps to e2 in stage 1
        assert app.active_hints[chess.E2] == "AB"

        # Type "AB" to select e2
        await pilot.press("a", "b")
        await pilot.pause()
        assert app.selected_square == chess.E2
        assert app.active_hints[chess.E4] == "BC"

        # Type "BC" to move e2 -> e4!
        await pilot.press("b", "c")
        await pilot.pause()
        assert app.selected_square is None
        assert app.game_state.move_history_san == ["e4"]
        assert app.game_state.board.piece_at(chess.E4) == chess.Piece(chess.PAWN, chess.WHITE)


async def test_vimium_dynamic_mode_and_escape_cancel(tmp_path: Path):
    app = _make_app(tmp_path)
    app.config.hints.mode = "dynamic"
    app.config.hints.alphabet = "ASDFGHJKL"
    async with app.run_test(size=(120, 42)) as pilot:
        await pilot.pause()
        e2_hint = app.active_hints[chess.E2]
        await pilot.press(e2_hint[0].lower())
        await pilot.pause()
        assert app.hint_buffer == e2_hint[0]

        await pilot.press("escape")
        await pilot.pause()
        assert app.hint_buffer == ""
        assert app.selected_square is None


async def test_vim_commands_customize_theme_pieces_and_zen(tmp_path: Path):
    app = _make_app(tmp_path)
    async with app.run_test(size=(120, 42)) as pilot:
        await pilot.pause()
        await app.run_vim_command("theme catppuccin-mocha")
        await app.run_vim_command("pieces block")
        await app.run_vim_command("size large")
        await app.run_vim_command("set layout.zen_mode true")
        await pilot.pause()

        assert app.config.theme == "catppuccin-mocha"
        assert app.config.board.piece_style == "block"
        assert app.config.board.square_size == "large"
        assert app.config.layout.zen_mode is True


async def test_san_command_move_and_modals_open_cleanly(tmp_path: Path):
    app = _make_app(tmp_path)
    async with app.run_test(size=(120, 42)) as pilot:
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        for ch in "e4":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        assert app.game_state.move_history_san == ["e4"]

        for key, screen_cls in (
            ("ctrl+a", AccountsScreen),
            ("ctrl+s", SettingsScreen),
            ("ctrl+p", PlayScreen),
            ("ctrl+g", ArchiveScreen),
            ("?", HelpScreen),
        ):
            await pilot.press(key)
            await pilot.pause()
            assert isinstance(app.screen, screen_cls)
            await pilot.press("escape")
            await pilot.pause()
            assert len(app.screen_stack) == 1


async def test_mouse_click_square_and_promotion_choice(tmp_path: Path):
    app = _make_app(tmp_path)
    async with app.run_test(size=(120, 42)) as pilot:
        await pilot.pause()
        board_w = app.query_one("#board_widget", BoardWidget)
        board_w.post_message(BoardWidget.SquareClicked(chess.E2))
        await pilot.pause()
        assert app.selected_square == chess.E2

        board_w.post_message(BoardWidget.SquareClicked(chess.E4))
        await pilot.pause()
        assert app.game_state.move_history_san == ["e4"]

        # Load pawn promotion position and choose Knight ('N') via Vimium hint
        await app.run_vim_command("fen 4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
        await pilot.pause()
        board_w.post_message(BoardWidget.SquareClicked(chess.A7))
        await pilot.pause()
        board_w.post_message(BoardWidget.SquareClicked(chess.A8))
        await pilot.pause()
        assert app.pending_promotion == (chess.A7, chess.A8)

        await pilot.press("n")
        await pilot.pause()
        assert app.pending_promotion is None
        assert app.game_state.board.piece_at(chess.A8) == chess.Piece(chess.KNIGHT, chess.WHITE)


async def test_settings_modal_saves_customizations(tmp_path: Path):
    app = _make_app(tmp_path)
    async with app.run_test(size=(120, 42)) as pilot:
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)

        from textual.widgets import Input, Select

        app.screen.query_one("#hints_alphabet", Input).value = "ASDFGHJKL"
        app.screen.query_one("#theme_select", Select).value = "tokyo-night"
        app.screen.query_one("#board_piece_style", Select).value = "block"
        app.screen.action_save_and_close()
        await pilot.pause()

        assert len(app.screen_stack) == 1
        assert app.config.hints.alphabet == "ASDFGHJKL"
        assert app.config.theme == "tokyo-night"
        assert app.config.board.piece_style == "block"


async def test_accounts_modal_adds_account_profile(tmp_path: Path):
    app = _make_app(tmp_path)
    async with app.run_test(size=(120, 42)) as pilot:
        await pilot.pause()
        await pilot.press("ctrl+a")
        await pilot.pause()
        assert isinstance(app.screen, AccountsScreen)

        from textual.widgets import Button, Input

        app.screen.query_one("#alias_input", Input).value = "speedrun"
        app.screen.query_one("#btn_add_only", Button).press()
        await pilot.pause()

        assert app.account_manager.get("speedrun") is not None
        await pilot.press("escape")
        await pilot.pause()
        assert len(app.screen_stack) == 1
