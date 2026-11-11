from pathlib import Path

from RecipeStudio.recipes.create.common import SimpleProcessModule


class HauntingModule(SimpleProcessModule):
    id = "create.haunting"
    title = "Haunting"
    order = 160
    category = "create"
    recipe_type = "create:haunting"
    group_input = True
    max_inputs = 4
    input_count = True
    description = "Soul campfire: item group -> chance results"
    icon = Path(__file__).with_name("icons") / "soul_campfire.png"


MODULE = HauntingModule()
