"""Help modal showing Vimium workflow, current keybindings, and `:` commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static

if TYPE_CHECKING:
    from chess_tui.tui.app import ChessTuiApp


class HelpScreen(ModalScreen[None]):
    """In-app guide to Vimium chess moves, customization, and Chess.com accounts."""

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.72);
    }
    HelpScreen #help_dialog {
        width: 84;
        height: 34;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    HelpScreen .title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    HelpScreen Button {
        margin-top: 1;
    }
    """

    BINDINGS = [("escape", "dismiss_modal", "Close"), ("q", "dismiss_modal", "Close")]

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)

    def compose(self) -> ComposeResult:
        tui: ChessTuiApp = self.app  # type: ignore[assignment]
        kb = tui.config.input.keybindings
        content = f"""
VIMIUM MOVE SYSTEM
  1. Every movable piece displays a tag like "AB", "CD", ...
  2. Type the piece's tag (e.g. "AB") -> selects that piece.
  3. Legal destination squares immediately show fresh tags (e.g. "BC").
  4. Type the target tag ("BC") -> executes the move!
     - Esc clears selection/buffer. Backspace edits buffer.
     - On pawn promotion, press Q, R, B, or N.
     - Supports Dynamic, Static (fixed 64-square map), Smart, & Coordinate modes!

KEYBINDINGS (Customizable in config.toml)
  {kb.get('command_palette', ':'):<12} Open Vim command bar (:theme, :set, :fen, :resign...)
  {kb.get('san_input', '/'):<12} Quick SAN / UCI move input (/Nf3, /O-O, /e2e4)
  {kb.get('open_accounts', 'ctrl+a'):<12} Chess.com Multi-Account Manager (Add / Switch / Login)
  {kb.get('open_settings', 'ctrl+s'):<12} Interactive Customizer (Themes, Hints, Art, Layout)
  {kb.get('open_play', 'ctrl+p'):<12} Play Menu (Chess.com Online, Daily Puzzle, Local, UCI)
  {kb.get('open_archives', 'ctrl+g'):<12} Player Ratings & Game Archive Replay (PubAPI)
  {kb.get('flip_board', 'ctrl+f'):<12} Flip Board Orientation
  {kb.get('toggle_hints', 'ctrl+h'):<12} Toggle Vimium Hints On/Off
  {kb.get('toggle_zen', 'ctrl+z'):<12} Toggle Zen Mode (Hide Sidebar)
  {kb.get('toggle_blindfold', 'ctrl+b'):<12} Toggle Blindfold Mode
  {kb.get('cycle_theme', 'ctrl+t'):<12} Cycle Built-in Color Themes
  {kb.get('cycle_size', 'ctrl+y'):<12} Cycle Board Square Sizes (auto/compact/medium/large/huge)
  {kb.get('resign', 'ctrl+r'):<12} Resign Game
  {kb.get('offer_draw', 'ctrl+d'):<12} Offer / Accept Draw
  {kb.get('quit', 'ctrl+q'):<12} Quit

VIM COMMANDS (`:`)
  :theme <name>             Switch theme (e.g. :theme catppuccin-mocha)
  :pieces <style>           unicode-filled | unicode-dual | block | ascii | nerd
  :size <size>              auto | compact | medium | large | huge
  :hints <mode>             dynamic | static | smart | coordinate | off | on
  :alphabet <chars>         Change hint characters (e.g. :alphabet ASDFGHJKL)
  :set <dot.path> <val>     Mutate & save any config field!
  :preset save|load <name>  Save or load named config presets
  :account <alias>          Connect/launch Chess.com account profile
  :puzzle [random]          Play Chess.com Daily Puzzle
  :fen <fen>                Load custom FEN position
  :resign / :draw / :abort / :rematch / :newgame
"""
        with Container(id="help_dialog"):
            yield Label("CHESS-TUI HELP & COMMANDS", classes="title")
            with VerticalScroll():
                yield Static(content.strip())
            yield Button("Close [Esc]", id="btn_close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)
