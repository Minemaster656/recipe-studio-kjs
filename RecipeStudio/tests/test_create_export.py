import json
import unittest
from types import SimpleNamespace

from RecipeStudio.model.ingredient import Ingredient
from RecipeStudio.recipes.create.common import (
    CreateEditorBase,
    custom_body,
    ingredient_json,
    result_json,
)


def item(item_id: str, count: int = 1) -> Ingredient:
    return Ingredient(kind="item", id=item_id, count=count)


class CustomBodyTests(unittest.TestCase):
    def test_crushing_shape(self):
        body = custom_body(
            "event",
            "create:crushing",
            [item("minecraft:iron_ore")],
            [item("create:crushed_raw_iron"), item("create:experience_nugget")],
            processing_time=250,
        )
        self.assertTrue(body.startswith("event.custom("))
        payload = json.loads(body[len("event.custom(") : -1])
        self.assertEqual(payload["type"], "create:crushing")
        self.assertEqual(payload["processing_time"], 250)
        self.assertEqual(
            payload["ingredients"], [{"item": "minecraft:iron_ore"}]
        )
        self.assertEqual(
            payload["results"],
            [{"id": "create:crushed_raw_iron"}, {"id": "create:experience_nugget"}],
        )

    def test_fluid_ingredient_shape(self):
        fluid = Ingredient(
            kind="fluid", id="minecraft:water", count=1, amount=250
        )
        self.assertEqual(
            ingredient_json(fluid),
            {"type": "neoforge:single", "fluid": "minecraft:water", "amount": 250},
        )

    def test_result_chance(self):
        result = result_json(Ingredient(kind="item", id="create:zinc_nugget", chance=0.5))
        self.assertEqual(result, {"id": "create:zinc_nugget", "chance": 0.5})


class ExportModeTests(unittest.TestCase):
    def _editor(self, mode: str):
        editor = CreateEditorBase.__new__(CreateEditorBase)
        editor.ctx = SimpleNamespace(
            app=SimpleNamespace(create_export_mode=mode)
        )
        return editor

    def test_addon_by_default(self):
        editor = CreateEditorBase.__new__(CreateEditorBase)
        editor.ctx = SimpleNamespace(app=SimpleNamespace())
        self.assertFalse(editor.use_custom())

    def test_custom_mode(self):
        self.assertTrue(self._editor("custom").use_custom())
        self.assertFalse(self._editor("addon").use_custom())


if __name__ == "__main__":
    unittest.main()