"""Shared presentation for the document steps in an expense review."""

from collections.abc import Callable
from pathlib import Path
import tkinter as tk
from tkinter import font, ttk

from classes.custom_tk_components.tk_link_class import TkLink
from classes.custom_tk_components.tk_warning_class import TkWarning


BACKGROUND = "#F4F6F9"
INK = "#172B4D"
MUTED = "#64748B"
BORDER = "#DDE4EC"


def document_button(parent: tk.Misc, text: str, command: Callable, primary: bool = False) -> tk.Button:
    default = font.nametofont("TkDefaultFont", root=parent).actual()
    return tk.Button(
        parent, text=text, command=command, relief="flat", borderwidth=2,
        bg="#2563EB" if primary else "#E5EFFB", fg="white" if primary else "#234E78",
        activebackground="#1D4ED8" if primary else "#CADCF2",
        activeforeground="white" if primary else "#234E78",
        font=(default["family"], default["size"], "bold"), cursor="hand2", padx=12, pady=7,
    )


class TkFileUpload(tk.Frame):
    """A file chooser with a separate filename and validation message."""

    def __init__(self, parent: tk.Misc, title: str, file_type: str, warning_text: str):
        super().__init__(parent, bg="#F8FAFC", highlightthickness=1, highlightbackground=BORDER)
        self.columnconfigure(0, weight=1)
        default = font.nametofont("TkDefaultFont", root=self).actual()
        tk.Label(self, text=title, bg="#F8FAFC", fg=INK, anchor="w",
                 font=(default["family"], default["size"], "bold")).grid(
            row=0, column=0, sticky="ew", padx=(12, 8), pady=(12, 0)
        )
        tk.Label(self, text=file_type, bg="#EAF0F7", fg=MUTED, padx=7, pady=3).grid(
            row=0, column=1, padx=(0, 12), pady=(12, 0)
        )
        self.filename = tk.Label(self, text="No file selected", bg="#F8FAFC", fg=MUTED,
                                 anchor="w", justify="left", wraplength=300)
        self.filename.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(8, 10))
        self.button = document_button(self, f"Choose {file_type}", lambda: None)
        self.button.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12)
        self.warning = TkWarning(self, warning_text=warning_text, bg="#F8FAFC",
                                 anchor="w", justify="left", wraplength=300)
        self.warning.grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=(4, 8))
        self.bind("<Configure>", self._resize_labels)

    def _resize_labels(self, event):
        for label in (self.filename, self.warning):
            label.configure(wraplength=max(100, event.width - 26))

    def select_path(self, path: str) -> None:
        self.filename.configure(text=f"Selected: {Path(path).name}", fg="#15803D")
        self.button.configure(text="Change file")
        self.warning.deactivate()


