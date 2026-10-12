from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from classes.budget_job_class import BudgetJob
from classes.daily_use_item_class import DailyUseItem, validate_daily_use
from classes.food_consumption_class import FoodConsumption
from classes.grocery_catalog_item_class import GroceryCatalogItem
from classes.grocery_unit_class import GroceryUnit
from classes.managers.budget_jobs_manager import BudgetJobsManager
from classes.managers.daily_use_manager import DailyUseManager
from classes.managers.day_off_foods_manager import DayOffFoodsManager
from classes.managers.grocery_catalog_manager import GroceryCatalogManager
from classes.managers.prepared_foods_manager import PreparedFoodsManager
from classes.pages.child_pages.budget_planning_page_class import BudgetPlanningPage
from classes.pages.child_pages.budget_planning_pages.daily_use_page import DailyUsePage, _CASE, _MONTHLY, _QUANTITY
from classes.prepared_food_class import PreparedFood


class DailyUsePersistenceTests(unittest.TestCase):
    def setUp(self):
        directory = Path(__file__).resolve().parent / "__pycache__"
        directory.mkdir(exist_ok=True)
        self.workspace = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="daily-use-", dir=directory)))
        self.store = DailyUseManager(self.workspace / "daily_use.json")
        self.food = PreparedFood("Lunch", (FoodConsumption(1, 1),))

    def test_valid_quantities_lifespans_and_food_references_round_trip(self):
        entries = (DailyUseItem(1, "0.5"), DailyUseItem(2, case_days="30"), DailyUseItem(None, "1.25", self.food.food_id))
        self.assertEqual(self.store.load(), ())
        self.store.save(entries)
        self.assertEqual(DailyUseManager(self.store.path).load(), entries)
        self.assertEqual(tuple(DailyUseItem.from_dict(item.to_dict()) for item in entries), entries)
        self.store.save(())
        self.assertEqual(self.store.load(), ())

    def test_invalid_ambiguous_and_duplicate_entries_are_rejected(self):
        for fields in ({"quantity": 1, "case_days": 30}, {}, {"quantity": "NaN"}, {"case_days": "sNaN"},
                       {"quantity": 0}, {"case_days": -1}, {"case_days": "Infinity"}, {"quantity": True},
                       {"case_days": "abc"}, {"quantity": ""}, {"quantity": 1, "food_id": self.food.food_id}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                DailyUseItem(1, **fields)
        with self.assertRaisesRegex(ValueError, "Case lifespan"):
            DailyUseItem(None, food_id=self.food.food_id, case_days=30)
        for record in (None, [], {}, {"grocery_item_id": 0, "quantity": 1}):
            with self.subTest(record=record), self.assertRaises(ValueError):
                DailyUseItem.from_dict(record)
        for items in (None, [None], [DailyUseItem(1, 1), DailyUseItem(1, case_days=30)]):
            with self.subTest(items=items), self.assertRaises(ValueError):
                validate_daily_use(items)

    def test_case_lifespan_uses_current_case_size_and_does_not_store_a_rounded_daily_amount(self):
        entry = DailyUseItem(1, case_days=30)
        grocery = GroceryCatalogItem(1, "Drink", "9.99", 12)
        self.assertEqual(entry.daily_consumption(grocery), FoodConsumption(1, "0.4"))
        self.assertEqual(entry.daily_consumption(replace(grocery, units_per_case=30)), FoodConsumption(1, 1))
        self.assertEqual(entry.to_dict(), {"grocery_item_id": 1, "case_days": "30"})
        recurring = DailyUseItem(1, case_days=3).daily_consumption(replace(grocery, units_per_case=1)).quantity
        self.assertEqual(recurring, Decimal(1) / Decimal(3))
        for item in (None, replace(grocery, item_id=2)):
            with self.subTest(item=item), self.assertRaises(ValueError):
                entry.daily_consumption(item)
        self.assertEqual(DailyUseItem(None, "0.5", self.food.food_id).daily_consumption(), FoodConsumption(None, "0.5", self.food.food_id))

    def test_corrupt_data_and_failed_atomic_saves_preserve_the_saved_baseline(self):
        self.store.save((DailyUseItem(1, "0.5"),))
        original = self.store.path.read_bytes()
        with patch("classes.managers.daily_use_manager.os.replace", side_effect=OSError("Disk full")), self.assertRaises(OSError):
            self.store.save(())
        self.assertEqual(self.store.path.read_bytes(), original)
        self.assertEqual(list(self.workspace.iterdir()), [self.store.path])
        for contents in ("bad JSON", "[]", '{"version":2,"items":[]}', '{"version":1,"items":null}',
                         '{"version":1,"items":[{}]}', '{"version":1,"items":[{"grocery_item_id":1,"quantity":"NaN"}]}'):
            with self.subTest(contents=contents):
                self.store.path.write_text(contents, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Could not read Daily Use"):
                    self.store.load()
                self.assertEqual(self.store.path.read_text(encoding="utf-8"), contents)

    def test_daily_baseline_persists_independently_of_shift_and_day_off_extras(self):
        baseline = (DailyUseItem(1, 1),)
        self.store.save(baseline)
        jobs = BudgetJobsManager(self.workspace / "jobs.json")
        day_off = DayOffFoodsManager(self.workspace / "day_off.json")
        job = BudgetJob("Job", 15, 20, (8,) * 5 + (0, 0), foods_per_shift=(FoodConsumption(1, 2),))
        jobs.save([job]); day_off.save((FoodConsumption(1, "0.5"),))
        self.store.save((DailyUseItem(1, case_days=30),))
        self.assertEqual(jobs.load(), [job])
        self.assertEqual(day_off.load(), (FoodConsumption(1, "0.5"),))
        jobs.save([]); day_off.save(())
        self.assertEqual(self.store.load(), (DailyUseItem(1, case_days=30),))

    def test_monthly_quantities_remain_exact_when_saved_and_existing_daily_records_are_preserved(self):
        daily, case = DailyUseItem(1, "0.5"), DailyUseItem(2, case_days=30)
        self.store.save((daily, case))
        original = self.store.path.read_bytes()
        self.assertEqual(self.store.load(), (daily, case))
        self.assertEqual(self.store.path.read_bytes(), original)
        monthly = DailyUseItem(None, food_id=self.food.food_id, monthly_quantity="1.25")
        self.store.save((daily, case, monthly))
        self.assertEqual(DailyUseManager(self.store.path).load(), (daily, case, monthly))
        self.assertEqual(monthly.to_dict(), {"food_id": self.food.food_id, "monthly_quantity": "1.25"})
        self.assertEqual(DailyUseItem.from_dict(monthly.to_dict()), monthly)

    def test_monthly_daily_equivalents_use_actual_calendar_days_including_leap_years(self):
        for month, days in ((date(2027, 2, 1), 28), (date(2028, 2, 1), 29),
                            (date(2026, 11, 1), 30), (date(2027, 1, 1), 31)):
            with self.subTest(month=month):
                entry = DailyUseItem(1, monthly_quantity=days)
                self.assertEqual(entry.daily_consumption(month=month), FoodConsumption(1, 1))
        entry = DailyUseItem(None, food_id=self.food.food_id, monthly_quantity="0.5")
        self.assertEqual(entry.daily_consumption(month=date(2028, 2, 1)).quantity, Decimal("0.5") / 29)
        with self.assertRaisesRegex(ValueError, "budget month"):
            entry.daily_consumption()

    def test_invalid_ambiguous_and_duplicate_monthly_quantities_cannot_replace_saved_data(self):
        for quantity in ("", 0, -1, "NaN", "sNaN", "Infinity", True, "abc"):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                DailyUseItem(1, monthly_quantity=quantity)
        for fields in ({"quantity": 1, "monthly_quantity": 30}, {"case_days": 30, "monthly_quantity": 1}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                DailyUseItem(1, **fields)
        self.store.save((DailyUseItem(1, 1),))
        original = self.store.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "already in Daily Use"):
            self.store.save((DailyUseItem(1, 1), DailyUseItem(1, monthly_quantity=30)))
        self.assertEqual(self.store.path.read_bytes(), original)


class DailyUsePageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as error:
            raise unittest.SkipTest(f"Tk unavailable: {error}")
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        directory = Path(__file__).resolve().parent / "__pycache__"
        directory.mkdir(exist_ok=True)
        self.workspace = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="daily-use-ui-", dir=directory)))
        self.catalog = GroceryCatalogManager(self.workspace / "groceries.csv")
        self.unit = GroceryUnit("Can")
        self.catalog.units_manager.save([self.unit])
        self.groceries = [GroceryCatalogItem(1, "Soup", "12.99", 12, unit_id=self.unit.unit_id),
                          GroceryCatalogItem(2, "Toothpaste", "4.99", 1)]
        self.catalog.save(self.groceries)
        self.foods = PreparedFoodsManager(self.workspace / "foods.json")
        self.food = PreparedFood("Lunch", (FoodConsumption(1, 1),))
        self.foods.save([self.food])
        self.daily = DailyUseManager(self.workspace / "daily_use.json")
        self.next_page, self.back = Mock(), Mock()
        self.page = DailyUsePage(self.root, self.next_page, self.back, self.catalog, self.foods, self.daily,
                                 today=lambda: date(2026, 10, 8))

    def tearDown(self):
        self.page._root.destroy()

    def choose(self, identifier, amount, mode=_QUANTITY):
        self.page._item_value.set(next(label for label, value in self.page._choices.items() if value == identifier))
        self.page._mode_value.set(mode)
        self.page._amount_value.set(str(amount))

    def add(self, identifier, amount, mode=_QUANTITY):
        self.choose(identifier, amount, mode)
        self.page._save_item_button.invoke()

    def test_add_edit_remove_and_restart_keep_daily_quantities_and_grocery_units(self):
        catalog_before = self.catalog.path.read_bytes()
        foods_before = self.foods.path.read_bytes()
        self.add(1, "0.5")
        self.add(self.food.food_id, 1)
        self.assertEqual(self.daily.load(), (DailyUseItem(1, "0.5"), DailyUseItem(None, 1, self.food.food_id)))
        rows = self.page._usage_table._components
        self.assertEqual((rows[0][2].cget("text"), rows[0][3].cget("text")), ("0.5", "Cans"))
        self.assertEqual(rows[1][3].cget("text"), "Serving")
        rows[0][4].winfo_children()[0].invoke()
        self.page._amount_value.set("1")
        self.page._save_item_button.invoke()
        self.assertEqual(self.page._usage_table._components[0][3].cget("text"), "Can")
        self.page._usage_table._components[1][4].winfo_children()[1].invoke()
        self.assertEqual(self.daily.load(), (DailyUseItem(1, 1),))
        restarted = DailyUsePage(self.root, Mock(), Mock(), self.catalog, self.foods, DailyUseManager(self.daily.path))
        self.addCleanup(restarted._root.destroy)
        self.assertEqual(restarted.items, (DailyUseItem(1, 1),))
        self.assertEqual(self.catalog.path.read_bytes(), catalog_before)
        self.assertEqual(self.foods.path.read_bytes(), foods_before)

    def test_case_duration_is_restored_on_edit_and_tracks_case_size_changes(self):
        self.add(1, 30, _CASE)
        self.assertEqual(self.daily.load(), (DailyUseItem(1, case_days=30),))
        row = self.page._usage_table._components[0]
        self.assertEqual((row[1].cget("text"), row[2].cget("text"), row[3].cget("text")), ("One case / 30 days", "0.4", "Cans"))
        self.page._edit_item(self.page.items[0])
        self.assertEqual((self.page._mode_value.get(), self.page._amount_value.get()), (_CASE, "30"))
        self.assertIn("12 Cans", self.page._preview_label.cget("text"))
        self.catalog.save([replace(self.groceries[0], name="New Soup", units_per_case=30), self.groceries[1]])
        self.page._reload_and_refresh()
        row = self.page._usage_table._components[0]
        self.assertEqual((row[0].cget("text"), row[2].cget("text"), row[3].cget("text")), ("New Soup", "1", "Can"))
        self.assertEqual(self.daily.load()[0].case_days, 30)
        self.page._mode_value.set(_QUANTITY)
        self.page._amount_value.set("0.25")
        self.page._save_item_button.invoke()
        self.assertEqual(self.daily.load(), (DailyUseItem(1, "0.25"),))

    def test_repeating_case_divisions_are_readable_and_keep_the_exact_duration(self):
        self.add(2, 30, _CASE)
        row = self.page._usage_table._components[0]
        self.assertEqual(row[2].cget("text"), "≈ 0.0333333")
        self.assertEqual(self.daily.load()[0].case_days, 30)
        self.assertNotIn("quantity", self.daily.load()[0].to_dict())

    def test_cancel_and_invalid_or_duplicate_inputs_do_not_modify_saved_entries(self):
        self.add(1, 1)
        original = self.daily.path.read_bytes()
        self.page._edit_item(self.page.items[0])
        self.page._amount_value.set("9")
        self.page._cancel_edit_button.invoke()
        self.assertEqual(self.daily.path.read_bytes(), original)
        for mode in (_QUANTITY, _CASE):
            for amount in ("", "0", "-1", "NaN", "sNaN", "Infinity", "abc"):
                with self.subTest(mode=mode, amount=amount):
                    self.choose(2, amount, mode)
                    self.page._save_item_button.invoke()
                    self.assertEqual(self.daily.path.read_bytes(), original)
        self.page._item_value.set(next(label for label, identifier in self.page._all_choices.items() if identifier == 1))
        self.page._mode_value.set(_CASE)
        self.page._amount_value.set("30")
        self.assertFalse(self.page._save_item())
        self.assertIn("Choose an available", self.page._status.cget("text"))
        self.assertEqual(self.daily.path.read_bytes(), original)

    def test_foods_use_servings_and_cannot_be_entered_as_a_grocery_case(self):
        self.choose(self.food.food_id, "0.5")
        self.assertEqual(self.page._mode_dropdown.cget("values"), (_QUANTITY, _MONTHLY))
        self.assertIn("0.5 Servings", self.page._preview_label.cget("text"))
        self.page._mode_value.set(_CASE)
        self.assertEqual(self.page._mode_value.get(), _QUANTITY)
        self.page._save_item_button.invoke()
        self.assertFalse(self.daily.path.exists())
        self.page._amount_value.set("0.5")
        self.page._save_item_button.invoke()
        self.foods.save([replace(self.food, name="Dinner")])
        self.page._reload_and_refresh()
        self.assertEqual(self.page._usage_table._components[0][0].cget("text"), "Dinner")
        self.assertEqual(self.daily.load()[0].food_id, self.food.food_id)

    def test_unavailable_groceries_and_foods_remain_visible_and_can_be_replaced_or_removed(self):
        self.add(1, 30, _CASE)
        self.add(self.food.food_id, 1)
        self.catalog.save([self.groceries[1]])
        self.foods.save([])
        self.page._reload_and_refresh()
        rows = self.page._usage_table._components
        self.assertIn("Unavailable grocery", rows[0][0].cget("text"))
        self.assertEqual(rows[0][2].cget("text"), "—")
        self.assertEqual(rows[1][0].cget("text"), "Unavailable food")
        self.page._edit_item(self.page.items[0])
        self.choose(2, 60, _CASE)
        self.page._save_item_button.invoke()
        self.assertEqual(self.daily.load()[0], DailyUseItem(2, case_days=60))
        self.page._remove_item(self.page.items[1])
        self.assertEqual(self.daily.load(), (DailyUseItem(2, case_days=60),))

    def test_failed_save_or_remove_keeps_saved_items_and_can_be_retried(self):
        self.add(1, 1)
        original = self.daily.path.read_bytes()
        self.choose(2, 30, _CASE)
        with patch.object(self.daily, "save", side_effect=OSError("Disk full")):
            self.page._save_item_button.invoke()
            self.page._remove_item(self.page.items[0])
        self.assertEqual(self.daily.path.read_bytes(), original)
        self.assertIn("Disk full", self.page._status.cget("text"))
        self.page._save_item_button.invoke()
        self.assertEqual(self.daily.load(), (DailyUseItem(1, 1), DailyUseItem(2, case_days=30)))

    def test_corrupt_saved_plan_or_catalogue_blocks_edits_without_rewriting_the_data(self):
        self.add(1, 1)
        self.daily.path.write_text("bad JSON", encoding="utf-8")
        self.page._reload_and_refresh()
        self.assertIn("Could not read Daily Use", self.page._status.cget("text"))
        self.assertFalse(self.page._save_item())
        self.assertEqual(self.daily.path.read_text(encoding="utf-8"), "bad JSON")
        self.daily.save((DailyUseItem(1, 1),))
        self.catalog.path.write_text("bad CSV", encoding="utf-8")
        self.page._reload_and_refresh()
        self.assertIn("Could not read grocery items", self.page._status.cget("text"))
        self.assertEqual(str(self.page._save_item_button.cget("state")), "disabled")
        self.catalog.save(self.groceries)
        self.page._reload_and_refresh()
        self.choose(2, 1)
        self.assertEqual(str(self.page._save_item_button.cget("state")), "normal")

    def test_continue_saves_valid_input_blocks_invalid_input_and_allows_an_empty_plan(self):
        self.choose(1, 0)
        self.page._continue_button.invoke()
        self.next_page.assert_not_called()
        self.page._amount_value.set("0.5")
        self.page._continue_button.invoke()
        self.next_page.assert_called_once_with()
        self.assertEqual(self.daily.load(), (DailyUseItem(1, "0.5"),))
        self.next_page.reset_mock()
        self.page._remove_item(self.page.items[0])
        self.page._continue_button.invoke()
        self.next_page.assert_called_once_with()
        self.page._back_button.invoke()
        self.back.assert_called_once_with()

    def test_budget_navigation_includes_daily_use_and_keeps_existing_income_and_budget_values(self):
        with patch("classes.managers.grocery_catalog_manager._GROCERIES_PATH", self.catalog.path), \
                patch("classes.managers.prepared_foods_manager._FOODS_PATH", self.foods.path), \
                patch("classes.managers.daily_use_manager._DAILY_USE_PATH", self.daily.path), \
                patch("classes.managers.budget_jobs_manager._JOBS_PATH", self.workspace / "jobs.json"), \
                patch("classes.pages.child_pages.budget_planning_pages.grocery_prices_page._DOWNLOADS_PATH", self.workspace / "downloads"):
            budget = BudgetPlanningPage(self.root, Mock())
        self.addCleanup(budget._root.destroy)
        original = budget.budget_summary
        budget._grocery_page._continue_button.invoke()
        budget._grocery_prices_page._continue_button.invoke()
        budget._foods_page._continue_button.invoke()
        self.assertEqual(budget._page_index, 2)
        self.assertIs(budget._pages[2], budget._daily_use_page)
        self.assertIs(budget._daily_use_page._foods_manager, budget._foods_page._foods_manager)
        self.daily.save((DailyUseItem(1, 1),))
        budget._daily_use_page.activate()
        self.assertEqual(budget.daily_use_plan, (DailyUseItem(1, 1),))
        budget._daily_use_page._continue_button.invoke()
        self.assertEqual(budget._page_index, 3)
        budget._income_page._back_button.invoke()
        self.assertEqual(budget._page_index, 2)
        budget._daily_use_page._back_button.invoke()
        self.assertEqual(budget._page_index, 1)
        budget._foods_page._continue_button.invoke()
        budget._daily_use_page._continue_button.invoke()
        budget._income_page._continue_button.invoke()
        self.assertEqual(budget._page_index, 4)
        self.assertEqual(budget.budget_summary, original)

    def test_monthly_groceries_and_foods_save_edit_switch_modes_and_reload(self):
        self.add(1, 12, _MONTHLY)
        self.add(self.food.food_id, "0.5", _MONTHLY)
        expected = (DailyUseItem(1, monthly_quantity=12), DailyUseItem(None, food_id=self.food.food_id, monthly_quantity="0.5"))
        self.assertEqual(self.daily.load(), expected)
        row = self.page._usage_table._components[0]
        self.assertEqual((row[1].cget("text"), row[2].cget("text"), row[3].cget("text")), ("12 per month", "0.4", "Cans"))
        restarted = DailyUsePage(self.root, Mock(), Mock(), self.catalog, self.foods, self.daily,
                                 today=lambda: date(2026, 10, 8))
        self.addCleanup(restarted._root.destroy)
        self.assertEqual(restarted.items, expected)
        self.page._edit_item(self.page.items[1])
        self.assertEqual((self.page._mode_value.get(), self.page._amount_value.get()), (_MONTHLY, "0.5"))
        self.assertEqual(self.page._amount_label.cget("text"), "Quantity / month")
        self.assertIn("0.5 Servings per month", self.page._preview_label.cget("text"))
        self.page._amount_value.set("30")
        self.page._save_item_button.invoke()
        self.assertEqual(self.page._usage_table._components[1][3].cget("text"), "Serving")
        self.page._edit_item(self.page.items[1])
        self.page._mode_value.set(_QUANTITY)
        self.page._amount_value.set("0.25")
        self.page._save_item_button.invoke()
        self.assertEqual(self.daily.load()[1], DailyUseItem(None, "0.25", self.food.food_id))

    def test_monthly_equivalents_refresh_for_next_month_without_changing_the_saved_amount(self):
        self.add(1, 28, _MONTHLY)
        original = self.daily.path.read_bytes()
        for today, month, days in ((date(2027, 1, 15), "February 2027", 28),
                                  (date(2028, 1, 15), "February 2028", 29),
                                  (date(2027, 12, 15), "January 2028", 31)):
            with self.subTest(today=today):
                self.page._today = lambda value=today: value
                self.page.activate()
                self.assertIn(f"{month} · {days} days", self.page._month_label.cget("text"))
                amount = self.page._usage_table._components[0][2].cget("text").removeprefix("≈ ")
                self.assertAlmostEqual(Decimal(amount), Decimal(28) / days, places=5)
                self.assertEqual(self.daily.path.read_bytes(), original)

    def test_daily_picker_filters_all_usage_modes_and_restores_items_after_cancel_replace_and_remove(self):
        self.add(1, "0.5")
        self.add(self.food.food_id, 12, _MONTHLY)
        self.add(2, 30, _CASE)
        self.assertEqual(tuple(self.page._item_dropdown.cget("values")), ())
        self.assertEqual(str(self.page._item_dropdown.cget("state")), "disabled")
        self.assertIn("All available items", self.page._preview_label.cget("text"))
        self.page._edit_item(self.page.items[1])
        self.assertEqual(set(self.page._choices.values()), {self.food.food_id})
        self.assertEqual(self.page._mode_value.get(), _MONTHLY)
        self.page._cancel_edit_button.invoke()
        self.assertEqual(self.page._choices, {})
        self.page._remove_item(self.page.items[2])
        self.assertEqual(set(self.page._choices.values()), {2})
        self.page._edit_item(self.page.items[0])
        self.assertEqual(set(self.page._choices.values()), {1, 2})
        self.choose(2, 30, _CASE)
        self.page._save_item_button.invoke()
        self.assertEqual(set(self.page._choices.values()), {1})
        self.page._reload_and_refresh()
        self.assertEqual(set(self.page._choices.values()), {1})

    def test_daily_picker_keeps_the_edited_item_selected_when_catalogue_labels_change(self):
        self.add(1, 12, _MONTHLY)
        self.page._edit_item(self.page.items[0])
        self.catalog.save([replace(self.groceries[0], name="Renamed Soup"), self.groceries[1]])
        self.page._reload_and_refresh()
        self.assertIn("Renamed Soup", self.page._item_value.get())
        self.assertEqual(set(self.page._choices.values()), {1, 2, self.food.food_id})
        self.page._cancel_edit_button.invoke()
        self.assertEqual(set(self.page._choices.values()), {2, self.food.food_id})


if __name__ == "__main__":
    unittest.main()
