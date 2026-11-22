"""Vimium-style move hint generator and matcher."""

from __future__ import annotations

from dataclasses import dataclass
import math

import chess

from chess_tui.config.schema import HintConfig


@dataclass(frozen=True, slots=True)
class HintMatchResult:
    """Result of matching a typed key buffer against active hints."""

    exact_square: chess.Square | None
    matching_squares: dict[chess.Square, str]
    has_matches: bool


def _sanitize_alphabet(alphabet: str) -> str:
    """Deduplicate characters while preserving order; fallback to safe default."""
    seen: set[str] = set()
    cleaned: list[str] = []
    for ch in alphabet:
        if ch.isspace():
            continue
        if ch not in seen:
            seen.add(ch)
            cleaned.append(ch)
    if len(cleaned) < 2:
        return "ABCDEFGHJKLMNPQRSTUVWXYZ"
    return "".join(cleaned)


def generate_prefix_free_codes(
    count: int,
    alphabet: str,
    min_length: int = 2,
    smart_shortest: bool = False,
) -> list[str]:
    """Generate `count` deterministic, prefix-free Vimium hint codes.

    Args:
        count: Number of distinct hint tags needed.
        alphabet: Characters used to build hint tags.
        min_length: Minimum tag length when not in smart shortest mode.
        smart_shortest: When True, builds a minimal prefix-free tree (classic Vimium)
            so small sets use 1-character tags and larger sets expand cleanly to 2+.
    """
    if count <= 0:
        return []

    chars = _sanitize_alphabet(alphabet)
    base = len(chars)

    if smart_shortest:
        # Classic Vimium variable-length prefix-free expansion:
        # Start with depth-1 codes; expand branches only as needed so total leaves >= count.
        codes = list(chars)
        while len(codes) < count:
            prefix = codes.pop(0)
            for ch in chars:
                codes.append(prefix + ch)
        return codes[:count]

    min_len = max(1, min_length)
    needed_len = max(min_len, math.ceil(math.log(max(count, 1), base)))
    if base**needed_len < count:
        needed_len += 1

    # Generate fixed-width lexicographic codes of length `needed_len`
    codes: list[str] = [""]
    for _ in range(needed_len):
        codes = [prefix + ch for prefix in codes for ch in chars]
        if len(codes) >= count and _ + 1 >= needed_len:
            break
    return codes[:count]


def visual_square_order(flipped: bool = False) -> list[chess.Square]:
    """Return all 64 squares ordered top-to-bottom, left-to-right as rendered."""
    ranks = range(8) if flipped else range(7, -1, -1)
    files = range(7, -1, -1) if flipped else range(8)
    return [chess.square(f, r) for r in ranks for f in files]


