"""Optional local UCI engine integration (strictly for offline/analysis play)."""

from __future__ import annotations

import asyncio
import shutil

import chess
import chess.engine


def find_uci_engine(configured_path: str = "") -> str | None:
    """Find an installed local UCI engine binary (e.g., stockfish)."""
    if configured_path:
        found = shutil.which(configured_path) or (configured_path if configured_path else None)
        if found:
            return found
    for candidate in ("stockfish", "lc0", "komodo", "ethereal"):
        found = shutil.which(candidate)
        if found:
            return found
    return None


class LocalUciEngine:
    """Async wrapper around python-chess SimpleEngine / popen_uci."""

    def __init__(self, binary_path: str, skill_level: int = 10) -> None:
        self.binary_path = binary_path
        self.skill_level = max(0, min(20, skill_level))
        self._transport: asyncio.SubprocessTransport | None = None
        self._engine: chess.engine.UciProtocol | None = None

    async def start(self) -> None:
        if self._engine is not None:
            return
        self._transport, self._engine = await chess.engine.popen_uci(self.binary_path)
        try:
            await self._engine.configure({"Skill Level": self.skill_level})
        except chess.engine.EngineError:
            pass

    async def best_move(self, board: chess.Board, time_limit: float = 0.5) -> chess.Move | None:
        if self._engine is None:
            await self.start()
        assert self._engine is not None
        result = await self._engine.play(board, chess.engine.Limit(time=time_limit))
        return result.move

    async def stop(self) -> None:
        if self._engine is not None:
            try:
                await self._engine.quit()
            except Exception:
                pass
            self._engine = None
            self._transport = None
