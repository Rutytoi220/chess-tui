"""Tests for AccountManager, DOM JS builders, and ExtensionWsBridge."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import websockets

from chess_tui.chesscom.accounts import AccountManager
from chess_tui.chesscom.dom_scripts import (
    READ_STATE_JS,
    build_click_action_js,
    build_promotion_coords_js,
    build_square_coords_js,
)
from chess_tui.chesscom.ws_bridge import ExtensionWsBridge


def test_account_manager_isolated_profiles(tmp_path: Path):
    mgr = AccountManager(data_dir=tmp_path)
    acc1 = mgr.add_account("Main")
    acc2 = mgr.add_account("Alt")

    assert acc1.alias == "main"
    assert acc2.alias == "alt"
    assert acc1.cdp_port != acc2.cdp_port
    assert Path(acc1.profile_dir).exists()
    assert Path(acc2.profile_dir).exists()

    mgr.update_username("main", "GM_Tester")
    reloaded = AccountManager(data_dir=tmp_path)
    assert reloaded.get("main") is not None
    assert reloaded.get("main").username == "GM_Tester"

    assert reloaded.remove_account("alt", delete_profile_dir=True) is True
    assert not Path(acc2.profile_dir).exists()


def test_dom_script_builders():
    assert "wc-chess-board" in READ_STATE_JS
    coords_js = build_square_coords_js("e2", "e4")
    assert '"e2"' in coords_js and '"e4"' in coords_js
    promo_js = build_promotion_coords_js("q")
    assert "wq" in promo_js
    act_js = build_click_action_js("resign")
    assert '"resign"' in act_js


async def test_extension_ws_bridge_roundtrip():
    received_states: list[dict] = []
    bridge = ExtensionWsBridge(host="127.0.0.1", port=0)

    # Bind on ephemeral port via websockets directly by picking an unused port
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    bridge = ExtensionWsBridge(host="127.0.0.1", port=port)

    async def on_state(payload: dict) -> None:
        received_states.append(payload)

    await bridge.start(on_state=on_state)
    try:
        async with websockets.connect(f"ws://127.0.0.1:{port}") as client:
            await client.send(
                json.dumps(
                    {
                        "type": "state_update",
                        "payload": {"hasBoard": True, "loggedInUser": "TestUser", "pieces": {"e2": "wp"}},
                    }
                )
            )
            await asyncio.sleep(0.05)
            assert len(received_states) == 1
            assert received_states[0]["loggedInUser"] == "TestUser"

            ok, _ = await bridge.send_move("e2", "e4", "q")
            assert ok is True
            cmd = json.loads(await asyncio.wait_for(client.recv(), timeout=1.0))
            assert cmd == {"type": "make_move", "fromSq": "e2", "toSq": "e4", "promotion": "q"}
    finally:
        await bridge.stop()
