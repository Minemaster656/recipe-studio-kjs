from pathlib import Path

from RecipeStudio.recipes.create.common import SimpleProcessModule


class SplashingModule(SimpleProcessModule):
    id = "create.splashing"
    title = "Splashing"
    order = 170
    category = "create"
    recipe_type = "create:splashing"
    group_input = True
    max_inputs = 4
    input_count = True
    description = "Water: item group -> chance results"
    icon = Path(__file__).with_name("icons") / "water_bucket.png"


MODULE = SplashingModule()
