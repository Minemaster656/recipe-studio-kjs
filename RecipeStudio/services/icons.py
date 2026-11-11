"""PNG icon loading with generated placeholders."""

from __future__ import annotations

from pathlib import Path

from RecipeStudio.model.ingredient import Ingredient
from RecipeStudio.services.catalog import Catalog, CatalogEntry

try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk
except Exception:  # pragma: no cover - Pillow is a declared dependency
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]
    ImageFont = None  # type: ignore[assignment]
    ImageTk = None  # type: ignore[assignment]

_PALETTE = ["#7aa2f7", "#bb9af7", "#9ece6a", "#e0af68", "#f7768e", "#7dcfff", "#ff9e64"]

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
]


def _font(size: int):
    if ImageFont is None:
        return None
    for candidate in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


class IconCache:
    def __init__(self, icons_dir: Path):
        self.icons_dir = icons_dir
        self._cache: dict[tuple, object] = {}

    # ------------------------------------------------------------------
    def _placeholder(self, text: str, seed: str, size: int):
        key = ("placeholder", text, seed, size)
        if key in self._cache:
            return self._cache[key]
        if Image is None or ImageTk is None or ImageDraw is None:
            return None
        color = _PALETTE[hash(seed or text) % len(_PALETTE)]
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        pad = max(1, size // 16)
        draw.rounded_rectangle(
            (pad, pad, size - pad - 1, size - pad - 1),
            radius=max(3, size // 7),
            fill="#24283b",
            outline=color,
            width=max(1, size // 18),
        )
        font = _font(max(8, int(size * 0.46)))
        if font is not None:
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(
                ((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]),
                text,
                fill=color,
                font=font,
            )
        photo = ImageTk.PhotoImage(img)
        self._cache[key] = photo
        return photo

    def _from_path(self, path: Path, size: int):
        key = ("file", str(path), size)
        if key in self._cache:
            return self._cache[key]
        if Image is None or ImageTk is None:
            return None
        try:
            img = Image.open(path).convert("RGBA")
            if img.size != (size, size):
                resample = (
                    Image.Resampling.LANCZOS
                    if img.width > size
                    else Image.Resampling.NEAREST
                )
                img = img.resize((size, size), resample)
            photo = ImageTk.PhotoImage(img)
            self._cache[key] = photo
            return photo
        except Exception:
            return None

    # ------------------------------------------------------------------
    def get_entry(self, entry: CatalogEntry, size: int = 32):
        if entry.icon_path is not None:
            photo = self._from_path(entry.icon_path, size)
            if photo is not None:
                return photo
        if entry.kind == "fluid":
            return self._placeholder("≈", entry.id, size)
        return self._placeholder(self._initials(entry), entry.mod or entry.id, size)

    def get_ingredient(
        self,
        ing: Ingredient,
        catalog: Catalog,
        size: int = 32,
    ):
        if ing.is_empty:
            return None
        if ing.kind == "tag":
            return self._placeholder("#", ing.id, size)
        if ing.kind == "fluid":
            return self.get_entry(catalog.get(ing.id), size)
        return self.get_entry(catalog.get(ing.id), size)

    @staticmethod
    def _initials(entry: CatalogEntry) -> str:
        mod = entry.mod.strip()
        path = entry.path.strip()
        letters = ""
        if mod:
            letters += mod[0].upper()
        if path:
            letters += path[0].upper()
        return letters or "?"
