"""Imports"""
from classes.grocery_class import Grocery
from classes.managers.file_manager import FileManager
from enums.folders_enum import Folders

"""Constants"""
GROCERIES_CSV = "groceries.csv"
ID = "id"
NAME = "name"
PRICE = "price"
NUM_ITEMS = "num_items"
LINK = "link"

"""Functions"""
def _import_data() -> list[dict]:
    return  FileManager.Open_File(file_name = GROCERIES_CSV,
                                  file_path = FileManager.Join_Paths(Folders.ASSETS,
                                                                      Folders.CSVS))
def _import_existing_ids() -> set[int]:
    #Imports the data
    data = _import_data()

    #Extracts the IDs
    existing_ids = set()

    for row in data:
        existing_ids.add(row[ID])

    return existing_ids

class GroceryController:
    def __init__(self):
        self._existing_ids:set[int] = _import_existing_ids()


    """Main Methods"""
    def import_existing_groceries(self) -> list[Grocery]:
        # Creates all the objects
        groceries = []

        for row in _import_data():
            # noinspection PyTypeChecker
            groceries.append(self.create_grocery(grocery_id = row[ID],
                                                 name = row[NAME],
                                                 num_items = row[NUM_ITEMS],
                                                 link = row[LINK]))

        #Closes the web manager
        #self._web_manager.close() TODO

        return groceries
    def create_grocery(self, grocery_id:int|None,
                        name:str,
                        num_items:int,
                        link:str) -> Grocery:

        #ID Handling
        if grocery_id is None:
            #Generates an id
            grocery_id = self._generate_id()

        price = 0

        return Grocery(grocery_id = grocery_id,
                       name = name,
                       num_items = num_items,
                       link = link,
                       price = price)


    """ID Related Methods"""
    def _generate_id(self):
        #Generates the ID
        grocery_id = max(self._existing_ids) + 1

        #Adds ID to list of existing ids
        self._existing_ids.add(grocery_id)

        return grocery_id
