from dataclasses import replace
from datetime import date
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from classes.budget_job_class import BudgetJob
from classes.food_consumption_class import FoodConsumption, validate_food_plan
from classes.grocery_catalog_item_class import GroceryCatalogItem
from classes.grocery_unit_class import GroceryUnit
from classes.managers.budget_jobs_manager import BudgetJobsManager
from classes.managers.day_off_foods_manager import DayOffFoodsManager
from classes.managers.grocery_catalog_manager import GroceryCatalogManager
from classes.managers.prepared_foods_manager import PreparedFoodsManager
from classes.pages.child_pages.budget_planning_page_class import BudgetPlanningPage
from classes.pages.child_pages.budget_planning_pages.foods_page import FoodsPage
from classes.pages.child_pages.budget_planning_pages.grocery_items_page import GroceryItemsPage
from classes.pages.child_pages.budget_planning_pages.grocery_prices_page import GroceryPricesPage
from classes.pages.child_pages.budget_planning_pages.income_estimation_page import IncomeEstimationPage
from classes.prepared_food_class import PreparedFood
from classes.work_shift_class import WorkShift


class PreparedFoodsPersistenceTests(unittest.TestCase):
    def setUp(self):
        directory = Path(__file__).resolve().parent / "__pycache__"
        directory.mkdir(exist_ok=True)
        self.workspace = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="prepared-foods-", dir=directory)))
        self.store = PreparedFoodsManager(self.workspace / "foods.json")
        self.food = PreparedFood("Sandwich", (FoodConsumption(1, "0.25"), FoodConsumption(2, 2)))

    def test_food_validation_requires_name_unique_grocery_ingredients_and_valid_saved_identifiers(self):
        for name, ingredients in (("", self.food.ingredients), (None, self.food.ingredients), ("Food", ()),
                                  ("Food", self.food.ingredients * 2), ("Food", [None]),
                                  ("Food", (FoodConsumption(None, 1, self.food.food_id),))):
            with self.subTest(name=name, ingredients=ingredients), self.assertRaises(ValueError):
                PreparedFood(name, ingredients)
        for record in ([], {}, {**self.food.to_dict(), "ingredients": None},
                       {**self.food.to_dict(), "food_id": "invalid"}):
            with self.subTest(record=record), self.assertRaises(ValueError):
                PreparedFood.from_dict(record)
        self.assertEqual(PreparedFood.from_dict(self.food.to_dict()), self.food)

    def test_foods_persist_with_stable_identifiers_and_names_must_be_unique(self):
        self.assertEqual(self.store.load(), [])
        self.store.save([self.food])
        renamed = replace(self.food, name="Lunch", ingredients=(FoodConsumption(1, "0.5"),))
        self.store.save([renamed])
        self.assertEqual(PreparedFoodsManager(self.store.path).load(), [renamed])
        original = self.store.path.read_bytes()
        for foods in ([renamed, renamed], [renamed, PreparedFood(" LUNCH ", self.food.ingredients)], [None]):
            with self.subTest(foods=foods), self.assertRaises(ValueError):
                self.store.save(foods)
        self.assertEqual(self.store.path.read_bytes(), original)
        self.store.save([])
        self.assertEqual(self.store.load(), [])

    def test_corrupt_files_and_failed_atomic_saves_preserve_existing_data(self):
        self.store.save([self.food])
        original = self.store.path.read_bytes()
        with patch("classes.managers.prepared_foods_manager.os.replace", side_effect=OSError("Disk full")), self.assertRaises(OSError):
            self.store.save([])
        self.assertEqual(self.store.path.read_bytes(), original)
        self.assertEqual(list(self.workspace.iterdir()), [self.store.path])
        for contents in ("bad JSON", "[]", '{"version":2,"foods":[]}', '{"version":1,"foods":[{}]}'):
            with self.subTest(contents=contents):
                self.store.path.write_text(contents, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Could not read prepared foods"):
                    self.store.load()
                self.assertEqual(self.store.path.read_text(encoding="utf-8"), contents)

    def test_mixed_food_and_grocery_plans_persist_in_jobs_and_days_off_without_id_collisions(self):
        plan = (FoodConsumption(1, "0.5"), FoodConsumption(None, "1.5", self.food.food_id))
        self.assertEqual(validate_food_plan(plan), plan)
        self.assertEqual(tuple(FoodConsumption.from_dict(item.to_dict()) for item in plan), plan)
        jobs = BudgetJobsManager(self.workspace / "jobs.json")
        job = BudgetJob("Job", "15", "20", (0,) * 7, foods_per_shift=plan)
        jobs.save([job])
        self.assertEqual(jobs.load(), [job])
        days_off = DayOffFoodsManager(self.workspace / "days_off.json")
        days_off.save(plan)
        self.assertEqual(days_off.load(), plan)
        self.assertEqual(FoodConsumption(1, 2).to_dict(), {"grocery_item_id": 1, "quantity": "2"})
        for arguments in ((1, 1, self.food.food_id), (None, 1, "invalid"), (None, 1, 123)):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                FoodConsumption(*arguments)
        with self.assertRaises(ValueError):
            validate_food_plan((plan[1], plan[1]))


class PreparedFoodsPageTests(unittest.TestCase):
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
        directory = Path(__file__).resolve().parent / "__pycache__"
        directory.mkdir(exist_ok=True)
        self.workspace = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="prepared-food-ui-", dir=directory)))
        self.catalog = GroceryCatalogManager(self.workspace / "groceries.csv")
        self.units = [GroceryUnit("Slice"), GroceryUnit("Spoonful", plural="Spoonfuls")]
        self.catalog.units_manager.save(self.units)
        self.items = [GroceryCatalogItem(1, "Bread", "3.99", 20, unit_id=self.units[0].unit_id),
                      GroceryCatalogItem(2, "Peanut Butter", "5.99", 40, unit_id=self.units[1].unit_id)]
        self.catalog.save(self.items)
        self.foods = PreparedFoodsManager(self.workspace / "foods.json")
        self.next_page, self.back = Mock(), Mock()
        self.page = FoodsPage(self.root, self.next_page, self.back, self.catalog, self.foods)
        self.enterContext(patch.object(tk, "Toplevel", side_effect=self.hidden_popup))

    def tearDown(self):
        self.page._root.destroy()

    def hidden_popup(self, *args, **kwargs):
        window = self.toplevel_type(*args, **kwargs)
        window.withdraw()
        return window

    def choose(self, editor, identifier, quantity):
        editor._food_value.set(next(label for label, value in editor._choices.items() if value == identifier))
        editor._quantity_value.set(str(quantity))

    def make_food(self, name="PB Sandwich"):
        editor = self.page._show_editor()
        editor._name_value.set(name)
        self.choose(editor, 1, 2)
        editor._save_food_button.invoke()
        self.choose(editor, 2, "0.5")
        editor._save_plan_button.invoke()
        self.assertFalse(editor.window.winfo_exists(), editor._error_label.cget("text") if editor.window.winfo_exists() else "")
        return self.foods.load()[0]

    def make_income_page(self):
        jobs = BudgetJobsManager(self.workspace / "jobs.json")
        days = DayOffFoodsManager(self.workspace / "days_off.json")
        page = IncomeEstimationPage(self.root, Mock(), jobs, today=lambda: date(2026, 10, 8),
                                    catalog_manager=self.catalog, day_off_foods_manager=days, foods_manager=self.foods)
        self.addCleanup(page._root.destroy)
        return page, jobs, days

    def test_create_food_saves_fractional_ingredients_and_reloads_without_changing_groceries(self):
        original = self.catalog.path.read_bytes()
        food = self.make_food()
        self.assertEqual(food.name, "PB Sandwich")
        self.assertEqual(food.ingredients, (FoodConsumption(1, 2), FoodConsumption(2, "0.5")))
        self.assertEqual(self.catalog.path.read_bytes(), original)
        self.assertEqual(self.page._food_table._components[0][1].cget("text"), "Bread: 2 Slices\nPeanut Butter: 0.5 Spoonfuls")
        restarted = FoodsPage(self.root, Mock(), Mock(), self.catalog, PreparedFoodsManager(self.foods.path))
        self.addCleanup(restarted._root.destroy)
        self.assertEqual(restarted._foods, [food])

    def test_editor_can_rename_edit_add_remove_and_cancel_without_losing_saved_data(self):
        original = self.make_food()
        editor = self.page._show_editor(original)
        editor._name_value.set("New Name")
        editor._edit_food(editor.foods[0])
        editor._quantity_value.set("1")
        editor._save_food_button.invoke()
        editor._remove_food(editor.foods[1])
        self.assertEqual(editor.foods, (FoodConsumption(1, 1),))
        editor.window.destroy()
        self.assertEqual(self.foods.load(), [original])
        editor = self.page._show_editor(original)
        editor._name_value.set("Toast")
        editor._remove_food(editor.foods[1])
        editor._edit_food(editor.foods[0])
        editor._quantity_value.set("1")
        editor._save_plan_button.invoke()
        updated, = self.foods.load()
        self.assertEqual((updated.food_id, updated.name, updated.ingredients),
                         (original.food_id, "Toast", (FoodConsumption(1, 1),)))

    def test_invalid_empty_duplicate_and_failed_saves_leave_editor_available_for_correction(self):
        original = self.make_food()
        editor = self.page._show_editor()
        editor._save_plan_button.invoke()
        self.assertIn("food name", editor._error_label.cget("text"))
        editor._name_value.set("Another Food")
        editor._save_plan_button.invoke()
        self.assertIn("at least one", editor._error_label.cget("text"))
        self.choose(editor, 1, 1)
        editor._name_value.set(original.name.lower())
        editor._save_plan_button.invoke()
        self.assertIn("already exists", editor._error_label.cget("text"))
        self.assertEqual(self.foods.load(), [original])
        editor._name_value.set("Toast")
        with patch.object(self.foods, "save", side_effect=OSError("Disk full")):
            editor._save_plan_button.invoke()
        self.assertIn("Disk full", editor._error_label.cget("text"))
        editor._save_plan_button.invoke()
        self.assertEqual([food.name for food in self.foods.load()], [original.name, "Toast"])

    def test_food_can_be_used_with_groceries_in_shift_and_day_off_plans(self):
        food = self.make_food()
        page, jobs, days = self.make_income_page()
        job = BudgetJob("Store", 15, 20, (0,) * 7, weekly_shifts=(WorkShift("8 AM", "4 PM"),) + (None,) * 6)
        jobs.save([job]); page._reload_and_refresh(); page._show_job_editor(job)
        editor = page._show_shift_foods()
        self.choose(editor, food.food_id, "1.5")
        editor._save_food_button.invoke()
        self.choose(editor, 1, "0.25")
        editor._save_plan_button.invoke()
        self.assertEqual(jobs.load(), [job])
        page._save_job_button.invoke()
        expected = (FoodConsumption(None, "1.5", food.food_id), FoodConsumption(1, "0.25"))
        self.assertEqual(jobs.load()[0].foods_per_shift, expected)
        editor = page._show_day_off_foods()
        self.choose(editor, food.food_id, 1)
        editor._save_plan_button.invoke()
        self.assertEqual(days.load(), (FoodConsumption(None, 1, food.food_id),))

    def test_food_renames_reach_existing_plans_and_deleted_foods_can_be_removed(self):
        food = self.make_food()
        page, _, days = self.make_income_page()
        reference = FoodConsumption(None, 2, food.food_id)
        days.save((reference, FoodConsumption(1, 1)))
        self.foods.save([replace(food, name="Lunch")])
        editor = page._show_day_off_foods()
        self.assertEqual(editor._food_table._components[0][0].cget("text"), "Lunch")
        self.assertEqual(editor._food_table._components[0][2].cget("text"), "Servings")
        with patch("classes.pages.child_pages.budget_planning_pages.foods_page.messagebox.askyesno", return_value=True):
            self.page._delete_food(food)
        self.assertEqual(self.foods.load(), [])
        self.assertEqual(days.load()[0], reference)
        editor._reload_catalog()
        self.assertEqual(editor._food_table._components[0][0].cget("text"), "Unavailable food")
        editor._remove_food(reference)
        editor._save_plan_button.invoke()
        self.assertEqual(days.load(), (FoodConsumption(1, 1),))

    def test_missing_groceries_are_visible_and_must_be_replaced_before_saving_a_food(self):
        original = self.make_food()
        self.catalog.save([replace(self.items[1], name="Almond Butter")])
        self.page._reload_and_refresh()
        text = self.page._food_table._components[0][1].cget("text")
        self.assertIn("Unavailable grocery", text)
        self.assertIn("Almond Butter", text)
        editor = self.page._show_editor(original)
        editor._save_plan_button.invoke()
        self.assertIn("unavailable groceries", editor._error_label.cget("text"))
        self.assertEqual(self.foods.load(), [original])
        editor._remove_food(editor.foods[0])
        editor._save_plan_button.invoke()
        self.assertEqual(self.foods.load()[0].ingredients, (FoodConsumption(2, "0.5"),))

    def test_corrupt_food_catalogue_blocks_changes_and_recovers_without_overwriting_it(self):
        food = self.make_food()
        self.foods.path.write_text("bad JSON", encoding="utf-8")
        self.page._reload_and_refresh()
        self.assertEqual(str(self.page._add_button.cget("state")), "disabled")
        self.assertIsNone(self.page._show_editor(food))
        self.assertIn("Could not read prepared foods", self.page._status.cget("text"))
        self.assertEqual(self.foods.path.read_text(encoding="utf-8"), "bad JSON")
        self.foods.save([food]); self.page._reload_and_refresh()
        self.assertEqual(str(self.page._add_button.cget("state")), "normal")

    def test_navigation_places_foods_between_prices_and_income_with_working_back_buttons(self):
        with patch("classes.managers.grocery_catalog_manager._GROCERIES_PATH", self.catalog.path), \
                patch("classes.managers.prepared_foods_manager._FOODS_PATH", self.foods.path), \
                patch("classes.managers.budget_jobs_manager._JOBS_PATH", self.workspace / "jobs.json"), \
                patch("classes.pages.child_pages.budget_planning_pages.grocery_prices_page._DOWNLOADS_PATH", self.workspace / "downloads"):
            budget = BudgetPlanningPage(self.root, Mock())
        self.addCleanup(budget._root.destroy)
        budget._grocery_page._continue_button.invoke()
        budget._grocery_prices_page._continue_button.invoke()
        self.assertEqual(budget._page_index, 1)
        self.assertIs(budget._pages[1], budget._foods_page)
        self.assertIs(budget._income_page._foods_manager, budget._foods_page._foods_manager)
        budget._foods_page._continue_button.invoke()
        self.assertEqual(budget._page_index, 2)
        budget._daily_use_page._continue_button.invoke()
        self.assertEqual(budget._page_index, 3)
        budget._income_page._back_button.invoke()
        self.assertEqual(budget._page_index, 2)
        budget._daily_use_page._back_button.invoke()
        self.assertEqual(budget._page_index, 1)
        budget._foods_page._back_button.invoke()
        self.assertEqual((budget._page_index, budget._groceries_page._page_index), (0, 1))

    def test_ingredient_filter_is_local_to_each_food_and_the_current_ingredient_remains_editable(self):
        food = self.make_food()
        editor = self.page._show_editor(food)
        self.assertEqual(tuple(editor._food_dropdown.cget("values")), ())
        editor._edit_food(editor.foods[0])
        self.assertEqual(set(editor._choices.values()), {1})
        editor._quantity_value.set("3")
        editor._save_food_button.invoke()
        self.assertEqual(editor._choices, {})
        editor._remove_food(editor.foods[1])
        self.assertEqual(set(editor._choices.values()), {2})
        editor.window.destroy()
        other = self.page._show_editor()
        self.assertEqual(set(other._choices.values()), {1, 2})

    def test_mixed_plan_filter_does_not_remove_choices_from_other_plans(self):
        food = self.make_food()
        page, jobs, days = self.make_income_page()
        days.save((FoodConsumption(None, 1, food.food_id), FoodConsumption(1, 1)))
        editor = page._show_day_off_foods()
        self.assertEqual(set(editor._choices.values()), {2})
        editor._edit_food(editor.foods[0])
        self.assertEqual(set(editor._choices.values()), {food.food_id, 2})
        editor.window.destroy()
        job = BudgetJob("Other job", 15, 20, (0,) * 7)
        jobs.save([job]); page._reload_and_refresh(); page._show_job_editor(job)
        editor = page._show_shift_foods()
        self.assertEqual(set(editor._choices.values()), {1, 2, food.food_id})

    def test_price_page_opens_without_shrinking_or_repeatedly_resizing_the_application(self):
        # Reproduce the app's natural window sizing, rather than fixing a geometry
        # which would hide the table-removal and wrapped-card feedback glitches.
        root = tk.Tk()
        root.withdraw(); root.attributes("-alpha", 0)
        self.addCleanup(root.destroy)
        root.maxsize(root.maxsize()[0], 1000)
        items = GroceryItemsPage(root, Mock(), catalog_manager=self.catalog)
        prices = GroceryPricesPage(root, Mock(), Mock(), self.catalog, self.workspace / "downloads")
        items.activate(); root.deiconify(); root.update()
        events = []
        root.bind("<Configure>", lambda event: events.append((event.width, event.height)) if event.widget is root else None)
        previous_table = prices._preview_table
        items.deactivate(); prices.activate()
        root.after(200, root.quit); root.mainloop()
        self.assertIs(prices._preview_table, previous_table)
        self.assertTrue(all(height >= 800 for _, height in events), events)
        self.assertLessEqual(len(set(events)), 3, events)
        prices.deactivate(); items.activate(); root.update()
        events.clear()
        items.deactivate(); prices.activate()
        root.after(200, root.quit); root.mainloop()
        self.assertTrue(all(height >= 800 for _, height in events), events)
        self.assertLessEqual(len(set(events)), 3, events)


if __name__ == "__main__":
    unittest.main()
