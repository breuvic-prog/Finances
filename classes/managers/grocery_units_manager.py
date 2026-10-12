"""Store grocery unit definitions independently of their item assignments."""

import json
import os
from pathlib import Path
import tempfile

from classes.grocery_unit_class import GroceryUnit


_UNITS_PATH = Path(__file__).resolve().parents[2] / "assets" / "jsons" / "grocery_units.json"


class GroceryUnitsManager:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else _UNITS_PATH

    @staticmethod
    def _validate(units: list[GroceryUnit]) -> None:
        if any(not isinstance(unit, GroceryUnit) for unit in units):
            raise ValueError("Provide valid grocery units.")
        if len({unit.unit_id for unit in units}) != len(units):
            raise ValueError("Grocery units must have unique identifiers.")
        labels = {}
        for unit in units:
            for label in (unit.name, unit.plural):
                if label.casefold() in labels and labels[label.casefold()] != unit.unit_id:
                    raise ValueError("A unit with that singular or plural name already exists.")
                labels[label.casefold()] = unit.unit_id

    def load(self) -> list[GroceryUnit]:
        if not self.path.exists():
            return []
        try:
            record = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(record, dict) or record.get("version") != 1 or not isinstance(record.get("units"), list):
                raise ValueError("Invalid saved grocery units format.")
            units = [GroceryUnit.from_dict(unit) for unit in record["units"]]
            self._validate(units)
            return units
        except (ValueError, TypeError) as error:
            raise ValueError(f"Could not read grocery units: {error}") from error

    def save(self, units: list[GroceryUnit]) -> None:
        self._validate(units)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=self.path.parent,
                                             prefix=".grocery-units-", suffix=".tmp", delete=False) as temporary:
                temporary_path = Path(temporary.name)
                json.dump({"version": 1, "units": [unit.to_dict() for unit in units]}, temporary,
                          ensure_ascii=False, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
