"""Shared editors and code generation for Create Ore Excavation."""

from __future__ import annotations

import tkinter as tk
from typing import Callable

import customtkinter as ctk

from RecipeStudio.components.create_widgets import FluidAmountField, IngredientGroup
from RecipeStudio.components.number_field import NumberField
from RecipeStudio.components.slot import Slot
from RecipeStudio.components.time_field import TimeField
from RecipeStudio.model.ingredient import Ingredient, normalize_fluid_id
from RecipeStudio.recipes.base import (
    EditorContext,
    RecipeEditor,
    RecipeModule,
    ingredient_from_state,
    ingredients_from_state,
)
from RecipeStudio.recipes.create.common import CreateEditorBase
from RecipeStudio.services.codegen import format_number, item_literal, quote
from RecipeStudio.theme import COLORS, FONT_UI_SMALL

DRILL_TIERS = {
    "Any": "#createoreexcavation:drills",
    "Iron": "createoreexcavation:drill",
    "Diamond": "createoreexcavation:diamond_drill",
    "Netherite": "createoreexcavation:netherite_drill",
}

FINITE_MODES = {
    "default": "defaultFinite",
    "never": "alwaysInfinite",
    "always": "alwaysFinite",
}


def _label(master, text: str, bold: bool = False) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        master,
        text=text,
        text_color=COLORS["text_muted"],
        font=("DejaVu Sans", 9, "bold" if bold else "normal"),
    )


