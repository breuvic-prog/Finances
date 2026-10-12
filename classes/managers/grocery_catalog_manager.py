"""Persist grocery product details without calculating shopping or budget totals."""

import csv
from dataclasses import replace
import os
from pathlib import Path
import tempfile

from classes.grocery_catalog_item_class import GroceryCatalogItem
from classes.managers.grocery_units_manager import GroceryUnitsManager


_DEFAULT_GROCERIES_PATH = Path(__file__).resolve().parents[2] / "assets" / "csvs" / "groceries.csv"
_GROCERIES_PATH = _DEFAULT_GROCERIES_PATH
_FIELDS = ("id", "name", "price", "num_items", "link", "unit_id")


class GroceryCatalogManager:
    def __init__(self, path: str | Path | None = None, units_manager: GroceryUnitsManager | None = None):
        self.path = Path(path) if path is not None else _GROCERIES_PATH
        unit_path = None if self.path.resolve() == _DEFAULT_GROCERIES_PATH.resolve() else self.path.with_name("grocery_units.json")
        self.units_manager = units_manager if units_manager is not None else GroceryUnitsManager(unit_path)

    def load(self) -> list[GroceryCatalogItem]:
        if not self.path.exists():
            return []
        try:
            with self.path.open(encoding="utf-8-sig", newline="") as source:
                reader = csv.DictReader(source, strict=True)
                columns = set(reader.fieldnames or ())
                if (len(reader.fieldnames or ()) != len(columns)
                        or not set(_FIELDS).difference({"price", "unit_id"}).issubset(columns) or columns.difference(_FIELDS)):
                    raise ValueError("Invalid grocery-list columns.")
                items = []
                for row in reader:
                    if None in row or any(value is None for value in row.values()):
                        raise ValueError("Invalid saved grocery row.")
                    items.append(GroceryCatalogItem.from_row(row))
            if len({item.item_id for item in items}) != len(items):
                raise ValueError("Saved groceries contain duplicate identifiers.")
            if any(item.unit_id is not None for item in items):
                available = {unit.unit_id for unit in self.units_manager.load()}
                # Deleted labels become unassigned, without altering product details
                # or needing a second file write during a unit deletion.
                items = [replace(item, unit_id=None) if item.unit_id is not None and item.unit_id not in available
                         else item for item in items]
            return items
        except (ValueError, csv.Error) as error:
            raise ValueError(f"Could not read grocery items: {error}") from error

    def save(self, items: list[GroceryCatalogItem]) -> None:
        if any(not isinstance(item, GroceryCatalogItem) for item in items):
            raise ValueError("Provide valid grocery items.")
        if len({item.item_id for item in items}) != len(items):
            raise ValueError("Grocery items must have unique identifiers.")
        if any(item.unit_id is not None for item in items):
            available = {unit.unit_id for unit in self.units_manager.load()}
            if any(item.unit_id is not None and item.unit_id not in available for item in items):
                raise ValueError("Choose an existing grocery unit for each assigned item.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=self.path.parent,
                                             prefix=".groceries-", suffix=".tmp", delete=False) as temporary:
                temporary_path = Path(temporary.name)
                writer = csv.DictWriter(temporary, fieldnames=_FIELDS)
                writer.writeheader()
                writer.writerows(item.to_row() for item in items)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
