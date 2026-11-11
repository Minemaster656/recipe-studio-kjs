# Recipe Studio

A small desktop editor for building KubeJS recipes (Minecraft 1.21.1, KubeJS 2101).

## Run

```bash
cd /home/minemaster/.local/share/PrismLauncher/instances/Kindur-II-DEV-III/minecraft/scripts
uv run python -m RecipeStudio
```

`uv run` installs the declared dependencies (including Pillow) automatically.
If the environment is already prepared, `uv sync` then `uv run …` works too.

## Hotkeys

| Key | Action |
| --- | --- |
| `Ctrl+F` | Focus search; press again to return to the item grid |
| `Ctrl+Shift+F` | Cycle search mode `S` → `F` → `E` |
| `Ctrl+Backspace` | Delete the previous word in the search field |
| `Ctrl+Delete` | Delete the next word in the search field |
| `Ctrl+E` | Copy the recipe |
| `Ctrl+Shift+E` | Copy the recipe with the original-recipe removal line |
| `Ctrl+A` | Show only favourites (when text input is not focused) |
| `A` | Toggle favourite on the hovered grid item |
| `+` / `-` | Change the count of the hovered slot |
| `Esc` | Leave search / clear selection / exit favourites |

The `★` button next to the palette counter toggles favourites-only mode as
well, so it can always be switched off without using the keyboard.

Search modes: `S` substring, `F` fuzzy, `E` embeddings (text or an image path).
`S` and `F` fall back to the local catalogue if the vector DB is unavailable.

Fluid slots accept NeoForge bucket items from the palette (for example
`minecraft:water_bucket`) and store/export the fluid id without the suffix
(`minecraft:water`). The vector DB indexes buckets rather than fluid ids.

## Adding a recipe type

Create a file under `RecipeStudio/recipes/` (for example `recipes/create/pressing.py`):

```python
from RecipeStudio.recipes.base import RecipeEditor, RecipeModule


class PressingEditor(RecipeEditor):
    def serialize(self, event_var="event"):
        return f"{event_var}.custom({{ type: 'create:pressing', ingredients: [...], results: [...] }})"


class PressingModule(RecipeModule):
    id = "create.pressing"
    title = "Pressing"
    order = 200
    description = "Create mechanical press"

    def create_editor(self, parent, ctx):
        return PressingEditor(parent, ctx, self)


MODULE = PressingModule()
```

It is discovered automatically. Disable a module by adding its id to
`RecipeStudio/config.json` → `disabled_modules`.

Tab icons are owned by the handler, not by the shared item catalogue. Put a
small PNG next to the module and point to it from the class:

```python
from pathlib import Path

icon = Path(__file__).with_name("icons") / "pressing.png"
```

The vanilla handlers use files in `recipes/vanilla/icons/`.

## Included modules

Vanilla: Crafting (shaped/shapeless), Smelting, Blasting, Smoking, Campfire
Cooking, Stonecutting, Smithing.

Create: Compacting, Milling, Crushing, Cutting, Deploying, Emptying, Filling,
Haunting, Splashing, Mixing, Pressing, Sandpaper Polishing, Mechanical
Crafting (up to 9×9), Sequenced Assembly.

## Layout

- `app.py` — window, hotkeys, wiring
- `components/` — slot, item grid, search bar, time/number fields, export panel
- `services/` — catalogue, icons, names, favourites, code generation, search gateway
- `recipes/` — recipe modules (`vanilla/` first)
- `data/` — cached favourites and display names (created on demand)

`services/search.py` is the only place that imports `emb_api` or opens
`embeddings.db`, so the editor can be moved to another project by changing
only `config.json`.
