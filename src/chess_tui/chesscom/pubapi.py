"""Official Chess.com Public Data API (PubAPI) client."""

from __future__ import annotations

from dataclasses import dataclass, field
import io
from typing import Any
from urllib.parse import quote

import chess.pgn
import httpx


PUBAPI_BASE = "https://api.chess.com/pub"


@dataclass(frozen=True, slots=True)
class PlayerProfile:
    """Chess.com player profile summary."""

    username: str
    url: str = ""
    name: str = ""
    title: str = ""
    country: str = ""
    followers: int = 0
    status: str = ""
    is_streamer: bool = False


@dataclass(frozen=True, slots=True)
class RatingRecord:
    """Rating + W/L/D record for one Chess.com time control."""

    rating: int = 0
    best_rating: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0


@dataclass(frozen=True, slots=True)
class PlayerStats:
    """Chess.com stats across formats."""

    bullet: RatingRecord | None = None
    blitz: RatingRecord | None = None
    rapid: RatingRecord | None = None
    daily: RatingRecord | None = None
    tactics_highest: int = 0
    puzzle_rush_best: int = 0


@dataclass(frozen=True, slots=True)
class DailyPuzzle:
    """Chess.com official Daily or Random Puzzle."""

    title: str
    url: str
    fen: str
    pgn: str
    solution_moves: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ArchivedGame:
    """Parsed Chess.com archived game summary."""

    url: str
    white_username: str
    white_rating: int
    white_result: str
    black_username: str
    black_rating: int
    black_result: str
    time_class: str
    time_control: str
    pgn: str
    end_time: int = 0
    rated: bool = True


def _parse_rating_record(raw: dict[str, Any] | None) -> RatingRecord | None:
    if not isinstance(raw, dict):
        return None
    last = raw.get("last") or {}
    best = raw.get("best") or {}
    record = raw.get("record") or {}
    return RatingRecord(
        rating=int(last.get("rating") or 0),
        best_rating=int(best.get("rating") or 0),
        wins=int(record.get("win") or 0),
        losses=int(record.get("loss") or 0),
        draws=int(record.get("draw") or 0),
    )


def _extract_pgn_moves(pgn_text: str, fen: str = "") -> list[str]:
    """Parse SAN move list from a Chess.com puzzle or game PGN."""
    if not pgn_text.strip():
        return []
    text = pgn_text
    if fen and "[FEN " not in text:
        text = f'[SetUp "1"]\n[FEN "{fen}"]\n\n{pgn_text}'
    game = chess.pgn.read_game(io.StringIO(text))
    if game is None:
        return []
    board = game.board()
    moves: list[str] = []
    for move in game.mainline_moves():
        moves.append(board.san(move))
        board.push(move)
    return moves


class ChessComPubApi:
    """Async client for Chess.com's official read-only Published-Data API."""

    def __init__(
        self,
        user_agent: str = "chess-tui/0.1.0 (https://github.com/Rutytoi220/chess-tui)",
        timeout: float = 12.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self._external_client = client

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }

    async def _get_json(self, url: str) -> dict[str, Any]:
        if self._external_client is not None:
            resp = await self._external_client.get(url, headers=self._headers(), timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        async with httpx.AsyncClient(headers=self._headers(), timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()

    async def get_player(self, username: str) -> PlayerProfile:
        """Fetch public profile for any Chess.com username."""
        safe = quote(username.strip().lower())
        data = await self._get_json(f"{PUBAPI_BASE}/player/{safe}")
        country_url = str(data.get("country") or "")
        country_code = country_url.rstrip("/").split("/")[-1] if country_url else ""
        return PlayerProfile(
            username=str(data.get("username") or username),
            url=str(data.get("url") or ""),
            name=str(data.get("name") or ""),
            title=str(data.get("title") or ""),
            country=country_code,
            followers=int(data.get("followers") or 0),
            status=str(data.get("status") or ""),
            is_streamer=bool(data.get("is_streamer") or False),
        )

    async def get_stats(self, username: str) -> PlayerStats:
        """Fetch rating and win/loss/draw stats for any Chess.com username."""
        safe = quote(username.strip().lower())
        data = await self._get_json(f"{PUBAPI_BASE}/player/{safe}/stats")
        tactics = (data.get("tactics") or {}).get("highest") or {}
        rush = (data.get("puzzle_rush") or {}).get("best") or {}
        return PlayerStats(
            bullet=_parse_rating_record(data.get("chess_bullet")),
            blitz=_parse_rating_record(data.get("chess_blitz")),
            rapid=_parse_rating_record(data.get("chess_rapid")),
            daily=_parse_rating_record(data.get("chess_daily")),
            tactics_highest=int(tactics.get("rating") or 0),
            puzzle_rush_best=int(rush.get("score") or 0),
        )

    async def get_archives(self, username: str) -> list[str]:
        """Return list of monthly archive URLs (newest last) for a player."""
        safe = quote(username.strip().lower())
        data = await self._get_json(f"{PUBAPI_BASE}/player/{safe}/games/archives")
        return [str(u) for u in (data.get("archives") or [])]

    async def get_archive_games(self, archive_url: str, limit: int = 50) -> list[ArchivedGame]:
        """Download and parse games from a monthly archive URL (most recent first)."""
        data = await self._get_json(archive_url)
        raw_games = list(data.get("games") or [])
        raw_games.reverse()
        parsed: list[ArchivedGame] = []
        for g in raw_games[:limit]:
            w = g.get("white") or {}
            b = g.get("black") or {}
            pgn = str(g.get("pgn") or "")
            if not pgn:
                continue
            parsed.append(
                ArchivedGame(
                    url=str(g.get("url") or ""),
                    white_username=str(w.get("username") or "White"),
                    white_rating=int(w.get("rating") or 0),
                    white_result=str(w.get("result") or ""),
                    black_username=str(b.get("username") or "Black"),
                    black_rating=int(b.get("rating") or 0),
                    black_result=str(b.get("result") or ""),
                    time_class=str(g.get("time_class") or ""),
                    time_control=str(g.get("time_control") or ""),
                    pgn=pgn,
                    end_time=int(g.get("end_time") or 0),
                    rated=bool(g.get("rated", True)),
                )
            )
        return parsed

    async def get_daily_puzzle(self, random: bool = False) -> DailyPuzzle:
        """Fetch Chess.com's official daily puzzle or a random daily puzzle."""
        endpoint = f"{PUBAPI_BASE}/puzzle/random" if random else f"{PUBAPI_BASE}/puzzle"
        data = await self._get_json(endpoint)
        pgn = str(data.get("pgn") or "")
        fen = str(data.get("fen") or "")
        return DailyPuzzle(
            title=str(data.get("title") or "Chess.com Daily Puzzle"),
            url=str(data.get("url") or ""),
            fen=fen,
            pgn=pgn,
            solution_moves=_extract_pgn_moves(pgn, fen=fen),
        )

    async def get_leaderboards(self) -> dict[str, list[dict[str, Any]]]:
        """Fetch Chess.com global leaderboards."""
        return await self._get_json(f"{PUBAPI_BASE}/leaderboards")
