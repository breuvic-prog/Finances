"""A daily or monthly quantity, or the lifespan of one grocery case."""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from classes.food_consumption_class import FoodConsumption
from classes.grocery_catalog_item_class import GroceryCatalogItem


@dataclass(frozen=True)
class DailyUseItem:
    grocery_item_id: int | None
    quantity: Decimal | None = None
    food_id: str | None = None
    case_days: Decimal | None = None
    monthly_quantity: Decimal | None = None

    def __post_init__(self):
        amounts = {"quantity": self.quantity, "case_days": self.case_days, "monthly_quantity": self.monthly_quantity}
        if sum(amount is not None for amount in amounts.values()) != 1:
            raise ValueError("Enter one quantity per day, quantity per month, or number of days one case lasts.")
        if self.case_days is not None and self.food_id is not None:
            raise ValueError("Case lifespan is available for groceries. Use servings per day or month for prepared foods.")
        field, amount = next((field, amount) for field, amount in amounts.items() if amount is not None)
        try:
            reference = FoodConsumption(self.grocery_item_id, amount, self.food_id)
        except ValueError as error:
            raise ValueError(f"Daily use requires a valid item and a positive quantity or number of days: {error}") from error
        object.__setattr__(self, "grocery_item_id", reference.grocery_item_id)
        object.__setattr__(self, "food_id", reference.food_id)
        object.__setattr__(self, field, reference.quantity)

    @property
    def key(self) -> tuple[str, int | str]:
        return ("food", self.food_id) if self.food_id is not None else ("grocery", self.grocery_item_id)

    def daily_consumption(self, grocery: GroceryCatalogItem | None = None, month: date | None = None) -> FoodConsumption:
        quantity = self.quantity
        if self.case_days is not None:
            if grocery is None or grocery.item_id != self.grocery_item_id:
                raise ValueError("This grocery is unavailable. Replace it to calculate daily use from its case size.")
            quantity = Decimal(grocery.units_per_case) / self.case_days
        elif self.monthly_quantity is not None:
            if not isinstance(month, date):
                raise ValueError("Choose a budget month to calculate the daily equivalent of monthly use.")
            quantity = self.monthly_quantity / Decimal(monthrange(month.year, month.month)[1])
        return FoodConsumption(self.grocery_item_id, quantity, self.food_id)

    def to_dict(self) -> dict:
        record = {"food_id": self.food_id} if self.food_id is not None else {"grocery_item_id": self.grocery_item_id}
        if self.case_days is not None:
            record["case_days"] = str(self.case_days)
        elif self.monthly_quantity is not None:
            record["monthly_quantity"] = str(self.monthly_quantity)
        else:
            record["quantity"] = str(self.quantity)
        return record

    @classmethod
    def from_dict(cls, record):
        if not isinstance(record, dict):
            raise ValueError("Invalid saved daily-use item.")
        return cls(record.get("grocery_item_id"), record.get("quantity"), record.get("food_id"),
                   record.get("case_days"), record.get("monthly_quantity"))


def validate_daily_use(items) -> tuple[DailyUseItem, ...]:
    try:
        items = tuple(items)
    except TypeError as error:
        raise ValueError("Provide a list of daily-use items.") from error
    if any(not isinstance(item, DailyUseItem) for item in items):
        raise ValueError("Provide valid daily-use items.")
    if len({item.key for item in items}) != len(items):
        raise ValueError("This item is already in Daily Use. Edit its quantity instead.")
    return items
