"""Tests for the Vimium-style HintEngine."""

from __future__ import annotations

import chess

from chess_tui.config.schema import HintConfig
from chess_tui.engine.hints import HintEngine, generate_prefix_free_codes


def test_prefix_free_codes_unique_and_non_colliding():
    for count in (1, 5, 16, 32, 64):
        for alphabet in ("ASDF", "ABCDEFGH", "ABCDEFGHJKLMNPQRSTUVWXYZ"):
            for smart in (False, True):
                codes = generate_prefix_free_codes(count, alphabet, min_length=2, smart_shortest=smart)
                assert len(codes) == count
                assert len(set(codes)) == count
                # Prefix-free property: no code may be a strict prefix of another
                for i, c1 in enumerate(codes):
                    for j, c2 in enumerate(codes):
                        if i != j:
                            assert not c2.startswith(c1), f"Collision: {c1} prefixes {c2}"


def test_dynamic_hints_select_then_move_flow():
    board = chess.Board()
    cfg = HintConfig(mode="dynamic", alphabet="ABCDEFGHJKLMNPQRSTUVWXYZ", min_length=2)
    engine = HintEngine(cfg)

    # Stage 1: Only movable white pieces (8 pawns + 2 knights = 10 pieces)
    stage1 = engine.compute_hints(board, selected_square=None)
    assert len(stage1) == 10
    assert chess.E2 in stage1
    assert chess.E1 not in stage1  # King has no legal moves on move 1

    # Typing first char matches prefix
    e2_tag = stage1[chess.E2]
    partial = engine.match_buffer(stage1, e2_tag[0])
    assert partial.exact_square is None
    assert partial.has_matches
    assert chess.E2 in partial.matching_squares

    # Typing full tag resolves exact square
    exact = engine.match_buffer(stage1, e2_tag)
    assert exact.exact_square == chess.E2

    # Stage 2: Selecting e2 yields hints only for e3 and e4
    stage2 = engine.compute_hints(board, selected_square=chess.E2)
    assert set(stage2.keys()) == {chess.E3, chess.E4}
    e4_tag = stage2[chess.E4]
    assert engine.match_buffer(stage2, e4_tag).exact_square == chess.E4


def test_static_64_square_grid_and_custom_map():
    board = chess.Board()
    cfg = HintConfig(
        mode="static",
        alphabet="ABCDEFGH",
        min_length=2,
        custom_square_map={"e2": "AB", "e4": "BC"},
    )
    engine = HintEngine(cfg)

    stage1 = engine.compute_hints(board, selected_square=None)
    assert stage1[chess.E2] == "AB"

    stage2 = engine.compute_hints(board, selected_square=chess.E2)
    assert stage2[chess.E4] == "BC"
    assert len(set(stage2.values())) == len(stage2)


def test_coordinate_mode():
    board = chess.Board()
    cfg = HintConfig(mode="coordinate")
    engine = HintEngine(cfg)
    stage1 = engine.compute_hints(board, selected_square=None)
    assert stage1[chess.E2] == "E2"
    stage2 = engine.compute_hints(board, selected_square=chess.E2)
    assert stage2[chess.E4] == "E4"


def test_case_insensitivity_and_premove_candidates():
    board = chess.Board()
    board.push_san("e4")  # Black to move
    cfg = HintConfig(mode="dynamic", alphabet="ASDFGHJKL", min_length=2, case_sensitive=False)
    engine = HintEngine(cfg)

    # White premove candidates when it's Black's turn
    hints = engine.compute_hints(
        board, selected_square=None, premove_mode=True, player_color=chess.WHITE
    )
    assert chess.E4 in hints  # White pawn on e4 can be premoved
    assert chess.E7 not in hints  # Enemy pawn is not selectable

    tag = hints[chess.E4]
    res = engine.match_buffer(hints, tag.lower())
    assert res.exact_square == chess.E4

    # Stage 2 premove targets for White pawn on e4 should be only e5, d5, f5 (not all 63 squares!)
    dest_hints = engine.compute_hints(
        board, selected_square=chess.E4, premove_mode=True, player_color=chess.WHITE
    )
    assert set(dest_hints.keys()) == {chess.E5, chess.D5, chess.F5}
