"""Local WebSocket bridge server for the bundled Chrome/Firefox Browser Extension."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import json
from typing import Any

import websockets
from websockets.asyncio.server import Server, ServerConnection


StateCallback = Callable[[dict[str, Any]], Awaitable[None] | None]


class ExtensionWsBridge:
    """Hosts a localhost WebSocket server that the browser extension connects to."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.host = host
        self.port = port
        self._server: Server | None = None
        self._clients: set[ServerConnection] = set()
        self._on_state: StateCallback | None = None
        self._last_error: str = ""

    @property
    def is_running(self) -> bool:
        return self._server is not None

    @property
    def client_count(self) -> int:
        return len(self._clients)

    @property
    def last_error(self) -> str:
        return self._last_error

    async def start(self, on_state: StateCallback | None = None) -> None:
        if self._server is not None:
            return
        self._on_state = on_state
        try:
            self._server = await websockets.serve(self._handle_client, self.host, self.port)
            self._last_error = ""
        except OSError as exc:
            self._last_error = str(exc)
            raise

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        for ws in list(self._clients):
            try:
                await ws.close()
            except Exception:
                pass
        self._clients.clear()

    async def _handle_client(self, ws: ServerConnection) -> None:
        self._clients.add(ws)
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                msg_type = msg.get("type")
                if msg_type in ("state_update", "hello") and self._on_state is not None:
                    payload = msg.get("payload") or {}
                    if isinstance(payload, dict):
                        ret = self._on_state(payload)
                        if asyncio.iscoroutine(ret):
                            await ret
                elif msg_type == "ping":
                    await ws.send(json.dumps({"type": "pong"}))
        except Exception:
            pass
        finally:
            self._clients.discard(ws)

    async def _broadcast(self, message: dict[str, Any]) -> bool:
        if not self._clients:
            return False
        raw = json.dumps(message)
        sent = False
        for ws in list(self._clients):
            try:
                await ws.send(raw)
                sent = True
            except Exception:
                self._clients.discard(ws)
        return sent

    async def send_move(self, from_sq: str, to_sq: str, promotion: str | None = None) -> tuple[bool, str]:
        ok = await self._broadcast(
            {
                "type": "make_move",
                "fromSq": from_sq.lower(),
                "toSq": to_sq.lower(),
                "promotion": promotion.lower() if promotion else None,
            }
        )
        if ok:
            return True, f"Sent {from_sq}->{to_sq} via Extension"
        return False, "No browser extension connected"

    async def navigate(self, url: str) -> bool:
        return await self._broadcast({"type": "navigate", "url": url})

    async def trigger_action(self, action: str) -> tuple[bool, str]:
        ok = await self._broadcast({"type": "game_action", "action": action})
        if ok:
            return True, f"Sent '{action}' via Extension"
        return False, "No browser extension connected"
