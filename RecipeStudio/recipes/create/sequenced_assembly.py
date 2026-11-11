from __future__ import annotations

import json
from pathlib import Path

import customtkinter as ctk

from RecipeStudio.components.create_widgets import FluidAmountField, IngredientGroup
from RecipeStudio.components.number_field import NumberField
from RecipeStudio.components.slot import Slot
from RecipeStudio.model.ingredient import Ingredient
from RecipeStudio.recipes.base import EditorContext, RecipeEditor, RecipeModule
from RecipeStudio.recipes.create.common import (
    CreateEditorBase,
    ingredient_json,
    result_json,
)
from RecipeStudio.services.codegen import item_literal
from RecipeStudio.theme import COLORS, FONT_UI_SMALL

STEP_TYPES = {
    "Pressing": "create:pressing",
    "Cutting": "create:cutting",
    "Deploying": "create:deploying",
    "Filling": "create:filling",
}


class SequenceStep(ctk.CTkFrame):
    def __init__(self, master, app, editor: "SequencedAssemblyEditor", on_remove):
        super().__init__(master, fg_color=COLORS["panel_alt"], corner_radius=8)
        self.app = app
        self.editor = editor
        self.on_remove = on_remove
        self.type_var = ctk.StringVar(value="Pressing")
        self.item_extra: Slot
        self.fluid_extra: Slot
        self.amount: FluidAmountField
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(3, weight=1)
        self.menu = ctk.CTkOptionMenu(
            self,
            values=list(STEP_TYPES),
            variable=self.type_var,
            command=lambda _v: self._refresh(),
            width=118,
            height=28,
            fg_color=COLORS["panel_hover"],
            button_color=COLORS["slot_border"],
            button_hover_color=COLORS["slot_hover"],
            text_color=COLORS["text"],
            font=FONT_UI_SMALL,
        )
        self.menu.grid(row=0, column=0, padx=(8, 6), pady=8)

        self.item_extra = Slot(
            self,
            self.app,
            size=34,
            allow_count=False,
            allow_tag=True,
            on_change=self.editor.changed,
        )
        self.item_extra.grid(row=0, column=1, padx=4, pady=6)
        self.fluid_extra = Slot(
            self,
            self.app,
            size=34,
            allow_count=False,
            allow_tag=False,
            allow_fluid=True,
            on_change=self._fluid_changed,
        )
        self.fluid_extra.grid(row=0, column=1, padx=4, pady=6)
        self.amount = FluidAmountField(
            self, value=1000, on_change=self._fluid_changed, width=132
        )
        self.amount.grid(row=0, column=2, padx=4, pady=6)

        self.hint = ctk.CTkLabel(
            self,
            text="",
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 9),
            anchor="w",
        )
        self.hint.grid(row=0, column=3, sticky="w", padx=6)

        ctk.CTkButton(
            self,
            text="×",
            width=28,
            height=26,
            fg_color=COLORS["panel_hover"],
            hover_color=COLORS["red"],
            text_color=COLORS["text"],
            command=self.on_remove,
        ).grid(row=0, column=4, padx=(4, 8))
        self._refresh()

    def _fluid_changed(self) -> None:
        fluid = self.fluid_extra.ingredient
        if not fluid.is_empty:
            fluid.amount = self.amount.value()
            self.fluid_extra._draw()
        self.editor.changed()

    def _refresh(self) -> None:
        kind = self.type_var.get()
        if kind == "Deploying":
            self.item_extra.grid()
            self.fluid_extra.grid_remove()
            self.amount.grid_remove()
            self.hint.configure(text="Held item by the deployer")
        elif kind == "Filling":
            self.item_extra.grid_remove()
            self.fluid_extra.grid()
            self.amount.grid()
            self.hint.configure(text="Fluid added by the spout")
        else:
            self.item_extra.grid_remove()
            self.fluid_extra.grid_remove()
            self.amount.grid_remove()
            self.hint.configure(text="No extra ingredient")
        self.editor.changed()

    def validate(self) -> list[str]:
        kind = self.type_var.get()
        if kind == "Deploying" and self.item_extra.ingredient.is_empty:
            return ["Deploying step needs a held item"]
        if kind == "Filling" and self.fluid_extra.ingredient.is_empty:
            return ["Filling step needs a fluid"]
        return []

    def serialize(self, transitional: Ingredient) -> dict:
        base = transitional.copy()
        base.count = 1
        recipe: dict = {"type": STEP_TYPES[self.type_var.get()]}
        if self.type_var.get() == "Deploying":
            recipe["ingredients"] = [
                ingredient_json(base),
                ingredient_json(self.item_extra.ingredient),
            ]
        elif self.type_var.get() == "Filling":
            fluid = self.fluid_extra.ingredient.copy()
            fluid.amount = self.amount.value()
            recipe["ingredients"] = [ingredient_json(base), ingredient_json(fluid)]
        else:
            recipe["ingredients"] = [ingredient_json(base)]
        recipe["results"] = [result_json(base)]
        return recipe

    def clear(self) -> None:
        self.item_extra.clear(notify=False)
        self.fluid_extra.clear(notify=False)
        self.amount.clear()


