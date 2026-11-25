"""Customizable sidebar widget displaying players, clocks, captures, moves, and logs."""

from __future__ import annotations

import chess
from rich.style import Style
from rich.text import Text
from textual.widget import Widget

from chess_tui.config.schema import HintConfig, LayoutConfig
from chess_tui.config.themes import PIECE_GLYPHS, ThemePalette
from chess_tui.engine.game_state import GameMode, GameState, PlayerInfo


class SidebarWidget(Widget):
    """Side panel showing player clocks, captured pieces, SAN move list, and connection status."""

    DEFAULT_CSS = """
    SidebarWidget {
        height: 1fr;
        padding: 1 2;
    }
    """

    def __init__(
        self,
        game_state: GameState,
        theme: ThemePalette,
        layout_config: LayoutConfig,
        hint_config: HintConfig,
        *,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self.game_state = game_state
        self.theme = theme
        self.layout_config = layout_config
        self.hint_config = hint_config
        self.flipped: bool = False
        self.connection_label: str = "OFFLINE • Local Mode"
        self.status_logs: list[str] = []

    def add_log(self, msg: str) -> None:
        self.status_logs.append(msg)
        self.status_logs = self.status_logs[-6:]
        self.refresh()

    def update_state(
        self,
        *,
        game_state: GameState | None = None,
        theme: ThemePalette | None = None,
        layout_config: LayoutConfig | None = None,
        hint_config: HintConfig | None = None,
        flipped: bool | None = None,
        connection_label: str | None = None,
    ) -> None:
        if game_state is not None:
            self.game_state = game_state
        if theme is not None:
            self.theme = theme
        if layout_config is not None:
            self.layout_config = layout_config
        if hint_config is not None:
            self.hint_config = hint_config
        if flipped is not None:
            self.flipped = flipped
        if connection_label is not None:
            self.connection_label = connection_label
        self.refresh()

    def _append_player_card(
        self,
        out: Text,
        player: PlayerInfo,
        side_label: str,
        captured: list[str],
        advantage: int,
    ) -> None:
        t = self.theme
        lc = self.layout_config
        title_badge = f"[{player.title}] " if player.title else ""
        rating_str = f" ({player.rating})" if player.rating else ""
        name_line = f"{side_label}: {title_badge}{player.username}{rating_str}"

        out.append(name_line + "\n", Style(color=t.text_fg, bold=True))

        if lc.show_clocks:
            is_low = (
                player.clock_seconds is not None
                and player.clock_seconds <= lc.low_time_seconds
            )
            if is_low:
                clk_style = Style(color=t.clock_low_fg, bgcolor=t.clock_low_bg, bold=True)
            elif player.is_active_clock:
                clk_style = Style(color=t.clock_active_fg, bgcolor=t.clock_active_bg, bold=True)
            else:
                clk_style = Style(color=t.clock_idle_fg, bgcolor=t.clock_idle_bg)

            out.append("  ⏱ ", Style(color=t.muted_fg))
            out.append(f" {player.clock_text} ", clk_style)
            if player.is_active_clock:
                out.append(" ● TURN", Style(color=t.accent_fg, bold=True))
            out.append("\n")

        if lc.show_captured:
            glyphs = PIECE_GLYPHS["unicode-dual"]
            cap_str = "".join(glyphs.get(ch, ch) for ch in captured)
            adv_str = f" +{advantage}" if (lc.show_material_diff and advantage > 0) else ""
            if cap_str or adv_str:
                out.append(f"  {cap_str}", Style(color=t.muted_fg))
                if adv_str:
                    out.append(adv_str, Style(color=t.success_fg, bold=True))
                out.append("\n")

    def render(self) -> Text:
        t = self.theme
        lc = self.layout_config
        gs = self.game_state
        out = Text()

        # Connection / Mode badge
        out.append("CONNECTION\n", Style(color=t.accent_fg, bold=True))
        out.append(f"  {self.connection_label}\n", Style(color=t.text_fg))
        if gs.puzzle_title:
            out.append(f"  Puzzle: {gs.puzzle_title}\n", Style(color=t.warning_fg, bold=True))
        if gs.mode == GameMode.CHESSCOM_ARCHIVE:
            out.append(
                f"  Replay Ply: {gs.archive_ply}/{len(gs.archive_moves)} (←/→ or n/p)\n",
                Style(color=t.warning_fg),
            )
        out.append("\n")

        # Turn banner (immediately distinguishes YOUR TURN vs OPPONENT'S TURN)
        if not gs.game_over and gs.mode != GameMode.CHESSCOM_ARCHIVE:
            if gs.player_color is not None:
                if gs.is_users_turn():
                    side = "WHITE" if gs.player_color == chess.WHITE else "BLACK"
                    out.append(
                        f" ▶ YOUR TURN ({side}) \n\n",
                        Style(color=t.clock_active_fg, bgcolor=t.clock_active_bg, bold=True),
                    )
                else:
                    out.append(
                        " ⏳ OPPONENT'S TURN (PREMOVE) \n\n",
                        Style(color=t.hint_fg, bgcolor=t.premove_bg, bold=True),
                    )
            else:
                side = "WHITE" if gs.board.turn == chess.WHITE else "BLACK"
                out.append(f" TURN: {side}\n\n", Style(color=t.accent_fg, bold=True))

        cap_white, cap_black, white_adv = gs.captured_pieces()
        top_is_white = self.flipped
        if lc.show_players:
            top_p = gs.white_player if top_is_white else gs.black_player
            bot_p = gs.black_player if top_is_white else gs.white_player
            top_cap = cap_white if top_is_white else cap_black
            bot_cap = cap_black if top_is_white else cap_white
            top_adv = white_adv if top_is_white else -white_adv
            bot_adv = -white_adv if top_is_white else white_adv

            self._append_player_card(
                out, top_p, "WHITE" if top_is_white else "BLACK", top_cap, top_adv
            )
            out.append("─" * 30 + "\n", Style(color=t.border_fg))
            self._append_player_card(
                out, bot_p, "BLACK" if top_is_white else "WHITE", bot_cap, bot_adv
            )
            out.append("\n")

        if gs.game_over:
            out.append("GAME OVER  ", Style(color=t.hint_fg, bgcolor=t.warning_fg, bold=True))
            out.append(f" {gs.result_text} ({gs.result_reason})\n", Style(color=t.warning_fg, bold=True))
            out.append("  ^E Share/PGN • :rematch • :newgame\n\n", Style(color=t.accent_fg))
        elif gs.premove is not None:
            p_from = chess.square_name(gs.premove[0]).upper()
            p_to = chess.square_name(gs.premove[1]).upper()
            out.append(" PREMOVE ", Style(color=t.hint_fg, bgcolor=t.premove_bg, bold=True))
            out.append(f" {p_from} → {p_to} (Esc cancel)\n\n", Style(color=t.warning_fg, bold=True))
        elif gs.board.is_check():
            out.append("CHECK!\n\n", Style(color=t.error_fg, bold=True))

        # Move list
        if lc.show_move_list:
            out.append("MOVES\n", Style(color=t.accent_fg, bold=True))
            moves = gs.move_history_san
            if not moves:
                out.append("  (No moves yet)\n", Style(color=t.muted_fg))
            else:
                pairs: list[str] = []
                for idx in range(0, len(moves), 2):
                    move_no = idx // 2 + 1
                    w_mv = moves[idx]
                    b_mv = moves[idx + 1] if idx + 1 < len(moves) else ""
                    pairs.append(f"  {move_no:>2}. {w_mv:<7} {b_mv}")
                # Show last 12 lines so panel stays clean
                visible_pairs = pairs[-12:]
                if len(pairs) > 12:
                    out.append(f"  ... ({len(pairs) - 12} earlier)\n", Style(color=t.muted_fg))
                for line in visible_pairs:
                    out.append(line + "\n", Style(color=t.text_fg))
            out.append("\n")

        # Hint Legend
        if lc.show_hint_legend:
            out.append("VIMIUM HINTS\n", Style(color=t.accent_fg, bold=True))
            state_lbl = "ON" if self.hint_config.enabled else "OFF"
            out.append(
                f"  Mode: {self.hint_config.mode} ({state_lbl}) • len≥{self.hint_config.min_length}\n",
                Style(color=t.muted_fg),
            )
            out.append("  Type tag to select, then target tag to move.\n", Style(color=t.text_fg))
            out.append("  ^A login  ^P play  ^S customize  ^G archives\n", Style(color=t.muted_fg))
            out.append("  ^E share/pgn  : command  / SAN  ? help\n", Style(color=t.muted_fg))
            out.append("\n")

        # Recent logs
        if lc.show_status_log and self.status_logs:
            out.append("ACTIVITY\n", Style(color=t.accent_fg, bold=True))
            for entry in self.status_logs[-4:]:
                out.append(f"  • {entry}\n", Style(color=t.muted_fg))

        return out
