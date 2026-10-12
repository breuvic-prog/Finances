import json
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from classes.budget_job_class import BudgetJob
from classes.work_shift_class import WorkShift
from classes.managers.budget_jobs_manager import BudgetJobsManager
from classes.managers.income_estimation_manager import IncomeEstimationManager


def scheduled_job(shifts, wage="15", tax="20"):
    return BudgetJob("Scheduled job", wage, tax, (0,) * 7, weekly_shifts=tuple(shifts))


class WorkShiftTests(unittest.TestCase):
    def test_example_is_seven_hours_and_fifty_one_minutes(self):
        shift = WorkShift("8:00 AM", "3:51 PM")
        self.assertEqual(shift.minutes, 471)
        self.assertEqual(shift.hours, Decimal("7.85"))
        self.assertFalse(shift.overnight)
        job = scheduled_job([shift, None, None, None, None, None, None])
        estimate = IncomeEstimationManager.estimate([job], date(2026, 10, 7))
        self.assertEqual(job.hours_per_week, Decimal("7.85"))
        self.assertEqual(estimate.jobs[0].hours, Decimal("39.25"))
        self.assertEqual((estimate.gross, estimate.tax, estimate.take_home),
                         (Decimal("588.75"), Decimal("117.75"), Decimal("471.00")))

    def test_am_pm_and_24_hour_formats_normalize_and_preserve_noon_and_midnight(self):
        for start, end in ((" 8:00am ", "3:51 pm"), ("08:00", "15:51"), ("8 AM", "3:51PM")):
            with self.subTest(start=start):
                self.assertEqual(WorkShift(start, end), WorkShift("8:00 AM", "3:51 PM"))
        self.assertEqual(WorkShift("12 AM", "12 PM").minutes, 720)
        self.assertEqual(WorkShift("12 PM", "12 AM").minutes, 720)
        self.assertEqual(WorkShift("11:30 PM", "1:15 AM").minutes, 105)
        self.assertTrue(WorkShift("11:30 PM", "1:15 AM").overnight)

    def test_invalid_incomplete_and_identical_times_are_rejected(self):
        for start, end in (("", "3 PM"), ("8 AM", ""), ("25:00", "10:00"), ("8:60 AM", "4 PM"),
                           ("13:00 PM", "4 PM"), ("0 AM", "4 PM"), ("eight", "4 PM"),
                           ("8:00 AM", "08:00"), (None, "4 PM"), ("8 AM", "3:5 PM")):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                WorkShift(start, end)

    def test_minute_precision_avoids_a_fractional_hour_rounding_error_in_gross_pay(self):
        shift = WorkShift("8:00 AM", "8:01 AM")
        job = scheduled_job([shift] * 5 + [None, None], wage="0.30", tax="0")
        estimate = IncomeEstimationManager.estimate([job], date(2026, 10, 7))
        self.assertEqual(estimate.gross, Decimal("0.11"))

    def test_unpaid_lunch_reduces_weekly_hours_and_monthly_income(self):
        shift = WorkShift("8:00 AM", "3:51 PM", "30")
        self.assertEqual(shift.minutes, 471)
        self.assertEqual(shift.unpaid_break_minutes, 30)
        self.assertEqual(shift.paid_minutes, 441)
        self.assertEqual(shift.hours, Decimal("7.35"))
        job = scheduled_job([shift, None, None, None, None, None, None])
        estimate = IncomeEstimationManager.estimate([job], date(2026, 10, 7))
        self.assertEqual(job.hours_per_week, Decimal("7.35"))
        self.assertEqual(estimate.jobs[0].hours, Decimal("36.75"))
        self.assertEqual((estimate.gross, estimate.tax, estimate.take_home),
                         (Decimal("551.25"), Decimal("110.25"), Decimal("441.00")))

    def test_invalid_breaks_are_rejected_including_breaks_as_long_as_the_shift(self):
        for unpaid_break in (-1, "-30", "lunch", "30.5", 30.5, "NaN", "Infinity", None, True, 471, 472):
            with self.subTest(unpaid_break=unpaid_break), self.assertRaisesRegex(ValueError, "[Uu]npaid break"):
                WorkShift("8:00 AM", "3:51 PM", unpaid_break)

    def test_overnight_breaks_are_proportional_across_month_boundaries(self):
        overnight = WorkShift("10 PM", "6 AM", 60)
        self.assertEqual(overnight.hours, 7)
        sunday = scheduled_job([None] * 6 + [overnight], wage="20", tax="0")
        wednesday = scheduled_job([None, None, overnight, None, None, None, None], wage="20", tax="0")
        estimate = IncomeEstimationManager.estimate([sunday, wednesday], date(2027, 2, 28))
        self.assertEqual([row.hours for row in estimate.jobs], [Decimal("33.25"), Decimal("29.75")])
        self.assertEqual(estimate.gross, Decimal("1260.00"))
        december = scheduled_job([None, None, None, overnight, None, None, None], wage="20", tax="0")
        self.assertEqual(IncomeEstimationManager.estimate([december], date(2026, 12, 31)).jobs[0].hours,
                         Decimal("33.25"))

    def test_breaks_persist_and_older_saved_shifts_default_to_no_break(self):
        job = scheduled_job([WorkShift("8 AM", "4 PM", 30), WorkShift("8 AM", "4 PM", 60)] + [None] * 5)
        tests_directory = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix="unpaid-breaks-", dir=tests_directory) as workspace:
            store = BudgetJobsManager(Path(workspace) / "jobs.json")
            store.save([job])
            reopened, = BudgetJobsManager(store.path).load()
            self.assertEqual(reopened, job)
            self.assertEqual(reopened.weekly_hours[:2], (Decimal("7.5"), Decimal("7")))
            self.assertEqual(reopened.hours_per_week, Decimal("14.5"))
            self.assertEqual(reopened.to_dict()["weekly_shifts"][0]["unpaid_break_minutes"], 30)
        old_record = job.to_dict()
        for shift in old_record["weekly_shifts"]:
            if shift is not None:
                shift.pop("unpaid_break_minutes")
        older = BudgetJob.from_dict(old_record)
        self.assertEqual(older.weekly_hours[:2], (Decimal(8), Decimal(8)))
        self.assertEqual(older.weekly_shifts[0].unpaid_break_minutes, 0)
        self.assertEqual(older.job_id, job.job_id)
        with self.assertRaises(ValueError):
            BudgetJob.from_dict({**old_record, "weekly_shifts": [
                {"start": "8 AM", "end": "4 PM", "unpaid_break_minutes": -30}] + [None] * 6})

    def test_overnight_shifts_allocate_hours_to_the_actual_review_month(self):
        overnight = WorkShift("10 PM", "6 AM")
        sunday = scheduled_job([None] * 6 + [overnight])
        wednesday = scheduled_job([None, None, overnight, None, None, None, None])
        estimate = IncomeEstimationManager.estimate([sunday, wednesday], date(2027, 2, 28))
        self.assertEqual(estimate.month, date(2027, 3, 1))
        self.assertEqual([row.hours for row in estimate.jobs], [38, 34])
        december = scheduled_job([None, None, None, overnight, None, None, None])
        january = IncomeEstimationManager.estimate([december], date(2026, 12, 31))
        self.assertEqual(january.jobs[0].hours, 38)

    def test_saved_shift_times_round_trip_and_override_stale_derived_hours(self):
        job = scheduled_job([WorkShift("8:00 AM", "3:51 PM")] * 5 + [None, None])
        record = job.to_dict()
        record["weekly_hours"] = ["24"] * 7
        loaded = BudgetJob.from_dict(record)
        self.assertEqual(loaded, job)
        self.assertEqual(loaded.weekly_hours, (Decimal("7.85"),) * 5 + (Decimal(0),) * 2)
        self.assertEqual(loaded.job_id, job.job_id)
        self.assertIsNone(loaded.weekly_shifts[-1])

    def test_invalid_saved_shifts_are_reported(self):
        record = scheduled_job([None] * 7).to_dict()
        for shifts in ([None] * 6, "invalid", [{"start": "8 AM"}] * 7, [{"start": "bad", "end": "4 PM"}] * 7):
            with self.subTest(shifts=shifts), self.assertRaises(ValueError):
                BudgetJob.from_dict({**record, "weekly_shifts": shifts})

    def test_existing_hours_only_jobs_keep_their_values_without_inventing_shift_times(self):
        record = {"id": "existing-job", "name": "Existing job", "hourly_wage": "15", "tax_percentage": "20",
                  "weekly_hours": ["8", "8", "8", "8", "8", "0", "0"]}
        tests_directory = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix="shift-migration-", dir=tests_directory) as workspace:
            path = Path(workspace) / "jobs.json"
            original = json.dumps({"version": 1, "jobs": [record]}).encode()
            path.write_bytes(original)
            store = BudgetJobsManager(path)
            loaded, = store.load()
            self.assertIsNone(loaded.weekly_shifts)
            self.assertEqual(loaded.job_id, "existing-job")
            self.assertEqual(IncomeEstimationManager.estimate([loaded], date(2026, 10, 7)).take_home, 2016)
            self.assertEqual(path.read_bytes(), original)
            updated = BudgetJob(loaded.name, loaded.hourly_wage, loaded.tax_percentage, (0,) * 7,
                                loaded.job_id, (WorkShift("8 AM", "4 PM"),) * 5 + (None, None))
            store.save([updated])
            self.assertEqual(store.load(), [updated])


if __name__ == "__main__":
    unittest.main()
