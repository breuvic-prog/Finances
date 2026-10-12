"""Imports"""
from enum import StrEnum

from classes.field_provenance import FieldProvenance
from classes.general.date_class import Date
from classes.general.dollar_amount_class import DollarAmount
from classes.receipt_class import Receipt
from enums.finances.categories_enum import Categories
from enums.finances.is_essential_enum import IsEssential
from enums.finances.locations_enum import Locations


class FinancialTransaction(FieldProvenance):
    def __init__(self, date:Date,
                 amount: DollarAmount,
                 location:Locations|None = None,
                 description:StrEnum|str|None = None,
                 category:Categories|None = None,
                 is_essential:IsEssential|None = None,
                 receipt:Receipt|None = None,
                 purchase_title:str|None = None,
                 description_is_autocompleted:bool = False,
                 source:Locations|None = None,
                 excluded_from_totals:bool = False,
                 hidden:bool = False):
        self._date = date
        self._location = location
        self._amount = amount
        self._description = description
        self._category = None
        self._is_essential = is_essential
        self._receipt = receipt
        self._purchase_title = purchase_title
        self._source = source
        self._excluded_from_totals = excluded_from_totals
        self._hidden = hidden
        self._initialize_field_origins({"location": location, "description": description,
                                        "category": category, "is_essential": is_essential})
        self.category = category
        if category is not None:
            self._field_origins = {**self._field_origins, "category": "initial"}
        if description_is_autocompleted and self.description is not None:
            self._field_origins = {**self._field_origins, "description": "automatic"}

    """Getters"""
    @property
    def date(self):
        return self._date
    @property
    def location(self):
        return self._location
    @property
    def source(self) -> Locations | None:
        return self._source
    @property
    def excluded_from_totals(self) -> bool:
        return self._excluded_from_totals
    @property
    def hidden(self) -> bool:
        return self._hidden
    @property
    def description(self):
        return self._description
    @property
    def purchase_title(self) -> str | None:
        return self._purchase_title
    @property
    def description_is_autocompleted(self) -> bool:
        return self.is_field_locked("description")
    @property
    def amount(self):
        return self._amount
    @property
    def category(self):
        return self._category
    @property
    def is_essential(self):
        return self._is_essential
    @property
    def is_essential_is_autocompleted(self) -> bool:
        return self.is_field_locked("is_essential")
    @property
    def receipt(self) -> Receipt | None:
        return self._receipt

    """Setters"""
    @location.setter
    def location(self, location:Locations):
        self._set_field("location", location)
        if location == Locations.DISCOVER and not (
            self.category == Categories.INCOME and self.is_field_locked("category")
        ):
            self.autocomplete_field("category", Categories.CREDIT_CARD)
    @description.setter
    def description(self, description:StrEnum|str|None):
        self._set_field("description", description)
    @category.setter
    def category(self, category:Categories|None):
        previous_category = self._category
        if category != Categories.INCOME and self.location == Locations.DISCOVER:
            self._set_field("category", Categories.CREDIT_CARD, "automatic")
        else:
            self._set_field("category", category)
        self._apply_category_defaults(previous_category)
    @is_essential.setter
    def is_essential(self, is_essential:IsEssential|None):
        if self.category == Categories.INCOME and is_essential != IsEssential.NOT_INCLUDED:
            self._set_field("is_essential", IsEssential.ESSENTIAL, "category")
        elif self.category == Categories.DISCRETIONARY_SPENDING and is_essential != IsEssential.NOT_INCLUDED:
            self._set_field("is_essential", IsEssential.NON_ESSENTIAL, "category")
        else:
            self._set_field("is_essential", is_essential)
    @receipt.setter
    def receipt(self, receipt:Receipt|None) -> None:
        self._receipt = receipt

    @excluded_from_totals.setter
    def excluded_from_totals(self, excluded: bool) -> None:
        self._excluded_from_totals = excluded

    @hidden.setter
    def hidden(self, hidden: bool) -> None:
        self._hidden = bool(hidden)

    def autocomplete_description(self, description: StrEnum) -> None:
        self.autocomplete_field("description", description)

    def __str__(self):
        return_string = "----Financial Transaction----\n"
        return_string += f"Location: {self._location}\n"
        return_string += f"Source: {self._source}\n"
        return_string += f"Description: {self._description}\n"
        return_string += f"Date: {self.date}\n"
        return_string += f"Amount: ${self.amount}\n"

        return return_string
