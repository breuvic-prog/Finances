"""Imports"""
from typing import Callable, Any

from classes.pages.child_page_class import ChildPage
from classes.pages.child_pages.budget_planning_page_class import BudgetPlanningPage
from classes.pages.child_pages.expense_reveiw_page_class import ExpenseReviewPage
from classes.pages.root_page_class import RootPage
import tkinter as tk


ENABLE_EXPENSE_REVIEW = False  # Set to True to restore the expense-review step.


class FinancesPage(RootPage):
    def __init__(self):
        self._root = tk.Tk()
        super().__init__()

        self._name = "Finance Manager"

        # Tkinter
        self._root.title(self._name)
        max_width, _ = self._root.maxsize()
        self._root.maxsize(max_width, 1000)

        # Starts the UI
        self._root.mainloop()

    def _create_pages(self, parent_root: tk.Tk | tk.Frame,
                      parent_next_method: Callable) -> list[ChildPage]:
        pages = []
        if ENABLE_EXPENSE_REVIEW:
            pages.append(ExpenseReviewPage(parent_root=parent_root, parent_next_method=parent_next_method))
        pages.append(BudgetPlanningPage(parent_root=parent_root, parent_next_method=parent_next_method))
        return pages




