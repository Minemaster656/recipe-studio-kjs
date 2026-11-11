"""Item/fluid catalogue built from the icon export."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from RecipeStudio.config import Config


@dataclass(frozen=True)
class CatalogEntry:
    id: str
    mod: str
    path: str
    kind: str = "item"  # item | fluid
    icon_path: Path | None = None

    @property
    def full(self) -> str:
        return self.id


class Catalog:
    def __init__(self, config: Config):
        self.config = config
        self.icons_dir: Path = config.path_for("icons_dir")
        self.items: list[CatalogEntry] = []
        self.fluids: list[CatalogEntry] = []
        self.by_id: dict[str, CatalogEntry] = {}
        self.fluids_by_id: dict[str, CatalogEntry] = {}
        self._load()

    def _load(self) -> None:
        icon_files: dict[str, Path] = {}
        try:
            for p in self.icons_dir.iterdir():
                if p.is_file() and p.suffix.lower() == ".png":
                    icon_files[p.name] = p
        except OSError:
            icon_files = {}

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
            full = f"{mod}:{fluid_path}"
            entry = CatalogEntry(full, mod, fluid_path, "fluid", path)
            self.fluids.append(entry)
            self.fluids_by_id[full] = entry

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
            full = f"{mod}:{item_path}"
            if full in self.by_id:
                continue
            entry = CatalogEntry(full, mod, item_path, "item", icon_files[name])
            self.items.append(entry)
            self.by_id[full] = entry

        self.items.sort(key=lambda e: e.id.casefold())
        self.fluids.sort(key=lambda e: e.id.casefold())

    def get(self, item_id: str) -> CatalogEntry:
        entry = self.by_id.get(item_id) or self.fluids_by_id.get(item_id)
        if entry is not None:
            return entry
        if ":" in item_id:
            mod, path = item_id.split(":", 1)
        else:
            mod, path = "", item_id
        icon = None
        try:
            icon = self.icons_dir / f"{mod}__{path}.png"
            if not icon.exists():
                icon = None
        except OSError:
            icon = None
        return CatalogEntry(item_id, mod, path, "item", icon)

    def search_items(self) -> list[CatalogEntry]:
        return self.items

    def count(self) -> int:
        return len(self.items)
