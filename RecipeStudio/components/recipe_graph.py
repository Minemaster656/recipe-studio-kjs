"""Interactive recipe graph rendered on a Tk canvas.

The graph is centred on one item.  Producers are expanded to the left and
consumers to the right; the two depth selectors control how many recipe/item
rings are explored in each direction.
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass

import customtkinter as ctk

from RecipeStudio.components.slot import Slot
from RecipeStudio.model.ingredient import Ingredient
from RecipeStudio.services.recipe_index import RecipeRecord
from RecipeStudio.theme import COLORS, FONT_UI_SMALL

try:  # Pillow is already a project dependency, but keep the UI usable without it.
    from PIL import Image, ImageTk
except Exception:  # pragma: no cover - only for minimal installations
    Image = None
    ImageTk = None


@dataclass(slots=True)
class _Box:
    x0: float
    y0: float
    x1: float
    y1: float
    kind: str
    value: object = None
    relation: str = ""
    hidden: int = 0


@dataclass(slots=True)
class _GNode:
    kind: str
    x: float
    y: float
    w: float
    h: float
    item_id: str = ""
    record: RecipeRecord | None = None
    relation: str = ""
    main: bool = False
    hidden_items: int = 0


class RecipeGraphView(ctk.CTkFrame):
    """Show recipes that produce/consume an item, up to configurable depth."""

    MAX_DEPTH = 4
    VERTICAL_VALUES = (3, 5, 8, 12, 20)
    DEFAULT_VERTICAL = 8
    MAX_NODES_PER_SIDE = 280
    CARD_W = 238
    CARD_H = 84
    ITEM_W = 174
    ITEM_H = 48
    CENTER_W = 194
    CENTER_H = 58
    COL_GAP = 92
    ROW_GAP = 18
    MARGIN = 28

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.target: Ingredient | None = None
        self.left_depth = 1
        self.right_depth = 1
        self.vertical_limit = self.DEFAULT_VERTICAL
        self._redraw_job = None
        self._photos: dict = {}
        self._item_boxes: list[_Box] = []
        self._recipe_boxes: list[_Box] = []
        self._import_boxes: list[_Box] = []
        self._hover_key = None
        self._nodes: list[_GNode] = []
        self._edges: list[tuple[_GNode, _GNode, bool]] = []
        self._producer_map: dict[str, list[RecipeRecord]] = {}
        self._consumer_map: dict[str, list[RecipeRecord]] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color=COLORS["panel"], corner_radius=10)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header,
            text="RECIPE GRAPH",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 10, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=(14, 8), pady=10)

        self.hint_label = ctk.CTkLabel(
            header,
            text="ПКМ по предмету → View in recipe graph",
            text_color=COLORS["text_dim"],
            anchor="w",
            justify="left",
            wraplength=240,
            font=FONT_UI_SMALL,
        )
        self.hint_label.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=10)

        depth_box = ctk.CTkFrame(header, fg_color="transparent")
        depth_box.grid(row=0, column=2, sticky="e", padx=(0, 10), pady=6)
        ctk.CTkLabel(
            depth_box,
            text="DEPTH · VERTICAL LIMIT",
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 8, "bold"),
        ).grid(row=0, column=0, columnspan=6, sticky="w")
        ctk.CTkLabel(
            depth_box,
            text="L",
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 9),
        ).grid(row=1, column=0, sticky="e", padx=(0, 3))
        self.left_depth_menu = ctk.CTkOptionMenu(
            depth_box,
            values=[str(n) for n in range(1, self.MAX_DEPTH + 1)],
            width=50,
            height=24,
            fg_color=COLORS["panel_alt"],
            button_color=COLORS["panel_hover"],
            button_hover_color=COLORS["accent"],
            text_color=COLORS["text"],
            font=("DejaVu Sans", 9),
            command=self._set_left_depth,
        )
        self.left_depth_menu.grid(row=1, column=1, padx=(0, 6))
        ctk.CTkLabel(
            depth_box,
            text="R",
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 9),
        ).grid(row=1, column=2, sticky="e", padx=(0, 3))
        self.right_depth_menu = ctk.CTkOptionMenu(
            depth_box,
            values=[str(n) for n in range(1, self.MAX_DEPTH + 1)],
            width=50,
            height=24,
            fg_color=COLORS["panel_alt"],
            button_color=COLORS["panel_hover"],
            button_hover_color=COLORS["accent"],
            text_color=COLORS["text"],
            font=("DejaVu Sans", 9),
            command=self._set_right_depth,
        )
        self.right_depth_menu.grid(row=1, column=3, padx=(0, 6))
        ctk.CTkLabel(
            depth_box,
            text="V",
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 9),
        ).grid(row=1, column=4, sticky="e", padx=(0, 3))
        self.vertical_menu = ctk.CTkOptionMenu(
            depth_box,
            values=[str(n) for n in self.VERTICAL_VALUES],
            width=54,
            height=24,
            fg_color=COLORS["panel_alt"],
            button_color=COLORS["panel_hover"],
            button_hover_color=COLORS["accent"],
            text_color=COLORS["text"],
            font=("DejaVu Sans", 9),
            command=self._set_vertical_limit,
        )
        self.vertical_menu.grid(row=1, column=5)
        self.vertical_menu.set(str(self.DEFAULT_VERTICAL))

        target_box = ctk.CTkFrame(header, fg_color="transparent")
        target_box.grid(row=0, column=3, sticky="e", padx=(0, 10), pady=6)
        ctk.CTkLabel(
            target_box,
            text="TARGET",
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 8, "bold"),
        ).grid(row=0, column=0, sticky="w")
        self.target_slot = Slot(
            target_box,
            self.app,
            size=44,
            on_change=self._on_target_changed,
        )
        self.target_slot.grid(row=1, column=0)

        ctk.CTkButton(
            header,
            text="Clear graph",
            width=100,
            height=30,
            corner_radius=7,
            fg_color=COLORS["panel_alt"],
            hover_color=COLORS["panel_hover"],
            text_color=COLORS["red"],
            font=FONT_UI_SMALL,
            command=self.clear,
        ).grid(row=0, column=4, padx=(0, 12))

        body = ctk.CTkFrame(self, fg_color=COLORS["panel"], corner_radius=10)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            body,
            bg=COLORS["panel"],
            highlightthickness=0,
            bd=0,
            takefocus=1,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)

        self.vbar = ctk.CTkScrollbar(
            body,
            orientation="vertical",
            command=self.canvas.yview,
            fg_color=COLORS["panel"],
            button_color=COLORS["slot_border"],
            button_hover_color=COLORS["slot_hover"],
        )
        self.vbar.grid(row=0, column=2, sticky="ns", padx=(4, 4), pady=8)
        self.hbar = ctk.CTkScrollbar(
            body,
            orientation="horizontal",
            command=self.canvas.xview,
            fg_color=COLORS["panel"],
            button_color=COLORS["slot_border"],
            button_hover_color=COLORS["slot_hover"],
        )
        self.hbar.grid(row=1, column=0, columnspan=3, sticky="ew", padx=8, pady=(0, 6))
        self.canvas.configure(
            yscrollcommand=self.vbar.set,
            xscrollcommand=self.hbar.set,
        )

        self.canvas.bind("<Configure>", self._on_configure)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", self._on_leave)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Shift-MouseWheel>", self._on_shift_wheel)
        self.canvas.bind("<Button-4>", lambda _e: self._scroll(1))
        self.canvas.bind("<Button-5>", lambda _e: self._scroll(-1))

        self._show_empty("Выберите предмет, чтобы построить граф")

    # ------------------------------------------------------------------
    def set_target(self, kind: str, item_id: str) -> None:
        item_id = str(item_id or "").strip()
        if not item_id:
            self.clear()
            return
        kind = kind if kind in ("item", "fluid", "tag") else "item"
        self.target = Ingredient(
            kind=kind,
            id=item_id.lstrip("#") if kind == "tag" else item_id,
            amount=1000 if kind == "fluid" else None,
        )
        self.target_slot.set_ingredient(self.target.copy(), notify=False)
        self.refresh(recenter=True)

    def clear(self, *, silent: bool = False) -> None:
        self.target = None
        self.target_slot.clear(notify=False)
        self._show_empty("Граф очищен. Выберите предмет для нового графа")
        if not silent:
            self.app.set_status("Recipe graph cleared")

    def refresh(self, *, recenter: bool = False) -> None:
        if self.target is None or self.target.is_empty:
            self._show_empty("Выберите предмет, чтобы построить граф")
            return
        if not self.app.recipe_index.records:
            self._show_empty(
                "Индекс рецептов пуст. Откройте вкладку Recipes и проиндексируйте "
                "mods / jar / KubeJS."
            )
            return
        self._draw_graph(recenter=recenter)

    # ------------------------------------------------------------------
    def _set_left_depth(self, value: str) -> None:
        self.left_depth = max(1, min(self.MAX_DEPTH, int(value)))
        self.left_depth_menu.set(str(self.left_depth))
        self.refresh(recenter=True)

    def _set_right_depth(self, value: str) -> None:
        self.right_depth = max(1, min(self.MAX_DEPTH, int(value)))
        self.right_depth_menu.set(str(self.right_depth))
        self.refresh(recenter=True)

    def _set_vertical_limit(self, value: str) -> None:
        try:
            limit = int(value)
        except TypeError, ValueError:
            return
        self.vertical_limit = max(1, min(max(self.VERTICAL_VALUES), limit))
        self.vertical_menu.set(str(self.vertical_limit))
        self.refresh(recenter=True)

    def _on_target_changed(self) -> None:
        if self.target_slot.is_empty:
            self.clear(silent=True)
            return
        self.target = self.target_slot.ingredient.copy()
        self.refresh(recenter=True)

    def _on_configure(self, _event=None) -> None:
        if self._redraw_job is not None:
            try:
                self.after_cancel(self._redraw_job)
            except Exception:
                pass
        self._redraw_job = self.after(140, self._redraw_after_resize)

    def _redraw_after_resize(self) -> None:
        self._redraw_job = None
        if self.target is None:
            self._show_empty("Выберите предмет, чтобы построить граф")
        else:
            self.refresh(recenter=False)

    # ------------------------------------------------------------------
    @staticmethod
    def _norm(item_id: str) -> str:
        return str(item_id or "").lstrip("#")

    def _build_maps(self) -> None:
        self._producer_map = {}
        self._consumer_map = {}
        for record in self.app.recipe_index.snapshot():
            for output in dict.fromkeys(record.outputs):
                self._producer_map.setdefault(self._norm(output), []).append(record)
            for input_id in dict.fromkeys(record.inputs):
                self._consumer_map.setdefault(self._norm(input_id), []).append(record)
        for values in (self._producer_map, self._consumer_map):
            for records in values.values():
                records.sort(key=lambda item: (item.display_name or "").lower())

    def _draw_graph(self, *, recenter: bool = False) -> None:
        self.canvas.delete("all")
        self._item_boxes = []
        self._recipe_boxes = []
        self._import_boxes = []
        self._nodes = []
        self._edges = []
        self._hover_key = None
        self.app.tooltip.hide()
        self._build_maps()

        left_rings = self.left_depth * 2
        right_rings = self.right_depth * 2
        left_width = sum(
            self.COL_GAP + (self.CARD_W if ring % 2 else self.ITEM_W)
            for ring in range(1, left_rings + 1)
        )
        right_width = sum(
            self.COL_GAP + (self.CARD_W if ring % 2 else self.ITEM_W)
            for ring in range(1, right_rings + 1)
        )
        leftmost = self.MARGIN
        center_x = leftmost + left_width
        width = center_x + self.CENTER_W + right_width + self.MARGIN
        top = self.MARGIN

        left_pos = {0: center_x}
        cursor = center_x
        for ring in range(1, left_rings + 1):
            cursor -= self.COL_GAP
            cursor -= self.CARD_W if ring % 2 else self.ITEM_W
            left_pos[ring] = cursor
        right_pos = {0: center_x}
        cursor = center_x + self.CENTER_W
        for ring in range(1, right_rings + 1):
            cursor += self.COL_GAP
            right_pos[ring] = cursor
            cursor += self.CARD_W if ring % 2 else self.ITEM_W

        raw_target = ("#" if self.target.kind == "tag" else "") + self.target.id
        key = self._norm(self.target.id)
        left_root = _GNode(
            "item",
            center_x,
            top,
            self.CENTER_W,
            self.CENTER_H,
            raw_target,
            main=True,
        )
        right_root = _GNode(
            "item",
            center_x,
            top,
            self.CENTER_W,
            self.CENTER_H,
            raw_target,
            main=True,
        )
        left_nodes: list[_GNode] = []
        right_nodes: list[_GNode] = []
        left_h, left_root = self._layout_item(
            raw_target,
            0,
            top,
            left_pos,
            direction=-1,
            max_ring=left_rings,
            path=frozenset({key}),
            root=left_root,
            budget=[self.MAX_NODES_PER_SIDE],
            out=left_nodes,
        )
        right_h, right_root = self._layout_item(
            raw_target,
            0,
            top,
            right_pos,
            direction=1,
            max_ring=right_rings,
            path=frozenset({key}),
            root=right_root,
            budget=[self.MAX_NODES_PER_SIDE],
            out=right_nodes,
        )
        height = max(left_h, right_h)
        left_shift = (height - left_h) / 2
        right_shift = (height - right_h) / 2
        for node in left_nodes:
            node.y += left_shift
        for node in right_nodes:
            node.y += right_shift
        left_root.y += left_shift
        right_root.y += right_shift
        self._nodes = left_nodes + right_nodes
        center_y = top + height / 2 - self.CENTER_H / 2

        total_h = top + height + self.MARGIN
        self.canvas.configure(scrollregion=(0, 0, width, total_h))

        for start, end, accent in self._edges:
            self._draw_edge(start, end, accent)

        for node in self._nodes:
            if node.kind == "recipe":
                self._draw_recipe(node)
            else:
                self._draw_item_node(node)
        self._draw_item_node(left_root)

        all_producers = self._producer_map.get(key, [])
        all_consumers = self._consumer_map.get(key, [])
        if not all_producers and not all_consumers:
            self.canvas.create_text(
                center_x + self.CENTER_W / 2,
                center_y + self.CENTER_H + 34,
                text=f"Рецептов с {self.target.id} не найдено",
                fill=COLORS["text_dim"],
                font=("DejaVu Sans", 11),
            )
        self.canvas.update_idletasks()
        if recenter:
            canvas_w = max(1, self.canvas.winfo_width())
            canvas_h = max(1, self.canvas.winfo_height())
            if width > canvas_w:
                cx = center_x + self.CENTER_W / 2
                self.canvas.xview_moveto(
                    max(0.0, min(1.0, (cx - canvas_w / 2) / width))
                )
            else:
                self.canvas.xview_moveto(0)
            if total_h > canvas_h:
                cy = center_y + self.CENTER_H / 2
                self.canvas.yview_moveto(
                    max(0.0, min(1.0, (cy - canvas_h / 2) / total_h))
                )
            else:
                self.canvas.yview_moveto(0)

    # ------------------------------------------------------------------
    def _layout_item(
        self,
        item_id: str,
        ring: int,
        top: float,
        positions: dict[int, float],
        *,
        direction: int,
        max_ring: int,
        path: frozenset[str],
        root: _GNode | None,
        budget: list[int],
        out: list[_GNode],
    ) -> tuple[float, _GNode]:
        key = self._norm(item_id)
        width = self.CENTER_W if ring == 0 else self.ITEM_W
        height = self.CENTER_H if ring == 0 else self.ITEM_H
        node = root or _GNode(
            "item",
            positions[ring],
            top,
            width,
            height,
            item_id,
        )
        if root is None:
            out.append(node)
            budget[0] -= 1

        records = (
            self._producer_map.get(key, [])
            if direction < 0
            else self._consumer_map.get(key, [])
        )
        can_expand = bool(records) and ring + 2 <= max_ring
        if ring > 0:
            can_expand = can_expand and key not in path
        if not can_expand or budget[0] <= 0:
            node.y = top
            return height, node

        limit = max(1, min(self.vertical_limit, budget[0]))
        records = records[:limit]
        y = top
        made = 0
        for record in records:
            if budget[0] <= 1:
                break
            child_items = record.inputs if direction < 0 else record.outputs
            child_items = [child for child in dict.fromkeys(child_items) if child]
            hidden_items = max(0, len(child_items) - self.vertical_limit)
            child_items = child_items[: self.vertical_limit]
            child_nodes: list[_GNode] = []
            child_top = y
            for child in child_items:
                if budget[0] <= 1:
                    break
                child_h, child_node = self._layout_item(
                    child,
                    ring + 2,
                    child_top,
                    positions,
                    direction=direction,
                    max_ring=max_ring,
                    path=path | {key},
                    root=None,
                    budget=budget,
                    out=out,
                )
                child_nodes.append(child_node)
                child_top += child_h + self.ROW_GAP
            child_total = max(0.0, child_top - y - (self.ROW_GAP if child_nodes else 0))
            block_h = max(self.CARD_H, child_total)
            recipe = _GNode(
                "recipe",
                positions[ring + 1],
                y + (block_h - self.CARD_H) / 2,
                self.CARD_W,
                self.CARD_H,
                record=record,
                relation=(
                    "производит этот предмет"
                    if direction < 0
                    else "использует этот предмет"
                ),
                hidden_items=hidden_items,
            )
            out.append(recipe)
            budget[0] -= 1
            for child_node in child_nodes:
                if direction < 0:
                    self._edges.append((child_node, recipe, False))
                else:
                    self._edges.append((recipe, child_node, False))
            if direction < 0:
                self._edges.append((recipe, node, True))
            else:
                self._edges.append((node, recipe, True))
            y += block_h + self.ROW_GAP
            made += 1

        total = y - top - (self.ROW_GAP if made else 0)
        node.y = top + (max(height, total) - height) / 2
        return max(height, total), node

    def _draw_edge(self, start: _GNode, end: _GNode, accent: bool) -> None:
        if start.x <= end.x:
            x0, y0 = start.x + start.w, start.y + start.h / 2
            x1, y1 = end.x, end.y + end.h / 2
        else:
            x0, y0 = start.x, start.y + start.h / 2
            x1, y1 = end.x + end.w, end.y + end.h / 2
        self.canvas.create_line(
            x0,
            y0,
            x1,
            y1,
            fill=COLORS["accent_2"] if accent else COLORS["slot_border"],
            width=2 if accent else 1,
            arrow=tk.LAST,
            arrowshape=(8, 10, 4),
        )

    # ------------------------------------------------------------------
    def _item_kind(self, item_id: str) -> tuple[str, str]:
        if str(item_id).startswith("#"):
            return "tag", str(item_id)[1:]
        if str(item_id) in getattr(self.app.catalog, "fluids_by_id", {}):
            return "fluid", str(item_id)
        return "item", str(item_id)

    def _icon(self, kind: str, item_id: str, size: int):
        ing = Ingredient(
            kind=kind,
            id=item_id,
            amount=1000 if kind == "fluid" else None,
        )
        photo = self.app.icons.get_ingredient(ing, self.app.catalog, size)
        if photo is not None:
            self._photos[("ing", kind, item_id, size)] = photo
        return photo

    def _draw_item_node(self, node: _GNode) -> None:
        kind, clean_id = self._item_kind(node.item_id)
        fill = COLORS["panel_hover"] if node.main else COLORS["panel_alt"]
        outline = COLORS["accent"] if node.main else COLORS["border"]
        self.canvas.create_rectangle(
            node.x,
            node.y,
            node.x + node.w,
            node.y + node.h,
            fill=fill,
            outline=outline,
            width=2 if node.main else 1,
        )
        icon_size = 34 if node.main else 28
        photo = self._icon(kind, clean_id, icon_size)
        if photo is not None:
            self.canvas.create_image(
                node.x + 8 + icon_size / 2,
                node.y + node.h / 2,
                image=photo,
            )
        else:
            self.canvas.create_text(
                node.x + 8 + icon_size / 2,
                node.y + node.h / 2,
                text="#",
                fill=COLORS["purple"] if kind == "tag" else COLORS["text_dim"],
                font=("DejaVu Sans", 12, "bold"),
            )
        name = self.app.names.get(clean_id) or clean_id
        display_id = ("#" if kind == "tag" else "") + clean_id
        text_x = node.x + 14 + icon_size
        available = max(30, int((node.w - (text_x - node.x) - 8) / 6.2))
        self.canvas.create_text(
            text_x,
            node.y + node.h / 2 - 8,
            anchor="w",
            text=self._truncate(name, available),
            fill=COLORS["text"],
            font=("DejaVu Sans", 10, "bold" if node.main else "normal"),
        )
        self.canvas.create_text(
            text_x,
            node.y + node.h / 2 + 9,
            anchor="w",
            text=self._truncate(display_id, available),
            fill=COLORS["text_dim"],
            font=("DejaVu Sans", 8),
        )
        self._item_boxes.append(
            _Box(
                node.x,
                node.y,
                node.x + node.w,
                node.y + node.h,
                kind,
                clean_id,
                "item",
            )
        )

    def _draw_recipe(self, node: _GNode) -> None:
        record = node.record
        if record is None:
            return
        self.canvas.create_rectangle(
            node.x,
            node.y,
            node.x + node.w,
            node.y + node.h,
            fill=COLORS["panel_alt"],
            outline=COLORS["border"],
        )
        title = self.app.module_title(record.module_id) or record.type_id
        photo = self._module_icon(record.module_id, 26)
        text_x = node.x + 40 if photo is not None else node.x + 10
        if photo is not None:
            self.canvas.create_image(node.x + 21, node.y + 22, image=photo)
        self.canvas.create_text(
            text_x,
            node.y + 9,
            anchor="nw",
            text=self._truncate(title, 38),
            fill=COLORS["text"],
            font=("DejaVu Sans", 10, "bold"),
        )
        subtitle = record.recipe_id or record.display_name or record.type_id
        self.canvas.create_text(
            node.x + 10,
            node.y + 32,
            anchor="nw",
            text=self._truncate(subtitle, 40),
            fill=COLORS["text_dim"],
            font=("DejaVu Sans", 8),
        )
        relation_text = node.relation
        if node.hidden_items:
            relation_text += f" · +{node.hidden_items}"
        self.canvas.create_text(
            node.x + 10,
            node.y + 53,
            anchor="nw",
            text=self._truncate(relation_text, 34),
            fill=COLORS["accent_2"] if record.importable else COLORS["text_dim"],
            font=("DejaVu Sans", 8),
        )

        if record.module_id:
            bx0, by0 = node.x + node.w - 74, node.y + node.h - 23
            bx1, by1 = node.x + node.w - 8, node.y + node.h - 6
            color = COLORS["accent"] if record.importable else COLORS["slot_border"]
            self.canvas.create_rectangle(
                bx0,
                by0,
                bx1,
                by1,
                fill=COLORS["panel"],
                outline=COLORS["border"],
            )
            self.canvas.create_text(
                (bx0 + bx1) / 2,
                (by0 + by1) / 2,
                text="Import",
                fill=color,
                font=("DejaVu Sans", 8, "bold"),
            )
            self._import_boxes.append(
                _Box(bx0, by0, bx1, by1, "import", record, node.relation)
            )
        self._recipe_boxes.append(
            _Box(
                node.x,
                node.y,
                node.x + node.w,
                node.y + node.h,
                "recipe",
                record,
                node.relation,
                hidden=node.hidden_items,
            )
        )

    def _module_icon(self, module_id: str, size: int):
        if Image is None or ImageTk is None:
            return None
        module = next((m for m in self.app.modules if m.id == module_id), None)
        path = getattr(module, "icon", None) if module is not None else None
        if path is None:
            return None
        key = ("module", str(path), size)
        if key in self._photos:
            return self._photos[key]
        try:
            with Image.open(path) as source:
                image = source.convert("RGBA")
                image = image.resize((size, size), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            self._photos[key] = photo
            return photo
        except Exception:
            return None

    @staticmethod
    def _truncate(text: str, max_chars: int) -> str:
        text = str(text)
        if max_chars <= 1:
            return ""
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 1] + "…"

    # ------------------------------------------------------------------
    def _show_empty(self, text: str) -> None:
        self.canvas.delete("all")
        self._item_boxes = []
        self._recipe_boxes = []
        self._import_boxes = []
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        self.canvas.configure(scrollregion=(0, 0, width, height))
        self.canvas.create_text(
            width / 2,
            max(90, height / 2),
            text=text,
            fill=COLORS["text_dim"],
            font=("DejaVu Sans", 12),
            justify="center",
            width=max(320, width - 120),
        )

    # ------------------------------------------------------------------
    def _hit(self, boxes, x: float, y: float):
        for box in reversed(boxes):
            if box.x0 <= x <= box.x1 and box.y0 <= y <= box.y1:
                return box
        return None

    def _on_motion(self, event) -> None:
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        box = self._hit(self._import_boxes, x, y)
        key = None
        text = ""
        if box is not None:
            record = box.value
            key = ("import", record.key)
            text = f"Import в редактор\n{record.recipe_id or record.display_name}"
        else:
            box = self._hit(self._recipe_boxes, x, y)
            if box is not None:
                key = ("recipe", box.value.key, box.relation, box.hidden)
                text = self._recipe_tooltip(box.value, box.relation, box.hidden)
            else:
                box = self._hit(self._item_boxes, x, y)
                if box is not None:
                    key = ("item", box.kind, box.value)
                    name = self.app.names.get(box.value) or box.value
                    text = f"{name}\n{box.value}\nНажмите, чтобы построить граф"
        if key != self._hover_key:
            self._hover_key = key
            if text:
                self.app.tooltip.show(text)
            else:
                self.app.tooltip.hide()

    def _on_leave(self, _event=None) -> None:
        self._hover_key = None
        self.app.tooltip.hide()

    def _on_click(self, event) -> str:
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        box = self._hit(self._import_boxes, x, y)
        if box is not None:
            return self._import_record(box.value)
        box = self._hit(self._item_boxes, x, y)
        if box is not None:
            self.app.tooltip.hide()
            self.set_target(box.kind, box.value)
            self.app.set_status(f"Recipe graph · {box.value}")
            return "break"
        return "break"

    def _on_double_click(self, event) -> str:
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        box = self._hit(self._recipe_boxes, x, y)
        if box is not None:
            return self._import_record(box.value)
        return "break"

    def _import_record(self, record: RecipeRecord) -> str:
        self.app.tooltip.hide()
        if record.import_error:
            self.app.set_status(f"Import failed: {record.import_error}", error=True)
            return "break"
        self.app.import_indexed_recipe(record, switch=True)
        return "break"

    def _recipe_tooltip(
        self, record: RecipeRecord, relation: str, hidden: int = 0
    ) -> str:
        title = self.app.module_title(record.module_id) or record.type_id
        lines = [title, f"Тип: {record.type_id}"]
        lines.append(f"ID: {record.recipe_id or '—'}")
        lines.append(f"Источник: {record.source_group} · {record.source_detail}")
        if record.target_mod:
            lines.append(f"Target: {record.target_mod}")
        lines.append("Вход: " + (", ".join(record.inputs) or "—"))
        lines.append("Выход: " + (", ".join(record.outputs) or "—"))
        lines.append(f"В графе: {relation}")
        if hidden:
            lines.append(
                f"Скрыто по вертикальному лимиту: {hidden} (V={self.vertical_limit})"
            )
        if record.importable:
            lines.append("Import: доступен")
        elif record.module_id:
            lines.append(f"Import: ошибка — {record.import_error or 'нет данных'}")
        else:
            lines.append("Import: тип не поддерживается редактором")
        if record.kind in ("jar", "zipjar"):
            lines.append(f"Файл: {record.path}")
            if record.member:
                lines.append(f"Запись: {record.member}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    def _on_wheel(self, event) -> str:
        if event.state & 0x0001:
            self.canvas.xview_scroll(-1 if event.delta > 0 else 1, "units")
        elif event.delta:
            self._scroll(1 if event.delta > 0 else -1)
        return "break"

    def _on_shift_wheel(self, event) -> str:
        self.canvas.xview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _scroll(self, delta: int) -> str:
        self.canvas.yview_scroll(-delta, "units")
        return "break"
