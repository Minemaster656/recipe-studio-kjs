#!/usr/bin/env python3
"""
Интерактивный поиск по embeddings.db:

  1) векторный поиск (текст)
  2) текстовый поиск (substring, LIKE)
  3) нечёткий (fuzzy) поиск
  4) векторный поиск по изображению (multimodal embedding)
  0) выход
"""

import argparse
import base64
import difflib
import math
import os
import shutil
import sqlite3
import struct
import subprocess
from pathlib import Path

import httpx
import sqlite_vec
from openai import OpenAI

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt
from rich.text import Text
from rich import box


# --------------------------------------------------------- Tokyo Night ----─

TN_BG = "#1a1b26"
TN_FG = "#c0caf5"
TN_BLUE = "#7aa2f7"
TN_CYAN = "#7dcfff"
TN_PURPLE = "#bb9af7"
TN_GREEN = "#9ece6a"
TN_YELLOW = "#e0af68"
TN_RED = "#f7768e"
TN_DIM = "#565f89"
TN_DARK = "#3b4261"

console = Console(style=f"{TN_FG} on {TN_BG}", color_system="truecolor")

HL_TEXT = f"bold underline {TN_YELLOW}"  # непрерывное совпадение
HL_FUZZY = f"bold {TN_YELLOW}"  # разрозненные буквы


# ------------------------------------------------------------- градиент ----─


def _lerp(a: str, b: str, t: float) -> str:
    ar, ag, ab = int(a[1:3], 16), int(a[3:5], 16), int(a[5:7], 16)
    br, bg, bb = int(b[1:3], 16), int(b[3:5], 16), int(b[5:7], 16)
    return "#{:02x}{:02x}{:02x}".format(
        round(ar + (br - ar) * t),
        round(ag + (bg - ag) * t),
        round(ab + (bb - ab) * t),
    )


def gradient(t: float) -> str:
    t = max(0.0, min(1.0, t))
    return (
        _lerp(TN_BLUE, TN_CYAN, t * 2)
        if t < 0.5
        else _lerp(TN_CYAN, TN_PURPLE, (t - 0.5) * 2)
    )


# ---------------------------------------------------- подсветка запроса ----─


def render_marked(text: str, query: str, color: str, fuzzy: bool = False) -> Text:
    out = Text()
    if not text:
        return out
    if not query:
        out.append(text, style=color)
        return out

    if not fuzzy:
        lt, lq = text.lower(), query.lower()
        pos = 0
        while True:
            i = lt.find(lq, pos)
            if i < 0:
                out.append(text[pos:], style=color)
                break
            out.append(text[pos:i], style=color)
            out.append(text[i : i + len(query)], style=HL_TEXT)
            pos = i + len(query)
        return out

    # fuzzy: подсвечиваем буквы, совпавшие по порядку
    sm = difflib.SequenceMatcher(None, query.lower(), text.lower())
    pos = 0
    for _i, j, n in sm.get_matching_blocks():
        if n == 0:
            continue
        if j > pos:
            out.append(text[pos:j], style=color)
        out.append(text[j : j + n], style=HL_FUZZY)
        pos = j + n
    if pos < len(text):
        out.append(text[pos:], style=color)
    return out


# --------------------------------------------------------------- инфра ----─


def open_db(path: str) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)
    return db


# микро-PNG 1×1 — если сервер пытается токенизировать как текст,
# это ~25 токенов, а не 90k; batch не взорвётся
_IMAGE_PROBE = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


