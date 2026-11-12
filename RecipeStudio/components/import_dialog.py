"""Modal dialog for importing KubeJS or datapack JSON recipes."""

from __future__ import annotations

import customtkinter as ctk

from RecipeStudio.services.recipe_import import RecipeImportError, parse_recipe
from RecipeStudio.theme import COLORS, FONT_MONO, FONT_UI, FONT_UI_SMALL


class ImportRecipeDialog(ctk.CTkToplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Import recipe")
        self.geometry("820x600")
        self.minsize(560, 360)
        self.configure(fg_color=COLORS["bg"])
        self.transient(app)
        self._build()
        self._center()
        self.grab_set()
        self.after(60, self._focus_text)

    def _build(self) -> None:
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        ctk.CTkLabel(
            header,
            text="IMPORT RECIPE",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 11, "bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            header,
            text="KubeJS · native KubeJS · datapack JSON",
            text_color=COLORS["text_dim"],
            font=FONT_UI_SMALL,
        ).pack(side="left", padx=(10, 0))

        self.text = ctk.CTkTextbox(
            self,
            fg_color=COLORS["code_bg"],
            border_color=COLORS["border"],
            border_width=1,
            text_color=COLORS["text"],
            font=FONT_MONO,
            wrap="none",
            activate_scrollbars=True,
        )
        self.text.grid(row=1, column=0, sticky="nsew", padx=16, pady=4)
        self.text.insert(
            "1.0",
            "// Вставь сюда рецепт, например:\n"
            "// event.shaped('minecraft:diamond_block', ['AAA','ABA','AAA'], "
            "{A: 'minecraft:iron_ingot', B: 'minecraft:diamond'})\n"
            '// или JSON датапака с полем "type".',
        )

        self.error_label = ctk.CTkLabel(
            self,
            text="",
            text_color=COLORS["red"],
            font=FONT_UI_SMALL,
            anchor="w",
            justify="left",
            wraplength=760,
        )
        self.error_label.grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 0))

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=3, column=0, sticky="e", padx=16, pady=(6, 14))
        ctk.CTkButton(
            buttons,
            text="Cancel",
            width=90,
            height=30,
            fg_color=COLORS["panel_alt"],
            hover_color=COLORS["panel_hover"],
            text_color=COLORS["text"],
            font=FONT_UI,
            command=self.destroy,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            buttons,
            text="Import",
            width=110,
            height=30,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_2"],
            text_color=COLORS["panel"],
            font=FONT_UI,
            command=self._import,
        ).pack(side="left")

    def _focus_text(self) -> None:
        try:
            self.text.focus_set()
        except Exception:
            pass

    def _center(self) -> None:
        try:
            self.update_idletasks()
            parent = self.app
            x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
            y = (
                parent.winfo_rooty()
                + (parent.winfo_height() - self.winfo_height()) // 2
            )
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

    def _import(self) -> None:
        raw = self.text.get("1.0", "end")
        try:
            recipe = parse_recipe(raw)
        except RecipeImportError as exc:
            self._show_error(str(exc))
            return
        except Exception as exc:
            self._show_error(
                f"Не удалось разобрать рецепт: {type(exc).__name__}: {exc}"
            )
            return

        try:
            self.destroy()
        finally:
            self.app.apply_imported_recipe(recipe)

    def _show_error(self, message: str) -> None:
        self.error_label.configure(text=message)
        self.set_status(message)
        try:
            self.text.focus_set()
        except Exception:
            pass

    def set_status(self, message: str) -> None:
        # The dialog keeps its own error line so a parse failure is visible
        # right next to the input.  The main window gets the same message.
        try:
            self.app.set_status(f"Import failed: {message}", error=True)
        except Exception:
            pass
