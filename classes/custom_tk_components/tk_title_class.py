"""Imports"""
import tkinter as tk


class TkTitle(tk.Label):
    def __init__(self, parent: tk.Misc,
                 text: str,
                 font_size: int = 18,
                 **kwargs):
        super().__init__(parent,
                         text = text,
                         font = ("TkDefaultFont", font_size, "bold"),
                         **kwargs)