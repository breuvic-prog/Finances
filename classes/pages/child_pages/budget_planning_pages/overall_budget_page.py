"""Show income, remaining budget, and totals of planned category expenses."""

from collections.abc import Callable
import tkinter as tk
from tkinter import font

from classes.custom_tk_components.tk_document_input_class import BACKGROUND, BORDER, INK, MUTED, document_button
from classes.custom_tk_components.tk_table_class import TkTable
from classes.managers.budget_summary_manager import BudgetSummary
from classes.managers.budget_category_manager import BudgetCategoryManager
from classes.managers.option_manager import OptionManager
from classes.pages.leaf_page_class import LeafPage
from classes.table_column_class import TableColumn


def _money(value) -> str:
    return ("-" if value < 0 else "") + f"${abs(value):,.2f}"


class OverallBudgetPage(LeafPage):
    def __init__(self, parent_root: tk.Misc, parent_next_method: Callable,
                 summary_provider: Callable[[], BudgetSummary], on_edit_income: Callable,
                 on_edit_groceries: Callable | None = None):
        self._summary_provider = summary_provider
        self._on_edit_income = on_edit_income
        self._on_edit_groceries = on_edit_groceries
        self._summary = summary_provider()
        self._category_table = None
        super().__init__(parent_root, parent_next_method)
        OptionManager.subscribe(self.refresh)

    @property
    def summary(self) -> BudgetSummary:
        return self._summary

    def activate(self):
        super().activate()
        self.refresh()

    def _setup_components(self):
        self._root.configure(bg=BACKGROUND)
        self._root.columnconfigure(0, weight=1)
        self._root.rowconfigure(4, weight=1)
        default = font.nametofont("TkDefaultFont", root=self._root).actual()
        self._bold_font = (default["family"], default["size"], "bold")
        self._amount_font = (default["family"], default["size"] + 9, "bold")

        header = tk.Frame(self._root, bg=BACKGROUND)
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 14))
        header.columnconfigure(0, weight=1)
        tk.Label(header, text="BUDGET PLANNING · STEP 5", bg=BACKGROUND, fg=MUTED,
                 font=self._bold_font, anchor="w").grid(row=0, column=0, sticky="ew")
        tk.Label(header, text="Overall Budget", bg=BACKGROUND, fg=INK, anchor="w",
                 font=(default["family"], default["size"] + 7, "bold")).grid(
            row=1, column=0, sticky="ew", pady=(5, 0))
        self._month_label = tk.Label(header, bg="#E5EFFB", fg="#234E78", padx=12, pady=8,
                                    font=self._bold_font)
        self._month_label.grid(row=1, column=1, sticky="e", padx=(12, 0))
        tk.Label(header, text="Bring your planned expenses together and see what is left for the month.",
                 bg=BACKGROUND, fg=MUTED, anchor="w").grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        total_card = tk.Frame(self._root, bg="white", highlightthickness=1, highlightbackground=BORDER)
        total_card.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        tk.Label(total_card, text="Total estimated budget", bg="white", fg=MUTED, anchor="w").pack(
            fill="x", padx=16, pady=(12, 5))
        self._budget_label = tk.Label(total_card, bg="white", fg=INK, anchor="w", font=self._amount_font)
        self._budget_label.pack(fill="x", padx=16)
        tk.Label(total_card, text="Estimated take-home income from your jobs, after tax and unpaid breaks.",
                 bg="white", fg=MUTED, anchor="w").pack(fill="x", padx=16, pady=(5, 12))

        self._remaining_card = tk.Frame(self._root, highlightthickness=1, highlightbackground=BORDER)
        self._remaining_card.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 16))
        self._remaining_title = tk.Label(self._remaining_card, text="Remaining budget", fg=MUTED, anchor="w")
        self._remaining_title.pack(fill="x", padx=16, pady=(12, 5))
        self._remaining_label = tk.Label(self._remaining_card, anchor="w", font=self._amount_font)
        self._remaining_label.pack(fill="x", padx=16)
        self._remaining_detail = tk.Label(self._remaining_card, fg=MUTED, anchor="w")
        self._remaining_detail.pack(fill="x", padx=16, pady=(5, 12))

        heading = tk.Frame(self._root, bg=BACKGROUND)
        heading.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 10))
        heading.columnconfigure(0, weight=1)
        tk.Label(heading, text="Budget categories", bg=BACKGROUND, fg=INK, anchor="w",
                 font=self._bold_font).grid(row=0, column=0, sticky="ew")
        self._status_label = tk.Label(heading, bg=BACKGROUND, fg=MUTED, anchor="w")
        self._status_label.grid(row=1, column=0, sticky="ew", pady=(5, 0))

        footer = tk.Frame(self._root, bg=BACKGROUND)
        footer.grid(row=5, column=0, sticky="ew", padx=20, pady=(12, 18))
        footer.columnconfigure(0, weight=1)
        self._expenses_label = tk.Label(footer, bg=BACKGROUND, fg=INK, anchor="w", font=self._bold_font)
        self._expenses_label.grid(row=0, column=0, sticky="ew")
        if self._on_edit_groceries is not None:
            self._edit_groceries_button = document_button(footer, "Edit Grocery Items", self._on_edit_groceries)
            self._edit_groceries_button.grid(row=0, column=1, padx=(12, 0))
        self._edit_income_button = document_button(footer, "Edit Income Estimate", self._on_edit_income)
        self._edit_income_button.grid(row=0, column=2, padx=(12, 0))
        self.refresh()

    def refresh(self):
        try:
            exists = self._root.winfo_exists()
        except tk.TclError:
            return
        if not exists:
            return
        self._summary = summary = self._summary_provider()
        self._month_label.configure(text=summary.month.strftime("%B %Y"))
        self._budget_label.configure(text=_money(summary.total_budget))
        background, foreground = ("#FFF1F2", "#BE123C") if summary.remaining_budget < 0 else ("#ECFDF5", "#15803D")
        self._remaining_card.configure(bg=background)
        for label in (self._remaining_title, self._remaining_label, self._remaining_detail):
            label.configure(bg=background)
        self._remaining_label.configure(text=_money(summary.remaining_budget), fg=foreground)
        self._remaining_detail.configure(text=f"{_money(summary.total_budget)} budget − {_money(summary.total_expenses)} planned expenses")
        self._expenses_label.configure(text=f"Total planned expenses: {_money(summary.total_expenses)}")
        self._status_label.configure(text="No planned expenses yet." if not summary.total_expenses
                                     else "Each category combines its planned subcategory costs.")
        if self._category_table is not None:
            self._category_table.destroy()
        self._category_table = table = TkTable(self._root, review_style=True, stretch_column=0,
                                             columns=[TableColumn("Category", tk.Widget), TableColumn("Planned cost", tk.Widget)])
        table.grid(row=4, column=0, sticky="nsew", padx=20)
        self._category_cells = {}
        for total in summary.categories:
            category = tk.Label(table._body, text=OptionManager.display(total.category))
            cost = tk.Label(table._body, text=_money(total.amount))
            table.add_row((category, cost))
            background, foreground = BudgetCategoryManager.colors(total.category)
            category.configure(bg=background, fg=foreground)
            cost.configure(anchor="e", font=self._bold_font)
            self._category_cells[total.category] = (category, cost)

    def _finalize(self):
        # More budget-planning steps will be added after this initial summary.
        pass
