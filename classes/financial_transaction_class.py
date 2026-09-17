"""Imports"""
from classes.general.date_class import Date
from classes.general.dollar_amount_class import DollarAmount
from enums.finances.categories_enum import Categories
from enums.finances.descriptions_enum import Descriptions
from enums.finances.is_essential_enum import IsEssential
from enums.locations_enum import Locations


class FinancialTransaction:
    def __init__(self, date:Date,
                 amount: DollarAmount,
                 location:Locations|None = None,
                 description:Descriptions|None = None,
                 category:Categories|None = None,
                 is_essential:IsEssential|None = None):
        self._date = date
        self._location = location
        self._amount = amount
        self._description = description
        self._category = category
        self._is_essential = is_essential

    """Getters"""
    @property
    def date(self):
        return self._date
    @property
    def location(self):
        return self._location
    @property
    def description(self):
        return self._description
    @property
    def amount(self):
        return self._amount
    @property
    def category(self):
        return self._category
    @property
    def is_essential(self):
        return self._is_essential

    """Setters"""
    @location.setter
    def location(self, location:Locations):
        self._location = location
    @description.setter
    def description(self, description:Descriptions):
        self._description = description
    @category.setter
    def category(self, category:Categories):
        self._category = category
    @is_essential.setter
    def is_essential(self, is_essential:bool):
        self._is_essential = is_essential

    def __str__(self):
        return_string = "----Financial Transaction----\n"
        return_string += f"Location: {self._location}\n"
        return_string += f"Description: {self._description}\n"
        return_string += f"Date: {self.date}\n"
        return_string += f"Amount: ${self.amount}\n"

        return return_string