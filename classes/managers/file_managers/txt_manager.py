"""Imports"""
from classes.managers.file_manager import FileManager


class TxtManager(FileManager):
    @classmethod
    def create(cls, name: str,
               path: str,
               content:list[str] = None) -> str:
        """
        Creates a txt file
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
                for line in content:
                    out_file.write(line + "\n")

        #Returns the final path
        return final_path

    @classmethod
    def open(cls, name: str,
             path: str) -> list[str]:
        #Gets the final path
        final_path = cls._prepare_path_for_open(name, path)

        # Opens the file
        with open(final_path, "r") as in_file:
            #Extracts the data
            raw_data = in_file.readlines()

            # Cleans up the data
            data = []

            for raw_datum in raw_data:
                clean_datum = raw_datum.strip()
                if clean_datum != "":
                    data.append(clean_datum)

            # Returns the data
            return data

