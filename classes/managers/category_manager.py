from pathlib import Path

from classes.managers.enum_manager import EnumManager
from enums.finances import categories_enum
from enums.finances.categories_enum import Categories


_CATEGORIES_ENUM_PATH = Path(categories_enum.__file__).resolve()


class CategoryManager:
    @staticmethod
    def create(name: str) -> Categories:
        """Save a category in the enum source and make it available immediately."""
        return EnumManager.create(name, Categories, _CATEGORIES_ENUM_PATH, "category")
