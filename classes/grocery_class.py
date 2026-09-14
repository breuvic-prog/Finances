"""Imports"""


class Grocery:
    def __init__(self, grocery_id:int,
                 name:str,
                 price:float,
                 num_items:float,
                 link:str):
        #Attributes
        self._grocery_id = grocery_id
        self._name = name
        self._price = price
        self._num_items = num_items#This should be manually set
        self._link = link

    """Getters"""
    @property
    def grocery_id(self):
        return self._grocery_id
    @property
    def name(self):
        return self._name
    @property
    def price(self):
        return self._price
    @property
    def num_items(self):
        return self._num_items
    @property
    def link(self):
        return self._link

    def __str__(self):
        return_string = "----Grocery Item----\n"
        return_string += f"ID: {self._grocery_id}\n"
        return_string += f"Name: {self._name}\n"
        return_string += f"Price: ${self._price}\n"
        return_string += f"Number of items: {self.num_items}\n"
        return_string += f"Link: {self._link}\n"

        return return_string
