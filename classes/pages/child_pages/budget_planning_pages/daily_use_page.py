"""Manage everyday consumption before adding work and day-off extras."""

from collections import Counter
from collections.abc import Callable
from calendar import monthrange
from datetime import date
from decimal import Decimal
import tkinter as tk
from tkinter import font, ttk

from classes.custom_tk_components.tk_document_input_class import BACKGROUND, BORDER, INK, MUTED, document_button
from classes.custom_tk_components.tk_food_plan_editor import format_quantity
from classes.custom_tk_components.tk_table_class import TkTable
from classes.daily_use_item_class import DailyUseItem
from classes.managers.daily_use_manager import DailyUseManager
from classes.managers.grocery_catalog_manager import GroceryCatalogManager
from classes.managers.income_estimation_manager import IncomeEstimationManager
from classes.managers.prepared_foods_manager import PreparedFoodsManager
from classes.pages.leaf_page_class import LeafPage
from classes.table_column_class import TableColumn


_QUANTITY = "Quantity per day"
_MONTHLY = "Quantity per month"
_CASE = "One case lasts … days"


def _daily_quantity_text(quantity: Decimal) -> str:
    rounded = Decimal(format(quantity, ".6g"))
    return ("≈ " if rounded != quantity else "") + format_quantity(rounded)


