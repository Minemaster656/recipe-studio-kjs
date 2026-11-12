"""Virtualised item grid drawn on a Tk canvas."""

from __future__ import annotations

import math
import tkinter as tk

import customtkinter as ctk

from RecipeStudio.services.catalog import CatalogEntry
from RecipeStudio.theme import COLORS


class ItemGrid(tk.Frame):
    def __init__(self, master, app, *, cell: int = 50):
        super().__init__(master, bg=COLORS["panel"], highlightthickness=0, bd=0)
        self.app = app
        self.cell = int(cell)
        self.entries: list[CatalogEntry] = []
        self.selected_id: str | None = None
        self._cols = 1
        self._hover_index = -1
        self._press_index = -1
        self._press_xy: tuple[int, int] | None = None
        self._dragging = False
        self._redraw_job = None
        self._images: dict = {}

        self.canvas = tk.Canvas(
            self,
            bg=COLORS["panel"],
            highlightthickness=0,
            bd=0,
            takefocus=1,
            yscrollincrement=self.cell,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ctk.CTkScrollbar(
            self,
            orientation="vertical",
            command=self.canvas.yview,
            fg_color=COLORS["panel"],
            button_color=COLORS["slot_border"],
            button_hover_color=COLORS["slot_hover"],
        )
        self.scrollbar.grid(row=0, column=1, sticky="ns", padx=(4, 0))
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.canvas.bind("<Configure>", self._on_configure)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", self._on_leave)
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<Button-3>", self._on_right_click)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self._scroll(-1))
        self.canvas.bind("<Button-5>", lambda e: self._scroll(1))

    # ------------------------------------------------------------------
    def set_entries(self, entries: list[CatalogEntry]) -> None:
        self.entries = list(entries)
        self._hover_index = -1
        self._press_index = -1
        self._dragging = False
        self.app.tooltip.hide()
        self.canvas.yview_moveto(0)
        self._recalc()
        self._schedule_redraw()

    def set_selected(self, item_id: str | None) -> None:
        self.selected_id = item_id
        self._schedule_redraw()

    def refresh(self) -> None:
        self._schedule_redraw()

    def focus(self) -> None:
        self.canvas.focus_set()

    # ------------------------------------------------------------------
    def _on_configure(self, _event=None) -> None:
        self._recalc()
        self._schedule_redraw()

    def _recalc(self) -> None:
        width = max(self.cell, self.canvas.winfo_width())
        self._cols = max(1, width // self.cell)
        rows = math.ceil(len(self.entries) / self._cols) if self.entries else 0
        height = max(1, rows * self.cell)
        self.canvas.configure(
            scrollregion=(0, 0, max(width, self._cols * self.cell), height)
        )

    def _schedule_redraw(self) -> None:
        if self._redraw_job is not None:
            return
        self._redraw_job = self.after_idle(self._redraw)

    def _redraw(self) -> None:
        self._redraw_job = None
        c = self.canvas
        c.delete("all")
        if not self.entries:
            c.create_text(
                max(120, c.winfo_width() // 2),
                80,
                text="No items found",
                fill=COLORS["text_dim"],
                font=("DejaVu Sans", 12),
            )
            return

        top = c.canvasy(0)
        height = max(1, c.winfo_height())
        rows = math.ceil(len(self.entries) / self._cols)
        first_row = max(0, int(top // self.cell))
        last_row = min(rows - 1, int((top + height) // self.cell) + 1)
        pad = 3
        icon_size = max(24, self.cell - 18)

        for row in range(first_row, last_row + 1):
            for col in range(self._cols):
                idx = row * self._cols + col
                if idx >= len(self.entries):
                    break
                entry = self.entries[idx]
                x0 = col * self.cell + pad
                y0 = row * self.cell + pad
                x1 = x0 + self.cell - pad * 2
                y1 = y0 + self.cell - pad * 2
                hover = idx == self._hover_index
                selected = entry.id == self.selected_id
                fav = self.app.favorites.is_fav(entry.id)
                fill = COLORS["panel_hover"] if hover else COLORS["panel_alt"]
                if selected:
                    outline = COLORS["accent"]
                    width = 2
                elif fav:
                    outline = COLORS["gold"]
                    width = 2
                elif hover:
                    outline = COLORS["accent_2"]
                    width = 1
                else:
                    outline = COLORS["border"]
                    width = 1
                c.create_rectangle(
                    x0, y0, x1, y1, fill=fill, outline=outline, width=width
                )
                photo = self.app.icons.get_entry(entry, icon_size)
                if photo is not None:
                    self._images[entry.id] = photo
                    c.create_image((x0 + x1) / 2, (y0 + y1) / 2, image=photo)
                else:
                    c.create_text(
                        (x0 + x1) / 2, (y0 + y1) / 2, text="?", fill=COLORS["text_dim"]
                    )

    # ------------------------------------------------------------------
    def _index_at(self, x: int, y: int) -> int:
        if not self.entries:
            return -1
        y_canvas = self.canvas.canvasy(y)
        col = int(x // self.cell)
        row = int(y_canvas // self.cell)
        if col < 0 or col >= self._cols or row < 0:
            return -1
        idx = row * self._cols + col
        return idx if 0 <= idx < len(self.entries) else -1

    def _on_motion(self, event) -> None:
        if self._dragging or self._press_index >= 0:
            return
        idx = self._index_at(event.x, event.y)
        if idx != self._hover_index:
            self._hover_index = idx
            self._schedule_redraw()
            if idx >= 0:
                self.app.hovered_entry = self.entries[idx]
                self.app.tooltip.show(
                    self.app.item_tooltip_text(self.entries[idx]),
                    event.x_root,
                    event.y_root,
                )
            else:
                self.app.hovered_entry = None
                self.app.tooltip.hide()

    def _on_leave(self, _event=None) -> None:
        self._hover_index = -1
        self.app.hovered_entry = None
        self.app.tooltip.hide()
        self._schedule_redraw()

    def _on_press(self, event) -> None:
        self._press_index = self._index_at(event.x, event.y)
        self._press_xy = (event.x_root, event.y_root)
        self._dragging = False

    def _on_drag(self, event) -> None:
        if self._dragging or self._press_index < 0 or self._press_xy is None:
            return
        dx = abs(event.x_root - self._press_xy[0])
        dy = abs(event.y_root - self._press_xy[1])
        if dx + dy < 6:
            return
        idx = self._press_index
        if 0 <= idx < len(self.entries):
            self._dragging = True
            self.app.tooltip.hide()
            self.app.drag_manager.start(self.entries[idx], event.x_root, event.y_root)

    def _on_right_click(self, event) -> str:
        idx = self._index_at(event.x, event.y)
        if idx < 0:
            return "break"
        self.app.tooltip.hide()
        self.app.show_item_context_menu(self.entries[idx], event.x_root, event.y_root)
        return "break"

    def _on_release(self, event) -> None:
        was_dragging = self._dragging
        self._dragging = False
        press = self._press_index
        self._press_index = -1
        self._press_xy = None
        if was_dragging or self.app.drag_manager.active:
            return
        idx = self._index_at(event.x, event.y)
        if idx >= 0 and idx == press:
            self.app.select_palette(self.entries[idx])

    def _on_wheel(self, event) -> str:
        if event.delta:
            self._scroll(-1 if event.delta > 0 else 1)
        return "break"

    def _scroll(self, delta: int) -> str:
        self.app.tooltip.hide()
        self.canvas.yview_scroll(delta, "units")
        self._schedule_redraw()
        return "break"

    def _scroll_units(self, delta: float) -> None:
        self.canvas.yview_scroll(delta, "units")
        self._schedule_redraw()
