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

    def test_native_create_item_with_count_and_chance(self):
        recipe = parse_recipe(
            "event.recipes.create.crushing("
            "[CreateItem.of(Item.of('minecraft:iron_ore', 3), 0.25)], "
            "'minecraft:stone')"
        )
        output = recipe.state["outputs"][0]
        self.assertEqual(output["id"], "minecraft:iron_ore")
        self.assertEqual(output["count"], 3)
        self.assertEqual(output["chance"], 0.25)

    def test_native_ore_excavation_merges_vein(self):
        recipe = parse_recipe(
            """
            event.recipes.createoreexcavation.vein('Iron Vein', 'minecraft:iron_ore')
              .id('kubejs:ore_vein_type/iron')
              .veinSize(10, 30)
              .placement(64, 8, 7)
              .defaultFinite()
              .biomeWhitelist('minecraft:is_overworld')
            event.recipes.createoreexcavation.drilling(
              [CreateItem.of('minecraft:iron_nugget', 0.5)],
              'kubejs:ore_vein_type/iron',
              600
            ).drill('createoreexcavation:diamond_drill').stress(512)
            """
        )
        self.assertEqual(recipe.module_id, "createoreexcavation.item_vein")
        self.assertEqual(recipe.type_id, "createoreexcavation:drilling")
        self.assertEqual(recipe.state["vein"]["name"], "Iron Vein")
        self.assertEqual(recipe.state["vein"]["vein_id"], "kubejs:ore_vein_type/iron")
        self.assertEqual(recipe.state["vein"]["salt"], 7)
        self.assertEqual(recipe.state["drill"], "Diamond")
        self.assertEqual(recipe.state["stress"], 512)
        self.assertEqual(recipe.state["outputs"][0]["chance"], 0.5)

    def test_json_ore_excavation_drilling(self):
        recipe = parse_recipe(
            """
            {
              "type": "createoreexcavation:drilling",
              "output": [{"id": "minecraft:gold_nugget", "chance": 0.8}],
              "veinId": "createoreexcavation:ore_vein_type/gold",
              "ticks": 400,
              "fluid": {"amount": 1000, "ingredient": {"fluid": "minecraft:lava"}}
            }
            """
        )
        self.assertEqual(recipe.module_id, "createoreexcavation.item_vein")
        self.assertEqual(
            recipe.state["vein"]["vein_id"], "createoreexcavation:ore_vein_type/gold"
        )
        self.assertEqual(recipe.state["fluid"]["id"], "minecraft:lava")
        self.assertEqual(recipe.state["fluid_amount"], 1000)

    def test_unsupported_type_is_readable_error(self):
        with self.assertRaises(RecipeImportError) as context:
            parse_recipe('{"type": "minecraft:not_a_recipe"}')
        self.assertIn("Неподдерживаемый", str(context.exception))

    def test_garbage_does_not_crash(self):
        with self.assertRaises(RecipeImportError):
            parse_recipe("this is not a recipe")


if __name__ == "__main__":
    unittest.main()
