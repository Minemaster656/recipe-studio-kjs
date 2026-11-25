"""Create / edit dialog for build projects.

A project is a JSON profile that stores every path the editor loads at
runtime: item catalogue, icon export, embeddings database, mods/KubeJS
folders and per-project caches.  Paths are stored absolute.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from RecipeStudio.config import Config
from RecipeStudio.services.projects import (
    ProjectError,
    create_project,
    save_project,
)
from RecipeStudio.theme import COLORS, FONT_UI_SMALL

# (key, label, mode)
PATH_FIELDS = (
    ("icons_dir", "Папка иконок", "dir"),
    ("items_json", "Каталог предметов (JSON)", "file"),
    ("icon_manifest", "Манифест иконок (JSON)", "file"),
    ("database", "База эмбеддингов", "file"),
    ("mods_dir", "Папка модов", "dir"),
    ("kubejs_dir", "Папка KubeJS", "dir"),
    ("favorites", "Избранное (JSON)", "file"),
    ("names_cache", "Кэш имён (JSON)", "file"),
)

LIST_FIELDS = (
    ("extra_lang_jars", "Доп. jar с переводами (по одному пути в строке)"),
    ("recipe_sources", "Источники рецептов (по одному пути в строке)"),
)


class ProjectDialog(ctk.CTkToplevel):
    def __init__(self, app, project: Config | None):
        super().__init__(fg_color=COLORS["bg"])
        self.app = app
        self.project = project
        self.vars: dict[str, ctk.StringVar] = {}
        self.text_boxes: dict[str, ctk.CTkTextbox] = {}
        self.auto_index_var = ctk.BooleanVar(
            value=bool(project.get("auto_index", True)) if project else True
        )

        title = "Редактировать проект" if project else "Новый проект"
        self.title(title)
        self.geometry("760x720")
        self.minsize(640, 520)
        self.transient(app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        body = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_fg_color=COLORS["panel"],
            scrollbar_button_color=COLORS["slot_border"],
        )
        body.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 4))
        body.grid_columnconfigure(1, weight=1)

        row = 0
        self.name_var = ctk.StringVar(
            value=str(project.get("name") or "New Project") if project else "New Project"
        )
        row = self._add_entry(body, row, "Название", self.name_var)

        for key, label, mode in PATH_FIELDS:
            variable = ctk.StringVar(
                value=str(project.get(key) or "") if project else ""
            )
            self.vars[key] = variable
            row = self._add_path_row(body, row, label, variable, mode)

        for key, label in LIST_FIELDS:
            row = self._add_list_row(body, row, label, key, project)

        self.search_limit_var = ctk.StringVar(
            value=str(project.get("search_limit", 500)) if project else "500"
        )
        row = self._add_entry(body, row, "Лимит поиска", self.search_limit_var)

        self.disabled_var = ctk.StringVar(
            value=", ".join(str(x) for x in (project.get("disabled_modules") or []))
            if project
            else ""
        )
        row = self._add_entry(
            body, row, "Отключённые модули (через запятую)", self.disabled_var
        )

        ctk.CTkCheckBox(
            body,
            text="Автоматически индексировать источники рецептов",
            variable=self.auto_index_var,
            font=FONT_UI_SMALL,
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(10, 4))
        row += 1

        self.create_mode_var = ctk.StringVar(
            value=str(project.get("create_export_mode") or "addon")
            if project
            else "addon"
        )
        ctk.CTkLabel(
            body, text="Create-рецепты:", anchor="w", font=FONT_UI_SMALL,
            text_color=COLORS["text_dim"],
        ).grid(row=row, column=0, sticky="w", pady=(4, 0))
        ctk.CTkOptionMenu(
            body,
            values=["addon", "custom"],
            variable=self.create_mode_var,
            width=180,
            fg_color=COLORS["panel_alt"],
            button_color=COLORS["panel_hover"],
            button_hover_color=COLORS["accent"],
            text_color=COLORS["text"],
            font=FONT_UI_SMALL,
        ).grid(row=row, column=1, sticky="w", padx=(6, 0), pady=(4, 0))
        row += 1

        ctk.CTkLabel(
            body,
            text=(
                "Все пути сохраняются абсолютными. Пустые поля остаются "
                "незаданными — палитра или поиск просто будут недоступны."
            ),
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 9),
            justify="left",
            anchor="w",
        ).grid(row=row, column=0, columnspan=3, sticky="ew", pady=(4, 0))

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=1, column=0, sticky="ew", padx=12, pady=(4, 12))
        buttons.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(
            buttons,
            text="Отмена",
            width=120,
            height=32,
            fg_color=COLORS["panel_alt"],
            hover_color=COLORS["panel_hover"],
            text_color=COLORS["text"],
            font=FONT_UI_SMALL,
            command=self.destroy,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            buttons,
            text="Сохранить",
            width=140,
            height=32,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_2"],
            text_color=COLORS["panel"],
            font=FONT_UI_SMALL,
            command=self._save,
        ).grid(row=0, column=1, sticky="e")

        self.error_label = ctk.CTkLabel(
            self,
            text="",
            text_color=COLORS["red"],
            font=("DejaVu Sans", 9),
            anchor="w",
        )
        self.error_label.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 8))

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.focus_force()

    # ------------------------------------------------------------------
    def _add_entry(self, master, row: int, label: str, variable) -> int:
        ctk.CTkLabel(
            master, text=label, anchor="w", font=FONT_UI_SMALL, text_color=COLORS["text_dim"]
        ).grid(row=row, column=0, sticky="w", pady=(6, 0))
        ctk.CTkEntry(
            master,
            textvariable=variable,
            height=30,
            fg_color=COLORS["panel_alt"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
            font=FONT_UI_SMALL,
        ).grid(row=row, column=1, sticky="ew", padx=(6, 0), pady=(6, 0))
        return row + 1

    def _add_path_row(self, master, row: int, label: str, variable, mode: str) -> int:
        ctk.CTkLabel(
            master, text=label, anchor="w", font=FONT_UI_SMALL, text_color=COLORS["text_dim"]
        ).grid(row=row, column=0, sticky="w", pady=(6, 0))
        ctk.CTkEntry(
            master,
            textvariable=variable,
            height=30,
            fg_color=COLORS["panel_alt"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
            font=FONT_UI_SMALL,
        ).grid(row=row, column=1, sticky="ew", padx=(6, 4), pady=(6, 0))
        ctk.CTkButton(
            master,
            text="…",
            width=40,
            height=30,
            corner_radius=7,
            fg_color=COLORS["panel_alt"],
            hover_color=COLORS["panel_hover"],
            text_color=COLORS["text"],
            font=FONT_UI_SMALL,
            command=lambda: self._browse(variable, mode),
        ).grid(row=row, column=2, sticky="e", pady=(6, 0))
        return row + 1

    def _add_list_row(self, master, row: int, label: str, key: str, project) -> int:
        ctk.CTkLabel(
            master, text=label, anchor="w", font=FONT_UI_SMALL, text_color=COLORS["text_dim"]
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(8, 0))
        box = ctk.CTkTextbox(
            master,
            height=64,
            fg_color=COLORS["panel_alt"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
            font=FONT_UI_SMALL,
        )
        values = (project.get(key) if project else None) or []
        if isinstance(values, str):
            values = [values]
        box.insert("1.0", "\n".join(str(item) for item in values))
        box.grid(row=row + 1, column=0, columnspan=3, sticky="ew", pady=(2, 0))
        self.text_boxes[key] = box
        return row + 2

    def _browse(self, variable, mode: str) -> None:
        if mode == "dir":
            path = filedialog.askdirectory(title="Выбрать папку")
        else:
            path = filedialog.askopenfilename(
                title="Выбрать файл", filetypes=[("JSON", "*.json"), ("All files", "*.*")]
            )
        if path:
            variable.set(path)

    # ------------------------------------------------------------------
    def _collect(self) -> dict:
        values: dict = {
            "name": self.name_var.get().strip() or "Project",
            "base_url": str(self.project.get("base_url") if self.project else ""),
            "embedding_model": str(
                self.project.get("embedding_model") if self.project else ""
            ),
            "auto_index": bool(self.auto_index_var.get()),
            "create_export_mode": self.create_mode_var.get() or "addon",
            "search_limit": int(self.search_limit_var.get() or 500),
            "disabled_modules": [
                part.strip()
                for part in self.disabled_var.get().split(",")
                if part.strip()
            ],
        }
        if not values["base_url"]:
            values["base_url"] = "http://127.0.0.1:9931/v1"
        if not values["embedding_model"]:
            values["embedding_model"] = "embeddinggemma2"
        for key, variable in self.vars.items():
            values[key] = variable.get().strip() or None
        for key, box in self.text_boxes.items():
            values[key] = [
                line.strip()
                for line in box.get("1.0", "end").splitlines()
                if line.strip()
            ]
        if not values["recipe_sources"]:
            values["recipe_sources"] = [
                path
                for path in (values.get("mods_dir"), values.get("kubejs_dir"))
                if path
            ]
        return values

    def _save(self) -> None:
        values = self._collect()
        try:
            if self.project is None:
                config = create_project(self.app.app_config, values["name"], values)
            else:
                data = {**self.project.data, **values}
                config = Config(
                    data, self.project.project_path, base_dir=self.project.base_dir
                )
                save_project(self.project.project_path, config)
        except (ProjectError, ValueError) as exc:
            self.error_label.configure(text=str(exc))
            return
        self.destroy()
        self.app.switch_project(config)