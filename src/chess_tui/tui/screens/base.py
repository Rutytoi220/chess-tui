"""Shared Vim-style (hjkl) modal navigation base class."""

from __future__ import annotations

from textual import events
from textual.screen import ModalScreen
from textual.widgets import Input, Select, TabbedContent


class VimModalScreen(ModalScreen[None]):
    """ModalScreen supporting Vim hjkl navigation across buttons, lists, and tabs."""

    def on_mount(self) -> None:
        # Ensure focus lands on the first interactive control rather than nothing
        if self.focused is None:
            self.focus_next()

    def on_key(self, event: events.Key) -> None:
        focused = self.focused
        # Never hijack typing inside text inputs
        if isinstance(focused, Input):
            if event.key == "escape":
                self.dismiss(None)
                event.prevent_default()
                event.stop()
            return

        # If a Select dropdown overlay is currently open, let Up/Down/j/k navigate its list
        key = event.key
        if key in ("j", "down"):
            if focused is not None and hasattr(focused, "action_cursor_down"):
                row_count = getattr(focused, "row_count", None)
                cursor_row = getattr(focused, "cursor_row", None)
                if row_count is None or (row_count > 0 and cursor_row is not None and cursor_row < row_count - 1):
                    focused.action_cursor_down()  # type: ignore[attr-defined]
                    event.prevent_default()
                    event.stop()
                    return
            self.focus_next()
            event.prevent_default()
            event.stop()
            return

        if key in ("k", "up"):
            if focused is not None and hasattr(focused, "action_cursor_up"):
                row_count = getattr(focused, "row_count", None)
                cursor_row = getattr(focused, "cursor_row", None)
                if row_count is None or (row_count > 0 and cursor_row is not None and cursor_row > 0):
                    focused.action_cursor_up()  # type: ignore[attr-defined]
                    event.prevent_default()
                    event.stop()
                    return
            self.focus_previous()
            event.prevent_default()
            event.stop()
            return

        if key in ("l", "right"):
            if isinstance(focused, Select) and focused.expanded:
                return
            tabs = self.query(TabbedContent)
            if tabs and focused is not None and focused.__class__.__name__ == "Tab":
                tc = tabs.first()
                if hasattr(tc, "action_next_tab"):
                    tc.action_next_tab()
                    event.prevent_default()
                    event.stop()
                    return
            self.focus_next()
            event.prevent_default()
            event.stop()
            return

        if key in ("h", "left"):
            if isinstance(focused, Select) and focused.expanded:
                return
            tabs = self.query(TabbedContent)
            if tabs and focused is not None and focused.__class__.__name__ == "Tab":
                tc = tabs.first()
                if hasattr(tc, "action_previous_tab"):
                    tc.action_previous_tab()
                    event.prevent_default()
                    event.stop()
                    return
            self.focus_previous()
            event.prevent_default()
            event.stop()
            return

        if key == "q":
            self.dismiss(None)
            event.prevent_default()
            event.stop()
