"""Imports"""
from classes.pages.child_page_class import ChildPage
import tkinter as tk
from collections.abc import Callable
from abc import ABC, abstractmethod

class LeafPage(ChildPage, ABC):
    def __init__(self, parent_root: tk.Tk|tk.Frame,
                 parent_next_method: Callable):
        super().__init__(parent_root = parent_root,
                         parent_next_method = parent_next_method)

        #Sets up the components
        self._setup_components()
    @abstractmethod
    def _setup_components(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def _finalize(self) -> None:
        raise NotImplementedError
