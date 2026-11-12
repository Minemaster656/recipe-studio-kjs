"""In-memory recipe index for jars, datapacks and KubeJS scripts.

The index deliberately keeps only lightweight metadata for datapack recipes.
The original JSON is re-read lazily when the user presses *Import*, so adding a
large modpack does not duplicate every recipe object in memory.
"""

from __future__ import annotations

import copy
import io
import json
import threading
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

try:  # Python 3.11+
    import tomllib
except ImportError:  # pragma: no cover - the project targets Python 3.14
    tomllib = None

from RecipeStudio.services.recipe_import import (
    ImportedRecipe,
    RecipeImportError,
    _state_input_ids,
    _state_output_ids,
    iter_imported_recipes,
    module_id_for_type,
    parse_recipe,
    target_mod_for_outputs,
)


ProgressCallback = Callable[[int, int, str], None]
DoneCallback = Callable[["IndexResult"], None]


@dataclass(slots=True)
class RecipeRecord:
    key: str
    recipe_id: str
    type_id: str
    module_id: str
    source_group: str
    source_detail: str
    target_mod: str
    outputs: tuple[str, ...]
    kind: str
    path: str
    inputs: tuple[str, ...] = ()
    member: str = ""
    nested: str = ""
    format: str = ""
    state: dict | None = None
    import_error: str = ""
    call_index: int = -1

    @property
    def display_name(self) -> str:
        if self.outputs:
            first = self.outputs[0]
            extra = len(self.outputs) - 1
            return first + (f"  +{extra}" if extra else "")
        if self.recipe_id:
            return self.recipe_id
        return self.type_id or self.source_detail

    @property
    def importable(self) -> bool:
        return bool(self.module_id) and not self.import_error

    def search_blob(self) -> str:
        return " ".join(
            (
                self.recipe_id,
                self.type_id,
                self.module_id,
                self.source_group,
                self.source_detail,
                self.target_mod,
                " ".join(self.outputs),
            )
        ).lower()


@dataclass(slots=True)
class IndexResult:
    added: int = 0
    skipped: int = 0
    failed: int = 0
    cancelled: bool = False
    errors: list[tuple[str, str]] = field(default_factory=list)


@dataclass(slots=True)
class _Job:
    kind: str
    path: Path
    member: str = ""
    nested: str = ""


def _is_recipe_entry(name: str) -> bool:
    parts = name.split("/")
    return (
        len(parts) >= 4
        and parts[0] == "data"
        and parts[2] in ("recipe", "recipes")
        and name.endswith(".json")
    )


def _recipe_id_from_entry(name: str) -> str:
    parts = name.split("/")
    if len(parts) >= 4 and parts[0] == "data" and parts[2] in ("recipe", "recipes"):
        return f"{parts[1]}:{'/'.join(parts[3:])[:-5]}"
    return ""


def _recipe_id_from_path(path: Path) -> str:
    parts = path.parts
    for index, part in enumerate(parts):
        if (
            part == "data"
            and index + 3 < len(parts)
            and parts[index + 2] in ("recipe", "recipes")
        ):
            return f"{parts[index + 1]}:{'/'.join(parts[index + 3 :])[:-5]}"
    return ""


def _mod_info(zf: zipfile.ZipFile, fallback: str) -> str:
    for name in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml"):
        try:
            raw = zf.read(name)
        except KeyError, OSError:
            continue
        if tomllib is not None:
            try:
                data = tomllib.loads(raw.decode("utf-8", errors="replace"))
            except Exception:
                data = None
            if isinstance(data, dict):
                mods = data.get("mods") or []
                if isinstance(mods, list) and mods and isinstance(mods[0], dict):
                    entry = mods[0]
                    name_value = entry.get("displayName") or entry.get("modId")
                    if (
                        isinstance(name_value, str)
                        and name_value
                        and "${" not in name_value
                    ):
                        return name_value

    try:
        raw = zf.read("fabric.mod.json")
        data = json.loads(raw.decode("utf-8", errors="replace"))
        name_value = data.get("name") or data.get("id")
        if isinstance(name_value, str) and name_value:
            return name_value
    except KeyError, OSError, ValueError, AttributeError:
        pass
    return fallback


