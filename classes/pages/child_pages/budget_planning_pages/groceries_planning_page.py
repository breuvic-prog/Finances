"""The grocery catalogue and price check form the first budget-planning step."""

from collections.abc import Callable
import tkinter as tk

from classes.managers.grocery_catalog_manager import GroceryCatalogManager
from classes.pages.branch_page_class import BranchPage
from classes.pages.child_pages.budget_planning_pages.grocery_items_page import GroceryItemsPage
from classes.pages.child_pages.budget_planning_pages.grocery_prices_page import GroceryPricesPage


class GroceriesPlanningPage(BranchPage):
    def __init__(self, parent_root: tk.Misc, parent_next_method: Callable):
        self._catalog = GroceryCatalogManager()
        super().__init__(parent_root, parent_next_method)

    def _create_pages(self, parent_root: tk.Misc, parent_next_method: Callable):
        self.items_page = GroceryItemsPage(parent_root, parent_next_method, catalog_manager=self._catalog)
        self.prices_page = GroceryPricesPage(parent_root, parent_next_method, self.show_items, self._catalog)
        return [self.items_page, self.prices_page]

    def show_items(self):
        self._show_page(0)

    def show_prices(self):
        self._show_page(1)

    def _show_page(self, index: int):
        if self._page_index < len(self._pages):
            self._pages[self._page_index].deactivate()
        self._page_index = index
        self._pages[index].activate()

    def activate(self):
        super().activate()
        if self._page_index >= len(self._pages):
            self._page_index = 0
        self._pages[self._page_index].activate()
