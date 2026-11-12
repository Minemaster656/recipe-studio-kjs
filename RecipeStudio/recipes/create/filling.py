from pathlib import Path

import customtkinter as ctk

from RecipeStudio.components.create_widgets import FluidAmountField
from RecipeStudio.recipes.base import (
    EditorContext,
    RecipeEditor,
    RecipeModule,
    ingredient_from_state,
)
from RecipeStudio.recipes.create.common import CreateEditorBase, custom_body
from RecipeStudio.theme import COLORS


class FillingEditor(CreateEditorBase):
    def __init__(self, master, ctx: EditorContext, module: "FillingModule"):
        super().__init__(master, ctx, module)
        self.item_in: object
        self.fluid_in: object
        self.output: object
        self.amount: FluidAmountField
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, padx=28, pady=(24, 10))

        left = ctk.CTkFrame(top, fg_color="transparent")
        left.grid(row=0, column=0)
        ctk.CTkLabel(
            left,
            text="ITEM INPUT",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 9, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        self.item_in = self.slot(left, size=54, allow_count=True, allow_tag=True)
        self.item_in.pack(anchor="w", pady=(0, 8))
        ctk.CTkLabel(
            left,
            text="FLUID INPUT",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 9, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        self.fluid_in = self.slot(
            left, size=54, allow_count=False, allow_tag=False, allow_fluid=True
        )
        self.fluid_in.pack(anchor="w", pady=(0, 6))
        self.amount = FluidAmountField(left, value=1000, on_change=self._fluid_changed)
        self.amount.pack(anchor="w")

        self.arrow(top).grid(row=0, column=1, padx=28)

        right = ctk.CTkFrame(top, fg_color="transparent")
        right.grid(row=0, column=2)
        ctk.CTkLabel(
            right,
            text="ITEM OUTPUT",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 9, "bold"),
        ).pack(pady=(0, 4))
        self.output = self.slot(right, size=58, allow_count=True, allow_tag=False)
        self.output.pack()

        ctk.CTkLabel(
            self,
            text="The fluid amount is applied to the fluid input slot.",
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 9),
        ).grid(row=1, column=0, pady=(0, 16))

    def _fluid_changed(self) -> None:
        ing = self.fluid_in.ingredient
        if not ing.is_empty:
            ing.amount = self.amount.value()
            self.fluid_in._draw()
        self.changed()

    def validate(self) -> list[str]:
        errors = []
        if self.item_in.ingredient.is_empty:
            errors.append("Add an input item")
        if self.fluid_in.ingredient.is_empty:
            errors.append("Add an input fluid")
        if self.output.ingredient.is_empty:
            errors.append("Add an output item")
        return errors

    def serialize(self, event_var: str = "event") -> str:
        if self.validate():
            return ""
        fluid = self.fluid_in.ingredient.copy()
        fluid.amount = self.amount.value()
        return custom_body(
            event_var,
            "create:filling",
            [self.item_in.ingredient, fluid],
            [self.output.ingredient],
        )

    def clear(self) -> None:
        self.item_in.clear(notify=False)
        self.fluid_in.clear(notify=False)
        self.output.clear(notify=False)
        self.amount.clear()
        self.changed()

    def main_output(self):
        return (
            self.output.ingredient.copy()
            if not self.output.ingredient.is_empty
            else None
        )

    def get_state(self) -> dict:
        return {
            "item_input": self.item_in.ingredient.to_dict(),
            "fluid_input": self.fluid_in.ingredient.to_dict(),
            "amount": self.amount.value(),
            "output": self.output.ingredient.to_dict(),
        }

    def set_state(self, state: dict) -> None:
        self.item_in.set_ingredient(
            ingredient_from_state(state.get("item_input")), notify=False
        )
        fluid = ingredient_from_state(state.get("fluid_input"))
        amount = state.get("amount")
        if amount is None and fluid.amount is not None:
            amount = fluid.amount
        self.amount.set_value(int(amount) if amount is not None else 1000)
        if not fluid.is_empty:
            fluid.amount = int(amount) if amount is not None else 1000
        self.fluid_in.set_ingredient(fluid, notify=False)
        self.output.set_ingredient(
            ingredient_from_state(state.get("output")), notify=False
        )
        self.changed()


class FillingModule(RecipeModule):
    id = "create.filling"
    title = "Filling"
    order = 150
    category = "create"
    description = "Spout: item + fluid -> item"
    icon = Path(__file__).with_name("icons") / "spout.png"

    def create_editor(self, parent, ctx: EditorContext) -> RecipeEditor:
        return FillingEditor(parent, ctx, self)


MODULE = FillingModule()
