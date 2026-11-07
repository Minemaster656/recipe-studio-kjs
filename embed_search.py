#!/usr/bin/env python3
"""
Интерактивный поиск по embeddings.db:

  1) векторный поиск (текст)
  2) текстовый поиск (substring, LIKE)
  3) нечёткий (fuzzy) поиск
  4) векторный поиск по изображению (multimodal embedding)
  0) выход

Библиотечная часть — в emb_api.py.
"""

import argparse
import difflib
import os
import shutil
import subprocess
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt
from rich.text import Text
from rich import box

from emb_api import (
    DEFAULT_BASE_URL,
    DEFAULT_DB,
    DEFAULT_MODEL,
    EmbeddingClient,
    EmbeddingError,
    Hit,
    ImageNotSupported,
    SearchIndex,
    open_db,
)


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
            r = subprocess.run(
                ["kitten", "icat", "--clear", path], check=False, timeout=15
            )
            if r.returncode == 0:
                return "kitty"
        except Exception:
            pass
    if shutil.which("chafa"):
        try:
            r = subprocess.run(["chafa", "-s", "60x30", path], check=False, timeout=15)
            if r.returncode == 0:
                return "chafa"
        except Exception:
            pass
    return None


# --------------------------------------------------------------- показ ----─


def show_results(title, rows: list[Hit], query, highlight=False, fuzzy=False):
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
    for i, hit in enumerate(rows):
        t = 1.0 if n == 1 else 1.0 - i / (n - 1)
        col = gradient(t)

        if highlight:
            full_t = render_marked(hit.full or "", query, col, fuzzy=fuzzy)
            mod_t = render_marked(hit.mod or "", query, col, fuzzy=fuzzy)
            id_t = render_marked(hit.id or "", query, col, fuzzy=fuzzy)
        else:
            full_t = Text(hit.full or "", style=col)
            mod_t = Text(hit.mod or "", style=col)
            id_t = Text(hit.id or "", style=col)

        table.add_row(
            Text(str(i + 1), style=TN_DIM),
            full_t,
            mod_t,
            id_t,
            Text(f"{hit.score * 100:5.1f}%", style=f"bold {col}"),
        )
    console.print(table)


# --------------------------------------------------------------- меню ----─


def ask_field():
    return Prompt.ask(
        f"[{TN_CYAN}]поле[/]", choices=["mod", "id", "full"], default="full"
    )


def do_vector(idx: SearchIndex):
    q = Prompt.ask(f"[{TN_CYAN}]фраза[/]").strip()
    if not q:
        return
    lim = IntPrompt.ask(f"[{TN_CYAN}]лимит[/]", default=10)
    with console.status(f"[{TN_CYAN}]эмбеддинг + KNN…[/]"):
        rows = idx.search_text(q, lim)
    show_results(f"[bold]векторный поиск:[/] {q!r}", rows, q)


def do_text(idx: SearchIndex):
    f = ask_field()
    q = Prompt.ask(f"[{TN_CYAN}]подстрока в {f}[/]").strip()
    if not q:
        return
    lim = IntPrompt.ask(f"[{TN_CYAN}]лимит[/]", default=10)
    rows = idx.search_substring(q, f, lim)
    show_results(
        f"[bold]текстовый поиск:[/] {q!r} в [magenta]{f}[/]",
        rows,
        q,
        highlight=True,
        fuzzy=False,
    )


def do_fuzzy(idx: SearchIndex):
    f = ask_field()
    q = Prompt.ask(f"[{TN_CYAN}]нечёткий запрос по {f}[/]").strip()
    if not q:
        return
    lim = IntPrompt.ask(f"[{TN_CYAN}]лимит[/]", default=10)
    with console.status(f"[{TN_CYAN}]fuzzy-скан…[/]"):
        rows = idx.search_fuzzy(q, f, lim)
    show_results(
        f"[bold]fuzzy-поиск:[/] {q!r} в [magenta]{f}[/]",
        rows,
        q,
        highlight=True,
        fuzzy=True,
    )


def do_image(idx: SearchIndex, image_model):
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
            rows = idx.search_image(path, lim, model=image_model)
        except ImageNotSupported as e:
            console.print(
                Panel(
                    f"[{TN_YELLOW}]обработка изображений недоступна[/]\n"
                    f"[{TN_DIM}]{e}[/]\n"
                    f"[{TN_DIM}]альтернатива — мультимодальный embedding-сервер "
                    f"(vLLM + CLIP/jina-clip, infinity, tei).[/]",
                    border_style=TN_DARK,
                )
            )
            return
        except EmbeddingError as e:
            console.print(Panel(f"[{TN_RED}]ошибка:[/] {e}", border_style=TN_DARK))
            return

    show_results(f"[bold]поиск по изображению:[/] {Path(path).name}", rows, "")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-d", "--db", default=DEFAULT_DB)
    ap.add_argument("-u", "--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("-m", "--model", default=DEFAULT_MODEL)
    ap.add_argument(
        "--image-model",
        default=None,
        help="модель для эмбеддинга изображений (по умолчанию -m)",
    )
    args = ap.parse_args()

    db = open_db(args.db)
    idx = SearchIndex(
        db,
        client=EmbeddingClient(args.base_url, args.model),
    )
    total = idx.count()

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
                do_vector(idx)
            elif choice == "2":
                do_text(idx)
            elif choice == "3":
                do_fuzzy(idx)
            elif choice == "4":
                do_image(idx, args.image_model)
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
