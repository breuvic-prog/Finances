"""A named food containing grocery quantities for one serving."""

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from classes.food_consumption_class import FoodConsumption, validate_food_plan


@dataclass(frozen=True)
class PreparedFood:
    name: str
    ingredients: tuple[FoodConsumption, ...]
    food_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Enter a food name.")
        ingredients = validate_food_plan(self.ingredients)
        if not ingredients:
            raise ValueError("Add at least one grocery ingredient to the food.")
        if any(ingredient.food_id is not None for ingredient in ingredients):
            raise ValueError("Food ingredients must come from the grocery list.")
        try:
            identifier = str(UUID(self.food_id))
        except (ValueError, TypeError, AttributeError) as error:
            raise ValueError("Invalid food identifier.") from error
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "ingredients", ingredients)
        object.__setattr__(self, "food_id", identifier)

    def to_dict(self) -> dict:
        return {"food_id": self.food_id, "name": self.name,
                "ingredients": [ingredient.to_dict() for ingredient in self.ingredients]}

    @classmethod
    def from_dict(cls, record):
        if not isinstance(record, dict):
            raise ValueError("Invalid saved food.")
        try:
            if not isinstance(record["ingredients"], list):
                raise ValueError("Invalid saved food ingredients.")
            return cls(record["name"], tuple(FoodConsumption.from_dict(item) for item in record["ingredients"]), record["food_id"])
        except KeyError as error:
            raise ValueError("Invalid saved food.") from error
