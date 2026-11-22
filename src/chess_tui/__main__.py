"""CLI entry point for chess-tui."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from chess_tui import __version__
from chess_tui.chesscom.accounts import AccountManager, find_browser_binary
from chess_tui.config.manager import ConfigManager, default_data_dir
from chess_tui.config.themes import THEMES
from chess_tui.engine.uci import find_uci_engine
from chess_tui.tui.app import ChessTuiApp


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chess-tui",
        description="Customizable Chess.com TUI with Vimium move hints & multi-account support.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--account", "-a", default="", help="Saved Chess.com account alias to connect on launch")
    parser.add_argument("--theme", "-t", default="", help="Override active theme preset")
    parser.add_argument("--puzzle", action="store_true", help="Open today's Chess.com Daily Puzzle on launch")
    parser.add_argument("--random-puzzle", action="store_true", help="Open a random Chess.com puzzle on launch")

    sub = parser.add_subparsers(dest="command")

    # Account subcommands
    acc_p = sub.add_parser("account", help="Manage saved Chess.com accounts")
    acc_sub = acc_p.add_subparsers(dest="acc_cmd", required=True)

    acc_sub.add_parser("list", help="List saved accounts")

    add_p = acc_sub.add_parser("add", help="Add an account profile and optionally launch login browser")
    add_p.add_argument("alias", help="Account alias (e.g. main, alt)")
    add_p.add_argument("--login", action="store_true", help="Immediately open visible browser to log in")

    login_p = acc_sub.add_parser("login", help="Launch visible browser window to log into an account")
    login_p.add_argument("alias", help="Account alias")

    rm_p = acc_sub.add_parser("remove", help="Remove an account entry")
    rm_p.add_argument("alias", help="Account alias")
    rm_p.add_argument("--purge", action="store_true", help="Also delete browser profile directory")

    # Config subcommands
    cfg_p = sub.add_parser("config", help="Manage configuration")
    cfg_sub = cfg_p.add_subparsers(dest="cfg_cmd", required=True)
    cfg_sub.add_parser("path", help="Show config file path")
    cfg_sub.add_parser("init", help="Create default config.toml if missing")
    cfg_sub.add_parser("themes", help="List built-in themes")

    # Doctor command
    sub.add_parser("doctor", help="Check browser, extension, UCI engine, and paths")

    return parser


def _run_doctor(cfg_mgr: ConfigManager, acc_mgr: AccountManager) -> int:
    cfg = cfg_mgr.config
    browser = find_browser_binary(cfg.bridge.browser_binary)
    uci = find_uci_engine(cfg.bridge.uci_engine_path)
    ext_dir = Path(__file__).resolve().parents[2] / "extension"

    print(f"chess-tui v{__version__}")
    print(f"  Config file   : {cfg_mgr.config_path} ({'exists' if cfg_mgr.config_path.exists() else 'defaults'})")
    print(f"  Data directory: {default_data_dir()}")
    print(f"  Browser (CDP) : {browser or 'NOT FOUND (install chromium/chrome/brave or use extension/)'}")
    print(f"  Extension dir : {ext_dir} ({'exists' if ext_dir.exists() else 'missing'})")
    print(f"  UCI engine    : {uci or 'none detected (optional, for offline play only)'}")
    print(f"  Saved accounts: {len(acc_mgr.list_accounts())}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    cfg_mgr = ConfigManager()
    cfg_mgr.ensure_exists()
    acc_mgr = AccountManager()

    if args.command == "doctor":
        return _run_doctor(cfg_mgr, acc_mgr)

    if args.command == "config":
        if args.cfg_cmd == "path":
            print(cfg_mgr.config_path)
            return 0
        if args.cfg_cmd == "init":
            path = cfg_mgr.save()
            print(f"Initialized {path}")
            return 0
        if args.cfg_cmd == "themes":
            for name, pal in THEMES.items():
                print(f"{name:<18} {pal.description}")
            return 0

    if args.command == "account":
        if args.acc_cmd == "list":
            accounts = acc_mgr.list_accounts()
            if not accounts:
                print("No saved accounts. Run: chess-tui account add main --login")
                return 0
            for a in accounts:
                status = "RUNNING" if acc_mgr.is_cdp_alive(a) else "stopped"
                print(f"{a.alias:<14} user={a.username or '(unknown)':<20} port={a.cdp_port} ({status})")
            return 0
        if args.acc_cmd == "add":
            acc = acc_mgr.add_account(args.alias)
            print(f"Saved account profile '{acc.alias}' (port {acc.cdp_port}, dir {acc.profile_dir})")
            if args.login:
                ok, msg = acc_mgr.launch_browser(
                    acc,
                    browser_binary=cfg_mgr.config.bridge.browser_binary,
                    extra_args=cfg_mgr.config.bridge.browser_extra_args,
                    start_url="https://www.chess.com/login",
                )
                print(msg)
                return 0 if ok else 1
            return 0
        if args.acc_cmd == "login":
            acc = acc_mgr.get(args.alias) or acc_mgr.add_account(args.alias)
            ok, msg = acc_mgr.launch_browser(
                acc,
                browser_binary=cfg_mgr.config.bridge.browser_binary,
                extra_args=cfg_mgr.config.bridge.browser_extra_args,
                start_url="https://www.chess.com/login",
            )
            print(msg)
            return 0 if ok else 1
        if args.acc_cmd == "remove":
            removed = acc_mgr.remove_account(args.alias, delete_profile_dir=args.purge)
            print("Removed." if removed else f"Account '{args.alias}' not found.")
            return 0 if removed else 1

    if args.theme:
        if args.theme not in THEMES:
            print(f"Unknown theme {args.theme!r}. Run 'chess-tui config themes' to list.", file=sys.stderr)
            return 2
        cfg_mgr.config.theme = args.theme

    app = ChessTuiApp(
        config_manager=cfg_mgr,
        account_manager=acc_mgr,
        initial_account=args.account,
        initial_puzzle=bool(args.puzzle or args.random_puzzle),
        initial_puzzle_random=bool(args.random_puzzle),
    )
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
