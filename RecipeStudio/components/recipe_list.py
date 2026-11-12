"""Virtualised, collapsible recipe list drawn on a Tk canvas."""

from __future__ import annotations

import bisect
import tkinter as tk

import customtkinter as ctk

from RecipeStudio.services.recipe_index import RecipeRecord
from RecipeStudio.theme import COLORS, FONT_UI_SMALL


class _Row:
    __slots__ = ("kind", "key", "record", "count")

    def __init__(self, kind: str, key: str, record=None, count: int = 0):
        self.kind = kind
        self.key = key
        self.record = record
        self.count = count


class RecipeList(tk.Frame):
    GROUP_HEIGHT = 30
    ROW_HEIGHT = 54

    def __init__(self, master, app):
        super().__init__(master, bg=COLORS["panel"], highlightthickness=0, bd=0)
        self.app = app
        self.groups: list[tuple[str, list[RecipeRecord]]] = []
        self.group_by = "type"
        self.collapsed: set[str] = set()
        self.rows: list[_Row] = []
        self._offsets: list[int] = []
        self._total_height = 0
        self._hover_row = -1
        self._redraw_job = None

        self.canvas = tk.Canvas(
            self,
            bg=COLORS["panel"],
            highlightthickness=0,
            bd=0,
            takefocus=1,
            yscrollincrement=18,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ctk.CTkScrollbar(
            self,
            orientation="vertical",
            command=self.canvas.yview,
            fg_color=COLORS["panel"],
            button_color=COLORS["slot_border"],
            button_hover_color=COLORS["slot_hover"],
        )
        self.scrollbar.grid(row=0, column=1, sticky="ns", padx=(4, 0))
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.canvas.bind("<Configure>", self._on_configure)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", self._on_leave)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self._scroll(-1))
        self.canvas.bind("<Button-5>", lambda e: self._scroll(1))

    # ------------------------------------------------------------------
    def set_groups(self, groups: list[tuple[str, list[RecipeRecord]]], by: str) -> None:
        if by != self.group_by:
            self.collapsed.clear()
        self.groups = list(groups)
        self.group_by = by
        self._rebuild()

    def refresh(self) -> None:
        self._rebuild()

    def focus(self) -> None:
        self.canvas.focus_set()

    # ------------------------------------------------------------------
    def _rebuild(self) -> None:
        rows: list[_Row] = []
        for key, records in self.groups:
            rows.append(_Row("group", key, count=len(records)))
            if key in self.collapsed:
                continue
            rows.extend(_Row("record", key, record=record) for record in records)
        self.rows = rows
        self._offsets = []
        y = 0
        for row in rows:
            self._offsets.append(y)
            y += self._row_height(row)
        self._total_height = y
        self._hover_row = -1
        self._recalc()
        self._schedule_redraw()

    def _row_height(self, row: _Row) -> int:
        return self.GROUP_HEIGHT if row.kind == "group" else self.ROW_HEIGHT

    def _recalc(self) -> None:
        width = max(1, self.canvas.winfo_width())
        self.canvas.configure(scrollregion=(0, 0, width, max(1, self._total_height)))

    def _schedule_redraw(self) -> None:
        if self._redraw_job is not None:
            return
        self._redraw_job = self.after_idle(self._redraw)

    def _redraw(self) -> None:
        self._redraw_job = None
        canvas = self.canvas
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        if not self.groups:
            canvas.create_text(
                max(120, width // 2),
                70,
                text="Рецепты не загружены",
                fill=COLORS["text_dim"],
                font=("DejaVu Sans", 12),
            )
            return

        top = canvas.canvasy(0)
        bottom = top + max(1, canvas.winfo_height())
        first = max(0, bisect.bisect_right(self._offsets, top) - 1)
        for index in range(first, len(self.rows)):
            y0 = self._offsets[index]
            row = self.rows[index]
            height = self._row_height(row)
            if y0 > bottom:
                break
            if y0 + height < top:
                continue
            if row.kind == "group":
                self._draw_group(index, row, y0, width, y0 + height)
            elif row.record is not None:
                self._draw_record(index, row, y0, width, y0 + height)

    def _group_label(self, key: str) -> str:
        if self.group_by == "type":
            title = self.app.module_title(key)
            if title:
                return f"{key}  ·  {title}"
        return key

    def _draw_group(self, index: int, row: _Row, y0: int, width: int, y1: int) -> None:
        canvas = self.canvas
        hover = index == self._hover_row
        canvas.create_rectangle(
            0,
            y0,
            width,
            y1,
            fill=COLORS["panel_hover"] if hover else COLORS["panel_alt"],
            outline="",
        )
        arrow = "▸" if row.key in self.collapsed else "▾"
        canvas.create_text(
            10,
            (y0 + y1) / 2,
            anchor="w",
            text=f"{arrow}  {self._group_label(row.key)}  ({row.count})",
            fill=COLORS["text"],
            font=("DejaVu Sans", 11, "bold"),
        )

    def _button_rects(
        self, y0: int, width: int
    ) -> dict[str, tuple[int, int, int, int]]:
        y1 = y0 + self.ROW_HEIGHT
        pad = 6
        delete = (width - 34, width - 8, y0 + pad, y1 - pad)
        copy = (delete[0] - 100, delete[0] - 6, y0 + pad, y1 - pad)
        import_rect = (copy[0] - 66, copy[0] - 6, y0 + pad, y1 - pad)
        return {"import": import_rect, "copy": copy, "delete": delete}

    def _draw_record(self, index: int, row: _Row, y0: int, width: int, y1: int) -> None:
        record = row.record
        if record is None:
            return
        canvas = self.canvas
        hover = index == self._hover_row
        fill = COLORS["panel_hover"] if hover else COLORS["panel"]
        canvas.create_rectangle(0, y0, width, y1 - 1, fill=fill, outline="")
        canvas.create_rectangle(
            0,
            y0,
            3,
            y1 - 1,
            fill=COLORS["accent"] if record.importable else COLORS["slot_border"],
            outline="",
        )

        text_width = max(120, width - 240)
        title = record.display_name
        max_title = max(16, int(text_width / 7))
        if len(title) > max_title:
            title = title[: max_title - 1] + "…"
        canvas.create_text(
            12,
            y0 + 17,
            anchor="w",
            text=title,
            fill=COLORS["text"],
            font=("DejaVu Sans", 11),
        )
        subtitle_parts = [record.recipe_id or record.source_detail]
        if record.type_id:
            subtitle_parts.append(record.type_id)
        subtitle_parts.append(record.target_mod)
        subtitle = "  ·  ".join(part for part in subtitle_parts if part)
        max_subtitle = max(20, int(text_width / 5.5))
        if len(subtitle) > max_subtitle:
            subtitle = subtitle[: max_subtitle - 1] + "…"
        canvas.create_text(
            12,
            y0 + 36,
            anchor="w",
            text=subtitle,
            fill=COLORS["text_dim"],
            font=("DejaVu Sans", 9),
        )

        rects = self._button_rects(y0, width)
        if record.module_id:
            import_color = (
                COLORS["accent"] if record.importable else COLORS["slot_border"]
            )
            self._draw_button(rects["import"], "Import", import_color)
        elif record.import_error:
            canvas.create_text(
                (rects["import"][0] + rects["import"][1]) / 2,
                (rects["import"][2] + rects["import"][3]) / 2,
                text="!",
                fill=COLORS["red"],
                font=("DejaVu Sans", 12, "bold"),
            )
        self._draw_button(rects["copy"], "Copy remove", COLORS["purple"])
        self._draw_button(rects["delete"], "×", COLORS["red"])

    def _draw_button(
        self, rect: tuple[int, int, int, int], text: str, color: str
    ) -> None:
        x0, x1, y0, y1 = rect
        self.canvas.create_rectangle(
            x0,
            y0,
            x1,
            y1,
            fill=COLORS["panel_alt"],
            outline=COLORS["border"],
        )
        self.canvas.create_text(
            (x0 + x1) / 2,
            (y0 + y1) / 2,
            text=text,
            fill=color,
            font=FONT_UI_SMALL,
        )

    # ------------------------------------------------------------------
    def _row_at(self, y: int) -> int:
        if not self.rows:
            return -1
        y_canvas = self.canvas.canvasy(y)
        index = bisect.bisect_right(self._offsets, y_canvas) - 1
        if index < 0 or index >= len(self.rows):
            return -1
        return index

    def _action_at(self, event) -> tuple[int, str] | None:
        index = self._row_at(event.y)
        if index < 0:
            return None
        row = self.rows[index]
        if row.kind == "group":
            return index, "toggle"
        if row.kind != "record" or row.record is None:
            return None
        y0 = self._offsets[index]
        y_canvas = self.canvas.canvasy(event.y)
        rects = self._button_rects(y0, max(1, self.canvas.winfo_width()))
        for action, (x0, x1, top, bottom) in rects.items():
            if x0 <= event.x <= x1 and top <= y_canvas <= bottom:
                if action == "import" and not row.record.module_id:
                    return index, "none"
                return index, action
        return index, "row"

    def _on_configure(self, _event=None) -> None:
        self._recalc()
        self._schedule_redraw()

    def _on_motion(self, event) -> None:
        index = self._row_at(event.y)
        if index != self._hover_row:
            self._hover_row = index
            self._schedule_redraw()
        action = self._action_at(event)
        cursor = (
            "hand2"
            if action and action[1] in ("toggle", "import", "copy", "delete")
            else ""
        )
        if self.canvas.cget("cursor") != cursor:
            self.canvas.configure(cursor=cursor)

    def _on_leave(self, _event=None) -> None:
        self._hover_row = -1
        self.canvas.configure(cursor="")
        self._schedule_redraw()

    def _on_click(self, event) -> None:
        action = self._action_at(event)
        if action is None:
            return
        index, name = action
        row = self.rows[index]
        if name == "toggle":
            if row.key in self.collapsed:
                self.collapsed.remove(row.key)
            else:
                self.collapsed.add(row.key)
            self._rebuild()
            return
        record = row.record
        if record is None or name == "none":
            return
        if name == "import":
            if record.importable:
                self.app.import_indexed_recipe(record)
            elif record.import_error:
                self.app.set_status(f"Import failed: {record.import_error}", error=True)
            return
        if name == "copy":
            self.app.copy_recipe_removal(record)
            return
        if name == "delete":
            self.app.remove_indexed_recipe(record)
            return

    def _on_double_click(self, event) -> None:
        action = self._action_at(event)
        if action is None:
            return
        index, name = action
        if name == "row":
            record = self.rows[index].record
            if record is not None and record.importable:
                self.app.import_indexed_recipe(record)

    def _on_wheel(self, event) -> str:
        if event.delta:
            self._scroll(-1 if event.delta > 0 else 1)
        return "break"

    def _scroll(self, delta: int) -> str:
        self.canvas.yview_scroll(delta * 3, "units")
        self._schedule_redraw()
        return "break"
