"""Imports"""
from enum import StrEnum

class Categories(StrEnum):
    CAR = "Car"
    HOUSING = "Housing"
    SUBSCRIPTIONS = "Subscriptions"
    SHOPPING = "Shopping"
    STUDENT_LOANS = "Student Loans"
    INCOME = "Income"
    CREDIT_CARD = "Credit Card"
    DISCRETIONARY_SPENDING = "Discretionary Spending"

    @classmethod
    def _missing_(cls, value):
        # Receipts saved before the rename still load into the same category.
        if isinstance(value, str):
            return {"groceries": cls.SHOPPING, "paycheck": cls.INCOME}.get(value.strip().casefold())
        return None
    BANK = 'Bank'
    SUBSTITUTE_TEACHING = 'Substitute Teaching'


