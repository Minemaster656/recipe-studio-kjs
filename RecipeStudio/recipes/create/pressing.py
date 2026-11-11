from pathlib import Path

from RecipeStudio.recipes.create.common import SimpleProcessModule


class PressingModule(SimpleProcessModule):
    id = "create.pressing"
    title = "Pressing"
    order = 210
    category = "create"
    recipe_type = "create:pressing"
    description = "Mechanical press: one input, chance results"
    icon = Path(__file__).with_name("icons") / "mechanical_press.png"


MODULE = PressingModule()
