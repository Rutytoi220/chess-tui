"""Highly customizable chessboard widget with Vimium hint badges and block-art pieces."""

from __future__ import annotations

from dataclasses import dataclass

import chess
from rich.style import Style
from rich.text import Text
from textual import events
from textual.message import Message
from textual.widget import Widget

from chess_tui.config.schema import BoardConfig, HintConfig
from chess_tui.config.themes import (
    BLOCK_SPRITES_5X3,
    BLOCK_SPRITES_7X3,
    BLOCK_SPRITES_9X4,
    PIECE_GLYPHS,
    ThemePalette,
)
from chess_tui.engine.game_state import GameState


BORDER_CHARS: dict[str, tuple[str, str, str, str, str, str]] = {
    "rounded": ("╭", "─", "╮", "│", "╰", "╯"),
    "double": ("╔", "═", "╗", "║", "╚", "╝"),
    "heavy": ("┏", "━", "┓", "┃", "┗", "┛"),
    "ascii": ("+", "-", "+", "|", "+", "+"),
    "none": ("", "", "", "", "", ""),
}


@dataclass(frozen=True, slots=True)
class SquareDims:
    width: int
    height: int
    name: str


SIZE_PRESETS: dict[str, SquareDims] = {
    "compact": SquareDims(5, 1, "compact"),
    "medium": SquareDims(7, 3, "medium"),
    "large": SquareDims(9, 4, "large"),
    "huge": SquareDims(11, 5, "huge"),
    "giant": SquareDims(13, 6, "giant"),
}


