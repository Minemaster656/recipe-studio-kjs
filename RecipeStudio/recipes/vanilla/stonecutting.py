"""Vanilla stonecutter."""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk

from RecipeStudio.components.slot import Slot
from RecipeStudio.model.ingredient import Ingredient
from RecipeStudio.recipes.base import EditorContext, RecipeEditor, RecipeModule
from RecipeStudio.services.codegen import item_literal
from RecipeStudio.theme import COLORS


class StonecuttingEditor(RecipeEditor):
    def __init__(self, master, ctx: EditorContext, module: "StonecuttingModule"):
        super().__init__(master, ctx, module)
        self.input: Slot
        self.output: Slot
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, padx=28, pady=34)

        in_frame = ctk.CTkFrame(top, fg_color="transparent")
        in_frame.grid(row=0, column=0)
        ctk.CTkLabel(
            in_frame,
            text="INPUT",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 9, "bold"),
        ).pack(pady=(0, 6))
        self.input = Slot(
            in_frame,
            self.ctx.app,
            size=58,
            allow_count=False,
            allow_tag=True,
            on_change=self.changed,
        )
        self.input.pack()

        ctk.CTkLabel(
            top,
            text="→",
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 26, "bold"),
        ).grid(row=0, column=1, padx=34)

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
            on_change=self.changed,
        )
        self.output.pack()

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.input.ingredient.is_empty:
            errors.append("Add an input")
        if self.output.ingredient.is_empty:
            errors.append("Add an output")
        elif self.output.ingredient.kind != "item":
            errors.append("Output must be an item")
        return errors

    def serialize(self, event_var: str = "event") -> str:
        if self.validate():
            return ""
        out = item_literal(self.output.ingredient, output=True)
        inp = item_literal(self.input.ingredient)
        return f"{event_var}.stonecutting({out}, {inp})"

    def clear(self) -> None:
        self.input.clear(notify=False)
        self.output.clear(notify=False)
        self.changed()

    def main_output(self) -> Ingredient | None:
        return self.output.ingredient.copy()

    def get_state(self) -> dict:
        return {
            "input": self.input.ingredient.to_dict(),
            "output": self.output.ingredient.to_dict(),
        }

    def set_state(self, state: dict) -> None:
        for key, slot in (("input", self.input), ("output", self.output)):
            if key in state:
                slot.set_ingredient(Ingredient.from_dict(state[key]), notify=False)
        self.changed()


class StonecuttingModule(RecipeModule):
    id = "vanilla.stonecutting"
    title = "Stonecutting"
    order = 60
    description = "Stonecutter recipe"
    icon = Path(__file__).with_name("icons") / "stonecutter.png"

    def create_editor(self, parent, ctx: EditorContext) -> RecipeEditor:
        return StonecuttingEditor(parent, ctx, self)


MODULE = StonecuttingModule()
