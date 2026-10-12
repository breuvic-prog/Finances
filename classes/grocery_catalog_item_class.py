"""Details of a saved grocery product, separate from purchased receipt items."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit


@dataclass(frozen=True)
class GroceryCatalogItem:
    item_id: int
    name: str
    price: Decimal
    units_per_case: int = 1
    link: str = ""
    unit_id: str | None = None

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Enter an item name.")
        try:
            item_id = Decimal(str(self.item_id))
            units = Decimal(str(self.units_per_case))
            price = Decimal(str(self.price).strip())
            if not item_id.is_finite() or item_id < 1 or item_id != item_id.to_integral_value():
                raise ValueError("The item must have a positive whole-number identifier.")
            if not units.is_finite() or units < 1 or units != units.to_integral_value():
                raise ValueError("Units per case must be a positive whole number.")
            if not price.is_finite() or price < 0 or price != price.quantize(Decimal("0.01")):
                raise ValueError("Price must be non-negative and have at most two decimal places.")
        except InvalidOperation as error:
            raise ValueError("Enter a valid price and whole-number units per case.") from error
        if self.link is not None and not isinstance(self.link, str):
            raise ValueError("Enter a valid product link or leave it blank.")
        link = (self.link or "").strip()
        if link:
            try:
                url = urlsplit(link)
                valid = url.scheme.lower() in ("http", "https") and bool(url.hostname)
            except ValueError:
                valid = False
            if not valid or any(character.isspace() for character in link):
                raise ValueError("Product links must start with http:// or https://, or be left blank.")
        if self.unit_id is not None and not isinstance(self.unit_id, str):
            raise ValueError("Choose a valid grocery unit.")
        object.__setattr__(self, "item_id", int(item_id))
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "price", price)
        object.__setattr__(self, "units_per_case", int(units))
        object.__setattr__(self, "link", link)
        object.__setattr__(self, "unit_id", self.unit_id.strip() or None if self.unit_id is not None else None)

    def to_row(self) -> dict:
        return {"id": self.item_id, "name": self.name, "price": str(self.price),
                "num_items": self.units_per_case, "link": self.link, "unit_id": self.unit_id or ""}

    @classmethod
    def from_row(cls, row: dict):
        try:
            return cls(row["id"], row["name"], row.get("price", "0"), row["num_items"], row["link"], row.get("unit_id"))
        except (KeyError, TypeError) as error:
            raise ValueError("Invalid saved grocery item.") from error
