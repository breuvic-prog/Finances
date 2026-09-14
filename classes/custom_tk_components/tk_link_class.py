"""Imports"""
import tkinter as tk
import webbrowser


class TkLink(tk.Label):

    def __init__(self, parent: tk.Misc,
                 text: str,
                 url: str,
                 **kwargs):

        super().__init__(parent,
                         text = text,
                         fg = "#0B57D0",
                         cursor = "hand2",
                         **kwargs)

        self._url = url

        self.bind("<Button-1>",
                  self._open_link)

    def _open_link(self, event = None) -> None:
        webbrowser.open(self._url)