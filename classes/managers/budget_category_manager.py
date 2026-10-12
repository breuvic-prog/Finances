"""Manage budget categories using their own enum and option-preference identities."""

from pathlib import Path

from classes.managers.enum_manager import EnumManager
from classes.managers.option_manager import OptionManager
from enums.budget import categories_enum
from enums.budget.categories_enum import BudgetCategories


_BUDGET_CATEGORIES_ENUM_PATH = Path(categories_enum.__file__).resolve()


class BudgetCategoryManager:
    @staticmethod
    def choices() -> list[BudgetCategories]:
        return OptionManager.available(BudgetCategories)

    @staticmethod
    def create(name: str) -> BudgetCategories:
        return EnumManager.create(name, BudgetCategories, _BUDGET_CATEGORIES_ENUM_PATH, "category")

    @staticmethod
    def colors(category: BudgetCategories) -> tuple[str, str]:
        if not isinstance(category, BudgetCategories):
            raise ValueError("Choose a budget planning category.")
        return OptionManager.colors(category)
