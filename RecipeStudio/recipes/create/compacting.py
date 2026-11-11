from pathlib import Path

import customtkinter as ctk

from RecipeStudio.components.create_widgets import HeatSelector, IngredientGroup
from RecipeStudio.recipes.base import EditorContext, RecipeEditor
from RecipeStudio.recipes.create.common import CreateEditorBase, custom_body
from RecipeStudio.recipes.base import RecipeModule
from RecipeStudio.theme import COLORS


class CompactingEditor(CreateEditorBase):
    def __init__(self, master, ctx: EditorContext, module: "CompactingModule"):
        super().__init__(master, ctx, module)
        self.item_inputs: IngredientGroup
        self.fluid_inputs: IngredientGroup
        self.outputs: IngredientGroup
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

        self.arrow(top).grid(row=0, column=1, padx=22)

        right = ctk.CTkFrame(top, fg_color="transparent")
        right.grid(row=0, column=2)
        ctk.CTkLabel(
            right,
            text="CHANCE RESULTS",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 9, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        self.outputs = IngredientGroup(
            right,
            self.ctx.app,
            max_items=6,
            slot_size=46,
            allow_chance=True,
            allow_count=True,
            on_change=self.changed,
        )
        self.outputs.pack(anchor="w")

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
        ctk.CTkLabel(
            self,
            text="Click the burner: none → heated → superheated. RMB goes back.",
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 9),
        ).grid(row=2, column=0, pady=(0, 12))

    def validate(self) -> list[str]:
        if not self.item_inputs.ingredients() and not self.fluid_inputs.ingredients():
            return ["Add at least one item or fluid input"]
        if not self.outputs.ingredients():
            return ["Add at least one result"]
        return []

    def serialize(self, event_var: str = "event") -> str:
        if self.validate():
            return ""
        inputs = self.item_inputs.ingredients() + self.fluid_inputs.ingredients()
        extra = {}
        req = self.heat.requirement()
        if req:
            extra["heat_requirement"] = req
        return custom_body(
            event_var,
            "create:compacting",
            inputs,
            self.outputs.ingredients(),
            **extra,
        )

    def clear(self) -> None:
        self.item_inputs.clear(notify=False)
        self.fluid_inputs.clear(notify=False)
        self.outputs.clear(notify=False)
        self.heat.clear()
        self.changed()

    def main_output(self):
        out = self.outputs.ingredients()
        return out[0] if out else None


class CompactingModule(RecipeModule):
    id = "create.compacting"
    title = "Compacting"
    order = 100
    category = "create"
    description = "Basin + press: items/fluids -> chance results, with heat"
    icon = Path(__file__).with_name("icons") / "basin.png"

    def create_editor(self, parent, ctx: EditorContext) -> RecipeEditor:
        return CompactingEditor(parent, ctx, self)


MODULE = CompactingModule()