class SequencedAssemblyEditor(CreateEditorBase):
    def __init__(self, master, ctx: EditorContext, module: "SequencedAssemblyModule"):
        super().__init__(master, ctx, module)
        self.start: Slot
        self.transitional: Slot
        self.steps: list[SequenceStep] = []
        self.steps_container: ctk.CTkFrame
        self.loops: NumberField
        self.results: IngredientGroup
        self.scrap: IngredientGroup
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="nw", padx=22, pady=(18, 6))

        left = ctk.CTkFrame(top, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nw")
        ctk.CTkLabel(
            left,
            text="STARTING ITEM",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 9, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        self.start = self.slot(left, size=50, allow_count=False, allow_tag=True)
        self.start.pack(anchor="w", pady=(0, 10))
        ctk.CTkLabel(
            left,
            text="TRANSITIONAL ITEM",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 9, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        self.transitional = self.slot(left, size=50, allow_count=False, allow_tag=False)
        self.transitional.pack(anchor="w")

        self.arrow(top).grid(row=0, column=1, padx=16, pady=30)

        middle = ctk.CTkFrame(top, fg_color="transparent")
        middle.grid(row=0, column=2, sticky="nsew")
        row = ctk.CTkFrame(middle, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkLabel(
            row,
            text="SEQUENCE",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 9, "bold"),
        ).pack(side="left")
        ctk.CTkButton(
            row,
            text="+ Add step",
            width=84,
            height=24,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_2"],
            text_color=COLORS["panel"],
            command=self.add_step,
        ).pack(side="right")
        self.steps_container = ctk.CTkFrame(middle, fg_color="transparent")
        self.steps_container.pack(fill="both", expand=True, pady=(4, 0))

        right = ctk.CTkFrame(top, fg_color="transparent")
        right.grid(row=0, column=3, sticky="nw", padx=(18, 0))
        ctk.CTkLabel(
            right,
            text="RESULTS",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 9, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        self.results = IngredientGroup(
            right,
            self.ctx.app,
            max_items=4,
            slot_size=42,
            allow_chance=True,
            allow_count=True,
            on_change=self.changed,
        )
        self.results.pack(anchor="w", pady=(0, 8))
        ctk.CTkLabel(
            right,
            text="SCRAP (chance)",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 9, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        self.scrap = IngredientGroup(
            right,
            self.ctx.app,
            max_items=4,
            slot_size=40,
            allow_chance=True,
            allow_count=False,
            on_change=self.changed,
        )
        self.scrap.pack(anchor="w", pady=(0, 8))
        loops_row = ctk.CTkFrame(right, fg_color="transparent")
        loops_row.pack(anchor="w")
        ctk.CTkLabel(
            loops_row,
            text="Loops",
            text_color=COLORS["text_muted"],
            font=FONT_UI_SMALL,
        ).pack(side="left", padx=(0, 6))
        self.loops = NumberField(
            loops_row,
            min_value=1,
            max_value=100,
            width=76,
            on_change=self.changed,
        )
        self.loops.set_value(1)
        self.loops.pack(side="left")

        self.add_step(notify=False)

    def add_step(self, notify: bool = True) -> None:
        step = SequenceStep(self.steps_container, self.ctx.app, self, on_remove=None)
        step.pack(fill="x", pady=2)
        step.on_remove = lambda s=step: self.remove_step(s)
        self.steps.append(step)
        if notify:
            self.changed()

    def remove_step(self, step: SequenceStep) -> None:
        if step in self.steps:
            self.steps.remove(step)
            step.destroy()
            self.changed()

    def _inputs(self) -> tuple[Ingredient, Ingredient] | None:
        if self.start.ingredient.is_empty or self.transitional.ingredient.is_empty:
            return None
        return self.start.ingredient, self.transitional.ingredient

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.start.ingredient.is_empty:
            errors.append("Add a starting item")
        if self.transitional.ingredient.is_empty:
            errors.append("Add a transitional item")
        if not self.steps:
            errors.append("Add at least one sequence step")
        for idx, step in enumerate(self.steps, start=1):
            for msg in step.validate():
                errors.append(f"Step {idx}: {msg}")
        if not self.results.ingredients() and not self.scrap.ingredients():
            errors.append("Add at least one result")
        return errors

    def serialize(self, event_var: str = "event") -> str:
        if self.validate():
            return ""
        start, transitional = self._inputs()  # type: ignore[misc]
        results = [i.copy() for i in self.results.ingredients()]
        results += [i.copy() for i in self.scrap.ingredients()]
        recipe = {
            "type": "create:sequenced_assembly",
            "ingredient": ingredient_json(start),
            "transitional_item": {"id": transitional.id},
            "sequence": [step.serialize(transitional) for step in self.steps],
            "results": [result_json(i) for i in results],
            "loops": int(self.loops.get_value() or 1),
        }
        return f"{event_var}.custom({json.dumps(recipe, indent=2, ensure_ascii=False)})"

    def clear(self) -> None:
        self.start.clear(notify=False)
        self.transitional.clear(notify=False)
        for step in list(self.steps):
            step.destroy()
        self.steps.clear()
        self.results.clear(notify=False)
        self.scrap.clear(notify=False)
        self.loops.set_value(1)
        self.add_step(notify=False)
        self.changed()

    def main_output(self):
        out = self.results.ingredients()
        return out[0] if out else None


class SequencedAssemblyModule(RecipeModule):
    id = "create.sequenced_assembly"
    title = "Sequenced Assembly"
    order = 240
    category = "create"
    description = "Belt sequence: step recipes, loops, results and scrap"
    icon = Path(__file__).with_name("icons") / "belt_connector.png"

    def create_editor(self, parent, ctx: EditorContext) -> RecipeEditor:
        return SequencedAssemblyEditor(parent, ctx, self)


MODULE = SequencedAssemblyModule()
