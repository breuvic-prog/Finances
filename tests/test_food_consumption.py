from dataclasses import replace
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from classes.budget_job_class import BudgetJob
from classes.custom_tk_components import tk_food_plan_editor
from classes.food_consumption_class import FoodConsumption, validate_food_plan
from classes.grocery_catalog_item_class import GroceryCatalogItem
from classes.grocery_unit_class import GroceryUnit
from classes.managers.budget_jobs_manager import BudgetJobsManager
from classes.managers.day_off_foods_manager import DayOffFoodsManager
from classes.managers.grocery_catalog_manager import GroceryCatalogManager
from classes.managers.prepared_foods_manager import PreparedFoodsManager
from classes.managers.income_estimation_manager import IncomeEstimationManager
from classes.pages.child_pages.budget_planning_pages import income_estimation_page
from classes.work_shift_class import WorkShift


def scheduled_job(name="Store job", foods=()):
    return BudgetJob(name, "15", "20", (0,) * 7,
                     weekly_shifts=(WorkShift("8 AM", "4 PM", 30),) * 5 + (None, None), foods_per_shift=foods)


class FoodConsumptionPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Path(self.enterContext(tempfile.TemporaryDirectory(
            prefix="food-consumption-", dir=Path(__file__).resolve().parent)))

    def test_food_quantities_accept_fractions_and_reject_invalid_ids_or_quantities(self):
        food = FoodConsumption("7", " 0.25 ")
        self.assertEqual((food.grocery_item_id, food.quantity), (7, Decimal("0.25")))
        self.assertEqual(FoodConsumption.from_dict(food.to_dict()), food)
        for identifier in (0, -1, "NaN", "Infinity", "1.5", None, True):
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                FoodConsumption(identifier, 1)
        for quantity in (0, -1, "", "NaN", "sNaN", "Infinity", "half", None, True):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                FoodConsumption(1, quantity)
        for record in (None, [], {}, {"grocery_item_id": 1}):
            with self.subTest(record=record), self.assertRaises(ValueError):
                FoodConsumption.from_dict(record)
        for foods in (None, [food, food], [{}]):
            with self.subTest(foods=foods), self.assertRaises(ValueError):
                validate_food_plan(foods)

    def test_jobs_keep_separate_shift_food_plans_across_restarts_and_income_is_unchanged(self):
        first = scheduled_job(foods=(FoodConsumption(1, "0.5"), FoodConsumption(2, "2")))
        second = scheduled_job("Other job", (FoodConsumption(1, "1.5"),))
        store = BudgetJobsManager(self.workspace / "jobs.json")
        store.save([first, second])
        self.assertEqual(BudgetJobsManager(store.path).load(), [first, second])
        with_foods = IncomeEstimationManager.estimate([first, second], date(2026, 10, 8))
        without_foods = IncomeEstimationManager.estimate([replace(first, foods_per_shift=()), replace(second, foods_per_shift=())], date(2026, 10, 8))
        self.assertEqual((with_foods.gross, with_foods.tax, with_foods.take_home),
                         (without_foods.gross, without_foods.tax, without_foods.take_home))
        store.save([replace(first, name="Renamed", foods_per_shift=(FoodConsumption(2, "3"),)), second])
        self.assertEqual(store.load()[0].job_id, first.job_id)
        self.assertEqual(store.load()[0].foods_per_shift, (FoodConsumption(2, "3"),))
        self.assertEqual(store.load()[1], second)

    def test_legacy_jobs_default_to_no_food_plan_without_rewriting_saved_data(self):
        record = scheduled_job().to_dict()
        record.pop("foods_per_shift")
        path = self.workspace / "jobs.json"
        original = json.dumps({"version": 1, "jobs": [record]})
        path.write_text(original, encoding="utf-8")
        self.assertEqual(BudgetJobsManager(path).load()[0].foods_per_shift, ())
        self.assertEqual(path.read_text(encoding="utf-8"), original)
        for foods in (None, {}, [{}], [{"grocery_item_id": 1, "quantity": 0}],
                      [{"grocery_item_id": 1, "quantity": 1}] * 2):
            with self.subTest(foods=foods), self.assertRaises(ValueError):
                BudgetJob.from_dict({**record, "foods_per_shift": foods})

    def test_day_off_plan_is_shared_and_persists_independently_of_jobs(self):
        store = DayOffFoodsManager(self.workspace / "day_off.json")
        self.assertEqual(store.load(), ())
        foods = (FoodConsumption(1, "1.25"), FoodConsumption(2, 2))
        store.save(foods)
        self.assertEqual(DayOffFoodsManager(store.path).load(), foods)
        jobs = BudgetJobsManager(self.workspace / "jobs.json")
        jobs.save([scheduled_job(foods=(FoodConsumption(1, 3),))])
        jobs.save([])
        self.assertEqual(store.load(), foods)
        store.save(())
        self.assertEqual(store.load(), ())

    def test_failed_or_invalid_day_off_saves_preserve_the_old_plan_and_clean_temporary_files(self):
        store = DayOffFoodsManager(self.workspace / "day_off.json")
        food = FoodConsumption(1, 2)
        store.save((food,))
        original = store.path.read_bytes()
        with self.assertRaises(ValueError):
            store.save((food, food))
        with patch("classes.managers.day_off_foods_manager.os.replace", side_effect=OSError("Disk full")), self.assertRaises(OSError):
            store.save((FoodConsumption(1, 3),))
        self.assertEqual(store.path.read_bytes(), original)
        self.assertEqual(list(self.workspace.iterdir()), [store.path])

    def test_corrupt_day_off_files_are_reported_without_rewriting_them(self):
        store = DayOffFoodsManager(self.workspace / "day_off.json")
        for contents in ("not JSON", "[]", '{"version":2,"foods":[]}', '{"version":1,"foods":null}',
                         '{"version":1,"foods":[{}]}', '{"version":1,"foods":[{"grocery_item_id":1,"quantity":"NaN"}]}'):
            with self.subTest(contents=contents):
                store.path.write_text(contents, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Could not read food for days off"):
                    store.load()
                self.assertEqual(store.path.read_text(encoding="utf-8"), contents)


class FoodConsumptionPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as error:
            raise unittest.SkipTest(f"Tk unavailable: {error}")
        cls.root.withdraw()
        cls.toplevel_type = tk.Toplevel

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.workspace = Path(self.enterContext(tempfile.TemporaryDirectory(
            prefix="food-plan-page-", dir=Path(__file__).resolve().parent)))
        self.catalog = GroceryCatalogManager(self.workspace / "groceries.csv")
        self.loaf, self.serving = GroceryUnit("Loaf", plural="Loaves"), GroceryUnit("Serving")
        self.catalog.units_manager.save([self.loaf, self.serving])
        self.items = [GroceryCatalogItem(1, "Bread", "4.99", 1, unit_id=self.loaf.unit_id),
                      GroceryCatalogItem(2, "Protein Powder", "24.99", 30, unit_id=self.serving.unit_id)]
        self.catalog.save(self.items)
        self.jobs = BudgetJobsManager(self.workspace / "jobs.json")
        self.day_off = DayOffFoodsManager(self.workspace / "day_off.json")
        self.page = income_estimation_page.IncomeEstimationPage(
            self.root, Mock(), self.jobs, today=lambda: date(2026, 10, 8),
            catalog_manager=self.catalog, day_off_foods_manager=self.day_off,
            foods_manager=PreparedFoodsManager(self.workspace / "foods.json"))
        self.enterContext(patch.object(tk, "Toplevel", side_effect=self.hidden_popup))

    def tearDown(self):
        if self.page._food_window_open():
            self.page._food_editor.window.destroy()
        if self.page._editor is not None and self.page._editor.winfo_exists():
            self.page._editor.destroy()
        self.page._root.destroy()

    def hidden_popup(self, *args, **kwargs):
        window = self.toplevel_type(*args, **kwargs)
        window.withdraw()
        return window

    def choose(self, editor, item_id, quantity):
        editor._food_value.set(next(label for label, identifier in editor._choices.items() if identifier == item_id))
        editor._quantity_value.set(str(quantity))

    def add_food(self, editor, item_id, quantity):
        self.choose(editor, item_id, quantity)
        editor._save_food_button.invoke()

    def existing_job_editor(self, foods=()):
        job = scheduled_job(foods=foods)
        self.jobs.save([job])
        self.page._reload_and_refresh()
        self.page._show_job_editor(job)
        return job

    def test_shift_foods_can_be_added_edited_and_removed_and_are_saved_with_the_job(self):
        original = self.existing_job_editor()
        job_bytes = self.jobs.path.read_bytes()
        catalog_bytes = self.catalog.path.read_bytes()
        editor = self.page._show_shift_foods()
        self.assertEqual(str(self.page._save_job_button.cget("state")), "disabled")
        self.add_food(editor, 1, "1")
        self.add_food(editor, 2, "0.5")
        self.assertEqual([row[2].cget("text") for row in editor._food_table._components], ["Loaf", "Servings"])
        editor._food_table._components[0][3].winfo_children()[0].invoke()
        editor._quantity_value.set("2")
        editor._save_food_button.invoke()
        self.assertEqual(editor._food_table._components[0][2].cget("text"), "Loaves")
        editor._food_table._components[1][3].winfo_children()[1].invoke()
        editor._save_plan_button.invoke()
        self.assertFalse(editor.window.winfo_exists())
        self.assertEqual(self.jobs.path.read_bytes(), job_bytes)
        self.assertEqual(str(self.page._save_job_button.cget("state")), "normal")
        self.assertEqual(self.page._shift_foods_label.cget("text"), "Food per shift: 1 food")
        self.page._save_job_button.invoke()
        saved, = BudgetJobsManager(self.jobs.path).load()
        self.assertEqual(saved.foods_per_shift, (FoodConsumption(1, 2),))
        self.assertEqual((saved.job_id, saved.weekly_shifts, saved.hourly_wage, saved.tax_percentage),
                         (original.job_id, original.weekly_shifts, original.hourly_wage, original.tax_percentage))
        self.assertEqual(self.catalog.path.read_bytes(), catalog_bytes)
        self.page._show_job_editor(saved)
        self.assertEqual(self.page._show_shift_foods().foods, saved.foods_per_shift)

    def test_cancel_food_dialog_or_job_editor_preserves_previously_saved_plan(self):
        original = self.existing_job_editor((FoodConsumption(1, 1),))
        original_bytes = self.jobs.path.read_bytes()
        editor = self.page._show_shift_foods()
        self.add_food(editor, 2, 2)
        editor.window.destroy()
        self.assertEqual(self.page._editor_foods, original.foods_per_shift)
        editor = self.page._show_shift_foods()
        self.add_food(editor, 2, 2)
        editor._save_plan_button.invoke()
        self.page._editor.destroy()
        self.assertEqual(self.jobs.path.read_bytes(), original_bytes)
        self.page._show_job_editor(original)
        self.assertEqual(self.page._editor_foods, original.foods_per_shift)

    def test_new_jobs_can_define_foods_before_saving_and_cancel_does_not_create_a_job(self):
        self.page._show_job_editor()
        editor = self.page._show_shift_foods()
        self.add_food(editor, 2, "0.25")
        editor._save_plan_button.invoke()
        self.page._editor.destroy()
        self.assertFalse(self.jobs.path.exists())
        self.page._show_job_editor()
        values = self.page._editor_values
        for key, value in (("name", "Weekend job"), ("wage", "20"), ("tax", "10")):
            values[key].set(value)
        values["working"][5].set(True)
        values["starts"][5].set("8 AM")
        values["ends"][5].set("4 PM")
        editor = self.page._show_shift_foods()
        self.choose(editor, 2, "0.25")
        editor._save_plan_button.invoke()  # Saves the current food form as well.
        self.page._save_job_button.invoke()
        self.assertEqual(self.jobs.load()[0].foods_per_shift, (FoodConsumption(2, "0.25"),))

    def test_invalid_or_duplicate_foods_do_not_change_the_draft_or_saved_plan(self):
        editor = self.page._show_day_off_foods()
        self.add_food(editor, 1, 1)
        for quantity in ("0", "-1", "NaN", "sNaN", "Infinity", "half", ""):
            with self.subTest(quantity=quantity):
                self.choose(editor, 2, quantity)
                editor._save_food_button.invoke()
                self.assertEqual(editor.foods, (FoodConsumption(1, 1),))
        # An old selection cannot re-add an item after the picker filters it out.
        editor._food_value.set(next(label for label, identifier in editor._all_choices.items() if identifier == 1))
        editor._quantity_value.set("2")
        editor._save_plan_button.invoke()
        self.assertIn("Choose an available", editor._error_label.cget("text"))
        self.assertTrue(editor.window.winfo_exists())
        self.assertFalse(self.day_off.path.exists())
        editor._cancel_edit()
        editor._save_plan_button.invoke()
        self.assertEqual(self.day_off.load(), (FoodConsumption(1, 1),))

    def test_day_off_foods_persist_with_no_jobs_and_can_be_edited_or_removed(self):
        self.page._day_off_foods_button.invoke()
        editor = self.page._food_editor
        self.add_food(editor, 2, 1)
        editor._save_plan_button.invoke()
        self.assertFalse(self.jobs.path.exists())
        self.assertEqual(DayOffFoodsManager(self.day_off.path).load(), (FoodConsumption(2, 1),))
        editor = self.page._show_day_off_foods()
        editor._edit_food(editor.foods[0])
        editor._quantity_value.set("1.5")
        editor._save_plan_button.invoke()
        self.assertEqual(self.day_off.load(), (FoodConsumption(2, "1.5"),))
        editor = self.page._show_day_off_foods()
        editor._remove_food(editor.foods[0])
        editor._save_plan_button.invoke()
        self.assertEqual(self.day_off.load(), ())

    def test_save_failure_keeps_food_editor_available_for_retry(self):
        self.day_off.save((FoodConsumption(1, 1),))
        original = self.day_off.path.read_bytes()
        editor = self.page._show_day_off_foods()
        self.add_food(editor, 2, 2)
        with patch.object(self.day_off, "save", side_effect=OSError("Disk full")):
            editor._save_plan_button.invoke()
        self.assertIn("Disk full", editor._error_label.cget("text"))
        self.assertTrue(editor.window.winfo_exists())
        self.assertEqual(self.day_off.path.read_bytes(), original)
        editor._save_plan_button.invoke()
        self.assertEqual(self.day_off.load(), (FoodConsumption(1, 1), FoodConsumption(2, 2)))

    def test_grocery_renames_and_custom_units_are_reloaded_and_deleted_foods_can_be_replaced(self):
        self.day_off.save((FoodConsumption(1, 2),))
        editor = self.page._show_day_off_foods()
        self.catalog.save([replace(self.items[0], name="Sourdough"), self.items[1]])
        self.catalog.units_manager.save([GroceryUnit("Slice", self.loaf.unit_id), self.serving])
        editor._reload_catalog()
        row = editor._food_table._components[0]
        self.assertEqual((row[0].cget("text"), row[2].cget("text")), ("Sourdough", "Slices"))
        self.catalog.save([self.items[1]])
        editor._reload_catalog()
        self.assertIn("Unavailable grocery", editor._food_table._components[0][0].cget("text"))
        editor._edit_food(editor.foods[0])
        self.choose(editor, 2, 1)
        editor._save_plan_button.invoke()
        self.assertFalse(editor.window.winfo_exists(), editor._error_label.cget("text") if editor.window.winfo_exists() else "")
        self.assertEqual(self.day_off.load(), (FoodConsumption(2, 1),))

    def test_empty_or_corrupt_catalogue_does_not_erase_saved_foods_and_reload_can_recover(self):
        self.day_off.save((FoodConsumption(1, 1),))
        self.catalog.save([])
        editor = self.page._show_day_off_foods()
        self.assertEqual(str(editor._save_food_button.cget("state")), "disabled")
        self.assertEqual(editor.foods, (FoodConsumption(1, 1),))
        self.catalog.path.write_text("bad CSV", encoding="utf-8")
        editor._reload_catalog()
        self.assertIn("Could not read grocery items", editor._error_label.cget("text"))
        self.assertEqual(self.day_off.load(), (FoodConsumption(1, 1),))
        self.catalog.save(self.items)
        editor._reload_catalog()
        self.choose(editor, 2, 2)
        self.assertEqual(str(editor._save_food_button.cget("state")), "normal")

    def test_corrupt_day_off_file_blocks_editor_without_overwriting_it(self):
        self.day_off.path.write_text("bad JSON", encoding="utf-8")
        with patch.object(income_estimation_page.messagebox, "showerror") as error:
            self.assertIsNone(self.page._show_day_off_foods())
        self.assertIn("Could not read food for days off", error.call_args.args[1])
        self.assertEqual(self.day_off.path.read_text(encoding="utf-8"), "bad JSON")

    def test_food_picker_excludes_added_items_and_restores_them_after_remove_or_replacement(self):
        editor = self.page._show_day_off_foods()
        self.add_food(editor, 1, 1)
        self.assertEqual(set(editor._choices.values()), {2})
        self.assertEqual(tuple(editor._food_dropdown.cget("values")), tuple(editor._choices))
        editor._edit_food(editor.foods[0])
        self.assertEqual(set(editor._choices.values()), {1, 2})
        self.assertIn("Bread", editor._food_value.get())
        self.choose(editor, 2, "0.5")
        editor._save_food_button.invoke()
        self.assertEqual(set(editor._choices.values()), {1})
        self.assertEqual(editor.foods, (FoodConsumption(2, "0.5"),))
        editor._remove_food(editor.foods[0])
        self.assertEqual(set(editor._choices.values()), {1, 2})

    def test_food_picker_handles_a_full_plan_and_keeps_only_the_edited_row_available(self):
        foods = (FoodConsumption(1, 1), FoodConsumption(2, 2))
        self.existing_job_editor(foods)
        editor = self.page._show_shift_foods()
        self.assertEqual(tuple(editor._food_dropdown.cget("values")), ())
        self.assertEqual(str(editor._food_dropdown.cget("state")), "disabled")
        editor._edit_food(editor.foods[0])
        self.assertEqual(set(editor._choices.values()), {1})
        self.assertEqual(str(editor._food_dropdown.cget("state")), "readonly")
        editor._cancel_edit()
        self.assertEqual(editor._choices, {})
        editor._remove_food(editor.foods[1])
        self.assertEqual(set(editor._choices.values()), {2})
        editor._reload_catalog()
        self.assertEqual(set(editor._choices.values()), {2})


if __name__ == "__main__":
    unittest.main()
