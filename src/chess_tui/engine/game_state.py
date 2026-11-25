"""Unified chess game state model supporting live Chess.com, puzzles, archives, and offline play."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
import io
import re
from typing import Any

import chess
import chess.pgn


class GameMode(StrEnum):
    """Active TUI play/view mode."""

    LOCAL_2P = "local-2p"
    LOCAL_ENGINE = "local-engine"
    SANDBOX = "sandbox"
    CHESSCOM_LIVE = "chesscom-live"
    CHESSCOM_PUZZLE = "chesscom-puzzle"
    CHESSCOM_ARCHIVE = "chesscom-archive"


PIECE_VALUES: dict[chess.PieceType, int] = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}

STARTING_COUNTS: dict[chess.PieceType, int] = {
    chess.QUEEN: 1,
    chess.ROOK: 2,
    chess.BISHOP: 2,
    chess.KNIGHT: 2,
    chess.PAWN: 8,
}


@dataclass
class PlayerInfo:
    """Metadata and clock status for one side."""

    username: str = "Player"
    rating: str = ""
    title: str = ""
    clock_text: str = "--:--"
    clock_seconds: float | None = None
    is_active_clock: bool = False


@dataclass
class GameState:
    """Complete reactive state of the active board."""

    board: chess.Board = field(default_factory=chess.Board)
    mode: GameMode = GameMode.LOCAL_2P
    player_color: chess.Color | None = None  # None means human controls current turn (2P/sandbox)
    white_player: PlayerInfo = field(default_factory=lambda: PlayerInfo(username="White"))
    black_player: PlayerInfo = field(default_factory=lambda: PlayerInfo(username="Black"))
    move_history_san: list[str] = field(default_factory=list)
    last_move: chess.Move | None = None
    premove: tuple[chess.Square, chess.Square, chess.PieceType | None] | None = None
    game_over: bool = False
    result_text: str = ""
    result_reason: str = ""
    game_url: str = ""
    raw_pgn: str = ""
    puzzle_solution: list[str] = field(default_factory=list)
    puzzle_index: int = 0
    puzzle_title: str = ""
    archive_moves: list[chess.Move] = field(default_factory=list)
    archive_ply: int = 0
    archive_initial_fen: str = chess.STARTING_FEN

    def reset_local(self, mode: GameMode = GameMode.LOCAL_2P, player_color: chess.Color | None = None) -> None:
        """Reset to a fresh starting chess position."""
        self.board = chess.Board()
        self.mode = mode
        self.player_color = player_color
        self.move_history_san = []
        self.last_move = None
        self.premove = None
        self.game_over = False
        self.result_text = ""
        self.result_reason = ""
        self.game_url = ""
        self.raw_pgn = ""
        self.puzzle_solution = []
        self.puzzle_index = 0
        self.puzzle_title = ""
        if mode == GameMode.LOCAL_2P:
            self.white_player = PlayerInfo(username="White (Local)")
            self.black_player = PlayerInfo(username="Black (Local)")
        elif mode == GameMode.LOCAL_ENGINE:
            self.white_player = PlayerInfo(username="You")
            self.black_player = PlayerInfo(username="UCI Engine")

    def is_users_turn(self) -> bool:
        """Return True if the local user controls the side currently to move."""
        if self.game_over:
            return False
        if self.mode == GameMode.CHESSCOM_ARCHIVE:
            return False
        if self.player_color is None:
            return True
        return self.board.turn == self.player_color

    def is_premove_allowed(self) -> bool:
        """Return True when online play allows queuing a premove on opponent's turn."""
        return (
            self.mode == GameMode.CHESSCOM_LIVE
            and not self.game_over
            and self.player_color is not None
            and self.board.turn != self.player_color
        )

    def apply_move(
        self,
        from_sq: chess.Square,
        to_sq: chess.Square,
        promotion: chess.PieceType | None = None,
    ) -> chess.Move:
        """Validate and execute a chess move on the internal board."""
        piece = self.board.piece_at(from_sq)
        if piece is not None and piece.piece_type == chess.PAWN and promotion is None:
            rank = chess.square_rank(to_sq)
            if (piece.color == chess.WHITE and rank == 7) or (piece.color == chess.BLACK and rank == 0):
                promotion = chess.QUEEN

        move = chess.Move(from_sq, to_sq, promotion=promotion)
        if move not in self.board.legal_moves:
            raise ValueError(f"Illegal move: {move.uci()}")

        san = self.board.san(move)
        self.board.push(move)
        self.move_history_san.append(san)
        self.last_move = move
        self.premove = None
        self._update_game_over_status()
        return move

    def needs_promotion_choice(self, from_sq: chess.Square, to_sq: chess.Square) -> bool:
        """Return True if moving from_sq -> to_sq is a legal (or premove) pawn promotion."""
        piece = self.board.piece_at(from_sq)
        if piece is None or piece.piece_type != chess.PAWN:
            return False
        if self.is_premove_allowed():
            promo_rank = 7 if piece.color == chess.WHITE else 0
            return chess.square_rank(to_sq) == promo_rank and abs(
                chess.square_file(to_sq) - chess.square_file(from_sq)
            ) <= 1
        promo_move = chess.Move(from_sq, to_sq, promotion=chess.QUEEN)
        return promo_move in self.board.legal_moves

    def parse_text_move(self, text: str) -> chess.Move | None:
        """Parse SAN ('Nf3', 'e4', 'O-O') or UCI ('e2e4', 'e7e8q') into a legal Move."""
        cleaned = text.strip()
        if not cleaned:
            return None
        try:
            return self.board.parse_san(cleaned)
        except ValueError:
            pass
        try:
            move = chess.Move.from_uci(cleaned.lower())
            if move in self.board.legal_moves:
                return move
        except ValueError:
            pass
        return None

    def _update_game_over_status(self) -> None:
        if self.board.is_game_over(claim_draw=True):
            outcome = self.board.outcome(claim_draw=True)
            self.game_over = True
            if outcome:
                self.result_text = outcome.result()
                self.result_reason = outcome.termination.name.replace("_", " ").title()
        else:
            self.game_over = False
            self.result_text = ""
            self.result_reason = ""

    def captured_pieces(self) -> tuple[list[str], list[str], int]:
        """Return (captured_by_white, captured_by_black, white_material_advantage).

        Symbols returned are piece letters ('q', 'r', 'b', 'n', 'p' for black pieces captured by white;
        'Q', 'R', 'B', 'N', 'P' for white pieces captured by black).
        """
        white_counts = {pt: 0 for pt in STARTING_COUNTS}
        black_counts = {pt: 0 for pt in STARTING_COUNTS}
        white_score = 0
        black_score = 0

        for sq in chess.SQUARES:
            piece = self.board.piece_at(sq)
            if piece is None:
                continue
            if piece.color == chess.WHITE:
                white_score += PIECE_VALUES[piece.piece_type]
                if piece.piece_type in white_counts:
                    white_counts[piece.piece_type] += 1
            else:
                black_score += PIECE_VALUES[piece.piece_type]
                if piece.piece_type in black_counts:
                    black_counts[piece.piece_type] += 1

        captured_by_white: list[str] = []
        captured_by_black: list[str] = []
        for pt, start_n in STARTING_COUNTS.items():
            missing_black = max(0, start_n - black_counts[pt])
            missing_white = max(0, start_n - white_counts[pt])
            captured_by_white.extend([chess.piece_symbol(pt).lower()] * missing_black)
            captured_by_black.extend([chess.piece_symbol(pt).upper()] * missing_white)

        return captured_by_white, captured_by_black, white_score - black_score

    def sync_from_bridge(self, snapshot: dict[str, Any]) -> bool:
        """Synchronize GameState from a Chess.com browser DOM snapshot.

        Returns True if the board position or move history changed.
        """
        old_fen = self.board.fen()
        old_moves = list(self.move_history_san)
        old_mode = self.mode
        old_player_color = self.player_color
        old_game_over = self.game_over

        old_url = self.game_url
        self.mode = GameMode.CHESSCOM_LIVE
        new_url = str(snapshot.get("url") or self.game_url)
        # Detect switching to a brand-new Chess.com game URL so stale moves/PGN don't bleed over
        if (
            old_url
            and new_url
            and "/game/" in new_url
            and new_url.split("?")[0] != old_url.split("?")[0]
        ):
            self.board = chess.Board()
            self.move_history_san = []
            self.raw_pgn = ""
            self.last_move = None
        self.game_url = new_url

        flipped = bool(snapshot.get("flipped", False))
        # Chess.com bottom player is always the perspective color when playing
        if snapshot.get("playerColor") in ("w", "b"):
            self.player_color = chess.WHITE if snapshot["playerColor"] == "w" else chess.BLACK
        elif snapshot.get("hasBoard"):
            self.player_color = chess.BLACK if flipped else chess.WHITE

        # Update player cards and clocks
        top_p = snapshot.get("topPlayer") or {}
        bot_p = snapshot.get("bottomPlayer") or {}
        if flipped:
            black_raw, white_raw = bot_p, top_p
        else:
            white_raw, black_raw = bot_p, top_p

        self.white_player = PlayerInfo(
            username=str(white_raw.get("username") or "White"),
            rating=str(white_raw.get("rating") or ""),
            title=str(white_raw.get("title") or ""),
            clock_text=str(white_raw.get("clock") or "--:--"),
            clock_seconds=parse_clock_seconds(white_raw.get("clock")),
            is_active_clock=bool(white_raw.get("isActive", False)),
        )
        self.black_player = PlayerInfo(
            username=str(black_raw.get("username") or "Black"),
            rating=str(black_raw.get("rating") or ""),
            title=str(black_raw.get("title") or ""),
            clock_text=str(black_raw.get("clock") or "--:--"),
            clock_seconds=parse_clock_seconds(black_raw.get("clock")),
            is_active_clock=bool(black_raw.get("isActive", False)),
        )

        dom_pieces: dict[str, str] = snapshot.get("pieces") or {}
        dom_moves: list[str] = [
            str(m)
            for m in (snapshot.get("moves") or [])
            if m and not re.fullmatch(r"\d+(?:\.\d+)?[smhd]", str(m).strip(), re.I)
        ]
        dom_fen: str | None = snapshot.get("fen")
        dom_pgn: str = str(snapshot.get("pgn") or "").strip()
        if dom_pgn:
            self.raw_pgn = dom_pgn

        rebuilt_board: chess.Board | None = None
        rebuilt_last_move: chess.Move | None = None

        # Tier 0: Direct PGN from Chess.com board controller (`board.game.getPGN()`)
        if dom_pgn:
            try:
                parsed_game = chess.pgn.read_game(io.StringIO(dom_pgn))
            except Exception:
                parsed_game = None
            if parsed_game is not None:
                candidate = parsed_game.board()
                san_list: list[str] = []
                for mv in parsed_game.mainline_moves():
                    san_list.append(candidate.san(mv))
                    candidate.push(mv)
                if san_list and (not dom_pieces or _board_matches_dom_pieces(candidate, dom_pieces)):
                    rebuilt_board = candidate
                    rebuilt_last_move = candidate.peek() if candidate.move_stack else None
                    self.move_history_san = san_list

        # Tier 1: Replay SAN move list from standard position and verify it matches DOM pieces
        if rebuilt_board is None and dom_moves:
            candidate = chess.Board()
            valid_replay = True
            for san in dom_moves:
                try:
                    mv = candidate.parse_san(san)
                    candidate.push(mv)
                except ValueError:
                    valid_replay = False
                    break
            if valid_replay and (not dom_pieces or _board_matches_dom_pieces(candidate, dom_pieces)):
                rebuilt_board = candidate
                rebuilt_last_move = candidate.peek() if candidate.move_stack else None
                self.move_history_san = dom_moves

        # Tier 1.5: Incremental legal-move inference from previous board when DOM move list is unavailable
        if rebuilt_board is None and dom_pieces and old_mode == GameMode.CHESSCOM_LIVE:
            if _board_matches_dom_pieces(self.board, dom_pieces):
                rebuilt_board = self.board
                rebuilt_last_move = self.last_move
            elif _board_matches_dom_pieces(chess.Board(), dom_pieces):
                rebuilt_board = chess.Board()
                rebuilt_last_move = None
                self.move_history_san = []
                self.raw_pgn = ""
            else:
                inferred = _infer_moves_to_dom(self.board, dom_pieces)
                if inferred is not None:
                    candidate = self.board.copy(stack=True)
                    new_sans = list(self.move_history_san)
                    for mv in inferred:
                        new_sans.append(candidate.san(mv))
                        candidate.push(mv)
                    rebuilt_board = candidate
                    rebuilt_last_move = inferred[-1]
                    self.move_history_san = new_sans

        # Tier 2: Direct FEN from board controller if available
        if rebuilt_board is None and dom_fen:
            try:
                rebuilt_board = chess.Board(dom_fen)
                if dom_moves:
                    self.move_history_san = dom_moves
            except ValueError:
                rebuilt_board = None

        # Tier 3: Reconstruct directly from 64 DOM square classes
        if rebuilt_board is None and dom_pieces:
            turn_str = snapshot.get("turn")
            if turn_str == "w":
                turn = chess.WHITE
            elif turn_str == "b":
                turn = chess.BLACK
            elif self.white_player.is_active_clock and not self.black_player.is_active_clock:
                turn = chess.WHITE
            elif self.black_player.is_active_clock and not self.white_player.is_active_clock:
                turn = chess.BLACK
            else:
                turn = chess.WHITE if len(dom_moves) % 2 == 0 else chess.BLACK

            rebuilt_board = _board_from_dom_pieces(dom_pieces, turn=turn)
            if dom_moves:
                self.move_history_san = dom_moves
            last_squares = snapshot.get("lastMoveSquares") or []
            if len(last_squares) == 2:
                try:
                    rebuilt_last_move = chess.Move(
                        chess.parse_square(last_squares[0]),
                        chess.parse_square(last_squares[1]),
                    )
                except ValueError:
                    pass

        if rebuilt_board is not None:
            self.board = rebuilt_board
            if rebuilt_last_move is not None:
                self.last_move = rebuilt_last_move
            elif not self.move_history_san:
                self.last_move = None

        # Game over info from DOM modal or board rules
        dom_result = snapshot.get("gameOver")
        if isinstance(dom_result, dict) and dom_result.get("isOver"):
            self.game_over = True
            self.result_text = str(dom_result.get("score") or "")
            self.result_reason = str(dom_result.get("reason") or "Game Over")
        else:
            self._update_game_over_status()

        if self.game_over:
            self.premove = None
        elif self.premove is not None:
            p_from = self.premove[0]
            piece = self.board.piece_at(p_from)
            if piece is None or (self.player_color is not None and piece.color != self.player_color):
                self.premove = None

        return (
            self.board.fen() != old_fen
            or self.move_history_san != old_moves
            or self.mode != old_mode
            or self.player_color != old_player_color
            or self.game_over != old_game_over
        )

    def export_fen(self) -> str:
        """Return the current board FEN string."""
        return self.board.fen()

    def share_links(self) -> dict[str, str]:
        """Return shareable URLs for the current game (Chess.com game/review + Lichess analysis)."""
        links: dict[str, str] = {}
        url = self.game_url.strip()
        if url and "chess.com" in url and "/game/" in url:
            clean_url = url.split("?")[0]
            links["game_url"] = clean_url
            m = re.search(r"/game/(live|daily)/(\d+)", clean_url)
            if m:
                kind, gid = m.group(1), m.group(2)
                links["review_url"] = f"https://www.chess.com/analysis/game/{kind}/{gid}?tab=review"
            else:
                links["review_url"] = clean_url
        fen_encoded = self.board.fen().replace(" ", "_")
        links["lichess_analysis_url"] = f"https://lichess.org/analysis/fromPosition/{fen_encoded}"
        links["lichess_paste_url"] = "https://lichess.org/paste"
        return links

    def export_pgn(self) -> str:
        """Build a clean standard PGN string for the current game."""
        if self.raw_pgn.strip():
            return self.raw_pgn.strip()

        game = chess.pgn.Game()
        event_map = {
            GameMode.CHESSCOM_LIVE: "Live Chess",
            GameMode.CHESSCOM_PUZZLE: self.puzzle_title or "Chess.com Puzzle",
            GameMode.CHESSCOM_ARCHIVE: "Chess.com Archive",
            GameMode.LOCAL_ENGINE: "Local vs UCI Engine",
            GameMode.LOCAL_2P: "Local 2-Player",
            GameMode.SANDBOX: "Custom Position",
        }
        game.headers["Event"] = event_map.get(self.mode, "Chess Game")
        game.headers["Site"] = "Chess.com" if self.mode == GameMode.CHESSCOM_LIVE else "chess-tui"
        game.headers["Date"] = datetime.now().strftime("%Y.%m.%d")
        game.headers["Round"] = "-"
        game.headers["White"] = self.white_player.username or "White"
        game.headers["Black"] = self.black_player.username or "Black"
        if self.white_player.rating:
            game.headers["WhiteElo"] = self.white_player.rating
        if self.black_player.rating:
            game.headers["BlackElo"] = self.black_player.rating

        res = self.result_text.strip()
        if res not in ("1-0", "0-1", "1/2-1/2"):
            outcome = self.board.outcome(claim_draw=True) if self.board.is_game_over(claim_draw=True) else None
            res = outcome.result() if outcome else "*"
        game.headers["Result"] = res

        if self.result_reason:
            game.headers["Termination"] = self.result_reason
        if self.game_url and "/game/" in self.game_url:
            game.headers["Link"] = self.game_url.split("?")[0]

        moves_to_write: list[chess.Move] = []
        start_board: chess.Board | None = None

        if self.mode == GameMode.CHESSCOM_ARCHIVE and self.archive_moves:
            start_board = chess.Board(self.archive_initial_fen)
            moves_to_write = list(self.archive_moves)
        elif self.board.move_stack:
            root = self.board.root()
            start_board = root
            moves_to_write = list(self.board.move_stack)
        elif self.move_history_san:
            tmp = chess.Board()
            parsed: list[chess.Move] = []
            ok = True
            for san in self.move_history_san:
                try:
                    mv = tmp.parse_san(san)
                    tmp.push(mv)
                    parsed.append(mv)
                except ValueError:
                    ok = False
                    break
            if ok and parsed:
                start_board = chess.Board()
                moves_to_write = parsed

        if start_board is not None and start_board.fen() != chess.STARTING_FEN:
            game.setup(start_board)
        elif not moves_to_write and self.board.fen() != chess.STARTING_FEN:
            game.setup(self.board)

        node: chess.pgn.GameNode = game
        for mv in moves_to_write:
            node = node.add_variation(mv)

        exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=False)
        return game.accept(exporter).strip()


