"""Edit grocery quantities for one work shift or one day off."""

from collections import Counter
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
import tkinter as tk
from tkinter import font, ttk

from classes.custom_tk_components.tk_document_input_class import BACKGROUND, BORDER, INK, MUTED, document_button
from classes.custom_tk_components.tk_table_class import TkTable
from classes.food_consumption_class import FoodConsumption, validate_food_plan
from classes.managers.grocery_catalog_manager import GroceryCatalogManager
from classes.managers.prepared_foods_manager import PreparedFoodsManager
from classes.table_column_class import TableColumn


def format_quantity(quantity: Decimal) -> str:
    text = format(quantity, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


class FoodPlanEditor:
    def __init__(self, parent: tk.Misc, title: str, subtitle: str, quantity_label: str,
                 foods: tuple[FoodConsumption, ...], catalog: GroceryCatalogManager,
                 on_save: Callable[[tuple[FoodConsumption, ...]], bool], on_close: Callable | None = None,
                 foods_manager: PreparedFoodsManager | None = None, name_value: tk.StringVar | None = None):
        self._foods = validate_food_plan(foods)
        self._catalog = catalog
        self._on_save = on_save
        self._foods_manager = foods_manager
        self._name_value = name_value
        self._prepared_foods = {}
        self._items = {}
        self._units = {}
        self._choices = {}
        self._all_choices = {}
        self._catalog_error = None
        self._editing = None
        self._food_table = None
        self.window = window = tk.Toplevel(parent)
        window.title(title)
        window.transient(parent.winfo_toplevel())
        window.configure(bg=BACKGROUND)
        window.geometry("900x660" if name_value is not None else "900x600")
        window.minsize(780, 580 if name_value is not None else 520)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(2, weight=1)
        default = font.nametofont("TkDefaultFont", root=window).actual()
        self._bold_font = (default["family"], default["size"], "bold")
        header = tk.Frame(window, bg=BACKGROUND)
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 14))
        header.columnconfigure(0, weight=1)
        tk.Label(header, text=title, bg=BACKGROUND, fg=INK, anchor="w",
                 font=(default["family"], default["size"] + 5, "bold")).grid(row=0, column=0, sticky="ew")
        document_button(header, "Reload Foods" if foods_manager is not None else "Reload Groceries",
                        self._reload_catalog).grid(row=0, column=1, padx=(12, 0))
        hint = tk.Label(header, text=subtitle, bg=BACKGROUND, fg=MUTED, anchor="w", justify="left", wraplength=760)
        hint.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        header.bind("<Configure>", lambda event: hint.configure(wraplength=max(100, event.width)))
        if name_value is not None:
            tk.Label(header, text="Food name", bg=BACKGROUND, fg=INK, anchor="w", font=self._bold_font).grid(
                row=2, column=0, columnspan=2, sticky="ew", pady=(14, 4))
            self._name_entry = ttk.Entry(header, textvariable=name_value)
            self._name_entry.grid(row=3, column=0, columnspan=2, sticky="ew")
            self._name_entry.focus_set()

        form = tk.Frame(window, bg="white", highlightthickness=1, highlightbackground=BORDER)
        form.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 14))
        form.columnconfigure(0, weight=1)
        for column, label in enumerate(("Food / grocery" if foods_manager is not None else "Grocery item", quantity_label, "Unit")):
            tk.Label(form, text=label, bg="white", fg=INK, anchor="w", font=self._bold_font).grid(
                row=0, column=column, sticky="ew", padx=12, pady=(12, 4))
        self._food_value = tk.StringVar(window)
        self._quantity_value = tk.StringVar(window, value="1")
        self._food_dropdown = ttk.Combobox(form, textvariable=self._food_value, state="readonly", width=30)
        self._food_dropdown.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        self._quantity_entry = ttk.Entry(form, textvariable=self._quantity_value, width=9)
        self._quantity_entry.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(0, 12))
        self._unit_label = tk.Label(form, bg="white", fg=MUTED, anchor="w", width=12)
        self._unit_label.grid(row=1, column=2, sticky="ew", padx=(0, 12), pady=(0, 12))
        self._add_text = "Add Ingredient" if name_value is not None else "Add Food"
        self._save_food_button = document_button(form, self._add_text, self._save_food, primary=True)
        self._save_food_button.grid(row=1, column=3, padx=(0, 8), pady=(0, 12))
        self._cancel_edit_button = document_button(form, "Cancel Edit", self._cancel_edit)
        self._cancel_edit_button.grid(row=1, column=4, padx=(0, 12), pady=(0, 12))
        self._food_value.trace_add("write", lambda *args: self._update_form())
        self._quantity_value.trace_add("write", lambda *args: self._update_form())

        self._error_label = tk.Label(window, bg=BACKGROUND, fg=MUTED, anchor="w", justify="left", wraplength=800)
        self._error_label.grid(row=3, column=0, sticky="ew", padx=20, pady=(10, 0))
        window.bind("<Configure>", lambda event: self._error_label.configure(wraplength=max(100, event.width - 40))
                    if event.widget is window else None)
        actions = tk.Frame(window, bg=BACKGROUND)
        actions.grid(row=4, column=0, sticky="ew", padx=20, pady=14)
        actions.columnconfigure(1, weight=1)
        document_button(actions, "Cancel", window.destroy).grid(row=0, column=0, padx=(0, 10))
        self._save_plan_button = document_button(actions, "Save Food" if name_value is not None else "Save Food Plan", self._save_plan, primary=True)
        self._save_plan_button.grid(row=0, column=1, sticky="ew")
        window.bind("<Escape>", lambda event: window.destroy())
        window.bind("<Return>", lambda event: self._save_food())
        if on_close is not None:
            window.bind("<Destroy>", lambda event: on_close() if event.widget is window else None)
        self._reload_catalog()

    @property
    def foods(self) -> tuple[FoodConsumption, ...]:
        return self._foods

    def _set_error(self, text: str, error: bool = False):
        self._error_label.configure(text=text, fg="#B91C1C" if error else MUTED)

    def _reload_catalog(self):
        selected = self._choices.get(self._food_value.get())
        try:
            items = self._catalog.load()
            units = self._catalog.units_manager.load()
        except (OSError, ValueError) as error:
            self._items, self._units, self._all_choices = {}, {}, {}
            self._catalog_error = str(error)
        else:
            self._items = {item.item_id: item for item in items}
            self._units = {unit.unit_id: unit for unit in units}
            self._catalog_error = None
            labels = {item.item_id: f"{item.name} — {item.units_per_case} {self._unit_text(item.item_id, Decimal(item.units_per_case))} per case"
                      for item in sorted(items, key=lambda item: item.name.casefold())}
            duplicates = Counter(labels.values())
            self._all_choices = {label + (f" (item {item_id})" if duplicates[label] > 1 else ""): item_id
                             for item_id, label in labels.items()}
        self._prepared_foods = {}
        if self._foods_manager is not None:
            try:
                prepared = self._foods_manager.load()
            except (OSError, ValueError) as error:
                self._catalog_error = "\n".join(filter(None, (self._catalog_error, str(error))))
            else:
                self._prepared_foods = {food.food_id: food for food in prepared}
                self._all_choices = {**{f"Food: {food.name} — per serving": food.food_id
                                        for food in sorted(prepared, key=lambda food: food.name.casefold())}, **self._all_choices}
        self._refresh_choices(selected)
        self._refresh_table()
        self._update_form()
        guidance = ("Choose foods by serving or groceries by their units. Fractions such as 0.5 are allowed."
                    if self._foods_manager is not None else "Choose groceries and enter quantities in individual units. Fractions such as 0.5 are allowed.")
        empty = ("All available items are already in this plan. Edit a row or remove one to add it again."
                 if self._all_choices else "Add grocery items on the Groceries page, then click Reload Groceries.")
        self._set_error(self._catalog_error or (guidance if self._choices else empty),
                        bool(self._catalog_error))

    def _refresh_choices(self, selected: int | str | None = None):
        if selected is None:
            selected = self._choices.get(self._food_value.get())
        used = {food.key for food in self._foods}
        editing = self._editing.key if self._editing is not None else None
        self._choices = {label: identifier for label, identifier in self._all_choices.items()
                         if (key := ("food" if isinstance(identifier, str) else "grocery", identifier)) not in used
                         or key == editing}
        self._food_dropdown.configure(values=list(self._choices), state="readonly" if self._choices else "disabled")
        self._food_value.set(next((label for label, identifier in self._choices.items() if identifier == selected), ""))
        self._update_form()

    def _unit_text(self, item_id: int | str, quantity: Decimal) -> str:
        if isinstance(item_id, str):
            return "Serving" if quantity == 1 else "Servings"
        item = self._items.get(item_id)
        unit = self._units.get(item.unit_id) if item is not None else None
        return unit.for_count(quantity) if unit is not None else ("Item" if quantity == 1 else "Items")

    def _identifier(self, food: FoodConsumption) -> int | str:
        return food.food_id if food.food_id is not None else food.grocery_item_id

    def _update_form(self):
        item_id = self._choices.get(self._food_value.get())
        try:
            quantity = Decimal(self._quantity_value.get())
        except InvalidOperation:
            quantity = Decimal(0)
        if not quantity.is_finite():
            quantity = Decimal(0)
        self._unit_label.configure(text=self._unit_text(item_id, quantity) if item_id is not None else "—")
        self._save_food_button.configure(state="normal" if item_id is not None else "disabled")
        self._cancel_edit_button.configure(state="normal" if self._editing is not None else "disabled")

    def _refresh_table(self):
        if self._food_table is not None:
            self._food_table.destroy()
        self._food_table = table = TkTable(self.window, review_style=True, stretch_column=0, columns=[
            TableColumn("Food", tk.Widget), TableColumn("Quantity", str), TableColumn("Unit", str),
            TableColumn("Actions", tk.Widget)])
        table.grid(row=2, column=0, sticky="nsew", padx=20)
        for food in self._foods:
            identifier = self._identifier(food)
            item = self._prepared_foods.get(identifier) if food.food_id is not None else self._items.get(identifier)
            missing = "Unavailable food" if food.food_id is not None else f"Unavailable grocery (item {identifier})"
            name = tk.Label(table._body, text=item.name if item is not None else missing)
            actions = tk.Frame(table._body)
            document_button(actions, "Edit", lambda food=food: self._edit_food(food)).pack(side="left", padx=(0, 6))
            remove = document_button(actions, "Remove", lambda food=food: self._remove_food(food))
            remove.configure(bg="#FEE2E2", fg="#B91C1C", activebackground="#FECACA", activeforeground="#B91C1C")
            remove.pack(side="left")
            actions.update_idletasks()
            table.add_row((name, format_quantity(food.quantity), self._unit_text(identifier, food.quantity) if item else "—", actions))
            if item is None:
                name.configure(fg="#B91C1C")
        if not self._foods:
            tk.Label(table._body, text="No foods in this plan yet.\nChoose a grocery item above to add one.",
                     bg="white", fg=MUTED, padx=24, pady=40).grid(row=0, column=0, columnspan=4, sticky="ew")

    def _save_food(self) -> bool:
        item_id = self._choices.get(self._food_value.get())
        if item_id is None:
            self._set_error("Choose an available food or grocery.", True)
            return False
        try:
            food = FoodConsumption(None, self._quantity_value.get(), item_id) if isinstance(item_id, str) else FoodConsumption(item_id, self._quantity_value.get())
            foods = [food if self._editing is not None and existing.key == self._editing.key else existing
                     for existing in self._foods]
            if self._editing is None:
                foods.append(food)
            foods = validate_food_plan(foods)
        except ValueError as error:
            self._set_error(str(error), True)
            return False
        self._foods = foods
        self._cancel_edit()
        self._refresh_table()
        self._set_error(f"Food list updated. Click {self._save_plan_button.cget('text')} to keep these changes.")
        return True

    def _edit_food(self, food: FoodConsumption):
        self._editing = food
        self._refresh_choices()
        self._food_value.set(next((label for label, item_id in self._choices.items() if item_id == self._identifier(food)), ""))
        self._quantity_value.set(format_quantity(food.quantity))
        self._save_food_button.configure(text="Save Quantity")
        self._update_form()
        self._quantity_entry.focus_set()
        if self._identifier(food) not in self._choices.values():
            self._set_error("This food or grocery is unavailable. Choose a replacement or remove it from the plan.", True)

    def _cancel_edit(self):
        self._editing = None
        self._food_value.set("")
        self._quantity_value.set("1")
        self._save_food_button.configure(text=self._add_text)
        self._refresh_choices()

    def _remove_food(self, food: FoodConsumption):
        self._foods = tuple(existing for existing in self._foods if existing.key != food.key)
        if self._editing is not None and self._editing.key == food.key:
            self._cancel_edit()
        else:
            self._refresh_choices()
        self._refresh_table()
        self._set_error(f"Food removed. Click {self._save_plan_button.cget('text')} to keep these changes.")

    def _save_plan(self):
        if self._editing is not None or self._food_value.get():
            if not self._save_food():
                return
        try:
            saved = self._on_save(validate_food_plan(self._foods))
        except (OSError, ValueError) as error:
            self._set_error(str(error), True)
            return
        if saved:
            self.window.destroy()
