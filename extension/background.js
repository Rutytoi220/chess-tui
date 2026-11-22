// Background WebSocket bridge between Chess.com content scripts and chess-tui

let ws = null;
let wsUrl = "ws://127.0.0.1:8765";
let enabled = true;
let connected = false;
let activeChessTabId = null;

chrome.storage.local.get(["wsUrl", "enabled"], (res) => {
  if (res.wsUrl) wsUrl = res.wsUrl;
  if (typeof res.enabled === "boolean") enabled = res.enabled;
  if (enabled) connectWs();
});

function connectWs() {
  if (!enabled) return;
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }
  try {
    ws = new WebSocket(wsUrl);
  } catch (err) {
    connected = false;
    setTimeout(connectWs, 3000);
    return;
  }

  ws.onopen = () => {
    connected = true;
    if (activeChessTabId !== null) {
      chrome.tabs.sendMessage(activeChessTabId, { type: "request_state" }).catch(() => {});
    }
  };

  ws.onmessage = (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch (_) {
      return;
    }
    if (msg.type === "navigate" && msg.url && activeChessTabId !== null) {
      chrome.tabs.update(activeChessTabId, { url: msg.url });
      return;
    }
    if ((msg.type === "make_move" || msg.type === "game_action") && activeChessTabId !== null) {
      chrome.tabs.sendMessage(activeChessTabId, msg).catch(() => {});
    }
  };

  ws.onclose = () => {
    connected = false;
    ws = null;
    if (enabled) setTimeout(connectWs, 2500);
  };

  ws.onerror = () => {
    connected = false;
  };
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "state_update" || msg.type === "hello") {
    if (sender.tab && sender.tab.id) {
      activeChessTabId = sender.tab.id;
    }
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(msg));
    }
    return false;
  }
  if (msg.type === "get_status") {
    sendResponse({ connected, enabled, wsUrl, activeChessTabId });
    return true;
  }
  if (msg.type === "update_settings") {
    if (typeof msg.enabled === "boolean") enabled = msg.enabled;
    if (msg.wsUrl) wsUrl = msg.wsUrl;
    chrome.storage.local.set({ wsUrl, enabled });
    if (ws) {
      ws.close();
      ws = null;
    }
    if (enabled) connectWs();
    sendResponse({ ok: true });
    return true;
  }
  return false;
});