def parse_clock_seconds(clock_text: Any) -> float | None:
    """Convert '04:32', '1:05:10', or '0:09.4' into seconds."""
    if not isinstance(clock_text, str):
        return None
    txt = clock_text.strip()
    if not txt or txt == "--:--":
        return None
    parts = txt.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        return float(txt)
    except ValueError:
        return None


def _board_matches_dom_pieces(board: chess.Board, dom_pieces: dict[str, str]) -> bool:
    """Verify every square piece in `board` equals `dom_pieces`."""
    for sq in chess.SQUARES:
        sq_name = chess.square_name(sq)
        piece = board.piece_at(sq)
        expected = None
        if piece is not None:
            color_ch = "w" if piece.color == chess.WHITE else "b"
            expected = color_ch + piece.symbol().lower()
        if dom_pieces.get(sq_name) != expected:
            return False
    return True


def _infer_moves_to_dom(board: chess.Board, dom_pieces: dict[str, str]) -> list[chess.Move] | None:
    """Infer a 1-ply (or 2-ply) legal move sequence transitioning `board` to `dom_pieces`."""
    # Fast 1-ply check
    for mv in board.legal_moves:
        board.push(mv)
        matched = _board_matches_dom_pieces(board, dom_pieces)
        board.pop()
        if matched:
            return [mv]

    # 2-ply check (e.g. fast premove or both moves happened within one poll interval)
    for mv1 in board.legal_moves:
        board.push(mv1)
        for mv2 in board.legal_moves:
            board.push(mv2)
            matched = _board_matches_dom_pieces(board, dom_pieces)
            board.pop()
            if matched:
                board.pop()
                return [mv1, mv2]
        board.pop()
    return None


