"""Exchange grocery prices with an external CSV without editing product details."""

import csv
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

from classes.grocery_catalog_item_class import GroceryCatalogItem
from classes.managers.grocery_catalog_manager import GroceryCatalogManager


_FIELDS = ("id", "name", "num_items", "unit_id", "unit", "link", "current_price", "updated_price")

PRICE_CHECK_INSTRUCTIONS = """Open groceries.csv in the attached ZIP and check its current grocery prices using web browsing.
For every row, use the product link when provided. Otherwise search for the exact
product and case size described by name, num_items, and unit. Prices must be USD
for the entire case/package, not for one unit. Match the exact size and variant.
Use a publicly available regular purchase price, before tax, without delivery
fees, coupons, subscriptions, or membership discounts. If you cannot verify a
current price or identify the exact product, leave updated_price blank. Do not
guess, and do not use zero to mean unavailable.

Exception for Gamer Supps (also written GamerSupps): updated_price MUST include
the product price PLUS its standard shipping cost, before tax. Check the cost of
ordering that case/package on its own from the linked seller. Only use zero
shipping if free shipping is verified for that purchase. If shipping depends on
the delivery destination, ask the user for the necessary destination details.
If the shipping cost cannot be verified, leave updated_price blank rather than
returning a price without shipping. The general rule excluding delivery fees
does not apply to Gamer Supps.

Return a downloadable UTF-8 CSV with exactly the original columns and all rows.
Only fill updated_price with a non-negative number with at most two decimal
places (for example 12.99). Keep id, name, num_items, unit_id, unit, link, and
current_price unchanged. Do not add currency symbols or thousands separators.
Include a brief explanation with source links and the date checked in your
message, separate from the CSV. Do not calculate grocery or budget totals."""


@dataclass(frozen=True)
class GroceryPriceUpdate:
    item: GroceryCatalogItem
    price: Decimal


class GroceryPriceUpdatesManager:
    def __init__(self, catalog_manager: GroceryCatalogManager):
        self.catalog = catalog_manager

    def export_csv(self, path: str | Path) -> int:
        destination = Path(path)
        if destination.resolve() in (self.catalog.path.resolve(), self.catalog.units_manager.path.resolve()):
            raise ValueError("Export to a separate file, outside the saved grocery catalogue.")
        items = self.catalog.load()
        units = {unit.unit_id: unit for unit in self.catalog.units_manager.load()}
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8-sig", newline="", dir=destination.parent,
                                             prefix=".grocery-prices-", suffix=".tmp", delete=False) as temporary:
                temporary_path = Path(temporary.name)
                writer = csv.DictWriter(temporary, fieldnames=_FIELDS)
                writer.writeheader()
                for item in items:
                    unit = units.get(item.unit_id)
                    writer.writerow({"id": item.item_id, "name": item.name, "num_items": item.units_per_case,
                                     "unit_id": item.unit_id or "", "unit": unit.for_count(item.units_per_case) if unit else "",
                                     "link": item.link, "current_price": f"{item.price:.2f}", "updated_price": ""})
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, destination)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return len(items)

    def download_package(self, downloads_path: str | Path) -> Path:
        downloads = Path(downloads_path)
        downloads.mkdir(parents=True, exist_ok=True)
        destination = downloads / "instructions.zip"
        # Build separately so a failed regeneration retains the previous download.
        with tempfile.TemporaryDirectory(prefix="grocery-price-check-", dir=downloads) as directory:
            workspace = Path(directory)
            csv_path = workspace / "groceries.csv"
            self.export_csv(csv_path)
            instructions = workspace / "instructions.txt"
            instructions.write_text(PRICE_CHECK_INSTRUCTIONS, encoding="utf-8", newline="\n")
            archive_path = workspace / destination.name
            with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
                archive.write(instructions, instructions.name)
                archive.write(csv_path, csv_path.name)
            os.replace(archive_path, destination)
        return destination

    def read_updates(self, path: str | Path) -> tuple[GroceryPriceUpdate, ...]:
        items = {item.item_id: item for item in self.catalog.load()}
        updates = []
        seen = set()
        try:
            with Path(path).open(encoding="utf-8-sig", newline="") as source:
                reader = csv.DictReader(source, strict=True)
                if len(reader.fieldnames or ()) != len(_FIELDS) or set(reader.fieldnames or ()) != set(_FIELDS):
                    raise ValueError("Use the exported price CSV with its original columns.")
                for line, row in enumerate(reader, start=2):
                    try:
                        if None in row or any(value is None for value in row.values()):
                            raise ValueError("Missing or extra CSV fields.")
                        identifier = row["id"].strip()
                        if not identifier.isascii() or not identifier.isdigit():
                            raise ValueError("Invalid item ID.")
                        item_id = int(identifier)
                        if item_id in seen:
                            raise ValueError("Duplicate item ID.")
                        seen.add(item_id)
                        if item_id not in items:
                            raise ValueError("Item no longer exists. Export a fresh CSV.")
                        item = items[item_id]
                        if (row["name"] != item.name or row["num_items"] != str(item.units_per_case)
                                or row["unit_id"] != (item.unit_id or "") or row["link"] != item.link
                                or Decimal(row["current_price"]) != item.price):
                            raise ValueError("Product details or the saved price changed. Export a fresh CSV.")
                        if row["updated_price"].strip():
                            # Reuse catalogue validation for finite, non-negative prices and cent precision.
                            updated = replace(item, price=row["updated_price"].strip())
                            if updated.price != item.price:
                                updates.append(GroceryPriceUpdate(item, updated.price))
                    except (ValueError, InvalidOperation) as error:
                        raise ValueError(f"Row {line}: {error}") from error
        except (csv.Error, UnicodeError) as error:
            raise ValueError(f"Could not read the price CSV: {error}") from error
        return tuple(updates)

    def apply_updates(self, updates: tuple[GroceryPriceUpdate, ...]) -> int:
        if any(not isinstance(update, GroceryPriceUpdate) for update in updates):
            raise ValueError("Provide valid grocery price updates.")
        by_id = {update.item.item_id: update for update in updates}
        if len(by_id) != len(updates):
            raise ValueError("Duplicate price updates.")
        items = self.catalog.load()
        current = {item.item_id: item for item in items}
        if any(current.get(item_id) != update.item for item_id, update in by_id.items()):
            raise ValueError("Groceries changed after importing. Export a fresh CSV and check the prices again.")
        updated_items = [replace(item, price=by_id[item.item_id].price) if item.item_id in by_id else item
                         for item in items]
        if updates:
            self.catalog.save(updated_items)
        return len(updates)
