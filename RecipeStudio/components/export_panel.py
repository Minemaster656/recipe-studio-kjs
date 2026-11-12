"""Bottom export panel: code preview, copy/clear, event/removal options."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from RecipeStudio.components.slot import Slot
from RecipeStudio.theme import COLORS, FONT_MONO, FONT_UI, FONT_UI_SMALL


class ExportPanel(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=COLORS["panel"], corner_radius=8)
        self.app = app
        self.wrap_var = tk.BooleanVar(value=True)
        self.remove_var = tk.BooleanVar(value=False)

        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            header,
            text="EXPORT",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 10, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            header,
            text="Copy",
            width=70,
            height=26,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_2"],
            text_color=COLORS["panel"],
            command=lambda: self.app.copy_export(False),
        ).grid(row=0, column=1, sticky="e", padx=(0, 6))
        ctk.CTkButton(
            header,
            text="Import",
            width=78,
            height=26,
            fg_color=COLORS["panel_alt"],
            hover_color=COLORS["panel_hover"],
            text_color=COLORS["text"],
            command=self.app.open_import_dialog,
        ).grid(row=0, column=2, sticky="e", padx=(0, 6))
        ctk.CTkButton(
            header,
            text="Clear editor",
            width=100,
            height=26,
            fg_color=COLORS["panel_alt"],
            hover_color=COLORS["panel_hover"],
            text_color=COLORS["text"],
            command=self.app.clear_editor,
        ).grid(row=0, column=3, sticky="e")

        self.code = ctk.CTkTextbox(
            self,
            height=150,
            fg_color=COLORS["code_bg"],
            border_color=COLORS["border"],
            border_width=1,
            text_color=COLORS["text"],
            font=FONT_MONO,
            wrap="none",
            activate_scrollbars=True,
        )
        self.code.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 2))
        self.code.configure(state="disabled")

        self.hbar = None
        try:
            self.hbar = ctk.CTkScrollbar(
                self,
                orientation="horizontal",
                command=self.code._textbox.xview,  # type: ignore[attr-defined]
                fg_color=COLORS["code_bg"],
                button_color=COLORS["slot_border"],
                button_hover_color=COLORS["slot_hover"],
            )
            self.hbar.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 6))
            self.code._textbox.configure(xscrollcommand=self.hbar.set)  # type: ignore[attr-defined]
        except Exception:
            self.hbar = None

        options = ctk.CTkFrame(self, fg_color="transparent")
        options.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 4))
        ctk.CTkCheckBox(
            options,
            text="Wrap in event",
            variable=self.wrap_var,
            command=self.app.update_export,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_2"],
            text_color=COLORS["text"],
            font=FONT_UI_SMALL,
            checkbox_width=18,
            checkbox_height=18,
        ).pack(side="left")
        ctk.CTkCheckBox(
            options,
            text="Remove original recipe",
            variable=self.remove_var,
            command=self.app.update_export,
            fg_color=COLORS["red"],
            hover_color=COLORS["orange"],
            text_color=COLORS["text"],
            font=FONT_UI_SMALL,
            checkbox_width=18,
            checkbox_height=18,
        ).pack(side="left", padx=(16, 0))

        filter_frame = ctk.CTkFrame(self, fg_color="transparent")
        filter_frame.grid(row=4, column=0, sticky="ew", padx=10, pady=(2, 4))
        ctk.CTkLabel(
            filter_frame,
            text="Remove filter:",
            text_color=COLORS["text_muted"],
            font=FONT_UI_SMALL,
        ).pack(side="left")
        self.override_slot = Slot(
            filter_frame,
            app,
            size=34,
            allow_count=False,
            allow_tag=True,
            allow_fluid=False,
            allow_chance=False,
            on_change=self.app.update_export,
            tooltip=True,
        )
        self.override_slot.pack(side="left", padx=(8, 8))
        self.effective_label = ctk.CTkLabel(
            filter_frame,
            text="",
            text_color=COLORS["text_dim"],
            font=FONT_UI_SMALL,
            anchor="w",
        )
        self.effective_label.pack(side="left", fill="x", expand=True)

        self.errors_label = ctk.CTkLabel(
            self,
            text="",
            text_color=COLORS["red"],
            font=FONT_UI_SMALL,
            anchor="w",
            justify="left",
            wraplength=900,
        )
        self.errors_label.grid(row=5, column=0, sticky="ew", padx=10, pady=(0, 8))

    # ------------------------------------------------------------------
    def set_code(self, code: str) -> None:
        self.code.configure(state="normal")
        self.code.delete("1.0", "end")
        self.code.insert("1.0", code)
        self.code.configure(state="disabled")

    def set_errors(self, errors: list[str]) -> None:
        if errors:
            self.errors_label.configure(text=" · ".join(errors))
        else:
            self.errors_label.configure(text="")

    def set_effective(self, ingredient) -> None:
        if ingredient is None or ingredient.is_empty:
            self.effective_label.configure(text="")
        else:
            self.effective_label.configure(text="→ " + ingredient.label())

    def get_override(self):
        return self.override_slot.ingredient

    def clear_override(self) -> None:
        self.override_slot.clear(notify=False)
