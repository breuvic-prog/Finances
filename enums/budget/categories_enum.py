"""Starter budget categories, maintained separately from expense-review categories."""

from enum import StrEnum


class BudgetCategories(StrEnum):
    CAR = "Car"
    HOUSING = "Housing"
    SUBSCRIPTIONS = "Subscriptions"
    SHOPPING = "Shopping"
    STUDENT_LOANS = "Student Loans"
    DISCRETIONARY_SPENDING = "Discretionary Spending"
