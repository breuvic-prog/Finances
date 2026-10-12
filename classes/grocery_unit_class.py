"""A reusable grocery quantity label with an identity preserved through renames."""

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import uuid4


@dataclass(frozen=True)
class GroceryUnit:
    name: str
    unit_id: str = field(default_factory=lambda: uuid4().hex)
    plural: str = ""

    def __post_init__(self):
        if not isinstance(self.name, str) or not any(character.isalnum() for character in self.name):
            raise ValueError("Enter a singular unit name, for example Can.")
        name = " ".join(self.name.split())
        if name.casefold() == "no unit":
            raise ValueError('Choose a different name. "No unit" means no unit is assigned.')
        if not isinstance(self.unit_id, str) or not self.unit_id.strip():
            raise ValueError("The unit must have an identifier.")
        if not isinstance(self.plural, str):
            raise ValueError("Enter a plural unit name.")
        plural = " ".join(self.plural.split())
        plural = plural or name + "s"
        if not any(character.isalnum() for character in plural) or plural.casefold() == "no unit":
            raise ValueError("Enter a valid plural unit name.")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "unit_id", self.unit_id.strip())
        object.__setattr__(self, "plural", plural)

    @property
    def singular(self) -> str:
        return self.name

    def for_count(self, count: int | Decimal) -> str:
        return self.name if count == 1 else self.plural

    def to_dict(self) -> dict:
        return {"id": self.unit_id, "name": self.name, "plural": self.plural}

    @classmethod
    def from_dict(cls, record: dict):
        if not isinstance(record, dict):
            raise ValueError("Invalid saved grocery unit.")
        try:
            return cls(record["name"], record["id"], record.get("plural", ""))
        except KeyError as error:
            raise ValueError("Invalid saved grocery unit.") from error
