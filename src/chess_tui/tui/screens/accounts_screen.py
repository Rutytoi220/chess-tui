"""Multi-account Chess.com session & browser bridge management modal."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Button, DataTable, Input, Label, Static

from chess_tui import get_extension_dir
from chess_tui.tui.screens.base import VimModalScreen

if TYPE_CHECKING:
    from chess_tui.tui.app import ChessTuiApp


class AccountsScreen(VimModalScreen):
    """Manage multiple Chess.com accounts with isolated visible browser logins."""

    DEFAULT_CSS = """
    AccountsScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.72);
    }
    AccountsScreen #accounts_dialog {
        width: 88;
        height: 36;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    AccountsScreen .title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    AccountsScreen .hint_box {
        background: $panel;
        padding: 1;
        margin-bottom: 1;
    }
    AccountsScreen #accounts_table {
        height: 10;
        margin-bottom: 1;
    }
    AccountsScreen .row {
        height: auto;
        margin-bottom: 1;
        align: left middle;
    }
    AccountsScreen Input {
        width: 1fr;
        margin-right: 1;
    }
    AccountsScreen Button {
        margin-right: 1;
    }
    AccountsScreen #acc_feedback {
        height: 2;
        color: $warning;
    }
    """

    BINDINGS = [("escape", "dismiss_modal", "Close")]

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)

    def compose(self) -> ComposeResult:
        tui: ChessTuiApp = self.app  # type: ignore[assignment]
        ext_path = get_extension_dir()
        ws_port = tui.config.bridge.extension_ws_port
        ws_clients = tui.ws_bridge.client_count

        with Container(id="accounts_dialog"):
            yield Label("CHESS.COM MULTI-ACCOUNT LOGIN & BRIDGE", classes="title")
            with VerticalScroll():
                yield Static(
                    "Each account gets an isolated Chromium profile directory so you can stay logged into\n"
                    "multiple Chess.com accounts at once. Sign in directly in the visible browser window\n"
                    "(supports passwords, 2FA, Google/Apple SSO, and any verification prompt).\n"
                    f"Extension WS Bridge: ws://127.0.0.1:{ws_port} ({ws_clients} connected) | Folder: {ext_path}",
                    classes="hint_box",
                )
                yield DataTable(id="accounts_table", cursor_type="row")

                with Horizontal(classes="row"):
                    yield Input(id="alias_input", placeholder="New account alias (e.g. main, alt, bullet)")
                    yield Button("Add & Launch Login", id="btn_add_login", variant="success")
                    yield Button("Add Only", id="btn_add_only")

                with Horizontal(classes="row"):
                    yield Button("Connect / Switch Selected", id="btn_connect", variant="primary")
                    yield Button("Open Play Online", id="btn_nav_play")
                    yield Button("Open Computer", id="btn_nav_bot")
                    yield Button("Remove Selected", id="btn_remove", variant="error")
                    yield Button("Close [Esc]", id="btn_close")

                yield Static("", id="acc_feedback")

    def on_mount(self) -> None:
        table = self.query_one("#accounts_table", DataTable)
        table.add_columns("Alias", "Chess.com User", "CDP Port", "Browser Status", "Active")
        self._reload_table()
        super().on_mount()

    def _reload_table(self) -> None:
        tui: ChessTuiApp = self.app  # type: ignore[assignment]
        table = self.query_one("#accounts_table", DataTable)
        table.clear()
        for acc in tui.account_manager.list_accounts():
            alive = "RUNNING" if tui.account_manager.is_cdp_alive(acc) else "Stopped"
            is_cur = "● ACTIVE" if tui.active_account_alias == acc.alias else ""
            table.add_row(
                acc.alias,
                acc.username or "(sign in via browser)",
                str(acc.cdp_port),
                alive,
                is_cur,
                key=acc.alias,
            )

    def _selected_alias(self) -> str | None:
        table = self.query_one("#accounts_table", DataTable)
        if table.row_count == 0 or table.cursor_row is None:
            return None
        row_key, _ = table.coordinate_to_cell_key((table.cursor_row, 0))
        return str(row_key.value)

    def _set_feedback(self, text: str) -> None:
        self.query_one("#acc_feedback", Static).update(text)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        tui: ChessTuiApp = self.app  # type: ignore[assignment]
        bid = event.button.id

        if bid == "btn_close":
            self.dismiss(None)
            return

        if bid in ("btn_add_login", "btn_add_only"):
            alias = self.query_one("#alias_input", Input).value.strip()
            if not alias:
                existing = {a.alias for a in tui.account_manager.list_accounts()}
                alias = "main"
                idx = 2
                while alias in existing:
                    alias = f"account{idx}"
                    idx += 1
            try:
                acc = tui.account_manager.add_account(alias)
            except ValueError as exc:
                self._set_feedback(str(exc))
                return
            self.query_one("#alias_input", Input).value = ""
            if bid == "btn_add_login":
                _, msg = await tui.connect_account(acc.alias, start_url="https://www.chess.com/login")
                self._set_feedback(msg)
            else:
                self._set_feedback(f"Added account profile '{acc.alias}' on port {acc.cdp_port}.")
            self._reload_table()
            return

        selected = self._selected_alias()
        if not selected:
            self._set_feedback("Select an account from the table first.")
            return

        if bid == "btn_connect":
            _, msg = await tui.connect_account(selected, start_url="https://www.chess.com/play/online")
            self._set_feedback(msg)
            self._reload_table()
        elif bid == "btn_nav_play":
            _, msg = await tui.connect_account(selected, start_url="https://www.chess.com/play/online", force_nav=True)
            self._set_feedback(msg)
            self._reload_table()
        elif bid == "btn_nav_bot":
            _, msg = await tui.connect_account(selected, start_url="https://www.chess.com/play/computer", force_nav=True)
            self._set_feedback(msg)
            self._reload_table()
        elif bid == "btn_remove":
            tui.account_manager.remove_account(selected, delete_profile_dir=False)
            self._set_feedback(f"Removed account '{selected}' (profile dir preserved on disk).")
            self._reload_table()
