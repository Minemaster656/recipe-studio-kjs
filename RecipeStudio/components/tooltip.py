"""Lightweight hover tooltip."""

from __future__ import annotations

import tkinter as tk

from RecipeStudio.theme import COLORS, FONT_UI_SMALL


class Tooltip:
    def __init__(self, app):
        self.app = app
        self.top: tk.Toplevel | None = None
        self.label: tk.Label | None = None
        self.text = ""
        self._after = None

    def show(self, text: str, x_root: int, y_root: int, delay: int = 350) -> None:
        if not text:
            self.hide()
            return
        self._cancel()
        self._after = self.app.after(
            delay, lambda: self._show_now(text, x_root, y_root)
        )

    def _show_now(self, text: str, x_root: int, y_root: int) -> None:
        self._after = None
        if self.top is not None and self.text == text:
            self._move(x_root, y_root)
            return
        self.hide()
        self.text = text
        self.top = tk.Toplevel(self.app)
        self.top.overrideredirect(True)
        try:
            self.top.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.top.configure(bg=COLORS["accent"])
        self.label = tk.Label(
            self.top,
            text=text,
            justify="left",
            anchor="w",
            bg=COLORS["panel_alt"],
            fg=COLORS["text"],
            font=FONT_UI_SMALL,
            padx=8,
            pady=5,
            wraplength=380,
        )
        self.label.pack(padx=1, pady=1)
        self._move(x_root, y_root)

    def _move(self, x_root: int, y_root: int) -> None:
        if self.top is None:
            return
        self.top.update_idletasks()
        w = max(1, self.top.winfo_reqwidth())
        h = max(1, self.top.winfo_reqheight())
        sw = self.top.winfo_screenwidth()
        sh = self.top.winfo_screenheight()
        x = min(x_root + 16, sw - w - 8)
        y = min(y_root + 18, sh - h - 8)
        x = max(0, x)
        y = max(0, y)
        self.top.geometry(f"+{x}+{y}")

    def hide(self) -> None:
        self._cancel()
        if self.top is not None:
            try:
                self.top.destroy()
            except tk.TclError:
                pass
        self.top = None
        self.label = None
        self.text = ""

    def _cancel(self) -> None:
        if self._after is not None:
            try:
                self.app.after_cancel(self._after)
            except Exception:
                pass
            self._after = None
