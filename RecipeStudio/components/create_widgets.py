"""Create-specific reusable widgets: heat, fluid amounts, expanding groups."""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk
import tkinter as tk

from RecipeStudio.components.number_field import NumberField
from RecipeStudio.components.slot import Slot
from RecipeStudio.model.ingredient import Ingredient
from RecipeStudio.theme import COLORS, FONT_UI_SMALL


class HeatSelector(ctk.CTkFrame):
    """Three-state blaze burner: none -> heated -> superheated."""

    LEVELS = [
        ("No heat", "create:empty_blaze_burner", None),
        ("Heated", "create:blaze_burner", "heated"),
        ("Superheated", "create:blaze_cake", "superheated"),
    ]

    def __init__(self, master, app, *, on_change: Callable[[], None] | None = None):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.on_change = on_change
        self.level = 0
        self._photo = None
        self._image = tk.Label(self, bg=COLORS["bg"], bd=0, cursor="hand2")
        self._image.pack()
        self._text = ctk.CTkLabel(
            self, text="", text_color=COLORS["text_dim"], font=FONT_UI_SMALL
        )
        self._text.pack(pady=(2, 0))
        for widget in (self._image, self._text):
            widget.bind("<Button-1>", lambda e: self.cycle(1))
            widget.bind("<Button-3>", lambda e: self.cycle(-1))
        self.set_level(0, notify=False)

    def cycle(self, delta: int = 1) -> None:
        self.set_level((self.level + delta) % len(self.LEVELS))

    def set_level(self, level: int, *, notify: bool = True) -> None:
        self.level = max(0, min(len(self.LEVELS) - 1, int(level)))
        label, item_id, _ = self.LEVELS[self.level]
        self._text.configure(text=label)
        entry = self.app.catalog.get(item_id)
        self._photo = self.app.icons.get_entry(entry, 34)
        if self._photo is not None:
            self._image.configure(image=self._photo)
        if notify and self.on_change is not None:
            self.on_change()

    def requirement(self) -> str | None:
        return self.LEVELS[self.level][2]

    def set_requirement(self, requirement: str | None, *, notify: bool = True) -> None:
        target = 0
        for index, (_label, _item_id, value) in enumerate(self.LEVELS):
            if value == requirement:
                target = index
                break
        self.set_level(target, notify=notify)

    def clear(self) -> None:
        self.set_level(0, notify=False)


class FluidAmountField(ctk.CTkFrame):
    """Fluid amount in mB with a right-click step selector."""

    STEPS = [(1, "1 mB"), (50, "50 mB"), (1000, "1 B")]

    def __init__(
        self,
        master,
        *,
        value: int = 1000,
        on_change: Callable[[], None] | None = None,
        width: int = 92,
    ):
        super().__init__(master, fg_color="transparent")
        self.on_change = on_change
        self.mode = 0
        self.field = NumberField(
            self,
            width=width,
            min_value=1,
            max_value=1_000_000,
            step=1,
            on_change=on_change,
        )
        self.field.grid(row=0, column=0, sticky="ew")
        self.unit = ctk.CTkLabel(
            self, text="mB", text_color=COLORS["text_dim"], font=FONT_UI_SMALL
        )
        self.unit.grid(row=0, column=1, padx=(4, 0))
        self.mode_label = ctk.CTkLabel(
            self,
            text="step 1",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 8),
        )
        self.mode_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(1, 0))
        self.field.set_value(value)
        self.bind("<Button-3>", self._cycle_mode)
        self.field.bind("<Button-3>", self._cycle_mode)
        self.field.entry.bind("<Button-3>", self._cycle_mode)

    def _cycle_mode(self, _event=None) -> str:
        self.mode = (self.mode + 1) % len(self.STEPS)
        step, label = self.STEPS[self.mode]
        self.field.step = step
        self.mode_label.configure(text=f"step {label}")
        return "break"

    def value(self) -> int:
        value = self.field.get_value()
        return int(value) if value is not None else 1000

    def set_value(self, value) -> None:
        self.field.set_value(value)

    def clear(self) -> None:
        self.field.set_value(1000)


class IngredientGroup(ctk.CTkFrame):
    """Slots with one trailing empty slot, up to ``max_items`` entries."""

    def __init__(
        self,
        master,
        app,
        *,
        kind: str = "item",
        max_items: int = 8,
        slot_size: int = 44,
        allow_chance: bool = False,
        allow_count: bool = True,
        on_change: Callable[[], None] | None = None,
    ):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.kind = kind
        self.max_items = max_items
        self.slot_size = slot_size
        self.allow_chance = allow_chance
        self.allow_count = allow_count
        self.on_change = on_change
        self.slots: list[Slot] = []
        self._busy = False
        self._append_slot()

    def _append_slot(self) -> Slot:
        slot = Slot(
            self,
            self.app,
            size=self.slot_size,
            allow_count=self.allow_count and self.kind != "fluid",
            max_count=64,
            allow_tag=self.kind != "fluid",
            allow_fluid=self.kind == "fluid",
            allow_chance=self.allow_chance,
            on_change=self._slot_changed,
        )
        slot.pack(side="left", padx=2)
        self.slots.append(slot)
        return slot

    def _slot_changed(self) -> None:
        self._normalize()
        self._notify()

    def _normalize(self) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            nonempty = [s for s in self.slots if not s.is_empty]
            # At most one trailing empty slot.
            while (
                len(self.slots) > 1
                and self.slots[-1].is_empty
                and self.slots[-2].is_empty
            ):
                slot = self.slots.pop()
                slot.destroy()
            if (
                len(nonempty) < self.max_items
                and self.slots
                and not self.slots[-1].is_empty
            ):
                self._append_slot()
            if not self.slots:
                self._append_slot()
        finally:
            self._busy = False

    def _notify(self) -> None:
        if self.on_change is not None:
            self.on_change()

    def ingredients(self) -> list[Ingredient]:
        return [slot.ingredient.copy() for slot in self.slots if not slot.is_empty]

    def set_ingredients(self, values: list[Ingredient]) -> None:
        self._busy = True
        try:
            for slot in self.slots:
                slot.clear(notify=False)
                slot.destroy()
            self.slots = []
            for ing in values[: self.max_items]:
                slot = self._append_slot()
                slot.set_ingredient(ing, notify=False)
            if not self.slots or (
                len(values) < self.max_items and not self.slots[-1].is_empty
            ):
                self._append_slot()
        finally:
            self._busy = False
        self._notify()

    def clear(self, *, notify: bool = True) -> None:
        self._busy = True
        try:
            for slot in self.slots:
                slot.clear(notify=False)
                slot.destroy()
            self.slots = []
            self._append_slot()
        finally:
            self._busy = False
        if notify:
            self._notify()
