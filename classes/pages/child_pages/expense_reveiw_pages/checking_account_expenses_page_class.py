"""Imports"""
from tkinter import filedialog
from classes.custom_tk_components.tk_document_input_class import TkDocumentInput, TkFileUpload
from classes.managers.date_manager import DateManager
from classes.managers.file_manager import FileManager
from classes.managers.path_manager import PathManager
from classes.pages.leaf_page_class import LeafPage
import tkinter as tk
from collections.abc import Callable
from enums.files_enum import Files
from enums.folders_enum import Folders
from pathlib import Path
from classes.managers.review_files_manager import ReviewFilesManager

"""Constants"""
FREEDOM_LOGIN_LINK = "https://www.freedombnk.com/Pages/login.aspx"


class CheckingAccountExpensesPage(LeafPage):
    def __init__(self, parent_root: tk.Tk|tk.Frame,
                 parent_next_method: Callable, review_files: ReviewFilesManager | None = None):
        self._review_files = review_files if review_files is not None else ReviewFilesManager()
        # Previous month components
        self._previous_month_file_button = None
        self._previous_month_path = None
        self._previous_month_warning_label = None

        super().__init__(parent_root, parent_next_method)

    def _setup_components(self) -> None:
        # Gets necessary information
        current_month = DateManager.get_current_month()
        previous_month = DateManager.month_number_to_name((current_month - 2) % 12 + 1)

        layout = TkDocumentInput(
            self._root, title="Checking Account Statement",
            subtitle=f"Add your Freedom Bank PDF for the {previous_month} expense review.", step=2,
            next_text="Continue to Receipts", on_next=self._finalize,
        )
        instructions = layout.card("Download from Freedom Bank", "Use the monthly checking-account statement.")
        layout.instructions(instructions, (
            "Sign in to your Freedom Bank account.",
            "Open your checking account by clicking its account number.",
            'Choose "Online Statements".',
            f"Download the {previous_month} statement as a PDF.",
        ), link_text="Open Freedom Bank login", url=FREEDOM_LOGIN_LINK)
        uploads = layout.card("Upload statement", "Select the PDF you just downloaded.")
        self._previous_month_upload = TkFileUpload(
            uploads, f"{previous_month} statement", "PDF", f"Must provide the {previous_month} PDF"
        )
        self._previous_month_upload.pack(fill="x", padx=16, pady=(0, 16))
        self._previous_month_warning_label = self._previous_month_upload.warning
        self._previous_month_file_button = self._previous_month_upload.button
        self._previous_month_file_button.configure(command=lambda: self._get_file_path(
            "_previous_month_path", self._previous_month_upload
        ))

    def _get_file_path(self, path_attribute: str, upload: TkFileUpload):
        # Gets the path
        path = filedialog.askopenfilename(title="Select a PDF",
                                          filetypes=[("PDF Files", "*.pdf")], parent=self._root.winfo_toplevel())
        # Checks if a path was actually returned
        if path == "":
            upload.warning.activate()
        else:
            upload.select_path(path)

            # Updates path variable
            setattr(self, path_attribute, path)

    def _finalize(self) -> None:
        # Checks if the  statement was entered
        if self._previous_month_path is None:
            if self._previous_month_path is None:
                self._previous_month_warning_label.activate()
        else:
            final_path = PathManager.join(Folders.ASSETS,
                                          Folders.PDFS)
            # Copies the billing statements inside the code
            FileManager.copy(source_path=self._previous_month_path,
                             destination_path=final_path,
                             destination_name=Files.CHECKING_ACCOUNT_PREVIOUS_MONTH_STATEMENT_PDF)
            self._review_files.track_file(Path(final_path) / Files.CHECKING_ACCOUNT_PREVIOUS_MONTH_STATEMENT_PDF,
                                          final_path)


            # Calls parent next method
            self._parent_next_method()

