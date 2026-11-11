"""Search entry with S/F/E mode cycler."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from RecipeStudio.services.search import SearchMode
from RecipeStudio.theme import COLORS, FONT_UI


class SearchBar(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.mode = SearchMode.SUBSTRING
        self._job = None

        self.entry = ctk.CTkEntry(
            self,
            height=34,
            placeholder_text="Search items…  (Ctrl+F)",
            fg_color=COLORS["slot"],
            border_color=COLORS["slot_border"],
            text_color=COLORS["text"],
            placeholder_text_color=COLORS["text_dim"],
            font=FONT_UI,
        )
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.mode_button = ctk.CTkButton(
            self,
            text=self.mode,
            width=40,
            height=34,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_2"],
            text_color=COLORS["panel"],
            font=("DejaVu Sans", 13, "bold"),
            command=self.cycle_mode,
        )
        self.mode_button.grid(row=0, column=1)
        self.clear_button = ctk.CTkButton(
            self,
            text="×",
            width=30,
            height=34,
            fg_color=COLORS["panel_alt"],
            hover_color=COLORS["panel_hover"],
            text_color=COLORS["text_dim"],
            command=self.clear,
        )
        self.clear_button.grid(row=0, column=2, padx=(6, 0))
        self.grid_columnconfigure(0, weight=1)

        self.entry.bind("<KeyRelease>", self._on_key)
        self.entry.bind("<Return>", self._immediate)
        self.entry.bind("<Escape>", self._escape)
        inner = getattr(self.entry, "_entry", self.entry)
        for widget in {self.entry, inner}:
            widget.bind("<Control-BackSpace>", self._delete_prev_word, add="+")
            widget.bind("<Control-Delete>", self._delete_next_word, add="+")
        self.mode_button.bind("<Enter>", self._mode_tooltip)
        self.mode_button.bind("<Leave>", lambda e: self.app.tooltip.hide())

    # ------------------------------------------------------------------
    def get_query(self) -> str:
        return self.entry.get().strip()

    def set_mode(self, mode: str) -> None:
        if mode not in SearchMode.ALL:
            return
        self.mode = mode
        colors = {
            SearchMode.SUBSTRING: COLORS["accent"],
            SearchMode.FUZZY: COLORS["purple"],
            SearchMode.EMBEDDINGS: COLORS["green"],
        }
        self.mode_button.configure(
            text=mode, fg_color=colors[mode], hover_color=colors[mode]
        )
        self.app.on_mode_changed(mode)

    def cycle_mode(self) -> None:
        idx = SearchMode.ALL.index(self.mode)
        self.set_mode(SearchMode.ALL[(idx + 1) % len(SearchMode.ALL)])

    def focus_search(self) -> None:
        if self.is_focused():
            self.app.focus_grid()
            return
        self.entry.focus_set()
        try:
            self.entry._entry.select_range(0, "end")  # type: ignore[attr-defined]
        except Exception:
            pass

    def is_focused(self) -> bool:
        try:
            focus = self.app.focus_get()
        except Exception:
            return False
        inner = getattr(self.entry, "_entry", None)
        return focus is self.entry or (inner is not None and focus is inner)

    # ------------------------------------------------------------------
    def _inner_entry(self):
        return getattr(self.entry, "_entry", self.entry)

    def _delete_prev_word(self, _event=None) -> str:
        entry = self._inner_entry()
        try:
            pos = int(entry.index("insert"))
            text = entry.get()
        except Exception:
            return "break"
        start = pos
        while start > 0 and text[start - 1].isspace():
            start -= 1
        while start > 0 and not text[start - 1].isspace():
            start -= 1
        if start < pos:
            entry.delete(start, pos)
            self._schedule()
        return "break"

    def _delete_next_word(self, _event=None) -> str:
        entry = self._inner_entry()
        try:
            pos = int(entry.index("insert"))
            text = entry.get()
        except Exception:
            return "break"
        end = pos
        while end < len(text) and text[end].isspace():
            end += 1
        while end < len(text) and not text[end].isspace():
            end += 1
        if end > pos:
            entry.delete(pos, end)
            self._schedule()
        return "break"

    def _on_key(self, event) -> None:
        if event.keysym in (
            "Return",
            "Escape",
            "Control_L",
            "Control_R",
            "Shift_L",
            "Shift_R",
        ):
            return
        self._schedule()

    def _schedule(self) -> None:
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
        self._job = self.after(180, self._run)

    def _run(self) -> None:
        self._job = None
        self.app.on_search_text(self.get_query())

    def _immediate(self, _event=None) -> str:
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        self.app.on_search_text(self.get_query())
        return "break"

    def _escape(self, _event=None) -> str:
        self.entry.delete(0, "end")
        self.app.show_all_items()
        self.app.focus_grid()
        return "break"

    def clear(self) -> None:
        self.entry.delete(0, "end")
        self.app.show_all_items()
        self.entry.focus_set()

    def _mode_tooltip(self, event=None) -> None:
        if event is None:
            return
        text = {
            SearchMode.SUBSTRING: "S — substring over full item id",
            SearchMode.FUZZY: "F — fuzzy matching",
            SearchMode.EMBEDDINGS: "E — embeddings (text or image path)",
        }[self.mode]
        self.app.tooltip.show(
            text + "\nCtrl+Shift+F to cycle", event.x_root, event.y_root
        )
