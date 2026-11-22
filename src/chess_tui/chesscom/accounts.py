"""Multi-account Chess.com session & isolated browser profile manager."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import time
from typing import Any

from chess_tui.config.manager import default_data_dir


BROWSER_CANDIDATES = (
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "brave",
    "brave-browser",
    "vivaldi",
    "microsoft-edge",
)


@dataclass
class ChessComAccount:
    """Saved Chess.com account entry backed by an isolated persistent browser profile."""

    alias: str
    username: str = ""
    backend: str = "cdp"  # "cdp" or "extension"
    profile_dir: str = ""
    cdp_port: int = 9222
    last_login_at: str = ""
    last_pid: int = 0
    last_mode: str = ""
    notes: str = ""


def find_browser_binary(preferred: str = "auto") -> str | None:
    """Locate an installed Chromium-family browser binary supporting CDP."""
    if preferred and preferred != "auto":
        found = shutil.which(preferred)
        if found:
            return found
        if Path(preferred).exists():
            return preferred
        return None
    for candidate in BROWSER_CANDIDATES:
        found = shutil.which(candidate)
        if found:
            return found
    return None


def _is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) == 0


def _sanitize_alias(alias: str) -> str:
    cleaned = "".join(ch for ch in alias.strip().lower() if ch.isalnum() or ch in ("-", "_"))
    if not cleaned:
        raise ValueError("Account alias must contain alphanumeric characters.")
    return cleaned


class AccountManager:
    """Manages multiple Chess.com accounts with isolated persistent browser profiles."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or default_data_dir()
        self.accounts_file = self.data_dir / "accounts.json"
        self.profiles_root = self.data_dir / "profiles"
        self._accounts: dict[str, ChessComAccount] = {}
        self._processes: dict[str, subprocess.Popen[bytes]] = {}
        self.load()

    def load(self) -> dict[str, ChessComAccount]:
        self._accounts = {}
        valid_keys = {f.name for f in fields(ChessComAccount)}
        if self.accounts_file.exists():
            raw = json.loads(self.accounts_file.read_text(encoding="utf-8"))
            for item in raw.get("accounts", []):
                filtered = {k: v for k, v in item.items() if k in valid_keys}
                acc = ChessComAccount(**filtered)
                self._accounts[acc.alias] = acc
        return self._accounts

    def save(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = {"accounts": [asdict(acc) for acc in self._accounts.values()]}
        self.accounts_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return self.accounts_file

    def list_accounts(self) -> list[ChessComAccount]:
        return list(self._accounts.values())

    def get(self, alias: str) -> ChessComAccount | None:
        return self._accounts.get(alias.strip().lower())

    def _allocate_port(self, base: int = 9222) -> int:
        used = {acc.cdp_port for acc in self._accounts.values()}
        port = base
        while port in used or _is_port_in_use(port):
            port += 1
        return port

    def add_account(
        self,
        alias: str,
        *,
        username: str = "",
        backend: str = "cdp",
        notes: str = "",
    ) -> ChessComAccount:
        """Create or update a named Chess.com account profile."""
        clean_alias = _sanitize_alias(alias)
        existing = self._accounts.get(clean_alias)
        if existing is not None:
            if username:
                existing.username = username
            if notes:
                existing.notes = notes
            existing.backend = backend
            self.save()
            return existing

        profile_dir = self.profiles_root / clean_alias
        profile_dir.mkdir(parents=True, exist_ok=True)
        account = ChessComAccount(
            alias=clean_alias,
            username=username.strip(),
            backend=backend,
            profile_dir=str(profile_dir),
            cdp_port=self._allocate_port(),
            last_login_at="",
            notes=notes,
        )
        self._accounts[clean_alias] = account
        self.save()
        return account

    def update_username(self, alias: str, username: str) -> None:
        acc = self.get(alias)
        if acc is None:
            return
        clean = username.strip()
        if clean and acc.username != clean:
            acc.username = clean
            acc.last_login_at = datetime.now(UTC).isoformat(timespec="seconds")
            self.save()
        elif clean and not acc.last_login_at:
            acc.last_login_at = datetime.now(UTC).isoformat(timespec="seconds")
            self.save()

    def remove_account(self, alias: str, delete_profile_dir: bool = False) -> bool:
        clean_alias = alias.strip().lower()
        acc = self._accounts.pop(clean_alias, None)
        if acc is None:
            return False
        proc = self._processes.pop(clean_alias, None)
        if proc and proc.poll() is None:
            proc.terminate()
        if delete_profile_dir and acc.profile_dir:
            shutil.rmtree(acc.profile_dir, ignore_errors=True)
        self.save()
        return True

    def is_cdp_alive(self, account: ChessComAccount) -> bool:
        return _is_port_in_use(account.cdp_port)

    def has_saved_session(self, account: ChessComAccount) -> bool:
        """Return True if this account has previously logged in / stored browser cookies."""
        if account.last_login_at:
            return True
        if not account.profile_dir:
            return False
        prof = Path(account.profile_dir)
        return (prof / "Default" / "Cookies").exists() or (prof / "Default" / "Network" / "Cookies").exists()

    def stop_browser(self, alias: str) -> bool:
        """Terminate any Chromium process launched by chess-tui for `alias`."""
        clean_alias = alias.strip().lower()
        acc = self.get(clean_alias)
        stopped = False

        proc = self._processes.pop(clean_alias, None)
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
            stopped = True

        if acc and acc.last_pid > 0:
            try:
                os.kill(acc.last_pid, signal.SIGTERM)
                stopped = True
            except ProcessLookupError:
                pass
            except PermissionError:
                pass
            acc.last_pid = 0
            acc.last_mode = ""
            self.save()

        # Brief wait for CDP port release if terminated
        if acc and stopped:
            for _ in range(10):
                if not self.is_cdp_alive(acc):
                    break
                time.sleep(0.1)
        return stopped

    def stop_all_browsers(self) -> int:
        """Terminate all Chromium instances launched by chess-tui."""
        count = 0
        for alias in list(self._accounts.keys()):
            if self.stop_browser(alias):
                count += 1
        return count

    def launch_browser(
        self,
        account: ChessComAccount,
        *,
        browser_binary: str = "auto",
        extra_args: list[str] | None = None,
        start_url: str = "https://www.chess.com/login",
        headless: bool = False,
        disable_images: bool = True,
        force_relaunch: bool = False,
    ) -> tuple[bool, str]:
        """Launch an isolated Chromium profile for this account (visible or low-RAM headless)."""
        if self.is_cdp_alive(account):
            desired = "headless" if headless else "visible"
            if not force_relaunch or account.last_mode == desired:
                return True, f"Attached to running {account.last_mode or 'browser'} session on port {account.cdp_port}"
            self.stop_browser(account.alias)

        binary = find_browser_binary(browser_binary)
        if not binary:
            return (
                False,
                "No Chromium-based browser found (tried chromium, google-chrome, brave). "
                "Install Chromium or use the Browser Extension bridge in extension/.",
            )

        profile_path = Path(account.profile_dir or (self.profiles_root / account.alias))
        profile_path.mkdir(parents=True, exist_ok=True)
        if not account.profile_dir:
            account.profile_dir = str(profile_path)

        cmd: list[str] = [
            binary,
            f"--user-data-dir={profile_path}",
            f"--remote-debugging-port={account.cdp_port}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-sync",
            "--disable-background-networking",
            "--disable-default-apps",
            "--disable-component-update",
            "--mute-audio",
            "--disable-features=Translate,BackForwardCache,MediaRouter,OptimizationHints",
        ]
        if headless:
            cmd.extend([
                "--headless=new",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--renderer-process-limit=1",
                "--window-size=1280,900",
            ])
            if disable_images:
                cmd.append("--blink-settings=imagesEnabled=false")

        if extra_args:
            cmd.extend(extra_args)
        cmd.append(start_url)

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self._processes[account.alias] = proc
        account.last_pid = proc.pid
        account.last_mode = "headless" if headless else "visible"
        self.save()
        mode_lbl = "low-RAM headless" if headless else "visible"
        return True, f"Launched {Path(binary).name} ({mode_lbl}) for '{account.alias}' on port {account.cdp_port}"

    def to_summary(self, account: ChessComAccount) -> dict[str, Any]:
        return {
            "alias": account.alias,
            "username": account.username or "(not signed in yet)",
            "backend": account.backend,
            "cdp_port": account.cdp_port,
            "running": self.is_cdp_alive(account),
            "last_login_at": account.last_login_at,
        }
