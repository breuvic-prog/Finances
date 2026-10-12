"""An hourly job with a recurring schedule of paid hours, Monday through Sunday."""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from uuid import uuid4
from classes.work_shift_class import WorkShift
from classes.food_consumption_class import FoodConsumption, validate_food_plan


WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _number(value, label: str) -> Decimal:
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation as error:
        raise ValueError(f"Enter a valid number for {label}.") from error
    if not number.is_finite():
        raise ValueError(f"Enter a valid number for {label}.")
    return number


@dataclass(frozen=True)
class BudgetJob:
    name: str
    hourly_wage: Decimal
    tax_percentage: Decimal
    weekly_hours: tuple[Decimal, ...]
    job_id: str = field(default_factory=lambda: uuid4().hex)
    weekly_shifts: tuple[WorkShift | None, ...] | None = None
    foods_per_shift: tuple[FoodConsumption, ...] = ()

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Enter a job name.")
        if not isinstance(self.job_id, str) or not self.job_id.strip():
            raise ValueError("The job must have an identifier.")
        wage = _number(self.hourly_wage, "hourly wage")
        tax = _number(self.tax_percentage, "tax percentage")
        if wage < 0:
            raise ValueError("Hourly wage cannot be negative.")
        if not 0 <= tax <= 100:
            raise ValueError("Tax percentage must be between 0 and 100.")
        if self.weekly_shifts is not None:
            if len(self.weekly_shifts) != 7 or any(shift is not None and not isinstance(shift, WorkShift)
                                                  for shift in self.weekly_shifts):
                raise ValueError("Provide a shift or a day off for all seven weekdays.")
            object.__setattr__(self, "weekly_shifts", tuple(self.weekly_shifts))
            hours = tuple(shift.hours if shift else Decimal(0) for shift in self.weekly_shifts)
        else:
            if len(self.weekly_hours) != 7:
                raise ValueError("Provide paid hours for all seven weekdays.")
            hours = tuple(_number(value, f"{day} hours") for day, value in zip(WEEKDAYS, self.weekly_hours))
        for day, value in zip(WEEKDAYS, hours):
            if not 0 <= value <= 24:
                raise ValueError(f"{day} hours must be between 0 and 24.")
        try:
            if wage != wage.quantize(Decimal("0.01")):
                raise ValueError("Hourly wage can have at most two decimal places.")
        except InvalidOperation as error:
            raise ValueError("Enter a valid hourly wage.") from error
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "hourly_wage", wage)
        object.__setattr__(self, "tax_percentage", tax)
        object.__setattr__(self, "weekly_hours", hours)
        object.__setattr__(self, "foods_per_shift", validate_food_plan(self.foods_per_shift))

    @property
    def hours_per_week(self) -> Decimal:
        return sum(self.weekly_minutes, Decimal(0)) / 60

    @property
    def weekly_minutes(self) -> tuple[Decimal, ...]:
        if self.weekly_shifts is not None:
            return tuple(Decimal(shift.paid_minutes) if shift else Decimal(0) for shift in self.weekly_shifts)
        return tuple(hours * 60 for hours in self.weekly_hours)

    def to_dict(self) -> dict:
        record = {"id": self.job_id, "name": self.name, "hourly_wage": str(self.hourly_wage),
                  "tax_percentage": str(self.tax_percentage), "weekly_hours": [str(value) for value in self.weekly_hours]}
        if self.weekly_shifts is not None:
            record["weekly_shifts"] = [shift.to_dict() if shift else None for shift in self.weekly_shifts]
        record["foods_per_shift"] = [food.to_dict() for food in self.foods_per_shift]
        return record

    @classmethod
    def from_dict(cls, record: dict):
        if not isinstance(record, dict):
            raise ValueError("Invalid saved job.")
        try:
            shifts = record.get("weekly_shifts")
            if shifts is not None:
                if not isinstance(shifts, list):
                    raise ValueError("Invalid saved weekly shifts.")
                shifts = tuple(WorkShift.from_dict(shift) if shift is not None else None for shift in shifts)
            elif not isinstance(record.get("weekly_hours"), list):
                raise ValueError("Invalid saved job.")
            foods = record.get("foods_per_shift", [])
            if not isinstance(foods, list):
                raise ValueError("Invalid saved shift food plan.")
            return cls(record["name"], record["hourly_wage"], record["tax_percentage"],
                       tuple(record.get("weekly_hours", (0,) * 7)), record["id"], shifts,
                       tuple(FoodConsumption.from_dict(food) for food in foods))
        except (KeyError, TypeError) as error:
            raise ValueError("Invalid saved job.") from error
