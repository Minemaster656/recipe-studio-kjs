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

    def show(
        self,
        text: str,
        x_root: int | None = None,
        y_root: int | None = None,
        delay: int = 350,
    ) -> None:
        if not text:
            self.hide()
            return
        self._cancel()
        # Always place the tooltip at the *current* pointer position when it
        # actually appears.  Cached event coordinates go stale while the
        # 350 ms delay is running and can even be (0, 0) for synthetic events.
        self._after = self.app.after(delay, lambda: self._show_now(text))

    def _show_now(self, text: str) -> None:
        self._after = None
        if self.top is not None and self.text == text:
            self._move_to_pointer()
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
        self._move_to_pointer()

    def _move_to_pointer(self) -> None:
        try:
            x_root, y_root = self.app.winfo_pointerxy()
        except tk.TclError:
            return
        self._move(x_root, y_root)

    def _move(self, x_root: int, y_root: int) -> None:
        if self.top is None:
            return
        try:
            self.top.update_idletasks()
        except tk.TclError:
            self.top = None
            self.label = None
            self.text = ""
            return
        w = max(1, self.top.winfo_width(), self.top.winfo_reqwidth())
        h = max(1, self.top.winfo_height(), self.top.winfo_reqheight())
        # Virtual root covers all monitors; winfo_screenwidth() only covers
        # the primary one and would clamp negative secondary-monitor coords
        # to (0, 0).
        sx = self.top.winfo_vrootx()
        sy = self.top.winfo_vrooty()
        sw = self.top.winfo_vrootwidth()
        sh = self.top.winfo_vrootheight()
        x = x_root + 16
        y = y_root + 18
        if x + w > sx + sw - 8:
            x = x_root - w - 12
        if y + h > sy + sh - 8:
            y = y_root - h - 12
        x = max(sx + 4, x)
        y = max(sy + 4, y)
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
