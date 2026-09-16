"""Imports"""

class Date:
    def __init__(self, day:int,
                 month:int,
                 year:int):
        self._day = day
        self._month = month
        self._year = year

    @property
    def day(self):
        return self._day
    @property
    def month(self):
        return self._month
    @property
    def year(self):
        return self._year

    def __lt__(self, other):
        return ((self.year, self.month, self.day)
                < (other.year, other.month, other.day))

    def __le__(self, other):
        return ((self.year, self.month, self.day)
                <= (other.year, other.month, other.day))

    def __gt__(self, other):
        return ((self.year, self.month, self.day)
                > (other.year, other.month, other.day))

    def __ge__(self, other):
        return ((self.year, self.month, self.day)
                >= (other.year, other.month, other.day))

    def __str__(self):
        return f"{self._month}/{self._day}/{self.year}"