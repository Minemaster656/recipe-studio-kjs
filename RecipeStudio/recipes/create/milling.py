from pathlib import Path

from RecipeStudio.recipes.create.common import SimpleProcessModule


class MillingModule(SimpleProcessModule):
    id = "create.milling"
    title = "Milling"
    order = 105
    category = "create"
    recipe_type = "create:milling"
    default_ticks = 100
    description = "Millstone: one input, chance results"
    icon = Path(__file__).with_name("icons") / "millstone.png"


MODULE = MillingModule()
