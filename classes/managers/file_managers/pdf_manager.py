"""Imports"""
import pymupdf
from classes.managers.file_manager import FileManager


class PdfManager(FileManager):
    @classmethod
    def open(cls, name: str,
             path: str) -> list[str]:
        """
        Opens a Pdf file
        :param name:
        :param path:
        :return: The CSV data
        """
        #Gets the final path
        final_path = cls._prepare_path_for_open(name, path)

        # Extracts the data
        # Opens the file
        doc = pymupdf.open(final_path)

        # Extracts the text
        pages = []
        for page in doc:
            pages.append(page.get_text())

        # Closes the file
        doc.close()

        return pages




