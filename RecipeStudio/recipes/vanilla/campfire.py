from pathlib import Path

from RecipeStudio.recipes.base import EditorContext, RecipeEditor
from RecipeStudio.recipes.vanilla.cooking_base import CookingEditor, CookingModule


class CampfireModule(CookingModule):
    id = "vanilla.campfire"
    title = "Campfire Cooking"
    order = 50
    method = "campfireCooking"
    default_ticks = 600
    description = "Campfire cooking"
    icon = Path(__file__).with_name("icons") / "campfire.png"

    def create_editor(self, parent, ctx: EditorContext) -> RecipeEditor:
        return CookingEditor(parent, ctx, self)


MODULE = CampfireModule()
