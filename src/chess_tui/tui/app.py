"""Main Textual application for chess-tui."""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import Any

import chess
import chess.pgn
from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Static

from chess_tui.chesscom.accounts import AccountManager
from chess_tui.chesscom.cdp_bridge import CdpBridge
from chess_tui.chesscom.pubapi import ArchivedGame, ChessComPubApi
from chess_tui.chesscom.ws_bridge import ExtensionWsBridge
from chess_tui.config.manager import ConfigManager
from chess_tui.config.schema import ChessTuiConfig
from chess_tui.config.themes import THEMES, ThemePalette, resolve_theme
from chess_tui.engine.game_state import GameMode, GameState, PlayerInfo
from chess_tui.engine.hints import HintEngine
from chess_tui.engine.uci import LocalUciEngine, find_uci_engine
from chess_tui.tui.screens import (
    AccountsScreen,
    ArchiveScreen,
    HelpScreen,
    PlayScreen,
    SettingsScreen,
)
from chess_tui.tui.widgets import BoardWidget, CommandBar, SidebarWidget


KEY_ALIASES: dict[str, str] = {
    "colon": ":",
    "slash": "/",
    "question_mark": "?",
    "escape": "escape",
    "backspace": "backspace",
}


class ChessTuiApp(App[None]):
    """Customizable Chess.com TUI with Vimium-style move hints."""

    CSS_PATH = "styles.tcss"
    TITLE = "chess-tui"
    ENABLE_COMMAND_PALETTE = False

    def __init__(
        self,
        *,
        config_manager: ConfigManager | None = None,
        account_manager: AccountManager | None = None,
        initial_account: str = "",
        initial_puzzle: bool = False,
        initial_puzzle_random: bool = False,
    ) -> None:
        super().__init__()
        self.config_manager = config_manager or ConfigManager()
        self.config: ChessTuiConfig = self.config_manager.config
        self.account_manager = account_manager or AccountManager()
        self.pubapi = ChessComPubApi(user_agent=self.config.bridge.pubapi_user_agent)

        self.theme_palette: ThemePalette = resolve_theme(
            self.config.theme, self.config.theme_overrides
        )
        self.game_state = GameState()
        self.hint_engine = HintEngine(self.config.hints)

        self.manual_flip_offset: bool = False
        self.selected_square: chess.Square | None = None
        self.cursor_square: chess.Square | None = None
        self.hint_buffer: str = ""
        self.active_hints: dict[chess.Square, str] = {}
        self.pending_promotion: tuple[chess.Square, chess.Square] | None = None
        self._confirm_resign_pending: bool = False
        self._status_msg: str = "Type a Vimium hint tag (e.g. AB) to select a piece • ? for help"

        # Bridges & optional offline UCI engine
        self.active_account_alias: str = ""
        self.active_username: str = ""
        self.cdp_bridge: CdpBridge | None = None
        self.ws_bridge = ExtensionWsBridge(
            host=self.config.bridge.extension_ws_host,
            port=self.config.bridge.extension_ws_port,
        )
        self.uci_engine: LocalUciEngine | None = None

        self._initial_account = initial_account or self.config.default_account
        self._initial_puzzle = initial_puzzle
        self._initial_puzzle_random = initial_puzzle_random
        self._last_turn_seen: chess.Color = self.game_state.board.turn

    def compose(self) -> ComposeResult:
        yield Static(id="top_bar")
        with Container(id="main_area"):
            yield BoardWidget(
                self.game_state,
                self.theme_palette,
                self.config.board,
                self.config.hints,
                id="board_widget",
            )
            yield SidebarWidget(
                self.game_state,
                self.theme_palette,
                self.config.layout,
                self.config.hints,
                id="sidebar_widget",
            )
        yield CommandBar(self.theme_palette, id="command_bar")

    async def on_mount(self) -> None:
        self.apply_config()
        self.recompute_hints()
        self.sync_ui()
        self.query_one("#board_widget", BoardWidget).focus()

        # Start Extension WS bridge automatically if enabled
        if self.config.bridge.extension_auto_start:
            try:
                await self.ws_bridge.start(on_state=self._on_bridge_state)
                self._log(
                    f"Extension WS listening on ws://{self.config.bridge.extension_ws_host}:{self.config.bridge.extension_ws_port}"
                )
            except OSError as exc:
                self._log(f"Extension WS port busy ({exc})")

        if self._initial_puzzle:
            await self.start_daily_puzzle(random=self._initial_puzzle_random)
        elif self._initial_account:
            _, msg = await self.connect_account(self._initial_account)
            self._set_status(msg)
            self._log(msg)

    async def on_unmount(self) -> None:
        if self.cdp_bridge is not None:
            await self.cdp_bridge.disconnect()
        await self.ws_bridge.stop()
        if self.uci_engine is not None:
            await self.uci_engine.stop()

    def effective_flipped(self) -> bool:
        """Compute board orientation from config, live player color, and manual flip."""
        pref = self.config.board.orientation.lower().strip()
        if pref == "white":
            base = False
        elif pref == "black":
            base = True
        else:
            base = self.game_state.player_color == chess.BLACK
        return (not base) if self.manual_flip_offset else base

    def apply_config(self) -> None:
        """Apply active ChessTuiConfig immediately across all widgets and styles."""
        self.theme_palette = resolve_theme(self.config.theme, self.config.theme_overrides)
        self.hint_engine = HintEngine(self.config.hints)
        self.pubapi.user_agent = self.config.bridge.pubapi_user_agent
        t = self.theme_palette

        self.screen.styles.background = t.app_bg
        self.screen.styles.color = t.text_fg

        top_bar = self.query_one("#top_bar", Static)
        top_bar.styles.background = t.panel_bg
        top_bar.styles.color = t.text_fg
        top_bar.styles.display = "block" if (self.config.layout.show_header and not self.config.layout.zen_mode) else "none"

        sidebar = self.query_one("#sidebar_widget", SidebarWidget)
        sidebar.styles.background = t.surface_bg
        sidebar.styles.width = self.config.layout.sidebar_width
        pos = self.config.layout.sidebar_position.lower().strip()
        if self.config.layout.zen_mode or pos == "none":
            sidebar.styles.display = "none"
        else:
            sidebar.styles.display = "block"
            sidebar.styles.dock = "left" if pos == "left" else "right"

        cmd_bar = self.query_one("#command_bar", CommandBar)
        cmd_bar.set_theme(t)
        cmd_bar.styles.display = "block" if self.config.layout.show_footer else "none"

        self.recompute_hints()
        self.sync_ui()

    def recompute_hints(self) -> None:
        """Recompute Vimium square hints for current board and selection stage."""
        premove = self.game_state.is_premove_allowed()
        if self.game_state.mode == GameMode.CHESSCOM_ARCHIVE:
            self.active_hints = {}
            return
        if not self.game_state.is_users_turn() and not premove:
            self.active_hints = {}
            return
        self.active_hints = self.hint_engine.compute_hints(
            self.game_state.board,
            self.selected_square,
            flipped=self.effective_flipped(),
            premove_mode=premove,
            player_color=self.game_state.player_color,
        )

    def _connection_label(self) -> str:
        if self.game_state.mode == GameMode.CHESSCOM_PUZZLE:
            return "Chess.com Daily Puzzle (PubAPI)"
        if self.game_state.mode == GameMode.CHESSCOM_ARCHIVE:
            return "Chess.com Game Replay (PubAPI)"
        if self.cdp_bridge and self.cdp_bridge.connected:
            user = self.active_username or self.active_account_alias
            return f"LIVE CDP • {user}"
        if self.ws_bridge.client_count > 0:
            user = self.active_username or "Browser Tab"
            return f"LIVE EXT • {user}"
        if self.game_state.mode == GameMode.LOCAL_ENGINE:
            return f"OFFLINE • vs UCI Engine (Lv {self.config.bridge.uci_skill_level})"
        return "OFFLINE • Local 2-Player"

    def sync_ui(self) -> None:
        """Refresh top bar, board widget, sidebar, and command bar."""
        if not self.is_mounted:
            return
        t = self.theme_palette
        flipped = self.effective_flipped()

        top = Text()
        top.append(" ♞ CHESS-TUI ", Style(color=t.hint_fg, bgcolor=t.accent_fg, bold=True))
        top.append(f"  {self._connection_label()}", Style(color=t.text_fg, bold=True))
        top.append(f"  │  Theme: {self.config.theme}", Style(color=t.muted_fg))
        top.append(f"  │  Hints: {self.config.hints.mode}", Style(color=t.muted_fg))
        if self.active_account_alias:
            top.append(f"  │  Acct: {self.active_account_alias}", Style(color=t.success_fg, bold=True))
        self.query_one("#top_bar", Static).update(top)

        self.query_one("#board_widget", BoardWidget).update_state(
            game_state=self.game_state,
            theme=t,
            board_config=self.config.board,
            hint_config=self.config.hints,
            flipped=flipped,
            selected_square=self.selected_square,
            cursor_square=self.cursor_square,
            active_hints=self.active_hints,
            hint_buffer=self.hint_buffer,
            pending_promotion=self.pending_promotion,
        )

        self.query_one("#sidebar_widget", SidebarWidget).update_state(
            game_state=self.game_state,
            theme=t,
            layout_config=self.config.layout,
            hint_config=self.config.hints,
            flipped=flipped,
            connection_label=self._connection_label(),
        )

        sel_lbl = chess.square_name(self.selected_square).upper() if self.selected_square is not None else ""
        self.query_one("#command_bar", CommandBar).update_status(
            hint_mode=self.config.hints.mode if self.config.hints.enabled else "off",
            hint_buffer=self.hint_buffer,
            selected_label=sel_lbl,
            message=self._status_msg,
        )

    def _set_status(self, message: str) -> None:
        self._status_msg = message
        if self.is_mounted:
            self.query_one("#command_bar", CommandBar).update_status(message=message)

    def _log(self, message: str) -> None:
        if self.is_mounted:
            self.query_one("#sidebar_widget", SidebarWidget).add_log(message)

    def _clear_selection(self) -> None:
        self.selected_square = None
        self.hint_buffer = ""
        self.pending_promotion = None
        self._confirm_resign_pending = False
        self.recompute_hints()
        self.sync_ui()

    # ------------------------------------------------------------------
    # Chess.com Bridges (Account CDP + Extension WS)
    # ------------------------------------------------------------------

    async def connect_account(
        self,
        alias: str,
        *,
        start_url: str = "https://www.chess.com/play/online",
        force_nav: bool = False,
    ) -> tuple[bool, str]:
        """Connect to or launch an isolated visible browser profile for `alias`."""
        acc = self.account_manager.get(alias)
        if acc is None:
            acc = self.account_manager.add_account(alias)

        ok, launch_msg = self.account_manager.launch_browser(
            acc,
            browser_binary=self.config.bridge.browser_binary,
            extra_args=self.config.bridge.browser_extra_args,
            start_url=start_url,
        )
        if not ok:
            return False, launch_msg

        if self.cdp_bridge is not None:
            await self.cdp_bridge.disconnect()

        bridge = CdpBridge(
            port=acc.cdp_port,
            poll_interval_ms=self.config.bridge.cdp_poll_interval_ms,
            move_method=self.config.bridge.move_dispatch_method,
            click_delay_ms=self.config.bridge.click_delay_ms,
        )
        # Retry briefly while freshly launched Chromium opens its CDP port
        last_err: Exception | None = None
        for _ in range(18):
            try:
                page_url = await bridge.connect(on_state=self._on_bridge_state)
                self.cdp_bridge = bridge
                self.active_account_alias = acc.alias
                self.active_username = acc.username
                self.config.default_account = acc.alias
                self.config_manager.save()
                if force_nav and start_url not in page_url:
                    await bridge.navigate(start_url)
                self._log(f"Connected CDP '{acc.alias}' ({page_url})")
                self.sync_ui()
                return True, f"Connected '{acc.alias}' on CDP port {acc.cdp_port}"
            except Exception as exc:
                last_err = exc
                await asyncio.sleep(0.35)

        return False, f"Launched browser, but CDP connection timed out ({last_err})"

    async def navigate_chesscom(self, url: str) -> bool:
        if self.cdp_bridge and self.cdp_bridge.connected:
            await self.cdp_bridge.navigate(url)
            self._log(f"Navigating browser -> {url}")
            return True
        if self.ws_bridge.client_count > 0:
            ok = await self.ws_bridge.navigate(url)
            if ok:
                self._log(f"Navigating extension tab -> {url}")
            return ok
        return False

    async def _on_bridge_state(self, snapshot: dict[str, Any]) -> None:
        """Handle live DOM state pushed from CDP or Browser Extension."""
        logged_user = str(snapshot.get("loggedInUser") or "").strip()
        if logged_user:
            self.active_username = logged_user
            if self.active_account_alias:
                self.account_manager.update_username(self.active_account_alias, logged_user)

        if snapshot.get("isLoginPage") and not snapshot.get("hasBoard"):
            self._set_status("Complete Chess.com login in the visible browser window...")
            self.sync_ui()
            return

        if not snapshot.get("hasBoard"):
            self._set_status(
                f"Browser connected ({logged_user or 'guest'}) — open a game on Chess.com or press Ctrl+P"
            )
            self.sync_ui()
            return

        changed = self.game_state.sync_from_bridge(snapshot)
        if changed:
            self.selected_square = None
            self.hint_buffer = ""
            self.pending_promotion = None
            if (
                self.config.layout.sound_bell
                and self.game_state.is_users_turn()
                and self.game_state.board.turn != self._last_turn_seen
            ):
                self.bell()
            self._last_turn_seen = self.game_state.board.turn
            self.recompute_hints()
        self.sync_ui()

    # ------------------------------------------------------------------
    # Offline / Puzzle / Archive Modes
    # ------------------------------------------------------------------

    def start_local_2p(self) -> None:
        self.game_state.reset_local(GameMode.LOCAL_2P, player_color=None)
        self._clear_selection()
        self._set_status("Started Local 2-Player game.")
        self._log("Started Local 2-Player game")

    async def start_local_uci(self) -> tuple[bool, str]:
        binary = find_uci_engine(self.config.bridge.uci_engine_path)
        if not binary:
            return False, "No UCI engine found (install 'stockfish' or set bridge.uci_engine_path)."
        if self.uci_engine is not None:
            await self.uci_engine.stop()
        self.uci_engine = LocalUciEngine(binary, skill_level=self.config.bridge.uci_skill_level)
        await self.uci_engine.start()
        self.game_state.reset_local(GameMode.LOCAL_ENGINE, player_color=chess.WHITE)
        self._clear_selection()
        self._set_status(f"Started Local game vs {Path(binary).name} (Skill {self.config.bridge.uci_skill_level})")
        self._log(f"Playing vs {Path(binary).name}")
        return True, "Started local UCI game"

    async def start_daily_puzzle(self, *, random: bool = False) -> tuple[bool, str]:
        try:
            puzzle = await self.pubapi.get_daily_puzzle(random=random)
            board = chess.Board(puzzle.fen)
        except Exception as exc:
            return False, f"Failed to fetch puzzle: {exc}"

        self.game_state.reset_local(GameMode.CHESSCOM_PUZZLE, player_color=board.turn)
        self.game_state.board = board
        self.game_state.puzzle_title = puzzle.title
        self.game_state.puzzle_solution = list(puzzle.solution_moves)
        self.game_state.puzzle_index = 0
        self.game_state.white_player = PlayerInfo(username="Puzzle (White)")
        self.game_state.black_player = PlayerInfo(username="Puzzle (Black)")
        self._clear_selection()
        side = "White" if board.turn == chess.WHITE else "Black"
        self._set_status(f"Puzzle: {puzzle.title} — {side} to move!")
        self._log(f"Loaded puzzle: {puzzle.title}")
        return True, "Loaded puzzle"

    def load_archived_game(self, archived: ArchivedGame) -> tuple[bool, str]:
        game = chess.pgn.read_game(io.StringIO(archived.pgn))
        if game is None:
            return False, "Failed to parse game PGN."
        initial_board = game.board()
        moves = list(game.mainline_moves())
        self.game_state.reset_local(GameMode.CHESSCOM_ARCHIVE, player_color=None)
        self.game_state.archive_initial_fen = initial_board.fen()
        self.game_state.archive_moves = moves
        self.game_state.archive_ply = 0
        self.game_state.board = initial_board
        self.game_state.white_player = PlayerInfo(
            username=archived.white_username, rating=str(archived.white_rating or "")
        )
        self.game_state.black_player = PlayerInfo(
            username=archived.black_username, rating=str(archived.black_rating or "")
        )
        self._clear_selection()
        self._set_status(
            f"Replay: {archived.white_username} vs {archived.black_username} — Use ←/→ or n/p"
        )
        self._log(f"Replaying {archived.white_username} vs {archived.black_username}")
        return True, "Loaded replay"

    def _step_archive(self, delta: int) -> None:
        if self.game_state.mode != GameMode.CHESSCOM_ARCHIVE:
            return
        target = max(0, min(len(self.game_state.archive_moves), self.game_state.archive_ply + delta))
        board = chess.Board(self.game_state.archive_initial_fen)
        san_list: list[str] = []
        last_mv: chess.Move | None = None
        for mv in self.game_state.archive_moves[:target]:
            san_list.append(board.san(mv))
            board.push(mv)
            last_mv = mv
        self.game_state.board = board
        self.game_state.move_history_san = san_list
        self.game_state.last_move = last_mv
        self.game_state.archive_ply = target
        self.sync_ui()

    def load_fen(self, fen: str) -> tuple[bool, str]:
        try:
            board = chess.Board(fen)
        except ValueError as exc:
            return False, f"Invalid FEN: {exc}"
        self.game_state.reset_local(GameMode.SANDBOX, player_color=None)
        self.game_state.board = board
        self._clear_selection()
        self._set_status("Loaded custom FEN position.")
        self._log("Loaded custom FEN")
        return True, "FEN loaded"

    # ------------------------------------------------------------------
    # Executing Moves (Vimium / Click / SAN / Cursor)
    # ------------------------------------------------------------------

    async def execute_move(
        self,
        from_sq: chess.Square,
        to_sq: chess.Square,
        promotion: chess.PieceType | None = None,
    ) -> None:
        """Execute a validated move locally or dispatch to live Chess.com bridge."""
        from_name = chess.square_name(from_sq)
        to_name = chess.square_name(to_sq)

        # Prompt for promotion piece if user hasn't picked one yet
        if promotion is None and self.game_state.needs_promotion_choice(from_sq, to_sq):
            self.pending_promotion = (from_sq, to_sq)
            self.hint_buffer = ""
            self._set_status("Choose promotion piece: Q (Queen), R (Rook), B (Bishop), N (Knight)")
            self.sync_ui()
            return

        # Live Chess.com Bridge mode
        if self.game_state.mode == GameMode.CHESSCOM_LIVE:
            promo_char = chess.piece_symbol(promotion).lower() if promotion else None
            if self.game_state.is_premove_allowed():
                self.game_state.premove = (from_sq, to_sq, promotion)
            else:
                # Validate legality locally before clicking browser
                test_mv = chess.Move(from_sq, to_sq, promotion=promotion)
                if test_mv not in self.game_state.board.legal_moves:
                    self._set_status(f"Illegal move: {from_name}->{to_name}")
                    self._clear_selection()
                    return

            msg = "No active Chess.com bridge"
            if self.cdp_bridge and self.cdp_bridge.connected:
                _, msg = await self.cdp_bridge.send_move(from_name, to_name, promo_char)
            elif self.ws_bridge.client_count > 0:
                _, msg = await self.ws_bridge.send_move(from_name, to_name, promo_char)

            self._set_status(msg)
            self._log(msg)
            self._clear_selection()
            return

        # Daily Puzzle validation mode
        if self.game_state.mode == GameMode.CHESSCOM_PUZZLE:
            candidate = chess.Move(from_sq, to_sq, promotion=promotion)
            if candidate not in self.game_state.board.legal_moves:
                self._set_status("Illegal puzzle move.")
                self._clear_selection()
                return
            san = self.game_state.board.san(candidate)
            sol = self.game_state.puzzle_solution
            idx = self.game_state.puzzle_index
            if idx < len(sol) and san.rstrip("+#") != sol[idx].rstrip("+#"):
                self._set_status(f"Incorrect ({san}) — try another move!")
                self._clear_selection()
                return
            self.game_state.apply_move(from_sq, to_sq, promotion=promotion)
            self.game_state.puzzle_index += 1
            self._log(f"Puzzle move: {san} ✓")

            # Auto-play opponent's puzzle response if more moves remain
            if self.game_state.puzzle_index < len(sol):
                reply_san = sol[self.game_state.puzzle_index]
                try:
                    reply_mv = self.game_state.board.parse_san(reply_san)
                    self.game_state.apply_move(
                        reply_mv.from_square, reply_mv.to_square, promotion=reply_mv.promotion
                    )
                    self.game_state.puzzle_index += 1
                except ValueError:
                    pass

            if self.game_state.puzzle_index >= len(sol):
                self._set_status(f"Puzzle Solved! ({self.game_state.puzzle_title})")
            else:
                self._set_status(f"Correct ({san})! Find the next move.")
            self._clear_selection()
            return

        # Local 2-Player / Sandbox / Local UCI Engine
        try:
            self.game_state.apply_move(from_sq, to_sq, promotion=promotion)
        except ValueError as exc:
            self._set_status(str(exc))
            self._clear_selection()
            return

        san_played = self.game_state.move_history_san[-1]
        self._set_status(f"Played {san_played}")
        self._log(f"Move: {san_played}")
        self._clear_selection()

        # Local UCI Engine reply (strictly offline only!)
        if (
            self.game_state.mode == GameMode.LOCAL_ENGINE
            and self.uci_engine is not None
            and not self.game_state.game_over
            and not self.game_state.is_users_turn()
        ):
            self._set_status("Engine thinking...")
            reply = await self.uci_engine.best_move(self.game_state.board)
            if reply is not None:
                self.game_state.apply_move(
                    reply.from_square, reply.to_square, promotion=reply.promotion
                )
                r_san = self.game_state.move_history_san[-1]
                self._set_status(f"Engine played {r_san}")
                self._log(f"Engine: {r_san}")
                self.recompute_hints()
                self.sync_ui()

    async def _handle_square_selection(self, sq: chess.Square) -> None:
        """Select source square or execute destination move for `sq`."""
        if self.selected_square is None:
            piece = self.game_state.board.piece_at(sq)
            if piece is None:
                return
            if not self.game_state.is_premove_allowed():
                has_legal = any(m.from_square == sq for m in self.game_state.board.legal_moves)
                if not has_legal:
                    return
            elif self.game_state.player_color is not None and piece.color != self.game_state.player_color:
                return

            self.selected_square = sq
            self.hint_buffer = ""
            self.recompute_hints()
            self._set_status(f"Selected {chess.square_name(sq).upper()} — type target hint or Esc")
            self.sync_ui()
            return

        if sq == self.selected_square:
            self._clear_selection()
            return

        # Clicking another friendly piece when it isn't a legal capture switches selection cleanly
        target_piece = self.game_state.board.piece_at(sq)
        is_legal_dest = any(
            m.from_square == self.selected_square and m.to_square == sq
            for m in self.game_state.board.legal_moves
        )
        if (
            not is_legal_dest
            and not self.game_state.is_premove_allowed()
            and target_piece is not None
            and target_piece.color == self.game_state.board.turn
            and any(m.from_square == sq for m in self.game_state.board.legal_moves)
        ):
            self.selected_square = sq
            self.hint_buffer = ""
            self.recompute_hints()
            self._set_status(f"Switched selection to {chess.square_name(sq).upper()}")
            self.sync_ui()
            return

        await self.execute_move(self.selected_square, sq)

    async def on_board_widget_square_clicked(self, event: BoardWidget.SquareClicked) -> None:
        if not self.config.input.allow_mouse_clicks:
            return
        self.cursor_square = event.square
        await self._handle_square_selection(event.square)

    # ------------------------------------------------------------------
    # Keyboard & Vimium Key State Machine
    # ------------------------------------------------------------------

    def _matches_binding(self, event: events.Key, action: str) -> bool:
        bound = self.config.input.keybindings.get(action, "")
        if not bound:
            return False
        norm_key = KEY_ALIASES.get(event.key, event.key)
        if norm_key == bound:
            return True
        return bool(event.character and event.character == bound)

    async def on_key(self, event: events.Key) -> None:
        # Don't intercept keys when a modal screen or command input box is active
        if len(self.screen_stack) > 1:
            return
        cmd_bar = self.query_one("#command_bar", CommandBar)
        if cmd_bar.input_active:
            if event.key == "escape":
                cmd_bar.close_input()
                event.stop()
            return

        # Check configured global action keybindings first
        if self._matches_binding(event, "quit"):
            self.exit()
            event.stop()
            return
        if self._matches_binding(event, "cancel"):
            self._clear_selection()
            self._set_status("Cleared selection")
            event.stop()
            return
        if self._matches_binding(event, "command_palette"):
            cmd_bar.open_input(":")
            event.stop()
            return
        if self._matches_binding(event, "san_input") and self.config.input.allow_san_command:
            cmd_bar.open_input("/")
            event.stop()
            return
        if self._matches_binding(event, "open_accounts"):
            self.push_screen(AccountsScreen())
            event.stop()
            return
        if self._matches_binding(event, "open_settings"):
            self.push_screen(SettingsScreen())
            event.stop()
            return
        if self._matches_binding(event, "open_play"):
            self.push_screen(PlayScreen())
            event.stop()
            return
        if self._matches_binding(event, "open_archives"):
            self.push_screen(ArchiveScreen())
            event.stop()
            return
        if self._matches_binding(event, "open_help"):
            self.push_screen(HelpScreen())
            event.prevent_default()
            event.stop()
            return
        if self._matches_binding(event, "flip_board"):
            self.manual_flip_offset = not self.manual_flip_offset
            self.recompute_hints()
            self.sync_ui()
            event.stop()
            return
        if self._matches_binding(event, "toggle_hints"):
            self.config.hints.enabled = not self.config.hints.enabled
            self.config_manager.save()
            self.recompute_hints()
            self.sync_ui()
            event.stop()
            return
        if self._matches_binding(event, "toggle_zen"):
            self.config.layout.zen_mode = not self.config.layout.zen_mode
            self.config_manager.save()
            self.apply_config()
            event.stop()
            return
        if self._matches_binding(event, "toggle_blindfold"):
            self.config.board.blindfold = not self.config.board.blindfold
            self.config_manager.save()
            self.sync_ui()
            event.stop()
            return
        if self._matches_binding(event, "cycle_theme"):
            names = list(THEMES.keys())
            cur = names.index(self.config.theme) if self.config.theme in names else 0
            self.config.theme = names[(cur + 1) % len(names)]
            self.config_manager.save()
            self.apply_config()
            self._set_status(f"Theme: {self.config.theme}")
            event.stop()
            return
        if self._matches_binding(event, "cycle_size"):
            sizes = ["auto", "compact", "medium", "large", "huge"]
            cur = sizes.index(self.config.board.square_size) if self.config.board.square_size in sizes else 0
            self.config.board.square_size = sizes[(cur + 1) % len(sizes)]
            self.config_manager.save()
            self.sync_ui()
            self._set_status(f"Square size: {self.config.board.square_size}")
            event.stop()
            return
        if self._matches_binding(event, "resign"):
            await self._trigger_resign()
            event.stop()
            return
        if self._matches_binding(event, "offer_draw"):
            await self._trigger_bridge_action("draw")
            event.stop()
            return
        if self._matches_binding(event, "new_game"):
            await self._trigger_bridge_action("new_game")
            event.stop()
            return

        # Archive Replay navigation
        if self.game_state.mode == GameMode.CHESSCOM_ARCHIVE:
            if event.key in ("right", "n", "space"):
                self._step_archive(1)
                event.stop()
                return
            if event.key in ("left", "p"):
                self._step_archive(-1)
                event.stop()
                return
            if event.key == "home":
                self._step_archive(-9999)
                event.stop()
                return
            if event.key == "end":
                self._step_archive(9999)
                event.stop()
                return

        # Pending pawn promotion shortcut (Q/R/B/N)
        if self.pending_promotion is not None and event.character:
            ch_up = event.character.upper()
            promo_map = {"q": chess.QUEEN, "r": chess.ROOK, "b": chess.BISHOP, "n": chess.KNIGHT}
            mapped = self.config.hints.promotion_keys.get(ch_up) or self.config.hints.promotion_keys.get(
                event.character
            )
            if mapped and mapped.lower() in promo_map:
                from_sq, to_sq = self.pending_promotion
                self.pending_promotion = None
                await self.execute_move(from_sq, to_sq, promotion=promo_map[mapped.lower()])
                event.stop()
                return

        # Backspace edits Vimium buffer or deselects square
        if self._matches_binding(event, "backspace"):
            if self.hint_buffer:
                self.hint_buffer = self.hint_buffer[:-1]
                self.sync_ui()
            elif self.selected_square is not None:
                self._clear_selection()
            event.stop()
            return

        # Cursor navigation (arrows)
        if self.config.input.allow_cursor_navigation and event.key in ("up", "down", "left", "right"):
            self._move_cursor(event.key)
            event.stop()
            return
        if self.config.input.allow_cursor_navigation and event.key in ("enter", "space"):
            if self.cursor_square is not None:
                await self._handle_square_selection(self.cursor_square)
                event.stop()
                return

        # Vimium hint character typing!
        if self.config.hints.enabled and event.character and event.character.isprintable() and self.active_hints:
            typed = event.character if self.config.hints.case_sensitive else event.character.upper()
            allowed_pool = (
                "ABCDEFGH12345678"
                if self.config.hints.mode == "coordinate"
                else (
                    self.config.hints.alphabet
                    if self.config.hints.case_sensitive
                    else self.config.hints.alphabet.upper()
                )
            )
            if typed not in allowed_pool and not any(
                (code if self.config.hints.case_sensitive else code.upper()).startswith(self.hint_buffer + typed)
                for code in self.active_hints.values()
            ):
                return

            self.hint_buffer += typed
            res = self.hint_engine.match_buffer(self.active_hints, self.hint_buffer)
            if res.exact_square is not None:
                self.hint_buffer = ""
                await self._handle_square_selection(res.exact_square)
            elif res.has_matches:
                self.sync_ui()
            else:
                bad = self.hint_buffer
                self.hint_buffer = ""
                self._set_status(f"No hint matching '{bad}'")
                self.sync_ui()
            event.stop()

    def _move_cursor(self, direction: str) -> None:
        if self.cursor_square is None:
            self.cursor_square = chess.E2 if not self.effective_flipped() else chess.E7
            self.sync_ui()
            return
        file_idx = chess.square_file(self.cursor_square)
        rank_idx = chess.square_rank(self.cursor_square)
        flipped = self.effective_flipped()
        df, dr = 0, 0
        if direction == "left":
            df = 1 if flipped else -1
        elif direction == "right":
            df = -1 if flipped else 1
        elif direction == "up":
            dr = -1 if flipped else 1
        elif direction == "down":
            dr = 1 if flipped else -1
        nf = max(0, min(7, file_idx + df))
        nr = max(0, min(7, rank_idx + dr))
        self.cursor_square = chess.square(nf, nr)
        self.sync_ui()

    async def _trigger_resign(self, force: bool = False) -> None:
        if self.game_state.mode == GameMode.CHESSCOM_LIVE:
            if self.config.input.confirm_resign and not force and not self._confirm_resign_pending:
                self._confirm_resign_pending = True
                self._set_status("Press resign shortcut again (or :resign!) to confirm resignation")
                return
            self._confirm_resign_pending = False
            await self._trigger_bridge_action("resign")
        else:
            self.game_state.game_over = True
            self.game_state.result_text = "Resigned"
            self.game_state.result_reason = "Local resignation"
            self.sync_ui()

    async def _trigger_bridge_action(self, action: str) -> None:
        if self.cdp_bridge and self.cdp_bridge.connected:
            _, msg = await self.cdp_bridge.trigger_action(action)
        elif self.ws_bridge.client_count > 0:
            _, msg = await self.ws_bridge.trigger_action(action)
        else:
            msg = "No live Chess.com browser connected"
        self._set_status(msg)
        self._log(msg)

    # ------------------------------------------------------------------
    # `:` Command Palette & `/` SAN Move Execution
    # ------------------------------------------------------------------

    async def on_command_bar_command_submitted(self, event: CommandBar.CommandSubmitted) -> None:
        self.query_one("#board_widget", BoardWidget).focus()
        if event.prefix == "/":
            mv = self.game_state.parse_text_move(event.text)
            if mv is None:
                self._set_status(f"Invalid/illegal move: {event.text}")
                return
            await self.execute_move(mv.from_square, mv.to_square, promotion=mv.promotion)
            return

        await self.run_vim_command(event.text)

    def on_command_bar_command_cancelled(self, event: CommandBar.CommandCancelled) -> None:
        self.query_one("#board_widget", BoardWidget).focus()

    async def run_vim_command(self, command_text: str) -> None:
        """Execute a Vim-style `:` command."""
        parts = command_text.strip().split()
        if not parts:
            return
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ("q", "quit", "exit"):
            self.exit()
        elif cmd == "theme":
            if not args:
                self._set_status("Themes: " + ", ".join(THEMES.keys()))
                return
            name = args[0].lower()
            if name not in THEMES:
                self._set_status(f"Unknown theme '{name}'. Available: {', '.join(THEMES)}")
                return
            self.config.theme = name
            self.config_manager.save()
            self.apply_config()
            self._set_status(f"Applied theme '{name}'")
        elif cmd == "pieces" and args:
            self.config.board.piece_style = args[0].lower()
            self.config_manager.save()
            self.sync_ui()
            self._set_status(f"Piece style: {self.config.board.piece_style}")
        elif cmd == "size" and args:
            self.config.board.square_size = args[0].lower()
            self.config_manager.save()
            self.sync_ui()
            self._set_status(f"Square size: {self.config.board.square_size}")
        elif cmd == "hints" and args:
            val = args[0].lower()
            if val in ("off", "false", "0"):
                self.config.hints.enabled = False
            elif val in ("on", "true", "1"):
                self.config.hints.enabled = True
            else:
                self.config.hints.enabled = True
                self.config.hints.mode = val
            self.config_manager.save()
            self.recompute_hints()
            self.sync_ui()
            self._set_status(f"Hints: {self.config.hints.mode} ({'ON' if self.config.hints.enabled else 'OFF'})")
        elif cmd == "alphabet" and args:
            self.config.hints.alphabet = args[0]
            self.config_manager.save()
            self.recompute_hints()
            self.sync_ui()
            self._set_status(f"Hint alphabet updated: {self.config.hints.alphabet}")
        elif cmd == "hintlen" and args:
            self.config.hints.min_length = max(1, min(3, int(args[0])))
            self.config_manager.save()
            self.recompute_hints()
            self.sync_ui()
        elif cmd == "coords" and args:
            self.config.board.coordinates = args[0].lower()
            self.config_manager.save()
            self.sync_ui()
        elif cmd == "flip":
            self.manual_flip_offset = not self.manual_flip_offset
            self.recompute_hints()
            self.sync_ui()
        elif cmd == "zen":
            self.config.layout.zen_mode = not self.config.layout.zen_mode
            self.config_manager.save()
            self.apply_config()
        elif cmd == "blindfold":
            self.config.board.blindfold = not self.config.board.blindfold
            self.config_manager.save()
            self.sync_ui()
        elif cmd == "set" and len(args) >= 2:
            key = args[0]
            val = " ".join(args[1:])
            try:
                coerced = self.config_manager.set_by_path(key, val, persist=True)
                self.config = self.config_manager.config
                self.apply_config()
                self._set_status(f"Set {key} = {coerced!r}")
            except Exception as exc:
                self._set_status(f"Error setting {key}: {exc}")
        elif cmd == "reload":
            self.config = self.config_manager.load()
            self.apply_config()
            self._set_status("Reloaded config.toml")
        elif cmd == "preset" and len(args) >= 2:
            sub, name = args[0].lower(), args[1]
            try:
                if sub == "save":
                    p = self.config_manager.save_preset(name)
                    self._set_status(f"Saved preset '{name}' ({p.name})")
                elif sub == "load":
                    self.config = self.config_manager.load_preset(name)
                    self.apply_config()
                    self._set_status(f"Loaded preset '{name}'")
            except Exception as exc:
                self._set_status(str(exc))
        elif cmd == "account":
            if not args:
                self.push_screen(AccountsScreen())
            else:
                _, msg = await self.connect_account(args[0])
                self._set_status(msg)
        elif cmd == "accounts":
            self.push_screen(AccountsScreen())
        elif cmd == "settings":
            self.push_screen(SettingsScreen())
        elif cmd == "play":
            self.push_screen(PlayScreen())
        elif cmd == "archive":
            self.push_screen(ArchiveScreen(initial_username=args[0] if args else ""))
        elif cmd == "puzzle":
            _, msg = await self.start_daily_puzzle(random=("random" in args))
            self._set_status(msg)
        elif cmd == "fen" and args:
            _, msg = self.load_fen(" ".join(args))
            self._set_status(msg)
        elif cmd == "local":
            self.start_local_2p()
        elif cmd == "resign":
            await self._trigger_resign(force=False)
        elif cmd == "resign!":
            await self._trigger_resign(force=True)
        elif cmd in ("draw", "abort", "rematch", "newgame"):
            mapped = "new_game" if cmd == "newgame" else cmd
            await self._trigger_bridge_action(mapped)
        elif cmd == "help":
            self.push_screen(HelpScreen())
        else:
            self._set_status(f"Unknown command ':{cmd}' — press ? for help")
