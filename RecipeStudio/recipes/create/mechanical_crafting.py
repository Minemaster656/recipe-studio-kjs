from pathlib import Path

import customtkinter as ctk

from RecipeStudio.components.slot import Slot
from RecipeStudio.recipes.base import (
    EditorContext,
    RecipeEditor,
    RecipeModule,
    ingredient_from_state,
)
from RecipeStudio.recipes.create.common import CreateEditorBase
from RecipeStudio.services.codegen import item_literal
from RecipeStudio.theme import COLORS, FONT_UI_SMALL


class MechanicalCraftingEditor(CreateEditorBase):
    MAX = 9

    def __init__(self, master, ctx: EditorContext, module: "MechanicalCraftingModule"):
        super().__init__(master, ctx, module)
        self.rows = 1
        self.cols = 1
        self.slots: list[list[Slot]] = []
        self.output: Slot
        self.size_label: ctk.CTkLabel
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, padx=22, pady=(16, 4))

        controls = ctk.CTkFrame(top, fg_color="transparent")
        controls.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        ctk.CTkLabel(
            controls,
            text="GRID",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 9, "bold"),
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            controls, text="−", width=28, height=26, command=lambda: self._resize(0, -1)
        ).pack(side="left")
        self.size_label = ctk.CTkLabel(
            controls,
            text="1 × 1",
            width=52,
            text_color=COLORS["text"],
            font=FONT_UI_SMALL,
        )
        self.size_label.pack(side="left", padx=4)
        ctk.CTkButton(
            controls, text="+", width=28, height=26, command=lambda: self._resize(0, 1)
        ).pack(side="left")
        ctk.CTkButton(
            controls, text="−", width=28, height=26, command=lambda: self._resize(-1, 0)
        ).pack(side="left", padx=(12, 0))
        ctk.CTkButton(
            controls, text="+", width=28, height=26, command=lambda: self._resize(1, 0)
        ).pack(side="left", padx=(2, 0))
        ctk.CTkLabel(
            controls,
            text="rows / columns",
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 9),
        ).pack(side="left", padx=(6, 0))

        self.grid_frame = ctk.CTkFrame(top, fg_color="transparent")
        self.grid_frame.grid(row=1, column=0, padx=(0, 24))
        for r in range(self.MAX):
            row: list[Slot] = []
            for c in range(self.MAX):
                slot = self.slot(
                    self.grid_frame,
                    size=38,
                    allow_count=True,
                    max_count=64,
                    allow_tag=True,
                )
                slot.grid(row=r, column=c, padx=2, pady=2)
                row.append(slot)
            self.slots.append(row)

        right = ctk.CTkFrame(top, fg_color="transparent")
        right.grid(row=1, column=1)
        ctk.CTkLabel(
            right,
            text="OUTPUT",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 9, "bold"),
        ).pack(pady=(0, 4))
        self.output = self.slot(right, size=58, allow_count=True, max_count=64)
        self.output.pack()

        ctk.CTkLabel(
            self,
            text="Pattern is trimmed automatically. Empty cells become spaces.",
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 9),
        ).grid(row=1, column=0, pady=(4, 12))
        self._apply_size()

    def _resize(self, d_rows: int, d_cols: int) -> None:
        old_rows, old_cols = self.rows, self.cols
        if d_rows:
            self.rows = min(self.MAX, max(1, self.rows + d_rows))
        if d_cols:
            self.cols = min(self.MAX, max(1, self.cols + d_cols))
        for r in range(self.MAX):
            for c in range(self.MAX):
                if r >= self.rows or c >= self.cols:
                    if r < old_rows and c < old_cols:
                        self.slots[r][c].clear(notify=False)
        self._apply_size()

    def _apply_size(self) -> None:
        for r in range(self.MAX):
            for c in range(self.MAX):
                slot = self.slots[r][c]
                if r < self.rows and c < self.cols:
                    slot.grid()
                else:
                    slot.grid_remove()
        self.size_label.configure(text=f"{self.rows} × {self.cols}")
        self.changed()

    def validate(self) -> list[str]:
        errors = []
        if self.output.ingredient.is_empty:
            errors.append("Add an output item")
        if not any(
            not self.slots[r][c].ingredient.is_empty
            for r in range(self.rows)
            for c in range(self.cols)
        ):
            errors.append("Add at least one ingredient")
        return errors

    def _trimmed(self):
        occupied = [
            (r, c)
            for r in range(self.rows)
            for c in range(self.cols)
            if not self.slots[r][c].ingredient.is_empty
        ]
        if not occupied:
            return None, None
        min_r = min(r for r, _ in occupied)
        max_r = max(r for r, _ in occupied)
        min_c = min(c for _, c in occupied)
        max_c = max(c for _, c in occupied)
        keys: dict[str, str] = {}
        by_literal: dict[str, str] = {}
        rows: list[str] = []
        for r in range(min_r, max_r + 1):
            chars = []
            for c in range(min_c, max_c + 1):
                ing = self.slots[r][c].ingredient
                if ing.is_empty:
                    chars.append(" ")
                    continue
                literal = item_literal(ing)
                if literal not in by_literal:
                    letter = chr(ord("A") + len(by_literal))
                    if len(by_literal) >= 26:
                        raise ValueError("Too many distinct ingredients (max 26)")
                    by_literal[literal] = letter
                    keys[letter] = literal
                chars.append(by_literal[literal])
            rows.append("".join(chars))
        return rows, keys

    def serialize(self, event_var: str = "event") -> str:
        if self.validate():
            return ""
        rows, keys = self._trimmed()
        if not rows:
            return ""
        out = item_literal(self.output.ingredient, output=True)
        pattern = ",\n".join(f"    '{row}'" for row in rows)
        key_lines = ",\n".join(f"    {k}: {v}" for k, v in keys.items())
        return (
            f"{event_var}.recipes.create.mechanical_crafting({out}, [\n"
            f"{pattern}\n"
            f"  ], {{\n"
            f"{key_lines}\n"
            f"  }})"
        )

    def clear(self) -> None:
        for row in self.slots:
            for slot in row:
                slot.clear(notify=False)
        self.output.clear(notify=False)
        self.rows = 1
        self.cols = 1
        self._apply_size()
        self.changed()

    def main_output(self):
        return (
            self.output.ingredient.copy()
            if not self.output.ingredient.is_empty
            else None
        )

    def get_state(self) -> dict:
        return {
            "rows": self.rows,
            "cols": self.cols,
            "grid": [
                [self.slots[r][c].ingredient.to_dict() for c in range(self.cols)]
                for r in range(self.rows)
            ],
            "output": self.output.ingredient.to_dict(),
        }

    def set_state(self, state: dict) -> None:
        for row in self.slots:
            for slot in row:
                slot.clear(notify=False)
        grid = state.get("grid") or []
        rows = state.get("rows") or len(grid) or 1
        cols = state.get("cols") or max((len(row) for row in grid), default=1)
        self.rows = max(1, min(self.MAX, int(rows)))
        self.cols = max(1, min(self.MAX, int(cols)))
        for r, row in enumerate(grid[: self.rows]):
            for c, value in enumerate(row[: self.cols]):
                if value:
                    self.slots[r][c].set_ingredient(
                        ingredient_from_state(value), notify=False
                    )
        self.output.set_ingredient(
            ingredient_from_state(state.get("output")), notify=False
        )
        self._apply_size()


class MechanicalCraftingModule(RecipeModule):
    id = "create.mechanical_crafting"
    title = "Mechanical Crafting"
    order = 230
    category = "create"
    description = "Mechanical crafter: free-form grid up to 9×9"
    icon = Path(__file__).with_name("icons") / "mechanical_crafter.png"

    def create_editor(self, parent, ctx: EditorContext) -> RecipeEditor:
        return MechanicalCraftingEditor(parent, ctx, self)


MODULE = MechanicalCraftingModule()
