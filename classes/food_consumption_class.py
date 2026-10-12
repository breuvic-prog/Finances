"""A grocery or prepared-food quantity consumed during a shift or day off."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from uuid import UUID


@dataclass(frozen=True)
class FoodConsumption:
    grocery_item_id: int | None
    quantity: Decimal
    food_id: str | None = None

    def __post_init__(self):
        try:
            quantity = Decimal(str(self.quantity).strip())
        except InvalidOperation as error:
            raise ValueError("Choose a grocery item and enter a valid quantity.") from error
        if self.food_id is not None:
            if self.grocery_item_id is not None:
                raise ValueError("Choose either a grocery or a prepared food.")
            try:
                identifier = str(UUID(self.food_id))
            except (ValueError, TypeError, AttributeError) as error:
                raise ValueError("Choose a valid prepared food.") from error
            object.__setattr__(self, "food_id", identifier)
        else:
            try:
                identifier = Decimal(str(self.grocery_item_id).strip())
            except InvalidOperation as error:
                raise ValueError("Choose a valid grocery item.") from error
            if not identifier.is_finite() or identifier < 1 or identifier != identifier.to_integral_value():
                raise ValueError("Choose a valid grocery item.")
            object.__setattr__(self, "grocery_item_id", int(identifier))
        if not quantity.is_finite() or quantity <= 0:
            raise ValueError("Food quantity must be a positive number.")
        object.__setattr__(self, "quantity", quantity)

    @property
    def key(self) -> tuple[str, int | str]:
        return ("food", self.food_id) if self.food_id is not None else ("grocery", self.grocery_item_id)

    def to_dict(self) -> dict:
        if self.food_id is not None:
            return {"food_id": self.food_id, "quantity": str(self.quantity)}
        return {"grocery_item_id": self.grocery_item_id, "quantity": str(self.quantity)}

    @classmethod
    def from_dict(cls, record: dict):
        if not isinstance(record, dict):
            raise ValueError("Invalid saved food consumption.")
        try:
            return cls(record.get("grocery_item_id"), record["quantity"], record.get("food_id"))
        except KeyError as error:
            raise ValueError("Invalid saved food consumption.") from error


def validate_food_plan(foods) -> tuple[FoodConsumption, ...]:
    try:
        foods = tuple(foods)
    except TypeError as error:
        raise ValueError("Provide a list of food quantities.") from error
    if any(not isinstance(food, FoodConsumption) for food in foods):
        raise ValueError("Provide valid food quantities.")
    if len({food.key for food in foods}) != len(foods):
        raise ValueError("This food is already in the plan. Edit its quantity instead.")
    return foods
