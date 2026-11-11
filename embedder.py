#!/usr/bin/env python3
"""
Index item icons from an icon export folder into sqlite-vec.

Source filenames (x32 icons):
    modid__item_id.png
    fluid__modid__fluid_id.png   -> skipped

An NBT/component suffix is cut off:
    addictives__big_vape__{'addictives__fluid_type'__'nicotine'}.png
    -> mod=addictives, id=big_vape
Collisions after the cut are collapsed (deduplicated by full "mod:id").

The embedded text is the item id *without* the mod prefix.

Columns (same schema as the previous indexer):
  full       TEXT  PRIMARY KEY  — "mod:id"
  mod        TEXT               — the part before the first "__"
  id         TEXT               — the item id (NBT suffix stripped)
  embedding  FLOAT[N]           — vector from the embedding server

Repeated runs do not create duplicates: already indexed "mod:id" rows
are skipped.
"""

import argparse
import sqlite3
import sys
import time
from pathlib import Path

import sqlite_vec

from emb_api import EmbeddingClient, ensure_table, open_db

DEFAULT_ICONS_DIR = "icon-exports-x32"
DEFAULT_DB = "embeddings.db"
DEFAULT_BASE_URL = "http://localhost:9931/v1"
DEFAULT_MODEL = "embeddinggemma2"

FLUID_PREFIX = "fluid__"
NBT_MARKER = "__{"


# ----------------------------- файлы --------------------------------------


def parse_icon_name(path: Path) -> tuple[str, str] | None:
    """'modid__item_id.png' -> ('modid', 'item_id'); None if not an item icon."""
    if path.suffix.lower() != ".png":
        return None

    stem = path.stem
    if stem.startswith(FLUID_PREFIX):
        return None
    if "__" not in stem:
        return None

    mod, rest = stem.split("__", 1)
    # NBT/component suffix: cut at the first "__{" occurrence
    item = rest.split(NBT_MARKER, 1)[0]
    if not mod or not item:
        return None
    return mod, item


def collect_icons(icons_dir: Path) -> tuple[list[tuple[str, str, str]], int]:
    """Return ([(full, mod, item), ...], skipped_fluids) deduplicated by full."""
    if not icons_dir.is_dir():
        raise SystemExit(f"каталог не найден: {icons_dir}")

    unique: dict[str, tuple[str, str, str]] = {}
    fluids = 0
    ignored = 0

    for path in sorted(icons_dir.glob("*.png")):
        if path.stem.startswith(FLUID_PREFIX):
            fluids += 1
            continue
        parsed = parse_icon_name(path)
        if parsed is None:
            ignored += 1
            continue

        mod, item = parsed
        full = f"{mod}:{item}"
        # защита от коллизий после обрезки NBT: первая запись выигрывает
        unique.setdefault(full, (full, mod, item))

    if ignored:
        print(f"пропущено нераспознанных имён: {ignored}", file=sys.stderr)
    return list(unique.values()), fluids


# ----------------------------- клиент -------------------------------------


def embed_safe(client: EmbeddingClient, texts: list[str]) -> list[list[float]]:
    """Try a batch first; on failure, fall back to one-at-a-time with retries."""
    try:
        return client.embed_texts(texts)
    except Exception as e:
        print(f"  [warn] батч упал ({e}); переключаюсь на поштучно", file=sys.stderr)

    out: list[list[float]] = []
    for text in texts:
        for attempt in range(3):
            try:
                out.append(client.embed_text(text))
                break
            except Exception as e:
                print(f"  [retry {attempt + 1}/3] {e}", file=sys.stderr)
                time.sleep(1.5 * (attempt + 1))
        else:
            raise RuntimeError(f"не удалось заэмбедить: {text[:80]!r}")
    return out


# ----------------------------- main ----------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "icons",
        nargs="?",
        default=DEFAULT_ICONS_DIR,
        help=f"каталог с иконками (по умолчанию {DEFAULT_ICONS_DIR})",
    )
    ap.add_argument("-d", "--db", default=DEFAULT_DB)
    ap.add_argument("-u", "--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("-m", "--model", default=DEFAULT_MODEL)
    ap.add_argument("-b", "--batch-size", type=int, default=32)
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        help="обработать только N первых pending-строк (для отладки)",
    )
    args = ap.parse_args()

    entries, fluids = collect_icons(Path(args.icons))
    print(f"иконок-предметов: {len(entries)} (fluid пропущено: {fluids})")
    if not entries:
        print("нечего делать")
        return

    db = open_db(args.db)
    client = EmbeddingClient(args.base_url, args.model)

    table_exists = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='items'"
    ).fetchone()
    existing: set[str] = set()
    if table_exists:
        existing = {row[0] for row in db.execute("SELECT full FROM items").fetchall()}
    print(f"уже в базе: {len(existing)}")

    pending = [e for e in entries if e[0] not in existing]
    print(f"к обработке: {len(pending)}")
    if args.limit is not None:
        pending = pending[: args.limit]
        print(f"  (--limit: {len(pending)})")
    if not pending:
        print(f"готово. всего строк в базе: {len(existing)}")
        return

    # 1) пробный эмбеддинг: определяем размерность и сразу используем его
    print("пробный запрос для определения размерности...")
    first_emb = embed_safe(client, [pending[0][2]])[0]
    dim = len(first_emb)
    print(f"dim = {dim}")

    ensure_table(db, dim)

    # если таблица уже была — размерность должна совпадать
    if table_exists and existing:
        row = db.execute("SELECT length(embedding) FROM items LIMIT 1").fetchone()
        if row and row[0] // 4 != dim:
            raise SystemExit(
                f"размерность не совпадает: сервер → {dim}, база → {row[0] // 4}"
            )

    def insert(full: str, mod: str, item: str, emb: list[float]) -> bool:
        try:
            db.execute(
                "INSERT INTO items(full, embedding, mod, id) VALUES (?, ?, ?, ?)",
                (full, sqlite_vec.serialize_float32(emb), mod, item),
            )
        except sqlite3.IntegrityError:
            return False
        existing.add(full)
        return True

    inserted = 0
    # 2) первый эмбеддинг уже есть — не тратим запрос повторно
    full, mod, item = pending[0]
    if insert(full, mod, item, first_emb):
        inserted += 1
    db.commit()
    pending = pending[1:]

    # 3) основной батч-цикл
    total = len(pending)
    for i in range(0, total, args.batch_size):
        batch = pending[i : i + args.batch_size]
        embs = embed_safe(client, [b[2] for b in batch])

        for (full, mod, item), emb in zip(batch, embs):
            if insert(full, mod, item, emb):
                inserted += 1
        db.commit()
        print(f"  {min(i + args.batch_size, total)}/{total}")

    count = db.execute("SELECT count(*) FROM items").fetchone()[0]
    print(f"готово. добавлено: {inserted}, всего строк в базе: {count}")


if __name__ == "__main__":
    main()
