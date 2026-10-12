"""Combine planned subcategory expenses into a monthly budget summary."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from classes.managers.income_estimation_manager import IncomeEstimate
from enums.budget.categories_enum import BudgetCategories


@dataclass(frozen=True)
class BudgetExpense:
    category: BudgetCategories
    subcategory: str
    amount: Decimal

    def __post_init__(self):
        if not isinstance(self.category, BudgetCategories) and type(self.category) is not str:
            raise ValueError("Choose a budget planning category.")
        try:
            category = BudgetCategories(self.category)
        except (ValueError, TypeError) as error:
            raise ValueError("Choose a valid budget category.") from error
        if not isinstance(self.subcategory, str) or not self.subcategory.strip():
            raise ValueError("Enter a budget subcategory.")
        try:
            amount = Decimal(str(self.amount).strip())
            if not amount.is_finite() or amount < 0 or amount != amount.quantize(Decimal("0.01")):
                raise ValueError("Planned expenses must be non-negative dollar amounts with at most two decimal places.")
        except InvalidOperation as error:
            raise ValueError("Enter a valid planned expense amount.") from error
        object.__setattr__(self, "category", category)
        object.__setattr__(self, "subcategory", self.subcategory.strip())
        object.__setattr__(self, "amount", amount)


@dataclass(frozen=True)
class CategoryBudgetTotal:
    category: BudgetCategories
    amount: Decimal


@dataclass(frozen=True)
class BudgetSummary:
    month: date
    total_budget: Decimal
    categories: tuple[CategoryBudgetTotal, ...]

    @property
    def total_expenses(self) -> Decimal:
        return sum((category.amount for category in self.categories), Decimal("0.00"))

    @property
    def remaining_budget(self) -> Decimal:
        return self.total_budget - self.total_expenses


class BudgetSummaryManager:
    @staticmethod
    def summarize(income: IncomeEstimate, expenses: Iterable[BudgetExpense],
                  categories: Iterable[BudgetCategories] = BudgetCategories) -> BudgetSummary:
        totals = {}
        for category in categories:
            if not isinstance(category, BudgetCategories):
                raise ValueError("Use budget planning categories for the budget summary.")
            totals[category] = Decimal("0.00")
        for expense in expenses:
            if not isinstance(expense, BudgetExpense):
                raise ValueError("Provide valid planned budget expenses.")
            # Keep expenses counted even if their category was subsequently hidden.
            totals[expense.category] = totals.get(expense.category, Decimal("0.00")) + expense.amount
        return BudgetSummary(income.month, income.take_home,
                             tuple(CategoryBudgetTotal(category, amount) for category, amount in totals.items()))
