"""Imports"""
from classes.pages.branch_page_class import BranchPage
import tkinter as tk
from collections.abc import Callable

from classes.pages.child_page_class import ChildPage
from classes.pages.child_pages.budget_planning_pages.income_estimation_page import IncomeEstimationPage
from classes.pages.child_pages.budget_planning_pages.groceries_planning_page import GroceriesPlanningPage
from classes.pages.child_pages.budget_planning_pages.foods_page import FoodsPage
from classes.pages.child_pages.budget_planning_pages.daily_use_page import DailyUsePage
from classes.daily_use_item_class import DailyUseItem
from classes.pages.child_pages.budget_planning_pages.overall_budget_page import OverallBudgetPage
from classes.managers.income_estimation_manager import IncomeEstimate
from classes.managers.budget_summary_manager import BudgetExpense, BudgetSummary, BudgetSummaryManager
from classes.managers.budget_category_manager import BudgetCategoryManager


class BudgetPlanningPage(BranchPage):
    def __init__(self, parent_root: tk.Tk,
                 parent_next_method: Callable):
        self._planned_expenses: tuple[BudgetExpense, ...] = ()
        super().__init__(parent_root = parent_root,
                         parent_next_method = parent_next_method)

    @property
    def income_estimate(self) -> IncomeEstimate:
        return self._income_page.income_estimate

    @property
    def daily_use_plan(self) -> tuple[DailyUseItem, ...]:
        return self._daily_use_page.items

    @property
    def budget_summary(self) -> BudgetSummary:
        return BudgetSummaryManager.summarize(self.income_estimate, self._planned_expenses,
                                             BudgetCategoryManager.choices())

    @property
    def planned_expenses(self) -> tuple[BudgetExpense, ...]:
        return self._planned_expenses

    def set_planned_expenses(self, expenses) -> None:
        expenses = tuple(expenses)
        BudgetSummaryManager.summarize(self.income_estimate, expenses)
        self._planned_expenses = expenses
        self._overall_page.refresh()

    def _edit_income(self):
        self._pages[self._page_index].deactivate()
        self._page_index = 3
        self._income_page.activate()

    def _edit_daily_use(self):
        self._pages[self._page_index].deactivate()
        self._page_index = 2
        self._daily_use_page.activate()

    def _edit_foods(self):
        self._pages[self._page_index].deactivate()
        self._page_index = 1
        self._foods_page.activate()

    def _edit_groceries(self, price_updates: bool = False):
        self._pages[self._page_index].deactivate()
        self._page_index = 0
        if price_updates:
            self._groceries_page.show_prices()
        else:
            self._groceries_page.show_items()
        self._groceries_page.activate()

    def activate(self):
        super().activate()
        self._pages[self._page_index].activate()

    def _create_pages(self, parent_root: tk.Tk | tk.Frame,
                      parent_next_method: Callable) -> list[ChildPage]:
        self._groceries_page = GroceriesPlanningPage(parent_root, parent_next_method)
        self._grocery_page = self._groceries_page.items_page
        self._grocery_prices_page = self._groceries_page.prices_page
        self._foods_page = FoodsPage(parent_root, parent_next_method,
                                     on_back=lambda: self._edit_groceries(price_updates=True),
                                     catalog_manager=self._grocery_page._catalog_manager)
        self._daily_use_page = DailyUsePage(parent_root, parent_next_method, on_back=self._edit_foods,
                                           catalog_manager=self._grocery_page._catalog_manager,
                                           foods_manager=self._foods_page._foods_manager)
        self._income_page = IncomeEstimationPage(parent_root, parent_next_method,
                                                on_back=self._edit_daily_use,
                                                catalog_manager=self._grocery_page._catalog_manager,
                                                foods_manager=self._foods_page._foods_manager)
        self._overall_page = OverallBudgetPage(parent_root, parent_next_method, lambda: self.budget_summary,
                                               self._edit_income, self._edit_groceries)
        return [self._groceries_page, self._foods_page, self._daily_use_page, self._income_page, self._overall_page]

