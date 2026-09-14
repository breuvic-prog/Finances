"""Imports"""
from abc import ABC
from classes.pages.page_container_class import PageContainer
from classes.pages.child_page_class import ChildPage
import tkinter as tk
from collections.abc import Callable


class BranchPage(PageContainer, ChildPage, ABC):
    def __init__(self, parent_root:tk.Tk|tk.Frame,
                 parent_next_method:Callable):
        super().__init__(parent_root = parent_root,
                         parent_next_method = parent_next_method)