"""Imports"""
import json
from classes.managers.file_manager import FileManager


class JsonManager(FileManager):
    @classmethod
    def create(cls, name: str,
               path: str,
               content:list[str] = None) -> str:
        """
        Creates a JSON file
        :param name: File name
        :param path: File path
        :param content: File content
        :return: The created file path
        """
        #Prepares the final path
        final_path = cls._prepare_path_for_create(name, path)

        # Opens and closes the file
        with open(final_path, "w") as out_file:
            #Checks if there's any content to write
            if content is not None:
                #Writes all the content
                json.dump(content, out_file, indent = 2)

        #Returns the final path
        return final_path

    @classmethod
    def open(cls, name: str,
             path: str) -> dict:
        """
        Opens a JSON file
        :param name:
        :param path:
        :return: The JSON data
        """
        #Gets the final path
        final_path = cls._prepare_path_for_open(name, path)

        # Opens the file
        with open(final_path, "r") as in_file:
            # Extracts the data
            data = json.load(in_file)

            #Returns the data
            return data

