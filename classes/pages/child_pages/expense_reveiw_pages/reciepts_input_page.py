"""Imports"""
from tkinter import filedialog

from classes.custom_tk_components.tk_link_class import TkLink
from classes.custom_tk_components.tk_title_class import TkTitle
from classes.custom_tk_components.tk_warning_class import TkWarning
from classes.managers.file_manager import FileManager
from classes.managers.folder_manager import FolderManager
from classes.managers.path_manager import PathManager
from classes.pages.leaf_page_class import LeafPage
import tkinter as tk
from collections.abc import Callable
from enums.files_enum import Files
from enums.paths_enum import Paths

"""Constants"""
CHAT_GPT_LINK = "https://chatgpt.com"

class ReceiptsInputPage(LeafPage):
    def __init__(self, parent_root: tk.Tk|tk.Frame, parent_next_method: Callable):
        self._zip_path = None
        self._zip_warning_label = None
        self._instructions_zip_path = None

        super().__init__(parent_root, parent_next_method)

    def _setup_components(self) -> None:
        # Step 1
        TkTitle(self._root,
                text="Step 1: Go to Chat GPT on Computer").pack()
        TkLink(self._root,
               text="Chat GPT Link",
               url=CHAT_GPT_LINK).pack()

        #Step 2
        TkTitle(self._root,
                text="Step 2: Download the instructions information below, upload to chat gpt, and submit").pack()

        tk.Button(self._root, text = "Download instructions.zip",
                  command = self._download_instructions).pack()

        #Step 3
        TkTitle(self._root,
                text="Step 3: Open Chat GPT on Phone, and take pictures of all receipts, say 'Done' when finished").pack()

        # Step 4
        TkTitle(self._root,
                text="Step 4: Go back to computer, download the zip file, and upload it below").pack()
        self._zip_warning_label = TkWarning(self._root,
                                      warning_text=f"Must provide the zip file")
        self._zip_warning_label.pack()

        zip_button = tk.Button(self._root,
                               text=f"Enter the zip file here",
                               command=lambda: self._get_file_path(
                                                         "_zip_path",
                                                         zip_button,
                                                         self._zip_warning_label))
        zip_button.pack()

        tk.Button(self._root,
                  text="Next",
                  command=self._finalize).pack()


    def _finalize(self) -> None:
        if self._zip_path is None:
            self._zip_warning_label.activate()
        else:
            #Delete instructions.zip
            #FileManager.delete(self._instructions_zip_path)

            #Extracts the receipt files from the zip file
            FolderManager.unzip(path = self._instructions_zip_path,
                                destination_path = Paths.ASSETS_JSONS_RECEIPTS)


            # Calls parent next method
            self._parent_next_method()

    def _get_file_path(self, path_attribute: str, button, warning_label):
        # Gets the path
        path = filedialog.askopenfilename(title="Select a ZIP",
                                          filetypes=[("ZIP Files", "*.zip")])
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


    def _download_instructions(self) -> None:
        #Create folder in downloads
        instructions_path = FolderManager.create(name = "instructions",
                                                 path = Paths.DOWNLOADS)

        #Copies the instructions txt file
        FileManager.copy(source_path = Paths.ASSETS_TXTS,
                         source_name = Files.RECEIPT_INSTRUCTIONS_TXT,
                         destination_path = instructions_path,
                         destination_name = Files.RECEIPT_INSTRUCTIONS_TXT)

        #Copies the receipt_example json file
        FileManager.copy(source_path=Paths.ASSETS_JSONS,
                         source_name=Files.RECEIPT_EXAMPLE_JSON,
                         destination_path=instructions_path,
                         destination_name=Files.RECEIPT_EXAMPLE_JSON)

        #Zips up the folder
        self._instructions_zip_path = FolderManager.zip(instructions_path)

        #Deletes the original folder
        FolderManager.delete(instructions_path)

