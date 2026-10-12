"""Imports"""
import tkinter as tk
from collections.abc import Callable
from tkinter import filedialog, messagebox
from pathlib import Path
from classes.custom_tk_components.tk_document_input_class import TkDocumentInput, TkFileUpload
from classes.managers.date_manager import DateManager
from classes.managers.discover_statement_manager import DiscoverStatementManager
from classes.managers.file_manager import FileManager
from classes.managers.path_manager import PathManager
from classes.managers.review_files_manager import ReviewFilesManager
from classes.pages.leaf_page_class import LeafPage
from enums.files_enum import Files
from enums.folders_enum import Folders

"""Constants"""
DISCOVER_LOGIN_LINK = "https://www.discover.com/login/"
BILLING_STATEMENT_NAME = "credit_card_billing_statement"


class CreditCardExpensesPage(LeafPage):
    def __init__(self, parent_root: tk.Tk|tk.Frame,
                 parent_next_method: Callable, review_files: ReviewFilesManager | None = None):
        self._review_files = review_files if review_files is not None else ReviewFilesManager()
        #Previous month components
        self._previous_month_file_button = None
        self._previous_month_path = None
        self._previous_month_warning_label = None

        #Previous previous month components
        self._previous_previous_month_file_button = None
        self._previous_previous_month_path = None
        self._previous_previous_month_warning_label = None


        super().__init__(parent_root, parent_next_method)



    def _setup_components(self) -> None:
        # Gets necessary information
        current_month = DateManager.get_current_month()
        previous_month = DateManager.month_number_to_name((current_month - 2) % 12 + 1)

        layout = TkDocumentInput(
            self._root, title="Credit Card Statements",
            subtitle=f"Gather your Discover PDFs for the {previous_month} expense review.", step=1,
            next_text="Continue to Checking Account", on_next=self._finalize,
        )
        instructions = layout.card("Download from Discover", "Use PDF account-activity exports with transaction details.")
        layout.instructions(instructions, (
            "Sign in to your Discover account.",
            'Open "Activity", then "Activity and Statements".',
            'Under "Show Me | Current Statement", choose "View Previous Statements".',
            f"Download PDFs for the two statement periods covering {previous_month}: the latest statement and the one before it.",
        ), link_text="Open Discover login", url=DISCOVER_LOGIN_LINK)
        uploads = layout.card("Upload statements", "Both statements are needed to cover the review month.")
        self._previous_month_upload = TkFileUpload(
            uploads, "Latest activity statement", "PDF", "Must provide the latest statement PDF"
        )
        self._previous_month_upload.pack(fill="x", padx=16, pady=(0, 12))
        self._previous_month_file_button = self._previous_month_upload.button
        self._previous_month_warning_label = self._previous_month_upload.warning
        self._previous_month_file_button.configure(command=lambda: self._get_file_path(
            "_previous_month_path", self._previous_month_upload
        ))
        self._previous_previous_month_upload = TkFileUpload(
            uploads, "Previous activity statement", "PDF", "Must provide the preceding statement PDF"
        )
        self._previous_previous_month_upload.pack(fill="x", padx=16, pady=(0, 16))
        self._previous_previous_month_file_button = self._previous_previous_month_upload.button
        self._previous_previous_month_warning_label = self._previous_previous_month_upload.warning
        self._previous_previous_month_file_button.configure(command=lambda: self._get_file_path(
            "_previous_previous_month_path", self._previous_previous_month_upload
        ))

    def _get_file_path(self, path_attribute: str, upload: TkFileUpload):
        #Gets the path
        path = filedialog.askopenfilename(title = "Select a PDF",
                                          filetypes = [("PDF Files", "*.pdf")], parent=self._root.winfo_toplevel())
        #Checks if a path was actually returned
        if path == "":
            upload.warning.activate()
        else:
            upload.select_path(path)

            #Updates path variable
            setattr(self, path_attribute, path)

    def _finalize(self) -> None:
        #Checks if the billing statement was entered
        if self._previous_month_path is None or self._previous_previous_month_path is None:
            if self._previous_month_path is None:
                self._previous_month_warning_label.activate()
            if self._previous_previous_month_path is None:
                self._previous_previous_month_warning_label.activate()
        else:
            # Validate both PDFs before replacing either imported statement.
            try:
                DiscoverStatementManager.open(name=self._previous_month_path, path="")
                DiscoverStatementManager.open(name=self._previous_previous_month_path, path="")
            except (OSError, ValueError) as error:
                messagebox.showerror("Could not read Discover PDF", str(error), parent=self._root)
                return
            final_path = PathManager.join(Folders.ASSETS,
                                          Folders.PDFS)
            names = (Files.CREDIT_CARD_PREVIOUS_MONTH_STATEMENT_PDF,
                     Files.CREDIT_CARD_PREVIOUS_PREVIOUS_MONTH_STATEMENT_PDF)
            if any((Path(final_path) / name).exists() for name in names):
                if not messagebox.askyesno("Replace imported Discover statements?",
                                          "Saved Discover PDFs already exist. Replace them with the selected PDFs?",
                                          parent=self._root, default="no"):
                    return
            #Copies the billing statements inside the code
            FileManager.copy(source_path = self._previous_month_path,
                             destination_path = final_path,
                             destination_name = Files.CREDIT_CARD_PREVIOUS_MONTH_STATEMENT_PDF)
            self._review_files.track_file(Path(final_path) / names[0], final_path)
            FileManager.copy(source_path = self._previous_previous_month_path,
                             destination_path = final_path,
                             destination_name = Files.CREDIT_CARD_PREVIOUS_PREVIOUS_MONTH_STATEMENT_PDF)
            self._review_files.track_file(Path(final_path) / names[1], final_path)

            #Calls parent next method
            self._parent_next_method()