class VeinEditorBase(CreateEditorBase):
    """Common vein fields shared by item and fluid vein tabs."""

    default_vein_id = "kubejs:ore_vein_type/custom"
    default_name = "Custom Vein"
    default_icon = "minecraft:stone"
    default_amount_min = 1.0
    default_amount_max = 2.0
    default_finite = "default"
    default_whitelist = "minecraft:is_overworld"

    def __init__(self, master, ctx: EditorContext, module: RecipeModule):
        super().__init__(master, ctx, module)
        self.name_var = ctk.StringVar(value=self.default_name)
        self.vein_id_var = ctk.StringVar(value=self.default_vein_id)
        self.translate_var = tk.BooleanVar(value=False)
        self.finite_var = ctk.StringVar(value=self.default_finite)
        self.whitelist_var = ctk.StringVar(value=self.default_whitelist)
        self.blacklist_var = ctk.StringVar(value="")
        self.icon: Slot
        self.priority: NumberField
        self.amount_min: NumberField
        self.amount_max: NumberField
        self.spacing: NumberField
        self.separation: NumberField
        self.salt: NumberField
        self._traced = False

    # ------------------------------------------------------------------
    # widgets
    # ------------------------------------------------------------------
    def _entry(self, master, var, width: int) -> ctk.CTkEntry:
        entry = ctk.CTkEntry(
            master,
            textvariable=var,
            width=width,
            height=28,
            fg_color=COLORS["slot"],
            border_color=COLORS["slot_border"],
            text_color=COLORS["text"],
            font=FONT_UI_SMALL,
        )
        if not self._traced:
            self._traced = True
            for value in (
                self.name_var,
                self.vein_id_var,
                self.whitelist_var,
                self.blacklist_var,
            ):
                value.trace_add("write", lambda *_: self.changed())
        return entry

    def _build_vein(self, parent) -> None:
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.grid(row=0, column=0, sticky="w", padx=22, pady=(18, 4))

        head = ctk.CTkFrame(box, fg_color="transparent")
        head.grid(row=0, column=0, sticky="w")
        _label(head, "VEIN NAME", True).grid(row=0, column=0, sticky="w")
        _label(head, "VEIN ID", True).grid(row=0, column=1, sticky="w", padx=(12, 0))
        _label(head, "ICON", True).grid(row=0, column=2, sticky="w", padx=(12, 0))
        self._entry(head, self.name_var, 220).grid(
            row=1, column=0, sticky="w", pady=(2, 0)
        )
        self._entry(head, self.vein_id_var, 250).grid(
            row=1, column=1, sticky="w", padx=(12, 0), pady=(2, 0)
        )
        self.icon = self.slot(head, size=44, allow_count=False, allow_tag=False)
        self.icon.grid(row=1, column=2, sticky="w", padx=(12, 0), pady=(2, 0))
        ctk.CTkCheckBox(
            head,
            text="name is a translation key",
            variable=self.translate_var,
            command=self.changed,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_2"],
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 9),
            checkbox_width=16,
            checkbox_height=16,
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))

        options = ctk.CTkFrame(parent, fg_color="transparent")
        options.grid(row=1, column=0, sticky="w", padx=22, pady=(6, 4))

        _label(options, "FINITE", True).grid(row=0, column=0, sticky="w")
        ctk.CTkSegmentedButton(
            options,
            values=["default", "never", "always"],
            variable=self.finite_var,
            command=lambda _v: self.changed(),
            height=26,
            fg_color=COLORS["panel_alt"],
            selected_color=COLORS["accent"],
            selected_hover_color=COLORS["accent_2"],
            unselected_color=COLORS["panel_alt"],
            unselected_hover_color=COLORS["panel_hover"],
            text_color=COLORS["text"],
            font=("DejaVu Sans", 9),
        ).grid(row=1, column=0, sticky="w", padx=(0, 14))

        _label(options, "PRIORITY", True).grid(row=0, column=1, sticky="w")
        self.priority = NumberField(
            options,
            width=70,
            min_value=0,
            max_value=10000,
            step=1,
            on_change=self.changed,
        )
        self.priority.set_value(0)
        self.priority.grid(row=1, column=1, sticky="w", padx=(0, 14))

        _label(options, "VEIN SIZE MIN / MAX", True).grid(
            row=0, column=2, sticky="w", columnspan=2
        )
        self.amount_min = NumberField(
            options,
            width=74,
            min_value=0.0,
            max_value=10000.0,
            step=0.5,
            allow_float=True,
            on_change=self.changed,
        )
        self.amount_min.set_value(self.default_amount_min)
        self.amount_min.grid(row=1, column=2, sticky="w", padx=(0, 4))
        self.amount_max = NumberField(
            options,
            width=74,
            min_value=0.0,
            max_value=10000.0,
            step=0.5,
            allow_float=True,
            on_change=self.changed,
        )
        self.amount_max.set_value(self.default_amount_max)
        self.amount_max.grid(row=1, column=3, sticky="w", padx=(0, 14))

        _label(options, "PLACEMENT SPACING / SEPARATION / SALT", True).grid(
            row=0, column=4, sticky="w", columnspan=3
        )
        for column, (field, value) in enumerate(
            (("spacing", 64), ("separation", 8), ("salt", 0)), start=4
        ):
            widget = NumberField(
                options,
                width=74,
                min_value=0,
                max_value=2_000_000_000,
                step=1,
                on_change=self.changed,
            )
            widget.set_value(value)
            widget.grid(row=1, column=column, sticky="w", padx=(0, 4))
            setattr(self, field, widget)

        biomes = ctk.CTkFrame(parent, fg_color="transparent")
        biomes.grid(row=2, column=0, sticky="w", padx=22, pady=(2, 8))
        _label(biomes, "BIOME WHITELIST (comma separated, optional)", True).grid(
            row=0, column=0, sticky="w"
        )
        _label(biomes, "BIOME BLACKLIST (comma separated, optional)", True).grid(
            row=0, column=1, sticky="w", padx=(12, 0)
        )
        self._entry(biomes, self.whitelist_var, 330).grid(
            row=1, column=0, sticky="w", pady=(2, 0)
        )
        self._entry(biomes, self.blacklist_var, 330).grid(
            row=1, column=1, sticky="w", padx=(12, 0), pady=(2, 0)
        )

    # ------------------------------------------------------------------
    # code generation
    # ------------------------------------------------------------------
    @staticmethod
    def _int(field: NumberField, default: int) -> int:
        value = field.get_value()
        return int(value) if value is not None else int(default)

    @staticmethod
    def _float(field: NumberField, default: float) -> float:
        value = field.get_value()
        return float(value) if value is not None else float(default)

    def vein_id(self) -> str:
        return self.vein_id_var.get().strip() or self.default_vein_id

    def vein_code(self, event_var: str = "event") -> str:
        name = self.name_var.get().strip() or self.default_name
        name_literal = (
            f"Text.translate({quote(name)})"
            if self.translate_var.get()
            else quote(name)
        )
        icon = item_literal(self.icon.ingredient) or quote(self.default_icon)
        body = f"{event_var}.recipes.createoreexcavation.vein({name_literal}, {icon})"

        chains = [f"id({quote(self.vein_id())})"]
        chains.append(
            "veinSize("
            f"{format_number(self._float(self.amount_min, self.default_amount_min))}, "
            f"{format_number(self._float(self.amount_max, self.default_amount_max))})"
        )
        chains.append(
            "placement("
            f"{self._int(self.spacing, 64)}, "
            f"{self._int(self.separation, 8)}, "
            f"{self._int(self.salt, 0)})"
        )
        chains.append(f"{FINITE_MODES.get(self.finite_var.get(), 'defaultFinite')}()")
        priority = self._int(self.priority, 0)
        if priority:
            chains.append(f"priority({priority})")
        for tag in self._split_tags(self.whitelist_var.get()):
            chains.append(f"biomeWhitelist({quote(tag)})")
        for tag in self._split_tags(self.blacklist_var.get()):
            chains.append(f"biomeBlacklist({quote(tag)})")
        return body + "." + ".".join(chains)

    @staticmethod
    def _split_tags(raw: str) -> list[str]:
        return [part.strip().lstrip("#") for part in raw.split(",") if part.strip()]

    def excavating_chains(
        self,
        drill_var: ctk.StringVar,
        stress: NumberField,
        fluid: Slot,
        fluid_amount: FluidAmountField,
        priority: NumberField,
    ) -> str:
        chains = [
            f"drill({quote(DRILL_TIERS.get(drill_var.get(), DRILL_TIERS['Any']))})"
        ]
        stress_value = self._int(stress, 256)
        if stress_value != 256:
            chains.append(f"stress({stress_value})")
        if not fluid.ingredient.is_empty:
            fluid_ing = fluid.ingredient.copy()
            fluid_ing.amount = fluid_amount.value()
            chains.append(f"fluid({item_literal(fluid_ing)})")
        priority_value = self._int(priority, 0)
        if priority_value:
            chains.append(f"priority({priority_value})")
        return "." + ".".join(chains)

    # ------------------------------------------------------------------
    # state
    # ------------------------------------------------------------------
    def get_vein_state(self) -> dict:
        return {
            "name": self.name_var.get(),
            "translate": bool(self.translate_var.get()),
            "vein_id": self.vein_id_var.get(),
            "icon": self.icon.ingredient.to_dict(),
            "finite": self.finite_var.get(),
            "priority": self._int(self.priority, 0),
            "amount_min": self._float(self.amount_min, self.default_amount_min),
            "amount_max": self._float(self.amount_max, self.default_amount_max),
            "spacing": self._int(self.spacing, 64),
            "separation": self._int(self.separation, 8),
            "salt": self._int(self.salt, 0),
            "whitelist": self.whitelist_var.get(),
            "blacklist": self.blacklist_var.get(),
        }

    def set_vein_state(self, state: dict) -> None:
        self.name_var.set(str(state.get("name", self.default_name)))
        self.translate_var.set(bool(state.get("translate", False)))
        self.vein_id_var.set(str(state.get("vein_id", self.default_vein_id)))
        self.icon.set_ingredient(ingredient_from_state(state.get("icon")), notify=False)
        self.finite_var.set(str(state.get("finite", self.default_finite)))
        self.priority.set_value(int(state.get("priority", 0) or 0))
        self.amount_min.set_value(
            float(state.get("amount_min", self.default_amount_min))
        )
        self.amount_max.set_value(
            float(state.get("amount_max", self.default_amount_max))
        )
        self.spacing.set_value(int(state.get("spacing", 64) or 64))
        self.separation.set_value(int(state.get("separation", 8) or 8))
        self.salt.set_value(int(state.get("salt", 0) or 0))
        self.whitelist_var.set(str(state.get("whitelist", self.default_whitelist)))
        self.blacklist_var.set(str(state.get("blacklist", "")))

    def clear_vein(self) -> None:
        self.name_var.set(self.default_name)
        self.vein_id_var.set(self.default_vein_id)
        self.translate_var.set(False)
        self.icon.clear(notify=False)
        self.finite_var.set(self.default_finite)
        self.priority.set_value(0)
        self.amount_min.set_value(self.default_amount_min)
        self.amount_max.set_value(self.default_amount_max)
        self.spacing.set_value(64)
        self.separation.set_value(8)
        self.salt.set_value(0)
        self.whitelist_var.set(self.default_whitelist)
        self.blacklist_var.set("")

    def validate_vein(self) -> list[str]:
        errors: list[str] = []
        if not self.name_var.get().strip():
            errors.append("Add a vein name")
        if not self.vein_id_var.get().strip():
            errors.append("Add a vein id")
        return errors
