#!/usr/bin/env python3
"""
Embed a list of "mod:id" strings through a local OpenAI-compatible
endpoint and store them in sqlite-vec.

Columns:
  full       TEXT  PRIMARY KEY  — the whole string ("mod:id")
  mod        TEXT               — the part before ':' (aux)
  id         TEXT               — the part after ':' (aux)
  embedding  FLOAT[N]           — vector from embeddinggemma2

Repeated runs do not create duplicates: already embedded strings are skipped.
"""

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

import sqlite_vec
from openai import OpenAI


# ----------------------------- утилиты -------------------------------------


def load_items(path: str) -> list[str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("ожидался JSON-массив строк")
    return data


def dedupe(seq: list[str]) -> list[str]:
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def split_full(full: str) -> tuple[str, str]:
    """'mod:id' -> ('mod', 'id'); if ':' is missing, mod='', id=full."""
    if ":" in full:
        mod, ident = full.split(":", 1)
        return mod, ident
    return "", full


# ----------------------------- клиент --------------------------------------


class Embedder:
    def __init__(self, base_url: str, model: str, api_key: str = "dummy"):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self.client.embeddings.create(model=self.model, input=texts)
        data = sorted(resp.data, key=lambda x: x.index)  # порядок = порядок input
        return [d.embedding for d in data]

    def embed_safe(self, texts: list[str]) -> list[list[float]]:
        """Try a batch first; on failure, fall back to one-at-a-time with retries."""
        try:
            return self.embed(texts)
        except Exception as e:
            print(
                f"  [warn] батч упал ({e}); переключаюсь на поштучно", file=sys.stderr
            )

        out: list[list[float]] = []
        for t in texts:
            for attempt in range(3):
                try:
                    out.append(self.embed([t])[0])
                    break
                except Exception as e:
                    print(f"  [retry {attempt + 1}/3] {e}", file=sys.stderr)
                    time.sleep(1.5 * (attempt + 1))
            else:
                raise RuntimeError(f"не удалось заэмбедить: {t[:80]!r}")
        return out


# ----------------------------- sqlite-vec ----------------------------------


def ensure_table(db: sqlite3.Connection, dim: int) -> None:
    db.execute(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS items USING vec0(
            full      TEXT PRIMARY KEY,
            embedding float[{dim}],
            +mod      TEXT,
            +id       TEXT
        )
    """)
    db.commit()


def open_db(path: str) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)
    return db


# ----------------------------- main ----------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", help="JSON-файл со списком строк 'mod:id'")
    ap.add_argument("-d", "--db", default="embeddings.db")
    ap.add_argument("-u", "--base-url", default="http://localhost:9931/v1")
    ap.add_argument("-m", "--model", default="embeddinggemma2")
    ap.add_argument("-b", "--batch-size", type=int, default=32)
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        help="обработать только N первых pending-строк (для отладки)",
    )
    args = ap.parse_args()

    items = dedupe(load_items(args.input))
    print(f"загружено уникальных строк: {len(items)}")
    if not items:
        print("нечего делать")
        return

    parsed = [(*split_full(it), it) for it in items]  # (mod, id, full)

    db = open_db(args.db)
    embedder = Embedder(args.base_url, args.model)

    # 1) определяем размерность эмбеддинга одним пробным запросом
    print("пробный запрос для определения размерности...")
    sample_emb = embedder.embed_safe([parsed[0][2]])[0]
    dim = len(sample_emb)
    print(f"dim = {dim}")

    ensure_table(db, dim)

    existing = {row[0] for row in db.execute("SELECT full FROM items").fetchall()}
    print(f"уже в базе: {len(existing)}")

    pending = [p for p in parsed if p[2] not in existing]
    print(f"к обработке: {len(pending)}")
    if args.limit is not None:
        pending = pending[: args.limit]
        print(f"  (--limit: {len(pending)})")

    # 2) пробную строку вставляем сразу — эмбеддинг уже есть
    if pending and pending[0][2] not in existing:
        mod, ident, full = pending[0]
        try:
            db.execute(
                "INSERT INTO items(full, embedding, mod, id) VALUES (?, ?, ?, ?)",
                (full, sqlite_vec.serialize_float32(sample_emb), mod, ident),
            )
            db.commit()
            existing.add(full)
            pending = pending[1:]
        except sqlite3.IntegrityError:
            pass

    # 3) основной батч-цикл
    total = len(pending)
    for i in range(0, total, args.batch_size):
        batch = pending[i : i + args.batch_size]
        embs = embedder.embed_safe([b[2] for b in batch])

        for (mod, ident, full), emb in zip(batch, embs):
            if full in existing:
                continue
            try:
                db.execute(
                    "INSERT INTO items(full, embedding, mod, id) VALUES (?, ?, ?, ?)",
                    (full, sqlite_vec.serialize_float32(emb), mod, ident),
                )
                existing.add(full)
            except sqlite3.IntegrityError:
                pass  # дубль — молча пропускаем
        db.commit()
        print(f"  {min(i + args.batch_size, total)}/{total}")

    count = db.execute("SELECT count(*) FROM items").fetchone()[0]
    print(f"готово. всего строк в базе: {count}")


if __name__ == "__main__":
    main()
