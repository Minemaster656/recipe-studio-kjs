"""Configuration loading for the app and for per-build projects.

The global ``config.json`` stores only application-wide settings (where the
projects folder is, which project is active, window prefs).  Everything that
belongs to a concrete modpack lives in a project JSON file.

Project files always store **absolute** paths.  ``Config.path_for`` still
expands ``~`` and, as a safety net for hand-written files, resolves relative
values against the project directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import platformdirs

PACKAGE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = PACKAGE_DIR.parent
CONFIG_PATH = PACKAGE_DIR / "config.json"

APP_NAME = "recipe-studio"


def app_data_dir() -> Path:
    """Per-user data directory (projects, caches) shared by all checkouts."""
    return Path(
        platformdirs.user_data_dir(APP_NAME, appauthor=False)
    ).expanduser()

# Keys that used to live in config.json before the project system existed.
LEGACY_PROJECT_KEYS = (
    "database",
    "base_url",
    "embedding_model",
    "items_json",
    "icons_dir",
    "mods_dir",
    "kubejs_dir",
    "extra_lang_jars",
    "favorites",
    "names_cache",
    "search_limit",
    "disabled_modules",
)

# Application-wide defaults.  Paths are absolute so the app never has to guess
# the working directory.
DEFAULT_CONFIG: dict[str, Any] = {
    "projects_dir": str(app_data_dir() / "projects"),
    "active_project": None,
    "start_maximized": False,
}

# Per-project defaults.  ``None`` means "not configured" rather than "use the
# current working directory".
DEFAULT_PROJECT: dict[str, Any] = {
    "schema": 1,
    "name": "Default",
    "items_json": None,
    "icons_dir": None,
    "icon_manifest": None,
    "database": None,
    "base_url": "http://127.0.0.1:9931/v1",
    "embedding_model": "embeddinggemma2",
    "mods_dir": None,
    "kubejs_dir": None,
    "extra_lang_jars": [],
    "recipe_sources": [],
    "auto_index": True,
    "favorites": None,
    "names_cache": None,
    "search_limit": 500,
    "disabled_modules": [],
    "create_export_mode": "addon",
}

# Backwards-compatible alias used by older imports.
DEFAULT_PROJECT_KEYS = tuple(DEFAULT_PROJECT)


class Config:
    def __init__(
        self,
        data: dict[str, Any] | None = None,
        path: Path | None = None,
        base_dir: Path | None = None,
    ):
        self.data: dict[str, Any] = dict(data or {})
        self.path = path
        self.base_dir = Path(base_dir).resolve() if base_dir else SCRIPTS_DIR
        self.project_path: Path | None = None
        self.project_name: str = ""

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.data[key] = value

    def path_for(self, key: str) -> Path:
        """Return the absolute path configured under ``key``.

        An empty value falls back to the base directory.  Callers that must
        distinguish "missing" from "base directory" should check
        ``config.get(key)`` first.
        """
        value = self.data.get(key)
        return self.resolve(value)

    def resolve(self, value: Any) -> Path:
        if not value:
            return self.base_dir
        p = Path(str(value)).expanduser()
        if not p.is_absolute():
            p = self.base_dir / p
        return p.resolve()

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self.path)


def load_config() -> Config:
    data: dict[str, Any] = {}
    if CONFIG_PATH.exists():
        try:
            loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except OSError, json.JSONDecodeError:
            data = {}
    merged = {**DEFAULT_CONFIG, **data}
    # Legacy config.json values were relative to the repository root, so keep
    # that base directory during migration.
    cfg = Config(merged, CONFIG_PATH, base_dir=SCRIPTS_DIR)
    if not CONFIG_PATH.exists():
        cfg.save()
    return cfg
