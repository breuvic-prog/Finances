import importlib.util
import re
import unicodedata
from enum import StrEnum
from pathlib import Path

from classes.managers.enum_manager import EnumManager
from classes.managers.option_manager import OptionManager
from enums.finances import descriptions_enum
from enums.finances.descriptions_enum import Descriptions
from enums.finances.categories_enum import Categories
from enums.finances.descriptions.car_descriptions_enum import CarDescriptions
from enums.finances.descriptions.grocery_descriptions_enum import GroceryDescriptions
from enums.finances.descriptions.housing_descriptions_enum import HousingDescriptions
from enums.finances.descriptions.subscription_descriptions_enum import SubscriptionDescriptions
from enums.finances.descriptions.student_loan_descriptions_enum import StudentLoanDescriptions
from enums.finances.descriptions.income_descriptions_enum import IncomeDescriptions
from enums.finances.descriptions.credit_card_descriptions_enum import CreditCardDescriptions
from enums.finances.descriptions.discretionary_spending_descriptions_enum import DiscretionarySpendingDescriptions


_DESCRIPTIONS_ENUM_PATH = Path(descriptions_enum.__file__).resolve()
_CATEGORY_ENUM_DIRECTORY = _DESCRIPTIONS_ENUM_PATH.parent / "descriptions"
_CATEGORY_DESCRIPTION_SOURCES = {
    Categories.CAR: (CarDescriptions, _CATEGORY_ENUM_DIRECTORY / "car_descriptions_enum.py"),
    Categories.SHOPPING: (GroceryDescriptions, _CATEGORY_ENUM_DIRECTORY / "grocery_descriptions_enum.py"),
    Categories.HOUSING: (HousingDescriptions, _CATEGORY_ENUM_DIRECTORY / "housing_descriptions_enum.py"),
    Categories.SUBSCRIPTIONS: (SubscriptionDescriptions, _CATEGORY_ENUM_DIRECTORY / "subscription_descriptions_enum.py"),
    Categories.STUDENT_LOANS: (StudentLoanDescriptions, _CATEGORY_ENUM_DIRECTORY / "student_loan_descriptions_enum.py"),
    Categories.INCOME: (IncomeDescriptions, _CATEGORY_ENUM_DIRECTORY / "income_descriptions_enum.py"),
    Categories.CREDIT_CARD: (CreditCardDescriptions, _CATEGORY_ENUM_DIRECTORY / "credit_card_descriptions_enum.py"),
    Categories.DISCRETIONARY_SPENDING: (
        DiscretionarySpendingDescriptions, _CATEGORY_ENUM_DIRECTORY / "discretionary_spending_descriptions_enum.py"
    ),
}


def _category_source(category: Categories, create: bool = False) -> tuple[type[StrEnum], Path] | None:
    source = _CATEGORY_DESCRIPTION_SOURCES.get(category)
    if source is not None:
        return source
    # Newly added categories also get a separate, persistent description enum.
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", category.name):
        raise ValueError("Invalid category identifier.")
    path = _CATEGORY_ENUM_DIRECTORY / f"custom_{category.name.lower()}_descriptions_enum.py"
    class_name = "".join(part.title() for part in category.name.split("_")) + "Descriptions"
    if not path.exists():
        if not create:
            return None
        path.write_text(f"from enum import StrEnum\n\n\nclass {class_name}(StrEnum):\n    pass\n",
                        encoding="utf-8")
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = (getattr(module, class_name), path)
    _CATEGORY_DESCRIPTION_SOURCES[category] = source
    return source


class DescriptionManager:
    @staticmethod
    def choices(category: Categories | None = None, include_hidden: bool = False) -> list[StrEnum]:
        """Combine general descriptions with those for the selected category."""
        values = list(Descriptions)
        categories = [category] if category is not None else []
        for candidate in categories:
            source = _category_source(candidate)
            if source is not None:
                values.extend(source[0])
        if include_hidden:
            return values
        unique_values = {}
        for member in OptionManager.available(values):
            unique_values.setdefault(OptionManager.display(member), member)
        return list(unique_values.values())

    @staticmethod
    def is_available(description: StrEnum | str, category: Categories | None) -> bool:
        return any(member.value == str(description) for member in DescriptionManager.choices(category))

    @staticmethod
    def display(description: StrEnum | str | None, category: Categories | None = None) -> str:
        if description is None:
            return ""
        member = OptionManager.resolve(DescriptionManager.choices(category, include_hidden=True), str(description))
        return OptionManager.display(member if member is not None else description)

    @staticmethod
    def create(name: str, category: Categories | None = None) -> StrEnum:
        """Save additions in the selected category, or in the general enum."""
        normalized_name = " ".join(name.split())
        if normalized_name.casefold() == "not included":
            raise ValueError('Select "Not Included" in Is Essential instead.')
        for member in DescriptionManager.choices(category, include_hidden=True):
            if normalized_name.casefold() in (member.value.casefold(), OptionManager.display(member).casefold()):
                return OptionManager.restore(member)
        identifier_text = unicodedata.normalize("NFKD", normalized_name).encode("ascii", "ignore").decode("ascii")
        if not re.search(r"[A-Za-z0-9]", identifier_text):
            raise ValueError("The description name must contain a letter or number.")
        enum_type, path = ((Descriptions, _DESCRIPTIONS_ENUM_PATH) if category is None
                           else _category_source(category, create=True))
        return EnumManager.create(name, enum_type, path, "description")
