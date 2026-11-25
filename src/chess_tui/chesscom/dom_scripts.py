"""Shared JavaScript DOM bridge helpers for reading and interacting with Chess.com."""

from __future__ import annotations

import json


READ_STATE_JS = r"""
(() => {
  const url = window.location.href || "";
  const pathname = window.location.pathname || "";
  const isLoginPage = pathname.includes("/login") || !!document.querySelector("#login, input[name='_username'], #username");
  const hasChallenge = !!(
    document.querySelector("#challenge-running, #challenge-form, iframe[src*='challenges.cloudflare.com']") ||
    (document.title || "").toLowerCase().includes("just a moment")
  );

  // Detect logged-in Chess.com username from header/nav/page globals without touching credentials
  let loggedInUser = "";
  const ignoredNavWords = new Set([
    "profile", "home", "play", "puzzles", "learn", "watch", "news",
    "social", "more", "settings", "log in", "login", "sign up", "signup"
  ]);
  if (window.context && window.context.user && window.context.user.username) {
    loggedInUser = String(window.context.user.username).trim();
  }
  if (!loggedInUser) {
    const userSelectors = [
      ".nav-user-popover-username",
      ".home-username-link",
      ".sidebar-user-username",
      "a.user-username-link[href*='/member/']",
      ".user-menu-username",
      "[data-username]"
    ];
    for (const sel of userSelectors) {
      const el = document.querySelector(sel);
      if (!el) continue;
      let candidate = el.getAttribute("data-username") || (el.textContent || "").trim();
      if ((!candidate || ignoredNavWords.has(candidate.toLowerCase())) && el.getAttribute("href")) {
        const m = el.getAttribute("href").match(/\/member\/([^/?#]+)/);
        if (m) candidate = m[1];
      }
      candidate = (candidate || "").replace(/^@/, "").trim();
      if (candidate && candidate.length <= 40 && !ignoredNavWords.has(candidate.toLowerCase())) {
        loggedInUser = candidate;
        break;
      }
    }
  }

  // Locate chessboard component
  const board = document.querySelector("wc-chess-board, chess-board, .board");
  if (!board) {
    return {
      url,
      isLoginPage,
      hasChallenge,
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

  // Optional internal board game object FEN/PGN/turn/moves if exposed
  let fen = null;
  let pgn = null;
  let turn = null;
  let playerColor = null;
  const controllerMoves = [];
  try {
    const g = board.game || board._game;
    if (g) {
      if (typeof g.getFEN === "function") fen = g.getFEN();
      if (typeof g.getPGN === "function") {
        const rawPgn = g.getPGN();
        if (typeof rawPgn === "string" && rawPgn.trim()) pgn = rawPgn.trim();
      }
      if (typeof g.getTurn === "function") {
        const t = g.getTurn();
        turn = t === 1 || t === "w" ? "w" : t === 2 || t === "b" ? "b" : null;
      }
      if (typeof g.getPlayingAs === "function") {
        const p = g.getPlayingAs();
        playerColor = p === 1 || p === "w" ? "w" : p === 2 || p === "b" ? "b" : null;
      }
      const rawHistory =
        (typeof g.getHistory === "function" && g.getHistory()) ||
        (typeof g.getMoveList === "function" && g.getMoveList()) ||
        null;
      if (Array.isArray(rawHistory)) {
        for (const item of rawHistory) {
          const san = typeof item === "string" ? item : (item && (item.san || item.notation || item.text));
          if (typeof san === "string" && san.trim()) controllerMoves.push(san.trim());
        }
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

  // Extract SAN move list (checking controller, shadow roots, and modern Chess.com selectors)
  const moves = controllerMoves.length ? [...controllerMoves] : [];
  if (!moves.length) {
    const moveRoots = [document];
    for (const host of document.querySelectorAll("wc-simple-move-list, vertical-move-list, wc-move-list")) {
      if (host.shadowRoot) moveRoots.push(host.shadowRoot);
    }
    const moveSel = [
      "wc-simple-move-list [data-ply]",
      "vertical-move-list [data-ply]",
      ".move-list-wrapper [data-ply]",
      ".main-line-ply",
      "[data-node]",
      "wc-simple-move-list .node",
      "vertical-move-list .node",
      ".node-highlight-content",
    ].join(", ");
    const seenNodes = new Set();
    for (const r of moveRoots) {
      for (const node of r.querySelectorAll(moveSel)) {
        if (seenNodes.has(node)) continue;
        seenNodes.add(node);
        if (node.closest("[class*='time'], [class*='clock']") || /time|clock/i.test(node.className || "")) continue;
        const figEl = node.querySelector("[data-figurine]");
        const fig = figEl ? figEl.getAttribute("data-figurine") || "" : "";
        const clone = node.cloneNode(true);
        for (const rm of clone.querySelectorAll("[class*='time'], [class*='clock'], [data-cy*='time']")) {
          rm.remove();
        }
        let txt = (clone.textContent || "").replace(/\s+/g, "").trim();
        txt = txt.replace(/^\d+\.+/, "");
        if (!txt) continue;
        if (/^\d+(\.\d+)?[smhd]$/i.test(txt) || /^\d+:\d+/.test(txt)) continue;
        if (fig && !txt.startsWith(fig) && !txt.startsWith("O-")) {
          txt = fig + txt;
        }
        if (!/^(1-0|0-1|1\/2-1\/2|\*)$/.test(txt)) {
          moves.push(txt);
        }
      }
      if (moves.length) break;
    }
  }

  // Promotion dialog presence
  const promoOpen = !!root.querySelector(".promotion-window, .promotion-piece");

  // Detect whether /play/online is still showing the pre-match lobby preview board vs an active live match
  const inOnlineLobbyUrl = pathname.startsWith("/play/online") && !pathname.includes("/game/");
  const nonNavButtons = Array.from(document.querySelectorAll("button")).filter(b => {
    if (b.closest("nav, [role='navigation'], .nav-menu-area")) return false;
    const r = b.getBoundingClientRect();
    return r.width > 20 && r.height > 15;
  });
  const isSearching = nonNavButtons.some(b => {
    const t = (b.textContent || "").replace(/\s+/g, " ").trim().toLowerCase();
    return t === "cancel" || t.includes("cancel seek") || t.includes("searching");
  });
  const hasStartBtn = nonNavButtons.some(b => {
    const t = (b.textContent || "").replace(/\s+/g, " ").trim().toLowerCase();
    return t === "play" || t === "start game" || t === "new game";
  });
  const isLobbyPreview = !!(
    inOnlineLobbyUrl &&
    (isSearching ||
      hasStartBtn ||
      ((topPlayer.username === "Opponent" || !topPlayer.username) &&
        !topPlayer.isActive &&
        !bottomPlayer.isActive &&
        moves.length === 0))
  );

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
    hasChallenge,
    loggedInUser,
    hasBoard: true,
    isLobbyPreview,
    isSearching,
    flipped,
    pieces,
    lastMoveSquares,
    fen,
    pgn,
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
    """Return JS locating Chess.com's time-control selector or target option coordinates."""
    tc = json.dumps(time_control.strip().lower())
    return f"""
(() => {{
  const want = {tc};
  if (!want) return {{ ok: true, skipped: true }};
  const norm = s => (s || "").replace(/\\s+/g, " ").trim().toLowerCase();
  const aliases = [want];
  if (want.endsWith(" min")) {{
    const mins = want.replace(" min", "").trim();
    aliases.push(`${{mins}} | 0`, `${{mins}}|0`, `${{mins}}+0`, `${{mins}} min | 0 sec`);
  }} else if (want.includes("|")) {{
    aliases.push(want.replace(/\\s*\\|\\s*/g, "|"), want.replace(/\\s*\\|\\s*/g, " + "), want.replace(/\\s*\\|\\s*/g, "+"));
  }}
  const matchesWant = txt => aliases.some(a => txt === a || txt.startsWith(a + " "));

  const isVisibleNonNav = el => {{
    if (!el || el.disabled) return false;
    if (el.closest("nav, [role='navigation'], .nav-menu-area")) return false;
    const r = el.getBoundingClientRect();
    const st = window.getComputedStyle(el);
    return r.width > 20 && r.height > 15 && st.visibility !== "hidden" && st.display !== "none";
  }};
  const centerOf = el => {{
    const r = el.getBoundingClientRect();
    return {{ x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) }};
  }};

  const allBtns = Array.from(document.querySelectorAll("button, [role='button']")).filter(isVisibleNonNav);
  const timeLikeBtns = allBtns.filter(b => /^\\d+\\s*(min|\\|\\s*\\d+|\\+\\s*\\d+)/i.test(norm(b.textContent)));

  // If multiple time options are visible, the picker is already open -> pick our target!
  if (timeLikeBtns.length >= 2) {{
    const pick = timeLikeBtns.find(b => matchesWant(norm(b.textContent)));
    if (pick) {{
      return {{ ok: true, action: "pick", selected: norm(pick.textContent), ...centerOf(pick) }};
    }}
  }}

  // Check if a selector dropdown button is present
  const toggleSelectors = [
    "[data-cy='time-control-selector']",
    ".time-selector-component button",
    ".time-selector-component",
    ".selector-button-button",
    "button[class*='selector-button']"
  ];
  let toggle = null;
  for (const sel of toggleSelectors) {{
    const found = Array.from(document.querySelectorAll(sel)).find(isVisibleNonNav);
    if (found) {{
      toggle = found;
      break;
    }}
  }}
  if (!toggle && timeLikeBtns.length === 1) {{
    toggle = timeLikeBtns[0];
  }}

  if (toggle) {{
    const curTxt = norm(toggle.textContent);
    if (matchesWant(curTxt)) {{
      return {{ ok: true, alreadySelected: true, selected: curTxt }};
    }}
    return {{ ok: false, action: "open_selector", current: curTxt, ...centerOf(toggle) }};
  }}
  return {{ ok: false, error: "Time-control selector not found on page" }};
}})()
"""


