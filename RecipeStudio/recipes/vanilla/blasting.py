from RecipeStudio.recipes.base import EditorContext, RecipeEditor
from RecipeStudio.recipes.vanilla.cooking_base import CookingEditor, CookingModule


class BlastingModule(CookingModule):
    id = "vanilla.blasting"
    title = "Blasting"
    order = 30
    method = "blasting"
    default_ticks = 100
    description = "Blast furnace"

    def create_editor(self, parent, ctx: EditorContext) -> RecipeEditor:
        return CookingEditor(parent, ctx, self)


MODULE = BlastingModule()
