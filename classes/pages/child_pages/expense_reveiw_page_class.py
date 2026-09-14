"""Imports"""
from classes.pages.branch_page_class import BranchPage
import tkinter as tk
from collections.abc import Callable

from classes.pages.child_page_class import ChildPage
from classes.pages.child_pages.expense_reveiw_pages.checking_account_expenses_page_class import \
    CheckingAccountExpensesPage
from classes.pages.child_pages.expense_reveiw_pages.credit_card_expenses_page_class import CreditCardExpensesPage
from classes.pages.child_pages.expense_reveiw_pages.reciepts_input_page import ReceiptsInputPage


class ExpenseReviewPage(BranchPage):
    def __init__(self, parent_root: tk.Tk|tk.Frame,
                 parent_next_method: Callable):
        super().__init__(parent_root = parent_root,
                         parent_next_method = parent_next_method)

    def _create_pages(self, parent_root: tk.Tk | tk.Frame,
                      parent_next_method: Callable) -> list[ChildPage]:
        return [ReceiptsInputPage(parent_root = parent_root,
                                  parent_next_method = parent_next_method)]

        """
            [CreditCardExpensesPage(parent_root = parent_root,
                                       parent_next_method = parent_next_method),
                CheckingAccountExpensesPage(parent_root = parent_root,
                                            parent_next_method = parent_next_method),
                ReceiptsInputPage(parent_root = parent_root,
                                  parent_next_method = parent_next_method)]
        """