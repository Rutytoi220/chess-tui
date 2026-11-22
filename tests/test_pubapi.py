"""Tests for the official Chess.com PubAPI client using MockTransport."""

from __future__ import annotations

import httpx

from chess_tui.chesscom.pubapi import ChessComPubApi


def _mock_client() -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/pub/player/hikaru":
            return httpx.Response(
                200,
                json={
                    "username": "Hikaru",
                    "url": "https://www.chess.com/member/Hikaru",
                    "title": "GM",
                    "country": "https://api.chess.com/pub/country/US",
                    "followers": 1500000,
                    "status": "premium",
                },
            )
        if path == "/pub/player/hikaru/stats":
            return httpx.Response(
                200,
                json={
                    "chess_blitz": {
                        "last": {"rating": 3250},
                        "best": {"rating": 3330},
                        "record": {"win": 20000, "loss": 3000, "draw": 2000},
                    }
                },
            )
        if path == "/pub/player/hikaru/games/archives":
            return httpx.Response(
                200,
                json={"archives": ["https://api.chess.com/pub/player/hikaru/games/2026/11"]},
            )
        if path == "/pub/player/hikaru/games/2026/11":
            return httpx.Response(
                200,
                json={
                    "games": [
                        {
                            "url": "https://www.chess.com/game/live/999",
                            "time_class": "blitz",
                            "time_control": "180",
                            "pgn": '[Event "Live"]\n\n1. e4 e5 2. Nf3 Nc6 1-0',
                            "white": {"username": "Hikaru", "rating": 3250, "result": "win"},
                            "black": {"username": "Opp", "rating": 3100, "result": "resigned"},
                        }
                    ]
                },
            )
        if path == "/pub/puzzle":
            return httpx.Response(
                200,
                json={
                    "title": "Fork Practice",
                    "url": "https://www.chess.com/daily-puzzle",
                    "fen": "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3",
                    "pgn": "1. Bb5 a6 *",
                },
            )
        return httpx.Response(404, json={"message": "not found"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_pubapi_player_stats_archives_and_puzzle():
    async with _mock_client() as client:
        api = ChessComPubApi(client=client)

        prof = await api.get_player("Hikaru")
        assert prof.username == "Hikaru"
        assert prof.title == "GM"
        assert prof.country == "US"

        stats = await api.get_stats("Hikaru")
        assert stats.blitz is not None
        assert stats.blitz.rating == 3250

        archives = await api.get_archives("Hikaru")
        assert len(archives) == 1

        games = await api.get_archive_games(archives[0])
        assert len(games) == 1
        assert games[0].white_username == "Hikaru"

        puzzle = await api.get_daily_puzzle()
        assert puzzle.title == "Fork Practice"
        assert puzzle.solution_moves == ["Bb5", "a6"]