class TkDocumentInput(tk.Frame):
    """A responsive setup page with a fixed footer and scrollable cards."""

    def __init__(self, parent: tk.Misc, title: str, subtitle: str, step: int,
                 next_text: str, on_next: Callable):
        super().__init__(parent, bg=BACKGROUND)
        parent.configure(bg=BACKGROUND)
        self.pack(fill="both", expand=True)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._cards: list[tk.Frame] = []
        self._wheel_remainder = 0
        default = font.nametofont("TkDefaultFont", root=self).actual()
        self._bold_font = (default["family"], default["size"], "bold")

        header = tk.Frame(self, bg=BACKGROUND)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(18, 14))
        header.columnconfigure(0, weight=1)
        tk.Label(header, text=title, bg=BACKGROUND, fg=INK, anchor="w",
                 font=(default["family"], default["size"] + 7, "bold")).grid(row=0, column=0, sticky="ew")
        tk.Label(header, text=f"Step {step} of 4", bg="#E5EFFB", fg="#234E78",
                 padx=10, pady=5, font=self._bold_font).grid(row=0, column=1, sticky="e")
        hint = tk.Label(header, text=subtitle, bg=BACKGROUND, fg=MUTED, anchor="w", justify="left")
        hint.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 14))
        header.bind("<Configure>", lambda event: hint.configure(wraplength=max(100, event.width)))
        progress = tk.Frame(header, bg=BACKGROUND)
        progress.grid(row=2, column=0, columnspan=2, sticky="ew")
        for index, text in enumerate(("Credit card", "Checking account", "Receipts", "Review"), start=1):
            progress.columnconfigure(index - 1, weight=1, uniform="document_progress")
            selected = index == step
            tk.Label(progress, text=f"{index}. {text}", padx=8, pady=8,
                     bg="#2563EB" if selected else "#EAF0F7",
                     fg="white" if selected else MUTED, font=self._bold_font).grid(
                row=0, column=index - 1, sticky="ew", padx=(0, 6) if index < 4 else 0
            )

        self._canvas = tk.Canvas(self, bg=BACKGROUND, highlightthickness=0,
                                 width=920, height=450, yscrollincrement=20)
        self._canvas.grid(row=1, column=0, sticky="nsew", padx=(20, 0))
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        scrollbar.grid(row=1, column=1, sticky="ns", padx=(4, 20))
        self._canvas.configure(yscrollcommand=scrollbar.set)
        self._content = tk.Frame(self._canvas, bg=BACKGROUND)
        self._content.columnconfigure(0, weight=1, uniform="document_cards")
        self._content.columnconfigure(1, weight=1, uniform="document_cards")
        self._content_window = self._canvas.create_window((0, 0), window=self._content, anchor="nw")
        self._content.bind("<Configure>", lambda event: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", self._resize_content)

        footer = tk.Frame(self, bg=BACKGROUND)
        footer.grid(row=2, column=0, columnspan=2, sticky="ew", padx=20, pady=(12, 18))
        self.next_button = document_button(footer, next_text, on_next, primary=True)
        self.next_button.configure(height=2, pady=1)
        self.next_button.pack(fill="x")
        self.bind("<Map>", lambda event: self._bind_scrolling(self))

    def card(self, title: str, subtitle: str) -> tk.Frame:
        card = tk.Frame(self._content, bg="white", highlightthickness=1, highlightbackground=BORDER)
        heading = tk.Label(card, text=title, bg="white", fg=INK, anchor="w", justify="left",
                           font=self._bold_font, wraplength=350)
        heading.pack(fill="x", padx=16, pady=(16, 5))
        hint = tk.Label(card, text=subtitle, bg="white", fg=MUTED, anchor="w", justify="left", wraplength=350)
        hint.pack(fill="x", padx=16, pady=(0, 14))
        def resize_labels(event):
            for label in (heading, hint):
                label.configure(wraplength=max(100, event.width - 34))

        card.bind("<Configure>", resize_labels)
        self._cards.append(card)
        self._resize_content()
        return card

    def instructions(self, card: tk.Frame, steps: tuple[str, ...], link_text: str, url: str) -> None:
        TkLink(card, text=link_text, url=url, bg="white", font=self._bold_font,
               anchor="w", padx=0, pady=0).pack(fill="x", padx=16, pady=(0, 12))
        for number, text in enumerate(steps, start=1):
            row = tk.Frame(card, bg="white")
            row.pack(fill="x", padx=16, pady=(0, 14))
            row.columnconfigure(1, weight=1)
            tk.Label(row, text=str(number), bg="#E5EFFB", fg="#234E78", width=2,
                     padx=5, pady=5, font=self._bold_font).grid(row=0, column=0, sticky="nw")
            label = tk.Label(row, text=text, bg="white", fg="#334155", justify="left", anchor="w", wraplength=320)
            label.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=3)
            row.bind("<Configure>", lambda event, label=label: label.configure(wraplength=max(100, event.width - 46)))

    def _resize_content(self, event=None):
        width = event.width if event is not None else max(1, self._canvas.winfo_width())
        self._canvas.itemconfigure(self._content_window, width=width)
        stacked = width < 760
        for index, card in enumerate(self._cards):
            card.grid(row=index if stacked else 0, column=0 if stacked else index,
                      columnspan=2 if stacked else 1, sticky="new",
                      padx=0 if stacked else ((0, 8) if index == 0 else (8, 0)), pady=(0, 12))

    def _bind_scrolling(self, widget: tk.Misc) -> None:
        widget.bind("<MouseWheel>", self._scroll)
        widget.bind("<Button-4>", self._scroll)
        widget.bind("<Button-5>", self._scroll)
        for child in widget.winfo_children():
            self._bind_scrolling(child)

    def _scroll(self, event):
        if self._content.winfo_height() <= self._canvas.winfo_height():
            return "break"
        if getattr(event, "num", None) in (4, 5):
            units = -1 if event.num == 4 else 1
        else:
            self._wheel_remainder += event.delta
            notches = int(self._wheel_remainder / 120)
            self._wheel_remainder -= notches * 120
            units = -notches
        if units:
            self._canvas.yview_scroll(units, "units")
        return "break"
