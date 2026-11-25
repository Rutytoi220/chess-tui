"""Post-game / Share & Export modal screen for copying PGN/FEN, saving files, and opening review links."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Label, Static

from chess_tui.engine.game_state import GameMode
from chess_tui.tui.screens.base import VimModalScreen

if TYPE_CHECKING:
    from chess_tui.tui.app import ChessTuiApp


class ShareScreen(VimModalScreen):
    """Interactive modal to export PGN/FEN, copy share links, open Game Review, or rematch."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("ctrl+c", "app.quit", "Quit"),
    ]

    DEFAULT_CSS = """
    ShareScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.72);
    }
    #share_dialog {
        width: 90;
        max-width: 94%;
        max-height: 90%;
        border: heavy #eab308;
        background: #18181b;
        padding: 1 2;
    }
    .share_title {
        text-style: bold;
        color: #facc15;
        margin-bottom: 1;
    }
    .share_subtitle {
        color: #e4e4e7;
        margin-bottom: 1;
    }
    .share_row {
        height: auto;
        margin-bottom: 1;
    }
    .share_row Button {
        margin-right: 1;
        min-width: 14;
    }
    #share_status {
        color: #4ade80;
        text-style: bold;
        min-height: 1;
        margin-bottom: 1;
    }
    #pgn_scroll {
        height: 12;
        border: round #3f3f46;
        background: #0f0f12;
        padding: 0 1;
        margin-bottom: 1;
    }
    #pgn_preview {
        color: #d4d4d8;
    }
    #fen_preview {
        color: #a1a1aa;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        app: ChessTuiApp = self.app  # type: ignore[assignment]
        gs = app.game_state
        links = gs.share_links()
        has_chesscom_url = "game_url" in links
        is_live = gs.mode == GameMode.CHESSCOM_LIVE

        if gs.game_over:
            res_part = f" — {gs.result_text}" if gs.result_text else ""
            reason_part = f" ({gs.result_reason})" if gs.result_reason else ""
            title = f"GAME OVER{res_part}{reason_part}"
        else:
            title = "EXPORT & SHARE GAME"

        players = f"{gs.white_player.username} (White)  vs  {gs.black_player.username} (Black)"
        link_line = f"\nLink: {links['game_url']}" if has_chesscom_url else ""

        with Vertical(id="share_dialog"):
            yield Label(title, classes="share_title")
            yield Static(players + link_line, id="share_subtitle", classes="share_subtitle")
            yield Static("", id="share_status")

            with Horizontal(classes="share_row"):
                yield Button("Copy PGN", id="btn_copy_pgn", variant="success")
                yield Button("Save .pgn File", id="btn_save_pgn", variant="primary")
                yield Button("Copy FEN", id="btn_copy_fen")
                yield Button("Copy Link", id="btn_copy_url")

            with Horizontal(classes="share_row"):
                if has_chesscom_url:
                    yield Button("Open Chess.com Review", id="btn_open_review", variant="warning")
                yield Button("Lichess Analysis", id="btn_open_lichess")
                if is_live or app.active_username:
                    yield Button("Fetch Official PGN", id="btn_fetch_pubapi")

            if is_live:
                with Horizontal(classes="share_row"):
                    yield Button("Rematch", id="btn_rematch", variant="success")
                    yield Button("New Game", id="btn_new_game", variant="primary")
                    yield Button("Close", id="btn_close")
            else:
                with Horizontal(classes="share_row"):
                    yield Button("Close", id="btn_close")

            yield Static(f"FEN: {gs.export_fen()}", id="fen_preview")
            with VerticalScroll(id="pgn_scroll"):
                yield Static(gs.export_pgn(), id="pgn_preview")

    def _set_feedback(self, message: str) -> None:
        self.query_one("#share_status", Static).update(message)

    def _refresh_preview(self) -> None:
        app: ChessTuiApp = self.app  # type: ignore[assignment]
        gs = app.game_state
        links = gs.share_links()
        players = f"{gs.white_player.username} (White)  vs  {gs.black_player.username} (Black)"
        link_line = f"\nLink: {links['game_url']}" if "game_url" in links else ""
        self.query_one("#share_subtitle", Static).update(players + link_line)
        self.query_one("#fen_preview", Static).update(f"FEN: {gs.export_fen()}")
        self.query_one("#pgn_preview", Static).update(gs.export_pgn())

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        app: ChessTuiApp = self.app  # type: ignore[assignment]
        bid = event.button.id

        if bid == "btn_copy_pgn":
            pgn = app.game_state.export_pgn()
            msg = app.copy_text(pgn, "PGN")
            self._set_feedback(msg)
        elif bid == "btn_save_pgn":
            _, msg = app.save_pgn_file()
            self._set_feedback(msg)
        elif bid == "btn_copy_fen":
            msg = app.copy_text(app.game_state.export_fen(), "FEN")
            self._set_feedback(msg)
        elif bid == "btn_copy_url":
            links = app.game_state.share_links()
            url = links.get("game_url") or links["lichess_analysis_url"]
            label = "Chess.com game link" if "game_url" in links else "Lichess analysis link"
            msg = app.copy_text(url, label)
            self._set_feedback(msg)
        elif bid == "btn_open_review":
            _, msg = app.open_game_in_browser(review=True)
            self._set_feedback(msg)
        elif bid == "btn_open_lichess":
            _, msg = app.open_game_in_browser(lichess=True)
            self._set_feedback(msg)
        elif bid == "btn_fetch_pubapi":
            self._set_feedback("Fetching latest completed game PGN from Chess.com PubAPI...")
            ok, msg = await app.fetch_latest_pubapi_pgn()
            if ok:
                self._refresh_preview()
            self._set_feedback(msg)
        elif bid == "btn_rematch":
            await app._trigger_bridge_action("rematch")
            self.dismiss(None)
        elif bid == "btn_new_game":
            await app._trigger_bridge_action("new_game")
            self.dismiss(None)
        elif bid == "btn_close":
            self.dismiss(None)
