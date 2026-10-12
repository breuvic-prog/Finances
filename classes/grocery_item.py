from enum import StrEnum

from classes.field_provenance import FieldProvenance
from enums.finances.categories_enum import Categories
from enums.finances.is_essential_enum import IsEssential


class GroceryItem(FieldProvenance):
    def __init__(self, name:str,
                 price:float,
                 link:str|None = None,
                 quantity:int|float = 1,
                 category:Categories|None = None,
                 is_essential:IsEssential|None = None,
                 description:StrEnum|str|None = None):
        self._name = name
        self._price = price
        self._link = link
        self._quantity = quantity
        self._category = None
        self._is_essential = is_essential
        self._description = description
        self._initialize_field_origins({"category": category, "description": description,
                                        "is_essential": is_essential})
        self.category = category
        if category is not None:
            self._field_origins = {**self._field_origins, "category": "initial"}


    @property
    def name(self):
        return self._name
    @property
    def price(self):
        return self._price
    @property
    def link(self):
        return self._link

    @property
    def quantity(self) -> int | float:
        return self._quantity

    @property
    def cost(self) -> float:
        return self._price * self._quantity

    @property
    def category(self) -> Categories | None:
        return self._category

    @category.setter
    def category(self, category: Categories | None) -> None:
        previous_category = self._category
        self._set_field("category", category)
        self._apply_category_defaults(previous_category)

    @property
    def is_essential(self) -> IsEssential | None:
        return self._is_essential

    @property
    def is_essential_is_autocompleted(self) -> bool:
        return self.is_field_locked("is_essential")

    @is_essential.setter
    def is_essential(self, is_essential: IsEssential | None) -> None:
        if self.category == Categories.INCOME and is_essential != IsEssential.NOT_INCLUDED:
            self._set_field("is_essential", IsEssential.ESSENTIAL, "category")
        elif self.category == Categories.DISCRETIONARY_SPENDING and is_essential != IsEssential.NOT_INCLUDED:
            self._set_field("is_essential", IsEssential.NON_ESSENTIAL, "category")
        else:
            self._set_field("is_essential", is_essential)

    @property
    def description(self) -> StrEnum | str | None:
        return self._description

    @property
    def description_is_autocompleted(self) -> bool:
        return self.is_field_locked("description")

    @description.setter
    def description(self, description: StrEnum | str | None) -> None:
        self._set_field("description", description)

    def __str__(self):
        return_string = "----Grocery Item----\n"
        return_string += f"Name: {self._name}\n"
        return_string += f"Price: ${self._price}\n"
        if self._link:
            return_string += f"Link: {self._link}\n"


        return return_string
