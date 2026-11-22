"""Chrome DevTools Protocol (CDP) bridge for live Chess.com browser control."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import itertools
import json
from typing import Any

import httpx
import websockets

from .dom_scripts import (
    READ_STATE_JS,
    build_click_action_js,
    build_click_play_button_js,
    build_promotion_coords_js,
    build_select_time_control_js,
    build_square_coords_js,
)


StateCallback = Callable[[dict[str, Any]], Awaitable[None] | None]


class CdpBridge:
    """Connects to an isolated Chromium instance via localhost CDP WebSocket."""

    def __init__(
        self,
        port: int = 9222,
        host: str = "127.0.0.1",
        poll_interval_ms: int = 200,
        move_method: str = "click",
        click_delay_ms: int = 45,
    ) -> None:
        self.host = host
        self.port = port
        self.poll_interval_ms = max(80, poll_interval_ms)
        self.move_method = move_method
        self.click_delay_ms = max(15, click_delay_ms)

        self._ws: Any = None
        self._id_gen = itertools.count(1)
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._recv_task: asyncio.Task[None] | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self._on_state: StateCallback | None = None
        self._connected = False
        self._target_url = ""

    @property
    def connected(self) -> bool:
        return self._connected and self._ws is not None

    async def discover_target_ws(self) -> tuple[str, str]:
        """Find the best Chess.com page tab WebSocket debugger URL."""
        url = f"http://{self.host}:{self.port}/json"
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            targets = resp.json()

        pages = [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
        if not pages:
            raise RuntimeError("No open browser page targets found on CDP port.")

        # Prefer active chess.com tab
        for p in pages:
            if "chess.com" in str(p.get("url", "")):
                return str(p["webSocketDebuggerUrl"]), str(p.get("url", ""))
        return str(pages[0]["webSocketDebuggerUrl"]), str(pages[0].get("url", ""))

    async def connect(self, on_state: StateCallback | None = None) -> str:
        """Connect to the CDP WebSocket and start polling Chess.com state."""
        self._on_state = on_state
        ws_url, page_url = await self.discover_target_ws()
        self._target_url = page_url
        self._ws = await websockets.connect(ws_url, max_size=4 * 1024 * 1024)
        self._connected = True
        self._recv_task = asyncio.create_task(self._recv_loop())
        await self._call("Page.enable")
        await self._call("Runtime.enable")
        self._poll_task = asyncio.create_task(self._poll_loop())
        return page_url

    async def disconnect(self) -> None:
        self._connected = False
        for task in (self._poll_task, self._recv_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._poll_task = None
        self._recv_task = None
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()

    async def _recv_loop(self) -> None:
        try:
            assert self._ws is not None
            async for raw in self._ws:
                msg = json.loads(raw)
                msg_id = msg.get("id")
                if msg_id is not None and msg_id in self._pending:
                    fut = self._pending.pop(msg_id)
                    if not fut.done():
                        fut.set_result(msg)
        except Exception:
            self._connected = False

    async def _call(self, method: str, params: dict[str, Any] | None = None, timeout: float = 5.0) -> dict[str, Any]:
        if not self._ws:
            raise RuntimeError("CDP WebSocket is not connected")
        cmd_id = next(self._id_gen)
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[cmd_id] = fut
        payload = {"id": cmd_id, "method": method, "params": params or {}}
        await self._ws.send(json.dumps(payload))
        res = await asyncio.wait_for(fut, timeout=timeout)
        if "error" in res:
            raise RuntimeError(str(res["error"]))
        return res.get("result", {})

    async def eval_js(self, expression: str) -> Any:
        res = await self._call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": False,
            },
        )
        remote = res.get("result") or {}
        return remote.get("value")

    async def read_state(self) -> dict[str, Any] | None:
        val = await self.eval_js(READ_STATE_JS)
        return val if isinstance(val, dict) else None

    async def _poll_loop(self) -> None:
        try:
            while self._connected:
                try:
                    state = await self.read_state()
                    if state and self._on_state is not None:
                        ret = self._on_state(state)
                        if asyncio.iscoroutine(ret):
                            await ret
                except asyncio.CancelledError:
                    raise
                except Exception:
                    # Page navigating or temporarily reloading; retry next tick
                    pass
                await asyncio.sleep(self.poll_interval_ms / 1000.0)
        except asyncio.CancelledError:
            pass

    async def _mouse_click(self, x: int, y: int) -> None:
        await self._call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
        await self._call(
            "Input.dispatchMouseEvent",
            {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1},
        )
        await self._call(
            "Input.dispatchMouseEvent",
            {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1},
        )

    async def _mouse_drag(self, x1: int, y1: int, x2: int, y2: int) -> None:
        await self._call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x1, "y": y1})
        await self._call(
            "Input.dispatchMouseEvent",
            {"type": "mousePressed", "x": x1, "y": y1, "button": "left", "clickCount": 1},
        )
        await asyncio.sleep(self.click_delay_ms / 1000.0)
        await self._call(
            "Input.dispatchMouseEvent",
            {"type": "mouseMoved", "x": x2, "y": y2, "button": "left", "buttons": 1},
        )
        await self._call(
            "Input.dispatchMouseEvent",
            {"type": "mouseReleased", "x": x2, "y": y2, "button": "left", "clickCount": 1},
        )

    async def send_move(self, from_sq: str, to_sq: str, promotion: str | None = None) -> tuple[bool, str]:
        """Dispatch genuine trusted browser pointer events to make a move on Chess.com."""
        coords = await self.eval_js(build_square_coords_js(from_sq, to_sq))
        if not isinstance(coords, dict) or not coords.get("ok"):
            return False, str((coords or {}).get("error") or "Unable to locate squares on Chess.com board")

        p1 = coords["from"]
        p2 = coords["to"]
        if self.move_method == "drag":
            await self._mouse_drag(p1["x"], p1["y"], p2["x"], p2["y"])
        else:
            await self._mouse_click(p1["x"], p1["y"])
            await asyncio.sleep(self.click_delay_ms / 1000.0)
            await self._mouse_click(p2["x"], p2["y"])

        if promotion:
            for _ in range(8):
                await asyncio.sleep(0.05)
                promo = await self.eval_js(build_promotion_coords_js(promotion))
                if isinstance(promo, dict) and promo.get("ok"):
                    await self._mouse_click(promo["x"], promo["y"])
                    break

        return True, f"Sent {from_sq}->{to_sq}" + (f"={promotion.upper()}" if promotion else "")

    async def navigate(self, url: str) -> None:
        await self._call("Page.navigate", {"url": url})

    async def trigger_action(self, action: str) -> tuple[bool, str]:
        res = await self.eval_js(build_click_action_js(action))
        if isinstance(res, dict) and res.get("ok"):
            return True, f"Action '{action}' triggered"
        return False, str((res or {}).get("error") or f"Action '{action}' failed")

    async def start_match(self, time_control: str = "") -> tuple[bool, str]:
        """Select a time control (if given) and click Play on Chess.com /play/online."""
        if time_control:
            res = await self.eval_js(build_select_time_control_js(time_control))
            if isinstance(res, dict) and res.get("openedSelector"):
                await asyncio.sleep(0.2)
                await self.eval_js(build_select_time_control_js(time_control))
            await asyncio.sleep(0.15)
        play_res = await self.eval_js(build_click_play_button_js())
        if isinstance(play_res, dict) and play_res.get("ok"):
            label = time_control or "default"
            return True, f"Searching Chess.com match ({label})..."
        return False, str((play_res or {}).get("error") or "Open chess.com/play/online and click Play")
