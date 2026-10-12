"""Manage reusable foods assembled from the grocery catalogue."""

from collections.abc import Callable
import tkinter as tk
from tkinter import font, messagebox

from classes.custom_tk_components.tk_document_input_class import BACKGROUND, INK, MUTED, document_button
from classes.custom_tk_components.tk_food_plan_editor import FoodPlanEditor, format_quantity
from classes.custom_tk_components.tk_table_class import TkTable
from classes.managers.grocery_catalog_manager import GroceryCatalogManager
from classes.managers.prepared_foods_manager import PreparedFoodsManager
from classes.pages.leaf_page_class import LeafPage
from classes.prepared_food_class import PreparedFood
from classes.table_column_class import TableColumn


class FoodsPage(LeafPage):
    def __init__(self, parent_root: tk.Misc, parent_next_method: Callable, on_back: Callable,
                 catalog_manager: GroceryCatalogManager | None = None,
                 foods_manager: PreparedFoodsManager | None = None):
        self._catalog = catalog_manager if catalog_manager is not None else GroceryCatalogManager()
        self._foods_manager = foods_manager if foods_manager is not None else PreparedFoodsManager()
        self._on_back = on_back
        self._foods, self._items, self._units = [], {}, {}
        self._load_error = self._catalog_error = None
        self._food_table = self._editor = None
        self._reload()
        super().__init__(parent_root, parent_next_method)

    def activate(self):
        self._reload()
        self._refresh()
        super().activate()

    def _reload(self):
        try:
            self._foods = self._foods_manager.load()
        except (OSError, ValueError) as error:
            self._load_error = str(error)
        else:
            self._load_error = None
        try:
            self._items = {item.item_id: item for item in self._catalog.load()}
            self._units = {unit.unit_id: unit for unit in self._catalog.units_manager.load()}
        except (OSError, ValueError) as error:
            self._catalog_error = str(error)
        else:
            self._catalog_error = None

    def _reload_and_refresh(self):
        self._reload()
        self._refresh()

    def _setup_components(self):
        self._root.configure(bg=BACKGROUND)
        self._root.columnconfigure(0, weight=1)
        self._root.rowconfigure(2, weight=1)
        default = font.nametofont("TkDefaultFont", root=self._root).actual()
        self._bold_font = (default["family"], default["size"], "bold")
        header = tk.Frame(self._root, bg=BACKGROUND)
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 16))
        tk.Label(header, text="BUDGET PLANNING · STEP 2", bg=BACKGROUND, fg=MUTED,
                 anchor="w", font=self._bold_font).pack(fill="x")
        tk.Label(header, text="Foods", bg=BACKGROUND, fg=INK, anchor="w",
                 font=(default["family"], default["size"] + 7, "bold")).pack(fill="x", pady=(5, 0))
        hint = tk.Label(header, text="Combine groceries into foods. Set ingredient quantities for one serving, then use the food in Daily Use, shift, and day-off plans.",
                        bg=BACKGROUND, fg=MUTED, anchor="w", justify="left", wraplength=900)
        hint.pack(fill="x", pady=(8, 0))
        header.bind("<Configure>", lambda event: hint.configure(wraplength=max(100, event.width)))
        toolbar = tk.Frame(self._root, bg=BACKGROUND)
        toolbar.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        toolbar.columnconfigure(0, weight=1)
        self._heading = tk.Label(toolbar, bg=BACKGROUND, fg=INK, font=self._bold_font, anchor="w")
        self._heading.grid(row=0, column=0, sticky="ew")
        document_button(toolbar, "Reload Foods", self._reload_and_refresh).grid(row=0, column=1, padx=(8, 8))
        self._add_button = document_button(toolbar, "+ Add Food", self._show_editor, primary=True)
        self._add_button.grid(row=0, column=2)
        footer = tk.Frame(self._root, bg=BACKGROUND)
        footer.grid(row=3, column=0, sticky="ew", padx=20, pady=(12, 18))
        footer.columnconfigure(1, weight=1)
        self._status = tk.Label(footer, bg=BACKGROUND, fg=MUTED, anchor="w", justify="left", wraplength=900)
        self._status.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        footer.bind("<Configure>", lambda event: self._status.configure(wraplength=max(100, event.width)))
        self._back_button = document_button(footer, "Back to Price Updates", self._on_back)
        self._back_button.configure(height=2, pady=1)
        self._back_button.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        self._continue_button = document_button(footer, "Continue to Daily Use", self._finalize, primary=True)
        self._continue_button.configure(height=2, pady=1)
        self._continue_button.grid(row=1, column=1, sticky="ew")
        self._refresh()

    def _ingredients_text(self, food: PreparedFood) -> str:
        descriptions = []
        for ingredient in food.ingredients:
            item = self._items.get(ingredient.grocery_item_id)
            if item is None:
                descriptions.append(f"Unavailable grocery (item {ingredient.grocery_item_id})")
                continue
            unit = self._units.get(item.unit_id)
            label = unit.for_count(ingredient.quantity) if unit else ("Item" if ingredient.quantity == 1 else "Items")
            descriptions.append(f"{item.name}: {format_quantity(ingredient.quantity)} {label}")
        return "\n".join(descriptions)

    def _refresh(self):
        self._heading.configure(text=f"Your foods ({len(self._foods)})")
        error = self._load_error or self._catalog_error
        self._status.configure(text=error or "Foods are saved for future runs. Each ingredient quantity represents one serving of the food.",
                               fg="#B91C1C" if error else MUTED)
        self._add_button.configure(state="disabled" if error else "normal")
        previous = self._food_table
        table = TkTable(self._root, review_style=True, stretch_column=1, columns=[
            TableColumn("Food", str), TableColumn("Ingredients per Serving", tk.Widget), TableColumn("Actions", tk.Widget)])
        for food in self._foods:
            ingredients = tk.Label(table._body, text=self._ingredients_text(food), justify="left", wraplength=480)
            actions = tk.Frame(table._body)
            edit = document_button(actions, "Edit", lambda food=food: self._show_editor(food))
            edit.pack(side="left", padx=(0, 6))
            delete = document_button(actions, "Delete", lambda food=food: self._delete_food(food))
            delete.configure(bg="#FEE2E2", fg="#B91C1C", activebackground="#FECACA", activeforeground="#B91C1C")
            delete.pack(side="left")
            if error:
                edit.configure(state="disabled")
            if self._load_error:
                delete.configure(state="disabled")
            actions.update_idletasks()
            table.add_row((food.name, ingredients, actions))
            if any(ingredient.grocery_item_id not in self._items for ingredient in food.ingredients):
                ingredients.configure(fg="#B91C1C")
        if not self._foods:
            tk.Label(table._body, text="No foods yet\nAdd a food and choose its grocery ingredients.", bg="white", fg=MUTED,
                     padx=24, pady=40).grid(row=0, column=0, columnspan=3, sticky="ew")
        table.grid(row=2, column=0, sticky="nsew", padx=20)
        self._food_table = table
        if previous is not None:
            previous.destroy()

    def _show_editor(self, existing: PreparedFood | None = None):
        if self._load_error or self._catalog_error:
            return None
        if self._editor is not None and self._editor.window.winfo_exists():
            self._editor.window.lift()
            return self._editor
        name = tk.StringVar(self._root, value=existing.name if existing else "")
        def save_food(ingredients):
            items = {item.item_id for item in self._catalog.load()}
            if any(ingredient.grocery_item_id not in items for ingredient in ingredients):
                raise ValueError("Replace or remove unavailable groceries before saving this food.")
            fields = {"name": name.get(), "ingredients": ingredients}
            if existing is not None:
                fields["food_id"] = existing.food_id
            food = PreparedFood(**fields)
            current = self._foods_manager.load()
            foods = [food if existing is not None and other.food_id == existing.food_id else other for other in current]
            if existing is None:
                foods.append(food)
            elif not any(other.food_id == existing.food_id for other in current):
                raise ValueError("This food was deleted. Close the editor and reload foods.")
            self._foods_manager.save(foods)
            self._foods = foods
            self._refresh()
            return True
        self._editor = FoodPlanEditor(self._root, "Edit Food" if existing else "Create Food",
                                      "Choose groceries and the amount of each used in one serving of this food.",
                                      "Quantity / serving", existing.ingredients if existing else (), self._catalog,
                                      save_food, name_value=name)
        return self._editor

    def _delete_food(self, food: PreparedFood):
        if self._load_error:
            return
        if not messagebox.askyesno("Delete food?", f'Delete "{food.name}"?', parent=self._root, default="no"):
            return
        try:
            current = self._foods_manager.load()
            self._foods_manager.save([other for other in current if other.food_id != food.food_id])
        except (OSError, ValueError) as error:
            self._status.configure(text=str(error), fg="#B91C1C")
            return
        self._reload_and_refresh()

    def _finalize(self):
        if self._editor is not None and self._editor.window.winfo_exists():
            self._editor.window.lift()
            return
        self._parent_next_method()
