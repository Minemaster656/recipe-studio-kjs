"""Project files: one JSON profile per modpack / build.

A project stores every path that used to be global in ``config.json``:
the icon export, item catalogue, embeddings database, mods/KubeJS folders,
api settings and per-project favourites/name caches.

Paths are always persisted as absolute paths.  Relative values are accepted
only when loading hand-written files and are resolved against the project
file's directory.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from RecipeStudio.config import (
    DEFAULT_PROJECT,
    LEGACY_PROJECT_KEYS,
    SCRIPTS_DIR,
    Config,
    app_data_dir,
)

PATH_KEYS = (
    "items_json",
    "icons_dir",
    "icon_manifest",
    "database",
    "mods_dir",
    "kubejs_dir",
    "favorites",
    "names_cache",
)

LIST_PATH_KEYS = ("extra_lang_jars", "recipe_sources")


class ProjectError(RuntimeError):
    """Raised when a project file cannot be read or written."""


@dataclass(frozen=True)
class ProjectInfo:
    slug: str
    path: Path
    name: str

    @property
    def label(self) -> str:
        return self.name or self.slug


def _absolute(value: Any, base: Path) -> Path:
    p = Path(str(value)).expanduser()
    if not p.is_absolute():
        p = base / p
    return p.resolve()


def _absolute_pattern(value: Any, base: Path) -> str:
    return str(_absolute(value, base))


def projects_dir(app_config: Config) -> Path:
    raw = app_config.get("projects_dir") or (app_data_dir() / "projects")
    path = _absolute(raw, SCRIPTS_DIR)
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ProjectError(f"Cannot create projects directory {path}: {exc}") from exc
    return path


def project_data_dir(slug: str) -> Path:
    safe = re.sub(r"[^\w.-]+", "-", str(slug or "project"), flags=re.UNICODE)
    safe = safe.strip("-._") or "project"
    return (app_data_dir() / "data" / safe).resolve()


def slugify(name: str) -> str:
    slug = re.sub(r"[^\w.-]+", "-", str(name or "").strip().lower(), flags=re.UNICODE)
    return slug.strip("-._") or "project"


def _default_caches(slug: str) -> dict[str, str]:
    folder = project_data_dir(slug)
    return {
        "favorites": str(folder / "favorites.json"),
        "names_cache": str(folder / "names_cache.json"),
    }


def default_project_payload(name: str = "Default") -> dict[str, Any]:
    slug = slugify(name)
    return {
        **DEFAULT_PROJECT,
        "name": name,
        **_default_caches(slug),
    }


def _list_from_config(config: Config, key: str) -> list[str]:
    value = config.get(key)
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    return []


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ProjectError(f"Cannot read project {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ProjectError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ProjectError(f"Project {path} must contain a JSON object")
    return data


def _normalise_project_data(
    data: dict[str, Any], path: Path, *, fill_caches: bool = True
) -> dict[str, Any]:
    result = {**DEFAULT_PROJECT, **data}
    result["schema"] = int(result.get("schema") or 1)
    result["name"] = str(result.get("name") or path.stem)

    for key in PATH_KEYS:
        value = result.get(key)
        if value:
            result[key] = str(_absolute(value, path.parent))

    for key in LIST_PATH_KEYS:
        values: Iterable[Any]
        raw = result.get(key)
        if isinstance(raw, str):
            values = [raw]
        elif isinstance(raw, (list, tuple)):
            values = raw
        else:
            values = []
        result[key] = [
            _absolute_pattern(value, path.parent)
            for value in values
            if str(value).strip()
        ]

    if fill_caches:
        slug = path.stem
        caches = _default_caches(slug)
        result.setdefault("favorites", caches["favorites"])
        result.setdefault("names_cache", caches["names_cache"])
        if not result.get("favorites"):
            result["favorites"] = caches["favorites"]
        if not result.get("names_cache"):
            result["names_cache"] = caches["names_cache"]

    result["search_limit"] = int(result.get("search_limit") or 500)
    disabled = result.get("disabled_modules") or []
    if isinstance(disabled, str):
        disabled = [part.strip() for part in disabled.split(",") if part.strip()]
    result["disabled_modules"] = [str(item) for item in disabled if str(item).strip()]
    result["auto_index"] = bool(result.get("auto_index", True))
    mode = str(result.get("create_export_mode") or "addon")
    result["create_export_mode"] = mode if mode in ("addon", "custom") else "addon"
    return result


def load_project(path: str | Path) -> Config:
    resolved = _absolute(path, SCRIPTS_DIR)
    data = _normalise_project_data(_read_json(resolved), resolved)
    config = Config(data, resolved, base_dir=resolved.parent)
    config.project_path = resolved
    config.project_name = str(data.get("name") or resolved.stem)
    return config


def save_project(path: str | Path, config: Config) -> Path:
    resolved = _absolute(path, SCRIPTS_DIR)
    data = _normalise_project_data(config.data, resolved)
    config.data = data
    config.path = resolved
    config.project_path = resolved
    config.project_name = str(data.get("name") or resolved.stem)
    try:
        config.save()
    except OSError as exc:
        raise ProjectError(f"Cannot write project {resolved}: {exc}") from exc
    return resolved


def unique_project_path(folder: Path, name: str) -> Path:
    slug = slugify(name)
    candidate = folder / f"{slug}.json"
    index = 2
    while candidate.exists():
        candidate = folder / f"{slug}-{index}.json"
        index += 1
    return candidate


def create_project(
    app_config: Config,
    name: str,
    values: dict[str, Any] | None = None,
) -> Config:
    folder = projects_dir(app_config)
    path = unique_project_path(folder, name)
    slug = path.stem
    data = default_project_payload(name)
    data.update(values or {})
    data["name"] = name
    data.update(_default_caches(slug))
    return load_project_from_data(path, data)


def load_project_from_data(path: str | Path, data: dict[str, Any]) -> Config:
    resolved = _absolute(path, SCRIPTS_DIR)
    normalised = _normalise_project_data(data, resolved)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    tmp = resolved.with_suffix(resolved.suffix + ".tmp")
    try:
        tmp.write_text(
            json.dumps(normalised, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        tmp.replace(resolved)
    except OSError as exc:
        raise ProjectError(f"Cannot write project {resolved}: {exc}") from exc
    config = Config(normalised, resolved, base_dir=resolved.parent)
    config.project_path = resolved
    config.project_name = str(normalised.get("name") or resolved.stem)
    return config


def list_projects(app_config: Config) -> list[ProjectInfo]:
    folder = projects_dir(app_config)
    projects: list[ProjectInfo] = []
    try:
        files = sorted(folder.glob("*.json"))
    except OSError:
        return projects
    for path in files:
        try:
            data = _read_json(path)
        except ProjectError:
            continue
        name = str(data.get("name") or path.stem)
        projects.append(ProjectInfo(path.stem, path.resolve(), name))
    projects.sort(key=lambda item: (item.label.casefold(), item.slug))
    return projects


def _legacy_path(config: Config, key: str) -> str | None:
    if not config.get(key):
        return None
    return str(config.path_for(key))


def legacy_project_payload(config: Config) -> dict[str, Any]:
    """Build a project from the old single-config layout."""
    data = default_project_payload("Default")

    for key in (
        "items_json",
        "icons_dir",
        "icon_manifest",
        "database",
        "mods_dir",
        "kubejs_dir",
    ):
        value = _legacy_path(config, key)
        if value:
            data[key] = value

    if config.get("base_url"):
        data["base_url"] = str(config.get("base_url"))
    if config.get("embedding_model"):
        data["embedding_model"] = str(config.get("embedding_model"))
    if config.get("search_limit") is not None:
        data["search_limit"] = int(config.get("search_limit") or 500)
    if config.get("disabled_modules") is not None:
        data["disabled_modules"] = _list_from_config(config, "disabled_modules")

    data["extra_lang_jars"] = [
        _absolute_pattern(item, SCRIPTS_DIR)
        for item in _list_from_config(config, "extra_lang_jars")
    ]

    sources: list[str] = []
    for key in ("mods_dir", "kubejs_dir"):
        value = data.get(key)
        if value and value not in sources:
            sources.append(value)
    data["recipe_sources"] = sources
    data["auto_index"] = True
    return data


def _has_legacy_keys(config: Config) -> bool:
    return any(key in config.data for key in LEGACY_PROJECT_KEYS)


def _copy_legacy_caches(legacy: Config, project: Config) -> None:
    """Move the old global favourites/name cache into the project folder."""
    for key in ("favorites", "names_cache"):
        if not legacy.get(key) or not project.get(key):
            continue
        source = legacy.path_for(key)
        target = project.path_for(key)
        if not source.is_file() or target.exists():
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
        except OSError:
            pass


def migrate_legacy_config(app_config: Config) -> Path | None:
    """Convert the old flat config.json into projects/default.json.

    Returns the created project path, or ``None`` when there is nothing to
    migrate.  The legacy keys are removed from the global config.
    """
    if not _has_legacy_keys(app_config):
        return None

    folder = projects_dir(app_config)
    existing = list_projects(app_config)
    created: Path | None = None
    if not existing:
        path = unique_project_path(folder, "Default")
        payload = legacy_project_payload(app_config)
        config = load_project_from_data(path, payload)
        _copy_legacy_caches(app_config, config)
        created = config.project_path or path

    for key in LEGACY_PROJECT_KEYS:
        app_config.data.pop(key, None)

    if created is not None:
        app_config.data["active_project"] = str(created)
    app_config.data["projects_dir"] = str(folder)
    app_config.save()
    return created


def _resolve_active(app_config: Config) -> Path | None:
    raw = app_config.get("active_project")
    if not raw:
        return None
    path = _absolute(raw, SCRIPTS_DIR)
    return path if path.is_file() else None


def ensure_active_project(app_config: Config) -> tuple[Config, ProjectInfo]:
    """Return the configured project, creating/migrating one when needed."""
    migrate_legacy_config(app_config)

    folder = projects_dir(app_config)
    projects = list_projects(app_config)
    active_path = _resolve_active(app_config)

    info: ProjectInfo | None = None
    if active_path is not None:
        info = next((item for item in projects if item.path == active_path), None)
        if info is None:
            try:
                data = _read_json(active_path)
            except ProjectError:
                data = {}
            info = ProjectInfo(
                active_path.stem,
                active_path,
                str(data.get("name") or active_path.stem),
            )

    if info is None and projects:
        info = projects[0]

    if info is None:
        payload = default_project_payload("Default")
        path = unique_project_path(folder, "Default")
        config = load_project_from_data(path, payload)
        info = ProjectInfo(path.stem, path, config.project_name or "Default")

    try:
        config = load_project(info.path)
    except ProjectError:
        config = load_project_from_data(
            info.path,
            {**default_project_payload(info.name), **_default_caches(info.path.stem)},
        )

    app_config.data["projects_dir"] = str(folder)
    app_config.data["active_project"] = str(info.path)
    app_config.save()
    return config, info
