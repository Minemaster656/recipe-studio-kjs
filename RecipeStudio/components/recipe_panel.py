"""Left-panel recipe browser with background indexing."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from RecipeStudio.components.recipe_list import RecipeList
from RecipeStudio.services.recipe_index import (
    IndexResult,
    RecipeIndex,
    RecipeIndexer,
)
from RecipeStudio.theme import COLORS, FONT_UI_SMALL


class RecipePanel(ctk.CTkFrame):
    def __init__(self, master, app, index: RecipeIndex):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.index = index
        self.group_by = "type"
        self._indexing = False
        self._cancel_event: threading.Event | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(5, weight=1)

        # ---------------------------------------------------------- loading
        load = ctk.CTkFrame(self, fg_color="transparent")
        load.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 2))
        load.grid_columnconfigure(0, weight=1)
        self.path_var = ctk.StringVar()
        self.path_entry = ctk.CTkEntry(
            load,
            textvariable=self.path_var,
            placeholder_text="Путь к .jar / .js / .json / папке",
            height=30,
            fg_color=COLORS["panel_alt"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
            font=FONT_UI_SMALL,
        )
        self.path_entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.path_entry.bind("<Return>", lambda _e: self._add_from_entry())
        ctk.CTkButton(
            load,
            text="Добавить",
            width=74,
            height=30,
            corner_radius=7,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_2"],
            text_color=COLORS["panel"],
            font=FONT_UI_SMALL,
            command=self._add_from_entry,
        ).grid(row=0, column=1)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 2))
        for column in range(4):
            buttons.grid_columnconfigure(column, weight=1)
        self._small_button(buttons, "Файлы…", self._pick_files).grid(
            row=0, column=0, sticky="ew", padx=(0, 2)
        )
        self._small_button(buttons, "Папка…", self._pick_folder).grid(
            row=0, column=1, sticky="ew", padx=2
        )
        self._small_button(buttons, "mods", self._add_mods).grid(
            row=0, column=2, sticky="ew", padx=2
        )
        self._small_button(buttons, "kubejs", self._add_kubejs).grid(
            row=0, column=3, sticky="ew", padx=(2, 0)
        )

        # --------------------------------------------------------- progress
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.grid(row=2, column=0, sticky="ew", padx=4, pady=(2, 2))
        self.progress_frame.grid_columnconfigure(0, weight=1)
        self.progress_label = ctk.CTkLabel(
            self.progress_frame,
            text="",
            anchor="w",
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 9),
        )
        self.progress_label.grid(row=0, column=2, sticky="w", padx=(4, 0))
        self.progress_bar = ctk.CTkProgressBar(
            self.progress_frame,
            height=8,
            fg_color=COLORS["panel_alt"],
            progress_color=COLORS["accent"],
        )
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        self.cancel_button = ctk.CTkButton(
            self.progress_frame,
            text="Отмена",
            width=58,
            height=20,
            corner_radius=5,
            fg_color=COLORS["panel_alt"],
            hover_color=COLORS["panel_hover"],
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 9),
            command=self.cancel_indexing,
        )
        self.cancel_button.grid(row=0, column=1, padx=(6, 0))
        self.progress_frame.grid_remove()

        # ---------------------------------------------------------- search
        self.search_var = ctk.StringVar()
        self.search_entry = ctk.CTkEntry(
            self,
            textvariable=self.search_var,
            placeholder_text="Поиск: id, тип, target, source",
            height=30,
            fg_color=COLORS["panel_alt"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
            font=FONT_UI_SMALL,
        )
        self.search_entry.grid(row=3, column=0, sticky="ew", padx=4, pady=(4, 2))
        self.search_entry.bind("<KeyRelease>", lambda _e: self.refresh())
        self.search_entry.bind("<Return>", lambda _e: self.refresh())

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.grid(row=4, column=0, sticky="ew", padx=4, pady=(0, 2))
        controls.grid_columnconfigure(0, weight=1)
        self.group_control = ctk.CTkSegmentedButton(
            controls,
            values=["Type", "Target", "Source"],
            height=26,
            fg_color=COLORS["panel_alt"],
            selected_color=COLORS["accent"],
            selected_hover_color=COLORS["accent_2"],
            unselected_color=COLORS["panel_alt"],
            unselected_hover_color=COLORS["panel_hover"],
            text_color=COLORS["text"],
            font=("DejaVu Sans", 9),
            command=self._on_group_changed,
        )
        self.group_control.set("Type")
        self.group_control.grid(row=0, column=0, sticky="ew")
        self.count_label = ctk.CTkLabel(
            controls,
            text="0",
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 9),
        )
        self.count_label.grid(row=0, column=1, sticky="e", padx=(6, 0))

        # The list must stay in the last row and take all remaining height.
        self.grid_rowconfigure(5, weight=1)
        self.list = RecipeList(self, self.app)
        self.list.grid(row=5, column=0, sticky="nsew", padx=(2, 0), pady=(2, 2))

        self.status_label = ctk.CTkLabel(
            self,
            text="",
            anchor="w",
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 9),
        )
        self.status_label.grid(row=6, column=0, sticky="ew", padx=4, pady=(0, 4))

        self._setup_dnd()

    # ------------------------------------------------------------------
    def _small_button(self, master, text: str, command) -> ctk.CTkButton:
        return ctk.CTkButton(
            master,
            text=text,
            height=24,
            corner_radius=6,
            fg_color=COLORS["panel_alt"],
            hover_color=COLORS["panel_hover"],
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 9),
            command=command,
        )

    def _set_status(self, text: str, *, error: bool = False) -> None:
        self.status_label.configure(
            text=text, text_color=COLORS["red"] if error else COLORS["text_dim"]
        )
        self.app.set_status(text, error=error)

    # ------------------------------------------------------------------
    def _add_from_entry(self) -> None:
        raw = self.path_var.get().strip()
        if not raw:
            return
        self.start_indexing([raw])

    def _pick_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Добавить рецепты",
            filetypes=[
                ("Mod jars", "*.jar"),
                ("Archives", "*.zip"),
                ("KubeJS scripts", "*.js"),
                ("Datapack JSON", "*.json"),
                ("All files", "*.*"),
            ],
        )
        if paths:
            self.start_indexing(list(paths))

    def _pick_folder(self) -> None:
        path = filedialog.askdirectory(title="Добавить папку с рецептами")
        if path:
            self.start_indexing([path])

    def _add_mods(self) -> None:
        path = self.app.config.path_for("mods_dir")
        if path.exists():
            self.start_indexing([path])
        else:
            self._set_status(f"Папка модов не найдена: {path}", error=True)

    def _add_kubejs(self) -> None:
        path = self.app.config.path_for("kubejs_dir")
        if path.exists():
            self.start_indexing([path])
        else:
            self._set_status(f"Папка KubeJS не найдена: {path}", error=True)

    # ------------------------------------------------------------------
    def start_indexing(self, paths) -> None:
        if self._indexing:
            self._set_status("Индексация уже идёт", error=True)
            return
        cleaned = [str(path) for path in paths if str(path).strip()]
        if not cleaned:
            return

        self._indexing = True
        self._cancel_event = threading.Event()
        self.progress_frame.grid()
        self.progress_bar.set(0)
        self.progress_label.configure(text="Индексация…")
        self.cancel_button.configure(state="normal", text="Отмена")
        self._set_status(f"Индексация: {len(cleaned)} источник(ов)")

        def progress(done: int, total: int, label: str) -> None:
            self.app._post(lambda: self._on_progress(done, total, label))

        def done(result: IndexResult) -> None:
            self.app._post(lambda: self._on_done(result))

        indexer = RecipeIndexer(
            self.index,
            on_progress=progress,
            on_done=done,
            cancel_event=self._cancel_event,
        )

        def worker() -> None:
            try:
                indexer.index_paths(cleaned)
            except Exception as exc:  # noqa: BLE001 - never crash the GUI thread
                self.app._post(lambda: self._on_failed(exc))

        threading.Thread(target=worker, daemon=True).start()

    def cancel_indexing(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()
            self.cancel_button.configure(state="disabled", text="Останавливаю…")

    def shutdown(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()

    def _on_progress(self, done: int, total: int, label: str) -> None:
        if not self._indexing:
            return
        fraction = (done / total) if total else 0.0
        self.progress_bar.set(max(0.0, min(1.0, fraction)))
        if total:
            self.progress_label.configure(text=f"{done}/{total} · {label}")
        else:
            self.progress_label.configure(text="Нет файлов для индексации")

    def _on_done(self, result: IndexResult) -> None:
        self._indexing = False
        self._cancel_event = None
        self.progress_bar.set(1.0)
        self.progress_frame.grid_remove()
        self.refresh()
        if result.cancelled:
            message = f"Индексация отменена · добавлено {result.added}"
        else:
            message = (
                f"Добавлено {result.added} · пропущено {result.skipped}"
                f" · ошибок {result.failed}"
            )
        if result.errors:
            first_path, first_error = result.errors[0]
            self._set_status(f"{message} · {first_path}: {first_error}", error=True)
        else:
            self._set_status(message, error=False)

    def _on_failed(self, exc: Exception) -> None:
        self._indexing = False
        self._cancel_event = None
        self.progress_frame.grid_remove()
        self._set_status(f"Ошибка индексации: {type(exc).__name__}: {exc}", error=True)

    # ------------------------------------------------------------------
    def _on_group_changed(self, value: str) -> None:
        self.group_by = value.lower()
        self.refresh()

    def refresh(self) -> None:
        query = self.search_var.get().strip()
        records = self.index.search(query)
        groups = self.index.group(records, self.group_by)
        self.list.set_groups(groups, self.group_by)
        total = len(self.index.records)
        self.count_label.configure(text=f"{len(records)} / {total}")

    # ------------------------------------------------------------------
    def _setup_dnd(self) -> None:
        try:
            from tkinterdnd2 import DND_FILES, TkinterDnD

            TkinterDnD._require(self.winfo_toplevel())
            for widget in (self, self.list, self.list.canvas, self.path_entry):
                try:
                    widget.drop_target_register(DND_FILES)
                    widget.dnd_bind("<<Drop>>", self._on_drop)
                except Exception:
                    continue
        except Exception:
            # Drag-and-drop is optional; the path entry and dialogs still work.
            pass

    def _on_drop(self, event):
        try:
            paths = list(self.tk.splitlist(event.data))
        except Exception:
            paths = [str(event.data)]
        if paths:
            self.start_indexing(paths)
        return event.action if hasattr(event, "action") else None
