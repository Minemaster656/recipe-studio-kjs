"""The single integration point with ``emb_api``.

Nothing else in Recipe Studio imports ``emb_api`` or opens ``embeddings.db``.
This makes the editor portable: only this module and the config need to know
where the vector database lives.
"""

from __future__ import annotations

import difflib
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from RecipeStudio.config import Config, SCRIPTS_DIR
from RecipeStudio.services.catalog import Catalog, CatalogEntry


class SearchUnavailable(RuntimeError):
    pass


class SearchMode:
    SUBSTRING = "S"
    FUZZY = "F"
    EMBEDDINGS = "E"
    ALL = (SUBSTRING, FUZZY, EMBEDDINGS)
    LABELS = {
        SUBSTRING: "Substring (full id)",
        FUZZY: "Fuzzy",
        EMBEDDINGS: "Embeddings",
    }


@dataclass
class SearchHit:
    entry: CatalogEntry
    score: float
    source: str = ""


class SearchGateway:
    def __init__(self, config: Config, catalog: Catalog):
        self.config = config
        self.catalog = catalog
        self._api = None
        self._api_error: Exception | None = None

    # ------------------------------------------------------------------
    def _load_api(self):
        if self._api is not None:
            return self._api
        if self._api_error is not None:
            return None
        try:
            if str(SCRIPTS_DIR) not in sys.path:
                sys.path.insert(0, str(SCRIPTS_DIR))
            from emb_api import EmbeddingClient, SearchIndex  # type: ignore

            self._api = (EmbeddingClient, SearchIndex)
        except Exception as exc:  # pragma: no cover - optional integration
            self._api_error = exc
            return None
        return self._api

    def _open_index(self, *, embeddings: bool = False):
        api = self._load_api()
        if api is None:
            raise SearchUnavailable(f"emb_api is unavailable: {self._api_error}")
        EmbeddingClient, SearchIndex = api
        db = self.config.path_for("database")
        if not db.exists():
            raise SearchUnavailable(f"Embedding database not found: {db}")
        client = None
        if embeddings:
            client = EmbeddingClient(
                base_url=str(self.config.get("base_url")),
                model=str(self.config.get("embedding_model")),
            )
        return SearchIndex(db_path=db, client=client)

    # ------------------------------------------------------------------
    def search(
        self, query: str, mode: str, limit: int | None = None
    ) -> list[SearchHit]:
        query = (query or "").strip()
        if not query:
            return []
        limit = int(limit or self.config.get("search_limit", 500))
        if mode == SearchMode.EMBEDDINGS:
            return self._embedding_search(query, limit)
        if mode == SearchMode.FUZZY:
            return self._fuzzy_search(query, limit)
        return self._substring_search(query, limit)

    # ------------------------------------------------------------------
    def _substring_search(self, query: str, limit: int) -> list[SearchHit]:
        hits = self._local_substring(query, limit)
        try:
            hits.extend(self._db_hits(query, limit, fuzzy=False))
        except SearchUnavailable:
            pass
        except Exception:
            pass
        return self._merge(hits, limit)

    def _fuzzy_search(self, query: str, limit: int) -> list[SearchHit]:
        hits = self._local_fuzzy(query, limit)
        try:
            hits.extend(self._db_hits(query, limit, fuzzy=True))
        except SearchUnavailable:
            pass
        except Exception:
            pass
        return self._merge(hits, limit)

    def _embedding_search(self, query: str, limit: int) -> list[SearchHit]:
        image_path = self._image_path(query)
        idx = None
        try:
            idx = self._open_index(embeddings=True)
            if image_path is not None:
                raw = idx.search_image(str(image_path), limit=limit)
            else:
                raw = idx.search_text(query, limit=limit)
        except SearchUnavailable:
            raise
        except Exception as exc:
            raise SearchUnavailable(f"Embedding search failed: {exc}") from exc
        finally:
            if idx is not None:
                try:
                    idx.close()
                except Exception:
                    pass

        hits: list[SearchHit] = []
        for item in raw:
            full = getattr(item, "full", None)
            if not full:
                continue
            hits.append(
                SearchHit(
                    self.catalog.get(full),
                    float(getattr(item, "score", 0.0)),
                    "embeddings",
                )
            )
        hits.sort(key=lambda h: (-h.score, len(h.entry.id), h.entry.id))
        return hits[:limit]

    # ------------------------------------------------------------------
    def _db_hits(self, query: str, limit: int, *, fuzzy: bool) -> list[SearchHit]:
        idx = None
        try:
            idx = self._open_index()
        except SearchUnavailable:
            raise
        try:
            raw = []
            for variant in self._variants(query):
                try:
                    if fuzzy:
                        raw.extend(idx.search_fuzzy(variant, field="full", limit=limit))
                    else:
                        raw.extend(
                            idx.search_substring(variant, field="full", limit=limit)
                        )
                except TypeError:
                    # Older emb_api versions may not accept ``field`` as kwarg.
                    if fuzzy:
                        raw.extend(idx.search_fuzzy(variant, limit=limit))
                    else:
                        raw.extend(idx.search_substring(variant, limit=limit))
        finally:
            try:
                idx.close()
            except Exception:
                pass
        hits = []
        for item in raw:
            full = getattr(item, "full", None)
            if not full:
                continue
            hits.append(
                SearchHit(
                    self.catalog.get(full), float(getattr(item, "score", 0.0)), "db"
                )
            )
        return hits

    # ------------------------------------------------------------------
    def _local_substring(self, query: str, limit: int) -> list[SearchHit]:
        q = self._norm(query)
        tokens = [t for t in q.split() if t]
        if not tokens:
            return []
        result: list[SearchHit] = []
        for entry in self.catalog.items:
            target = self._norm(entry.id)
            if not all(t in target for t in tokens):
                continue
            score = 0.58 + 0.34 * (len(q) / max(1, len(target)))
            if q in target:
                score = 0.93
            if target.endswith(q):
                score = 0.96
            result.append(SearchHit(entry, min(score, 0.99), "local"))
        result.sort(key=lambda h: (-h.score, len(h.entry.id), h.entry.id))
        return result[: max(limit * 2, limit)]

    def _local_fuzzy(self, query: str, limit: int) -> list[SearchHit]:
        q = self._norm(query)
        result: list[SearchHit] = []
        for entry in self.catalog.items:
            target = self._norm(entry.id)
            ratio = difflib.SequenceMatcher(None, q, target).ratio()
            if q and q in target:
                ratio = max(ratio, 0.86 + 0.1 * (len(q) / max(1, len(target))))
            if ratio >= 0.34:
                result.append(SearchHit(entry, min(ratio, 0.99), "local"))
        result.sort(key=lambda h: (-h.score, len(h.entry.id), h.entry.id))
        return result[: max(limit * 2, limit)]

    # ------------------------------------------------------------------
    def _merge(self, hits: list[SearchHit], limit: int) -> list[SearchHit]:
        merged: dict[str, SearchHit] = {}
        for hit in hits:
            prev = merged.get(hit.entry.id)
            if prev is None or hit.score > prev.score:
                merged[hit.entry.id] = hit
        result = list(merged.values())
        result.sort(key=lambda h: (-h.score, len(h.entry.id), h.entry.id))
        return result[:limit]

    @staticmethod
    def _norm(value: str) -> str:
        return " ".join(
            value.lower().replace("_", " ").replace("-", " ").replace("/", " ").split()
        )

    @staticmethod
    def _variants(query: str) -> list[str]:
        base = " ".join(query.strip().split())
        variants = [
            base,
            base.replace(" ", "_"),
            base.replace("_", " "),
            base.replace("-", " "),
        ]
        out: list[str] = []
        for v in variants:
            if v and v not in out:
                out.append(v)
        return out

    @staticmethod
    def _image_path(query: str) -> Path | None:
        raw = query.strip().strip("'\"")
        if not raw:
            return None
        suffix = Path(raw).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}:
            return None
        path = Path(os.path.expanduser(raw))
        if path.is_file():
            return path
        return None
