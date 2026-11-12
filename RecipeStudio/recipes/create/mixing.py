from pathlib import Path

import customtkinter as ctk

from RecipeStudio.components.create_widgets import HeatSelector, IngredientGroup
from RecipeStudio.recipes.base import (
    EditorContext,
    RecipeEditor,
    RecipeModule,
    ingredients_from_state,
)
from RecipeStudio.recipes.create.common import CreateEditorBase, custom_body
from RecipeStudio.theme import COLORS


class MixingEditor(CreateEditorBase):
    def __init__(self, master, ctx: EditorContext, module: "MixingModule"):
        super().__init__(master, ctx, module)
        self.item_inputs: IngredientGroup
        self.fluid_inputs: IngredientGroup
        self.fluid_outputs: IngredientGroup
        self.item_outputs: IngredientGroup
        self.heat: HeatSelector
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, padx=22, pady=(20, 8))

        left = ctk.CTkFrame(top, fg_color="transparent")
        left.grid(row=0, column=0)
        ctk.CTkLabel(
            left,
            text="ITEM INPUTS",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 9, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        self.item_inputs = IngredientGroup(
            left,
            self.ctx.app,
            max_items=6,
            slot_size=44,
            allow_count=True,
            on_change=self.changed,
        )
        self.item_inputs.pack(anchor="w", pady=(0, 8))
        ctk.CTkLabel(
            left,
            text="FLUID INPUTS",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 9, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        self.fluid_inputs = IngredientGroup(
            left,
            self.ctx.app,
            kind="fluid",
            max_items=4,
            slot_size=44,
            allow_count=False,
            on_change=self.changed,
        )
        self.fluid_inputs.pack(anchor="w")

        self.arrow(top).grid(row=0, column=1, padx=18)

        right = ctk.CTkFrame(top, fg_color="transparent")
        right.grid(row=0, column=2)
        ctk.CTkLabel(
            right,
            text="FLUID OUTPUTS",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 9, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        self.fluid_outputs = IngredientGroup(
            right,
            self.ctx.app,
            kind="fluid",
            max_items=4,
            slot_size=44,
            allow_count=False,
            on_change=self.changed,
        )
        self.fluid_outputs.pack(anchor="w", pady=(0, 8))
        ctk.CTkLabel(
            right,
            text="CHANCE RESULTS",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 9, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        self.item_outputs = IngredientGroup(
            right,
            self.ctx.app,
            max_items=4,
            slot_size=44,
            allow_chance=True,
            allow_count=True,
            on_change=self.changed,
        )
        self.item_outputs.pack(anchor="w")

        heat_frame = ctk.CTkFrame(self, fg_color="transparent")
        heat_frame.grid(row=1, column=0, pady=(8, 18))
        ctk.CTkLabel(
            heat_frame,
            text="HEAT",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 9, "bold"),
        ).pack(side="left", padx=(0, 10))
        self.heat = HeatSelector(heat_frame, self.ctx.app, on_change=self.changed)
        self.heat.pack(side="left")

    def validate(self) -> list[str]:
        if not self.item_inputs.ingredients() and not self.fluid_inputs.ingredients():
            return ["Add at least one item or fluid input"]
        if not self.fluid_outputs.ingredients() and not self.item_outputs.ingredients():
            return ["Add at least one result"]
        return []

    def serialize(self, event_var: str = "event") -> str:
        if self.validate():
            return ""
        inputs = self.item_inputs.ingredients() + self.fluid_inputs.ingredients()
        outputs = self.fluid_outputs.ingredients() + self.item_outputs.ingredients()
        extra = {}
        req = self.heat.requirement()
        if req:
            extra["heat_requirement"] = req
        return custom_body(event_var, "create:mixing", inputs, outputs, **extra)

    def clear(self) -> None:
        for group in (
            self.item_inputs,
            self.fluid_inputs,
            self.fluid_outputs,
            self.item_outputs,
        ):
            group.clear(notify=False)
        self.heat.clear()
        self.changed()

    def main_output(self):
        out = self.item_outputs.ingredients() or self.fluid_outputs.ingredients()
        return out[0] if out else None

    def get_state(self) -> dict:
        return {
            "item_inputs": [i.to_dict() for i in self.item_inputs.ingredients()],
            "fluid_inputs": [i.to_dict() for i in self.fluid_inputs.ingredients()],
            "item_outputs": [i.to_dict() for i in self.item_outputs.ingredients()],
            "fluid_outputs": [i.to_dict() for i in self.fluid_outputs.ingredients()],
            "heat_requirement": self.heat.requirement(),
        }

    def set_state(self, state: dict) -> None:
        self.item_inputs.set_ingredients(
            ingredients_from_state(state.get("item_inputs"))
        )
        self.fluid_inputs.set_ingredients(
            ingredients_from_state(state.get("fluid_inputs"))
        )
        self.item_outputs.set_ingredients(
            ingredients_from_state(state.get("item_outputs"))
        )
        self.fluid_outputs.set_ingredients(
            ingredients_from_state(state.get("fluid_outputs"))
        )
        self.heat.set_requirement(state.get("heat_requirement"), notify=False)
        self.changed()


class MixingModule(RecipeModule):
    id = "create.mixing"
    title = "Mixing"
    order = 200
    category = "create"
    description = "Basin + mixer: items/fluids -> fluids/chance results, with heat"
    icon = Path(__file__).with_name("icons") / "mechanical_mixer.png"

    def create_editor(self, parent, ctx: EditorContext) -> RecipeEditor:
        return MixingEditor(parent, ctx, self)


MODULE = MixingModule()
