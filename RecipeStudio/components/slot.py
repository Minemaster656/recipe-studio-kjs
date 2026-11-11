"""Reusable item/tag/fluid slot with count badge and settings dialog."""

from __future__ import annotations

import tkinter as tk
from typing import Callable

import customtkinter as ctk

from RecipeStudio.components.number_field import NumberField
from RecipeStudio.model.ingredient import (
    Ingredient,
    fluid_id_from_bucket,
    is_bucket_id,
    normalize_fluid_id,
)
from RecipeStudio.services.catalog import CatalogEntry
from RecipeStudio.theme import COLORS, FONT_UI_SMALL


class Slot(tk.Frame):
    def __init__(
        self,
        master,
        app,
        *,
        size: int = 48,
        allow_count: bool = False,
        max_count: int = 64,
        allow_tag: bool = False,
        allow_fluid: bool = False,
        allow_chance: bool = False,
        on_change: Callable[[], None] | None = None,
        tooltip: bool = True,
    ):
        super().__init__(
            master,
            width=size,
            height=size,
            bg=COLORS["bg"],
            highlightthickness=0,
            bd=0,
            takefocus=0,
        )
        self.pack_propagate(False)
        self.grid_propagate(False)
        self.app = app
        self.size = int(size)
        self.allow_count = allow_count
        self.max_count = int(max_count)
        self.allow_tag = allow_tag
        self.allow_fluid = allow_fluid
        self.allow_chance = allow_chance
        self.on_change = on_change
        self.use_tooltip = tooltip
        self.ingredient = Ingredient()
        self._hover = False
        self._drop_target = False
        self._img = None

        self.canvas = tk.Canvas(
            self,
            width=size,
            height=size,
            bg=COLORS["bg"],
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<Button-1>", self._left_click)
        self.canvas.bind("<Button-2>", self._middle_click)
        self.canvas.bind("<Button-3>", self._right_click)
        self.canvas.bind("<Enter>", self._enter)
        self.canvas.bind("<Leave>", self._leave)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Button-4>", lambda e: self._wheel_delta(1, e))
        self.canvas.bind("<Button-5>", lambda e: self._wheel_delta(-1, e))

        self.app.register_slot(self)
        self._draw()

    # ------------------------------------------------------------------
    @property
    def is_empty(self) -> bool:
        return self.ingredient.is_empty

    def set_ingredient(self, ing: Ingredient, *, notify: bool = True) -> None:
        self.ingredient = ing.copy()
        if self.ingredient.kind == "fluid":
            self.ingredient.id = normalize_fluid_id(self.ingredient.id)
        if self.ingredient.kind == "item" and self.ingredient.count < 1:
            self.ingredient.count = 1
        self._draw()
        if notify:
            self._changed()

    def set_from_entry(self, entry: CatalogEntry, *, notify: bool = True) -> None:
        if self.allow_fluid:
            # The vector DB indexes NeoForge's generated buckets, not fluids.
            # A fluid slot therefore accepts bucket items and stores the fluid id.
            if entry.kind == "fluid" or not is_bucket_id(entry.id):
                return
            amount = self.ingredient.amount if self.ingredient.kind == "fluid" else 1000
            self.set_ingredient(
                Ingredient(
                    kind="fluid",
                    id=fluid_id_from_bucket(entry.id),
                    amount=amount,
                ),
                notify=notify,
            )
            return
        kind = "fluid" if entry.kind == "fluid" else "item"
        self.set_ingredient(Ingredient(kind=kind, id=entry.id, count=1), notify=notify)

    def set_from_drop(self, payload) -> bool:
        """Apply a palette entry or a picked slot ingredient.

        Returns ``True`` when the payload was accepted, so the caller can keep
        or clear an active eyedropper pick.
        """
        if isinstance(payload, CatalogEntry):
            if not self.accepts_entry(payload):
                return False
            self.set_from_entry(payload)
            return True
        if not isinstance(payload, Ingredient):
            return False
        if self.allow_fluid:
            if payload.kind == "fluid":
                amount = payload.amount or (
                    self.ingredient.amount if self.ingredient.kind == "fluid" else 1000
                )
                self.set_ingredient(
                    Ingredient(
                        kind="fluid",
                        id=normalize_fluid_id(payload.id),
                        amount=amount,
                    )
                )
                return True
            if payload.kind != "item" or not is_bucket_id(payload.id):
                return False
            amount = self.ingredient.amount if self.ingredient.kind == "fluid" else 1000
            self.set_ingredient(
                Ingredient(
                    kind="fluid",
                    id=fluid_id_from_bucket(payload.id),
                    amount=amount,
                )
            )
            return True
        if payload.kind == "fluid":
            return False
        if payload.kind == "tag" and not self.allow_tag:
            return False
        self.set_ingredient(payload)
        return True

    def accepts_entry(self, entry: CatalogEntry) -> bool:
        if self.allow_fluid:
            return entry.kind != "fluid" and is_bucket_id(entry.id)
        if entry.kind == "fluid":
            return False
        return True

    def set_drop_target(self, active: bool) -> None:
        active = bool(active)
        if active == self._drop_target:
            return
        self._drop_target = active
        self._draw()

    def clear(self, *, notify: bool = True) -> None:
        self.ingredient.clear()
        self._draw()
        if notify:
            self._changed()

    def set_allow_count(self, value: bool) -> None:
        self.allow_count = bool(value)
        if not self.allow_count and self.ingredient.count > 1:
            self.ingredient.count = 1
        self._draw()

    def adjust_count(self, delta: int) -> str:
        if not self.allow_count or self.ingredient.is_empty:
            return "break"
        self.ingredient.count = max(
            1, min(self.max_count, self.ingredient.count + delta)
        )
        self._draw()
        self._changed()
        return "break"

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change()
        else:
            self.app.on_editor_changed(None)

    # ------------------------------------------------------------------
    def _draw(self) -> None:
        c = self.canvas
        c.delete("all")
        s = self.size
        ing = self.ingredient
        fill = COLORS["slot"]
        if self._drop_target:
            outline = COLORS["accent_2"]
            fill = COLORS["panel_hover"]
            width = 3
        else:
            outline = COLORS["slot_hover"] if self._hover else COLORS["slot_border"]
            width = 2
        c.create_rectangle(1, 1, s - 1, s - 1, fill=fill, outline=outline, width=width)

        if ing.is_empty:
            color = COLORS["accent"] if self._hover else COLORS["text_dim"]
            pad = s * 0.34
            c.create_line(pad, s / 2, s - pad, s / 2, fill=color, width=2)
            c.create_line(s / 2, pad, s / 2, s - pad, fill=color, width=2)
        else:
            photo = self.app.icons.get_ingredient(
                ing, self.app.catalog, max(16, s - 10)
            )
            if photo is not None:
                self._img = photo
                c.create_image(s / 2, s / 2, image=photo)
            else:
                c.create_text(s / 2, s / 2, text="?", fill=COLORS["text_dim"])

        if ing.kind == "tag":
            c.create_rectangle(2, 2, 18, 18, fill=COLORS["purple"], outline="")
            c.create_text(
                10, 9, text="#", fill=COLORS["panel"], font=("DejaVu Sans", 10, "bold")
            )
        elif ing.kind == "fluid":
            c.create_rectangle(2, 2, 20, 18, fill=COLORS["accent_2"], outline="")
            c.create_text(
                11, 9, text="≈", fill=COLORS["panel"], font=("DejaVu Sans", 10, "bold")
            )

        if ing.chance is not None:
            c.create_rectangle(s - 28, 2, s - 2, 18, fill=COLORS["orange"], outline="")
            c.create_text(
                s - 15,
                9,
                text=f"{ing.chance:g}",
                fill=COLORS["panel"],
                font=("DejaVu Sans", 8, "bold"),
            )

        if not ing.is_empty and (ing.count > 1 or self.allow_count):
            text = str(ing.count)
            c.create_rectangle(
                s - 22, s - 18, s - 2, s - 2, fill=COLORS["panel"], outline=""
            )
            c.create_text(
                s - 12,
                s - 9,
                text=text,
                fill=COLORS["text"],
                font=("DejaVu Sans", 10, "bold"),
            )

    # ------------------------------------------------------------------
    def _left_click(self, _event=None) -> str:
        self.app.on_slot_left_click(self)
        return "break"

    def _middle_click(self, _event=None) -> str:
        self.app.pick_slot_ingredient(self)
        return "break"

    def _right_click(self, _event=None) -> str:
        self.app.open_slot_settings(self)
        return "break"

    def _enter(self, event=None) -> None:
        self._hover = True
        self.app.hovered_slot = self
        self._draw()
        if self.use_tooltip and not self.ingredient.is_empty:
            text = self._tooltip_text()
            x = self.winfo_rootx() + self.size
            y = self.winfo_rooty() + self.size
            self.app.tooltip.show(text, x, y)
        return None

    def _leave(self, event=None) -> None:
        self._hover = False
        if self.app.hovered_slot is self:
            self.app.hovered_slot = None
        self._draw()
        self.app.tooltip.hide()
        return None

    def _wheel(self, event) -> str:
        if event.delta:
            self._wheel_delta(1 if event.delta > 0 else -1, event)
        return "break"

    def _wheel_delta(self, delta: int, event=None) -> str:
        alt = bool(event is not None and (event.state & (0x0008 | 0x20000)))
        if alt and self.allow_chance and not self.ingredient.is_empty:
            chance = self.ingredient.chance
            if chance is None:
                chance = 1.0
            step = 0.001 if chance < 0.01 else 0.01
            chance = round(max(0.001, min(1.0, chance + step * delta)), 3)
            self.ingredient.chance = chance
            self._draw()
            self._changed()
            return "break"
        self.adjust_count(delta)
        return "break"

    def _tooltip_text(self) -> str:
        ing = self.ingredient
        if ing.is_empty:
            return ""
        if ing.kind == "tag":
            return f"Tag\n#{ing.id}" + (f"\nx{ing.count}" if ing.count > 1 else "")
        name = self.app.names.get(ing.id)
        lines = [name, ing.id]
        if ing.kind == "fluid":
            lines.append(f"{ing.amount or 1000} mB")
        if ing.count > 1:
            lines.append(f"Count: {ing.count}")
        if ing.chance is not None:
            lines.append(f"Chance: {ing.chance:g}")
        if ing.nbt:
            lines.append(f"NBT: {ing.nbt}")
        return "\n".join(lines)


class SlotSettingsDialog(ctk.CTkToplevel):
    def __init__(self, slot: Slot):
        super().__init__(slot)
        self.slot = slot
        self.app = slot.app
        self.title("Slot settings")
        self.resizable(False, False)
        self.transient(slot.app)
        self.configure(fg_color=COLORS["panel"])
        self.kind_var = tk.StringVar(value=self._kind_label(slot.ingredient.kind))

        self._build()
        self._center()
        self.grab_set()
        self.wait_window(self)

    # ------------------------------------------------------------------
    @staticmethod
    def _kind_label(kind: str) -> str:
        return {"item": "Item", "tag": "Tag", "fluid": "Fluid"}.get(kind, "Item")

    def _build(self) -> None:
        pad = 14
        row = 0
        ctk.CTkLabel(
            self, text="Kind", anchor="w", text_color=COLORS["text_muted"]
        ).grid(row=row, column=0, sticky="w", padx=(pad, 8), pady=(pad, 4))
        values = ["Fluid"] if self.slot.allow_fluid else ["Item"]
        if not self.slot.allow_fluid and self.slot.allow_tag:
            values.append("Tag")
        self.kind_btn = ctk.CTkSegmentedButton(
            self,
            values=values,
            variable=self.kind_var,
            command=lambda _v: self._sync_kind(),
            fg_color=COLORS["panel_alt"],
            selected_color=COLORS["accent"],
            selected_hover_color=COLORS["accent"],
            unselected_color=COLORS["panel_alt"],
            unselected_hover_color=COLORS["panel_hover"],
            text_color=COLORS["text"],
        )
        self.kind_btn.grid(row=row, column=1, sticky="ew", padx=(0, pad), pady=(pad, 4))
        row += 1

        ctk.CTkLabel(self, text="ID", anchor="w", text_color=COLORS["text_muted"]).grid(
            row=row, column=0, sticky="w", padx=(pad, 8), pady=4
        )
        self.id_entry = ctk.CTkEntry(
            self,
            width=300,
            fg_color=COLORS["slot"],
            border_color=COLORS["slot_border"],
            text_color=COLORS["text"],
            placeholder_text="mod:path",
        )
        self.id_entry.grid(row=row, column=1, sticky="ew", padx=(0, pad), pady=4)
        row += 1

        ctk.CTkLabel(
            self, text="Count", anchor="w", text_color=COLORS["text_muted"]
        ).grid(row=row, column=0, sticky="w", padx=(pad, 8), pady=4)
        self.count = NumberField(
            self,
            width=90,
            min_value=1,
            max_value=self.slot.max_count,
            on_change=None,
        )
        self.count.grid(row=row, column=1, sticky="w", padx=(0, pad), pady=4)
        row += 1
        self.count_label_row = row - 1

        ctk.CTkLabel(
            self, text="Chance", anchor="w", text_color=COLORS["text_muted"]
        ).grid(row=row, column=0, sticky="w", padx=(pad, 8), pady=4)
        self.chance = NumberField(
            self,
            width=90,
            min_value=0,
            max_value=1,
            step=0.05,
            allow_float=True,
            allow_empty=True,
            placeholder="0.0 - 1.0",
        )
        self.chance.grid(row=row, column=1, sticky="w", padx=(0, pad), pady=4)
        row += 1
        self.chance_label_row = row - 1

        ctk.CTkLabel(
            self, text="NBT", anchor="w", text_color=COLORS["text_muted"]
        ).grid(row=row, column=0, sticky="w", padx=(pad, 8), pady=4)
        self.nbt_entry = ctk.CTkEntry(
            self,
            width=300,
            fg_color=COLORS["slot"],
            border_color=COLORS["slot_border"],
            text_color=COLORS["text"],
            placeholder_text="optional, e.g. {Damage:0}",
        )
        self.nbt_entry.grid(row=row, column=1, sticky="ew", padx=(0, pad), pady=4)
        row += 1

        ctk.CTkLabel(
            self, text="Amount", anchor="w", text_color=COLORS["text_muted"]
        ).grid(row=row, column=0, sticky="w", padx=(pad, 8), pady=4)
        self.amount = NumberField(
            self,
            width=90,
            min_value=1,
            max_value=1_000_000,
            step=100,
            allow_empty=True,
            placeholder="1000",
        )
        self.amount.grid(row=row, column=1, sticky="w", padx=(0, pad), pady=4)
        row += 1
        self.amount_label_row = row - 1

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=pad, pady=(12, pad)
        )
        ctk.CTkButton(
            buttons,
            text="Clear",
            width=80,
            fg_color=COLORS["panel_alt"],
            hover_color=COLORS["panel_hover"],
            text_color=COLORS["red"],
            command=self._clear,
        ).pack(side="left")
        ctk.CTkButton(
            buttons,
            text="Cancel",
            width=80,
            fg_color=COLORS["panel_alt"],
            hover_color=COLORS["panel_hover"],
            text_color=COLORS["text"],
            command=self.destroy,
        ).pack(side="right", padx=(6, 0))
        ctk.CTkButton(
            buttons,
            text="Save",
            width=90,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_2"],
            text_color=COLORS["panel"],
            command=self._save,
        ).pack(side="right")

        self._fill()
        self._sync_kind()
        self.bind("<Escape>", lambda e: self.destroy())

    def _fill(self) -> None:
        ing = self.slot.ingredient
        self.id_entry.delete(0, "end")
        self.id_entry.insert(0, ing.id)
        if ing.count > 1:
            self.count.set_value(ing.count)
        if ing.chance is not None:
            self.chance.set_value(ing.chance)
        if ing.nbt:
            self.nbt_entry.insert(0, ing.nbt)
        if ing.amount is not None:
            self.amount.set_value(ing.amount)

    def _sync_kind(self) -> None:
        kind = self.kind_var.get()
        if kind == "Item":
            self.id_entry.configure(placeholder_text="mod:path")
        elif kind == "Tag":
            self.id_entry.configure(placeholder_text="#mod:tag/path")
        else:
            self.id_entry.configure(placeholder_text="mod:fluid_bucket")
        show_count = self.slot.allow_count and kind != "Tag"
        self._show_row(self.count_label_row, show_count)
        self._show_row(self.chance_label_row, self.slot.allow_chance)
        self._show_row(self.amount_label_row, kind == "Fluid")

    def _show_row(self, row: int, visible: bool) -> None:
        for widget in self.grid_slaves():
            info = widget.grid_info()
            if not info:
                continue
            if int(info.get("row", -1)) == row:
                if visible:
                    widget.grid()
                else:
                    widget.grid_remove()

    def _center(self) -> None:
        self.update_idletasks()
        w = max(420, self.winfo_reqwidth())
        h = max(360, self.winfo_reqheight())
        x = self.slot.winfo_rootx() + self.slot.winfo_width() // 2 - w // 2
        y = self.slot.winfo_rooty() + self.slot.winfo_height() // 2 - h // 2
        self.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")

    def _save(self) -> None:
        kind = {"Item": "item", "Tag": "tag", "Fluid": "fluid"}.get(
            self.kind_var.get(), "item"
        )
        raw_id = self.id_entry.get().strip()
        if raw_id.startswith("#"):
            raw_id = raw_id[1:]
        if not raw_id:
            self.slot.clear()
            self.destroy()
            return
        if kind == "fluid":
            raw_id = normalize_fluid_id(raw_id)
        count = self.count.get_value() or 1
        chance = self.chance.get_value()
        amount = self.amount.get_value() if kind == "fluid" else None
        nbt = self.nbt_entry.get().strip() or None
        ing = Ingredient(
            kind=kind,
            id=raw_id,
            count=int(count),
            chance=chance,
            nbt=nbt,
            amount=int(amount) if amount else None,
        )
        self.slot.set_ingredient(ing)
        self.destroy()

    def _clear(self) -> None:
        self.slot.clear()
        self.destroy()
