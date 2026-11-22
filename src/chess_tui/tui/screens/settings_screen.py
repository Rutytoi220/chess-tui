"""Interactive live customization modal ("customizable af" config editor)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual import events
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Button, Input, Label, Select, Static, Switch, TabbedContent, TabPane

from chess_tui.config.themes import THEMES
from chess_tui.tui.screens.base import VimModalScreen

if TYPE_CHECKING:
    from chess_tui.tui.app import ChessTuiApp


class SettingsScreen(VimModalScreen):
    """Full live customization modal for themes, Vimium hints, board rendering, layout, and presets."""

    DEFAULT_CSS = """
    SettingsScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.72);
    }
    SettingsScreen #settings_dialog {
        width: 92;
        height: 38;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    SettingsScreen .title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    SettingsScreen TabbedContent {
        height: 1fr;
    }
    SettingsScreen .setting_row {
        height: auto;
        margin-bottom: 1;
        align: left middle;
    }
    SettingsScreen .setting_label {
        width: 28;
        color: $text;
    }
    SettingsScreen Select, SettingsScreen Input {
        width: 1fr;
    }
    SettingsScreen .btn_bar {
        height: 3;
        margin-top: 1;
        align: right middle;
    }
    SettingsScreen Button {
        margin-left: 1;
    }
    SettingsScreen #settings_msg {
        color: $success;
        height: 1;
    }
    """

    BINDINGS = [("escape", "save_and_close", "Save & Close")]

    def compose(self) -> ComposeResult:
        tui: ChessTuiApp = self.app  # type: ignore[assignment]
        cfg = tui.config

        theme_opts = [(f"{name} — {t.description}", name) for name, t in THEMES.items()]
        preset_opts = [(p, p) for p in tui.config_manager.list_presets()]

        with Container(id="settings_dialog"):
            yield Label(
                "CUSTOMIZE CHESS-TUI  (1-4 or [ / ] or h/l to switch tabs • Esc to save)",
                classes="title",
            )
            with TabbedContent(id="settings_tabs"):
                with TabPane("1: Vimium Hints", id="tab_hints"):
                    with VerticalScroll():
                        with Horizontal(classes="setting_row"):
                            yield Label("Enable Vimium Hints", classes="setting_label")
                            yield Switch(value=cfg.hints.enabled, id="hints_enabled")
                        with Horizontal(classes="setting_row"):
                            yield Label("Hint Mode", classes="setting_label")
                            yield Select(
                                [
                                    ("Dynamic (pieces -> legal targets)", "dynamic"),
                                    ("Static (persistent 64-square map)", "static"),
                                    ("Smart (shortest prefix-free)", "smart"),
                                    ("Coordinate (e2 -> e4)", "coordinate"),
                                ],
                                value=cfg.hints.mode,
                                id="hints_mode",
                                allow_blank=False,
                            )
                        with Horizontal(classes="setting_row"):
                            yield Label("Hint Alphabet", classes="setting_label")
                            yield Input(value=cfg.hints.alphabet, id="hints_alphabet")
                        with Horizontal(classes="setting_row"):
                            yield Label("Quick Alphabets", classes="setting_label")
                            yield Button("Standard (AB..)", id="alpha_std")
                            yield Button("Home Row (ASDF..)", id="alpha_home")
                            yield Button("8x8 Grid (A-H)", id="alpha_grid")
                        with Horizontal(classes="setting_row"):
                            yield Label("Minimum Tag Length", classes="setting_label")
                            yield Select(
                                [("1 char (fast)", "1"), ("2 chars (AB / BC)", "2"), ("3 chars", "3")],
                                value=str(cfg.hints.min_length),
                                id="hints_min_length",
                                allow_blank=False,
                            )
                        with Horizontal(classes="setting_row"):
                            yield Label("Hint Badge Position", classes="setting_label")
                            yield Select(
                                [
                                    ("Top-Left", "top-left"),
                                    ("Top-Right", "top-right"),
                                    ("Bottom-Left", "bottom-left"),
                                    ("Bottom-Right", "bottom-right"),
                                    ("Center", "center"),
                                ],
                                value=cfg.hints.position,
                                id="hints_position",
                                allow_blank=False,
                            )
                        with Horizontal(classes="setting_row"):
                            yield Label("Dim Non-Matching Hints", classes="setting_label")
                            yield Switch(value=cfg.hints.dim_non_matching, id="hints_dim")
                        with Horizontal(classes="setting_row"):
                            yield Label("Case Sensitive Hints", classes="setting_label")
                            yield Switch(value=cfg.hints.case_sensitive, id="hints_case")
                        with Horizontal(classes="setting_row"):
                            yield Label("Premove Hints on Enemy Turn", classes="setting_label")
                            yield Switch(value=cfg.hints.show_premove_hints, id="hints_premove")

                with TabPane("2: Theme & Board", id="tab_board"):
                    with VerticalScroll():
                        with Horizontal(classes="setting_row"):
                            yield Label("Theme Preset", classes="setting_label")
                            yield Select(theme_opts, value=cfg.theme, id="theme_select", allow_blank=False)
                        with Horizontal(classes="setting_row"):
                            yield Label("Piece Art Style", classes="setting_label")
                            yield Select(
                                [
                                    ("Auto (Staunton Braille on large, unicode small)", "auto"),
                                    ("Staunton Braille Art (14x12 smooth)", "braille"),
                                    ("Line Art (smooth box/curves)", "line-art"),
                                    ("Multi-line Block Art (5x3/7x3/9x4)", "block"),
                                    ("Unicode Filled (♚♛♜♝♞♟)", "unicode-filled"),
                                    ("Unicode Dual (♔♕ vs ♚♛)", "unicode-dual"),
                                    ("ASCII (K Q R vs k q r)", "ascii"),
                                    ("ASCII Uppercase", "ascii-upper"),
                                    ("Nerd Font Icons", "nerd"),
                                    ("Custom (from config.toml)", "custom"),
                                ],
                                value=cfg.board.piece_style,
                                id="board_piece_style",
                                allow_blank=False,
                            )
                        with Horizontal(classes="setting_row"):
                            yield Label("Square Size", classes="setting_label")
                            yield Select(
                                [
                                    ("Auto (fill terminal)", "auto"),
                                    ("Compact (5x1)", "compact"),
                                    ("Medium (7x3)", "medium"),
                                    ("Large (9x4)", "large"),
                                    ("Huge (11x5)", "huge"),
                                    ("Giant (13x6)", "giant"),
                                ],
                                value=cfg.board.square_size,
                                id="board_square_size",
                                allow_blank=False,
                            )
                        with Horizontal(classes="setting_row"):
                            yield Label("Border Style", classes="setting_label")
                            yield Select(
                                [
                                    ("Rounded", "rounded"),
                                    ("Double", "double"),
                                    ("Heavy", "heavy"),
                                    ("ASCII", "ascii"),
                                    ("None", "none"),
                                ],
                                value=cfg.board.border_style,
                                id="board_border",
                                allow_blank=False,
                            )
                        with Horizontal(classes="setting_row"):
                            yield Label("Coordinates", classes="setting_label")
                            yield Select(
                                [("Outside", "outside"), ("Inside", "inside"), ("Hidden", "none")],
                                value=cfg.board.coordinates,
                                id="board_coords",
                                allow_blank=False,
                            )
                        with Horizontal(classes="setting_row"):
                            yield Label("Legal Move Indicator", classes="setting_label")
                            yield Select(
                                [
                                    ("Dot (●)", "dot"),
                                    ("Ring (○)", "ring"),
                                    ("Tint Square", "tint"),
                                    ("Dot + Tint", "both"),
                                    ("None", "none"),
                                ],
                                value=cfg.board.legal_move_indicator,
                                id="board_legal_ind",
                                allow_blank=False,
                            )
                        with Horizontal(classes="setting_row"):
                            yield Label("Orientation", classes="setting_label")
                            yield Select(
                                [("Auto (match color)", "auto"), ("White Bottom", "white"), ("Black Bottom", "black")],
                                value=cfg.board.orientation,
                                id="board_orientation",
                                allow_blank=False,
                            )
                        with Horizontal(classes="setting_row"):
                            yield Label("Blindfold Mode", classes="setting_label")
                            yield Switch(value=cfg.board.blindfold, id="board_blindfold")

                with TabPane("3: Layout & Bridge", id="tab_layout"):
                    with VerticalScroll():
                        with Horizontal(classes="setting_row"):
                            yield Label("Sidebar Position", classes="setting_label")
                            yield Select(
                                [("Right", "right"), ("Left", "left"), ("Hidden", "none")],
                                value=cfg.layout.sidebar_position,
                                id="layout_sidebar_pos",
                                allow_blank=False,
                            )
                        with Horizontal(classes="setting_row"):
                            yield Label("Vim hjkl Navigation", classes="setting_label")
                            yield Select(
                                [
                                    ("Always (h/j/k/l move cursor, excluded from hints)", "always"),
                                    ("Auto (yield when HJKL in hint alphabet)", "auto"),
                                    ("Off (arrows only)", "off"),
                                ],
                                value=cfg.input.hjkl_navigation,
                                id="input_hjkl",
                                allow_blank=False,
                            )
                        with Horizontal(classes="setting_row"):
                            yield Label("Show Clocks", classes="setting_label")
                            yield Switch(value=cfg.layout.show_clocks, id="layout_clocks")
                        with Horizontal(classes="setting_row"):
                            yield Label("Show Captured & Material", classes="setting_label")
                            yield Switch(value=cfg.layout.show_captured, id="layout_captured")
                        with Horizontal(classes="setting_row"):
                            yield Label("Show Move List", classes="setting_label")
                            yield Switch(value=cfg.layout.show_move_list, id="layout_moves")
                        with Horizontal(classes="setting_row"):
                            yield Label("Zen Mode (Board Only)", classes="setting_label")
                            yield Switch(value=cfg.layout.zen_mode, id="layout_zen")
                        with Horizontal(classes="setting_row"):
                            yield Label("Terminal Sound Bell", classes="setting_label")
                            yield Switch(value=cfg.layout.sound_bell, id="layout_bell")
                        with Horizontal(classes="setting_row"):
                            yield Label("Chess.com Browser Mode", classes="setting_label")
                            yield Select(
                                [
                                    ("Auto (visible login -> low-RAM headless)", "auto"),
                                    ("Headless (always low-RAM background)", "headless"),
                                    ("Visible (always show browser window)", "visible"),
                                ],
                                value=cfg.bridge.browser_mode,
                                id="bridge_browser_mode",
                                allow_blank=False,
                            )
                        with Horizontal(classes="setting_row"):
                            yield Label("Disable Images in Headless", classes="setting_label")
                            yield Switch(value=cfg.bridge.disable_images_in_headless, id="bridge_no_images")
                        with Horizontal(classes="setting_row"):
                            yield Label("Auto-Stop Browser on Exit", classes="setting_label")
                            yield Switch(value=cfg.bridge.auto_close_browser_on_exit, id="bridge_auto_close")
                        with Horizontal(classes="setting_row"):
                            yield Label("Chess.com Move Method", classes="setting_label")
                            yield Select(
                                [("Click-to-move", "click"), ("Drag-and-drop", "drag")],
                                value=cfg.bridge.move_dispatch_method,
                                id="bridge_move_method",
                                allow_blank=False,
                            )
                        with Horizontal(classes="setting_row"):
                            yield Label("Offline UCI Engine Path", classes="setting_label")
                            yield Input(value=cfg.bridge.uci_engine_path, placeholder="e.g. stockfish", id="bridge_uci_path")

                with TabPane("4: Colors & Presets", id="tab_presets"):
                    with VerticalScroll():
                        with Horizontal(classes="setting_row"):
                            yield Label("Light Square Hex", classes="setting_label")
                            yield Input(
                                value=cfg.theme_overrides.get("light_square_bg", ""),
                                placeholder="Override hex (e.g. #EEEED2)",
                                id="ovr_light",
                            )
                        with Horizontal(classes="setting_row"):
                            yield Label("Dark Square Hex", classes="setting_label")
                            yield Input(
                                value=cfg.theme_overrides.get("dark_square_bg", ""),
                                placeholder="Override hex (e.g. #769656)",
                                id="ovr_dark",
                            )
                        with Horizontal(classes="setting_row"):
                            yield Label("Hint Badge Bg Hex", classes="setting_label")
                            yield Input(
                                value=cfg.theme_overrides.get("hint_bg", ""),
                                placeholder="Override hex (e.g. #FFE066)",
                                id="ovr_hint_bg",
                            )
                        with Horizontal(classes="setting_row"):
                            yield Label("Hint Badge Text Hex", classes="setting_label")
                            yield Input(
                                value=cfg.theme_overrides.get("hint_fg", ""),
                                placeholder="Override hex (e.g. #111111)",
                                id="ovr_hint_fg",
                            )
                        with Horizontal(classes="setting_row"):
                            yield Label("Save Named Preset", classes="setting_label")
                            yield Input(placeholder="Preset name (e.g. blitz-block)", id="preset_name_input")
                            yield Button("Save Preset", id="btn_save_preset")
                        if preset_opts:
                            with Horizontal(classes="setting_row"):
                                yield Label("Load Saved Preset", classes="setting_label")
                                yield Select(preset_opts, id="preset_select", prompt="Choose preset...")
                                yield Button("Load Preset", id="btn_load_preset")
                        with Horizontal(classes="setting_row"):
                            yield Label("Config File Path", classes="setting_label")
                            yield Static(str(tui.config_manager.config_path))

            yield Static("", id="settings_msg")
            with Horizontal(classes="btn_bar"):
                yield Button("Clear Color Overrides", id="btn_clear_overrides")
                yield Button("Apply & Save [Esc]", id="btn_apply", variant="success")

    def _apply_form(self) -> None:
        tui: ChessTuiApp = self.app  # type: ignore[assignment]
        cfg = tui.config

        cfg.hints.enabled = self.query_one("#hints_enabled", Switch).value
        cfg.hints.mode = str(self.query_one("#hints_mode", Select).value)
        alpha = self.query_one("#hints_alphabet", Input).value.strip()
        if len(alpha) >= 2:
            cfg.hints.alphabet = alpha
        cfg.hints.min_length = int(str(self.query_one("#hints_min_length", Select).value))
        cfg.hints.position = str(self.query_one("#hints_position", Select).value)
        cfg.hints.dim_non_matching = self.query_one("#hints_dim", Switch).value
        cfg.hints.case_sensitive = self.query_one("#hints_case", Switch).value
        cfg.hints.show_premove_hints = self.query_one("#hints_premove", Switch).value

        cfg.theme = str(self.query_one("#theme_select", Select).value)
        cfg.board.piece_style = str(self.query_one("#board_piece_style", Select).value)
        cfg.board.square_size = str(self.query_one("#board_square_size", Select).value)
        cfg.board.border_style = str(self.query_one("#board_border", Select).value)
        cfg.board.coordinates = str(self.query_one("#board_coords", Select).value)
        cfg.board.legal_move_indicator = str(self.query_one("#board_legal_ind", Select).value)
        cfg.board.orientation = str(self.query_one("#board_orientation", Select).value)
        cfg.board.blindfold = self.query_one("#board_blindfold", Switch).value

        cfg.layout.sidebar_position = str(self.query_one("#layout_sidebar_pos", Select).value)
        cfg.input.hjkl_navigation = str(self.query_one("#input_hjkl", Select).value)
        cfg.layout.show_clocks = self.query_one("#layout_clocks", Switch).value
        cfg.layout.show_captured = self.query_one("#layout_captured", Switch).value
        cfg.layout.show_move_list = self.query_one("#layout_moves", Switch).value
        cfg.layout.zen_mode = self.query_one("#layout_zen", Switch).value
        cfg.layout.sound_bell = self.query_one("#layout_bell", Switch).value
        cfg.bridge.browser_mode = str(self.query_one("#bridge_browser_mode", Select).value)
        cfg.bridge.disable_images_in_headless = self.query_one("#bridge_no_images", Switch).value
        cfg.bridge.auto_close_browser_on_exit = self.query_one("#bridge_auto_close", Switch).value
        cfg.bridge.move_dispatch_method = str(self.query_one("#bridge_move_method", Select).value)
        cfg.bridge.uci_engine_path = self.query_one("#bridge_uci_path", Input).value.strip()

        for key, inp_id in (
            ("light_square_bg", "#ovr_light"),
            ("dark_square_bg", "#ovr_dark"),
            ("hint_bg", "#ovr_hint_bg"),
            ("hint_fg", "#ovr_hint_fg"),
        ):
            val = self.query_one(inp_id, Input).value.strip()
            if val:
                cfg.theme_overrides[key] = val
            else:
                cfg.theme_overrides.pop(key, None)

        tui.config_manager.save()
        tui.apply_config()

    def action_save_and_close(self) -> None:
        self._apply_form()
        self.dismiss(None)

    def on_key(self, event: events.Key) -> None:
        if not isinstance(self.focused, Input):
            tab_map = {
                "1": "tab_hints",
                "2": "tab_board",
                "3": "tab_layout",
                "4": "tab_presets",
            }
            if event.character in tab_map:
                self.query_one("#settings_tabs", TabbedContent).active = tab_map[event.character]
                event.prevent_default()
                event.stop()
                return
            if event.character in ("]", "L"):
                self._switch_tab(forward=True)
                event.prevent_default()
                event.stop()
                return
            if event.character in ("[", "H"):
                self._switch_tab(forward=False)
                event.prevent_default()
                event.stop()
                return
        super().on_key(event)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        tui: ChessTuiApp = self.app  # type: ignore[assignment]
        bid = event.button.id
        msg_w = self.query_one("#settings_msg", Static)

        if bid == "alpha_std":
            self.query_one("#hints_alphabet", Input).value = "ABCDEFGMNOPQRSTUVWXYZ"
            return
        if bid == "alpha_home":
            self.query_one("#hints_alphabet", Input).value = "ASDFGHJKL"
            return
        if bid == "alpha_grid":
            self.query_one("#hints_alphabet", Input).value = "ABCDEFGH"
            return

        if bid == "btn_clear_overrides":
            for inp_id in ("#ovr_light", "#ovr_dark", "#ovr_hint_bg", "#ovr_hint_fg"):
                self.query_one(inp_id, Input).value = ""
            tui.config.theme_overrides.clear()
            tui.config_manager.save()
            tui.apply_config()
            msg_w.update("Cleared custom color overrides.")
            return

        if bid == "btn_save_preset":
            name = self.query_one("#preset_name_input", Input).value.strip()
            if not name:
                msg_w.update("Enter a preset name first.")
                return
            self._apply_form()
            path = tui.config_manager.save_preset(name)
            msg_w.update(f"Saved preset '{name}' -> {path.name}")
            return

        if bid == "btn_load_preset":
            sel = self.query_one("#preset_select", Select)
            if sel.value is Select.BLANK:
                return
            tui.config_manager.load_preset(str(sel.value))
            tui.config = tui.config_manager.config
            tui.apply_config()
            self.dismiss(None)
            return

        if bid == "btn_apply":
            self.action_save_and_close()
