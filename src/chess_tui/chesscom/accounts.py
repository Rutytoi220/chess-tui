"""Multi-account Chess.com session & isolated browser profile manager."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, UTC
import json
from pathlib import Path
import shutil
import socket
import subprocess
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
        if self.accounts_file.exists():
            raw = json.loads(self.accounts_file.read_text(encoding="utf-8"))
            for item in raw.get("accounts", []):
                acc = ChessComAccount(**item)
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

    def launch_browser(
        self,
        account: ChessComAccount,
        *,
        browser_binary: str = "auto",
        extra_args: list[str] | None = None,
        start_url: str = "https://www.chess.com/login",
    ) -> tuple[bool, str]:
        """Launch a visible isolated browser window for this account if not already running.

        The user signs in manually in the visible window (supporting passwords, 2FA, SSO,
        and any human verification challenge). Session cookies persist in `account.profile_dir`.
        """
        if self.is_cdp_alive(account):
            return True, f"Attached to running browser session on port {account.cdp_port}"

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
            self.save()

        cmd: list[str] = [
            binary,
            f"--user-data-dir={profile_path}",
            f"--remote-debugging-port={account.cdp_port}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
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
        return True, f"Launched {Path(binary).name} for '{account.alias}' on CDP port {account.cdp_port}"

    def to_summary(self, account: ChessComAccount) -> dict[str, Any]:
        return {
            "alias": account.alias,
            "username": account.username or "(not signed in yet)",
            "backend": account.backend,
            "cdp_port": account.cdp_port,
            "running": self.is_cdp_alive(account),
            "last_login_at": account.last_login_at,
        }
