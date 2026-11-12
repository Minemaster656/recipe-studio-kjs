import unittest

from RecipeStudio.services.recipe_import import RecipeImportError, parse_recipe


class RecipeImportTests(unittest.TestCase):
    def test_vanilla_shaped_json(self):
        recipe = parse_recipe(
            """
            {
              "type": "minecraft:crafting_shaped",
              "pattern": ["AA", "AA"],
              "key": {"A": {"item": "minecraft:iron_ingot"}},
              "result": {"id": "minecraft:iron_block"}
            }
            """
        )
        self.assertEqual(recipe.module_id, "vanilla.crafting")
        self.assertFalse(recipe.state["shapeless"])
        self.assertEqual(recipe.state["inputs"][0][0]["id"], "minecraft:iron_ingot")
        self.assertEqual(recipe.state["output"]["id"], "minecraft:iron_block")

    def test_native_kubejs_shaped(self):
        recipe = parse_recipe(
            "event.shaped('2x minecraft:stone', ['A'], {A: 'minecraft:cobblestone'})"
        )
        self.assertEqual(recipe.module_id, "vanilla.crafting")
        self.assertEqual(recipe.state["output"]["count"], 2)

    def test_event_custom_json(self):
        recipe = parse_recipe(
            """
            event.custom({
              type: "create:filling",
              ingredients: [
                {item: "minecraft:glass_bottle"},
                {type: "neoforge:single", fluid: "minecraft:water", amount: 250}
              ],
              results: [{id: "minecraft:potion"}]
            })
            """
        )
        self.assertEqual(recipe.module_id, "create.filling")
        self.assertEqual(recipe.state["item_input"]["id"], "minecraft:glass_bottle")
        self.assertEqual(recipe.state["fluid_input"]["id"], "minecraft:water")
        self.assertEqual(recipe.state["amount"], 250)

    def test_native_create_simple(self):
        recipe = parse_recipe(
            "event.recipes.create.crushing("
            "['2x minecraft:iron_nugget', CreateItem.of('minecraft:iron_ore', 0.25)], "
            "'minecraft:iron_ore').processingTime(250)"
        )
        self.assertEqual(recipe.module_id, "create.crushing")
        self.assertEqual(recipe.state["processing_time"], 250)
        self.assertEqual(recipe.state["outputs"][1]["chance"], 0.25)

    def test_native_sequenced_assembly_extras(self):
        recipe = parse_recipe(
            """
            event.recipes.create.sequenced_assembly(
              ['minecraft:diamond'], 'minecraft:iron_ingot', [
                event.recipes.create.pressing('minecraft:iron_ingot', 'minecraft:iron_ingot'),
                event.recipes.create.deploying('minecraft:iron_ingot', ['minecraft:iron_ingot', 'minecraft:diamond']),
                event.recipes.create.filling('minecraft:iron_ingot', ['minecraft:iron_ingot', Fluid.of('minecraft:water', 250)])
              ]
            ).transitionalItem('minecraft:iron_ingot').loops(2)
            """
        )
        self.assertEqual(recipe.module_id, "create.sequenced_assembly")
        steps = recipe.state["steps"]
        self.assertEqual(steps[1]["item"]["id"], "minecraft:diamond")
        self.assertEqual(steps[2]["fluid"]["id"], "minecraft:water")
        self.assertEqual(steps[2]["fluid"]["amount"], 250)
        self.assertEqual(recipe.state["loops"], 2)

    def test_unsupported_type_is_readable_error(self):
        with self.assertRaises(RecipeImportError) as context:
            parse_recipe('{"type": "minecraft:not_a_recipe"}')
        self.assertIn("Неподдерживаемый", str(context.exception))

    def test_garbage_does_not_crash(self):
        with self.assertRaises(RecipeImportError):
            parse_recipe("this is not a recipe")


if __name__ == "__main__":
    unittest.main()
