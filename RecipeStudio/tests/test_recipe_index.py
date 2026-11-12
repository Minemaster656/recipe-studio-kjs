import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from RecipeStudio.services.recipe_import import removal_snippet
from RecipeStudio.services.recipe_index import (
    RecipeIndex,
    RecipeIndexer,
    load_imported_recipe,
)


def make_jar(path: Path, mod_id: str = "testmod", mod_name: str = "Test Mod") -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "META-INF/mods.toml",
            f'[[mods]]\nmodId="{mod_id}"\ndisplayName="{mod_name}"\n',
        )
        zf.writestr(
            f"data/{mod_id}/recipe/crushing/ore.json",
            json.dumps(
                {
                    "type": "create:crushing",
                    "ingredients": [{"item": "minecraft:iron_ore"}],
                    "results": [{"id": "create:crushed_iron_ore", "count": 2}],
                }
            ),
        )
        zf.writestr(
            f"data/{mod_id}/recipe/crafting/torch.json",
            json.dumps(
                {
                    "type": "minecraft:crafting_shapeless",
                    "ingredients": ["minecraft:stick", "minecraft:coal"],
                    "result": {"id": "minecraft:torch", "count": 4},
                }
            ),
        )


class RecipeIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_jar_metadata_and_import(self):
        jar = self.root / "testmod-1.0.jar"
        make_jar(jar)
        index = RecipeIndex()
        result = RecipeIndexer(index).index_paths([jar])

        self.assertEqual(result.added, 2)
        self.assertEqual(len(index.records), 2)
        record = next(r for r in index.records if r.module_id == "create.crushing")
        self.assertEqual(record.source_group, "Test Mod")
        self.assertEqual(record.recipe_id, "testmod:crushing/ore")
        self.assertEqual(record.target_mod, "create")
        self.assertEqual(record.outputs, ("create:crushed_iron_ore",))
        self.assertTrue(record.importable)

        recipe = load_imported_recipe(record)
        self.assertEqual(recipe.module_id, "create.crushing")
        self.assertEqual(recipe.state["outputs"][0]["id"], "create:crushed_iron_ore")

    def test_js_multiple_recipes_and_remove_is_skipped(self):
        script = self.root / "scripts.js"
        script.write_text(
            """
            ServerEvents.recipes((event) => {
              event.recipes.create.crushing(
                ['minecraft:iron_nugget'], 'minecraft:iron_ore')
              event.shapeless('minecraft:torch', ['minecraft:stick'])
              event.remove({ output: 'minecraft:dirt' })
            })
            """,
            encoding="utf-8",
        )
        index = RecipeIndex()
        result = RecipeIndexer(index).index_paths([script])

        self.assertEqual(result.added, 2)
        self.assertEqual(len(index.records), 2)
        self.assertEqual(index.records[0].source_group, "KubeJS JavaScript")
        torch = next(r for r in index.records if r.module_id == "vanilla.crafting")
        self.assertEqual(torch.type_id, "minecraft:crafting_shapeless")
        self.assertEqual(torch.target_mod, "minecraft")

        recipe = load_imported_recipe(index.records[0])
        self.assertEqual(recipe.state["outputs"][0]["id"], "minecraft:iron_nugget")

    def test_loose_datapack_json(self):
        path = self.root / "data" / "pack" / "recipe" / "smelt.json"
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps(
                {
                    "type": "minecraft:smelting",
                    "ingredient": "minecraft:sand",
                    "result": "minecraft:glass",
                    "cookingtime": 100,
                }
            ),
            encoding="utf-8",
        )
        index = RecipeIndex()
        RecipeIndexer(index).index_paths([path])

        self.assertEqual(len(index.records), 1)
        record = index.records[0]
        self.assertEqual(record.recipe_id, "pack:smelt")
        self.assertEqual(record.source_group, "Datapack")
        self.assertEqual(record.target_mod, "minecraft")
        self.assertEqual(load_imported_recipe(record).state["ticks"], 100)

    def test_zip_with_nested_jar(self):
        jar = self.root / "testmod.jar"
        make_jar(jar)
        archive = self.root / "bundle.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.write(jar, "mods/testmod.jar")

        index = RecipeIndex()
        result = RecipeIndexer(index).index_paths([archive])

        self.assertEqual(result.added, 2)
        self.assertTrue(all(record.kind == "zipjar" for record in index.records))
        record = next(r for r in index.records if r.module_id == "create.crushing")
        self.assertEqual(record.recipe_id, "testmod:crushing/ore")
        self.assertIn("bundle.zip", record.source_detail)
        self.assertEqual(
            load_imported_recipe(record).state["outputs"][0]["id"],
            "create:crushed_iron_ore",
        )

    def test_duplicate_paths_are_not_indexed_twice(self):
        jar = self.root / "testmod.jar"
        make_jar(jar)
        index = RecipeIndex()
        RecipeIndexer(index).index_paths([jar, jar])
        self.assertEqual(len(index.records), 2)

    def test_search_and_group(self):
        jar = self.root / "testmod.jar"
        make_jar(jar)
        index = RecipeIndex()
        RecipeIndexer(index).index_paths([jar])

        self.assertEqual(len(index.search("crushed")), 1)
        self.assertEqual(len(index.search("testmod torch")), 1)
        by_type = dict(index.group(by="type"))
        self.assertIn("create:crushing", by_type)
        by_target = dict(index.group(by="target"))
        self.assertIn("create", by_target)
        self.assertIn("minecraft", by_target)
        by_source = dict(index.group(by="source"))
        self.assertIn("Test Mod", by_source)

    def test_removal_snippet(self):
        with_id = removal_snippet("testmod:crushing/ore", ())
        self.assertIn("event.remove({ id: 'testmod:crushing/ore' })", with_id)
        by_output = removal_snippet(None, ("create:crushed_iron_ore",))
        self.assertIn("event.remove({ output: 'create:crushed_iron_ore' })", by_output)
        by_input = removal_snippet(None, (), ("minecraft:iron_ore",))
        self.assertIn("event.remove({ input: 'minecraft:iron_ore' })", by_input)
        self.assertEqual(removal_snippet(None, ()), "")

    def test_corrupted_archives_do_not_stop_indexing(self):
        bad = self.root / "broken.zip"
        bad.write_bytes(b"this is not a zip")
        good = self.root / "testmod.jar"
        make_jar(good)
        index = RecipeIndex()
        result = RecipeIndexer(index).index_paths([bad, good])
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.added, 2)


if __name__ == "__main__":
    unittest.main()