class DailyUsePage(LeafPage):
    def __init__(self, parent_root: tk.Misc, parent_next_method: Callable, on_back: Callable,
                 catalog_manager: GroceryCatalogManager | None = None,
                 foods_manager: PreparedFoodsManager | None = None,
                 daily_use_manager: DailyUseManager | None = None,
                 today: Callable[[], date] = date.today):
        self._catalog = catalog_manager if catalog_manager is not None else GroceryCatalogManager()
        self._foods_manager = foods_manager if foods_manager is not None else PreparedFoodsManager()
        self._daily_use_manager = daily_use_manager if daily_use_manager is not None else DailyUseManager()
        self._on_back = on_back
        self._today = today
        self._month = IncomeEstimationManager.next_month(self._today())
        self._entries = ()
        self._items, self._foods, self._units, self._choices = {}, {}, {}, {}
        self._all_choices = {}
        self._load_error = self._catalog_error = None
        self._editing = self._usage_table = None
        super().__init__(parent_root, parent_next_method)
        self._reload_and_refresh()

    @property
    def items(self) -> tuple[DailyUseItem, ...]:
        return self._entries

    def activate(self):
        self._reload_and_refresh()
        super().activate()

    def _setup_components(self):
        self._root.configure(bg=BACKGROUND)
        self._root.columnconfigure(0, weight=1)
        self._root.rowconfigure(3, weight=1)
        default = font.nametofont("TkDefaultFont", root=self._root).actual()
        self._bold_font = (default["family"], default["size"], "bold")
        header = tk.Frame(self._root, bg=BACKGROUND)
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 16))
        tk.Label(header, text="BUDGET PLANNING · STEP 3", bg=BACKGROUND, fg=MUTED,
                 anchor="w", font=self._bold_font).pack(fill="x")
        title = tk.Frame(header, bg=BACKGROUND)
        title.pack(fill="x", pady=(5, 0))
        tk.Label(title, text="Daily Use", bg=BACKGROUND, fg=INK, anchor="w",
                 font=(default["family"], default["size"] + 7, "bold")).pack(side="left", fill="x", expand=True)
        self._month_label = tk.Label(title, bg="#E5EFFB", fg="#234E78", padx=12, pady=8, font=self._bold_font)
        self._month_label.pack(side="right", padx=(12, 0))
        hint = tk.Label(header, text="Your everyday baseline, whether you work or have a day off. Shift and day-off plans add extra consumption on top of this.",
                        bg=BACKGROUND, fg=MUTED, anchor="w", justify="left", wraplength=900)
        hint.pack(fill="x", pady=(8, 0))
        header.bind("<Configure>", lambda event: hint.configure(wraplength=max(100, event.width)))
        toolbar = tk.Frame(self._root, bg=BACKGROUND)
        toolbar.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        toolbar.columnconfigure(0, weight=1)
        self._heading = tk.Label(toolbar, bg=BACKGROUND, fg=INK, anchor="w", font=self._bold_font)
        self._heading.grid(row=0, column=0, sticky="ew")
        document_button(toolbar, "Reload Items", self._reload_and_refresh).grid(row=0, column=1, padx=(8, 0))

        form = tk.Frame(self._root, bg="white", highlightthickness=1, highlightbackground=BORDER)
        form.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 14))
        form.columnconfigure(0, weight=1)
        for column, text in enumerate(("Grocery / food", "Enter as", "Quantity / day")):
            label = tk.Label(form, text=text, bg="white", fg=INK, font=self._bold_font, anchor="w")
            label.grid(row=0, column=column, sticky="ew", padx=12, pady=(12, 4))
            if column == 2:
                self._amount_label = label
        self._item_value = tk.StringVar(self._root)
        self._mode_value = tk.StringVar(self._root, value=_QUANTITY)
        self._amount_value = tk.StringVar(self._root, value="1")
        self._item_dropdown = ttk.Combobox(form, textvariable=self._item_value, state="readonly", width=35)
        self._item_dropdown.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))
        self._mode_dropdown = ttk.Combobox(form, textvariable=self._mode_value, state="readonly", values=(_QUANTITY, _MONTHLY, _CASE), width=24)
        self._mode_dropdown.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(0, 10))
        self._amount_entry = ttk.Entry(form, textvariable=self._amount_value, width=12)
        self._amount_entry.grid(row=1, column=2, sticky="ew", padx=(0, 12), pady=(0, 10))
        self._save_item_button = document_button(form, "Add Item", self._save_item, primary=True)
        self._save_item_button.grid(row=1, column=3, padx=(0, 8), pady=(0, 10))
        self._cancel_edit_button = document_button(form, "Cancel Edit", self._cancel_edit)
        self._cancel_edit_button.grid(row=1, column=4, padx=(0, 12), pady=(0, 10))
        self._preview_label = tk.Label(form, bg="white", fg=MUTED, anchor="w", justify="left", wraplength=900)
        self._preview_label.grid(row=2, column=0, columnspan=5, sticky="ew", padx=12, pady=(0, 12))
        form.bind("<Configure>", lambda event: self._preview_label.configure(wraplength=max(100, event.width - 26)))
        for variable in (self._item_value, self._mode_value, self._amount_value):
            variable.trace_add("write", lambda *args: self._update_form())
        self._amount_entry.bind("<Return>", lambda event: self._save_item())
        footer = tk.Frame(self._root, bg=BACKGROUND)
        footer.grid(row=4, column=0, sticky="ew", padx=20, pady=(12, 18))
        footer.columnconfigure(1, weight=1)
        self._status = tk.Label(footer, bg=BACKGROUND, fg=MUTED, anchor="w", justify="left", wraplength=900)
        self._status.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        footer.bind("<Configure>", lambda event: self._status.configure(wraplength=max(100, event.width)))
        self._back_button = document_button(footer, "Back to Foods", self._on_back)
        self._back_button.configure(height=2, pady=1)
        self._back_button.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        self._continue_button = document_button(footer, "Continue to Income Estimation", self._finalize, primary=True)
        self._continue_button.configure(height=2, pady=1)
        self._continue_button.grid(row=1, column=1, sticky="ew")

    def _reload_and_refresh(self):
        self._month = IncomeEstimationManager.next_month(self._today())
        self._month_label.configure(text=f"{self._month:%B %Y} · {monthrange(self._month.year, self._month.month)[1]} days")
        selected = self._choices.get(self._item_value.get())
        try:
            self._entries = self._daily_use_manager.load()
        except (OSError, ValueError) as error:
            self._load_error = str(error)
        else:
            self._load_error = None
        try:
            items = self._catalog.load()
            units = self._catalog.units_manager.load()
            foods = self._foods_manager.load()
        except (OSError, ValueError) as error:
            self._catalog_error = str(error)
            self._all_choices = {}
        else:
            self._catalog_error = None
            self._items = {item.item_id: item for item in items}
            self._units = {unit.unit_id: unit for unit in units}
            self._foods = {food.food_id: food for food in foods}
            names = Counter(item.name for item in items)
            grocery_choices = {f"Grocery: {item.name}" + (f" (item {item.item_id})" if names[item.name] > 1 else ""): item.item_id
                               for item in sorted(items, key=lambda item: item.name.casefold())}
            self._all_choices = {**{f"Food: {food.name}": food.food_id for food in sorted(foods, key=lambda food: food.name.casefold())}, **grocery_choices}
        self._refresh_choices(selected)
        self._refresh_table()
        self._update_form()
        self._set_status(self._load_error or self._catalog_error or "Add, edit, and remove items to save your daily baseline automatically.",
                         bool(self._load_error or self._catalog_error))

    def _set_status(self, text: str, error: bool = False):
        self._status.configure(text=text, fg="#B91C1C" if error else MUTED)

    def _refresh_choices(self, selected: int | str | None = None):
        if selected is None:
            selected = self._choices.get(self._item_value.get())
        used = {entry.key for entry in self._entries}
        editing = self._editing.key if self._editing is not None else None
        self._choices = {label: identifier for label, identifier in self._all_choices.items()
                         if (key := ("food" if isinstance(identifier, str) else "grocery", identifier)) not in used
                         or key == editing}
        self._item_dropdown.configure(values=list(self._choices), state="readonly" if self._choices else "disabled")
        self._item_value.set(next((label for label, identifier in self._choices.items() if identifier == selected), ""))
        self._update_form()

    def _entry_from_form(self) -> DailyUseItem:
        identifier = self._choices.get(self._item_value.get())
        if identifier is None:
            raise ValueError("Choose an available grocery or food.")
        if self._mode_value.get() not in (_QUANTITY, _MONTHLY, _CASE):
            raise ValueError("Choose quantity per day, quantity per month, or case lifespan.")
        fields = {"grocery_item_id": identifier if isinstance(identifier, int) else None,
                  "food_id": identifier if isinstance(identifier, str) else None}
        field = {_QUANTITY: "quantity", _MONTHLY: "monthly_quantity", _CASE: "case_days"}[self._mode_value.get()]
        fields[field] = self._amount_value.get()
        return DailyUseItem(**fields)

    def _unit_text(self, entry: DailyUseItem, quantity: Decimal) -> str:
        if entry.food_id is not None:
            return "Serving" if quantity == 1 else "Servings"
        grocery = self._items.get(entry.grocery_item_id)
        unit = self._units.get(grocery.unit_id) if grocery is not None else None
        return unit.for_count(quantity) if unit else ("Item" if quantity == 1 else "Items")

    def _update_form(self):
        identifier = self._choices.get(self._item_value.get())
        prepared = isinstance(identifier, str)
        self._mode_dropdown.configure(values=(_QUANTITY, _MONTHLY) if prepared else (_QUANTITY, _MONTHLY, _CASE))
        if prepared and self._mode_value.get() == _CASE:
            self._mode_value.set(_QUANTITY)
            self._amount_value.set("")
        case = self._mode_value.get() == _CASE
        monthly = self._mode_value.get() == _MONTHLY
        self._amount_label.configure(text="Days per case" if case else "Quantity / month" if monthly else "Quantity / day")
        self._save_item_button.configure(state="normal" if identifier is not None and not self._load_error and not self._catalog_error else "disabled")
        self._cancel_edit_button.configure(state="normal" if self._editing is not None else "disabled")
        try:
            entry = self._entry_from_form()
            quantity = entry.daily_consumption(self._items.get(entry.grocery_item_id), self._month).quantity
        except ValueError:
            text = ("All available items are already in this list. Edit a row or remove one to add it again."
                    if self._all_choices and not self._choices else
                    "Choose a grocery or food and enter a positive quantity. Fractional amounts are allowed.")
        else:
            label = "Daily equivalent" if monthly else "Daily use"
            text = f"{label}: {_daily_quantity_text(quantity)} {self._unit_text(entry, quantity)} per day."
            if case:
                grocery = self._items[entry.grocery_item_id]
                text = f"One case contains {grocery.units_per_case} {self._unit_text(entry, Decimal(grocery.units_per_case))} and lasts {format_quantity(entry.case_days)} days. " + text
            elif monthly:
                text = f"{format_quantity(entry.monthly_quantity)} {self._unit_text(entry, entry.monthly_quantity)} per month, spread over {monthrange(self._month.year, self._month.month)[1]} days in {self._month:%B %Y}. " + text
        self._preview_label.configure(text=text)

    def _refresh_table(self):
        self._heading.configure(text=f"Daily baseline ({len(self._entries)} items)")
        previous = self._usage_table
        table = TkTable(self._root, review_style=True, stretch_column=0, columns=[
            TableColumn("Item", tk.Widget), TableColumn("Entered As", str), TableColumn("Quantity per Day", str),
            TableColumn("Unit", str), TableColumn("Actions", tk.Widget)])
        for entry in self._entries:
            grocery = self._items.get(entry.grocery_item_id)
            item = self._foods.get(entry.food_id) if entry.food_id is not None else grocery
            missing = "Unavailable food" if entry.food_id is not None else f"Unavailable grocery (item {entry.grocery_item_id})"
            name = tk.Label(table._body, text=item.name if item is not None else missing)
            try:
                quantity = entry.daily_consumption(grocery, self._month).quantity
            except ValueError:
                amount, unit = "—", "—"
            else:
                amount = format_quantity(quantity) if entry.quantity is not None else _daily_quantity_text(quantity)
                unit = self._unit_text(entry, quantity) if item is not None else "—"
            if entry.case_days is not None:
                entered = f"One case / {format_quantity(entry.case_days)} days"
            elif entry.monthly_quantity is not None:
                entered = f"{format_quantity(entry.monthly_quantity)} per month"
            else:
                entered = f"{format_quantity(entry.quantity)} per day"
            actions = tk.Frame(table._body)
            edit = document_button(actions, "Edit", lambda entry=entry: self._edit_item(entry))
            edit.pack(side="left", padx=(0, 6))
            remove = document_button(actions, "Remove", lambda entry=entry: self._remove_item(entry))
            remove.configure(bg="#FEE2E2", fg="#B91C1C", activebackground="#FECACA", activeforeground="#B91C1C")
            remove.pack(side="left")
            if self._load_error or self._catalog_error:
                edit.configure(state="disabled")
            if self._load_error:
                remove.configure(state="disabled")
            actions.update_idletasks()
            table.add_row((name, entered, amount, unit, actions))
            if item is None:
                name.configure(fg="#B91C1C")
        if not self._entries:
            tk.Label(table._body, text="No daily-use items yet\nChoose groceries or foods above to add your everyday baseline.",
                     bg="white", fg=MUTED, padx=24, pady=40).grid(row=0, column=0, columnspan=5, sticky="ew")
        table.grid(row=3, column=0, sticky="nsew", padx=20)
        self._usage_table = table
        if previous is not None:
            previous.destroy()

    def _save_item(self) -> bool:
        if self._load_error or self._catalog_error:
            return False
        try:
            entry = self._entry_from_form()
            current = self._daily_use_manager.load()
            if self._editing is not None and not any(item.key == self._editing.key for item in current):
                raise ValueError("This entry was removed. Cancel the edit and reload items.")
            entries = [entry if self._editing is not None and item.key == self._editing.key else item for item in current]
            if self._editing is None:
                entries.append(entry)
            self._daily_use_manager.save(entries)
        except (OSError, ValueError) as error:
            self._set_status(str(error), True)
            return False
        self._entries = tuple(entries)
        self._cancel_edit()
        self._refresh_table()
        self._set_status("Daily-use item saved. Your baseline is saved for future budgets.")
        return True

    def _edit_item(self, entry: DailyUseItem):
        if self._load_error or self._catalog_error:
            return
        self._editing = entry
        self._refresh_choices()
        identifier = entry.food_id if entry.food_id is not None else entry.grocery_item_id
        self._item_value.set(next((label for label, value in self._choices.items() if value == identifier), ""))
        if entry.case_days is not None:
            mode, amount = _CASE, entry.case_days
        elif entry.monthly_quantity is not None:
            mode, amount = _MONTHLY, entry.monthly_quantity
        else:
            mode, amount = _QUANTITY, entry.quantity
        self._mode_value.set(mode)
        self._amount_value.set(format_quantity(amount))
        self._save_item_button.configure(text="Save Changes")
        self._amount_entry.focus_set()
        self._update_form()
        if identifier not in self._choices.values():
            self._set_status("This item is unavailable. Choose a replacement or remove the entry.", True)

    def _cancel_edit(self):
        self._editing = None
        self._item_value.set("")
        self._mode_value.set(_QUANTITY)
        self._amount_value.set("1")
        self._save_item_button.configure(text="Add Item")
        self._refresh_choices()

    def _remove_item(self, entry: DailyUseItem):
        if self._load_error:
            return
        try:
            entries = tuple(item for item in self._daily_use_manager.load() if item.key != entry.key)
            self._daily_use_manager.save(entries)
        except (OSError, ValueError) as error:
            self._set_status(str(error), True)
            return
        self._entries = entries
        if self._editing is not None and self._editing.key == entry.key:
            self._cancel_edit()
        else:
            self._refresh_choices()
        self._refresh_table()
        self._set_status("Daily-use item removed.")

    def _finalize(self):
        if self._editing is not None or self._item_value.get():
            if not self._save_item():
                return
        self._parent_next_method()
