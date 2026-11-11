"""Main application window and wiring."""

from __future__ import annotations

import threading
import tkinter as tk

import customtkinter as ctk

from RecipeStudio.components.drag_manager import DragManager
from RecipeStudio.components.export_panel import ExportPanel
from RecipeStudio.components.item_grid import ItemGrid
from RecipeStudio.components.search_bar import SearchBar
from RecipeStudio.components.slot import Slot, SlotSettingsDialog
from RecipeStudio.components.tooltip import Tooltip
from RecipeStudio.config import Config
from RecipeStudio.model.ingredient import Ingredient
from RecipeStudio.recipes.base import EditorContext
from RecipeStudio.recipes.registry import discover_modules
from RecipeStudio.services.catalog import Catalog, CatalogEntry
from RecipeStudio.services.codegen import build_export
from RecipeStudio.services.favorites import Favorites
from RecipeStudio.services.icons import IconCache
from RecipeStudio.services.names import NameResolver
from RecipeStudio.services.search import SearchGateway, SearchMode, SearchUnavailable
from RecipeStudio.theme import COLORS, FONT_UI, FONT_UI_SMALL, FONT_UI_BOLD


class RecipeStudioApp(ctk.CTk):
    def __init__(self, config: Config):
        super().__init__(fg_color=COLORS["bg"])
        self.config = config
        self.title("Recipe Studio")
        self.geometry("1440x920")
        self.minsize(1000, 700)
        self._center()

        self.catalog = Catalog(config)
        self.names = NameResolver(config)
        self.icons = IconCache(config.path_for("icons_dir"))
        self.favorites = Favorites(config.path_for("favorites"))
        self.search_gateway = SearchGateway(config, self.catalog)
        self.tooltip = Tooltip(self)
        self.drag_manager = DragManager(self)

        self.palette_selection: CatalogEntry | None = None
        self.hovered_entry: CatalogEntry | None = None
        self.hovered_slot: Slot | None = None
        self.drag_target_slot: Slot | None = None
        self.registered_slots: list[Slot] = []
        self.editors: dict[str, object] = {}
        self.current_module = None
        self.current_editor = None
        self.modules, self.module_errors = discover_modules(config)
        self.editor_ctx = EditorContext(
            app=self,
            catalog=self.catalog,
            names=self.names,
            icons=self.icons,
            config=config,
        )
        self._all_entries: list[CatalogEntry] = []
        self._search_gen = 0
        self.favorites_only = False
        self._tab_images: list[ctk.CTkImage] = []

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._build_ui()
        self._bind_hotkeys()

        self.after(80, self.show_all_items)
        self.after(250, self._load_names_async)
        if self.modules:
            self.show_module(self.modules[0])
        else:
            self.set_status("No recipe modules found", error=True)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    def _center(self) -> None:
        self.update_idletasks()
        w, h = 1440, 920
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self) -> None:
        self.paned = tk.PanedWindow(
            self,
            orient="horizontal",
            sashwidth=6,
            bd=0,
            bg=COLORS["bg"],
            sashrelief=tk.FLAT,
        )
        self.paned.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 0))

        left = ctk.CTkFrame(self.paned, fg_color=COLORS["panel"], corner_radius=10)
        right = ctk.CTkFrame(self.paned, fg_color=COLORS["panel"], corner_radius=10)
        self.paned.add(left, minsize=360, width=520)
        self.paned.add(right, minsize=620)

        # ---- left: palette ------------------------------------------------
        left.grid_rowconfigure(2, weight=1)
        left.grid_columnconfigure(0, weight=1)
        header = ctk.CTkFrame(left, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            header,
            text="ITEM PALETTE",
            text_color=COLORS["text_muted"],
            font=("DejaVu Sans", 10, "bold"),
        ).grid(row=0, column=0, sticky="w")
        self.count_label = ctk.CTkLabel(
            header,
            text="",
            text_color=COLORS["text_dim"],
            font=FONT_UI_SMALL,
        )
        self.count_label.grid(row=0, column=1, sticky="e")

        self.fav_button = ctk.CTkButton(
            header,
            text="★",
            width=28,
            height=22,
            corner_radius=6,
            fg_color=COLORS["panel_alt"],
            hover_color=COLORS["panel_hover"],
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 13, "bold"),
            command=self.toggle_favorites_only,
        )
        self.fav_button.grid(row=0, column=2, sticky="e", padx=(8, 0))
        self._update_fav_button()

        self.search_bar = SearchBar(left, self)
        self.search_bar.grid(row=1, column=0, sticky="ew", padx=12, pady=(2, 8))

        self.item_grid = ItemGrid(left, self)
        self.item_grid.grid(row=2, column=0, sticky="nsew", padx=(8, 4), pady=(0, 2))

        ctk.CTkLabel(
            left,
            text="Click to select · drag to a slot · A favourite · Ctrl+A / ★ favourites · Esc exits",
            text_color=COLORS["text_dim"],
            font=("DejaVu Sans", 9),
        ).grid(row=3, column=0, pady=(2, 8))

        # ---- right: tabs, editor, export --------------------------------
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)
        self.tabbar = ctk.CTkScrollableFrame(
            right,
            orientation="horizontal",
            height=44,
            fg_color="transparent",
            scrollbar_fg_color=COLORS["panel"],
            scrollbar_button_color=COLORS["slot_border"],
            scrollbar_button_hover_color=COLORS["slot_hover"],
        )
        self.tabbar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))
        self.tab_buttons: dict[str, ctk.CTkButton] = {}
        for module in self.modules:
            image = self._load_tab_icon(module)
            width = max(80, len(module.title) * 8 + 26) + (24 if image else 0)
            btn = ctk.CTkButton(
                self.tabbar,
                text=module.title,
                image=image,
                compound="left",
                anchor="w",
                height=30,
                width=width,
                corner_radius=8,
                fg_color=COLORS["panel_alt"],
                hover_color=COLORS["panel_hover"],
                text_color=COLORS["text"],
                font=FONT_UI_SMALL,
                command=lambda m=module: self.show_module(m),
            )
            btn.pack(side="left", padx=2, pady=2)
            self.tab_buttons[module.id] = btn

        self.editor_container = ctk.CTkFrame(right, fg_color="transparent")
        self.editor_container.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 4))
        self.editor_container.grid_rowconfigure(0, weight=1)
        self.editor_container.grid_columnconfigure(0, weight=1)

        self.export_panel = ExportPanel(right, self)
        self.export_panel.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))

        self.status_label = ctk.CTkLabel(
            self,
            text="",
            anchor="w",
            text_color=COLORS["text_dim"],
            font=FONT_UI_SMALL,
        )
        self.status_label.grid(row=1, column=0, sticky="ew", padx=14, pady=(2, 6))

    # ------------------------------------------------------------------
    def _load_tab_icon(self, module):
        path = getattr(module, "icon", None)
        if path is None:
            return None
        try:
            from PIL import Image

            with Image.open(path) as source:
                image = source.convert("RGBA")
            ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=(18, 18))
            self._tab_images.append(ctk_image)
            return ctk_image
        except Exception:
            return None

    # ------------------------------------------------------------------
    def show_module(self, module) -> None:
        if self.current_module is module:
            return
        if self.current_editor is not None:
            try:
                self.current_editor.grid_remove()
            except Exception:
                pass
        editor = self.editors.get(module.id)
        if editor is None:
            try:
                editor = module.create_editor(self.editor_container, self.editor_ctx)
            except Exception as exc:
                self.set_status(f"Failed to open {module.title}: {exc}", error=True)
                return
            editor.grid(row=0, column=0, sticky="nsew")
            self.editors[module.id] = editor
        else:
            editor.grid()
        self.current_module = module
        self.current_editor = editor
        for module_id, btn in self.tab_buttons.items():
            if module_id == module.id:
                btn.configure(fg_color=COLORS["accent"], text_color=COLORS["panel"])
            else:
                btn.configure(fg_color=COLORS["panel_alt"], text_color=COLORS["text"])
        self.export_panel.clear_override()
        self.update_export()
        self.set_status(module.description or module.title)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def on_search_text(self, query: str) -> None:
        if not query:
            self.show_all_items()
            return
        mode = self.search_bar.mode
        self._search_gen += 1
        gen = self._search_gen
        self.set_status(f"Searching ({mode})…")
        limit = int(self.config.get("search_limit", 500))

        def worker():
            try:
                hits = self.search_gateway.search(query, mode, limit)
            except SearchUnavailable as exc:
                self._post(lambda: self._search_failed(gen, str(exc)))
            except Exception as exc:
                self._post(
                    lambda: self._search_failed(gen, f"{type(exc).__name__}: {exc}")
                )
            else:
                self._post(lambda: self._search_done(gen, hits, mode))

        threading.Thread(target=worker, daemon=True).start()

    def _post(self, callback) -> None:
        """Schedule a callback from a worker thread, ignoring shutdown."""
        try:
            self.after(0, callback)
        except RuntimeError, tk.TclError:
            pass

    def _search_done(self, gen: int, hits, mode: str) -> None:
        if gen != self._search_gen:
            return
        self._all_entries = [hit.entry for hit in hits]
        entries = self._filtered(self._all_entries)
        self.item_grid.set_entries(entries)
        suffix = " · favourites" if self.favorites_only else ""
        self.set_status(f"{len(entries)} results · mode {mode}{suffix}")

    def _search_failed(self, gen: int, message: str) -> None:
        if gen != self._search_gen:
            return
        self.set_status(message, error=True)

    def on_mode_changed(self, mode: str) -> None:
        self.set_status(SearchMode.LABELS.get(mode, mode))
        query = self.search_bar.get_query()
        if query:
            self.on_search_text(query)
        else:
            self.show_all_items()

    def show_all_items(self) -> None:
        self._search_gen += 1
        self._all_entries = self.catalog.search_items()
        entries = self._filtered(self._all_entries)
        self.item_grid.set_entries(entries)
        suffix = " · favourites" if self.favorites_only else ""
        self.count_label.configure(text=f"{len(entries)} items")
        self.set_status(f"{len(entries)} items{suffix}")

    def _filtered(self, entries: list[CatalogEntry]) -> list[CatalogEntry]:
        if not self.favorites_only:
            return entries
        return [e for e in entries if self.favorites.is_fav(e.id)]

    # ------------------------------------------------------------------
    # Palette / slots
    # ------------------------------------------------------------------
    def select_palette(self, entry: CatalogEntry) -> None:
        if self.palette_selection is not None and self.palette_selection.id == entry.id:
            self.palette_selection = None
            self.item_grid.set_selected(None)
            self.set_status("Selection cleared")
            return
        self.palette_selection = entry
        self.item_grid.set_selected(entry.id)
        self.set_status(f"Selected {entry.id} — click a slot or drag it there")

    def on_slot_left_click(self, slot: Slot) -> None:
        if self.palette_selection is not None:
            slot.set_from_entry(self.palette_selection)
            return
        if not slot.is_empty:
            slot.clear()
            return
        self.open_slot_settings(slot)

    def open_slot_settings(self, slot: Slot) -> None:
        SlotSettingsDialog(slot)
        self.update_export()

    def register_slot(self, slot: Slot) -> None:
        if slot not in self.registered_slots:
            self.registered_slots.append(slot)

    def find_slot_at(self, x_root: int, y_root: int) -> Slot | None:
        for slot in reversed(self.registered_slots):
            try:
                if not slot.winfo_exists() or not slot.winfo_ismapped():
                    continue
                x = slot.winfo_rootx()
                y = slot.winfo_rooty()
                w = slot.winfo_width()
                h = slot.winfo_height()
            except tk.TclError:
                continue
            if x <= x_root <= x + w and y <= y_root <= y + h:
                return slot
        return None

    def highlight_drop_target(self, slot: Slot | None) -> None:
        if self.drag_target_slot is slot:
            return
        if self.drag_target_slot is not None:
            try:
                self.drag_target_slot.set_drop_target(False)
            except Exception:
                pass
        self.drag_target_slot = slot
        if slot is not None:
            try:
                slot.set_drop_target(True)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Favourites
    # ------------------------------------------------------------------
    def toggle_favorite(self, entry: CatalogEntry) -> None:
        added = self.favorites.toggle(entry.id)
        self.item_grid.refresh()
        self.set_status(
            ("Added to" if added else "Removed from") + f" favourites: {entry.id}"
        )
        if self.favorites_only and not added:
            self.show_all_items()

    def toggle_favorites_only(self) -> None:
        self.favorites_only = not self.favorites_only
        entries = self._filtered(self._all_entries)
        self.item_grid.set_entries(entries)
        self._update_fav_button()
        self.set_status(
            f"Showing {len(entries)} favourites"
            if self.favorites_only
            else f"{len(entries)} items"
        )

    def _update_fav_button(self) -> None:
        if not hasattr(self, "fav_button"):
            return
        self.fav_button.configure(
            fg_color=COLORS["accent"] if self.favorites_only else COLORS["panel_alt"],
            text_color=COLORS["panel"] if self.favorites_only else COLORS["text_dim"],
        )

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    def _compute_export(self, force_remove: bool = False):
        editor = self.current_editor
        if editor is None:
            return "", ["No recipe tab open"], "", None
        errors = list(editor.validate())
        try:
            body = editor.serialize("event")
        except Exception as exc:
            body = ""
            errors.append(f"{type(exc).__name__}: {exc}")

        remove = bool(self.export_panel.remove_var.get() or force_remove)
        wrap = bool(self.export_panel.wrap_var.get() or remove)
        override = self.export_panel.get_override()
        main = editor.main_output()
        remove_filter = (
            override if override is not None and not override.is_empty else main
        )
        if remove and (remove_filter is None or remove_filter.is_empty):
            errors.append("No output item to use for removal")
            remove_filter = None
        code = build_export(body, remove_filter if remove else None, wrap=wrap)
        return code, errors, body, remove_filter if remove else None

    def update_export(self) -> None:
        if not hasattr(self, "export_panel"):
            return
        code, errors, _body, effective = self._compute_export(False)
        self.export_panel.set_code(code)
        self.export_panel.set_errors(errors)
        self.export_panel.set_effective(effective)

    def copy_export(self, force_remove: bool = False) -> None:
        code, errors, body, _effective = self._compute_export(force_remove)
        self.export_panel.set_code(code)
        self.export_panel.set_errors(errors)
        if not body or not code:
            self.set_status("Nothing to export yet", error=True)
            return
        self.clipboard_clear()
        self.clipboard_append(code)
        self.update_idletasks()
        self.set_status("Copied recipe" + (" with removal" if force_remove else ""))

    def clear_editor(self) -> None:
        if self.current_editor is None:
            return
        self.current_editor.clear()
        self.export_panel.clear_override()
        self.update_export()
        self.set_status("Editor cleared")

    def on_editor_changed(self, _editor=None) -> None:
        self.update_export()

    # ------------------------------------------------------------------
    # Hotkeys
    # ------------------------------------------------------------------
    def _bind_hotkeys(self) -> None:
        for sequence in ("<Control-f>", "<Control-F>"):
            self.bind_all(sequence, self._hotkey_focus_or_mode, add="+")
        for sequence in ("<Control-e>", "<Control-E>"):
            self.bind_all(sequence, self._hotkey_export, add="+")
        for sequence in ("<Control-a>", "<Control-A>"):
            self.bind_all(sequence, self._hotkey_favourites, add="+")
        for sequence in ("<KeyPress-a>", "<KeyPress-A>"):
            self.bind_all(sequence, self._hotkey_toggle_fav, add="+")
        for sequence in ("<KeyPress-plus>", "<KeyPress-equal>", "<KP_Add>"):
            self.bind_all(sequence, lambda e: self._hotkey_count(1), add="+")
        for sequence in ("<KeyPress-minus>", "<KP_Subtract>"):
            self.bind_all(sequence, lambda e: self._hotkey_count(-1), add="+")
        self.bind_all("<Escape>", self._hotkey_escape, add="+")

    def _is_text_focus(self) -> bool:
        try:
            w = self.focus_get()
        except Exception:
            return False
        if w is None:
            return False
        try:
            return w.winfo_class() in ("Entry", "TEntry", "Text", "Spinbox")
        except Exception:
            return False

    def _hotkey_focus_or_mode(self, event):
        if event.state & 0x0001:  # Shift
            self.search_bar.cycle_mode()
        else:
            self.search_bar.focus_search()
        return "break"

    def _hotkey_export(self, event):
        force = bool(event.state & 0x0001)
        self.copy_export(force)
        return "break"

    def _hotkey_favourites(self, event):
        if self._is_text_focus():
            return None
        self.toggle_favorites_only()
        return "break"

    def _hotkey_toggle_fav(self, event):
        if event.state & 0x0004:  # Control
            return None
        if self._is_text_focus():
            return None
        if self.hovered_entry is not None:
            self.toggle_favorite(self.hovered_entry)
            return "break"
        return None

    def _hotkey_count(self, delta: int):
        if self._is_text_focus():
            return None
        if self.hovered_slot is not None:
            self.hovered_slot.adjust_count(delta)
            return "break"
        return None

    def _hotkey_escape(self, _event=None):
        if self.search_bar.is_focused():
            self.focus_grid()
            return "break"
        if self.palette_selection is not None:
            self.palette_selection = None
            self.item_grid.set_selected(None)
            return "break"
        if self.favorites_only:
            self.toggle_favorites_only()
            return "break"
        return None

    def focus_grid(self) -> None:
        self.item_grid.focus()

    # ------------------------------------------------------------------
    def item_tooltip_text(self, entry: CatalogEntry) -> str:
        name = self.names.get(entry.id)
        star = " ★" if self.favorites.is_fav(entry.id) else ""
        kind = " (fluid)" if entry.kind == "fluid" else ""
        return f"{name}{star}\n{entry.id}{kind}"

    def set_status(self, text: str, *, error: bool = False) -> None:
        if not hasattr(self, "status_label"):
            return
        self.status_label.configure(
            text=text,
            text_color=COLORS["red"] if error else COLORS["text_dim"],
        )

    # ------------------------------------------------------------------
    def _load_names_async(self) -> None:
        def worker():
            try:
                rebuilt = self.names.build_if_needed()
            except Exception:
                rebuilt = False
            self._post(lambda: self._names_loaded(rebuilt))

        threading.Thread(target=worker, daemon=True).start()

    def _names_loaded(self, rebuilt: bool) -> None:
        if rebuilt:
            self.set_status(f"Name cache ready ({len(self.names.names)} names)")

    def _on_close(self) -> None:
        try:
            self.drag_manager.cleanup()
        except Exception:
            pass
        self.destroy()
