"""Imports"""
from abc import ABC, abstractmethod
from collections.abc import Callable
import tkinter as tk
from classes.pages.child_page_class import ChildPage


class PageContainer(ABC):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._pages: list[ChildPage] = []
        self._page_index = 0

        # Creates and stores this container's child pages.
        self._set_pages(self._create_pages(parent_root = self._root,
                                           parent_next_method = self.next_page))

    """Helper Methods"""

    def _set_pages(self, pages: list[ChildPage]) -> None:
        self._pages = pages
        self._page_index = 0

        if self._pages:
            self._pages[0].activate()

    @abstractmethod
    def _create_pages(self, parent_root: tk.Tk | tk.Frame,
                      parent_next_method: Callable) -> list[ChildPage]:
        raise NotImplementedError

    """Page Navigation Methods"""
    def next_page(self) -> None:
        # Remove/deactivate the current page.
        self._pages[self._page_index].deactivate()

        # Move to the next page.
        self._page_index += 1

        # Activate the next page if one remains.
        if self._page_index < len(self._pages):
            self._pages[self._page_index].activate()