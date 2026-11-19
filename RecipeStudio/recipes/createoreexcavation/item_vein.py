from pathlib import Path

import customtkinter as ctk

from RecipeStudio.components.create_widgets import FluidAmountField, IngredientGroup
from RecipeStudio.components.number_field import NumberField
from RecipeStudio.components.slot import Slot
from RecipeStudio.components.time_field import TimeField
from RecipeStudio.recipes.base import (
    EditorContext,
    RecipeEditor,
    RecipeModule,
    ingredient_from_state,
    ingredients_from_state,
)
from RecipeStudio.recipes.create.common import js_array
from RecipeStudio.recipes.createoreexcavation.common import (
    DRILL_TIERS,
    VeinEditorBase,
    _label,
)
from RecipeStudio.services.codegen import item_literal, quote
from RecipeStudio.theme import COLORS, FONT_UI_SMALL


class ItemVeinEditor(VeinEditorBase):
    default_vein_id = "kubejs:ore_vein_type/iron"
    default_name = "Iron Vein"
    default_icon = "minecraft:iron_ore"
    default_amount_min = 10.0
    default_amount_max = 30.0

    def __init__(self, master, ctx: EditorContext, module: "ItemVeinModule"):
        super().__init__(master, ctx, module)
        self.outputs: IngredientGroup
        self.drill_var = ctk.StringVar(value="Any")
        self.ticks: TimeField
        self.stress: NumberField
        self.priority_recipe: NumberField
        self.fluid: Slot
        self.fluid_amount: FluidAmountField
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self._build_vein(self)

        box = ctk.CTkFrame(self, fg_color="transparent")
        box.grid(row=3, column=0, sticky="w", padx=22, pady=(2, 16))

        left = ctk.CTkFrame(box, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nw")
        _label(left, "DRILLING OUTPUTS (chance / count)", True).pack(
            anchor="w", pady=(0, 4)
        )
        self.outputs = IngredientGroup(
            left,
            self.ctx.app,
            max_items=8,
            slot_size=44,
            allow_chance=True,
            allow_count=True,
            on_change=self.changed,
        )
        self.outputs.pack(anchor="w")

        right = ctk.CTkFrame(box, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nw", padx=(26, 0))

        row = ctk.CTkFrame(right, fg_color="transparent")
        row.pack(anchor="w")
        _label(row, "DRILL TIER", True).pack(side="left", padx=(0, 8))
        ctk.CTkSegmentedButton(
            row,
            values=list(DRILL_TIERS),
            variable=self.drill_var,
            command=lambda _v: self.changed(),
            height=26,
            fg_color=COLORS["panel_alt"],
            selected_color=COLORS["accent"],
            selected_hover_color=COLORS["accent_2"],
            unselected_color=COLORS["panel_alt"],
            unselected_hover_color=COLORS["panel_hover"],
            text_color=COLORS["text"],
            font=("DejaVu Sans", 9),
        ).pack(side="left")

        row = ctk.CTkFrame(right, fg_color="transparent")
        row.pack(anchor="w", pady=(8, 0))
        _label(row, "TICKS", True).pack(side="left", padx=(0, 8))
        self.ticks = TimeField(
            row, default_ticks=600, on_change=self.changed, width=110
        )
        self.ticks.pack(side="left", padx=(0, 14))
        _label(row, "STRESS", True).pack(side="left", padx=(0, 6))
        self.stress = NumberField(
            row,
            width=82,
            min_value=1,
            max_value=1_000_000,
            step=1,
            on_change=self.changed,
        )
        self.stress.set_value(256)
        self.stress.pack(side="left", padx=(0, 14))
        _label(row, "PRIORITY", True).pack(side="left", padx=(0, 6))
        self.priority_recipe = NumberField(
            row,
            width=64,
            min_value=0,
            max_value=10000,
            step=1,
            on_change=self.changed,
        )
        self.priority_recipe.set_value(0)
        self.priority_recipe.pack(side="left")

        row = ctk.CTkFrame(right, fg_color="transparent")
        row.pack(anchor="w", pady=(8, 0))
        _label(row, "REQUIRED FLUID (optional)", True).pack(side="left", padx=(0, 8))
        self.fluid = self.slot(
            row, size=40, allow_count=False, allow_tag=False, allow_fluid=True
        )
        self.fluid.pack(side="left")
        self.fluid_amount = FluidAmountField(
            row, value=1000, on_change=self._fluid_changed, width=100
        )
        self.fluid_amount.pack(side="left", padx=(6, 0))

        ctk.CTkLabel(
            self,
            text=(
                "The vein is emitted first, then the drilling recipe that "
                "references its id."
            ),
            text_color=COLORS["text_dim"],
            font=FONT_UI_SMALL,
        ).grid(row=4, column=0, sticky="w", padx=22, pady=(0, 10))

    def _fluid_changed(self) -> None:
        ing = self.fluid.ingredient
        if not ing.is_empty:
            ing.amount = self.fluid_amount.value()
            self.fluid._draw()
        self.changed()

    def validate(self) -> list[str]:
        errors = self.validate_vein()
        if not self.outputs.ingredients():
            errors.append("Add at least one drilling output")
        return errors

    def serialize(self, event_var: str = "event") -> str:
        if self.validate():
            return ""
        result_literals = [
            item_literal(i, output=True) for i in self.outputs.ingredients()
        ]
        result_literals = [x for x in result_literals if x]
        ticks = self.ticks.get_ticks() or 600
        body = (
            f"{event_var}.recipes.createoreexcavation.drilling(\n"
            f"  {js_array(result_literals)},\n"
            f"  {quote(self.vein_id())},\n"
            f"  {int(ticks)}\n"
            ")"
        )
        body += self.excavating_chains(
            self.drill_var,
            self.stress,
            self.fluid,
            self.fluid_amount,
            self.priority_recipe,
        )
        return self.vein_code(event_var) + "\n\n" + body

    def clear(self) -> None:
        self.clear_vein()
        self.outputs.clear(notify=False)
        self.drill_var.set("Any")
        self.ticks.clear()
        self.stress.set_value(256)
        self.priority_recipe.set_value(0)
        self.fluid.clear(notify=False)
        self.fluid_amount.clear()
        self.changed()

    def main_output(self):
        out = self.outputs.ingredients()
        return out[0] if out else None

    def get_state(self) -> dict:
        return {
            "vein": self.get_vein_state(),
            "outputs": [i.to_dict() for i in self.outputs.ingredients()],
            "drill": self.drill_var.get(),
            "ticks": self.ticks.get_ticks(),
            "stress": int(self.stress.get_value() or 256),
            "recipe_priority": int(self.priority_recipe.get_value() or 0),
            "fluid": self.fluid.ingredient.to_dict(),
            "fluid_amount": self.fluid_amount.value(),
        }

    def set_state(self, state: dict) -> None:
        self.set_vein_state(state.get("vein") or {})
        self.outputs.set_ingredients(ingredients_from_state(state.get("outputs")))
        drill = str(state.get("drill", "Any"))
        self.drill_var.set(drill if drill in DRILL_TIERS else "Any")
        ticks = state.get("ticks")
        self.ticks.set_ticks(int(ticks) if ticks is not None else None)
        self.stress.set_value(int(state.get("stress", 256) or 256))
        self.priority_recipe.set_value(int(state.get("recipe_priority", 0) or 0))
        fluid = ingredient_from_state(state.get("fluid"))
        amount = state.get("fluid_amount")
        if amount is None and fluid.amount is not None:
            amount = fluid.amount
        self.fluid_amount.set_value(int(amount) if amount is not None else 1000)
        if not fluid.is_empty:
            fluid.amount = int(amount) if amount is not None else 1000
        self.fluid.set_ingredient(fluid, notify=False)
        self.changed()


class ItemVeinModule(RecipeModule):
    id = "createoreexcavation.item_vein"
    title = "Item Vein"
    order = 300
    category = "createoreexcavation"
    description = "Ore Excavation item vein + drilling recipe"
    icon = Path(__file__).parent.parent / "create" / "icons" / "crushing_wheel.png"

    def create_editor(self, parent, ctx: EditorContext) -> RecipeEditor:
        return ItemVeinEditor(parent, ctx, self)


MODULE = ItemVeinModule()