def _append_outputs(value, result: list[str]) -> None:
    if value is None:
        return
    if isinstance(value, list):
        for item in value:
            _append_outputs(item, result)
        return
    if isinstance(value, str):
        if value:
            result.append(value)
        return
    if not isinstance(value, dict):
        return
    if value.get("kind") == "empty":
        return
    item_id = value.get("id")
    if isinstance(item_id, str) and item_id:
        result.append(item_id)
        return
    item = value.get("item")
    if isinstance(item, str):
        result.append(item)
        return
    if isinstance(item, dict):
        _append_outputs(item, result)
        return
    fluid = value.get("fluid")
    if isinstance(fluid, str):
        result.append(fluid)
        return
    if isinstance(fluid, dict):
        _append_outputs(fluid, result)
        return
    tag = value.get("tag")
    if isinstance(tag, str):
        result.append(f"#{tag}")


def _json_outputs(data: dict) -> list[str]:
    result: list[str] = []
    for key in ("result", "results", "output", "outputs"):
        if key in data:
            _append_outputs(data[key], result)
    return list(dict.fromkeys(result))


def _json_inputs(data: dict) -> list[str]:
    result: list[str] = []
    for key in (
        "ingredient",
        "ingredients",
        "input",
        "inputs",
        "template",
        "base",
        "addition",
    ):
        if key in data:
            _append_outputs(data[key], result)
    return list(dict.fromkeys(result))


class RecipeIndex:
    """Thread-safe collection of recipe records."""

    def __init__(self) -> None:
        self.records: list[RecipeRecord] = []
        self._keys: set[str] = set()
        self._lock = threading.RLock()

    def clear(self) -> None:
        with self._lock:
            self.records.clear()
            self._keys.clear()

    def add(self, record: RecipeRecord) -> bool:
        with self._lock:
            if record.key in self._keys:
                return False
            self._keys.add(record.key)
            self.records.append(record)
            return True

    def extend(self, records: Iterable[RecipeRecord]) -> int:
        return sum(1 for record in records if self.add(record))

    def remove(self, key: str) -> bool:
        with self._lock:
            if key not in self._keys:
                return False
            self._keys.remove(key)
            self.records = [record for record in self.records if record.key != key]
            return True

    def snapshot(self) -> list[RecipeRecord]:
        with self._lock:
            return list(self.records)

    def search(self, query: str) -> list[RecipeRecord]:
        records = self.snapshot()
        words = [word for word in str(query or "").lower().split() if word]
        if not words:
            return records
        return [
            record
            for record in records
            if all(word in record.search_blob() for word in words)
        ]

    def group(
        self, records: list[RecipeRecord] | None = None, by: str = "type"
    ) -> list[tuple[str, list[RecipeRecord]]]:
        if records is None:
            records = self.snapshot()
        grouped: dict[str, list[RecipeRecord]] = {}
        for record in records:
            if by == "target":
                key = record.target_mod or "unknown"
            elif by == "source":
                key = record.source_group or "unknown"
            else:
                key = record.type_id or "unknown"
            grouped.setdefault(key, []).append(record)
        return sorted(grouped.items(), key=lambda item: item[0].lower())


def _read_text(record: RecipeRecord) -> str:
    path = Path(record.path)
    if record.kind == "json":
        return path.read_text(encoding="utf-8-sig", errors="replace")
    if record.kind == "jar":
        with zipfile.ZipFile(path) as zf:
            return zf.read(record.member).decode("utf-8-sig", errors="replace")
    if record.kind == "zipjson":
        with zipfile.ZipFile(path) as zf:
            return zf.read(record.member).decode("utf-8-sig", errors="replace")
    if record.kind == "zipjar":
        with zipfile.ZipFile(path) as outer:
            data = outer.read(record.nested)
        with zipfile.ZipFile(io.BytesIO(data)) as inner:
            return inner.read(record.member).decode("utf-8-sig", errors="replace")
    raise RecipeImportError(f"Неизвестный источник рецепта: {record.kind}")


def load_imported_recipe(record: RecipeRecord) -> ImportedRecipe:
    """Read the original source and return a state ready for the editor."""
    if record.kind == "js":
        if record.state is None:
            raise RecipeImportError("Состояние KubeJS-рецепта потеряно")
        return ImportedRecipe(
            record.module_id,
            copy.deepcopy(record.state),
            record.format or "KubeJS",
            [],
            record.type_id or None,
            record.recipe_id or None,
            record.call_index,
        )
    text = _read_text(record)
    recipe = parse_recipe(text)
    if record.recipe_id:
        recipe.recipe_id = record.recipe_id
    return recipe


