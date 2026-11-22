"""Chess.com PubAPI Profile, Ratings & Game Archive Explorer modal."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, DataTable, Input, Label, Static

from chess_tui.chesscom.pubapi import ArchivedGame
from chess_tui.tui.screens.base import VimModalScreen

if TYPE_CHECKING:
    from chess_tui.tui.app import ChessTuiApp


class ArchiveScreen(VimModalScreen):
    """Look up any Chess.com player's ratings and replay their archived games in the TUI."""

    DEFAULT_CSS = """
    ArchiveScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.72);
    }
    ArchiveScreen #archive_dialog {
        width: 92;
        height: 36;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    ArchiveScreen .title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    ArchiveScreen .row {
        height: auto;
        margin-bottom: 1;
    }
    ArchiveScreen Input {
        width: 1fr;
        margin-right: 1;
    }
    ArchiveScreen Button {
        margin-right: 1;
    }
    ArchiveScreen #profile_box {
        height: 4;
        background: $panel;
        padding: 0 1;
        margin-bottom: 1;
    }
    ArchiveScreen #games_table {
        height: 1fr;
        margin-bottom: 1;
    }
    ArchiveScreen #arch_status {
        height: 1;
        color: $warning;
    }
    """

    BINDINGS = [("escape", "dismiss_modal", "Close")]

    def __init__(self, initial_username: str = "") -> None:
        super().__init__()
        self._initial_username = initial_username
        self._games: list[ArchivedGame] = []

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)

    def compose(self) -> ComposeResult:
        tui: ChessTuiApp = self.app  # type: ignore[assignment]
        default_user = self._initial_username
        if not default_user and tui.active_account_alias:
            acc = tui.account_manager.get(tui.active_account_alias)
            if acc and acc.username:
                default_user = acc.username
        if not default_user:
            default_user = "hikaru"

        with Container(id="archive_dialog"):
            yield Label("CHESS.COM PLAYER STATS & GAME ARCHIVE EXPLORER", classes="title")
            with Horizontal(classes="row"):
                yield Input(value=default_user, id="user_input", placeholder="Chess.com username...")
                yield Button("Lookup Player", id="btn_lookup", variant="primary")
                yield Button("Replay Selected Game", id="btn_replay", variant="success")
                yield Button("Close [Esc]", id="btn_close")
            yield Static("Enter any Chess.com username to view ratings and recent games.", id="profile_box")
            yield DataTable(id="games_table", cursor_type="row")
            yield Static("", id="arch_status")

    def on_mount(self) -> None:
        table = self.query_one("#games_table", DataTable)
        table.add_columns("#", "Format", "White", "Black", "Result")
        super().on_mount()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        tui: ChessTuiApp = self.app  # type: ignore[assignment]
        bid = event.button.id
        status = self.query_one("#arch_status", Static)

        if bid == "btn_close":
            self.dismiss(None)
            return

        if bid == "btn_lookup":
            username = self.query_one("#user_input", Input).value.strip()
            if not username:
                status.update("Enter a Chess.com username.")
                return
            status.update(f"Fetching {username} from api.chess.com...")
            try:
                profile = await tui.pubapi.get_player(username)
                stats = await tui.pubapi.get_stats(username)
                archives = await tui.pubapi.get_archives(username)
                games: list[ArchivedGame] = []
                if archives:
                    games = await tui.pubapi.get_archive_games(archives[-1], limit=30)
                self._games = games

                def fmt_stat(label: str, rec) -> str:
                    return f"{label}: {rec.rating} ({rec.wins}W/{rec.losses}L)" if rec else f"{label}: —"

                title_pfx = f"[{profile.title}] " if profile.title else ""
                summary = (
                    f"{title_pfx}{profile.username}  |  Country: {profile.country or 'N/A'}  |  Followers: {profile.followers}\n"
                    f"{fmt_stat('Bullet', stats.bullet)}   {fmt_stat('Blitz', stats.blitz)}   "
                    f"{fmt_stat('Rapid', stats.rapid)}   {fmt_stat('Daily', stats.daily)}"
                )
                self.query_one("#profile_box", Static).update(summary)

                table = self.query_one("#games_table", DataTable)
                table.clear()
                for idx, g in enumerate(games):
                    table.add_row(
                        str(idx + 1),
                        g.time_class,
                        f"{g.white_username} ({g.white_rating})",
                        f"{g.black_username} ({g.black_rating})",
                        f"{g.white_result} / {g.black_result}",
                        key=str(idx),
                    )
                status.update(f"Loaded {len(games)} recent games for {profile.username}.")
            except Exception as exc:
                status.update(f"Lookup error: {exc}")
            return

        if bid == "btn_replay":
            table = self.query_one("#games_table", DataTable)
            if table.row_count == 0 or table.cursor_row is None:
                status.update("Select a game first.")
                return
            row_key, _ = table.coordinate_to_cell_key((table.cursor_row, 0))
            idx = int(str(row_key.value))
            game = self._games[idx]
            ok, msg = tui.load_archived_game(game)
            if ok:
                self.dismiss(None)
            else:
                status.update(msg)