def build_click_play_button_js() -> str:
    """Return JS locating the visible Play / Start Game button outside navigation menus."""
    return """
(() => {
  const norm = s => (s || "").replace(/\\s+/g, " ").trim().toLowerCase();
  const isVisibleNonNav = el => {
    if (!el || el.disabled || el.getAttribute("aria-disabled") === "true") return false;
    if (el.closest("nav, [role='navigation'], .nav-menu-area, header")) return false;
    const r = el.getBoundingClientRect();
    const st = window.getComputedStyle(el);
    return r.width >= 40 && r.height >= 20 && st.visibility !== "hidden" && st.display !== "none";
  };
  const centerOf = el => {
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) };
  };

  const allBtns = Array.from(document.querySelectorAll("button, a[role='button']")).filter(isVisibleNonNav);
  const cancelBtn = allBtns.find(b => {
    const t = norm(b.textContent);
    return t === "cancel" || t.includes("cancel seek");
  });
  if (cancelBtn) {
    return { ok: true, alreadySearching: true };
  }

  const prioritySelectors = [
    "button[data-cy='new-game-index-play']",
    "button[data-test*='play']",
    ".new-game-index-component button.cc-button-primary",
    ".create-game-component button.cc-button-primary",
    "#board-layout-sidebar button.cc-button-primary",
    "#board-layout-sidebar button.ui_v5-button-primary",
    "button.cc-button-primary",
    "button.ui_v5-button-primary"
  ];
  const playTexts = new Set(["play", "start game", "new game", "find match", "create game"]);

  for (const sel of prioritySelectors) {
    const matches = Array.from(document.querySelectorAll(sel)).filter(isVisibleNonNav);
    for (const el of matches) {
      const txt = norm(el.textContent);
      if (playTexts.has(txt) || txt.startsWith("play ")) {
        return { ok: true, clicked: txt, ...centerOf(el) };
      }
    }
  }

  for (const el of allBtns) {
    const txt = norm(el.textContent);
    if (playTexts.has(txt)) {
      return { ok: true, clicked: txt, ...centerOf(el) };
    }
  }
  return { ok: false, error: "Start/Play button not found outside navigation" };
})()
"""
