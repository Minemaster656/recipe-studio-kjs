"""Internal drag and drop for palette items -> slots."""

from __future__ import annotations

import tkinter as tk

from RecipeStudio.model.ingredient import Ingredient
from RecipeStudio.services.catalog import CatalogEntry
from RecipeStudio.theme import COLORS, FONT_UI_SMALL


class DragManager:
    def __init__(self, app):
        self.app = app
        self.payload = None
        self.ghost: tk.Toplevel | None = None
        self.active = False
        self.app.bind_all("<B1-Motion>", self._motion, add="+")
        self.app.bind_all("<ButtonRelease-1>", self._release, add="+")

    def start(self, payload, x_root: int, y_root: int) -> None:
        if self.active:
            return
        self.active = True
        self.payload = payload
        self._make_ghost(payload)
        self._move_ghost(x_root, y_root)

    def _make_ghost(self, payload) -> None:
        self.ghost = tk.Toplevel(self.app)
        self.ghost.overrideredirect(True)
        try:
            self.ghost.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.ghost.configure(bg=COLORS["accent"])
        frame = tk.Frame(self.ghost, bg=COLORS["panel_alt"])
        frame.pack(padx=1, pady=1)
        photo = None
        text = ""
        if isinstance(payload, CatalogEntry):
            photo = self.app.icons.get_entry(payload, 28)
            text = self.app.names.get(payload.id)
        elif isinstance(payload, Ingredient):
            photo = self.app.icons.get_ingredient(payload, self.app.catalog, 28)
            text = (
                self.app.names.get(payload.id)
                if payload.kind != "tag"
                else "#" + payload.id
            )
        if photo is not None:
            tk.Label(frame, image=photo, bg=COLORS["panel_alt"]).pack(
                side="left", padx=(4, 2), pady=2
            )
            frame.image = photo  # type: ignore[attr-defined]
        tk.Label(
            frame,
            text=text,
            bg=COLORS["panel_alt"],
            fg=COLORS["text"],
            font=FONT_UI_SMALL,
            padx=4,
        ).pack(side="left", padx=(0, 6), pady=3)

    def _move_ghost(self, x_root: int, y_root: int) -> None:
        if self.ghost is None:
            return
        self.ghost.geometry(f"+{x_root + 14}+{y_root + 14}")

    def _motion(self, event) -> None:
        if not self.active:
            return
        self._move_ghost(event.x_root, event.y_root)
        slot = self.app.find_slot_at(event.x_root, event.y_root)
        self.app.highlight_drop_target(slot)

    def _release(self, event) -> None:
        if not self.active:
            return
        slot = self.app.find_slot_at(event.x_root, event.y_root)
        if slot is not None:
            slot.set_from_drop(self.payload)
        self.cleanup()

    def cleanup(self) -> None:
        self.active = False
        self.payload = None
        self.app.highlight_drop_target(None)
        if self.ghost is not None:
            try:
                self.ghost.destroy()
            except tk.TclError:
                pass
        self.ghost = None
