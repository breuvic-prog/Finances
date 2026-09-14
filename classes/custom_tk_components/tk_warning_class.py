"""Imports"""
import tkinter as tk


class TkWarning(tk.Label):

    def __init__(self, parent: tk.Misc,
                 warning_text: str,
                 **kwargs):
        self._warning_text = warning_text

        super().__init__(parent,
                         fg = "red",
                         **kwargs)

    def activate(self):
        self.config(text = self._warning_text)

    def deactivate(self):
        self.config(text = "")

