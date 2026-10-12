"""A recurring shift represented by clock times at minute precision."""

from dataclasses import dataclass
from decimal import Decimal
import re


_TIME = re.compile(r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<period>AM|PM)?", re.IGNORECASE)


def _minutes(value: str, label: str) -> int:
    match = _TIME.fullmatch(value.strip()) if isinstance(value, str) else None
    if match is None:
        raise ValueError(f"Enter a valid {label}, for example 8:00 AM or 15:51.")
    hour = int(match["hour"])
    minute = int(match["minute"] or 0)
    period = match["period"]
    if minute > 59 or (not 1 <= hour <= 12 if period else not 0 <= hour <= 23):
        raise ValueError(f"Enter a valid {label}, for example 8:00 AM or 15:51.")
    if period:
        hour = hour % 12 + (12 if period.upper() == "PM" else 0)
    return hour * 60 + minute


def _clock(minutes: int) -> str:
    hour, minute = divmod(minutes, 60)
    return f"{hour % 12 or 12}:{minute:02d} {'AM' if hour < 12 else 'PM'}"


@dataclass(frozen=True)
class WorkShift:
    start: str
    end: str
    unpaid_break_minutes: int = 0

    def __post_init__(self):
        start = _minutes(self.start, "shift start time")
        end = _minutes(self.end, "shift end time")
        if start == end:
            raise ValueError("Shift start and end times must be different.")
        break_text = str(self.unpaid_break_minutes).strip()
        if re.fullmatch(r"[0-9]+", break_text) is None:
            raise ValueError("Enter unpaid break time as a non-negative number of whole minutes.")
        break_minutes = int(break_text)
        if break_minutes >= (end - start) % (24 * 60):
            raise ValueError("Unpaid break time must be shorter than the shift.")
        object.__setattr__(self, "start", _clock(start))
        object.__setattr__(self, "end", _clock(end))
        object.__setattr__(self, "unpaid_break_minutes", break_minutes)

    @property
    def start_minutes(self) -> int:
        return _minutes(self.start, "shift start time")

    @property
    def minutes(self) -> int:
        return (_minutes(self.end, "shift end time") - self.start_minutes) % (24 * 60)

    @property
    def hours(self) -> Decimal:
        return Decimal(self.paid_minutes) / 60

    @property
    def paid_minutes(self) -> int:
        return self.minutes - self.unpaid_break_minutes

    @property
    def overnight(self) -> bool:
        return _minutes(self.end, "shift end time") < self.start_minutes

    def to_dict(self) -> dict:
        return {"start": self.start, "end": self.end, "unpaid_break_minutes": self.unpaid_break_minutes}

    @classmethod
    def from_dict(cls, record: dict):
        if not isinstance(record, dict):
            raise ValueError("Invalid saved shift.")
        try:
            return cls(record["start"], record["end"], record.get("unpaid_break_minutes", 0))
        except KeyError as error:
            raise ValueError("Invalid saved shift.") from error
