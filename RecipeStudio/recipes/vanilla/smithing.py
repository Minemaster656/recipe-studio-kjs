"""Vanilla smithing table recipe (1.21 layout)."""

from __future__ import annotations

import customtkinter as ctk

from RecipeStudio.components.slot import Slot
from RecipeStudio.model.ingredient import Ingredient
from RecipeStudio.recipes.base import EditorContext, RecipeEditor, RecipeModule
from RecipeStudio.services.codegen import item_literal
from RecipeStudio.theme import COLORS, FONT_UI_SMALL


class SmithingEditor(RecipeEditor):
    def __init__(self, master, ctx: EditorContext, module: "SmithingModule"):
        super().__init__(master, ctx, module)
        self.template: Slot
        self.base: Slot
        self.addition: Slot
        self.output: Slot
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, padx=28, pady=26)

        stack = ctk.CTkFrame(top, fg_color="transparent")
        stack.grid(row=0, column=0)

        def labeled_slot(label: str) -> Slot:
            row = ctk.CTkFrame(stack, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(
                row,
                text=label,
                width=78,
                anchor="e",
                text_color=COLORS["text_muted"],
                font=FONT_UI_SMALL,
            ).pack(side="left", padx=(0, 10))
            slot = Slot(
                row,
                self.ctx.app,
                size=52,
                allow_tag=True,
                on_change=self.changed,
            )
            slot.pack(side="left")
            return slot

        self.template = labeled_slot("TEMPLATE")
        self.base = labeled_slot("BASE")
        self.addition = labeled_slot("ADDITION")

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
        if self.template.ingredient.is_empty:
            errors.append("Add a template")
        if self.base.ingredient.is_empty:
            errors.append("Add a base item")
        if self.addition.ingredient.is_empty:
            errors.append("Add an addition")
        if self.output.ingredient.is_empty:
            errors.append("Add an output")
        elif self.output.ingredient.kind != "item":
            errors.append("Output must be an item")
        return errors

    def serialize(self, event_var: str = "event") -> str:
        if self.validate():
            return ""
        out = item_literal(self.output.ingredient, output=True)
        template = item_literal(self.template.ingredient)
        base = item_literal(self.base.ingredient)
        addition = item_literal(self.addition.ingredient)
        return f"{event_var}.smithing({out}, {template}, {base}, {addition})"

    def clear(self) -> None:
        for slot in (self.template, self.base, self.addition, self.output):
            slot.clear(notify=False)
        self.changed()

    def main_output(self) -> Ingredient | None:
        return self.output.ingredient.copy()

    def get_state(self) -> dict:
        return {
            "template": self.template.ingredient.to_dict(),
            "base": self.base.ingredient.to_dict(),
            "addition": self.addition.ingredient.to_dict(),
            "output": self.output.ingredient.to_dict(),
        }

    def set_state(self, state: dict) -> None:
        for key, slot in (
            ("template", self.template),
            ("base", self.base),
            ("addition", self.addition),
            ("output", self.output),
        ):
            if key in state:
                slot.set_ingredient(Ingredient.from_dict(state[key]), notify=False)
        self.changed()


class SmithingModule(RecipeModule):
    id = "vanilla.smithing"
    title = "Smithing"
    order = 70
    description = "Smithing table: template + base + addition -> output"

    def create_editor(self, parent, ctx: EditorContext) -> RecipeEditor:
        return SmithingEditor(parent, ctx, self)


MODULE = SmithingModule()
