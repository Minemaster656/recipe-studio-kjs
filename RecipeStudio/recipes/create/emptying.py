from pathlib import Path

import customtkinter as ctk

from RecipeStudio.components.create_widgets import FluidAmountField
from RecipeStudio.model.ingredient import Ingredient
from RecipeStudio.recipes.base import (
    EditorContext,
    RecipeEditor,
    RecipeModule,
    ingredient_from_state,
)
from RecipeStudio.recipes.create.common import CreateEditorBase, custom_body
from RecipeStudio.theme import COLORS, FONT_UI_SMALL


class EmptyingEditor(CreateEditorBase):
    def __init__(self, master, ctx: EditorContext, module: "EmptyingModule"):
        super().__init__(master, ctx, module)
        self.input: object
        self.item_out: object
        self.fluid_out: object
        self.amount: FluidAmountField
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, padx=28, pady=(28, 12))

        in_frame = ctk.CTkFrame(top, fg_color="transparent")
        in_frame.grid(row=0, column=0)
        ctk.CTkLabel(
            in_frame,
            text="ITEM INPUT",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 9, "bold"),
        ).pack(pady=(0, 4))
        self.input = self.slot(in_frame, size=58, allow_count=True, allow_tag=True)
        self.input.pack()

        self.arrow(top).grid(row=0, column=1, padx=26)

        out = ctk.CTkFrame(top, fg_color="transparent")
        out.grid(row=0, column=2)
        ctk.CTkLabel(
            out,
            text="ITEM OUTPUT",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 9, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        self.item_out = self.slot(out, size=54, allow_count=True, allow_tag=False)
        self.item_out.pack(anchor="w", pady=(0, 8))
        ctk.CTkLabel(
            out,
            text="FLUID OUTPUT",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 9, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        self.fluid_out = self.slot(
            out, size=54, allow_count=False, allow_tag=False, allow_fluid=True
        )
        self.fluid_out.pack(anchor="w", pady=(0, 6))
        self.amount = FluidAmountField(out, value=1000, on_change=self._fluid_changed)
        self.amount.pack(anchor="w")

        ctk.CTkLabel(
            self,
            text="The fluid amount is applied to the fluid output slot.",
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 9),
        ).grid(row=1, column=0, pady=(0, 16))

    def _fluid_changed(self) -> None:
        ing = self.fluid_out.ingredient
        if not ing.is_empty:
            ing.amount = self.amount.value()
            self.fluid_out._draw()
        self.changed()

    def validate(self) -> list[str]:
        errors = []
        if self.input.ingredient.is_empty:
            errors.append("Add an input item")
        if self.item_out.ingredient.is_empty and self.fluid_out.ingredient.is_empty:
            errors.append("Add an item or fluid output")
        return errors

    def serialize(self, event_var: str = "event") -> str:
        if self.validate():
            return ""
        outputs = []
        if not self.item_out.ingredient.is_empty:
            outputs.append(self.item_out.ingredient.copy())
        if not self.fluid_out.ingredient.is_empty:
            fluid = self.fluid_out.ingredient.copy()
            fluid.amount = self.amount.value()
            outputs.append(fluid)
        return custom_body(
            event_var, "create:emptying", [self.input.ingredient], outputs
        )

    def clear(self) -> None:
        self.input.clear(notify=False)
        self.item_out.clear(notify=False)
        self.fluid_out.clear(notify=False)
        self.amount.clear()
        self.changed()

    def main_output(self):
        return (
            self.item_out.ingredient.copy()
            if not self.item_out.ingredient.is_empty
            else None
        )

    def get_state(self) -> dict:
        return {
            "input": self.input.ingredient.to_dict(),
            "item_output": self.item_out.ingredient.to_dict(),
            "fluid_output": self.fluid_out.ingredient.to_dict(),
            "amount": self.amount.value(),
        }

    def set_state(self, state: dict) -> None:
        self.input.set_ingredient(
            ingredient_from_state(state.get("input")), notify=False
        )
        self.item_out.set_ingredient(
            ingredient_from_state(state.get("item_output")), notify=False
        )
        fluid = ingredient_from_state(state.get("fluid_output"))
        amount = state.get("amount")
        if amount is None and fluid.amount is not None:
            amount = fluid.amount
        self.amount.set_value(int(amount) if amount is not None else 1000)
        if not fluid.is_empty:
            fluid.amount = int(amount) if amount is not None else 1000
        self.fluid_out.set_ingredient(fluid, notify=False)
        self.changed()


class EmptyingModule(RecipeModule):
    id = "create.emptying"
    title = "Emptying"
    order = 140
    category = "create"
    description = "Item drain: container -> item + fluid"
    icon = Path(__file__).with_name("icons") / "item_drain.png"

    def create_editor(self, parent, ctx: EditorContext) -> RecipeEditor:
        return EmptyingEditor(parent, ctx, self)


MODULE = EmptyingModule()
