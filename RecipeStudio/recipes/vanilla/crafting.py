"""Vanilla crafting table: shaped and shapeless."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from RecipeStudio.components.slot import Slot
from RecipeStudio.model.ingredient import Ingredient
from RecipeStudio.recipes.base import EditorContext, RecipeEditor, RecipeModule
from RecipeStudio.services.codegen import item_literal
from RecipeStudio.theme import COLORS, FONT_UI_SMALL, FONT_UI_BOLD


class CraftingEditor(RecipeEditor):
    def __init__(self, master, ctx: EditorContext, module: "CraftingModule"):
        super().__init__(master, ctx, module)
        self.shapeless = tk.BooleanVar(value=False)
        self.inputs: list[list[Slot]] = []
        self.output: Slot
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, padx=28, pady=26)

        grid_frame = ctk.CTkFrame(top, fg_color="transparent")
        grid_frame.grid(row=0, column=0)
        for r in range(3):
            row = []
            for c in range(3):
                slot = Slot(
                    grid_frame,
                    self.ctx.app,
                    size=54,
                    allow_count=False,
                    max_count=9,
                    allow_tag=True,
                    allow_chance=False,
                    on_change=self.changed,
                )
                slot.grid(row=r, column=c, padx=3, pady=3)
                row.append(slot)
            self.inputs.append(row)

        ctk.CTkLabel(
            top,
            text="→",
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 26, "bold"),
        ).grid(row=0, column=1, padx=30)

        out_frame = ctk.CTkFrame(top, fg_color="transparent")
        out_frame.grid(row=0, column=2)
        ctk.CTkLabel(
            out_frame,
            text="OUTPUT",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 9, "bold"),
        ).pack(pady=(0, 6))
        self.output = Slot(
            out_frame,
            self.ctx.app,
            size=58,
            allow_count=True,
            max_count=64,
            allow_tag=False,
            allow_chance=False,
            on_change=self.changed,
        )
        self.output.pack()

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=1, column=0, pady=(0, 24))
        ctk.CTkCheckBox(
            bottom,
            text="Shapeless",
            variable=self.shapeless,
            command=self._toggle_shapeless,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_2"],
            text_color=COLORS["text"],
            font=FONT_UI_SMALL,
            checkbox_width=18,
            checkbox_height=18,
        ).pack()
        ctk.CTkLabel(
            bottom,
            text="Shaped mode ignores per-slot counts. Shapeless total must be ≤ 9.",
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 9),
        ).pack(pady=(8, 0))

    def _toggle_shapeless(self) -> None:
        for row in self.inputs:
            for slot in row:
                slot.set_allow_count(self.shapeless.get())
        self.changed()

    # ------------------------------------------------------------------
    def _flat(self) -> list[Ingredient]:
        return [
            slot.ingredient
            for row in self.inputs
            for slot in row
            if not slot.ingredient.is_empty
        ]

    def _trimmed(self) -> list[list[Ingredient]]:
        grid = [[slot.ingredient.copy() for slot in row] for row in self.inputs]
        rows = [r for r in range(3) if any(not grid[r][c].is_empty for c in range(3))]
        cols = [c for c in range(3) if any(not grid[r][c].is_empty for r in range(3))]
        if not rows or not cols:
            return []
        return [[grid[r][c] for c in cols] for r in rows]

    def validate(self) -> list[str]:
        errors: list[str] = []
        out = self.output.ingredient
        if out.is_empty:
            errors.append("Add an output item")
        elif out.kind != "item":
            errors.append("Output must be an item")
        if self.shapeless.get():
            flat = self._flat()
            if not flat:
                errors.append("Add at least one ingredient")
            total = sum(max(1, i.count) for i in flat)
            if total > 9:
                errors.append(f"Shapeless total is {total}; maximum is 9")
        else:
            if not self._trimmed():
                errors.append("Add at least one ingredient")
        return errors

    def serialize(self, event_var: str = "event") -> str:
        if self.validate():
            return ""
        out = item_literal(self.output.ingredient, output=True)
        if self.shapeless.get():
            flat = self._flat()
            lines = [f"{event_var}.shapeless({out}, ["]
            for ing in flat:
                lines.append(f"  {item_literal(ing)},")
            lines.append("])")
            return "\n".join(lines)

        grid = self._trimmed()
        keys = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        key_for: dict[tuple, str] = {}
        mapping: list[tuple[str, Ingredient]] = []
        pattern: list[str] = []
        for row in grid:
            chars = []
            for ing in row:
                if ing.is_empty:
                    chars.append(" ")
                    continue
                token = (ing.kind, ing.id, ing.nbt)
                if token not in key_for:
                    key = keys[len(key_for)]
                    key_for[token] = key
                    mapping.append((key, ing))
                chars.append(key_for[token])
            pattern.append("".join(chars))

        lines = [f"{event_var}.shaped({out}, ["]
        for row in pattern:
            lines.append(f"  '{row}',")
        lines.append("], {")
        for key, ing in mapping:
            lines.append(f"  {key}: {item_literal(ing)},")
        lines.append("})")
        return "\n".join(lines)

    def clear(self) -> None:
        for row in self.inputs:
            for slot in row:
                slot.clear(notify=False)
        self.output.clear(notify=False)
        self.shapeless.set(False)
        self._toggle_shapeless()
        self.changed()

    def main_output(self) -> Ingredient | None:
        return self.output.ingredient.copy()

    def get_state(self) -> dict:
        return {
            "shapeless": self.shapeless.get(),
            "inputs": [
                [slot.ingredient.to_dict() for slot in row] for row in self.inputs
            ],
            "output": self.output.ingredient.to_dict(),
        }

    def set_state(self, state: dict) -> None:
        self.shapeless.set(bool(state.get("shapeless", False)))
        for r, row in enumerate(state.get("inputs", [])):
            for c, data in enumerate(row):
                if r < 3 and c < 3:
                    self.inputs[r][c].set_ingredient(
                        Ingredient.from_dict(data), notify=False
                    )
        if "output" in state:
            self.output.set_ingredient(
                Ingredient.from_dict(state["output"]), notify=False
            )
        self._toggle_shapeless()
        self.changed()


class CraftingModule(RecipeModule):
    id = "vanilla.crafting"
    title = "Crafting"
    order = 10
    description = "Shaped or shapeless crafting table recipe"

    def create_editor(self, parent, ctx: EditorContext) -> RecipeEditor:
        return CraftingEditor(parent, ctx, self)


MODULE = CraftingModule()
