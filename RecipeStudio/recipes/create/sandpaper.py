from pathlib import Path

from RecipeStudio.recipes.create.common import SimpleProcessModule


class SandpaperModule(SimpleProcessModule):
    id = "create.sandpaper"
    title = "Sandpaper"
    order = 220
    category = "create"
    recipe_type = "create:sandpaper_polishing"
    description = "Sandpaper polishing: one input, chance result"
    icon = Path(__file__).with_name("icons") / "sand_paper.png"


MODULE = SandpaperModule()
