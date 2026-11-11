"""Shared UI for smelting-like recipes."""

from __future__ import annotations

import customtkinter as ctk

from RecipeStudio.components.number_field import NumberField
from RecipeStudio.components.slot import Slot
from RecipeStudio.components.time_field import TimeField
from RecipeStudio.model.ingredient import Ingredient
from RecipeStudio.recipes.base import EditorContext, RecipeEditor, RecipeModule
from RecipeStudio.services.codegen import format_number, item_literal
from RecipeStudio.theme import COLORS, FONT_UI_SMALL


class CookingEditor(RecipeEditor):
    def __init__(self, master, ctx: EditorContext, module: "CookingModule"):
        super().__init__(master, ctx, module)
        self.module = module
        self.input: Slot
        self.output: Slot
        self.time: TimeField
        self.xp: NumberField
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, padx=28, pady=(30, 18))

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

        options = ctk.CTkFrame(self, fg_color="transparent")
        options.grid(row=1, column=0, padx=28, pady=(0, 24))
        ctk.CTkLabel(
            options,
            text="Time",
            text_color=COLORS["text_muted"],
            font=FONT_UI_SMALL,
        ).grid(row=0, column=0, padx=(0, 8))
        self.time = TimeField(
            options,
            default_ticks=self.module.default_ticks,
            on_change=self.changed,
            width=110,
        )
        self.time.grid(row=0, column=1, padx=(0, 24))
        ctk.CTkLabel(
            options,
            text="XP",
            text_color=COLORS["text_muted"],
            font=FONT_UI_SMALL,
        ).grid(row=0, column=2, padx=(0, 8))
        self.xp = NumberField(
            options,
            width=100,
            min_value=0,
            max_value=100,
            step=0.1,
            allow_float=True,
            allow_empty=True,
            placeholder="default",
            on_change=self.changed,
        )
        self.xp.grid(row=0, column=3)
        ctk.CTkLabel(
            self,
            text="Time: LMB clears · RMB seconds/ticks · double-click to type",
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 9),
        ).grid(row=2, column=0, pady=(0, 18))

    # ------------------------------------------------------------------
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
        text = f"{event_var}.{self.module.method}({out}, {inp})"
        xp = self.xp.get_value()
        if xp is not None:
            text += f".xp({format_number(float(xp))})"
        ticks = self.time.get_ticks()
        if ticks is not None:
            text += f".cookingTime({ticks})"
        return text

    def clear(self) -> None:
        self.input.clear(notify=False)
        self.output.clear(notify=False)
        self.time.clear()
        self.xp.clear()
        self.changed()

    def main_output(self) -> Ingredient | None:
        return self.output.ingredient.copy()

    def get_state(self) -> dict:
        return {
            "input": self.input.ingredient.to_dict(),
            "output": self.output.ingredient.to_dict(),
            "ticks": self.time.get_ticks(),
            "xp": self.xp.get_value(),
        }

    def set_state(self, state: dict) -> None:
        for key, slot in (("input", self.input), ("output", self.output)):
            if key in state:
                slot.set_ingredient(Ingredient.from_dict(state[key]), notify=False)
        self.time.set_ticks(state.get("ticks"))
        self.xp.set_value(state.get("xp"))
        self.changed()


class CookingModule(RecipeModule):
    method = "smelting"
    default_ticks = 200
    description = ""
