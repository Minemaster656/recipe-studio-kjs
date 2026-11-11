from RecipeStudio.recipes.base import EditorContext, RecipeEditor
from RecipeStudio.recipes.vanilla.cooking_base import CookingEditor, CookingModule


class SmokingModule(CookingModule):
    id = "vanilla.smoking"
    title = "Smoking"
    order = 40
    method = "smoking"
    default_ticks = 100
    description = "Smoker"

    def create_editor(self, parent, ctx: EditorContext) -> RecipeEditor:
        return CookingEditor(parent, ctx, self)


MODULE = SmokingModule()