class RecipeIndexer:
    """Background-friendly indexer; call it from a worker thread."""

    def __init__(
        self,
        index: RecipeIndex,
        *,
        on_progress: ProgressCallback | None = None,
        on_done: DoneCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        self.index = index
        self.on_progress = on_progress
        self.on_done = on_done
        self.cancel_event = cancel_event or threading.Event()

    def index_paths(self, paths: Iterable[str | Path]) -> IndexResult:
        result = IndexResult()
        jobs = self._collect_jobs(paths, result)
        total = len(jobs)
        for counter, job in enumerate(jobs, start=1):
            if self.cancel_event.is_set():
                result.cancelled = True
                break
            label = job.path.name
            if job.nested:
                label += f" / {Path(job.nested).name}"
            self._progress(counter - 1, total, label)
            try:
                added = self._run_job(job)
            except Exception as exc:  # noqa: BLE001 - one bad archive must not stop the rest
                result.failed += 1
                result.errors.append((str(job.path), f"{type(exc).__name__}: {exc}"))
            else:
                result.added += added
                if added == 0:
                    result.skipped += 1
            self._progress(counter, total, label)
        if self.cancel_event.is_set():
            result.cancelled = True
        if self.on_done is not None:
            self.on_done(result)
        return result

    # ------------------------------------------------------------------
    def _progress(self, done: int, total: int, label: str) -> None:
        if self.on_progress is not None:
            try:
                self.on_progress(done, total, label)
            except Exception:
                pass

    def _collect_jobs(
        self, paths: Iterable[str | Path], result: IndexResult
    ) -> list[_Job]:
        jobs: list[_Job] = []
        seen: set[tuple[str, str, str, str]] = set()

        def add_job(job: _Job) -> None:
            marker = (job.kind, str(job.path), job.member, job.nested)
            if marker not in seen:
                seen.add(marker)
                jobs.append(job)

        def add_file(path: Path) -> None:
            suffix = path.suffix.lower()
            if suffix == ".jar":
                add_job(_Job("jar", path.resolve()))
            elif suffix == ".js":
                add_job(_Job("js", path.resolve()))
            elif suffix == ".json":
                add_job(_Job("json", path.resolve()))
            elif suffix == ".zip":
                try:
                    with zipfile.ZipFile(path) as zf:
                        names = zf.namelist()
                except Exception as exc:  # noqa: BLE001
                    result.failed += 1
                    result.errors.append((str(path), str(exc)))
                    return
                nested_jars = [name for name in names if name.lower().endswith(".jar")]
                direct_json = [name for name in names if _is_recipe_entry(name)]
                for name in nested_jars:
                    add_job(_Job("zipjar", path.resolve(), nested=name))
                for name in direct_json:
                    add_job(_Job("zipjson", path.resolve(), member=name))

        for raw in paths:
            path = Path(str(raw)).expanduser()
            if not path.exists():
                result.failed += 1
                result.errors.append((str(path), "Путь не существует"))
                continue
            if path.is_dir():
                for child in sorted(path.rglob("*")):
                    if child.is_file() and child.suffix.lower() in (
                        ".jar",
                        ".zip",
                        ".js",
                        ".json",
                    ):
                        add_file(child)
            elif path.is_file():
                add_file(path)
            else:
                result.failed += 1
                result.errors.append((str(path), "Это не файл и не папка"))
        return jobs

    def _run_job(self, job: _Job) -> int:
        if job.kind == "jar":
            return self._index_jar(job)
        if job.kind == "zipjar":
            return self._index_zip_jar(job)
        if job.kind == "zipjson":
            return self._index_zip_json(job)
        if job.kind == "json":
            return self._index_json(job)
        if job.kind == "js":
            return self._index_js(job)
        return 0

    # ------------------------------------------------------------------
    def _index_jar(self, job: _Job) -> int:
        added = 0
        with zipfile.ZipFile(job.path) as zf:
            source_group = _mod_info(zf, job.path.stem)
            for entry in zf.namelist():
                if not _is_recipe_entry(entry):
                    continue
                try:
                    raw = zf.read(entry)
                except KeyError, OSError:
                    continue
                record = self._json_record(
                    raw,
                    recipe_id=_recipe_id_from_entry(entry),
                    source_group=source_group,
                    source_detail=job.path.name,
                    kind="jar",
                    path=str(job.path),
                    member=entry,
                )
                if record is not None and self.index.add(record):
                    added += 1
        return added

    def _index_zip_jar(self, job: _Job) -> int:
        with zipfile.ZipFile(job.path) as outer:
            data = outer.read(job.nested)
        added = 0
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            source_group = _mod_info(zf, Path(job.nested).stem)
            for entry in zf.namelist():
                if not _is_recipe_entry(entry):
                    continue
                try:
                    raw = zf.read(entry)
                except KeyError, OSError:
                    continue
                record = self._json_record(
                    raw,
                    recipe_id=_recipe_id_from_entry(entry),
                    source_group=source_group,
                    source_detail=f"{job.path.name} / {Path(job.nested).name}",
                    kind="zipjar",
                    path=str(job.path),
                    member=entry,
                    nested=job.nested,
                )
                if record is not None and self.index.add(record):
                    added += 1
        return added

    def _index_zip_json(self, job: _Job) -> int:
        with zipfile.ZipFile(job.path) as zf:
            raw = zf.read(job.member)
        record = self._json_record(
            raw,
            recipe_id=_recipe_id_from_entry(job.member),
            source_group="Datapack",
            source_detail=job.path.name,
            kind="zipjson",
            path=str(job.path),
            member=job.member,
        )
        return 1 if record is not None and self.index.add(record) else 0

    def _index_json(self, job: _Job) -> int:
        raw = job.path.read_bytes()
        record = self._json_record(
            raw,
            recipe_id=_recipe_id_from_path(job.path),
            source_group="Datapack",
            source_detail=job.path.name,
            kind="json",
            path=str(job.path),
        )
        return 1 if record is not None and self.index.add(record) else 0

    def _json_record(
        self,
        raw: bytes,
        *,
        recipe_id: str,
        source_group: str,
        source_detail: str,
        kind: str,
        path: str,
        member: str = "",
        nested: str = "",
    ) -> RecipeRecord | None:
        text = raw.decode("utf-8-sig", errors="replace")
        try:
            data = json.loads(text)
        except ValueError:
            return None
        if not isinstance(data, dict):
            return None
        type_id = str(data.get("type", "")).strip()
        if not type_id:
            return None

        module_id = module_id_for_type(type_id) or ""
        outputs = _json_outputs(data)
        inputs = _json_inputs(data)
        import_error = ""
        if module_id:
            try:
                imported = parse_recipe(text)
                outputs = _state_output_ids(imported.state) or outputs
                inputs = _state_input_ids(imported.state) or inputs
            except Exception as exc:  # noqa: BLE001 - keep the row, show the error on import
                import_error = str(exc)

        key = f"{kind}:{path}:{nested}:{member}"
        return RecipeRecord(
            key=key,
            recipe_id=recipe_id,
            type_id=type_id,
            module_id=module_id,
            source_group=source_group or "Datapack",
            source_detail=source_detail,
            target_mod=target_mod_for_outputs(outputs),
            outputs=tuple(dict.fromkeys(outputs)),
            kind=kind,
            path=path,
            inputs=tuple(dict.fromkeys(inputs)),
            member=member,
            nested=nested,
            format="datapack JSON",
            import_error=import_error,
        )

    def _index_js(self, job: _Job) -> int:
        text = job.path.read_text(encoding="utf-8-sig", errors="replace")
        added = 0
        for imported in iter_imported_recipes(text):
            outputs = _state_output_ids(imported.state)
            inputs = _state_input_ids(imported.state)
            key = f"js:{job.path}:{imported.call_index}"
            record = RecipeRecord(
                key=key,
                recipe_id=imported.recipe_id or "",
                type_id=imported.type_id or "",
                module_id=imported.module_id,
                source_group="KubeJS JavaScript",
                source_detail=job.path.name,
                target_mod=target_mod_for_outputs(outputs),
                outputs=tuple(dict.fromkeys(outputs)),
                kind="js",
                path=str(job.path),
                inputs=tuple(dict.fromkeys(inputs)),
                format=imported.format,
                state=imported.state,
                call_index=imported.call_index,
            )
            if self.index.add(record):
                added += 1
        return added
