"""Manage a reusable grocery catalogue without adding its prices to a budget."""

from collections.abc import Callable
import tkinter as tk
from tkinter import font, messagebox, ttk

from classes.custom_tk_components.tk_document_input_class import BACKGROUND, BORDER, INK, MUTED, document_button
from classes.custom_tk_components.tk_link_class import TkLink
from classes.custom_tk_components.tk_table_class import TkTable
from classes.grocery_catalog_item_class import GroceryCatalogItem
from classes.grocery_unit_class import GroceryUnit
from classes.managers.grocery_catalog_manager import GroceryCatalogManager
from classes.pages.leaf_page_class import LeafPage
from classes.table_column_class import TableColumn


class GroceryItemsPage(LeafPage):
    def __init__(self, parent_root: tk.Misc, parent_next_method: Callable, on_back: Callable | None = None,
                 catalog_manager: GroceryCatalogManager | None = None):
        self._catalog_manager = catalog_manager if catalog_manager is not None else GroceryCatalogManager()
        self._on_back = on_back
        self._items = []
        self._units = []
        self._unit_load_error = None
        self._units_window = None
        self._units_table = None
        self._unit_being_edited = None
        self._load_error = None
        self._item_table = None
        self._editor = None
        self._reload_items()
        super().__init__(parent_root, parent_next_method)

    @property
    def items(self) -> tuple[GroceryCatalogItem, ...]:
        return tuple(self._items)

    def activate(self):
        super().activate()
        self._reload_items()
        self._refresh()

    def _reload_items(self):
        try:
            self._units = self._catalog_manager.units_manager.load()
        except (OSError, ValueError) as error:
            self._unit_load_error = self._load_error = str(error)
            return
        self._unit_load_error = None
        try:
            self._items = self._catalog_manager.load()
        except (OSError, ValueError) as error:
            self._load_error = str(error)
        else:
            self._load_error = None

    def _reload_and_refresh(self):
        selected = self._selected_unit_id()
        self._reload_items()
        self._refresh()
        self._refresh_unit_selector(selected)
        if self._units_window is not None and self._units_window.winfo_exists():
            self._refresh_units_window()

    def _setup_components(self):
        self._root.configure(bg=BACKGROUND)
        self._root.columnconfigure(0, weight=1)
        self._root.rowconfigure(2, weight=1)
        default = font.nametofont("TkDefaultFont", root=self._root).actual()
        self._normal_font = (default["family"], default["size"])
        self._bold_font = (*self._normal_font, "bold")
        header = tk.Frame(self._root, bg=BACKGROUND)
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 16))
        header.columnconfigure(0, weight=1)
        tk.Label(header, text="BUDGET PLANNING · STEP 1 · GROCERIES 1 OF 2", bg=BACKGROUND, fg=MUTED,
                 anchor="w", font=self._bold_font).grid(row=0, column=0, sticky="ew")
        tk.Label(header, text="Grocery Items", bg=BACKGROUND, fg=INK, anchor="w",
                 font=(default["family"], default["size"] + 7, "bold")).grid(
            row=1, column=0, sticky="ew", pady=(5, 0))
        tk.Label(header, text="Keep grocery names, prices, case sizes, and product links handy.",
                 bg=BACKGROUND, fg=MUTED, anchor="w").grid(row=2, column=0, sticky="ew", pady=(8, 0))

        toolbar = tk.Frame(self._root, bg=BACKGROUND)
        toolbar.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        toolbar.columnconfigure(0, weight=1)
        self._items_heading = tk.Label(toolbar, bg=BACKGROUND, fg=INK, font=self._bold_font, anchor="w")
        self._items_heading.grid(row=0, column=0, sticky="ew")
        document_button(toolbar, "Reload Items", self._reload_and_refresh).grid(row=0, column=1, padx=8)
        document_button(toolbar, "Manage Units", self._show_units_manager).grid(row=0, column=2, padx=(0, 8))
        self._add_button = document_button(toolbar, "+ Add Item", self._show_item_editor, primary=True)
        self._add_button.grid(row=0, column=3)

        footer = tk.Frame(self._root, bg=BACKGROUND)
        footer.grid(row=3, column=0, sticky="ew", padx=20, pady=(12, 18))
        footer.columnconfigure(1, weight=1)
        self._status = tk.Label(footer, bg=BACKGROUND, fg=MUTED, anchor="w", justify="left")
        self._status.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        if self._on_back is not None:
            self._back_button = document_button(footer, "Back", self._on_back)
            self._back_button.configure(height=2, pady=1)
            self._back_button.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        self._continue_button = document_button(footer, "Continue to Price Updates", self._finalize, primary=True)
        self._continue_button.configure(height=2, pady=1)
        self._continue_button.grid(row=1, column=1, sticky="ew")
        self._refresh()

    def _refresh(self):
        self._items_heading.configure(text=f"Your groceries ({len(self._items)})")
        self._status.configure(text=self._load_error or "Changes are saved automatically. Linked product prices are updated on the next page.",
                               fg="#B91C1C" if self._load_error else MUTED)
        self._add_button.configure(state="disabled" if self._load_error else "normal")
        if self._item_table is not None:
            self._item_table.destroy()
        self._item_table = table = TkTable(self._root, review_style=True, stretch_column=0, columns=[
            TableColumn("Name", tk.Widget), TableColumn("Price", tk.Widget),
            TableColumn("Units per Case", str), TableColumn("Actions", tk.Widget)])
        table.grid(row=2, column=0, sticky="nsew", padx=20)
        for item in self._items:
            name = TkLink(table._body, text=item.name, url=item.link) if item.link else tk.Label(table._body, text=item.name)
            price = tk.Label(table._body, text=f"${item.price:,.2f}")
            actions = tk.Frame(table._body)
            edit = document_button(actions, "Edit", lambda item=item: self._show_item_editor(item))
            edit.pack(side="left", padx=(0, 6))
            delete = document_button(actions, "Delete", lambda item=item: self._delete_item(item))
            delete.configure(bg="#FEE2E2", fg="#B91C1C", activebackground="#FECACA", activeforeground="#B91C1C")
            delete.pack(side="left")
            if self._load_error:
                edit.configure(state="disabled")
                delete.configure(state="disabled")
            actions.update_idletasks()
            unit = next((unit for unit in self._units if unit.unit_id == item.unit_id), None)
            quantity = f"{item.units_per_case} {unit.for_count(item.units_per_case)}" if unit else str(item.units_per_case)
            table.add_row((name, price, quantity, actions))
            price.configure(anchor="e")
            if item.link:
                name.configure(fg="#0B57D0", font=(*self._normal_font, "underline"))
        if not self._items:
            text = "Saved items could not be loaded. Resolve the error, then click Reload Items." if self._load_error else (
                "No grocery items yet\nAdd an item to start your list.")
            tk.Label(table._body, text=text, bg="white", fg=MUTED, justify="center", padx=24, pady=40).grid(
                row=0, column=0, columnspan=len(table.columns), sticky="ew")

    def _commit_items(self, items: list[GroceryCatalogItem]) -> bool:
        try:
            self._catalog_manager.save(items)
        except (OSError, ValueError) as error:
            messagebox.showerror("Could not save grocery items", str(error), parent=self._root)
            return False
        self._items = items
        self._refresh()
        return True

    def _delete_item(self, item: GroceryCatalogItem):
        if self._load_error:
            return
        if messagebox.askyesno("Delete grocery item?", f'Delete "{item.name}" from your grocery list?',
                              parent=self._root, default="no"):
            self._commit_items([other for other in self._items if other.item_id != item.item_id])

    def _show_item_editor(self, item: GroceryCatalogItem | None = None):
        if self._load_error:
            return None
        if self._editor is not None and self._editor.winfo_exists():
            self._editor.lift()
            return self._editor
        window = self._editor = tk.Toplevel(self._root)
        window.title("Edit Grocery Item" if item else "Add Grocery Item")
        window.transient(self._root.winfo_toplevel())
        window.configure(bg=BACKGROUND)
        window.geometry("650x500")
        window.minsize(560, 500)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)
        tk.Label(window, text="Edit Grocery Item" if item else "Add a Grocery Item", bg=BACKGROUND, fg=INK,
                 anchor="w", font=(self._normal_font[0], self._normal_font[1] + 5, "bold")).grid(
            row=0, column=0, sticky="ew", padx=20, pady=(18, 12))
        form = tk.Frame(window, bg="white", highlightthickness=1, highlightbackground=BORDER)
        form.grid(row=1, column=0, sticky="nsew", padx=20)
        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)
        self._editor_values = {
            "name": tk.StringVar(window, value=item.name if item else ""),
            "price": tk.StringVar(window, value=f"{item.price:.2f}" if item else ""),
            "units": tk.StringVar(window, value=str(item.units_per_case) if item else "1"),
            "link": tk.StringVar(window, value=item.link if item else ""),
            "unit": tk.StringVar(window, value=next((unit.name for unit in self._units
                                                     if item and unit.unit_id == item.unit_id), "No unit")),
        }
        for label, key, row, column, span in (("Name", "name", 0, 0, 2), ("Price ($)", "price", 2, 0, 1),
                                             ("Units per case", "units", 2, 1, 1), ("Product link (optional)", "link", 6, 0, 2)):
            tk.Label(form, text=label, bg="white", fg=INK, anchor="w", font=self._bold_font).grid(
                row=row, column=column, columnspan=span, sticky="ew", padx=14, pady=(12, 4))
            entry = ttk.Entry(form, textvariable=self._editor_values[key])
            entry.grid(row=row + 1, column=column, columnspan=span, sticky="ew", padx=14, pady=(0, 10))
            if key == "name":
                entry.focus_set()
            elif key == "price":
                self._price_entry = entry
        tk.Label(form, text="Unit", bg="white", fg=INK, anchor="w", font=self._bold_font).grid(
            row=4, column=0, columnspan=2, sticky="ew", padx=14, pady=(12, 4))
        self._unit_dropdown = ttk.Combobox(form, textvariable=self._editor_values["unit"], state="readonly",
                                           values=["No unit", *(unit.name for unit in self._units)])
        self._unit_dropdown.grid(row=5, column=0, sticky="ew", padx=14, pady=(0, 10))
        document_button(form, "Manage Units", self._show_units_manager).grid(
            row=5, column=1, sticky="ew", padx=14, pady=(0, 10))
        self._editor_error = tk.Label(window, text="Use a product link starting with https://, or leave it blank.",
                                      bg=BACKGROUND, fg=MUTED, anchor="w", justify="left", wraplength=600)
        self._editor_error.grid(row=2, column=0, sticky="ew", padx=20, pady=(10, 0))
        self._editor_saved_price = f"{item.price:.2f}" if item else "0.00"
        self._editor_values["link"].trace_add("write", lambda *args: self._update_price_lock())
        self._update_price_lock()
        window.bind("<Configure>", lambda event: self._editor_error.configure(wraplength=max(100, event.width - 40))
                    if event.widget is window else None)
        actions = tk.Frame(window, bg=BACKGROUND)
        actions.grid(row=3, column=0, sticky="ew", padx=20, pady=14)
        actions.columnconfigure(1, weight=1)
        document_button(actions, "Cancel", window.destroy).grid(row=0, column=0, padx=(0, 10))
        self._save_item_button = document_button(actions, "Save Item", lambda: self._save_item(item), primary=True)
        self._save_item_button.grid(row=0, column=1, sticky="ew")
        window.bind("<Escape>", lambda event: window.destroy())
        window.bind("<Return>", lambda event: self._save_item(item))
        return window

    def _save_item(self, existing: GroceryCatalogItem | None):
        values = self._editor_values
        try:
            current_items = self._catalog_manager.load()
            current = next((item for item in current_items if existing and item.item_id == existing.item_id), None)
            if existing and current is None:
                raise ValueError("This item has been removed. Close the editor and reload your grocery list.")
            item_id = existing.item_id if existing else max((item.item_id for item in current_items), default=0) + 1
            unit_id = self._selected_unit_id()
            if values["unit"].get() != "No unit" and unit_id is None:
                raise ValueError("Choose an existing unit or select No unit.")
            link = values["link"].get()
            # An open editor must not overwrite a price imported on the other grocery page.
            price = (current.price if current else "0.00") if link.strip() else values["price"].get()
            item = GroceryCatalogItem(item_id, values["name"].get(), price,
                                      values["units"].get(), link, unit_id)
        except (OSError, ValueError) as error:
            self._editor_error.configure(text=str(error), fg="#B91C1C")
            return
        items = [item if existing and other.item_id == existing.item_id else other for other in current_items]
        if existing is None:
            items.append(item)
        if self._commit_items(items):
            self._editor.destroy()

    def _update_price_lock(self):
        linked = bool(self._editor_values["link"].get().strip())
        self._price_entry.configure(state="disabled" if linked else "normal")
        if linked:
            self._editor_values["price"].set(self._editor_saved_price)
        self._editor_error.configure(
            text="Price is locked for linked products. Use the Price Updates page to import their prices. New linked products start at $0.00."
            if linked else "Use a product link starting with https://, or leave it blank. Prices without links can be edited here.",
            fg=MUTED)

    def _selected_unit_id(self) -> str | None:
        if self._editor is None or not self._editor.winfo_exists():
            return None
        return next((unit.unit_id for unit in self._units if unit.name == self._editor_values["unit"].get()), None)

    def _refresh_unit_selector(self, selected: str | None):
        if self._editor is not None and self._editor.winfo_exists():
            self._unit_dropdown.configure(values=["No unit", *(unit.name for unit in self._units)])
            self._editor_values["unit"].set(next((unit.name for unit in self._units if unit.unit_id == selected), "No unit"))

    def _show_units_manager(self):
        if self._units_window is not None and self._units_window.winfo_exists():
            self._units_window.lift()
            return self._units_window
        window = self._units_window = tk.Toplevel(self._root)
        window.title("Manage Grocery Units")
        window.transient(self._editor if self._editor is not None and self._editor.winfo_exists() else self._root.winfo_toplevel())
        window.configure(bg=BACKGROUND)
        window.geometry("780x540")
        window.minsize(700, 480)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(2, weight=1)
        header = tk.Frame(window, bg=BACKGROUND)
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 12))
        header.columnconfigure(0, weight=1)
        tk.Label(header, text="Manage Units", bg=BACKGROUND, fg=INK, anchor="w",
                 font=(self._normal_font[0], self._normal_font[1] + 5, "bold")).grid(row=0, column=0, sticky="ew")
        document_button(header, "Reload", self._reload_and_refresh).grid(row=0, column=1, padx=(10, 0))
        form = tk.Frame(window, bg="white", highlightthickness=1, highlightbackground=BORDER)
        form.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 12))
        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)
        for column, label in enumerate(("Singular (for example Can)", "Plural (defaults to singular + s)")):
            tk.Label(form, text=label, bg="white", fg=INK, anchor="w", font=self._bold_font).grid(
                row=0, column=column, sticky="ew", padx=14, pady=(12, 4))
        self._unit_name_value = tk.StringVar(window)
        self._unit_plural_value = tk.StringVar(window)
        self._unit_plural_custom = False
        self._syncing_unit_plural = False
        self._unit_name_value.trace_add("write", self._update_unit_plural)
        self._unit_plural_value.trace_add("write", self._track_unit_plural)
        self._unit_name_entry = ttk.Entry(form, textvariable=self._unit_name_value)
        self._unit_name_entry.grid(row=1, column=0, sticky="ew", padx=(14, 8), pady=(0, 10))
        self._unit_plural_entry = ttk.Entry(form, textvariable=self._unit_plural_value)
        self._unit_plural_entry.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(0, 10))
        self._unit_save_button = document_button(form, "Add Unit", self._save_unit, primary=True)
        self._unit_save_button.grid(row=1, column=2, padx=(0, 8), pady=(0, 10))
        self._unit_cancel_button = document_button(form, "Cancel Edit", self._cancel_unit_rename)
        self._unit_cancel_button.grid(row=1, column=3, padx=(0, 14), pady=(0, 10))
        self._unit_error_label = tk.Label(form, bg="white", fg=MUTED, anchor="w", justify="left", wraplength=520)
        self._unit_error_label.grid(row=2, column=0, columnspan=4, sticky="ew", padx=14, pady=(0, 10))
        window.bind("<Configure>", lambda event: self._unit_error_label.configure(wraplength=max(100, event.width - 70))
                    if event.widget is window else None)
        done = document_button(window, "Done", window.destroy, primary=True)
        done.grid(row=3, column=0, sticky="ew", padx=20, pady=14)
        window.bind("<Escape>", lambda event: window.destroy())
        self._unit_being_edited = None
        self._refresh_units_window()
        return window

    def _refresh_units_window(self):
        self._unit_error_label.configure(text=self._unit_load_error or "Unit changes are saved immediately.",
                                         fg="#B91C1C" if self._unit_load_error else MUTED)
        self._unit_save_button.configure(state="disabled" if self._unit_load_error else "normal")
        self._unit_name_entry.configure(state="disabled" if self._unit_load_error else "normal")
        self._unit_plural_entry.configure(state="disabled" if self._unit_load_error else "normal")
        self._unit_cancel_button.configure(state="normal" if self._unit_being_edited is not None else "disabled")
        if self._units_table is not None:
            self._units_table.destroy()
        self._units_table = table = TkTable(self._units_window, review_style=True, stretch_column=0,
                                           columns=[TableColumn("Singular", str), TableColumn("Plural", str),
                                                    TableColumn("Actions", tk.Widget)])
        table.grid(row=2, column=0, sticky="nsew", padx=20)
        for unit in self._units:
            actions = tk.Frame(table._body)
            rename = document_button(actions, "Edit", lambda unit=unit: self._rename_unit(unit))
            rename.pack(side="left", padx=(0, 6))
            delete = document_button(actions, "Delete", lambda unit=unit: self._delete_unit(unit))
            delete.configure(bg="#FEE2E2", fg="#B91C1C", activebackground="#FECACA", activeforeground="#B91C1C")
            delete.pack(side="left")
            if self._unit_load_error:
                rename.configure(state="disabled")
                delete.configure(state="disabled")
            actions.update_idletasks()
            table.add_row((unit.name, unit.plural, actions))
        if not self._units:
            tk.Label(table._body, text="No units yet\nEnter a name above to add one.", bg="white", fg=MUTED,
                     padx=20, pady=30, justify="center").grid(row=0, column=0, columnspan=3, sticky="ew")

    def _update_unit_plural(self, *args):
        if self._syncing_unit_plural or self._unit_plural_custom:
            return
        self._syncing_unit_plural = True
        name = " ".join(self._unit_name_value.get().split())
        self._unit_plural_value.set(name + "s" if name else "")
        self._syncing_unit_plural = False

    def _track_unit_plural(self, *args):
        if not self._syncing_unit_plural:
            plural = " ".join(self._unit_plural_value.get().split())
            name = " ".join(self._unit_name_value.get().split())
            self._unit_plural_custom = bool(plural) and plural != name + "s"

    def _rename_unit(self, unit: GroceryUnit):
        self._unit_being_edited = unit
        self._syncing_unit_plural = True
        self._unit_name_value.set(unit.name)
        self._unit_plural_value.set(unit.plural)
        self._syncing_unit_plural = False
        self._unit_plural_custom = unit.plural != unit.name + "s"
        self._unit_save_button.configure(text="Save Unit")
        self._unit_cancel_button.configure(state="normal")
        self._unit_name_entry.focus_set()

    def _cancel_unit_rename(self):
        self._unit_being_edited = None
        self._unit_plural_custom = False
        self._unit_name_value.set("")
        self._unit_save_button.configure(text="Add Unit")
        self._unit_cancel_button.configure(state="disabled")

    def _commit_units(self, units: list[GroceryUnit], selected: str | None) -> bool:
        try:
            self._catalog_manager.units_manager.save(units)
        except (OSError, ValueError) as error:
            self._unit_error_label.configure(text=str(error), fg="#B91C1C")
            return False
        self._reload_items()
        self._refresh()
        self._refresh_unit_selector(selected)
        self._refresh_units_window()
        return True

    def _save_unit(self):
        if self._unit_load_error:
            return
        existing = self._unit_being_edited
        try:
            fields = {"name": self._unit_name_value.get(), "plural": self._unit_plural_value.get()}
            if existing:
                fields["unit_id"] = existing.unit_id
            unit = GroceryUnit(**fields)
        except ValueError as error:
            self._unit_error_label.configure(text=str(error), fg="#B91C1C")
            return
        units = [unit if existing and other.unit_id == existing.unit_id else other for other in self._units]
        if existing is None:
            units.append(unit)
        selected = self._selected_unit_id() if existing else unit.unit_id
        if self._commit_units(units, selected):
            self._cancel_unit_rename()

    def _delete_unit(self, unit: GroceryUnit):
        if self._unit_load_error:
            return
        if messagebox.askyesno("Delete unit?", f'Delete "{unit.name}"? Items using it will keep their quantities and have no unit assigned.',
                              parent=self._units_window, default="no"):
            selected = self._selected_unit_id()
            if self._commit_units([other for other in self._units if other.unit_id != unit.unit_id], selected):
                if self._unit_being_edited is not None and self._unit_being_edited.unit_id == unit.unit_id:
                    self._cancel_unit_rename()

    def _finalize(self):
        self._parent_next_method()
