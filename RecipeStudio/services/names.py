"""Resolve human readable names from mod lang files, with a cache."""

from __future__ import annotations

import glob
import json
import zipfile
from pathlib import Path

from RecipeStudio.config import Config, SCRIPTS_DIR


def prettify(item_id: str) -> str:
    if not item_id:
        return ""
    raw = item_id
    if raw.startswith("#"):
        raw = raw[1:]
    path = raw.split(":", 1)[-1]
    words = path.replace("-", " ").replace("_", " ").replace("/", " ").split()
    name = " ".join(w[:1].upper() + w[1:] for w in words)
    return name or item_id


class NameResolver:
    def __init__(self, config: Config):
        self.config = config
        self.cache_path = config.path_for("names_cache")
        self.names: dict[str, str] = {}
        self.signature: list[list] = []
        self._load_cache()

    # ------------------------------------------------------------------
    def _load_cache(self) -> None:
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                names = data.get("names")
                if isinstance(names, dict):
                    self.names = {str(k): str(v) for k, v in names.items()}
                sig = data.get("signature")
                if isinstance(sig, list):
                    self.signature = sig
        except OSError, json.JSONDecodeError:
            self.names = {}
            self.signature = []

    def _current_signature(self) -> list[list]:
        paths: list[Path] = []
        mods_dir = self.config.path_for("mods_dir")
        try:
            paths.extend(sorted(mods_dir.glob("*.jar")))
        except OSError:
            pass
        kubejs = self.config.path_for("kubejs_dir")
        try:
            paths.extend(sorted((kubejs / "assets").glob("*/lang/en_us.json")))
        except OSError:
            pass
        for pattern in self.config.get("extra_lang_jars", []) or []:
            for raw in glob.glob(str(SCRIPTS_DIR / str(pattern))):
                p = Path(raw)
                if p.is_file():
                    paths.append(p)
        sig: list[list] = []
        seen: set[str] = set()
        for p in paths:
            try:
                st = p.stat()
            except OSError:
                continue
            key = str(p)
            if key in seen:
                continue
            seen.add(key)
            sig.append([key, int(st.st_mtime), st.st_size])
        sig.sort(key=lambda row: row[0])
        return sig

    def build_if_needed(self, force: bool = False) -> bool:
        """Build the cache when jars changed.  Returns True when rebuilt."""
        sig = self._current_signature()
        if not force and self.names and sig == self.signature:
            return False
        self.build()
        return True

    def build(self) -> None:
        names: dict[str, str] = {}
        paths: list[Path] = []
        try:
            paths.extend(sorted(self.config.path_for("mods_dir").glob("*.jar")))
        except OSError:
            pass

        kubejs = self.config.path_for("kubejs_dir")
        try:
            for p in sorted((kubejs / "assets").glob("*/lang/en_us.json")):
                self._read_lang_file(p, names)
        except OSError:
            pass

        for pattern in self.config.get("extra_lang_jars", []) or []:
            for raw in glob.glob(str(SCRIPTS_DIR / str(pattern))):
                p = Path(raw)
                if p.is_file():
                    paths.append(p)

        seen: set[str] = set()
        for jar in paths:
            key = str(jar)
            if key in seen:
                continue
            seen.add(key)
            self._read_jar(jar, names)

        self.names = names
        self.signature = self._current_signature()
        self._save_cache()

    def _save_cache(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"signature": self.signature, "names": self.names}
            tmp = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
            tmp.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            tmp.replace(self.cache_path)
        except OSError:
            pass

    # ------------------------------------------------------------------
    def _read_lang_file(self, path: Path, names: dict[str, str]) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except OSError, json.JSONDecodeError:
            return
        self._merge_lang(data, names)

    def _read_jar(self, jar: Path, names: dict[str, str]) -> None:
        try:
            with zipfile.ZipFile(jar) as zf:
                for member in zf.namelist():
                    if not member.startswith("assets/"):
                        continue
                    if not member.endswith("/lang/en_us.json"):
                        continue
                    try:
                        data = json.loads(zf.read(member).decode("utf-8"))
                    except KeyError, UnicodeDecodeError, json.JSONDecodeError, OSError:
                        continue
                    self._merge_lang(data, names)
        except OSError, zipfile.BadZipFile:
            pass

    @staticmethod
    def _merge_lang(data: dict, names: dict[str, str]) -> None:
        if not isinstance(data, dict):
            return
        for key, value in data.items():
            if not isinstance(key, str) or not isinstance(value, str):
                continue
            parts = key.split(".")
            if len(parts) < 3:
                continue
            prefix = parts[0]
            if prefix not in ("item", "block", "fluid_type"):
                continue
            mod = parts[1]
            path = ".".join(parts[2:])
            names.setdefault(f"{mod}:{path}", value)

    # ------------------------------------------------------------------
    def get(self, item_id: str) -> str:
        if not item_id:
            return ""
        exact = self.names.get(item_id)
        if exact:
            return exact
        return prettify(item_id)
