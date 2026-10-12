"""Prepare a ChatGPT price-check ZIP and automatically save returned CSV prices."""

from collections.abc import Callable
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, font

from classes.custom_tk_components.tk_document_input_class import BACKGROUND, BORDER, INK, MUTED, document_button
from classes.custom_tk_components.tk_link_class import TkLink
from classes.custom_tk_components.tk_table_class import TkTable
from classes.managers.grocery_catalog_manager import GroceryCatalogManager
from classes.managers.grocery_price_updates_manager import GroceryPriceUpdatesManager
from classes.pages.leaf_page_class import LeafPage
from classes.table_column_class import TableColumn
from enums.paths_enum import Paths


_DOWNLOADS_PATH = Path(Paths.DOWNLOADS)


class GroceryPricesPage(LeafPage):
    def __init__(self, parent_root: tk.Misc, parent_next_method: Callable, on_back: Callable,
                 catalog_manager: GroceryCatalogManager | None = None, downloads_path: str | Path | None = None):
        self._catalog = catalog_manager if catalog_manager is not None else GroceryCatalogManager()
        self._price_updates = GroceryPriceUpdatesManager(self._catalog)
        self._downloads_path = Path(downloads_path) if downloads_path is not None else _DOWNLOADS_PATH
        self._instructions_zip_path = None
        self._on_back = on_back
        self._items = []
        self._last_updates = ()
        self._load_error = None
        self._preview_table = None
        self._preview_state = None
        super().__init__(parent_root, parent_next_method)
        self._reload_catalog()

    def activate(self):
        # Finish loading and laying out the page before showing it. Rebuilding
        # the mapped table briefly made Tk shrink the entire application.
        self._reload_catalog()
        self._prepare_instructions()
        super().activate()

    def _setup_components(self):
        self._root.configure(bg=BACKGROUND)
        self._root.columnconfigure(0, weight=1)
        self._root.rowconfigure(3, weight=1)
        default = font.nametofont("TkDefaultFont", root=self._root).actual()
        self._bold_font = (default["family"], default["size"], "bold")
        header = tk.Frame(self._root, bg=BACKGROUND)
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 16))
        tk.Label(header, text="BUDGET PLANNING · STEP 1 · GROCERIES 2 OF 2", bg=BACKGROUND, fg=MUTED,
                 anchor="w", font=self._bold_font).pack(fill="x")
        tk.Label(header, text="Update Grocery Prices", bg=BACKGROUND, fg=INK, anchor="w",
                 font=(default["family"], default["size"] + 7, "bold")).pack(fill="x", pady=(5, 0))
        tk.Label(header, text="Send the automatically prepared ZIP to ChatGPT, then select its returned CSV to update prices.",
                 bg=BACKGROUND, fg=MUTED, anchor="w").pack(fill="x", pady=(8, 0))

        # A canvas gives the cards the available width without feeding their
        # wrapped text widths back into the application's requested window size.
        cards_canvas = tk.Canvas(self._root, bg=BACKGROUND, width=840, height=240, highlightthickness=0)
        cards_canvas.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 16))
        cards = tk.Frame(cards_canvas, bg=BACKGROUND)
        cards_window = cards_canvas.create_window((0, 0), window=cards, anchor="nw")
        cards_canvas.bind("<Configure>", lambda event: cards_canvas.itemconfigure(cards_window, width=event.width))
        def resize_cards(event):
            if int(cards_canvas.cget("height")) != event.height:
                cards_canvas.configure(height=event.height)
        cards.bind("<Configure>", resize_cards)
        for column, title, text in (
                (0, "1. Send your groceries to ChatGPT", "instructions.zip is created automatically in Downloads. Upload it to ChatGPT; it contains the instructions and all grocery items."),
                (1, "2. Bring the prices back", "Download ChatGPT's returned CSV and select it below. Valid prices are saved automatically. Blank prices keep the saved price.")):
            cards.columnconfigure(column, weight=1, uniform="price_cards")
            card = tk.Frame(cards, bg="white", highlightthickness=1, highlightbackground=BORDER)
            card.grid(row=0, column=column, sticky="nsew", padx=(0, 12) if column == 0 else 0)
            tk.Label(card, text=title, bg="white", fg=INK, font=self._bold_font, anchor="w").pack(
                fill="x", padx=16, pady=(14, 6))
            hint = tk.Label(card, text=text, bg="white", fg=MUTED, anchor="w", justify="left", wraplength=360)
            hint.pack(fill="x", padx=16, pady=(0, 12))
            card.bind("<Configure>", lambda event, label=hint: label.configure(wraplength=max(100, event.width - 34)))
            actions = tk.Frame(card, bg="white")
            actions.pack(fill="x", padx=16, pady=(0, 14))
            if column == 0:
                self._export_button = document_button(actions, "Regenerate Price Check ZIP", self._prepare_instructions, primary=True)
                self._export_button.pack(side="left", padx=(0, 8))
                TkLink(actions, text="Open ChatGPT", url="https://chatgpt.com", bg="white",
                       font=self._bold_font).pack(side="left")
                self._instructions_status = tk.Label(card, text="Preparing the ZIP when this page opens…",
                                                      bg="white", fg=MUTED, anchor="w", justify="left", wraplength=360)
                self._instructions_status.pack(fill="x", padx=16, pady=(0, 14))
                card.bind("<Configure>", lambda event: self._instructions_status.configure(
                    wraplength=max(100, event.width - 34)), add="+")
            else:
                self._import_button = document_button(actions, "Select Updated CSV", self._import_csv, primary=True)
                self._import_button.pack(fill="x")
                self._import_status = tk.Label(card, text="No updated CSV selected yet.", bg="white", fg=MUTED,
                                               anchor="w", justify="left", wraplength=360)
                self._import_status.pack(fill="x", padx=16, pady=(0, 14))
                card.bind("<Configure>", lambda event: self._import_status.configure(
                    wraplength=max(100, event.width - 34)), add="+")

        toolbar = tk.Frame(self._root, bg=BACKGROUND)
        toolbar.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))
        toolbar.columnconfigure(0, weight=1)
        self._preview_heading = tk.Label(toolbar, bg=BACKGROUND, fg=INK, font=self._bold_font, anchor="w")
        self._preview_heading.grid(row=0, column=0, sticky="ew")
        document_button(toolbar, "Reload Prices", self._reload_catalog).grid(row=0, column=1, padx=(8, 0))

        footer = tk.Frame(self._root, bg=BACKGROUND)
        footer.grid(row=4, column=0, sticky="ew", padx=20, pady=(12, 18))
        footer.columnconfigure(1, weight=1)
        self._status = tk.Label(footer, bg=BACKGROUND, fg=MUTED, anchor="w", justify="left", wraplength=900)
        self._status.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        footer.bind("<Configure>", lambda event: self._status.configure(wraplength=max(100, event.width)))
        back = document_button(footer, "Back to Grocery Items", self._on_back)
        back.configure(height=2, pady=1)
        back.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        self._continue_button = document_button(footer, "Continue to Foods", self._finalize, primary=True)
        self._continue_button.configure(height=2, pady=1)
        self._continue_button.grid(row=1, column=1, sticky="ew")

    def _set_status(self, text: str, error: bool = False):
        self._status.configure(text=text, fg="#B91C1C" if error else MUTED)

    def _reload_catalog(self):
        try:
            self._items = self._catalog.load()
            self._catalog.units_manager.load()
        except (OSError, ValueError) as error:
            self._load_error = str(error)
        else:
            self._load_error = None
        self._refresh()
        self._set_status(self._load_error or "Price checking is optional. Selecting an updated CSV automatically saves valid prices.",
                         bool(self._load_error))

    def _refresh(self):
        current = {item.item_id: item for item in self._items}
        self._last_updates = tuple(update for update in self._last_updates
                                   if update.item.item_id in current and current[update.item.item_id].price == update.price)
        applied = {update.item.item_id: update for update in self._last_updates}
        self._preview_heading.configure(text=f"Last price updates ({len(applied)})" if applied else
                                        f"Saved grocery prices ({len(self._items)})")
        self._export_button.configure(state="disabled" if self._load_error or not self._items else "normal")
        self._import_button.configure(state="disabled" if self._load_error or not self._items else "normal")
        state = (tuple(self._items), self._last_updates)
        if self._preview_table is not None and self._preview_state == state:
            return
        previous = self._preview_table
        table = TkTable(self._root, review_style=True, stretch_column=0, columns=[
            TableColumn("Name", str), TableColumn("Previous Price", str), TableColumn("Current Price", str),
            TableColumn("Change", tk.Widget)])
        for item in self._items:
            update = applied.get(item.item_id)
            difference = update.price - update.item.price if update else None
            change = tk.Label(table._body, text=(f"{'+' if difference >= 0 else '-'}${abs(difference):,.2f}"
                                                if update else "—"))
            table.add_row((item.name, f"${update.item.price:,.2f}" if update else "—", f"${item.price:,.2f}", change))
            if update:
                change.configure(fg="#B91C1C" if difference > 0 else "#15803D", font=self._bold_font)
        if not self._items:
            tk.Label(table._body, text="Add grocery items on the previous page to check their prices.",
                     bg="white", fg=MUTED, padx=24, pady=40).grid(row=0, column=0, columnspan=4, sticky="ew")
        table.grid(row=3, column=0, sticky="nsew", padx=20)
        self._preview_table, self._preview_state = table, state
        if previous is not None:
            previous.destroy()

    def _prepare_instructions(self):
        if self._load_error or not self._items:
            self._instructions_status.configure(text=self._load_error or "Add grocery items on the previous page to prepare the ZIP.",
                                                 fg="#B91C1C" if self._load_error else MUTED)
            return
        try:
            self._instructions_zip_path = self._price_updates.download_package(self._downloads_path)
        except (OSError, ValueError) as error:
            self._instructions_status.configure(text=f"Could not create the price-check ZIP: {error}\nClick Regenerate to try again.",
                                                 fg="#B91C1C")
            return
        self._instructions_status.configure(text=f"ZIP ready in Downloads:\n{self._instructions_zip_path}", fg="#15803D")

    def _import_csv(self):
        if self._load_error or not self._items:
            return
        path = filedialog.askopenfilename(parent=self._root, title="Import Updated Grocery Prices",
                                         filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        try:
            updates = self._price_updates.read_updates(path)
            count = self._price_updates.apply_updates(updates)
        except (OSError, ValueError) as error:
            self._import_status.configure(text=f"Could not import {Path(path).name}.", fg="#B91C1C")
            self._set_status(str(error), True)
            return
        self._last_updates = updates
        self._reload_catalog()
        self._import_status.configure(text=f"{Path(path).name}: {count} prices updated.", fg="#15803D")
        self._set_status(f"Saved {count} updated prices automatically. These prices will be available the next time you open the program."
                         if count else "No price changes to apply. Blank or unchanged prices keep the saved price.")

    def _finalize(self):
        self._parent_next_method()
