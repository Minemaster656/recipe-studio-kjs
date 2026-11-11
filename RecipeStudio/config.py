"""Configuration loading.

All paths in config.json are relative to the ``scripts`` directory unless
absolute.  This keeps RecipeStudio usable when the whole folder is moved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PACKAGE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = PACKAGE_DIR.parent
CONFIG_PATH = PACKAGE_DIR / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    # Data used by the search gateway.  This is the only place the embedding
    # database is referenced.
    "database": "embeddings.db",
    "base_url": "http://127.0.0.1:9931/v1",
    "embedding_model": "embeddinggemma2",
    # Local game data.
    "items_json": "all_items.json",
    "icons_dir": "icon-exports-x32",
    "mods_dir": "../mods",
    "kubejs_dir": "../kubejs",
    "extra_lang_jars": ["../../../../versions/*/*.jar"],
    # Persisted UI data.
    "favorites": "RecipeStudio/data/favorites.json",
    "names_cache": "RecipeStudio/data/names_cache.json",
    # Behaviour.
    "search_limit": 500,
    "disabled_modules": [],
    "start_maximized": False,
}


class Config:
    def __init__(self, data: dict[str, Any] | None = None, path: Path | None = None):
        self.data: dict[str, Any] = {**DEFAULT_CONFIG, **(data or {})}
        self.path = path

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def path_for(self, key: str) -> Path:
        value = self.data.get(key)
        if not value:
            return SCRIPTS_DIR
        p = Path(str(value)).expanduser()
        if not p.is_absolute():
            p = SCRIPTS_DIR / p
        return p.resolve()

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def load_config() -> Config:
    data: dict[str, Any] = {}
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except OSError, json.JSONDecodeError:
            data = {}
    else:
        cfg = Config({}, CONFIG_PATH)
        cfg.save()
        return cfg
    return Config(data, CONFIG_PATH)
