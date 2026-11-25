"""Tests for GameState rules, SAN/UCI parsing, captured pieces, and Chess.com DOM sync."""

from __future__ import annotations

import chess

from chess_tui.engine.game_state import GameMode, GameState, parse_clock_seconds


def test_move_execution_and_captured_material():
    gs = GameState()
    for mv_san in ("e4", "d5", "exd5"):
        mv = gs.parse_text_move(mv_san)
        assert mv is not None
        gs.apply_move(mv.from_square, mv.to_square, mv.promotion)

    cap_w, cap_b, adv = gs.captured_pieces()
    assert cap_w == ["p"]
    assert cap_b == []
    assert adv == 1


def test_promotion_detection():
    gs = GameState()
    gs.board = chess.Board("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    assert gs.needs_promotion_choice(chess.A7, chess.A8) is True
    mv = gs.apply_move(chess.A7, chess.A8, promotion=chess.KNIGHT)
    assert mv.promotion == chess.KNIGHT
    assert gs.board.piece_at(chess.A8) == chess.Piece(chess.KNIGHT, chess.WHITE)


def test_sync_from_bridge_reconstructs_moves_and_clocks():
    gs = GameState()
    snapshot = {
        "url": "https://www.chess.com/game/live/123456",
        "hasBoard": True,
        "flipped": True,
        "moves": ["e4", "2s", "c5", "0s", "Nf3", "1.4s"],
        "topPlayer": {"username": "WhitePlayer", "rating": "1850", "clock": "02:58", "isActive": False},
        "bottomPlayer": {"username": "BlackPlayer", "rating": "1900", "clock": "03:00", "isActive": True},
        "gameOver": {"isOver": False},
    }
    changed = gs.sync_from_bridge(snapshot)
    assert changed is True
    assert gs.mode == GameMode.CHESSCOM_LIVE
    assert gs.player_color == chess.BLACK
    assert gs.board.turn == chess.BLACK
    assert gs.move_history_san == ["e4", "c5", "Nf3"]
    assert gs.white_player.username == "WhitePlayer"
    assert gs.black_player.username == "BlackPlayer"
    assert gs.black_player.is_active_clock is True
    assert gs.white_player.clock_seconds == 178.0


def test_sync_from_bridge_tier3_raw_dom_pieces():
    gs = GameState()
    snapshot = {
        "hasBoard": True,
        "flipped": False,
        "turn": "b",
        "pieces": {"e1": "wk", "e8": "bk", "e4": "wp"},
        "lastMoveSquares": ["e2", "e4"],
        "topPlayer": {"username": "Opp", "clock": "04:55", "isActive": True},
        "bottomPlayer": {"username": "Hero", "clock": "05:00", "isActive": False},
    }
    changed = gs.sync_from_bridge(snapshot)
    assert changed is True
    assert gs.board.turn == chess.BLACK
    assert gs.board.piece_at(chess.E4) == chess.Piece(chess.PAWN, chess.WHITE)
    assert gs.last_move == chess.Move(chess.E2, chess.E4)


def test_parse_clock_seconds():
    assert parse_clock_seconds("04:32") == 272.0
    assert parse_clock_seconds("1:02:03") == 3723.0
    assert parse_clock_seconds("0:08.5") == 8.5
    assert parse_clock_seconds("--:--") is None


def _pieces_map(board: chess.Board) -> dict[str, str]:
    out: dict[str, str] = {}
    for sq in chess.SQUARES:
        p = board.piece_at(sq)
        if p is not None:
            out[chess.square_name(sq)] = ("w" if p.color == chess.WHITE else "b") + p.symbol().lower()
    return out


def test_incremental_move_inference_when_dom_moves_missing():
    gs = GameState()
    ref = chess.Board()

    # Initial board snapshot with empty DOM move list
    gs.sync_from_bridge(
        {
            "url": "https://www.chess.com/game/live/999111",
            "hasBoard": True,
            "flipped": False,
            "pieces": _pieces_map(ref),
            "moves": [],
            "topPlayer": {"username": "Darian-1899", "clock": "10:00", "isActive": False},
            "bottomPlayer": {"username": "Rutytoi220", "clock": "10:00", "isActive": True},
        }
    )
    assert gs.move_history_san == []

    # 1-ply move (e4) with empty DOM move list
    ref.push_san("e4")
    gs.sync_from_bridge(
        {
            "url": "https://www.chess.com/game/live/999111",
            "hasBoard": True,
            "flipped": False,
            "pieces": _pieces_map(ref),
            "moves": [],
            "topPlayer": {"username": "Darian-1899", "clock": "10:00", "isActive": True},
            "bottomPlayer": {"username": "Rutytoi220", "clock": "09:58", "isActive": False},
        }
    )
    assert gs.move_history_san == ["e4"]

    # 2-ply jump (e5 + Nf3) between polls with empty DOM move list
    ref.push_san("e5")
    ref.push_san("Nf3")
    gs.sync_from_bridge(
        {
            "url": "https://www.chess.com/game/live/999111",
            "hasBoard": True,
            "flipped": False,
            "pieces": _pieces_map(ref),
            "moves": [],
            "topPlayer": {"username": "Darian-1899", "clock": "09:55", "isActive": True},
            "bottomPlayer": {"username": "Rutytoi220", "clock": "09:57", "isActive": False},
        }
    )
    assert gs.move_history_san == ["e4", "e5", "Nf3"]
    pgn = gs.export_pgn()
    assert "1. e4 e5 2. Nf3" in pgn
    assert '[White "Rutytoi220"]' in pgn
    assert '[Black "Darian-1899"]' in pgn
    assert '[Link "https://www.chess.com/game/live/999111"]' in pgn


def test_tier0_pgn_sync_and_share_links():
    gs = GameState()
    pgn_text = '[Event "Live Chess"]\n[White "Hero"]\n[Black "Villain"]\n[Result "1-0"]\n\n1. f3 e5 2. g4 Qh4# 0-1'
    gs.sync_from_bridge(
        {
            "url": "https://www.chess.com/game/live/123456789?tab=game",
            "hasBoard": True,
            "flipped": False,
            "pgn": pgn_text,
            "moves": [],
            "gameOver": {"isOver": True, "score": "0-1", "reason": "Checkmate"},
        }
    )
    assert gs.move_history_san == ["f3", "e5", "g4", "Qh4#"]
    assert gs.export_pgn() == pgn_text
    links = gs.share_links()
    assert links["game_url"] == "https://www.chess.com/game/live/123456789"
    assert links["review_url"] == "https://www.chess.com/analysis/game/live/123456789?tab=review"
    assert links["lichess_analysis_url"].startswith("https://lichess.org/analysis/fromPosition/")
