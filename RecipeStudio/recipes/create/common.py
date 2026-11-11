"""Shared code generation and layouts for Create recipe modules."""

from __future__ import annotations

import json
from pathlib import Path

import customtkinter as ctk

from RecipeStudio.components.create_widgets import IngredientGroup
from RecipeStudio.components.slot import Slot
from RecipeStudio.components.time_field import TimeField
from RecipeStudio.model.ingredient import Ingredient, normalize_fluid_id
from RecipeStudio.recipes.base import EditorContext, RecipeEditor, RecipeModule
from RecipeStudio.theme import COLORS, FONT_UI_SMALL


def ingredient_json(ing: Ingredient) -> dict:
    if ing.kind == "tag":
        data = {"tag": ing.id.lstrip("#")}
        if ing.count > 1:
            data["count"] = int(ing.count)
        return data
    if ing.kind == "fluid":
        return {
            "type": "neoforge:single",
            "fluid": normalize_fluid_id(ing.id),
            "amount": int(ing.amount or 1000),
        }
    data = {"item": ing.id}
    if ing.count > 1:
        data["count"] = int(ing.count)
    return data


def result_json(ing: Ingredient) -> dict:
    if ing.kind == "fluid":
        return {"id": normalize_fluid_id(ing.id), "amount": int(ing.amount or 1000)}
    data = {"id": ing.id}
    if ing.count > 1:
        data["count"] = int(ing.count)
    if ing.chance is not None:
        data["chance"] = round(float(ing.chance), 3)
    return data


def custom_body(
    event_var: str,
    recipe_type: str,
    ingredients: list[Ingredient],
    results: list[Ingredient],
    **extra,
) -> str:
    recipe: dict = {
        "ingredients": [ingredient_json(i) for i in ingredients],
        "results": [result_json(i) for i in results],
    }
    recipe.update(extra)
    recipe["type"] = recipe_type
    return f"{event_var}.custom({json.dumps(recipe, indent=2, ensure_ascii=False)})"


class CreateEditorBase(RecipeEditor):
    def __init__(self, master, ctx: EditorContext, module: RecipeModule):
        super().__init__(master, ctx, module)
        self.grid_columnconfigure(0, weight=1)

    def title(self, text: str):
        return ctk.CTkLabel(
            self,
            text=text,
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 9, "bold"),
        )

    def hint(self, text: str):
        return ctk.CTkLabel(
            self,
            text=text,
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 9),
        )

    def slot(self, master, **kwargs) -> Slot:
        kwargs.setdefault("on_change", self.changed)
        return Slot(master, self.ctx.app, **kwargs)

    def body(self, **extra) -> str:
        raise NotImplementedError

    @staticmethod
    def arrow(master):
        return ctk.CTkLabel(
            master,
            text="→",
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 24, "bold"),
        )


class SimpleProcessEditor(CreateEditorBase):
    """Single-input or group-input recipe with chance outputs."""

    def __init__(
        self,
        master,
        ctx: EditorContext,
        module: "SimpleProcessModule",
    ):
        super().__init__(master, ctx, module)
        self.module = module
        self.inputs: list[Slot] = []
        self.input_group: IngredientGroup | None = None
        self.output_group: IngredientGroup
        self.time: TimeField | None = None
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, padx=22, pady=(22, 8))

        in_frame = ctk.CTkFrame(top, fg_color="transparent")
        in_frame.grid(row=0, column=0)
        ctk.CTkLabel(
            in_frame,
            text="INPUT" if not self.module.group_input else "INPUTS",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 9, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        if self.module.group_input:
            self.input_group = IngredientGroup(
                in_frame,
                self.ctx.app,
                max_items=self.module.max_inputs,
                slot_size=44,
                allow_count=self.module.input_count,
                on_change=self.changed,
            )
            self.input_group.pack(anchor="w")
        else:
            slot = self.slot(
                in_frame,
                size=58,
                allow_count=self.module.input_count,
                max_count=64,
                allow_tag=True,
            )
            slot.pack()
            self.inputs.append(slot)

        self.arrow(top).grid(row=0, column=1, padx=20)

        out_frame = ctk.CTkFrame(top, fg_color="transparent")
        out_frame.grid(row=0, column=2)
        ctk.CTkLabel(
            out_frame,
            text="RESULTS (chance)",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 9, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        self.output_group = IngredientGroup(
            out_frame,
            self.ctx.app,
            max_items=6,
            slot_size=46,
            allow_chance=True,
            allow_count=True,
            on_change=self.changed,
        )
        self.output_group.pack(anchor="w")

        options = ctk.CTkFrame(self, fg_color="transparent")
        options.grid(row=1, column=0, pady=(4, 16))
        if self.module.default_ticks is not None:
            ctk.CTkLabel(
                options,
                text="Processing time",
                text_color=COLORS["text_muted"],
                font=FONT_UI_SMALL,
            ).pack(side="left", padx=(0, 8))
            self.time = TimeField(
                options,
                default_ticks=self.module.default_ticks,
                on_change=self.changed,
                width=110,
            )
            self.time.pack(side="left")
        self.hint("Chance: Alt+wheel. Count: wheel. RMB a slot for exact values.").grid(
            row=2, column=0, pady=(0, 14)
        )

    def _ingredients(self) -> list[Ingredient]:
        if self.input_group is not None:
            return self.input_group.ingredients()
        return [s.ingredient.copy() for s in self.inputs if not s.is_empty]

    def _results(self) -> list[Ingredient]:
        return self.output_group.ingredients()

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self._ingredients():
            errors.append("Add at least one input")
        if not self._results():
            errors.append("Add at least one result")
        return errors

    def serialize(self, event_var: str = "event") -> str:
        if self.validate():
            return ""
        extra = {}
        if self.time is not None and self.time.get_ticks() is not None:
            extra["processing_time"] = int(self.time.get_ticks())
        return custom_body(
            event_var,
            self.module.recipe_type,
            self._ingredients(),
            self._results(),
            **extra,
        )

    def clear(self) -> None:
        if self.input_group is not None:
            self.input_group.clear(notify=False)
        for slot in self.inputs:
            slot.clear(notify=False)
        self.output_group.clear(notify=False)
        if self.time is not None:
            self.time.clear()
        self.changed()

    def main_output(self) -> Ingredient | None:
        results = self._results()
        return results[0] if results else None


class SimpleProcessModule(RecipeModule):
    recipe_type = "create:crushing"
    group_input = False
    max_inputs = 1
    input_count = False
    default_ticks = None
    create_class = SimpleProcessEditor

    def create_editor(self, parent, ctx: EditorContext) -> RecipeEditor:
        return self.create_class(parent, ctx, self)


__all__ = [
    "CreateEditorBase",
    "SimpleProcessEditor",
    "SimpleProcessModule",
    "custom_body",
    "ingredient_json",
    "result_json",
]