class Embedder:
    def __init__(self, base_url: str, model: str, api_key: str = "dummy"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self._image_mode = None  # None=не пробовали, False=нет, str=формат

    def embed_one(self, text: str) -> list[float]:
        r = self.client.embeddings.create(model=self.model, input=[text])
        return list(r.data[0].embedding)

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _probe_image(self, model: str):
        """Один раз проверяем, понимает ли сервер картинки в /v1/embeddings."""
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
                return name
        return None

    def embed_image(self, path: str, image_model: str | None = None):
        """
        Возвращает list[float] или None если сервер не поддерживает картинки.
        Бросает RuntimeError с осмысленным сообщением при HTTP-ошибке.
        """
        model = image_model or self.model

        if self._image_mode is None:
            self._image_mode = self._probe_image(model) or False
        if not self._image_mode:
            return None

        data_url = image_to_data_url(path)
        url = f"{self.base_url}/embeddings"
        if self._image_mode == "content":
            # llama.cpp (--mmproj): content-массив внутри input-элемента
            body = {
                "model": model,
                "input": [
                    {"content": [{"type": "image_url", "image_url": {"url": data_url}}]}
                ],
            }
        elif self._image_mode == "image_url":
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
            r = httpx.post(url, json=body, headers=self._headers(), timeout=120.0)
        except Exception as e:
            raise RuntimeError(f"сетевая ошибка: {e}")

        if r.status_code != 200:
            try:
                err = r.json().get("error", {})
                msg = err.get("message") or r.text[:300]
            except Exception:
                msg = r.text[:300]
            low = msg.lower()
            if "prompt elements" in low or "too large to process" in low:
                self._image_mode = False  # кешируем «не умеет»
                return None
            raise RuntimeError(f"HTTP {r.status_code}: {msg}")

        try:
            return list(r.json()["data"][0]["embedding"])
        except (KeyError, IndexError, ValueError) as e:
            raise RuntimeError(f"некорректный ответ: {e}")


def image_to_data_url(path: str) -> str:
    p = Path(path)
    ext = p.suffix.lower().lstrip(".")
    mime = {
        "jpg": "jpeg",
        "jpeg": "jpeg",
        "png": "png",
        "webp": "webp",
        "gif": "gif",
        "bmp": "bmp",
    }.get(ext, "png")
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:image/{mime};base64,{data}"


# ------------------------------------------------------------ картинки ----─


def _has_kitty_graphics() -> bool:
    return (
        os.environ.get("KITTY_WINDOW_ID") is not None
        or os.environ.get("TERM_PROGRAM") in ("kitty", "WezTerm", "ghostty")
        or "kitty" in os.environ.get("TERM", "").lower()
    )


def try_display_image(path: str):
    """Возвращает 'kitty' | 'chafa' | None."""
    if _has_kitty_graphics() and shutil.which("kitten"):
        try:
            subprocess.run(["kitten", "icat", "--clear", path], check=False, timeout=15)
            return "kitty"
        except Exception:
            pass
    if shutil.which("chafa"):
        try:
            subprocess.run(["chafa", "-s", "60x30", path], check=False, timeout=15)
            return "chafa"
        except Exception:
            pass
    return None


# --------------------------------------------------------------- поиск ----─


def _cos(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def knn_by_vec(db, qvec, limit):
    qblob = sqlite_vec.serialize_float32(qvec)
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
        return scored[:limit]
    except sqlite3.OperationalError:
        rows = db.execute(
            "SELECT full, mod, id, distance FROM items "
            "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
            (qblob, limit),
        ).fetchall()
        return [
            (f, m, i, max(-1.0, min(1.0, 1.0 - d * d / 2.0))) for f, m, i, d in rows
        ]


def _pick_col(field):
    return field if field in ("mod", "id", "full") else "full"


def _subject(full, mod, ident, field):
    return {"mod": mod or "", "id": ident or "", "full": full or ""}[field]


def _pct_for_text(query, subject):
    q, s = query.lower(), subject.lower()
    if not q or not s:
        return 0.0
    if s == q:
        return 1.0
    r = difflib.SequenceMatcher(None, q, s).ratio()
    if q in s:
        r = max(r, 0.85)
    return max(0.0, min(1.0, r))


def text_search(db, query, field, limit):
    col = _pick_col(field)
    like = f"%{query.lower()}%"
    rows = db.execute(
        f"SELECT full, mod, id FROM items WHERE LOWER({col}) LIKE ? LIMIT ?",
        (like, limit * 20),
    ).fetchall()
    scored = [
        (f, m, i, _pct_for_text(query, _subject(f, m, i, field))) for f, m, i in rows
    ]
    scored.sort(key=lambda x: -x[3])
    return scored[:limit]


def fuzzy_search(db, query, field, limit):
    rows = db.execute("SELECT full, mod, id FROM items").fetchall()
    q = query.lower()
    scored = []
    for f, m, i in rows:
        s = _subject(f, m, i, field)
        if not s:
            continue
        sl = s.lower()
        ratio = difflib.SequenceMatcher(None, q, sl).ratio()
        if q in sl:
            ratio = max(ratio, 0.85 + 0.15 * (len(q) / max(1, len(sl))))
        scored.append((f, m, i, min(1.0, ratio)))
    scored.sort(key=lambda x: -x[3])
    return scored[:limit]


# --------------------------------------------------------------- показ ----─


def show_results(title, rows, query, highlight=False, fuzzy=False):
    if not rows:
        console.print(
            Panel(
                f"[{TN_YELLOW}]ничего не найдено[/]", title=title, border_style=TN_DARK
            )
        )
        return

    table = Table(
        title=title,
        box=box.ROUNDED,
        border_style=TN_DARK,
        header_style=f"bold {TN_CYAN}",
        title_style=f"bold {TN_PURPLE}",
        pad_edge=False,
    )
    table.add_column("#", justify="right", width=3, style=TN_DIM)
    table.add_column("full", overflow="fold")
    table.add_column("mod", overflow="fold")
    table.add_column("id", overflow="fold")
    table.add_column("score", justify="right", width=8)

    n = len(rows)
    for i, (full, mod, ident, score) in enumerate(rows):
        t = 1.0 if n == 1 else 1.0 - i / (n - 1)
        col = gradient(t)

        if highlight:
            full_t = render_marked(full or "", query, col, fuzzy=fuzzy)
            mod_t = render_marked(mod or "", query, col, fuzzy=fuzzy)
            id_t = render_marked(ident or "", query, col, fuzzy=fuzzy)
        else:
            full_t = Text(full or "", style=col)
            mod_t = Text(mod or "", style=col)
            id_t = Text(ident or "", style=col)

        table.add_row(
            Text(str(i + 1), style=TN_DIM),
            full_t,
            mod_t,
            id_t,
            Text(f"{score * 100:5.1f}%", style=f"bold {col}"),
        )
    console.print(table)


# --------------------------------------------------------------- меню ----─


def ask_field():
    return Prompt.ask(
        f"[{TN_CYAN}]поле[/]", choices=["mod", "id", "full"], default="full"
    )


def do_vector(db, emb):
    q = Prompt.ask(f"[{TN_CYAN}]фраза[/]").strip()
    if not q:
        return
    lim = IntPrompt.ask(f"[{TN_CYAN}]лимит[/]", default=10)
    with console.status(f"[{TN_CYAN}]эмбеддинг + KNN…[/]"):
        rows = knn_by_vec(db, emb.embed_one(q), lim)
    show_results(f"[bold]векторный поиск:[/] {q!r}", rows, q)


def do_text(db):
    f = ask_field()
    q = Prompt.ask(f"[{TN_CYAN}]подстрока в {f}[/]").strip()
    if not q:
        return
    lim = IntPrompt.ask(f"[{TN_CYAN}]лимит[/]", default=10)
    rows = text_search(db, q, f, lim)
    show_results(
        f"[bold]текстовый поиск:[/] {q!r} в [magenta]{f}[/]",
        rows,
        q,
        highlight=True,
        fuzzy=False,
    )


def do_fuzzy(db):
    f = ask_field()
    q = Prompt.ask(f"[{TN_CYAN}]нечёткий запрос по {f}[/]").strip()
    if not q:
        return
    lim = IntPrompt.ask(f"[{TN_CYAN}]лимит[/]", default=10)
    with console.status(f"[{TN_CYAN}]fuzzy-скан…[/]"):
        rows = fuzzy_search(db, q, f, lim)
    show_results(
        f"[bold]fuzzy-поиск:[/] {q!r} в [magenta]{f}[/]",
        rows,
        q,
        highlight=True,
        fuzzy=True,
    )


def do_image(db, emb, image_model):
    path = Prompt.ask(f"[{TN_CYAN}]путь к изображению[/]").strip().strip('"').strip("'")
    if not path or not os.path.isfile(path):
        console.print(f"[{TN_YELLOW}]файл не найден[/]")
        return

    how = try_display_image(path)
    if how is None:
        console.print(
            f"[{TN_DIM}]показать изображение не могу (нет kitty graphics / chafa)[/]"
        )
    else:
        console.print(f"[{TN_DIM}]показано через {how}[/]")

    lim = IntPrompt.ask(f"[{TN_CYAN}]лимит[/]", default=10)

    with console.status(f"[{TN_CYAN}]эмбеддинг изображения…[/]"):
        try:
            vec = emb.embed_image(path, image_model)
        except RuntimeError as e:
            console.print(Panel(f"[{TN_RED}]ошибка:[/] {e}", border_style=TN_DARK))
            return

    if vec is None:
        console.print(
            Panel(
                f"[{TN_YELLOW}]обработка изображений недоступна[/]\n"
                f"[{TN_DIM}]сервер не принимает изображения в /v1/embeddings. "
                f"Для llama.cpp запусти его с --embeddings и --mmproj.[/]\n"
                f"[{TN_DIM}]альтернатива — мультимодальный embedding-сервер "
                f"(vLLM + CLIP/jina-clip, infinity, tei).[/]",
                border_style=TN_DARK,
            )
        )
        return

    dim_db = None
    try:
        row = db.execute("SELECT length(embedding) FROM items LIMIT 1").fetchone()
        if row:
            dim_db = row[0] // 4
    except sqlite3.OperationalError:
        pass
    if dim_db is not None and len(vec) != dim_db:
        console.print(
            Panel(
                f"[{TN_RED}]размерность не совпадает[/]: "
                f"изображение → {len(vec)}, база → {dim_db}",
                border_style=TN_DARK,
            )
        )
        return

    try:
        rows = knn_by_vec(db, vec, lim)
    except sqlite3.OperationalError as e:
        console.print(f"[{TN_RED}]ошибка поиска:[/] {e}")
        return

    show_results(f"[bold]поиск по изображению:[/] {Path(path).name}", rows, "")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-d", "--db", default="embeddings.db")
    ap.add_argument("-u", "--base-url", default="http://localhost:9931/v1")
    ap.add_argument("-m", "--model", default="embeddinggemma2")
    ap.add_argument(
        "--image-model",
        default=None,
        help="модель для эмбеддинга изображений (по умолчанию -m)",
    )
    args = ap.parse_args()

    db = open_db(args.db)
    emb = Embedder(args.base_url, args.model)

    total = db.execute("SELECT count(*) FROM items").fetchone()[0]
    console.print(
        Panel(
            f"[bold {TN_CYAN}]Embedding search[/] — "
            f"[{TN_GREEN}]{args.db}[/]  "
            f"([{TN_YELLOW}]{total}[/] записей, "
            f"[{TN_PURPLE}]{args.model}[/])",
            box=box.ROUNDED,
            border_style=TN_BLUE,
        )
    )

    while True:
        console.print()
        console.print(f"[bold {TN_CYAN}]1[/] — векторный поиск (текст)")
        console.print(f"[bold {TN_CYAN}]2[/] — текстовый поиск (substring)")
        console.print(f"[bold {TN_CYAN}]3[/] — нечёткий (fuzzy) поиск")
        console.print(f"[bold {TN_CYAN}]4[/] — векторный поиск по изображению")
        console.print(f"[bold {TN_CYAN}]0[/] — выход")
        try:
            choice = Prompt.ask(f"[{TN_CYAN}]выбор[/]", default="1")
            if choice == "1":
                do_vector(db, emb)
            elif choice == "2":
                do_text(db)
            elif choice == "3":
                do_fuzzy(db)
            elif choice == "4":
                do_image(db, emb, args.image_model)
            elif choice in ("0", "q", "quit", "exit"):
                break
            else:
                console.print(f"[{TN_RED}]не понял[/]")
        except KeyboardInterrupt:
            console.print(f"\n[{TN_DIM}]Ctrl-C[/]")
        except EOFError:
            break
        except Exception as e:
            console.print(f"[{TN_RED}]ошибка:[/] {e}")


if __name__ == "__main__":
    main()
