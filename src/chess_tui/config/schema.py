"""Strongly-typed configuration schema for chess-tui."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class HintConfig:
    """Vimium-style hint engine configuration."""

    enabled: bool = True
    # "dynamic" (only movable pieces -> only legal targets),
    # "static" (persistent 64-square hint map),
    # "smart" (shortest prefix-free tags like classic Vimium)
    mode: str = "dynamic"
    # Characters used to construct hint labels (e.g. "ABCDEFGMNOPQRSTUVWXYZ", "ASDFGHJKL")
    alphabet: str = "ABCDEFGMNOPQRSTUVWXYZ"
    # Minimum hint length: 2 gives classic "AB" / "BC" style tags
    min_length: int = 2
    case_sensitive: bool = False
    # Hint placement within each square: "top-left", "top-right", "bottom-left", "bottom-right", "center"
    position: str = "top-left"
    # Show destination hints on all squares during premove / opponent turn
    show_premove_hints: bool = True
    # Dim hints that do not match the currently typed prefix
    dim_non_matching: bool = True
    # Automatically clear hint buffer after N seconds of inactivity (0 = never)
    timeout_seconds: float = 0.0
    # Promotion choice keys mapped to piece letters
    promotion_keys: dict[str, str] = field(
        default_factory=lambda: {"Q": "q", "R": "r", "B": "b", "N": "n"}
    )
    # Optional explicit 64-square map for static mode (e.g. {"e2": "AB", "e4": "BC", ...})
    custom_square_map: dict[str, str] = field(default_factory=dict)


@dataclass
class BoardConfig:
    """Visual board rendering customization."""

    # "auto", "compact", "medium", "large", "huge", "giant"
    square_size: str = "auto"
    # "auto" (large block art when space fits, unicode when compact),
    # "block", "unicode-filled", "unicode-dual", "ascii", "ascii-upper", "nerd", "custom"
    piece_style: str = "auto"
    # Custom 12-piece map used when piece_style == "custom"
    custom_pieces: dict[str, str] = field(
        default_factory=lambda: {
            "K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "P": "♙",
            "k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟",
        }
    )
    # "rounded", "double", "heavy", "ascii", "none"
    border_style: str = "rounded"
    # "outside", "inside", "none"
    coordinates: str = "outside"
    # "auto" (match player color), "white", "black"
    orientation: str = "auto"
    # Legal move marker style: "dot", "ring", "tint", "both", "none"
    legal_move_indicator: str = "dot"
    highlight_last_move: bool = True
    highlight_check: bool = True
    highlight_selected: bool = True
    blindfold: bool = False
    show_square_cursor: bool = True


@dataclass
class LayoutConfig:
    """TUI panel & widget layout customization."""

    # "right", "left", "none"
    sidebar_position: str = "right"
    sidebar_width: int = 32
    show_clocks: bool = True
    show_players: bool = True
    show_captured: bool = True
    show_material_diff: bool = True
    show_move_list: bool = True
    show_status_log: bool = True
    show_hint_legend: bool = True
    show_header: bool = True
    show_footer: bool = True
    zen_mode: bool = False
    # Low-time warning threshold in seconds
    low_time_seconds: int = 20
    # Terminal bell on opponent move / game start
    sound_bell: bool = False


@dataclass
class InputConfig:
    """Keyboard & mouse interaction settings."""

    # Allow typing SAN ("Nf3", "e4", "O-O") or UCI ("e2e4") via `/` or command bar
    allow_san_command: bool = True
    # Allow vim-style cursor navigation (arrows + hjkl)
    allow_cursor_navigation: bool = True
    # "always" = hjkl always move cursor (h/j/k/l excluded from hints),
    # "auto"   = hjkl move cursor when not used by active hint alphabet,
    # "off"    = arrow keys only
    hjkl_navigation: str = "always"
    allow_mouse_clicks: bool = True
    # Confirm before resigning or aborting a live game
    confirm_resign: bool = True
    # Keybindings map (action -> key string)
    keybindings: dict[str, str] = field(
        default_factory=lambda: {
            "command_palette": ":",
            "san_input": "/",
            "cancel": "escape",
            "backspace": "backspace",
            "flip_board": "ctrl+f",
            "toggle_hints": "ctrl+h",
            "toggle_zen": "ctrl+z",
            "toggle_blindfold": "ctrl+b",
            "open_accounts": "ctrl+a",
            "open_settings": "ctrl+s",
            "open_play": "ctrl+p",
            "open_archives": "ctrl+g",
            "open_share": "ctrl+e",
            "open_help": "?",
            "cycle_theme": "ctrl+t",
            "cycle_size": "ctrl+y",
            "cycle_pieces": "ctrl+o",
            "resign": "ctrl+r",
            "offer_draw": "ctrl+d",
            "new_game": "ctrl+n",
            "quit": "ctrl+c",
        }
    )


@dataclass
class BridgeConfig:
    """Chess.com connection, browser launcher, and PubAPI configuration."""

    # Contact email or identifier included in official Chess.com PubAPI User-Agent header
    pubapi_user_agent: str = "chess-tui/0.1.0 (https://github.com/Rutytoi220/chess-tui)"
    # Preferred browser binary for managed accounts ("auto", "chromium", "google-chrome", "brave", or path)
    browser_binary: str = "auto"
    # "auto" (visible for first login, stripped low-RAM headless once logged in), "headless", or "visible"
    browser_mode: str = "auto"
    # Disable image decoding in headless mode to slash RAM usage (board DOM still works 100%)
    disable_images_in_headless: bool = True
    # Block heavy third-party ads/analytics/media assets via CDP Network.setBlockedURLs
    block_heavy_assets: bool = True
    # Terminate TUI-launched Chromium when exiting chess-tui so zero background RAM stays used
    auto_close_browser_on_exit: bool = True
    # Auto-connect default_account on startup (keeps you logged in across restarts!)
    auto_connect_on_start: bool = True
    # Extra flags passed when launching managed Chromium
    browser_extra_args: list[str] = field(default_factory=list)
    # Local WebSocket port for the optional Chrome/Firefox extension bridge
    extension_ws_host: str = "127.0.0.1"
    extension_ws_port: int = 8765
    extension_auto_start: bool = True
    # Poll interval (ms) for syncing live Chess.com board & clocks over CDP
    cdp_poll_interval_ms: int = 200
    # Prefer CDP drag (mousedown->mousemove->mouseup) vs click-to-move (click from -> click to)
    move_dispatch_method: str = "click"
    # Delay in ms between source square click and destination square click
    click_delay_ms: int = 45
    # Optional path to local UCI engine (e.g. "stockfish") - strictly offline/analysis only!
    uci_engine_path: str = ""
    uci_skill_level: int = 10


@dataclass
class ChessTuiConfig:
    """Root configuration object persisted to TOML."""

    theme: str = "chesscom-green"
    theme_overrides: dict[str, str] = field(default_factory=dict)
    default_account: str = ""
    hints: HintConfig = field(default_factory=HintConfig)
    board: BoardConfig = field(default_factory=BoardConfig)
    layout: LayoutConfig = field(default_factory=LayoutConfig)
    input: InputConfig = field(default_factory=InputConfig)
    bridge: BridgeConfig = field(default_factory=BridgeConfig)

    def to_dict(self) -> dict[str, Any]:
        """Serialize config cleanly to nested dicts."""
        return asdict(self)
