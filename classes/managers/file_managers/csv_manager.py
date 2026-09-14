"""Imports"""
import csv
from classes.managers.string_manager import StringManager
from classes.managers.file_manager import FileManager


class CsvManager(FileManager):
    @classmethod
    def open(cls, name: str,
             path: str) -> list[dict]:
        """
        Opens a CSV file
        :param name:
        :param path:
        :return: The CSV data
        """
        #Gets the final path
        final_path = cls._prepare_path_for_open(name, path)

        # Extracts the data
        with open(final_path, "r", newline="", encoding="utf-8") as file:
            # Gets the reader
            reader = csv.DictReader(file)

            # Extracts the info
            data = []

            for row in reader:
                cleaned_row = {}

                for key, value in row.items():
                    # Checks the datatype
                    if StringManager.can_convert_to_bool(value):
                        cleaned_row[key] = bool(value)
                    elif StringManager.can_convert_to_int(value):
                        cleaned_row[key] = int(value)
                    elif StringManager.can_convert_to_float(value):
                        cleaned_row[key] = float(value)
                    else:
                        # Cleans up the value
                        stripped_value = value.strip()

                        if stripped_value != "":  # Valid string
                            cleaned_row[key] = stripped_value
                        else:  # None
                            cleaned_row[key] = None

                data.append(cleaned_row)

            # Returns the info
            return data



