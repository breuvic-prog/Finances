"""Imports"""
from tkinter import filedialog
from pathlib import Path
import os
import tempfile
from zipfile import BadZipFile, ZipFile

from classes.custom_tk_components.tk_document_input_class import TkDocumentInput, TkFileUpload, document_button
from classes.managers.file_manager import FileManager
from classes.managers.folder_manager import FolderManager
from classes.managers.path_manager import PathManager
from classes.managers.receipt_instruction_manager import ReceiptInstructionManager
from classes.managers.review_files_manager import ReviewFilesManager
from classes.pages.leaf_page_class import LeafPage
import tkinter as tk
from collections.abc import Callable
from enums.files_enum import Files
from enums.paths_enum import Paths

"""Constants"""
CHAT_GPT_LINK = "https://chatgpt.com"

class ReceiptsInputPage(LeafPage):
    def __init__(self, parent_root: tk.Tk|tk.Frame, parent_next_method: Callable,
                 review_files: ReviewFilesManager | None = None):
        self._review_files = review_files if review_files is not None else ReviewFilesManager()
        self._zip_path = None
        self._zip_warning_label = None
        self._instructions_zip_path = None
        self._instructions_status = None

        super().__init__(parent_root, parent_next_method)

    def _setup_components(self) -> None:
        layout = TkDocumentInput(
            self._root, title="Purchase Receipts",
            subtitle="Prepare your receipts with ChatGPT, then upload the completed ZIP.", step=3,
            next_text="Continue to Transaction Review", on_next=self._finalize,
        )
        instructions = layout.card("Prepare your receipts", "Start on your computer, then use your phone for photos.")
        layout.instructions(instructions, (
            "Open ChatGPT on your computer.",
            "Upload instructions.zip from your Downloads folder to ChatGPT and submit it. The file is created automatically.",
            'Use ChatGPT on your phone to photograph your receipts. Say "Done" after the photos, '
            "then follow the remaining receipt prompts.",
            "Back on your computer, download the final ZIP from ChatGPT and select it here.",
        ), link_text="Open ChatGPT", url=CHAT_GPT_LINK)
        uploads = layout.card("Instructions and receipt ZIP", "Your instructions are prepared automatically. Upload the finished receipts below.")
        document_button(uploads, "Regenerate instructions.zip", self._prepare_instructions).pack(
            fill="x", padx=16, pady=(0, 8)
        )
        self._instructions_status = tk.Label(uploads, text="Preparing instructions when this step opens…",
                                             bg="white", fg="#64748B", anchor="w", justify="left", wraplength=320)
        self._instructions_status.pack(fill="x", padx=16, pady=(0, 16))
        self._zip_upload = TkFileUpload(uploads, "Completed receipts", "ZIP", "Must provide the zip file")
        self._zip_upload.pack(fill="x", padx=16, pady=(0, 16))
        self._zip_warning_label = self._zip_upload.warning
        self._zip_upload.button.configure(command=lambda: self._get_file_path("_zip_path", self._zip_upload))


    def _finalize(self) -> None:
        if self._zip_path is None:
            self._zip_warning_label.activate()
        else:
            # Check the uploaded ZIP before deleting the current receipts.
            with ZipFile(self._zip_path) as archive:
                corrupt_file = archive.testzip()
                if corrupt_file is not None:
                    raise BadZipFile(f"Receipt ZIP contains a corrupt file: {corrupt_file}")
                imported_paths = [ReviewFilesManager.validate_path(Path(Paths.RECEIPTS) / member.filename,
                                                                  Paths.RECEIPTS)
                                  for member in archive.infolist() if not member.is_dir()]

            # Remove the previous receipt JSONs before extracting the new set.
            if PathManager.exists(Paths.RECEIPTS):
                for receipt_file_name in FileManager.get_files_at_location(Paths.RECEIPTS):
                    if receipt_file_name.lower().endswith(".json"):
                        FileManager.delete(PathManager.join(Paths.RECEIPTS, receipt_file_name))

            #Extracts the receipt files from the zip file
            FolderManager.unzip(path = self._zip_path,
                                destination_path = Paths.RECEIPTS)
            for path in imported_paths:
                self._review_files.track_file(path, Paths.RECEIPTS)

            # Calls parent next method
            self._parent_next_method()

    def _get_file_path(self, path_attribute: str, upload: TkFileUpload):
        # Gets the path
        path = filedialog.askopenfilename(title="Select a ZIP",
                                          filetypes=[("ZIP Files", "*.zip")], parent=self._root.winfo_toplevel())
        # Checks if a path was actually returned
        if path == "":
            upload.warning.activate()
        else:
            upload.select_path(path)

            # Updates path variable
            setattr(self, path_attribute, path)


    def activate(self):
        super().activate()
        # Pages are constructed before statement imports; generate only when reached.
        self._prepare_instructions()

    def _prepare_instructions(self):
        try:
            self._download_instructions()
        except (OSError, ValueError) as error:
            self._instructions_status.configure(
                text=f"Could not create instructions.zip: {error}\nClick Regenerate to try again.", fg="#B91C1C")
        else:
            self._instructions_status.configure(
                text=f"instructions.zip is ready in your Downloads folder.\n{self._instructions_zip_path}", fg="#15803D")

    def _download_instructions(self) -> None:
        downloads = Path(Paths.DOWNLOADS)
        downloads.mkdir(parents=True, exist_ok=True)
        # Build separately so a failure retains the previous ZIP and any existing instructions folder.
        with tempfile.TemporaryDirectory(prefix="receipt-instructions-", dir=downloads) as workspace:
            instructions_path = FolderManager.create(name="instructions", path=workspace)
            ReceiptInstructionManager.create(instructions_path)
            FileManager.copy(source_path=Paths.ASSETS_JSONS, source_name=Files.RECEIPT_EXAMPLE_JSON,
                             destination_path=instructions_path, destination_name=Files.RECEIPT_EXAMPLE_JSON)
            archive = FolderManager.zip(instructions_path)
            destination = downloads / "instructions.zip"
            os.replace(archive, destination)
            self._instructions_zip_path = str(destination)
            self._review_files.track_file(destination, downloads)

