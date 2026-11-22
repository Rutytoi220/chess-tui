// Content script running on https://www.chess.com/* to sync board state & execute moves

(() => {
  let lastSnapshotJson = "";

  function readState() {
    const url = window.location.href || "";
    const pathname = window.location.pathname || "";
    const isLoginPage =
      pathname.includes("/login") ||
      !!document.querySelector("#login, input[name='_username'], #username");

    let loggedInUser = "";
    const ignoredNavWords = new Set([
      "profile", "home", "play", "puzzles", "learn", "watch", "news",
      "social", "more", "settings", "log in", "login", "sign up", "signup"
    ]);
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

    const board = document.querySelector("wc-chess-board, chess-board, .board");
    if (!board) {
      return {
        url,
        isLoginPage,
        loggedInUser,
        hasBoard: false,
        pieces: {},
        moves: [],
        flipped: false
      };
    }

    const root = board.shadowRoot || board;
    const flipped = board.classList.contains("flipped");
    const pieces = {};
    for (const el of root.querySelectorAll(".piece")) {
      const cls = el.className || "";
      const sqMatch = cls.match(/square-(\d)(\d)/);
      const pieceMatch = cls.match(/\b([wb][prnbqk])\b/);
      if (!sqMatch || !pieceMatch) continue;
      const f = parseInt(sqMatch[1], 10);
      const r = parseInt(sqMatch[2], 10);
      if (f < 1 || f > 8 || r < 1 || r > 8) continue;
      pieces[String.fromCharCode(96 + f) + String(r)] = pieceMatch[1];
    }

    const lastMoveSquares = [];
    for (const el of root.querySelectorAll(".highlight")) {
      const sqMatch = (el.className || "").match(/square-(\d)(\d)/);
      if (sqMatch) {
        const f = parseInt(sqMatch[1], 10);
        const r = parseInt(sqMatch[2], 10);
        if (f >= 1 && f <= 8 && r >= 1 && r <= 8) {
          const sq = String.fromCharCode(96 + f) + String(r);
          if (!lastMoveSquares.includes(sq)) lastMoveSquares.push(sq);
        }
      }
    }

    function readPlayerPanel(sel) {
      const panel = document.querySelector(sel);
      if (!panel) return {};
      const nameEl = panel.querySelector(
        ".user-username-component, .user-tagline-username, [data-test-element='user-tagline-username'], .player-name"
      );
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
        isActive
      };
    }

    const moves = [];
    const moveNodes = document.querySelectorAll(
      "wc-simple-move-list [data-ply], vertical-move-list [data-ply], .move-list-wrapper [data-ply], wc-simple-move-list .node, vertical-move-list .node"
    );
    for (const node of moveNodes) {
      if (node.closest("[class*='time'], [class*='clock']") || /time|clock/i.test(node.className || "")) continue;
      const figEl = node.querySelector("[data-figurine]");
      const fig = figEl ? figEl.getAttribute("data-figurine") || "" : "";
      const clone = node.cloneNode(true);
      for (const rm of clone.querySelectorAll("[class*='time'], [class*='clock'], [data-cy*='time']")) {
        rm.remove();
      }
      let txt = (clone.textContent || "").replace(/\s+/g, "").trim().replace(/^\d+\.+/, "");
      if (!txt) continue;
      if (/^\d+(\.\d+)?[smhd]$/i.test(txt) || /^\d+:\d+/.test(txt)) continue;
      if (fig && !txt.startsWith(fig) && !txt.startsWith("O-")) txt = fig + txt;
      if (!/^(1-0|0-1|1\/2-1\/2|\*)$/.test(txt)) moves.push(txt);
    }

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
        reason: subEl ? (subEl.textContent || "").trim() : ""
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
      topPlayer: readPlayerPanel("#board-layout-player-top, .player-top"),
      bottomPlayer: readPlayerPanel("#board-layout-player-bottom, .player-bottom"),
      moves,
      gameOver
    };
  }

  function dispatchClickAt(target, x, y) {
    const opts = { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y, button: 0, buttons: 1 };
    target.dispatchEvent(new PointerEvent("pointerdown", opts));
    target.dispatchEvent(new MouseEvent("mousedown", opts));
    target.dispatchEvent(new PointerEvent("pointerup", { ...opts, buttons: 0 }));
    target.dispatchEvent(new MouseEvent("mouseup", { ...opts, buttons: 0 }));
    target.dispatchEvent(new MouseEvent("click", { ...opts, buttons: 0 }));
  }

  function squareCenter(board, sq) {
    const rect = board.getBoundingClientRect();
    const flipped = board.classList.contains("flipped");
    const fileIdx = sq.charCodeAt(0) - 97;
    const rankIdx = parseInt(sq[1], 10) - 1;
    const col = flipped ? 7 - fileIdx : fileIdx;
    const row = flipped ? rankIdx : 7 - rankIdx;
    return {
      x: rect.left + (col + 0.5) * (rect.width / 8),
      y: rect.top + (row + 0.5) * (rect.height / 8)
    };
  }

  function performMove(fromSq, toSq, promotion) {
    const board = document.querySelector("wc-chess-board, chess-board, .board");
    if (!board) return;
    const p1 = squareCenter(board, fromSq);
    const p2 = squareCenter(board, toSq);
    const el1 = document.elementFromPoint(p1.x, p1.y) || board;
    dispatchClickAt(el1, p1.x, p1.y);
    setTimeout(() => {
      const el2 = document.elementFromPoint(p2.x, p2.y) || board;
      dispatchClickAt(el2, p2.x, p2.y);
      if (promotion) {
        setTimeout(() => {
          const root = board.shadowRoot || board;
          for (const el of root.querySelectorAll(".promotion-window .promotion-piece, .promotion-piece")) {
            const cls = el.className || "";
            if (cls.includes("w" + promotion) || cls.includes("b" + promotion)) {
              const r = el.getBoundingClientRect();
              dispatchClickAt(el, r.left + r.width / 2, r.top + r.height / 2);
              break;
            }
          }
        }, 80);
      }
    }, 50);
  }

  function pushState(force = false) {
    const snap = readState();
    const serialized = JSON.stringify(snap);
    if (!force && serialized === lastSnapshotJson) return;
    lastSnapshotJson = serialized;
    chrome.runtime.sendMessage({ type: "state_update", payload: snap }).catch(() => {});
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "request_state") {
      pushState(true);
    } else if (msg.type === "make_move" && msg.fromSq && msg.toSq) {
      performMove(msg.fromSq, msg.toSq, msg.promotion || null);
    } else if (msg.type === "game_action") {
      const action = String(msg.action || "");
      const btns = Array.from(document.querySelectorAll("button"));
      const match = btns.find((b) =>
        (b.textContent || b.getAttribute("aria-label") || "").toLowerCase().includes(action.replace("_", " "))
      );
      if (match) match.click();
    }
  });

  setInterval(() => pushState(false), 250);
  pushState(true);
})();
