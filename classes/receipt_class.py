"""Imports"""
from classes.grocery_item import GroceryItem
from classes.general.date_class import Date
from classes.general.time_class import Time

class Receipt:
    def __init__(self, location:str,
                 date:Date,
                 time:Time|None,
                 subtotal:float,
                 taxes:float,
                 total:float,
                 items:list[GroceryItem]):
        self._location = location
        self._date = date
        self._time = time
        self._subtotal = subtotal
        self._taxes = taxes
        self._total = total
        self._items = items

    @property
    def location(self):
        return self._location
    @property
    def date(self):
        return self._date

    @property
    def time(self):
        return self._time
    @property
    def subtotal(self):
        return self._subtotal
    @property
    def taxes(self):
        return self._taxes
    @property
    def total(self):
        return self._total
    @property
    def items(self):
        return self._items

    def __str__(self):
        return_string = "----Receipt----\n"
        return_string += f"Location: {self._location}\n"
        return_string += f"Date: {self._date}\n"
        if self._time:
            return_string += f"Time: {self._time}\n"
        return_string += f"Subtotal: ${self._subtotal}\n"
        return_string += f"Taxes: ${self._taxes}\n"
        return_string += f"Total: ${self._total}\n"
        return_string += f"Items: \n"
        for item in self._items:
            return_string += str(item) + "\n"

        return return_string