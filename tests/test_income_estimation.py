import json
import tempfile
import tkinter as tk
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from classes.budget_job_class import BudgetJob
from classes.work_shift_class import WorkShift
from classes.managers.budget_jobs_manager import BudgetJobsManager
from classes.managers.income_estimation_manager import IncomeEstimationManager
from classes.pages.child_pages.budget_planning_page_class import BudgetPlanningPage
from classes.pages.child_pages.budget_planning_pages import income_estimation_page
from classes.pages.page_container_class import PageContainer


def job(name="Primary job", wage="15.00", tax="20", hours=(8, 8, 8, 8, 8, 0, 0)):
    return BudgetJob(name, wage, tax, tuple(hours))


class IncomeCalculationTests(unittest.TestCase):
    def test_next_month_uses_actual_workdays_for_multiple_jobs(self):
        estimate = IncomeEstimationManager.estimate([
            job(), job("Weekend job", "20", "10", (0, 0, 0, 0, 0, 4, 4))], date(2026, 10, 7))
        self.assertEqual(estimate.month, date(2026, 11, 1))
        self.assertEqual([row.hours for row in estimate.jobs], [168, 36])
        self.assertEqual([row.gross for row in estimate.jobs], [2520, 720])
        self.assertEqual([row.tax for row in estimate.jobs], [504, 72])
        self.assertEqual((estimate.gross, estimate.tax, estimate.take_home), (3240, 576, 2664))

    def test_leap_february_counts_the_extra_scheduled_day(self):
        estimate = IncomeEstimationManager.estimate([job(hours=(0, 0, 0, 8, 8, 0, 0))], date(2024, 1, 31))
        self.assertEqual(estimate.month, date(2024, 2, 1))
        self.assertEqual(estimate.jobs[0].hours, 72)
        self.assertEqual(estimate.jobs[0].gross, 1080)

    def test_december_rolls_over_to_january_of_the_next_year(self):
        estimate = IncomeEstimationManager.estimate([job(hours=(0, 0, 0, 0, 8, 0, 0))], date(2026, 12, 31))
        self.assertEqual(estimate.month, date(2027, 1, 1))
        self.assertEqual(estimate.jobs[0].hours, 40)

    def test_fractional_hours_and_percentages_round_money_to_cents(self):
        estimate = IncomeEstimationManager.estimate([job(wage="19.99", tax="12.5", hours=("7.5", 0, 0, 0, 0, 0, 0))],
                                                    date(2026, 10, 1))
        row, = estimate.jobs
        self.assertEqual(row.hours, Decimal("37.5"))
        self.assertEqual((row.gross, row.tax, row.take_home),
                         (Decimal("749.63"), Decimal("93.70"), Decimal("655.93")))
        small = IncomeEstimationManager.estimate([job(wage="0.01", tax="10", hours=(1, 0, 0, 0, 0, 0, 0))],
                                                date(2026, 10, 1))
        self.assertEqual((small.gross, small.tax, small.take_home),
                         (Decimal("0.05"), Decimal("0.01"), Decimal("0.04")))

    def test_zero_income_and_zero_or_full_tax_are_supported(self):
        empty = IncomeEstimationManager.estimate([], date(2026, 10, 1))
        self.assertEqual((empty.gross, empty.tax, empty.take_home), (0, 0, 0))
        estimate = IncomeEstimationManager.estimate([job(tax=0), job(tax=100), job(hours=(0,) * 7)], date(2026, 10, 1))
        self.assertEqual([row.take_home for row in estimate.jobs], [2520, 0, 0])

    def test_invalid_rates_percentages_and_schedules_are_rejected(self):
        for fields in ({"name": " "}, {"wage": ""}, {"wage": "-1"}, {"wage": "NaN"},
                       {"wage": "1.234"}, {"wage": "Infinity"}, {"tax": "NaN"}, {"tax": "101"},
                       {"tax": "-0.1"}, {"hours": (0,) * 6}, {"hours": (25, 0, 0, 0, 0, 0, 0)},
                       {"hours": (-1, 0, 0, 0, 0, 0, 0)}, {"hours": ("NaN", 0, 0, 0, 0, 0, 0)}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                job(**fields)


class BudgetJobsPersistenceTests(unittest.TestCase):
    def setUp(self):
        tests_directory = Path(__file__).resolve().parent
        self.workspace = Path(self.enterContext(tempfile.TemporaryDirectory(
            prefix="budget-jobs-", dir=tests_directory))).resolve()
        if self.workspace.parent != tests_directory:
            raise RuntimeError("Unexpected temporary directory location.")
        self.store = BudgetJobsManager(self.workspace / "jobs.json")

    def test_jobs_and_schedules_are_reused_after_restart_and_removal_is_persistent(self):
        self.assertEqual(self.store.load(), [])
        jobs = [job(name='Store "North"'), job("Weekend", "19.99", "12.5", (0, 0, 0, 0, 0, "7.5", 0))]
        self.store.save(jobs)
        reopened = BudgetJobsManager(self.store.path)
        self.assertEqual(reopened.load(), jobs)
        self.store.save([jobs[1]])
        self.assertEqual(reopened.load(), [jobs[1]])
        self.store.save([])
        self.assertEqual(reopened.load(), [])
        self.assertEqual(list(self.workspace.iterdir()), [self.store.path])

    def test_corrupt_or_unsupported_settings_are_reported_without_overwriting_them(self):
        for contents in ("not JSON", "[]", '{"version":2,"jobs":[]}', '{"version":1,"jobs":[{}]}',
                         '{"version":1,"jobs":null}'):
            with self.subTest(contents=contents):
                self.store.path.write_text(contents, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Could not read saved jobs"):
                    self.store.load()
                self.assertEqual(self.store.path.read_text(encoding="utf-8"), contents)

    def test_duplicate_ids_are_rejected_and_failed_writes_preserve_the_previous_settings(self):
        original = job()
        self.store.save([original])
        contents = self.store.path.read_bytes()
        with self.assertRaises(ValueError):
            self.store.save([original, original])
        self.assertEqual(self.store.path.read_bytes(), contents)
        with patch("classes.managers.budget_jobs_manager.os.replace", side_effect=OSError("Disk full")), \
                self.assertRaisesRegex(OSError, "Disk full"):
            self.store.save([job("Replacement")])
        self.assertEqual(self.store.path.read_bytes(), contents)
        self.assertEqual(list(self.workspace.iterdir()), [self.store.path])
        self.store.path.write_text(json.dumps({"version": 1, "jobs": [original.to_dict()] * 2}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate identifiers"):
            self.store.load()


class IncomePageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as error:
            raise unittest.SkipTest(f"Tk is unavailable: {error}")
        cls.root.withdraw()
        cls.toplevel_type = tk.Toplevel

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        tests_directory = Path(__file__).resolve().parent
        self.workspace = Path(self.enterContext(tempfile.TemporaryDirectory(
            prefix="income-page-", dir=tests_directory))).resolve()
        self.store = BudgetJobsManager(self.workspace / "jobs.json")
        self.page = income_estimation_page.IncomeEstimationPage(self.root, Mock(), self.store,
                                                              today=lambda: date(2026, 10, 7))

    def tearDown(self):
        if self.page._editor is not None and self.page._editor.winfo_exists():
            self.page._editor.destroy()
        self.page._root.destroy()

    def hidden_popup(self, *args, **kwargs):
        popup = self.toplevel_type(*args, **kwargs)
        popup.withdraw()
        return popup

    def open_editor(self, existing=None):
        with patch.object(income_estimation_page.tk, "Toplevel", side_effect=self.hidden_popup):
            return self.page._show_job_editor(existing)

    def set_fields(self, name="Main job", wage="15", tax="20", hours=(8, 8, 8, 8, 8, 0, 0)):
        fields = self.page._editor_values
        for key, value in (("name", name), ("wage", wage), ("tax", tax)):
            fields[key].set(value)
        for working, start, end, value in zip(fields["working"], fields["starts"], fields["ends"], hours):
            working.set(bool(value))
            start.set("8:00 AM" if value else "")
            total_minutes = int(Decimal(str(value)) * 60) + 8 * 60
            end.set(f"{total_minutes // 60 % 24:02d}:{total_minutes % 60:02d}" if value else "")

    def add_job(self):
        popup = self.open_editor()
        self.set_fields()
        self.page._save_job_button.invoke()
        self.assertFalse(popup.winfo_exists())

    def test_add_and_edit_persist_all_job_fields_and_refresh_the_monthly_totals(self):
        self.assertEqual(self.page._month_label.cget("text"), "November 2026")
        self.add_job()
        original, = self.page._jobs
        self.assertEqual(self.store.load(), [original])
        self.assertEqual(self.page._total_labels["take_home"].cget("text"), "$2,016.00")
        cells = self.page._job_table._components[0]
        self.assertEqual(cells[0].cget("text"), "Main job")
        self.assertIn("Mon", cells[1].cget("text"))
        self.assertIn("8:00 AM – 4:00 PM", cells[1].cget("text"))
        self.assertEqual(cells[4].cget("text"), "168")
        with patch.object(income_estimation_page.tk, "Toplevel", side_effect=self.hidden_popup):
            cells[8].winfo_children()[0].invoke()
        self.set_fields(name="Renamed job", wage="20")
        self.page._save_job_button.invoke()
        edited, = self.page._jobs
        self.assertEqual(edited.job_id, original.job_id)
        self.assertEqual(edited.name, "Renamed job")
        self.assertEqual(self.store.load(), [edited])
        self.assertEqual(self.page._total_labels["take_home"].cget("text"), "$2,688.00")

    def test_remove_requires_confirmation_and_updates_saved_jobs_and_estimates(self):
        self.add_job()
        contents = self.store.path.read_bytes()
        remove = self.page._job_table._components[0][8].winfo_children()[1]
        self.assertEqual(remove.cget("fg"), "#B91C1C")
        with patch.object(income_estimation_page.messagebox, "askyesno", return_value=False):
            remove.invoke()
        self.assertEqual(self.store.path.read_bytes(), contents)
        self.assertEqual(len(self.page._jobs), 1)
        with patch.object(income_estimation_page.messagebox, "askyesno", return_value=True):
            remove.invoke()
        self.assertEqual(self.page._jobs, [])
        self.assertEqual(self.store.load(), [])
        self.assertEqual(self.page._total_labels["take_home"].cget("text"), "$0.00")

    def test_invalid_editor_values_and_cancel_do_not_modify_saved_jobs(self):
        self.add_job()
        contents = self.store.path.read_bytes()
        popup = self.open_editor(self.page._jobs[0])
        self.set_fields(tax="101")
        self.page._save_job_button.invoke()
        self.assertTrue(popup.winfo_exists())
        self.assertIn("between 0 and 100", self.page._editor_error.cget("text"))
        self.assertEqual(self.store.path.read_bytes(), contents)
        popup.destroy()
        self.assertEqual(self.store.path.read_bytes(), contents)

    def test_save_failure_keeps_the_editor_and_previous_values_available_for_retry(self):
        popup = self.open_editor()
        self.set_fields()
        with patch.object(self.store, "save", side_effect=OSError("Disk full")), \
                patch.object(income_estimation_page.messagebox, "showerror") as error:
            self.page._save_job_button.invoke()
        self.assertIn("Disk full", error.call_args.args[1])
        self.assertTrue(popup.winfo_exists())
        self.assertFalse(self.store.path.exists())
        self.assertEqual(self.page._jobs, [])
        self.page._save_job_button.invoke()
        self.assertFalse(popup.winfo_exists())
        self.assertEqual(len(self.store.load()), 1)

    def test_corrupt_settings_block_edits_until_reloaded_successfully(self):
        self.store.path.write_bytes(b"not JSON")
        self.page._reload_and_refresh()
        self.assertIn("Could not read saved jobs", self.page._status.cget("text"))
        self.assertEqual(str(self.page._add_button.cget("state")), "disabled")
        self.assertEqual(str(self.page._continue_button.cget("state")), "disabled")
        self.page._continue_button.invoke()
        self.page._parent_next_method.assert_not_called()
        self.assertIsNone(self.page._show_job_editor())
        self.assertEqual(self.store.path.read_bytes(), b"not JSON")
        self.store.save([job()])
        self.page._reload_and_refresh()
        self.assertEqual(str(self.page._add_button.cget("state")), "normal")
        self.assertEqual(self.page.income_estimate.take_home, 2016)

    def test_activation_reuses_jobs_and_recalculates_after_the_current_month_changes(self):
        self.add_job()
        self.page._today = lambda: date(2026, 12, 31)
        self.page.activate()
        self.assertEqual(self.page._month_label.cget("text"), "January 2027")
        self.assertEqual(len(self.page._jobs), 1)
        self.assertEqual(self.page.income_estimate.jobs[0].hours, 168)

    def test_budget_page_opens_with_two_grocery_subpages_before_income_estimation(self):
        with patch("classes.managers.budget_jobs_manager._JOBS_PATH", self.store.path), \
                patch("classes.managers.grocery_catalog_manager._GROCERIES_PATH", self.store.path.with_suffix(".csv")):
            budget = BudgetPlanningPage(self.root, Mock())
        self.addCleanup(budget._root.destroy)
        self.assertEqual(len(budget._pages), 5)
        self.assertEqual(len(budget._pages[0]._pages), 2)
        self.assertIs(budget._pages[0].items_page, budget._grocery_page)
        self.assertIs(budget._pages[0].prices_page, budget._grocery_prices_page)
        self.assertIs(budget._pages[1], budget._foods_page)
        self.assertIs(budget._pages[2], budget._daily_use_page)
        self.assertIsInstance(budget._pages[3], income_estimation_page.IncomeEstimationPage)
        self.assertIs(budget.income_estimate, budget._pages[3].income_estimate)

    def test_headers_align_with_job_rows_and_footer_remains_visible_in_a_smaller_window(self):
        self.add_job()
        self.root.attributes("-alpha", 0)
        self.root.geometry("1100x650")
        self.page.activate()
        self.root.deiconify()
        self.root.update()
        try:
            table = self.page._job_table
            for header, cell in zip(table._head_components, table._components[0]):
                self.assertEqual(header.winfo_rootx(), cell.winfo_rootx())
                self.assertEqual(header.winfo_width(), cell.winfo_width())
            self.assertTrue(self.page._status.winfo_ismapped())
            self.assertLessEqual(self.page._status.winfo_rooty() + self.page._status.winfo_height(),
                                 self.root.winfo_rooty() + self.root.winfo_height())
        finally:
            self.root.withdraw()

    def test_shift_times_preview_calculated_hours_and_persist_for_later_edits(self):
        popup = self.open_editor()
        self.set_fields(hours=(8, 0, 0, 0, 0, 0, 0))
        values = self.page._editor_values
        values["ends"][0].set("3:51 PM")
        self.assertNotIn("hours", values)
        self.assertEqual(self.page._shift_hours_labels[0].cget("text"), "7.85 h")
        self.assertEqual(self.page._shift_hours_labels[1].cget("text"), "Off")
        self.assertEqual(str(self.page._shift_entries[1][0].cget("state")), "disabled")
        self.page._save_job_button.invoke()
        self.assertFalse(popup.winfo_exists())
        saved, = self.store.load()
        self.assertEqual(saved.weekly_shifts[0], WorkShift("8:00 AM", "3:51 PM"))
        self.assertEqual(self.page.income_estimate.jobs[0].hours, Decimal("39.25"))
        self.assertEqual(self.page._total_labels["take_home"].cget("text"), "$471.00")
        self.assertIn("8:00 AM – 3:51 PM", self.page._job_table._components[0][1].cget("text"))
        self.open_editor(saved)
        self.assertEqual(self.page._editor_values["starts"][0].get(), "8:00 AM")
        self.assertEqual(self.page._editor_values["ends"][0].get(), "3:51 PM")

    def test_incomplete_or_equal_shift_times_keep_the_editor_open_and_do_not_save(self):
        popup = self.open_editor()
        self.set_fields(hours=(8, 0, 0, 0, 0, 0, 0))
        self.page._editor_values["ends"][0].set("")
        self.page._save_job_button.invoke()
        self.assertTrue(popup.winfo_exists())
        self.assertIn("Monday", self.page._editor_error.cget("text"))
        self.assertIn("end time", self.page._editor_error.cget("text"))
        self.assertFalse(self.store.path.exists())
        self.page._editor_values["ends"][0].set("8 AM")
        self.page._save_job_button.invoke()
        self.assertIn("different", self.page._editor_error.cget("text"))
        self.assertFalse(self.store.path.exists())
        self.page._editor_values["working"][0].set(False)
        self.page._save_job_button.invoke()
        self.assertFalse(popup.winfo_exists())
        self.assertEqual(self.page.income_estimate.gross, 0)

    def test_unpaid_breaks_update_paid_hours_and_income_and_are_available_when_editing(self):
        popup = self.open_editor()
        self.set_fields(hours=(8, 0, 0, 0, 0, 0, 0))
        values = self.page._editor_values
        self.assertEqual(values["breaks"][0].get(), "0")
        self.assertEqual(str(self.page._shift_entries[1][2].cget("state")), "disabled")
        values["ends"][0].set("3:51 PM")
        values["breaks"][0].set("30")
        self.assertEqual(self.page._shift_hours_labels[0].cget("text"), "7.35 h")
        self.page._save_job_button.invoke()
        self.assertFalse(popup.winfo_exists())
        saved, = self.store.load()
        self.assertEqual(saved.weekly_shifts[0], WorkShift("8:00 AM", "3:51 PM", 30))
        self.assertEqual(self.page._total_labels["take_home"].cget("text"), "$441.00")
        schedule = self.page._job_table._components[0][1].cget("text")
        self.assertIn("30 min unpaid break", schedule)
        self.assertIn("7.35 paid hours / week", schedule)
        self.open_editor(saved)
        self.assertEqual(self.page._editor_values["breaks"][0].get(), "30")
        self.page._editor_values["breaks"][0].set("60")
        self.page._save_job_button.invoke()
        updated, = self.store.load()
        self.assertEqual(updated.weekly_shifts[0].unpaid_break_minutes, 60)
        self.assertEqual(updated.job_id, saved.job_id)
        self.assertEqual(self.page._total_labels["take_home"].cget("text"), "$411.00")

    def test_invalid_breaks_cannot_save_and_blank_or_days_off_mean_no_break(self):
        popup = self.open_editor()
        self.set_fields(hours=(8, 0, 0, 0, 0, 0, 0))
        values = self.page._editor_values
        for invalid in ("-1", "1.5", "lunch", "480", "481"):
            with self.subTest(invalid=invalid):
                values["breaks"][0].set(invalid)
                self.assertEqual(self.page._shift_hours_labels[0].cget("text"), "—")
                self.page._save_job_button.invoke()
                self.assertTrue(popup.winfo_exists())
                self.assertIn("Monday", self.page._editor_error.cget("text"))
                self.assertIn("unpaid break", self.page._editor_error.cget("text").lower())
                self.assertFalse(self.store.path.exists())
        values["breaks"][0].set(" ")
        values["breaks"][1].set("ignored while off")
        self.assertEqual(self.page._shift_hours_labels[0].cget("text"), "8 h")
        self.page._save_job_button.invoke()
        self.assertFalse(popup.winfo_exists())
        saved, = self.store.load()
        self.assertEqual(saved.weekly_shifts[0].unpaid_break_minutes, 0)
        self.assertIsNone(saved.weekly_shifts[1])
        self.assertEqual(self.page.income_estimate.jobs[0].hours, 40)

    def test_hours_only_jobs_are_preserved_until_the_user_saves_shift_times(self):
        existing = job()
        self.store.save([existing])
        original = self.store.path.read_bytes()
        self.page._reload_and_refresh()
        self.assertEqual(self.page.income_estimate.take_home, 2016)
        self.assertIn("Shift times not set", self.page._job_table._components[0][1].cget("text"))
        popup = self.open_editor(existing)
        self.assertTrue(self.page._editor_values["working"][0].get())
        self.assertEqual(self.page._editor_values["starts"][0].get(), "")
        self.assertIn("Saved hours are unchanged", self.page._editor_error.cget("text"))
        popup.destroy()
        self.assertEqual(self.store.path.read_bytes(), original)
        self.open_editor(existing)
        self.set_fields()
        self.page._save_job_button.invoke()
        updated, = self.store.load()
        self.assertEqual(updated.job_id, existing.job_id)
        self.assertEqual(updated.weekly_shifts[0], WorkShift("8 AM", "4 PM"))
        self.assertEqual(self.page.income_estimate.take_home, 2016)


class BudgetNavigationTests(unittest.TestCase):
    def test_completing_the_expense_branch_advances_to_budget_planning(self):
        expense_step = Mock()
        budget_step = Mock()
        root = SimpleNamespace(_pages=[expense_step, budget_step], _page_index=0)
        final_review = Mock()
        branch = SimpleNamespace(_pages=[final_review], _page_index=0,
                                 _parent_next_method=lambda: PageContainer.next_page(root))
        PageContainer.next_page(branch)
        final_review.deactivate.assert_called_once()
        expense_step.deactivate.assert_called_once()
        budget_step.activate.assert_called_once()
        self.assertEqual(root._page_index, 1)


if __name__ == "__main__":
    unittest.main()
