"""Shared JavaScript DOM bridge helpers for reading and interacting with Chess.com."""

from __future__ import annotations

import json


READ_STATE_JS = r"""
(() => {
  const url = window.location.href || "";
  const pathname = window.location.pathname || "";
  const isLoginPage = pathname.includes("/login") || !!document.querySelector("#login, input[name='_username'], #username");

  // Detect logged-in Chess.com username from header/nav/page globals without touching credentials
  let loggedInUser = "";
  const userSelectors = [
    "[data-user-activity-key]",
    ".nav-user-popover-username",
    ".home-username-link",
    "a.user-username-link[href*='/member/']",
    ".sidebar-user-username",
    "#user-popover-trigger",
    "[data-username]"
  ];
  for (const sel of userSelectors) {
    const el = document.querySelector(sel);
    if (!el) continue;
    const candidate =
      el.getAttribute("data-username") ||
      el.getAttribute("data-user-activity-key") ||
      (el.textContent || "").trim();
    if (candidate && candidate.length <= 40 && !candidate.includes("Log In")) {
      loggedInUser = candidate.replace(/^@/, "");
      break;
    }
  }
  if (!loggedInUser && window.context && window.context.user && window.context.user.username) {
    loggedInUser = String(window.context.user.username);
  }

  // Locate chessboard component
  const board = document.querySelector("wc-chess-board, chess-board, .board");
  if (!board) {
    return {
      url,
      isLoginPage,
      loggedInUser,
      hasBoard: false,
      pieces: {},
      moves: [],
      flipped: false,
    };
  }

  const root = board.shadowRoot || board;
  const flipped = board.classList.contains("flipped");

  // Parse pieces from Chess.com `.piece` classes (e.g. `piece wp square-52`)
  const pieces = {};
  const pieceEls = root.querySelectorAll(".piece");
  for (const el of pieceEls) {
    const cls = el.className || "";
    const sqMatch = cls.match(/square-(\d)(\d)/);
    const pieceMatch = cls.match(/\b([wb][prnbqk])\b/);
    if (!sqMatch || !pieceMatch) continue;
    const fileIdx = parseInt(sqMatch[1], 10);
    const rankIdx = parseInt(sqMatch[2], 10);
    if (fileIdx < 1 || fileIdx > 8 || rankIdx < 1 || rankIdx > 8) continue;
    const sqName = String.fromCharCode(96 + fileIdx) + String(rankIdx);
    pieces[sqName] = pieceMatch[1];
  }

  // Last move highlights
  const lastMoveSquares = [];
  for (const el of root.querySelectorAll(".highlight")) {
    const cls = el.className || "";
    const sqMatch = cls.match(/square-(\d)(\d)/);
    if (sqMatch) {
      const f = parseInt(sqMatch[1], 10);
      const r = parseInt(sqMatch[2], 10);
      if (f >= 1 && f <= 8 && r >= 1 && r <= 8) {
        const sq = String.fromCharCode(96 + f) + String(r);
        if (!lastMoveSquares.includes(sq)) lastMoveSquares.push(sq);
      }
    }
  }

  // Optional internal board game object FEN/turn if exposed
  let fen = null;
  let turn = null;
  let playerColor = null;
  try {
    const g = board.game || board._game;
    if (g) {
      if (typeof g.getFEN === "function") fen = g.getFEN();
      if (typeof g.getTurn === "function") {
        const t = g.getTurn();
        turn = t === 1 || t === "w" ? "w" : t === 2 || t === "b" ? "b" : null;
      }
      if (typeof g.getPlayingAs === "function") {
        const p = g.getPlayingAs();
        playerColor = p === 1 || p === "w" ? "w" : p === 2 || p === "b" ? "b" : null;
      }
    }
  } catch (_) {}

  function readPlayerPanel(selector) {
    const panel = document.querySelector(selector);
    if (!panel) return {};
    const nameEl = panel.querySelector(".user-username-component, .user-tagline-username, [data-test-element='user-tagline-username'], .player-name");
    const ratingEl = panel.querySelector(".user-tagline-rating, .player-rating");
    const titleEl = panel.querySelector(".user-chess-title-component, .player-title");
    const clockEl = panel.querySelector(".clock-component, [role='timer'], .clock-time-monospace");
    const clockTextEl = panel.querySelector(".clock-time-monospace") || clockEl;
    const isActive = !!(
      clockEl &&
      (clockEl.classList.contains("clock-player-turn") ||
        clockEl.classList.contains("clock-running") ||
        clockEl.getAttribute("data-running") === "true")
    );
    return {
      username: nameEl ? (nameEl.textContent || "").trim() : "",
      rating: ratingEl ? (ratingEl.textContent || "").replace(/[()]/g, "").trim() : "",
      title: titleEl ? (titleEl.textContent || "").trim() : "",
      clock: clockTextEl ? (clockTextEl.textContent || "").trim() : "--:--",
      isActive,
    };
  }

  const topPlayer = readPlayerPanel("#board-layout-player-top, .player-top");
  const bottomPlayer = readPlayerPanel("#board-layout-player-bottom, .player-bottom");

  // Extract SAN move list
  const moves = [];
  const moveNodes = document.querySelectorAll(
    "wc-simple-move-list [data-ply], vertical-move-list [data-ply], .move-list-wrapper [data-ply], wc-simple-move-list .node, vertical-move-list .node"
  );
  for (const node of moveNodes) {
    // Handle Chess.com figurine font attributes if present (`data-figurine="N"`)
    const figEl = node.querySelector("[data-figurine]");
    const fig = figEl ? figEl.getAttribute("data-figurine") || "" : "";
    let txt = (node.textContent || "").replace(/\s+/g, "").trim();
    txt = txt.replace(/^\d+\.+/, "");
    if (!txt) continue;
    if (fig && !txt.startsWith(fig) && !txt.startsWith("O-")) {
      txt = fig + txt;
    }
    if (!/^(1-0|0-1|1\/2-1\/2|\*)$/.test(txt)) {
      moves.push(txt);
    }
  }

  // Promotion dialog presence
  const promoOpen = !!root.querySelector(".promotion-window, .promotion-piece");

  // Game over modal
  const gameOverModal = document.querySelector(
    ".game-over-modal-content, .modal-game-over-component, .game-result-component"
  );
  let gameOver = { isOver: false, score: "", reason: "" };
  if (gameOverModal) {
    const titleEl = gameOverModal.querySelector(".header-title-component, h2, .game-over-header-title");
    const subEl = gameOverModal.querySelector(".header-subtitle-component, .game-over-header-subtitle, p");
    gameOver = {
      isOver: true,
      score: titleEl ? (titleEl.textContent || "").trim() : "Game Over",
      reason: subEl ? (subEl.textContent || "").trim() : "",
    };
  }

  return {
    url,
    isLoginPage,
    loggedInUser,
    hasBoard: true,
    flipped,
    pieces,
    lastMoveSquares,
    fen,
    turn,
    playerColor,
    topPlayer,
    bottomPlayer,
    moves,
    promoOpen,
    gameOver,
  };
})()
"""