def _board_from_dom_pieces(dom_pieces: dict[str, str], turn: chess.Color) -> chess.Board:
    """Build a chess.Board from Chess.com DOM piece map (e.g. {'e2': 'wp', 'e8': 'bk'})."""
    board = chess.Board.empty()
    board.turn = turn
    for sq_name, code in dom_pieces.items():
        if len(code) != 2:
            continue
        try:
            sq = chess.parse_square(sq_name)
        except ValueError:
            continue
        color = chess.WHITE if code[0] == "w" else chess.BLACK
        pt = chess.Piece.from_symbol(code[1].upper()).piece_type
        board.set_piece_at(sq, chess.Piece(pt, color))

    # Infer reasonable castling rights when kings and rooks sit on initial squares
    fen_castling = ""
    if board.piece_at(chess.E1) == chess.Piece(chess.KING, chess.WHITE):
        if board.piece_at(chess.H1) == chess.Piece(chess.ROOK, chess.WHITE):
            fen_castling += "K"
        if board.piece_at(chess.A1) == chess.Piece(chess.ROOK, chess.WHITE):
            fen_castling += "Q"
    if board.piece_at(chess.E8) == chess.Piece(chess.KING, chess.BLACK):
        if board.piece_at(chess.H8) == chess.Piece(chess.ROOK, chess.BLACK):
            fen_castling += "k"
        if board.piece_at(chess.A8) == chess.Piece(chess.ROOK, chess.BLACK):
            fen_castling += "q"
    board.set_castling_fen(fen_castling or "-")
    return board
