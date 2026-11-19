import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from RecipeStudio.config import Config
from RecipeStudio.services.catalog import Catalog
from RecipeStudio.services.projects import (
    create_project,
    ensure_active_project,
    list_projects,
    load_project,
    migrate_legacy_config,
    save_project,
)


class ProjectPathTests(unittest.TestCase):
    def test_absolute_and_relative_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects = root / "projects"
            projects.mkdir()
            (projects / "icons").mkdir()
            path = projects / "demo.json"
            path.write_text(
                json.dumps(
                    {
                        "name": "Demo",
                        "icons_dir": "icons",
                        "items_json": str(root / "all_items.json"),
                        "recipe_sources": ["../mods", str(root / "kubejs")],
                        "extra_lang_jars": ["../versions/*/*.jar"],
                    }
                ),
                encoding="utf-8",
            )

            config = load_project(path)

            self.assertEqual(
                config.path_for("icons_dir"), (projects / "icons").resolve()
            )
            self.assertEqual(
                config.path_for("items_json"), (root / "all_items.json").resolve()
            )
            self.assertEqual(
                config.get("recipe_sources"),
                [
                    str((root / "mods").resolve()),
                    str((root / "kubejs").resolve()),
                ],
            )
            self.assertEqual(
                config.get("extra_lang_jars"),
                [str((root / "versions" / "*" / "*.jar").resolve())],
            )

    def test_save_keeps_absolute_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects = root / "projects"
            projects.mkdir()
            app_config = Config(
                {"projects_dir": str(projects)}, root / "config.json", base_dir=root
            )
            config = create_project(app_config, "Saved", {"icons_dir": str(root / "i")})
            save_project(config.project_path, config)
            data = json.loads(config.project_path.read_text(encoding="utf-8"))
            self.assertEqual(data["icons_dir"], str((root / "i").resolve()))
            self.assertTrue(Path(data["favorites"]).is_absolute())
            self.assertTrue(Path(data["names_cache"]).is_absolute())


class ProjectMigrationTests(unittest.TestCase):
    def _legacy_config(self, root: Path) -> Config:
        root_config = root / "config.json"
        root_config.write_text(
            json.dumps(
                {
                    "projects_dir": str(root / "projects"),
                    "database": str(root / "embeddings.db"),
                    "icons_dir": str(root / "icon-exports-x32"),
                    "items_json": str(root / "all_items.json"),
                    "mods_dir": str(root / "mods"),
                    "kubejs_dir": str(root / "kubejs"),
                    "extra_lang_jars": [str(root / "versions/*/*.jar")],
                    "favorites": "RecipeStudio/data/favorites.json",
                    "names_cache": "RecipeStudio/data/names_cache.json",
                    "disabled_modules": ["create"],
                    "search_limit": 100,
                    "start_maximized": True,
                }
            ),
            encoding="utf-8",
        )
        return Config(
            json.loads(root_config.read_text(encoding="utf-8")),
            root_config,
            base_dir=root,
        )

    def test_migration_creates_default_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "projects").mkdir()
            app_config = self._legacy_config(root)

            created = migrate_legacy_config(app_config)

            self.assertIsNotNone(created)
            self.assertTrue(Path(created).is_file())
            self.assertEqual(app_config.get("start_maximized"), True)
            for key in ("database", "icons_dir", "mods_dir", "disabled_modules"):
                self.assertNotIn(key, app_config.data)

            project = load_project(created)
            self.assertEqual(
                project.path_for("database"), (root / "embeddings.db").resolve()
            )
            self.assertEqual(project.get("disabled_modules"), ["create"])
            self.assertEqual(project.get("search_limit"), 100)
            self.assertEqual(
                project.get("recipe_sources"),
                [
                    str((root / "mods").resolve()),
                    str((root / "kubejs").resolve()),
                ],
            )

    def test_legacy_caches_are_copied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "projects").mkdir()
            app_config = self._legacy_config(root)
            legacy_fav = root / "RecipeStudio" / "data" / "favorites.json"
            legacy_fav.parent.mkdir(parents=True)
            legacy_fav.write_text('["minecraft:stone"]', encoding="utf-8")

            with mock.patch(
                "RecipeStudio.services.projects.project_data_dir",
                return_value=root / "cache" / "default",
            ):
                created = migrate_legacy_config(app_config)

            project = load_project(created)
            favourites = project.path_for("favorites")
            self.assertTrue(favourites.is_file())
            self.assertEqual(
                json.loads(favourites.read_text(encoding="utf-8")),
                ["minecraft:stone"],
            )

    def test_ensure_active_project_creates_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects = root / "projects"
            app_config = Config(
                {"projects_dir": str(projects)}, root / "config.json", base_dir=root
            )

            config, info = ensure_active_project(app_config)

            self.assertTrue(info.path.is_file())
            self.assertEqual(info.path, Path(app_config.get("active_project")))
            self.assertEqual(config.get("name"), "Default")


class ProjectCatalogTests(unittest.TestCase):
    def test_manifest_items_and_icons_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            icons = root / "icon-exports-x32"
            icons.mkdir()
            (icons / "minecraft__stone.png").write_bytes(b"icon")
            (icons / "fluid__minecraft__water.png").write_bytes(b"icon")
            (root / "stone.png").write_bytes(b"icon")
            (root / "cogwheel.png").write_bytes(b"icon")

            items_json = root / "all_items.json"
            items_json.write_text(
                json.dumps(
                    [
                        "minecraft:dirt",
                        {"id": "create:cogwheel", "path": "cogwheel.png"},
                    ]
                ),
                encoding="utf-8",
            )
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "minecraft:stone": "stone.png",
                        "create:shaft": {"data": "aGVsbG8="},
                    }
                ),
                encoding="utf-8",
            )

            config = Config(
                {
                    "icons_dir": str(icons),
                    "items_json": str(items_json),
                    "icon_manifest": str(manifest),
                },
                base_dir=root,
            )
            catalog = Catalog(config)

            self.assertEqual(
                {entry.id for entry in catalog.items},
                {
                    "minecraft:stone",
                    "minecraft:dirt",
                    "create:cogwheel",
                    "create:shaft",
                },
            )
            self.assertIn("minecraft:water", catalog.fluids_by_id)
            self.assertEqual(
                catalog.get("minecraft:stone").icon_path, (root / "stone.png").resolve()
            )
            self.assertEqual(catalog.get("create:shaft").icon_data, b"hello")
            self.assertEqual(
                catalog.get("create:cogwheel").icon_path,
                (root / "cogwheel.png").resolve(),
            )

    def test_empty_project_has_empty_palette(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Config({}, base_dir=Path(tmp))
            catalog = Catalog(config)
            self.assertEqual(catalog.count(), 0)
            self.assertEqual(catalog.search_items(), [])


class ProjectListingTests(unittest.TestCase):
    def test_create_and_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app_config = Config(
                {"projects_dir": str(root / "projects")},
                root / "config.json",
                base_dir=root,
            )

            first = create_project(app_config, "Kindur II")
            second = create_project(app_config, "Alpha")

            self.assertTrue(first.project_path.is_file())
            self.assertTrue(second.project_path.is_file())
            labels = [info.label for info in list_projects(app_config)]
            self.assertEqual(labels, ["Alpha", "Kindur II"])


if __name__ == "__main__":
    unittest.main()