def build_square_coords_js(from_sq: str, to_sq: str) -> str:
    """Return JS evaluating exact viewport coordinates for `from_sq` and `to_sq`."""
    payload = json.dumps({"fromSq": from_sq.lower(), "toSq": to_sq.lower()})
    return f"""
(() => {{
  const args = {payload};
  const board = document.querySelector("wc-chess-board, chess-board, .board");
  if (!board) return {{ ok: false, error: "No Chess.com board found on page" }};
  const rect = board.getBoundingClientRect();
  if (!rect || rect.width <= 0 || rect.height <= 0) {{
    return {{ ok: false, error: "Board has zero bounding rect" }};
  }}
  const flipped = board.classList.contains("flipped");
  function centerOf(sq) {{
    const fileIdx = sq.charCodeAt(0) - 97; // 0..7
    const rankIdx = parseInt(sq[1], 10) - 1; // 0..7
    const col = flipped ? (7 - fileIdx) : fileIdx;
    const row = flipped ? rankIdx : (7 - rankIdx);
    const sqW = rect.width / 8;
    const sqH = rect.height / 8;
    return {{
      x: Math.round(rect.left + (col + 0.5) * sqW),
      y: Math.round(rect.top + (row + 0.5) * sqH),
    }};
  }}
  return {{
    ok: true,
    flipped,
    from: centerOf(args.fromSq),
    to: centerOf(args.toSq),
  }};
}})()
"""


