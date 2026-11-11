"""Time input storing ticks internally.

LMB clears the override (defaults apply), RMB toggles seconds/ticks,
double-click allows typing.  The widget always stores integer ticks.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable

import customtkinter as ctk

from RecipeStudio.theme import COLORS, FONT_UI_SMALL


class TimeField(ctk.CTkFrame):
    def __init__(
        self,
        master,
        *,
        default_ticks: int = 200,
        unit: str = "s",
        on_change: Callable[[], None] | None = None,
        width: int = 110,
    ):
        super().__init__(master, fg_color="transparent", width=width, height=30)
        self.default_ticks = int(default_ticks)
        self.unit = unit if unit in ("s", "t") else "s"
        self.ticks: int | None = None
        self.on_change = on_change
        self._editing = False

        self.label = ctk.CTkLabel(
            self,
            text="",
            width=width,
            height=30,
            corner_radius=6,
            fg_color=COLORS["slot"],
            text_color=COLORS["text_dim"],
            font=FONT_UI_SMALL,
            cursor="hand2",
        )
        self.label.grid(row=0, column=0, sticky="ew")
        self.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(
            self,
            width=width,
            height=30,
            fg_color=COLORS["slot"],
            border_color=COLORS["accent"],
            text_color=COLORS["text"],
            font=FONT_UI_SMALL,
        )

        self.label.bind("<Button-1>", self._left_click)
        self.label.bind("<Button-3>", self._toggle_unit)
        self.label.bind("<Double-Button-1>", self._begin_edit)
        self.label.bind("<MouseWheel>", self._wheel)
        self.label.bind("<Button-4>", lambda e: self._bump(1))
        self.label.bind("<Button-5>", lambda e: self._bump(-1))
        self.entry.bind("<Return>", lambda e: self._commit())
        self.entry.bind("<FocusOut>", lambda e: self._commit())
        self.entry.bind("<Escape>", lambda e: self._cancel_edit())
        self._render()

    # ------------------------------------------------------------------
    def _display_value(self) -> str:
        if self.ticks is None:
            return ""
        if self.unit == "s":
            seconds = self.ticks / 20
            if float(seconds).is_integer():
                return str(int(seconds))
            return f"{seconds:.2f}".rstrip("0").rstrip(".")
        return str(int(self.ticks))

    def _default_text(self) -> str:
        if self.unit == "s":
            seconds = self.default_ticks / 20
            if float(seconds).is_integer():
                return f"{int(seconds)} s"
            return f"{seconds:.2f}".rstrip("0").rstrip(".") + " s"
        return f"{self.default_ticks} t"

    def _render(self) -> None:
        if self.ticks is None:
            self.label.configure(
                text=f"default {self._default_text()}", text_color=COLORS["text_dim"]
            )
        else:
            unit = "s" if self.unit == "s" else "t"
            self.label.configure(
                text=f"{self._display_value()} {unit}", text_color=COLORS["text"]
            )

    # ------------------------------------------------------------------
    def _left_click(self, _event=None) -> str:
        if self._editing:
            return "break"
        self.ticks = None
        self._render()
        self._notify()
        return "break"

    def _toggle_unit(self, _event=None) -> str:
        self.unit = "t" if self.unit == "s" else "s"
        self._render()
        if self._editing:
            self.entry.delete(0, "end")
            self.entry.insert(0, self._display_value())
        return "break"

    def _begin_edit(self, _event=None) -> str:
        self._editing = True
        self.label.grid_remove()
        self.entry.grid(row=0, column=0, sticky="ew")
        self.entry.delete(0, "end")
        self.entry.insert(0, self._display_value())
        self.entry.focus_set()
        self.entry.select_range(0, "end")
        return "break"

    def _commit(self) -> None:
        if not self._editing:
            return
        raw = self.entry.get().strip()
        self._editing = False
        self.entry.grid_remove()
        self.label.grid()
        if not raw:
            self.ticks = None
        else:
            try:
                value = float(raw)
                self.ticks = max(
                    1, int(round(value * 20)) if self.unit == "s" else int(round(value))
                )
            except ValueError:
                pass
        self._render()
        self._notify()

    def _cancel_edit(self) -> None:
        self._editing = False
        self.entry.grid_remove()
        self.label.grid()
        self._render()

    def _wheel(self, event) -> str:
        if event.delta:
            self._bump(1 if event.delta > 0 else -1)
        return "break"

    def _bump(self, direction: int) -> None:
        if self.ticks is None:
            self.ticks = self.default_ticks
        else:
            step = 20 if self.unit == "s" else 1
            self.ticks = max(1, self.ticks + direction * step)
        self._render()
        self._notify()

    def _notify(self) -> None:
        if self.on_change is not None:
            self.on_change()

    # ------------------------------------------------------------------
    def get_ticks(self) -> int | None:
        return self.ticks

    def set_ticks(self, ticks: int | None) -> None:
        self.ticks = None if ticks is None else max(1, int(ticks))
        self._render()

    def clear(self) -> None:
        self.ticks = None
        self._render()
