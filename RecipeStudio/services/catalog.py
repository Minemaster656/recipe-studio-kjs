"""Item/fluid catalogue built from icons and optional manifests.

Sources, in priority order:

1. ``icon_manifest`` — JSON mapping ``mod:id`` to an icon path or base64 data.
2. ``items_json`` — list of ids or a mapping with optional icon paths.
3. ``icons_dir`` — the classic IconExporter folder (``modid__item_id.png``).

Every source is optional; a project with no data simply gets an empty palette.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from RecipeStudio.config import Config


@dataclass(frozen=True)
class CatalogEntry:
    id: str
    mod: str
    path: str
    kind: str = "item"  # item | fluid
    icon_path: Path | None = None
    icon_data: bytes | None = None

    @property
    def full(self) -> str:
        return self.id


class Catalog:
    def __init__(self, config: Config):
        self.config = config
        icons = config.get("icons_dir")
        self.icons_dir: Path | None = config.path_for("icons_dir") if icons else None
        self.items: list[CatalogEntry] = []
        self.fluids: list[CatalogEntry] = []
        self.by_id: dict[str, CatalogEntry] = {}
        self.fluids_by_id: dict[str, CatalogEntry] = {}
        self._load()

    # ------------------------------------------------------------------
    def _load(self) -> None:
        self._load_manifest()
        self._load_items_json()
        self._load_icons_dir()

        self.items.sort(key=lambda e: e.path.casefold())
        self.fluids.sort(key=lambda e: e.path.casefold())

    # ------------------------------------------------------------------
    @staticmethod
    def _split_id(item_id: str) -> tuple[str, str]:
        if ":" in item_id:
            return tuple(item_id.split(":", 1))  # type: ignore[return-value]
        return "", item_id

    def _store(self, entry: CatalogEntry) -> None:
        table = self.fluids_by_id if entry.kind == "fluid" else self.by_id
        existing = table.get(entry.id)
        if existing is None:
            table[entry.id] = entry
            (self.fluids if entry.kind == "fluid" else self.items).append(entry)
            return
        # An early source may only know the id; attach an icon found later.
        if (
            existing.icon_path is None
            and existing.icon_data is None
            and (entry.icon_path is not None or entry.icon_data is not None)
        ):
            replacement = CatalogEntry(
                existing.id,
                existing.mod,
                existing.path,
                existing.kind,
                entry.icon_path,
                entry.icon_data,
            )
            table[entry.id] = replacement
            target = self.fluids if existing.kind == "fluid" else self.items
            for index, item in enumerate(target):
                if item.id == existing.id:
                    target[index] = replacement
                    break

    # ------------------------------------------------------------------
    def _load_manifest(self) -> None:
        raw = self.config.get("icon_manifest")
        if not raw:
            return
        base = self.config.base_dir
        data: Any = raw
        if isinstance(raw, (str, Path)):
            path = self.config.path_for("icon_manifest")
            base = path.parent
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except OSError, json.JSONDecodeError:
                return
        if not isinstance(data, dict):
            return
        payload = data.get("items") if isinstance(data.get("items"), dict) else data
        for item_id, value in payload.items():
            self._add_described(str(item_id), value, base)

    def _load_items_json(self) -> None:
        raw = self.config.get("items_json")
        if not raw:
            return
        path = self.config.path_for("items_json")
        base = path.parent
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except OSError, json.JSONDecodeError:
            return

        if isinstance(data, dict):
            nested = data.get("items")
            if isinstance(nested, dict):
                for item_id, value in nested.items():
                    self._add_described(str(item_id), value, base)
                return
            if isinstance(nested, list):
                data = nested
            else:
                for item_id, value in data.items():
                    self._add_described(str(item_id), value, base)
                return

        if not isinstance(data, list):
            return
        for value in data:
            if isinstance(value, str):
                self._add_entry(value, "item", base=base)
            elif isinstance(value, dict):
                item_id = value.get("id") or value.get("item") or value.get("name")
                if not item_id:
                    continue
                self._add_described(str(item_id), value, base)

    def _add_described(self, item_id: str, value: Any, base: Path) -> None:
        if not item_id:
            return
        kind = "item"
        icon_path: Path | None = None
        icon_data: bytes | None = None
        if isinstance(value, str):
            icon_path = self._icon_path(value, base)
        elif isinstance(value, dict):
            kind = str(value.get("kind") or "item")
            if kind not in ("item", "fluid"):
                kind = "item"
            raw_path = value.get("path") or value.get("icon") or value.get("file")
            if raw_path:
                icon_path = self._icon_path(str(raw_path), base)
            raw_data = value.get("data") or value.get("base64")
            if raw_data:
                icon_data = self._decode_data(str(raw_data))
        self._store(self._make_entry(item_id, kind, icon_path, icon_data))

    def _load_icons_dir(self) -> None:
        if self.icons_dir is None:
            return
        icon_files: dict[str, Path] = {}
        try:
            for p in self.icons_dir.iterdir():
                if p.is_file() and p.suffix.lower() == ".png":
                    icon_files[p.name] = p
        except OSError:
            return

        # Fluids are exported as fluid__mod__path.png.  Files such as
        # fluid__baton.png belong to the mod literally called "fluid" and
        # therefore must not be treated as fluids.
        for name, path in icon_files.items():
            if not name.startswith("fluid__"):
                continue
            rest = name[len("fluid__") : -len(".png")]
            if "__" not in rest:
                continue
            mod, fluid_path = rest.split("__", 1)
            self._store(
                CatalogEntry(f"{mod}:{fluid_path}", mod, fluid_path, "fluid", path)
            )

        # Items come from the icon export, so every catalogue entry has a real
        # texture.  The exporter writes "modid__item_id.png"; an NBT/component
        # suffix ("__{...}") is cut off and collisions are collapsed.
        for name in sorted(icon_files):
            stem = name[: -len(".png")]
            if stem.startswith("fluid__"):
                rest = stem[len("fluid__") :]
                if "__" in rest:
                    continue  # fluid icon, already handled above
            if "__" not in stem:
                continue
            mod, rest = stem.split("__", 1)
            item_path = rest.split("__{", 1)[0]
            if not mod or not item_path:
                continue
            self._store(
                CatalogEntry(
                    f"{mod}:{item_path}", mod, item_path, "item", icon_files[name]
                )
            )

    # ------------------------------------------------------------------
    @staticmethod
    def _icon_path(value: str, base: Path) -> Path | None:
        p = Path(value).expanduser()
        if not p.is_absolute():
            p = base / p
        return p.resolve()

    @staticmethod
    def _decode_data(value: str) -> bytes | None:
        raw = value.strip()
        if raw.startswith("data:"):
            _, _, raw = raw.partition(",")
        try:
            return base64.b64decode(raw, validate=False)
        except ValueError, TypeError:
            return None

    def _make_entry(
        self,
        item_id: str,
        kind: str,
        icon_path: Path | None,
        icon_data: bytes | None,
    ) -> CatalogEntry:
        mod, path = self._split_id(item_id)
        return CatalogEntry(item_id, mod, path, kind, icon_path, icon_data)

    def _add_entry(self, item_id: str, kind: str, *, base: Path) -> None:
        self._store(self._make_entry(item_id, kind, None, None))

    # ------------------------------------------------------------------
    def get(self, item_id: str) -> CatalogEntry:
        entry = self.by_id.get(item_id) or self.fluids_by_id.get(item_id)
        if entry is not None:
            return entry
        mod, path = self._split_id(item_id)
        icon = None
        if self.icons_dir is not None:
            try:
                candidate = self.icons_dir / f"{mod}__{path}.png"
                if candidate.exists():
                    icon = candidate
            except OSError:
                icon = None
        return CatalogEntry(item_id, mod, path, "item", icon)

    def search_items(self) -> list[CatalogEntry]:
        return self.items

    def count(self) -> int:
        return len(self.items)
