#!/usr/bin/env python3
"""
Semantic search library for embeddings.db.

Example:

    from emb_api import EmbeddingClient, SearchIndex

    client = EmbeddingClient("http://localhost:9931/v1", "embeddinggemma2")
    idx = SearchIndex("embeddings.db", client=client)

    hits = idx.search_text("black fan", limit=5)
    hits = idx.search_image("~/fan.jpg", limit=5)
    hits = idx.search_substring("fan", field="id", limit=5)
    hits = idx.search_fuzzy("fna", field="id", limit=5)

All search functions return list[Hit]. Low-level functions
(knn_by_vec, text_search, fuzzy_search, open_db) are also available.
"""

import base64
import difflib
import math
import sqlite3
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, Sequence

import httpx
import sqlite_vec
from openai import OpenAI
from schemafunc.schemafunc import add_schemafunc

DEFAULT_BASE_URL = "http://localhost:9931/v1"
DEFAULT_MODEL = "embeddinggemma2"
DEFAULT_DB = "embeddings.db"

FIELDS = ("mod", "id", "full")


# --------------------------------------------------------------- ошибки ----─


class EmbeddingError(RuntimeError):
    """Base embedding/search error."""


class ImageNotSupported(EmbeddingError):
    """The server does not support image embeddings."""


# -------------------------------------------------------------- результат ----─


@dataclass(frozen=True, slots=True)
class Hit:
    full: str
    mod: str
    id: str
    score: float  # 0..1

    def as_dict(self) -> dict:
        return {
            "full": self.full,
            "mod": self.mod,
            "id": self.id,
            "score": self.score,
        }


# --------------------------------------------------------------- инфра ----─


def open_db(path: str | Path) -> sqlite3.Connection:
    db = sqlite3.connect(str(path))
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)
    return db


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


def split_full(full: str) -> tuple[str, str]:
    """'mod:id' -> ('mod', 'id'); if ':' is missing, mod='', id=full."""
    if ":" in full:
        mod, ident = full.split(":", 1)
        return mod, ident
    return "", full


# ------------------------------------------------------------ картинки ----─

_MIME_BY_EXT = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "tif": "image/tiff",
    "tiff": "image/tiff",
}


def _sniff_mime(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"BM"):
        return "image/bmp"
    if data.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    return "application/octet-stream"


def image_to_data_url(
    source: str | Path | bytes | bytearray | memoryview,
    mime: str | None = None,
) -> str:
    """Convert a file path or raw bytes to a data: URL for /v1/embeddings."""
    if isinstance(source, (bytes, bytearray, memoryview)):
        data = bytes(source)
        mime = mime or _sniff_mime(data)
    else:
        path = Path(source).expanduser()
        data = path.read_bytes()
        mime = mime or _MIME_BY_EXT.get(path.suffix.lower().lstrip("."))
        mime = mime or _sniff_mime(data)
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


# микро-PNG 1×1 — если сервер пытается токенизировать как текст,
# это ~25 токенов, а не 90k; batch не взорвётся
_IMAGE_PROBE = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


# ------------------------------------------------------------- клиент ----─


