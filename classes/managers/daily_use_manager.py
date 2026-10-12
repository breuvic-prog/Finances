"""Save the daily baseline independently of work and day-off consumption."""

import json
import os
from pathlib import Path
import tempfile

from classes.daily_use_item_class import DailyUseItem, validate_daily_use


_DAILY_USE_PATH = Path(__file__).resolve().parents[2] / "assets" / "jsons" / "daily_use.json"


class DailyUseManager:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else _DAILY_USE_PATH

    def load(self) -> tuple[DailyUseItem, ...]:
        if not self.path.exists():
            return ()
        try:
            record = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(record, dict) or record.get("version") != 1 or not isinstance(record.get("items"), list):
                raise ValueError("Invalid saved daily-use plan.")
            return validate_daily_use(DailyUseItem.from_dict(item) for item in record["items"])
        except (ValueError, TypeError) as error:
            raise ValueError(f"Could not read Daily Use: {error}") from error

    def save(self, items) -> None:
        items = validate_daily_use(items)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=self.path.parent,
                                             prefix=".daily-use-", suffix=".tmp", delete=False) as temporary:
                temporary_path = Path(temporary.name)
                json.dump({"version": 1, "items": [item.to_dict() for item in items]}, temporary, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
