import tempfile
import tkinter as tk
import unittest
from datetime import date
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from unittest.mock import Mock, patch

from classes.budget_job_class import BudgetJob
from classes.managers import option_manager
from classes.managers import budget_category_manager
from classes.managers.budget_category_manager import BudgetCategoryManager
from classes.managers.budget_jobs_manager import BudgetJobsManager
from classes.managers.budget_summary_manager import BudgetExpense, BudgetSummaryManager
from classes.managers.income_estimation_manager import IncomeEstimationManager
from classes.managers.option_manager import OptionManager
from classes.pages.child_pages.budget_planning_page_class import BudgetPlanningPage
from classes.pages.child_pages.budget_planning_pages.overall_budget_page import OverallBudgetPage
from classes.work_shift_class import WorkShift
from enums.budget.categories_enum import BudgetCategories as Categories
from enums.finances.categories_enum import Categories as ExpenseCategories


def scheduled_job(wage="15"):
    return BudgetJob("Main job", wage, "20", (0,) * 7,
                     weekly_shifts=(WorkShift("8 AM", "4 PM"),) * 5 + (None, None))


class BudgetSummaryTests(unittest.TestCase):
    def setUp(self):
        self.income = IncomeEstimationManager.estimate([scheduled_job()], date(2026, 10, 7))

    def test_subcategories_combine_into_categories_and_reduce_take_home_budget(self):
        summary = BudgetSummaryManager.summarize(self.income, [
            BudgetExpense(Categories.CAR, "Fuel", "25.75"),
            BudgetExpense(Categories.CAR, "Maintenance", "30"),
            BudgetExpense(Categories.HOUSING, "Rent", "900"),
            BudgetExpense(Categories.HOUSING, "Utilities", "20")])
        totals = {total.category: total.amount for total in summary.categories}
        self.assertEqual(summary.month, date(2026, 11, 1))
        self.assertEqual(summary.total_budget, Decimal("2016.00"))
        self.assertEqual(totals[Categories.CAR], Decimal("55.75"))
        self.assertEqual(totals[Categories.HOUSING], Decimal("920"))
        self.assertEqual(totals[Categories.SHOPPING], 0)
        self.assertEqual(summary.total_expenses, Decimal("975.75"))
        self.assertEqual(summary.remaining_budget, Decimal("1040.25"))

    def test_no_expenses_exact_budget_and_overspending_preserve_cent_precision(self):
        empty = BudgetSummaryManager.summarize(self.income, [])
        self.assertEqual(empty.total_expenses, 0)
        self.assertEqual(empty.remaining_budget, self.income.take_home)
        for amount, remaining in (("2016", "0.00"), ("2016.01", "-0.01")):
            with self.subTest(amount=amount):
                summary = BudgetSummaryManager.summarize(self.income, [BudgetExpense(Categories.HOUSING, "Rent", amount)])
                self.assertEqual(summary.remaining_budget, Decimal(remaining))
        cents = BudgetSummaryManager.summarize(self.income, [
            BudgetExpense(Categories.CAR, "Fuel", "0.10"), BudgetExpense(Categories.CAR, "Maintenance", "0.20")])
        self.assertEqual(cents.total_expenses, Decimal("0.30"))

    def test_expenses_still_count_when_their_category_is_missing_from_available_choices(self):
        summary = BudgetSummaryManager.summarize(self.income, [BudgetExpense(Categories.SHOPPING, "Food", "100")],
                                                categories=[Categories.CAR])
        self.assertEqual([total.category for total in summary.categories], [Categories.CAR, Categories.SHOPPING])
        self.assertEqual(summary.total_expenses, 100)
        self.assertEqual(summary.remaining_budget, 1916)

    def test_invalid_planned_expenses_are_rejected(self):
        for amount in ("", "NaN", "Infinity", "-1", "1.234", None):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                BudgetExpense(Categories.CAR, "Fuel", amount)
        for category, subcategory in (("Unknown", "Fuel"), (Categories.CAR, ""), (Categories.CAR, None)):
            with self.subTest(category=category, subcategory=subcategory), self.assertRaises(ValueError):
                BudgetExpense(category, subcategory, "10")
        with self.assertRaises(ValueError):
            BudgetSummaryManager.summarize(self.income, [object()])

    def test_expense_review_categories_are_rejected_even_when_their_names_match(self):
        self.assertEqual(Categories.CAR.value, ExpenseCategories.CAR.value)
        with self.assertRaisesRegex(ValueError, "budget planning category"):
            BudgetExpense(ExpenseCategories.CAR, "Fuel", "10")
        with self.assertRaisesRegex(ValueError, "budget planning categories"):
            BudgetSummaryManager.summarize(self.income, [], categories=ExpenseCategories)
        self.assertIs(BudgetExpense("Car", "Fuel", "10").category, Categories.CAR)


class OverallBudgetPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as error:
            raise unittest.SkipTest(f"Tk is unavailable: {error}")
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.workspace = Path(self.enterContext(tempfile.TemporaryDirectory(
            prefix="budget-summary-", dir=Path(__file__).resolve().parent)))
        self.enterContext(patch.object(option_manager, "_OPTIONS_PATH", self.workspace / "options.json"))
        self.enterContext(patch.object(OptionManager, "_loaded_path", None))
        self.enterContext(patch.object(OptionManager, "_preferences", {}))
        self.enterContext(patch.object(OptionManager, "_listeners", set()))
        self.enterContext(patch("classes.pages.child_pages.budget_planning_pages.grocery_prices_page._DOWNLOADS_PATH",
                                self.workspace / "downloads"))
        self.store = BudgetJobsManager(self.workspace / "jobs.json")
        self.store.save([scheduled_job()])
        self.completed = Mock()
        with patch("classes.managers.budget_jobs_manager._JOBS_PATH", self.store.path), \
                patch("classes.managers.grocery_catalog_manager._GROCERIES_PATH", self.workspace / "groceries.csv"):
            self.budget = BudgetPlanningPage(self.root, self.completed)
        self.income = self.budget._income_page
        self.overall = self.budget._overall_page
        self.income._today = lambda: date(2026, 10, 7)
        self.budget.activate()

    def tearDown(self):
        self.budget._root.destroy()

    def show_overall(self):
        if self.budget._page_index == 0:
            self.budget._grocery_page._continue_button.invoke()
            self.budget._grocery_prices_page._continue_button.invoke()
        if self.budget._page_index == 1:
            self.budget._foods_page._continue_button.invoke()
        if self.budget._page_index == 2:
            self.budget._daily_use_page._continue_button.invoke()
        self.income._continue_button.invoke()

    def test_navigation_carries_current_income_and_preserves_expenses_after_editing_jobs(self):
        self.assertIsInstance(self.budget._pages[4], OverallBudgetPage)
        self.budget.set_planned_expenses([BudgetExpense(Categories.CAR, "Fuel", "100")])
        self.show_overall()
        self.assertEqual(self.budget._page_index, 4)
        self.assertEqual(self.overall._month_label.cget("text"), "November 2026")
        self.assertEqual(self.overall._budget_label.cget("text"), "$2,016.00")
        self.assertEqual(self.overall._remaining_label.cget("text"), "$1,916.00")
        self.assertEqual(self.overall._category_cells[Categories.CAR][1].cget("text"), "$100.00")
        self.completed.assert_not_called()

        self.overall._edit_income_button.invoke()
        self.assertEqual(self.budget._page_index, 3)
        popup = self.income._show_job_editor(self.income._jobs[0])
        popup.withdraw()
        self.income._editor_values["wage"].set("20")
        self.income._save_job_button.invoke()
        self.assertFalse(popup.winfo_exists())
        self.show_overall()
        self.assertEqual(self.overall._budget_label.cget("text"), "$2,688.00")
        self.assertEqual(self.overall._remaining_label.cget("text"), "$2,588.00")
        self.assertEqual(self.budget.budget_summary.total_expenses, 100)
        self.assertEqual(self.store.load()[0].hourly_wage, 20)

        self.overall._edit_income_button.invoke()
        self.income._today = lambda: date(2026, 12, 31)
        self.income.activate()
        self.show_overall()
        self.assertEqual(self.overall._month_label.cget("text"), "January 2027")

    def test_zero_expenses_and_overspending_update_display_without_discarding_invalid_changes(self):
        self.show_overall()
        self.assertEqual(self.overall._remaining_label.cget("text"), "$2,016.00")
        self.assertEqual(self.overall._expenses_label.cget("text"), "Total planned expenses: $0.00")
        self.assertEqual(len(self.overall._category_cells), len(Categories))
        self.assertTrue(all(cost.cget("text") == "$0.00" for _, cost in self.overall._category_cells.values()))
        expenses = [BudgetExpense(Categories.HOUSING, "Rent", "2016.01")]
        self.budget.set_planned_expenses(expenses)
        self.assertEqual(self.overall._remaining_label.cget("text"), "-$0.01")
        self.assertEqual(self.overall._remaining_label.cget("fg"), "#BE123C")
        self.assertEqual(self.overall._expenses_label.cget("text"), "Total planned expenses: $2,016.01")
        with self.assertRaises(ValueError):
            self.budget.set_planned_expenses([object()])
        self.assertEqual(self.budget.planned_expenses, tuple(expenses))
        self.assertEqual(self.overall.summary.total_expenses, Decimal("2016.01"))
        self.budget.set_planned_expenses([])
        self.assertEqual(self.overall._remaining_label.cget("text"), "$2,016.00")
        self.assertEqual(self.overall._remaining_label.cget("fg"), "#15803D")

    def test_category_labels_colors_and_visibility_follow_saved_preferences_without_losing_expenses(self):
        self.budget.set_planned_expenses([BudgetExpense(Categories.SHOPPING, "Food", "80")])
        self.show_overall()
        OptionManager.rename(Categories.SHOPPING, "Everyday Shopping", Categories)
        OptionManager.set_color(Categories.SHOPPING, "#BBCCDD")
        category, cost = self.overall._category_cells[Categories.SHOPPING]
        self.assertEqual(category.cget("text"), "Everyday Shopping")
        self.assertEqual(category.cget("bg"), "#BBCCDD")
        self.assertEqual(cost.cget("text"), "$80.00")
        OptionManager.delete(Categories.HOUSING)
        self.assertNotIn(Categories.HOUSING, self.overall._category_cells)
        OptionManager.delete(Categories.SHOPPING)
        self.assertIn(Categories.SHOPPING, self.overall._category_cells)
        self.assertEqual(self.overall._remaining_label.cget("text"), "$1,936.00")

    def test_budget_categories_and_preferences_are_independent_of_expense_review(self):
        self.show_overall()
        initial_budget_color = self.overall._category_cells[Categories.SHOPPING][0].cget("bg")
        OptionManager.rename(ExpenseCategories.SHOPPING, "Expense Shopping", ExpenseCategories)
        OptionManager.set_color(ExpenseCategories.SHOPPING, "#334455")
        OptionManager.delete(ExpenseCategories.HOUSING)
        budget_shopping = self.overall._category_cells[Categories.SHOPPING][0]
        self.assertEqual(budget_shopping.cget("text"), "Shopping")
        self.assertEqual(budget_shopping.cget("bg"), initial_budget_color)
        self.assertIn(Categories.HOUSING, self.overall._category_cells)
        self.assertNotIn(ExpenseCategories.BANK.value, [category.value for category in self.overall._category_cells])

        OptionManager.rename(Categories.SHOPPING, "Budget Shopping", Categories)
        OptionManager.set_color(Categories.SHOPPING, "#BBCCDD")
        OptionManager.delete(Categories.CAR)
        self.assertEqual(OptionManager.display(ExpenseCategories.SHOPPING), "Expense Shopping")
        self.assertEqual(OptionManager.colors(ExpenseCategories.SHOPPING)[0], "#334455")
        self.assertIn(ExpenseCategories.CAR, OptionManager.available(ExpenseCategories))
        self.assertNotIn(Categories.CAR, self.overall._category_cells)
        self.assertEqual(self.overall._category_cells[Categories.SHOPPING][0].cget("text"), "Budget Shopping")
        self.assertEqual(self.overall._category_cells[Categories.SHOPPING][0].cget("bg"), "#BBCCDD")

    def test_creating_a_budget_category_saves_to_its_own_enum_even_when_review_has_the_same_name(self):
        class TestBudgetCategories(StrEnum):
            CAR = "Car"

        source_path = self.workspace / "budget_categories.py"
        source_path.write_text('from enum import StrEnum\n\nclass TestBudgetCategories(StrEnum):\n    CAR = "Car"\n',
                               encoding="utf-8")
        original_review_members = list(ExpenseCategories)
        original_review_colors = OptionManager.colors(ExpenseCategories.BANK)
        with patch.object(budget_category_manager, "BudgetCategories", TestBudgetCategories), \
                patch.object(budget_category_manager, "_BUDGET_CATEGORIES_ENUM_PATH", source_path), \
                patch.object(OptionManager, "_listeners", set()):
            created = BudgetCategoryManager.create("Bank")
            self.assertIsInstance(created, TestBudgetCategories)
            self.assertIsNot(created, ExpenseCategories.BANK)
            self.assertIn(created, BudgetCategoryManager.choices())
            self.assertIs(BudgetCategoryManager.create("Bank"), created)
            namespace = {}
            exec(source_path.read_text(encoding="utf-8"), namespace)
            self.assertEqual(namespace["TestBudgetCategories"].BANK.value, "Bank")
        self.assertEqual(list(ExpenseCategories), original_review_members)
        self.assertEqual(OptionManager.colors(ExpenseCategories.BANK), original_review_colors)


if __name__ == "__main__":
    unittest.main()
