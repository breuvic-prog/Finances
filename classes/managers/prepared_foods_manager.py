"""Persist named foods while keeping their ingredient and plan references stable."""

import json
import os
from pathlib import Path
import tempfile

from classes.prepared_food_class import PreparedFood


_FOODS_PATH = Path(__file__).resolve().parents[2] / "assets" / "jsons" / "prepared_foods.json"


class PreparedFoodsManager:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else _FOODS_PATH

    def load(self) -> list[PreparedFood]:
        if not self.path.exists():
            return []
        try:
            record = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(record, dict) or record.get("version") != 1 or not isinstance(record.get("foods"), list):
                raise ValueError("Invalid saved foods.")
            return self._validate(PreparedFood.from_dict(food) for food in record["foods"])
        except (ValueError, TypeError) as error:
            raise ValueError(f"Could not read prepared foods: {error}") from error

    @staticmethod
    def _validate(foods) -> list[PreparedFood]:
        try:
            foods = list(foods)
        except TypeError as error:
            raise ValueError("Provide a list of prepared foods.") from error
        if any(not isinstance(food, PreparedFood) for food in foods):
            raise ValueError("Provide valid prepared foods.")
        if len({food.food_id for food in foods}) != len(foods):
            raise ValueError("Foods must have unique identifiers.")
        if len({food.name.casefold() for food in foods}) != len(foods):
            raise ValueError("A food with that name already exists. Choose a different name.")
        return foods

    def save(self, foods) -> None:
        foods = self._validate(foods)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=self.path.parent,
                                             prefix=".prepared-foods-", suffix=".tmp", delete=False) as temporary:
                temporary_path = Path(temporary.name)
                json.dump({"version": 1, "foods": [food.to_dict() for food in foods]}, temporary, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
