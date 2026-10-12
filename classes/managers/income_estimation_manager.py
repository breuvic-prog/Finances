from calendar import monthrange
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from classes.budget_job_class import BudgetJob


CENT = Decimal("0.01")


@dataclass(frozen=True)
class JobIncomeEstimate:
    job: BudgetJob
    hours: Decimal
    gross: Decimal
    tax: Decimal
    take_home: Decimal


@dataclass(frozen=True)
class IncomeEstimate:
    month: date
    jobs: tuple[JobIncomeEstimate, ...]

    @property
    def gross(self) -> Decimal:
        return sum((job.gross for job in self.jobs), Decimal("0.00"))

    @property
    def tax(self) -> Decimal:
        return sum((job.tax for job in self.jobs), Decimal("0.00"))

    @property
    def take_home(self) -> Decimal:
        return sum((job.take_home for job in self.jobs), Decimal("0.00"))


class IncomeEstimationManager:
    @staticmethod
    def next_month(current_date: date | None = None) -> date:
        today = current_date or date.today()
        return date(today.year + (today.month == 12), today.month % 12 + 1, 1)

    @classmethod
    def estimate(cls, jobs: list[BudgetJob], current_date: date | None = None) -> IncomeEstimate:
        month = cls.next_month(current_date)
        weekdays = Counter(date(month.year, month.month, day).weekday()
                           for day in range(1, monthrange(month.year, month.month)[1] + 1))
        estimates = []
        for job in jobs:
            if job.weekly_shifts is None:
                minutes = sum((paid_minutes * weekdays[day] for day, paid_minutes in enumerate(job.weekly_minutes)), Decimal(0))
            else:
                # Include overnight hours carried in from the preceding month, and
                # exclude any hours extending beyond the final night of this month.
                last_day = monthrange(month.year, month.month)[1]
                minutes = Decimal(0)
                for offset in range(-1, last_day):
                    shift = job.weekly_shifts[(month + timedelta(days=offset)).weekday()]
                    if shift is not None:
                        start = offset * 1440 + shift.start_minutes
                        end = start + shift.minutes
                        overlap = max(0, min(end, last_day * 1440) - max(start, 0))
                        # Only a break's duration is known. For shifts crossing a
                        # month boundary, allocate it in proportion to each part.
                        minutes += Decimal(overlap) * shift.paid_minutes / shift.minutes
            hours = minutes / 60
            gross = (minutes * job.hourly_wage / 60).quantize(CENT, rounding=ROUND_HALF_UP)
            tax = (gross * job.tax_percentage / 100).quantize(CENT, rounding=ROUND_HALF_UP)
            estimates.append(JobIncomeEstimate(job, hours, gross, tax, gross - tax))
        return IncomeEstimate(month, tuple(estimates))
