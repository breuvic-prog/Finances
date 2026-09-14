# child_page_class.py

import tkinter as tk
from collections.abc import Callable


class ChildPage:
    def __init__(self, parent_root: tk.Misc,
                 parent_next_method: Callable,
                 **kwargs):
        self._root = tk.Frame(parent_root)
        self._parent_next_method = parent_next_method

        super().__init__(**kwargs)

    def activate(self):
        # Packs the component
        self._root.pack()

    def deactivate(self):
        # Unpacks the component
        self._root.pack_forget()