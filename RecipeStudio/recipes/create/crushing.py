from pathlib import Path

from RecipeStudio.recipes.create.common import SimpleProcessModule


class CrushingModule(SimpleProcessModule):
    id = "create.crushing"
    title = "Crushing"
    order = 110
    category = "create"
    recipe_type = "create:crushing"
    default_ticks = 250
    description = "Crushing wheels: one input, chance results"
    icon = Path(__file__).with_name("icons") / "crushing_wheel.png"


MODULE = CrushingModule()
