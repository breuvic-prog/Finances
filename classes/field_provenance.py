from enums.finances.categories_enum import Categories
from enums.finances.descriptions.discretionary_spending_descriptions_enum import DiscretionarySpendingDescriptions
from enums.finances.is_essential_enum import IsEssential


class FieldProvenance:
    """Keep automatic values locked while preserving the user's own choices."""

    def _initialize_field_origins(self, values: dict) -> None:
        self._field_origins = {field: "initial" for field, value in values.items() if value is not None}

    def is_field_locked(self, field: str) -> bool:
        return self._field_origins.get(field) in ("initial", "automatic", "category")

    def _set_field(self, field: str, value, origin: str = "user") -> None:
        setattr(self, f"_{field}", value)
        # Copies used by receipt drafts must not share mutable provenance.
        self._field_origins = {name: source for name, source in self._field_origins.items() if name != field}
        if value is not None:
            self._field_origins[field] = origin

    def autocomplete_field(self, field: str, value) -> None:
        setattr(self, field, value)
        if value is not None:
            self._field_origins = {**self._field_origins, field: "automatic"}

    def copy_fields_from(self, other, fields: tuple[str, ...]) -> None:
        for field in fields:
            self._set_field(field, getattr(other, field), other._field_origins.get(field, "user"))

    def _apply_category_defaults(self, previous_category) -> None:
        if previous_category in (Categories.DISCRETIONARY_SPENDING, Categories.INCOME) and previous_category != self._category:
            for field in ("description", "is_essential"):
                if self._field_origins.get(field) == "category":
                    self._set_field(field, None)
        if self._category == Categories.DISCRETIONARY_SPENDING:
            self._set_field("description", DiscretionarySpendingDescriptions.DISCRETIONARY_SPENDING, "category")
            if self._is_essential != IsEssential.NOT_INCLUDED:
                self._set_field("is_essential", IsEssential.NON_ESSENTIAL, "category")
        elif self._category == Categories.INCOME:
            if self._is_essential != IsEssential.NOT_INCLUDED:
                self._set_field("is_essential", IsEssential.ESSENTIAL, "category")
