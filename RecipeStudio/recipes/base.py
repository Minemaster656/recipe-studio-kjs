"""Contracts every recipe module implements."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import customtkinter as ctk

from RecipeStudio.components.slot import Slot
from RecipeStudio.model.ingredient import Ingredient


@dataclass
class EditorContext:
    app: Any
    catalog: Any
    names: Any
    icons: Any
    config: Any

    def changed(self, editor=None) -> None:
        self.app.on_editor_changed(editor)

    def slot(self, master, **kwargs) -> Slot:
        return Slot(master, self.app, on_change=lambda: self.changed(None), **kwargs)


class RecipeEditor(ctk.CTkFrame):
    def __init__(self, master, ctx: EditorContext, module: "RecipeModule"):
        super().__init__(master, fg_color="transparent")
        self.ctx = ctx
        self.module = module

    # ------------------------------------------------------------------
    def serialize(self, event_var: str = "event") -> str:
        raise NotImplementedError

    def validate(self) -> list[str]:
        return []

    def clear(self) -> None:
        raise NotImplementedError

    def get_state(self) -> dict:
        return {}

    def set_state(self, state: dict) -> None:
        pass

    def main_output(self) -> Ingredient | None:
        return None

    # ------------------------------------------------------------------
    def changed(self) -> None:
        self.ctx.changed(self)


class RecipeModule:
    id: str = ""
    title: str = ""
    order: int = 100
    category: str = "vanilla"
    description: str = ""
    # Each handler ships its own small icon next to its code; do not depend on
    # the shared item catalogue for these.
    icon: Path | None = None

    def create_editor(self, parent, ctx: EditorContext) -> RecipeEditor:
        raise NotImplementedError
