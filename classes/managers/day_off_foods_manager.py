"""Save the shared food plan for one day off, independently of individual jobs."""

import json
import os
from pathlib import Path
import tempfile

from classes.food_consumption_class import FoodConsumption, validate_food_plan


_DAY_OFF_FOODS_PATH = Path(__file__).resolve().parents[2] / "assets" / "jsons" / "day_off_foods.json"


class DayOffFoodsManager:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else _DAY_OFF_FOODS_PATH

    def load(self) -> tuple[FoodConsumption, ...]:
        if not self.path.exists():
            return ()
        try:
            record = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(record, dict) or record.get("version") != 1 or not isinstance(record.get("foods"), list):
                raise ValueError("Invalid saved day-off food plan.")
            return validate_food_plan(FoodConsumption.from_dict(food) for food in record["foods"])
        except (ValueError, TypeError) as error:
            raise ValueError(f"Could not read food for days off: {error}") from error

    def save(self, foods: tuple[FoodConsumption, ...]) -> None:
        foods = validate_food_plan(foods)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=self.path.parent,
                                             prefix=".day-off-foods-", suffix=".tmp", delete=False) as temporary:
                temporary_path = Path(temporary.name)
                json.dump({"version": 1, "foods": [food.to_dict() for food in foods]}, temporary, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
