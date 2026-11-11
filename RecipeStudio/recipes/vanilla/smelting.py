from pathlib import Path

from RecipeStudio.recipes.base import EditorContext, RecipeEditor
from RecipeStudio.recipes.vanilla.cooking_base import CookingEditor, CookingModule


class SmeltingModule(CookingModule):
    id = "vanilla.smelting"
    title = "Smelting"
    order = 20
    method = "smelting"
    default_ticks = 200
    description = "Furnace smelting"
    icon = Path(__file__).with_name("icons") / "furnace.png"

    def create_editor(self, parent, ctx: EditorContext) -> RecipeEditor:
        return CookingEditor(parent, ctx, self)


MODULE = SmeltingModule()
