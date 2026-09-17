"""Imports"""


class DollarAmount(float):
    def __new__(cls, value: float = 0.0):
        return super().__new__(cls, value)

    def __str__(self):
        if self >= 0:
            return f"${self:.2f}"
        else:
            return f"-${-self:.2f}"