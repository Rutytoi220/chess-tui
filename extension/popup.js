const statusEl = document.getElementById("status");
const wsUrlEl = document.getElementById("wsUrl");
const enabledEl = document.getElementById("enabled");
const saveBtn = document.getElementById("save");

chrome.runtime.sendMessage({ type: "get_status" }, (res) => {
  if (!res) return;
  wsUrlEl.value = res.wsUrl || "ws://127.0.0.1:8765";
  enabledEl.checked = res.enabled !== false;
  statusEl.textContent = res.connected
    ? "Connected to chess-tui"
    : "Waiting for chess-tui on " + wsUrlEl.value;
});

saveBtn.addEventListener("click", () => {
  chrome.runtime.sendMessage(
    {
      type: "update_settings",
      wsUrl: wsUrlEl.value.trim(),
      enabled: enabledEl.checked
    },
    () => {
      statusEl.textContent = "Saved! Reconnecting...";
    }
  );
});
