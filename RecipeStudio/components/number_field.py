"""Numeric input with +/- buttons and wheel support."""

from __future__ import annotations

import tkinter as tk
from typing import Callable

import customtkinter as ctk

from RecipeStudio.theme import COLORS, FONT_UI_SMALL


class NumberField(ctk.CTkFrame):
    def __init__(
        self,
        master,
        *,
        width: int = 90,
        min_value: float | None = 0,
        max_value: float | None = None,
        step: float = 1,
        allow_empty: bool = False,
        allow_float: bool = False,
        placeholder: str = "",
        on_change: Callable[[], None] | None = None,
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.min_value = min_value
        self.max_value = max_value
        self.step = step
        self.allow_empty = allow_empty
        self.allow_float = allow_float
        self.on_change = on_change
        self._suspend = False

        self.var = tk.StringVar()
        self.entry = ctk.CTkEntry(
            self,
            width=width,
            height=28,
            textvariable=self.var,
            placeholder_text=placeholder,
            fg_color=COLORS["slot"],
            border_color=COLORS["slot_border"],
            text_color=COLORS["text"],
            font=FONT_UI_SMALL,
        )
        self.entry.grid(row=0, column=0, sticky="ew")
        self.minus = ctk.CTkButton(
            self,
            text="−",
            width=26,
            height=28,
            fg_color=COLORS["panel_alt"],
            hover_color=COLORS["panel_hover"],
            text_color=COLORS["text_dim"],
            command=lambda: self.bump(-self.step),
        )
        self.minus.grid(row=0, column=1, padx=(3, 0))
        self.plus = ctk.CTkButton(
            self,
            text="+",
            width=26,
            height=28,
            fg_color=COLORS["panel_alt"],
            hover_color=COLORS["panel_hover"],
            text_color=COLORS["text_dim"],
            command=lambda: self.bump(self.step),
        )
        self.plus.grid(row=0, column=2, padx=(3, 0))
        self.grid_columnconfigure(0, weight=1)

        self.var.trace_add("write", self._on_write)
        self.entry.bind("<FocusOut>", self._normalize)
        self.entry.bind("<MouseWheel>", self._wheel)
        self.entry.bind("<Button-4>", lambda e: self.bump(self.step))
        self.entry.bind("<Button-5>", lambda e: self.bump(-self.step))
        self.bind("<MouseWheel>", self._wheel)

    # ------------------------------------------------------------------
    def _on_write(self, *_args) -> None:
        if self._suspend:
            return
        if self.on_change is not None:
            self.on_change()

    def _wheel(self, event) -> str:
        if event.delta:
            self.bump(self.step if event.delta > 0 else -self.step)
        return "break"

    def _parse(self):
        raw = self.var.get().strip()
        if not raw:
            return None
        try:
            return float(raw) if self.allow_float else int(float(raw))
        except ValueError:
            return None

    def get_value(self):
        value = self._parse()
        if value is None:
            return None
        if self.min_value is not None:
            value = max(self.min_value, value)
        if self.max_value is not None:
            value = min(self.max_value, value)
        return value

    def set_value(self, value) -> None:
        self._suspend = True
        try:
            if value is None:
                self.var.set("")
            elif self.allow_float:
                self.var.set(f"{float(value):g}")
            else:
                self.var.set(str(int(value)))
        finally:
            self._suspend = False
        self._notify()

    def bump(self, delta: float) -> None:
        current = self.get_value()
        if current is None:
            current = 0 if self.min_value is None else self.min_value
        value = current + delta
        if self.min_value is not None and value < self.min_value:
            value = self.min_value
        if self.max_value is not None and value > self.max_value:
            value = self.max_value
        self.set_value(value)

    def _normalize(self, _event=None) -> None:
        value = self.get_value()
        if value is None:
            if not self.allow_empty:
                self.set_value(self.min_value or 0)
            return
        self.set_value(value)

    def _notify(self) -> None:
        if self.on_change is not None:
            self.on_change()

    def clear(self) -> None:
        self.set_value(None)
