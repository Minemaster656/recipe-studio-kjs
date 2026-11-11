from pathlib import Path
import tkinter as tk

import customtkinter as ctk

from RecipeStudio.components.create_widgets import IngredientGroup
from RecipeStudio.components.slot import Slot
from RecipeStudio.recipes.base import EditorContext, RecipeEditor, RecipeModule
from RecipeStudio.recipes.create.common import CreateEditorBase, custom_body
from RecipeStudio.theme import COLORS, FONT_UI_SMALL


class DeployingEditor(CreateEditorBase):
    def __init__(self, master, ctx: EditorContext, module: "DeployingModule"):
        super().__init__(master, ctx, module)
        self.depot: Slot
        self.held: Slot
        self.outputs: IngredientGroup
        self.keep_held = tk.BooleanVar(value=False)
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, padx=24, pady=(26, 8))

        machine = ctk.CTkFrame(top, fg_color="transparent")
        machine.grid(row=0, column=0)
        ctk.CTkLabel(
            machine,
            text="DEPLOYER (held item)",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 9, "bold"),
        ).pack(pady=(0, 4))
        self.held = self.slot(machine, size=54, allow_count=False, allow_tag=True)
        self.held.pack()
        ctk.CTkLabel(
            machine,
            text="↓",
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 18, "bold"),
        ).pack(pady=4)
        ctk.CTkLabel(
            machine,
            text="DEPOT (input)",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 9, "bold"),
        ).pack(pady=(0, 4))
        self.depot = self.slot(machine, size=54, allow_count=True, allow_tag=True)
        self.depot.pack()

        self.arrow(top).grid(row=0, column=1, padx=24)

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

        options = ctk.CTkFrame(self, fg_color="transparent")
        options.grid(row=1, column=0, pady=(6, 18))
        ctk.CTkCheckBox(
            options,
            text="Keep held item",
            variable=self.keep_held,
            command=self.changed,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_2"],
            text_color=COLORS["text"],
            font=FONT_UI_SMALL,
            checkbox_width=18,
            checkbox_height=18,
        ).pack()

    def validate(self) -> list[str]:
        errors = []
        if self.depot.ingredient.is_empty:
            errors.append("Add the depot input item")
        if self.held.ingredient.is_empty:
            errors.append("Add the deployer held item")
        if not self.outputs.ingredients():
            errors.append("Add at least one result")
        return errors

    def serialize(self, event_var: str = "event") -> str:
        if self.validate():
            return ""
        extra = {}
        if self.keep_held.get():
            extra["keep_held_item"] = True
        return custom_body(
            event_var,
            "create:deploying",
            [self.depot.ingredient, self.held.ingredient],
            self.outputs.ingredients(),
            **extra,
        )

    def clear(self) -> None:
        self.depot.clear(notify=False)
        self.held.clear(notify=False)
        self.outputs.clear(notify=False)
        self.keep_held.set(False)
        self.changed()

    def main_output(self):
        out = self.outputs.ingredients()
        return out[0] if out else None


class DeployingModule(RecipeModule):
    id = "create.deploying"
    title = "Deploying"
    order = 130
    category = "create"
    description = "Deployer on a depot, with optional keepHeldItem"
    icon = Path(__file__).with_name("icons") / "deployer.png"

    def create_editor(self, parent, ctx: EditorContext) -> RecipeEditor:
        return DeployingEditor(parent, ctx, self)


MODULE = DeployingModule()
