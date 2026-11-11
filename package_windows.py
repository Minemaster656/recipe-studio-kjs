"""Build a portable Windows zip for Recipe Studio.

Usage:
    python package_windows.py                 # app only
    python package_windows.py --with-data     # app + embeddings.db + icons
    python package_windows.py --out C:\\path\\RecipeStudio-Windows.zip

The resulting archive extracts into a single ``RecipeStudio-Windows`` folder.
Run ``start_recipe_studio.bat`` from that folder on Windows.
"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"

# Files that must sit next to the RecipeStudio package.
TOP_LEVEL_FILES = [
    ".python-version",
    "emb_api.py",
    "pyproject.toml",
    "README.md",
    "RecipeStudio",
    "src",
    "start_recipe_studio.bat",
    "TECHNICAL.md",
    "uv.lock",
    "WINDOWS.md",
]

# Small data file: kept in the app archive because it is cheap and config.json
# still references it.
SMALL_DATA_FILES = ["all_items.json"]

# Large data that the user may prefer to send separately.
OPTIONAL_DATA_FILES = ["embeddings.db"]
OPTIONAL_DATA_DIRS = ["icon-exports-x32"]

EXCLUDED_DIRS = {"__pycache__", ".git", ".venv", ".ruff_cache", ".pytest_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".tmp"}
EXCLUDED_NAMES = {"favorites.json"}


def iter_files(path: Path):
    if path.is_file():
        yield path
        return
    for child in sorted(path.rglob("*")):
        if not child.is_file():
            continue
        relative_parts = child.relative_to(ROOT).parts
        if any(part in EXCLUDED_DIRS for part in relative_parts):
            continue
        if child.suffix in EXCLUDED_SUFFIXES:
            continue
        if child.name in EXCLUDED_NAMES:
            continue
        yield child


def add_file(
    archive: zipfile.ZipFile,
    source: Path,
    archive_root: str,
    compresslevel: int,
) -> None:
    relative = source.relative_to(ROOT).as_posix()
    target = f"{archive_root}/{relative}"
    data = source.read_bytes()
    if source.suffix.lower() == ".bat":
        # cmd.exe is happier with CRLF, especially on older Windows builds.
        data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    info = zipfile.ZipInfo(target)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(
        info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=compresslevel
    )


def build(out_path: Path, with_data: bool) -> list[Path]:
    app_files: list[Path] = []
    for name in TOP_LEVEL_FILES:
        path = ROOT / name
        if not path.exists():
            raise FileNotFoundError(f"Missing required file: {path}")
        app_files.extend(iter_files(path))

    for name in SMALL_DATA_FILES:
        path = ROOT / name
        if path.exists():
            app_files.append(path)

    data_files: list[Path] = []
    if with_data:
        for name in OPTIONAL_DATA_FILES:
            path = ROOT / name
            if path.exists():
                data_files.append(path)
        for name in OPTIONAL_DATA_DIRS:
            path = ROOT / name
            if path.exists():
                data_files.extend(iter_files(path))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    archive_root = "RecipeStudio-Windows"

    with zipfile.ZipFile(
        out_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as zf:
        for path in app_files + data_files:
            add_file(zf, path, archive_root, compresslevel=9)

    print(f"Created {out_path} ({out_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"  app files:  {len(app_files)}")
    print(f"  data files: {len(data_files)}")

    if not with_data:
        missing = [
            name
            for name in OPTIONAL_DATA_FILES + OPTIONAL_DATA_DIRS
            if not (ROOT / name).exists()
        ]
        print("Data not included. Send these separately and place them at the")
        print(f"root of the extracted {archive_root} folder:")
        for name in OPTIONAL_DATA_FILES + OPTIONAL_DATA_DIRS:
            print(f"  - {name}")
        if missing:
            print("  (not found locally: " + ", ".join(missing) + ")")
    return app_files + data_files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--with-data",
        action="store_true",
        help="also add embeddings.db and icon-exports-x32 to the archive",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DIST / "RecipeStudio-Windows.zip",
        help="output zip path (default: dist/RecipeStudio-Windows.zip)",
    )
    args = parser.parse_args()
    build(args.out.resolve(), args.with_data)


if __name__ == "__main__":
    main()
