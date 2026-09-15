"""Imports"""
import tkinter as tk

class TkTable(tk.Frame):
    def __init__(self, parent: tk.Misc,
                 **kwargs):
        super().__init__(parent,
                         **kwargs)