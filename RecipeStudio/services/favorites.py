"""Persistent set of favourite item ids."""

from __future__ import annotations

import json
from pathlib import Path


class Favorites:
    def __init__(self, path: Path):
        self.path = path
        self._ids: set[str] = set()
        self.load()

    def load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self._ids = {str(x) for x in data if x}
        except OSError, json.JSONDecodeError:
            self._ids = set()

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(
                json.dumps(sorted(self._ids), indent=2) + "\n", encoding="utf-8"
            )
            tmp.replace(self.path)
        except OSError:
            pass

    def is_fav(self, item_id: str) -> bool:
        return item_id in self._ids

    def toggle(self, item_id: str) -> bool:
        if item_id in self._ids:
            self._ids.remove(item_id)
            result = False
        else:
            self._ids.add(item_id)
            result = True
        self.save()
        return result

    def all(self) -> set[str]:
        return set(self._ids)