class EmbeddingClient:
    """Wrapper around an OpenAI-compatible /v1/embeddings endpoint."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        api_key: str = "dummy",
        timeout: float = 120.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self._image_modes: dict[str, str | None] = {}

    # --- текст ---

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            r = self.client.embeddings.create(model=self.model, input=list(texts))
        except Exception as e:
            raise EmbeddingError(f"не удалось получить эмбеддинг: {e}") from e
        data = sorted(r.data, key=lambda d: d.index)
        return [list(d.embedding) for d in data]

    # --- изображения ---

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _probe_image(self, model: str) -> str | None:
        """Check once whether the server accepts images in /v1/embeddings."""
        if model in self._image_modes:
            return self._image_modes[model]

        url = f"{self.base_url}/embeddings"
        attempts = [
            # llama.cpp: input-элемент — объект с массивом content
            (
                "content",
                {
                    "model": model,
                    "input": [
                        {
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {"url": _IMAGE_PROBE},
                                }
                            ]
                        }
                    ],
                },
            ),
            (
                "image_url",
                {
                    "model": model,
                    "input": [
                        {"type": "image_url", "image_url": {"url": _IMAGE_PROBE}}
                    ],
                },
            ),
            (
                "text+image_url",
                {
                    "model": model,
                    "input": [
                        {"type": "text", "text": ""},
                        {"type": "image_url", "image_url": {"url": _IMAGE_PROBE}},
                    ],
                },
            ),
        ]
        for name, body in attempts:
            try:
                r = httpx.post(url, json=body, headers=self._headers(), timeout=20.0)
            except Exception:
                continue
            if r.status_code != 200:
                continue
            try:
                emb = r.json()["data"][0]["embedding"]
            except KeyError, IndexError, ValueError:
                continue
            if (
                isinstance(emb, list)
                and emb
                and all(isinstance(x, (int, float)) for x in emb[:3])
            ):
                self._image_modes[model] = name
                return name

        self._image_modes[model] = None
        return None

    def embed_image(
        self,
        source: str | Path | bytes | bytearray | memoryview,
        model: str | None = None,
    ) -> list[float] | None:
        """
        Return the image embedding, or None if the server does not support images.
        Raise EmbeddingError on network/HTTP errors.
        """
        model = model or self.model
        mode = self._probe_image(model)
        if not mode:
            return None

        data_url = image_to_data_url(source)
        url = f"{self.base_url}/embeddings"
        if mode == "content":
            # llama.cpp (--mmproj): content-массив внутри input-элемента
            body = {
                "model": model,
                "input": [
                    {"content": [{"type": "image_url", "image_url": {"url": data_url}}]}
                ],
            }
        elif mode == "image_url":
            body = {
                "model": model,
                "input": [{"type": "image_url", "image_url": {"url": data_url}}],
            }
        else:
            body = {
                "model": model,
                "input": [
                    {"type": "text", "text": ""},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }

        try:
            r = httpx.post(
                url, json=body, headers=self._headers(), timeout=self.timeout
            )
        except Exception as e:
            raise EmbeddingError(f"сетевая ошибка: {e}") from e

        if r.status_code != 200:
            try:
                err = r.json().get("error", {})
                msg = err.get("message") or r.text[:300]
            except Exception:
                msg = r.text[:300]
            low = msg.lower()
            if "prompt elements" in low or "too large to process" in low:
                return None
            raise EmbeddingError(f"HTTP {r.status_code}: {msg}")

        try:
            return list(r.json()["data"][0]["embedding"])
        except (KeyError, IndexError, ValueError) as e:
            raise EmbeddingError(f"некорректный ответ: {e}") from e


# --------------------------------------------------------------- поиск ----─


def _cos(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _row_to_hit(full, mod, ident, score) -> Hit:
    return Hit(full or "", mod or "", ident or "", max(0.0, min(1.0, score)))


def knn_by_vec(
    db: sqlite3.Connection,
    qvec: Sequence[float],
    limit: int = 10,
) -> list[Hit]:
    qblob = sqlite_vec.serialize_float32(list(qvec))
    try:
        cand = db.execute(
            "SELECT full, mod, id, distance, embedding FROM items "
            "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
            (qblob, max(limit * 4, limit + 10)),
        ).fetchall()
        scored = []
        for full, mod, ident, _d, blob in cand:
            vec = struct.unpack(f"<{len(blob) // 4}f", blob)
            scored.append((full, mod, ident, max(-1.0, min(1.0, _cos(qvec, vec)))))
        scored.sort(key=lambda x: -x[3])
        return [_row_to_hit(*row) for row in scored[:limit]]
    except sqlite3.OperationalError:
        rows = db.execute(
            "SELECT full, mod, id, distance FROM items "
            "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
            (qblob, limit),
        ).fetchall()
        return [
            _row_to_hit(f, m, i, max(-1.0, min(1.0, 1.0 - d * d / 2.0)))
            for f, m, i, d in rows
        ]


def _check_field(field: str) -> str:
    if field not in FIELDS:
        raise ValueError(f"поле должно быть одним из {FIELDS}, а не {field!r}")
    return field


def _subject(hit_fields: tuple[str, str, str], field: str) -> str:
    full, mod, ident = hit_fields
    return {"mod": mod, "id": ident, "full": full}[field]


def _pct_for_text(query: str, subject: str) -> float:
    q, s = query.lower(), subject.lower()
    if not q or not s:
        return 0.0
    if s == q:
        return 1.0
    r = difflib.SequenceMatcher(None, q, s).ratio()
    if q in s:
        r = max(r, 0.85)
    return max(0.0, min(1.0, r))


def text_search(
    db: sqlite3.Connection,
    query: str,
    field: str = "full",
    limit: int = 10,
) -> list[Hit]:
    field = _check_field(field)
    esc = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    like = f"%{esc.lower()}%"
    rows = db.execute(
        f"SELECT full, mod, id FROM items WHERE LOWER({field}) LIKE ? ESCAPE '\\' LIMIT ?",
        (like, limit * 20),
    ).fetchall()
    scored = [
        (f, m, i, _pct_for_text(query, _subject((f or "", m or "", i or ""), field)))
        for f, m, i in rows
    ]
    scored.sort(key=lambda x: -x[3])
    return [_row_to_hit(*row) for row in scored[:limit]]


def fuzzy_search(
    db: sqlite3.Connection,
    query: str,
    field: str = "full",
    limit: int = 10,
) -> list[Hit]:
    field = _check_field(field)
    rows = db.execute("SELECT full, mod, id FROM items").fetchall()
    q = query.lower()
    scored = []
    for f, m, i in rows:
        s = _subject((f or "", m or "", i or ""), field)
        if not s:
            continue
        sl = s.lower()
        ratio = difflib.SequenceMatcher(None, q, sl).ratio()
        if q in sl:
            ratio = max(ratio, 0.85 + 0.15 * (len(q) / max(1, len(sl))))
        scored.append((f, m, i, min(1.0, ratio)))
    scored.sort(key=lambda x: -x[3])
    return [_row_to_hit(*row) for row in scored[:limit]]


# ------------------------------------------------------------ индексация ----─


def _dedupe(items: Iterable[str]) -> list[str]:
    seen, out = set(), []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def index_texts(
    texts: Iterable[str],
    *,
    db_path: str | Path | sqlite3.Connection = DEFAULT_DB,
    client: EmbeddingClient | None = None,
    batch_size: int = 32,
    model: str | None = None,
) -> int:
    """
    Idempotently add "mod:id" strings to embeddings.db.
    Return the number of rows actually inserted.
    """
    items = _dedupe(texts)
    if not items:
        return 0

    client = client or EmbeddingClient(model=model or DEFAULT_MODEL)
    owns_db = not isinstance(db_path, sqlite3.Connection)
    db = open_db(db_path) if owns_db else db_path
    inserted = 0

    def insert(full: str, emb: Sequence[float]) -> bool:
        mod, ident = split_full(full)
        try:
            db.execute(
                "INSERT INTO items(full, embedding, mod, id) VALUES (?, ?, ?, ?)",
                (full, sqlite_vec.serialize_float32(list(emb)), mod, ident),
            )
        except sqlite3.IntegrityError:
            return False
        return True

    try:
        # размерность определяем до создания таблицы
        first = client.embed_text(items[0])
        first_full = items[0]
        ensure_table(db, len(first))

        existing = {row[0] for row in db.execute("SELECT full FROM items").fetchall()}
        pending = [x for x in items if x not in existing]
        if not pending:
            return 0

        # первый эмбеддинг уже есть — не тратим запрос повторно
        if pending[0] == first_full:
            if insert(first_full, first):
                inserted += 1
            db.commit()
            pending = pending[1:]

        for start in range(0, len(pending), batch_size):
            batch = pending[start : start + batch_size]
            try:
                embs = client.embed_texts(batch)
            except EmbeddingError:
                # батч не зашёл — по одной
                embs = [client.embed_text(x) for x in batch]

            for full, emb in zip(batch, embs):
                if insert(full, emb):
                    inserted += 1
            db.commit()
    finally:
        if owns_db:
            db.close()

    return inserted


# ------------------------------------------------------------- фасад ----─


class SearchIndex:
    """Convenient facade: database + client + all search modes."""

    def __init__(
        self,
        db_path: str | Path | sqlite3.Connection = DEFAULT_DB,
        client: EmbeddingClient | None = None,
        model: str | None = None,
    ):
        self._owns_db = not isinstance(db_path, sqlite3.Connection)
        self.db = open_db(db_path) if self._owns_db else db_path
        self.client = client or EmbeddingClient(model=model or DEFAULT_MODEL)

    # --- служебное ---

    def close(self) -> None:
        if self._owns_db:
            self.db.close()

    def __enter__(self) -> "SearchIndex":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def count(self) -> int:
        return self.db.execute("SELECT count(*) FROM items").fetchone()[0]

    def dimension(self) -> int | None:
        try:
            row = self.db.execute(
                "SELECT length(embedding) FROM items LIMIT 1"
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        return row[0] // 4 if row else None

    # --- поиск ---

    def knn(self, qvec: Sequence[float], limit: int = 10) -> list[Hit]:
        return knn_by_vec(self.db, qvec, limit)

    @add_schemafunc(ignore_args=("self",), require_all_params_in_doc=False)
    def search_text(self, query: str, limit: int = 10) -> list[Hit]:
        """Search records by the meaning of a text query using vector search.

        Use this method for semantic search: the query and records may not share
        words but may have the same meaning (for example, "black fan" will find
        `dndecor:black_large_fan`).

        Args:
            query: Natural-language search query.
            limit: Maximum number of results (default 10).

        Returns:
            A list of Hit objects sorted by descending score (0..1).
        """
        if not query.strip():
            raise ValueError("пустой запрос")
        return self.knn(self.client.embed_text(query), limit)

    @add_schemafunc(ignore_args=("self",), require_all_params_in_doc=False)
    def search_image(
        self,
        source: str,
        limit: int = 10,
        model: str | None = None,
    ) -> list[Hit]:
        """Search records similar to an image using multimodal embeddings.

        Args:
            source: Path to an image file. pathlib.Path and raw bytes are also
                accepted at runtime, but the LLM schema declares this as a string.
            limit: Maximum number of results (default 10).
            model: Optional embedding model name for images.

        Returns:
            A list of Hit objects sorted by descending score (0..1).

        Raises:
            ImageNotSupported: The server does not support image embeddings.
            EmbeddingError: A network error occurred or the dimensions do not match.
        """
        vec = self.client.embed_image(source, model=model)
        if vec is None:
            raise ImageNotSupported(
                "сервер не принимает изображения в /v1/embeddings "
                "(для llama.cpp нужны --embeddings и --mmproj)"
            )
        dim_db = self.dimension()
        if dim_db is not None and len(vec) != dim_db:
            raise EmbeddingError(
                f"размерность не совпадает: изображение → {len(vec)}, база → {dim_db}"
            )
        return self.knn(vec, limit)

    @add_schemafunc(ignore_args=("self",), require_all_params_in_doc=False)
    def search_substring(
        self,
        query: str,
        field: Literal["mod", "id", "full"] = "full",
        limit: int = 10,
    ) -> list[Hit]:
        """Search for an exact substring match in the selected field.

        Args:
            query: Substring to search for (case-insensitive).
            field: Field to search: "full", "mod", or "id".
            limit: Maximum number of results (default 10).

        Returns:
            A list of Hit objects sorted by descending score (0..1).
        """
        return text_search(self.db, query, field, limit)

    @add_schemafunc(ignore_args=("self",), require_all_params_in_doc=False)
    def search_fuzzy(
        self,
        query: str,
        field: Literal["mod", "id", "full"] = "full",
        limit: int = 10,
    ) -> list[Hit]:
        """Search records using fuzzy string matching.

        Useful for typos and imprecise names: "blak fan" will find
        `dndecor:black_large_fan`.

        Args:
            query: Imprecise query.
            field: Field to compare: "full", "mod", or "id".
            limit: Maximum number of results (default 10).

        Returns:
            A list of Hit objects sorted by descending score (0..1).
        """
        return fuzzy_search(self.db, query, field, limit)

    # --- индексация ---

    def index(self, texts: Iterable[str], batch_size: int = 32) -> int:
        return index_texts(
            texts,
            db_path=self.db,
            client=self.client,
            batch_size=batch_size,
        )


_SEARCH_METHODS = (
    SearchIndex.search_text,
    SearchIndex.search_image,
    SearchIndex.search_substring,
    SearchIndex.search_fuzzy,
)


def search_tool_schemas() -> list[dict]:
    """Return OpenAI-compatible schemas for all four search methods.

    Returns:
        A list of JSON schemas of the form {"type": "function", "function": {...}},
        ready for the tools parameter of the Chat Completions API.
    """
    return [method.schemafunc.openai.schema for method in _SEARCH_METHODS]
