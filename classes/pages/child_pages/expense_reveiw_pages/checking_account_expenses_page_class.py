"""Imports"""
from tkinter import filedialog
from classes.custom_tk_components.tk_link_class import TkLink
from classes.custom_tk_components.tk_title_class import TkTitle
from classes.custom_tk_components.tk_warning_class import TkWarning
from classes.managers.date_manager import DateManager
from classes.managers.file_manager import FileManager
from classes.managers.path_manager import PathManager
from classes.pages.leaf_page_class import LeafPage
import tkinter as tk
from collections.abc import Callable
from enums.files_enum import Files
from enums.folders_enum import Folders

"""Constants"""
FREEDOM_LOGIN_LINK = "https://www.freedombnk.com/Pages/login.aspx"


class CheckingAccountExpensesPage(LeafPage):
    def __init__(self, parent_root: tk.Tk|tk.Frame,
                 parent_next_method: Callable):
        # Previous month components
        self._previous_month_file_button = None
        self._previous_month_path = None
        self._previous_month_warning_label = None

        super().__init__(parent_root, parent_next_method)

    def _setup_components(self) -> None:
        # Gets necessary information
        current_month = DateManager.get_current_month()
        previous_month = DateManager.month_number_to_name((current_month - 2) % 12 + 1)

        # Step 1
        TkTitle(self._root,
                text="Step 1: Login to Freedom").pack()
        TkLink(self._root,
               text="Login Link",
               url=FREEDOM_LOGIN_LINK).pack()

        # Step 2
        TkTitle(self._root,
                text="Step 2: Click on the Checking Account's account number").pack()

        #Step 3
        TkTitle(self._root,
                text='Step 3: Click on "Online Statements"').pack()

        # Step 4
        TkTitle(self._root,
                text=f'Step 4: Click on the {previous_month} statement, download, and submit it here').pack()
        self._previous_month_warning_label = TkWarning(self._root,
                                                       warning_text=f"Must provide the {previous_month} PDF")
        self._previous_month_warning_label.pack()
        self._previous_month_file_button = tk.Button(self._root,
                                                     text=f"Enter the {previous_month} statement here",
                                                     command=lambda: self._get_file_path(
                                                         "_previous_month_path",
                                                         self._previous_month_file_button,
                                                         self._previous_month_warning_label))
        self._previous_month_file_button.pack()

        tk.Button(self._root,
                  text="Next",
                  command=self._finalize).pack()

    def _get_file_path(self, path_attribute: str, button, warning_label):
        # Gets the path
        path = filedialog.askopenfilename(title="Select a PDF",
                                          filetypes=[("PDF Files", "*.pdf")])
        # Checks if a path was actually returned
        if path == "":
            warning_label.activate()
        else:
            # Resets text of the warning label
            warning_label.deactivate()

            # Changes button text to path
            button.config(text=path)

            # Updates path variable
            setattr(self, path_attribute, path)

    def _finalize(self) -> None:
        # Checks if the  statement was entered
        if self._previous_month_path is None:
            if self._previous_month_path is None:
                self._previous_month_warning_label.activate()
        else:
            # TODO:Need to change the final save locations
            final_path = PathManager.join(Folders.ASSETS,
                                          Folders.PDFS)
            # Copies the billing statements inside the code
            FileManager.copy(source_path=self._previous_month_path,
                             destination_path=final_path,
                             destination_name=Files.CHECKING_ACCOUNT_PREVIOUS_MONTH_STATEMENT_PDF)


            # Calls parent next method
            self._parent_next_method()