class BoardWidget(Widget):
    """Renders the 8x8 board, pieces, highlights, coordinates, and Vimium hint overlays."""

    can_focus = True

    DEFAULT_CSS = """
    BoardWidget {
        width: 1fr;
        height: 1fr;
        content-align: center middle;
    }
    """

    class SquareClicked(Message):
        """Emitted when the user clicks a square on the terminal chessboard."""

        def __init__(self, square: chess.Square) -> None:
            self.square = square
            super().__init__()

    def __init__(
        self,
        game_state: GameState,
        theme: ThemePalette,
        board_config: BoardConfig,
        hint_config: HintConfig,
        *,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self.game_state = game_state
        self.theme = theme
        self.board_config = board_config
        self.hint_config = hint_config

        self.flipped: bool = False
        self.selected_square: chess.Square | None = None
        self.cursor_square: chess.Square | None = None
        self.active_hints: dict[chess.Square, str] = {}
        self.hint_buffer: str = ""
        self.pending_promotion: tuple[chess.Square, chess.Square] | None = None

        # Geometry cached after render for mouse hit-testing
        self._grid_origin_x: int = 0
        self._grid_origin_y: int = 0
        self._last_dims: SquareDims = SIZE_PRESETS["medium"]

    def update_state(
        self,
        *,
        game_state: GameState | None = None,
        theme: ThemePalette | None = None,
        board_config: BoardConfig | None = None,
        hint_config: HintConfig | None = None,
        flipped: bool | None = None,
        selected_square: chess.Square | None = None,
        cursor_square: chess.Square | None = None,
        active_hints: dict[chess.Square, str] | None = None,
        hint_buffer: str | None = None,
        pending_promotion: tuple[chess.Square, chess.Square] | None = None,
    ) -> None:
        if game_state is not None:
            self.game_state = game_state
        if theme is not None:
            self.theme = theme
        if board_config is not None:
            self.board_config = board_config
        if hint_config is not None:
            self.hint_config = hint_config
        if flipped is not None:
            self.flipped = flipped
        self.selected_square = selected_square
        self.cursor_square = cursor_square
        if active_hints is not None:
            self.active_hints = active_hints
        if hint_buffer is not None:
            self.hint_buffer = hint_buffer
        self.pending_promotion = pending_promotion
        self.refresh()

    def _resolve_dims(self) -> SquareDims:
        pref = self.board_config.square_size.lower().strip()
        if pref in SIZE_PRESETS:
            return SIZE_PRESETS[pref]

        avail_w = max(40, self.size.width)
        avail_h = max(10, self.size.height)
        overhead_w = 5 if self.board_config.coordinates == "outside" else 2
        overhead_h = 3 if self.board_config.coordinates == "outside" else 2
        promo_h = 2 if self.pending_promotion else 0

        max_sq_w = max(5, (avail_w - overhead_w - 2) // 8)
        max_sq_h = max(1, (avail_h - overhead_h - promo_h - 1) // 8)

        # Keep roughly 2:1 cell ratio (square visual proportions) while filling available space
        sq_h = min(max_sq_h, max_sq_w // 2, 7)
        if sq_h < 1:
            sq_h = 1
        sq_w = min(max_sq_w, max(5, sq_h * 2 + 1))
        return SquareDims(sq_w, sq_h, "auto")

    def _piece_symbol(self, piece: chess.Piece) -> str:
        key = piece.symbol()
        style_name = self.board_config.piece_style.lower().strip()
        if style_name == "custom":
            return self.board_config.custom_pieces.get(key, PIECE_GLYPHS["unicode-filled"][key])
        if style_name in PIECE_GLYPHS:
            return PIECE_GLYPHS[style_name][key]
        return PIECE_GLYPHS["unicode-filled"][key]

    def _square_bg(
        self,
        sq: chess.Square,
        is_light: bool,
        legal_targets: set[chess.Square],
        checked_king: chess.Square | None,
    ) -> str:
        t = self.theme
        if self.board_config.highlight_check and checked_king == sq:
            return t.check_bg
        if self.board_config.highlight_selected and self.selected_square == sq:
            return t.selected_bg
        if self.game_state.premove and sq in (self.game_state.premove[0], self.game_state.premove[1]):
            return t.premove_bg
        if self.board_config.show_square_cursor and self.cursor_square == sq:
            return t.cursor_bg
        if self.board_config.highlight_last_move and self.game_state.last_move is not None and sq in (
            self.game_state.last_move.from_square,
            self.game_state.last_move.to_square,
        ):
            return t.last_move_light_bg if is_light else t.last_move_dark_bg
        if (
            self.board_config.legal_move_indicator in ("tint", "both")
            and sq in legal_targets
        ):
            return t.selected_bg
        return t.light_square_bg if is_light else t.dark_square_bg

    def _hint_segments(
        self,
        sq: chess.Square,
        sq_bg: str,
    ) -> list[tuple[str, Style]]:
        """Build styled segments for a square's Vimium hint tag, respecting partial buffer match."""
        tag = self.active_hints.get(sq)
        if not tag:
            return []

        buf = self.hint_buffer if self.hint_config.case_sensitive else self.hint_buffer.upper()
        cmp_tag = tag if self.hint_config.case_sensitive else tag.upper()
        t = self.theme

        if buf:
            if cmp_tag.startswith(buf):
                matched_part = tag[: len(buf)]
                rest_part = tag[len(buf) :]
                segs = [
                    (
                        matched_part,
                        Style(color=t.hint_matched_fg, bgcolor=t.hint_bg, bold=True, underline=True),
                    )
                ]
                if rest_part:
                    segs.append((rest_part, Style(color=t.hint_fg, bgcolor=t.hint_bg, bold=True)))
                return segs
            if self.hint_config.dim_non_matching:
                return [(tag, Style(color=t.hint_dim_fg, bgcolor=sq_bg, dim=True))]
        return [(tag, Style(color=t.hint_fg, bgcolor=t.hint_bg, bold=True))]

    def _render_square_row(
        self,
        sq: chess.Square,
        row_idx: int,
        dims: SquareDims,
        sq_bg: str,
        legal_targets: set[chess.Square],
        coord_label: str,
    ) -> list[tuple[str, Style]]:
        """Render one horizontal slice (`row_idx`) of a single square (`dims.width` cells)."""
        w, h = dims.width, dims.height
        t = self.theme
        piece = None if self.board_config.blindfold else self.game_state.board.piece_at(sq)
        is_legal_target = sq in legal_targets
        hint_segs = self._hint_segments(sq, sq_bg)
        hint_len = sum(len(s[0]) for s in hint_segs)
        base_style = Style(color=t.text_fg, bgcolor=sq_bg)

        # Compact 1-row layout: `[AB♟  ]` or `[  ♟  ]`
        if h == 1:
            if piece is not None:
                p_fg = t.white_piece_fg if piece.color == chess.WHITE else t.black_piece_fg
                p_sym = self._piece_symbol(piece)
                p_style = Style(color=p_fg, bgcolor=sq_bg, bold=True)
                if hint_segs and hint_len + 2 <= w:
                    pad_right = w - hint_len - 1
                    return [*hint_segs, (p_sym, p_style), (" " * pad_right, base_style)]
                left_pad = (w - 1) // 2
                right_pad = w - 1 - left_pad
                return [(" " * left_pad, base_style), (p_sym, p_style), (" " * right_pad, base_style)]
            if hint_segs:
                pad_right = max(0, w - hint_len)
                return [*hint_segs, (" " * pad_right, base_style)]
            if is_legal_target and self.board_config.legal_move_indicator in ("dot", "both"):
                left_pad = (w - 1) // 2
                right_pad = w - 1 - left_pad
                return [
                    (" " * left_pad, base_style),
                    ("•", Style(color=t.legal_move_fg, bgcolor=sq_bg, bold=True)),
                    (" " * right_pad, base_style),
                ]
            return [(" " * w, base_style)]

        # Multi-row square rendering (`medium`, `large`, `huge`, `giant`, `auto`)
        style_pref = self.board_config.piece_style.lower().strip()
        use_block = (
            style_pref in ("block", "auto")
            and piece is not None
            and w >= 7
            and h >= 4
        )
        hint_pos = self.hint_config.position
        hint_row = 0 if hint_pos.startswith("top") or hint_pos == "center" else (h - 1)
        if hint_pos == "center" and piece is None:
            hint_row = h // 2

        # Block-art multi-line pieces occupy rows below row 0
        if use_block and piece is not None:
            if w >= 11 and h >= 5:
                sprite_rows: tuple[str, ...] = BLOCK_SPRITES_9X4[piece.symbol().upper()]
            elif w >= 9:
                sprite_rows = BLOCK_SPRITES_7X3[piece.symbol().upper()]
            else:
                sprite_rows = BLOCK_SPRITES_5X3[piece.symbol().upper()]
            sprite_h = len(sprite_rows)
            sprite_start_row = 1
            if row_idx != hint_row and sprite_start_row <= row_idx < sprite_start_row + sprite_h:
                line = sprite_rows[row_idx - sprite_start_row]
                p_fg = t.white_piece_fg if piece.color == chess.WHITE else t.black_piece_fg
                p_style = Style(color=p_fg, bgcolor=sq_bg, bold=True)
                left_pad = (w - len(line)) // 2
                right_pad = w - len(line) - left_pad
                return [(" " * left_pad, base_style), (line, p_style), (" " * right_pad, base_style)]

        # Hint row (typically row 0)
        if row_idx == hint_row and hint_segs:
            if hint_pos.endswith("right"):
                left_pad = max(0, w - hint_len)
                return [(" " * left_pad, base_style), *hint_segs]
            if hint_pos == "center":
                left_pad = max(0, (w - hint_len) // 2)
                right_pad = max(0, w - hint_len - left_pad)
                return [(" " * left_pad, base_style), *hint_segs, (" " * right_pad, base_style)]
            right_pad = max(0, w - hint_len)
            # Capture ring marker on top-right when square has enemy target
            if is_legal_target and piece is not None and right_pad >= 1:
                return [
                    *hint_segs,
                    (" " * (right_pad - 1), base_style),
                    ("◎", Style(color=t.capture_ring_fg, bgcolor=sq_bg, bold=True)),
                ]
            return [*hint_segs, (" " * right_pad, base_style)]

        # Center row for single-glyph pieces or legal-move dot
        center_row = h // 2
        if row_idx == center_row and not use_block:
            if piece is not None:
                p_fg = t.white_piece_fg if piece.color == chess.WHITE else t.black_piece_fg
                p_sym = self._piece_symbol(piece)
                left_pad = (w - 1) // 2
                right_pad = w - 1 - left_pad
                return [
                    (" " * left_pad, base_style),
                    (p_sym, Style(color=p_fg, bgcolor=sq_bg, bold=True)),
                    (" " * right_pad, base_style),
                ]
            if is_legal_target and self.board_config.legal_move_indicator in ("dot", "ring", "both"):
                marker = "●" if self.board_config.legal_move_indicator in ("dot", "both") else "○"
                left_pad = (w - 1) // 2
                right_pad = w - 1 - left_pad
                return [
                    (" " * left_pad, base_style),
                    (marker, Style(color=t.legal_move_fg, bgcolor=sq_bg, bold=True)),
                    (" " * right_pad, base_style),
                ]

        # Inside coordinates on bottom row if configured
        if row_idx == h - 1 and coord_label and self.board_config.coordinates == "inside":
            pad_left = max(0, w - len(coord_label))
            return [
                (" " * pad_left, base_style),
                (coord_label, Style(color=t.muted_fg, bgcolor=sq_bg)),
            ]

        return [(" " * w, base_style)]

    def render(self) -> Text:
        dims = self._resolve_dims()
        self._last_dims = dims
        t = self.theme
        board = self.game_state.board

        legal_targets: set[chess.Square] = set()
        if self.selected_square is not None:
            if self.game_state.is_premove_allowed():
                legal_targets = {sq for sq in chess.SQUARES if sq != self.selected_square}
            else:
                legal_targets = {
                    m.to_square for m in board.legal_moves if m.from_square == self.selected_square
                }

        checked_king = board.king(board.turn) if board.is_check() else None

        ranks = list(range(8)) if self.flipped else list(range(7, -1, -1))
        files = list(range(7, -1, -1)) if self.flipped else list(range(8))

        tl, horiz, tr, vert, bl, br = BORDER_CHARS.get(
            self.board_config.border_style, BORDER_CHARS["rounded"]
        )
        has_border = bool(tl)
        outside_coords = self.board_config.coordinates == "outside"
        left_margin = 3 if outside_coords else 0
        board_pixel_w = dims.width * 8

        # Center vertically and horizontally inside widget area
        total_h = dims.height * 8 + (2 if has_border else 0) + (1 if outside_coords else 0) + (2 if self.pending_promotion else 0)
        total_w = board_pixel_w + left_margin + (2 if has_border else 0)
        pad_top = max(0, (self.size.height - total_h) // 2)
        pad_left = max(0, (self.size.width - total_w) // 2)

        self._grid_origin_x = pad_left + left_margin + (1 if has_border else 0)
        self._grid_origin_y = pad_top + (1 if has_border else 0)

        border_style = Style(color=t.border_fg, bgcolor=t.app_bg)
        bg_style = Style(color=t.text_fg, bgcolor=t.app_bg)
        coord_style = Style(color=t.muted_fg, bgcolor=t.app_bg, bold=True)

        out = Text()

        for _ in range(pad_top):
            out.append("\n")

        if has_border:
            out.append(" " * (pad_left + left_margin), bg_style)
            out.append(tl + (horiz * board_pixel_w) + tr + "\n", border_style)

        for r_idx, rank in enumerate(ranks):
            for sub_row in range(dims.height):
                out.append(" " * pad_left, bg_style)
                if outside_coords:
                    if sub_row == dims.height // 2:
                        out.append(f" {rank + 1} ", coord_style)
                    else:
                        out.append("   ", bg_style)
                if has_border:
                    out.append(vert, border_style)

                for c_idx, file_idx in enumerate(files):
                    sq = chess.square(file_idx, rank)
                    is_light = (file_idx + rank) % 2 == 1
                    sq_bg = self._square_bg(sq, is_light, legal_targets, checked_king)

                    coord_label = ""
                    if self.board_config.coordinates == "inside":
                        if r_idx == 7 and c_idx == 0:
                            coord_label = chess.square_name(sq)
                        elif r_idx == 7:
                            coord_label = chess.FILE_NAMES[file_idx]
                        elif c_idx == 7:
                            coord_label = str(rank + 1)

                    for text_part, st in self._render_square_row(
                        sq, sub_row, dims, sq_bg, legal_targets, coord_label
                    ):
                        out.append(text_part, st)

                if has_border:
                    out.append(vert, border_style)
                out.append("\n")

        if has_border:
            out.append(" " * (pad_left + left_margin), bg_style)
            out.append(bl + (horiz * board_pixel_w) + br + "\n", border_style)

        if outside_coords:
            out.append(" " * (pad_left + left_margin + (1 if has_border else 0)), bg_style)
            for file_idx in files:
                lbl = chess.FILE_NAMES[file_idx]
                l_pad = (dims.width - 1) // 2
                r_pad = dims.width - 1 - l_pad
                out.append((" " * l_pad) + lbl + (" " * r_pad), coord_style)
            out.append("\n")

        if self.pending_promotion is not None:
            out.append("\n")
            out.append(" " * (pad_left + left_margin), bg_style)
            promo_banner = " PROMOTE TO: "
            out.append(promo_banner, Style(color=t.hint_fg, bgcolor=t.accent_fg, bold=True))
            for key_label, p_name in [("Q", "Queen"), ("R", "Rook"), ("B", "Bishop"), ("N", "Knight")]:
                out.append("  ", bg_style)
                out.append(f" {key_label} ", Style(color=t.hint_fg, bgcolor=t.hint_bg, bold=True))
                out.append(f" {p_name}", Style(color=t.text_fg, bgcolor=t.app_bg))
            out.append("\n")

        return out

    def on_click(self, event: events.Click) -> None:
        """Translate terminal mouse click coordinates to the corresponding chess square."""
        dims = self._last_dims
        rel_x = event.x - self._grid_origin_x
        rel_y = event.y - self._grid_origin_y
        if rel_x < 0 or rel_y < 0:
            return
        col = rel_x // dims.width
        row = rel_y // dims.height
        if not (0 <= col < 8 and 0 <= row < 8):
            return
        file_idx = (7 - col) if self.flipped else col
        rank_idx = row if self.flipped else (7 - row)
        sq = chess.square(file_idx, rank_idx)
        self.post_message(self.SquareClicked(sq))
