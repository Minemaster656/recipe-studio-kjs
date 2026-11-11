from pathlib import Path

from RecipeStudio.recipes.create.common import SimpleProcessModule


class CuttingModule(SimpleProcessModule):
    id = "create.cutting"
    title = "Cutting"
    order = 120
    category = "create"
    recipe_type = "create:cutting"
    default_ticks = 50
    description = "Mechanical saw: one input, chance results"
    icon = Path(__file__).with_name("icons") / "mechanical_saw.png"


MODULE = CuttingModule()
