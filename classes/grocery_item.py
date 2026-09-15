


class GroceryItem:
    def __init__(self, name:str,
                 price:float,
                 link:str|None = None):
        self._name = name
        self._price = price
        self._link = link


    @property
    def name(self):
        return self._name
    @property
    def price(self):
        return self._price
    @property
    def link(self):
        return self._link

    def __str__(self):
        return_string = "----Grocery Item----\n"
        return_string += f"Name: {self._name}\n"
        return_string += f"Price: ${self._price}\n"
        if self._link:
            return_string += f"Link: {self._link}\n"


        return return_string
