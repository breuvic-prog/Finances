"""Imports"""
from classes.pages.branch_page_class import BranchPage
import tkinter as tk
from collections.abc import Callable

from classes.pages.child_page_class import ChildPage


class BudgetPlanningPage(BranchPage):
    def __init__(self, parent_root: tk.Tk,
                 parent_next_method: Callable):
        super().__init__(parent_root = parent_root,
                         parent_next_method = parent_next_method)

    def _create_pages(self, parent_root: tk.Tk | tk.Label,
                      parent_next_method: Callable) -> list[ChildPage]:
        return []

