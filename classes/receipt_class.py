"""Imports"""
from classes.grocery_item import GroceryItem
from classes.general.date_class import Date
from classes.general.time_class import Time
import json

class Receipt:
    def __init__(self, location:str,
                 date:Date,
                 time:Time|None,
                 subtotal:float,
                 taxes:float,
                 total:float,
                 items:list[GroceryItem],
                 raw_contents:str|None = None,
                 source_file_name:str|None = None):
        self._location = location
        self._date = date
        self._time = time
        self._subtotal = subtotal
        self._taxes = taxes
        self._total = total
        self._items = items
        self._raw_contents = raw_contents
        self._source_file_name = source_file_name

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

    @property
    def source_file_name(self) -> str | None:
        return self._source_file_name

    @property
    def raw_contents(self) -> str:
        if self._raw_contents is not None:
            return self._raw_contents
        items = []
        for item in self.items:
            data = {"name": item.name, "price": item.price, "quantity": item.quantity}
            for field in ("link", "category", "description", "is_essential"):
                value = getattr(item, field)
                if value is not None:
                    data[field] = value
            items.append(data)
        return json.dumps({"general": {"subtotal": self.subtotal, "tax": self.taxes, "total": self.total},
                           "items": items}, indent=2, ensure_ascii=False)

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