def build_promotion_coords_js(piece_char: str) -> str:
    """Return JS locating a visible promotion option button ('q','r','b','n')."""
    p = piece_char.lower()
    return f"""
(() => {{
  const board = document.querySelector("wc-chess-board, chess-board, .board");
  const root = (board && board.shadowRoot) || board || document;
  const candidates = root.querySelectorAll(".promotion-window .promotion-piece, .promotion-piece");
  for (const el of candidates) {{
    const cls = el.className || "";
    if (cls.includes("w{p}") || cls.includes("b{p}") || el.getAttribute("data-piece") === "{p}") {{
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) {{
        return {{ ok: true, x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) }};
      }}
    }}
  }}
  return {{ ok: false }};
}})()
"""


def build_click_action_js(action: str) -> str:
    """Return JS performing common Chess.com game controls (resign, draw, abort, rematch, new_game)."""
    act = json.dumps(action)
    return f"""
(() => {{
  const action = {act};
  function clickMatch(selectors, textMatches) {{
    for (const sel of selectors) {{
      const els = document.querySelectorAll(sel);
      for (const el of els) {{
        const txt = (el.textContent || el.getAttribute("aria-label") || "").trim().toLowerCase();
        if (!textMatches.length || textMatches.some(t => txt.includes(t))) {{
          el.click();
          return {{ ok: true, clicked: txt || sel }};
        }}
      }}
    }}
    return null;
  }}

  if (action === "resign") {{
    return clickMatch(
      ["button.resign-button-component", "button[aria-label*='Resign']", "button"],
      ["resign"]
    ) || {{ ok: false, error: "Resign button not found" }};
  }}
  if (action === "draw") {{
    return clickMatch(
      ["button.draw-button-component", "button[aria-label*='Draw']", "button"],
      ["draw", "accept draw"]
    ) || {{ ok: false, error: "Draw button not found" }};
  }}
  if (action === "abort") {{
    return clickMatch(
      ["button[aria-label*='Abort']", "button"],
      ["abort"]
    ) || {{ ok: false, error: "Abort button not found" }};
  }}
  if (action === "rematch") {{
    return clickMatch(
      ["button[data-cy='rematch-button']", "button"],
      ["rematch"]
    ) || {{ ok: false, error: "Rematch button not found" }};
  }}
  if (action === "new_game") {{
    return clickMatch(
      ["button[data-cy='new-game-index-play']", "button.new-game-button", "button"],
      ["new game", "play"]
    ) || {{ ok: false, error: "New Game button not found" }};
  }}
  if (action === "confirm") {{
    return clickMatch(
      [".ui_modal-component button", "button.cc-button-primary", "button"],
      ["yes", "confirm", "resign"]
    ) || {{ ok: false, error: "Confirm button not found" }};
  }}
  return {{ ok: false, error: "Unknown action: " + action }};
}})()
"""


def build_select_time_control_js(time_control: str) -> str:
    """Return JS opening Chess.com's time-control selector and picking `time_control` (e.g. '3 min')."""
    tc = json.dumps(time_control.strip().lower())
    return f"""
(() => {{
  const want = {tc};
  if (!want) return {{ ok: true, skipped: true }};
  const norm = s => (s || "").replace(/\\s+/g, " ").trim().toLowerCase();

  // Check if time option is already visible on page
  const allBtns = Array.from(document.querySelectorAll("button, [role='button']"));
  let match = allBtns.find(b => norm(b.textContent) === want);
  if (match) {{
    match.click();
    return {{ ok: true, selected: norm(match.textContent) }};
  }}

  // Otherwise open the time selector dropdown
  const toggle = document.querySelector(
    ".time-selector-component, [data-cy='time-control-selector'], .selector-button-button"
  );
  if (toggle) {{
    toggle.click();
    return {{ ok: false, openedSelector: true }};
  }}
  return {{ ok: false, error: "Time selector not found" }};
}})()
"""


def build_click_play_button_js() -> str:
    """Return JS clicking the primary Play / Start Game button on /play/online."""
    return """
(() => {
  const candidates = [
    ...document.querySelectorAll("button[data-cy='new-game-index-play']"),
    ...document.querySelectorAll("button.cc-button-primary, button.ui_v5-button-primary"),
    ...document.querySelectorAll("button")
  ];
  for (const el of candidates) {
    const txt = (el.textContent || "").replace(/\\s+/g, " ").trim().toLowerCase();
    if (txt === "play" || txt === "start game" || txt === "new game") {
      el.click();
      return { ok: true, clicked: txt };
    }
  }
  return { ok: false, error: "Play button not found on page" };
})()
"""