class HintEngine:
    """Computes and matches Vimium-style hint tags for chess squares."""

    def __init__(self, config: HintConfig) -> None:
        self.config = config
        self._static_cache_key: tuple[str, int, bool, tuple[tuple[str, str], ...]] | None = None
        self._static_map: dict[chess.Square, str] = {}

    def _build_static_map(self, flipped: bool) -> dict[chess.Square, str]:
        """Create a persistent 64-square tag map (respecting custom_square_map)."""
        custom_items = tuple(sorted(self.config.custom_square_map.items()))
        cache_key = (self.config.alphabet, max(2, self.config.min_length), flipped, custom_items)
        if self._static_cache_key == cache_key and self._static_map:
            return self._static_map

        mapping: dict[chess.Square, str] = {}
        used_codes: set[str] = set()

        for sq_name, code in self.config.custom_square_map.items():
            try:
                sq = chess.parse_square(sq_name.strip().lower())
            except ValueError:
                continue
            normalized = code if self.config.case_sensitive else code.upper()
            if normalized and normalized not in used_codes:
                mapping[sq] = normalized
                used_codes.add(normalized)

        ordered_squares = visual_square_order(flipped=flipped)
        remaining_squares = [sq for sq in ordered_squares if sq not in mapping]
        # Build fixed-length codes of length >= 2 so static 64-square codes never collide
        chars = _sanitize_alphabet(self.config.alphabet)
        min_len = max(2, self.config.min_length)
        if len(chars) >= 8 and min_len == 2:
            # Visual row-col grid encoding when alphabet has >= 8 chars:
            # Row 0 Col 1 -> "AB", Row 1 Col 2 -> "BC", matching intuitive coordinates!
            for idx, sq in enumerate(ordered_squares):
                if sq in mapping:
                    continue
                r_idx = idx // 8
                c_idx = idx % 8
                candidate = chars[r_idx] + chars[c_idx]
                if not self.config.case_sensitive:
                    candidate = candidate.upper()
                if candidate not in used_codes:
                    mapping[sq] = candidate
                    used_codes.add(candidate)

        still_missing = [sq for sq in remaining_squares if sq not in mapping]
        if still_missing:
            pool = generate_prefix_free_codes(
                len(still_missing) + len(used_codes),
                chars,
                min_length=min_len,
                smart_shortest=False,
            )
            pool_iter = (
                c if self.config.case_sensitive else c.upper()
                for c in pool
                if (c if self.config.case_sensitive else c.upper()) not in used_codes
            )
            for sq, code in zip(still_missing, pool_iter, strict=False):
                mapping[sq] = code
                used_codes.add(code)

        self._static_cache_key = cache_key
        self._static_map = mapping
        return mapping

    def candidate_squares(
        self,
        board: chess.Board,
        selected_square: chess.Square | None,
        *,
        flipped: bool = False,
        premove_mode: bool = False,
        player_color: chess.Color | None = None,
    ) -> list[chess.Square]:
        """Return valid target squares for the current selection stage in visual order."""
        order = visual_square_order(flipped=flipped)
        if selected_square is None:
            if premove_mode and player_color is not None:
                valid = {
                    sq
                    for sq in chess.SQUARES
                    if (p := board.piece_at(sq)) is not None and p.color == player_color
                }
            else:
                valid = {move.from_square for move in board.legal_moves}
            return [sq for sq in order if sq in valid]

        if premove_mode and self.config.show_premove_hints:
            valid = {sq for sq in chess.SQUARES if sq != selected_square}
        else:
            valid = {
                move.to_square
                for move in board.legal_moves
                if move.from_square == selected_square
            }
        return [sq for sq in order if sq in valid]

    def compute_hints(
        self,
        board: chess.Board,
        selected_square: chess.Square | None = None,
        *,
        flipped: bool = False,
        premove_mode: bool = False,
        player_color: chess.Color | None = None,
    ) -> dict[chess.Square, str]:
        """Compute active square -> hint tag mapping for current stage."""
        if not self.config.enabled:
            return {}

        targets = self.candidate_squares(
            board,
            selected_square,
            flipped=flipped,
            premove_mode=premove_mode,
            player_color=player_color,
        )
        if not targets:
            return {}

        mode = self.config.mode.lower().strip()
        if mode == "coordinate":
            return {
                sq: (chess.square_name(sq) if self.config.case_sensitive else chess.square_name(sq).upper())
                for sq in targets
            }

        if mode == "static":
            static_map = self._build_static_map(flipped=flipped)
            return {sq: static_map[sq] for sq in targets if sq in static_map}

        # "dynamic" or "smart"
        smart = mode == "smart"
        codes = generate_prefix_free_codes(
            len(targets),
            self.config.alphabet,
            min_length=self.config.min_length,
            smart_shortest=smart,
        )
        if not self.config.case_sensitive:
            codes = [c.upper() for c in codes]
        return dict(zip(targets, codes, strict=True))

    def match_buffer(self, hints: dict[chess.Square, str], buffer: str) -> HintMatchResult:
        """Match current typed hint buffer against active square hints."""
        if not buffer:
            return HintMatchResult(exact_square=None, matching_squares=dict(hints), has_matches=bool(hints))

        needle = buffer if self.config.case_sensitive else buffer.upper()
        matching: dict[chess.Square, str] = {}
        for sq, code in hints.items():
            haystack = code if self.config.case_sensitive else code.upper()
            if haystack == needle:
                return HintMatchResult(
                    exact_square=sq,
                    matching_squares={sq: code},
                    has_matches=True,
                )
            if haystack.startswith(needle):
                matching[sq] = code

        return HintMatchResult(
            exact_square=None,
            matching_squares=matching,
            has_matches=bool(matching),
        )
