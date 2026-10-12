import csv
import json
import tempfile
import tkinter as tk
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from classes.budget_job_class import BudgetJob
from classes.custom_tk_components.tk_link_class import TkLink
from classes.grocery_catalog_item_class import GroceryCatalogItem
from classes.grocery_unit_class import GroceryUnit
from classes.managers.budget_jobs_manager import BudgetJobsManager
from classes.managers.budget_summary_manager import BudgetExpense
from classes.managers.grocery_catalog_manager import GroceryCatalogManager
from classes.pages.child_pages.budget_planning_page_class import BudgetPlanningPage
from classes.pages.child_pages.budget_planning_pages import grocery_items_page
from enums.budget.categories_enum import BudgetCategories


def product(item_id=1, name="Breakfast sandwiches", price="12.99", units=8, link="https://example.com/product", unit_id=None):
    return GroceryCatalogItem(item_id, name, price, units, link, unit_id)


class GroceryCatalogTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Path(self.enterContext(tempfile.TemporaryDirectory(
            prefix="grocery-catalog-", dir=Path(__file__).resolve().parent)))
        self.store = GroceryCatalogManager(self.workspace / "groceries.csv")

    def test_product_details_round_trip_through_restarts_and_empty_lists_stay_empty(self):
        self.assertEqual(self.store.load(), [])
        items = [product(name='Crackers, "Original"'), product(2, "Café coffee", "3.20", "1", None)]
        self.store.save(items)
        self.assertEqual(GroceryCatalogManager(self.store.path).load(), items)
        self.store.save([items[1]])
        self.assertEqual(self.store.load(), [items[1]])
        self.store.save([])
        self.assertEqual(GroceryCatalogManager(self.store.path).load(), [])
        self.assertEqual(list(self.workspace.iterdir()), [self.store.path])

    def test_existing_csv_rows_keep_names_ids_case_sizes_and_links_without_loading_rewriting_them(self):
        original = "id,name,num_items,link\n7,Existing grocery,22,https://example.com/existing\n"
        self.store.path.write_text(original, encoding="utf-8")
        loaded, = self.store.load()
        self.assertEqual(loaded, product(7, "Existing grocery", "0", 22, "https://example.com/existing"))
        self.assertEqual(self.store.path.read_text(encoding="utf-8"), original)
        edited = product(loaded.item_id, loaded.name, "4.59", loaded.units_per_case, loaded.link)
        self.store.save([edited])
        self.assertEqual(self.store.load(), [edited])
        with self.store.path.open(encoding="utf-8", newline="") as source:
            self.assertEqual(next(csv.DictReader(source))["price"], "4.59")

    def test_invalid_product_details_are_rejected_and_zero_price_or_no_link_are_valid(self):
        for fields in ({"name": " "}, {"price": ""}, {"price": "NaN"}, {"price": "Infinity"},
                       {"price": "-1"}, {"price": "1.234"}, {"units": 0}, {"units": "1.5"},
                       {"units": "NaN"}, {"units": True}, {"item_id": 0}, {"item_id": "1.5"},
                       {"link": "example.com"}, {"link": "javascript:alert(1)"},
                       {"link": "https://"}, {"link": "https://example.com/a b"}, {"link": 42}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                product(**fields)
        self.assertEqual(product(price="0", units="1.0", link="").units_per_case, 1)

    def test_corrupt_csv_is_reported_without_overwriting_it(self):
        for contents in ("wrong,header\n", "id,name,num_items,link\n1,Missing fields\n",
                         "id,name,num_items,link\n1,One,1,\n1,Two,1,\n",
                         "id,name,price,num_items,link\n1,Item,NaN,1,\n",
                         "id,name,num_items,link,link\n1,Item,1,,\n"):
            with self.subTest(contents=contents):
                self.store.path.write_text(contents, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Could not read grocery items"):
                    self.store.load()
                self.assertEqual(self.store.path.read_text(encoding="utf-8"), contents)

    def test_failed_or_duplicate_saves_preserve_previous_data_and_remove_temporary_files(self):
        original = product()
        self.store.save([original])
        contents = self.store.path.read_bytes()
        with self.assertRaises(ValueError):
            self.store.save([original, original])
        with patch("classes.managers.grocery_catalog_manager.os.replace", side_effect=OSError("Disk full")), \
                self.assertRaisesRegex(OSError, "Disk full"):
            self.store.save([product(price="15")])
        self.assertEqual(self.store.path.read_bytes(), contents)
        self.assertEqual(list(self.workspace.iterdir()), [self.store.path])

    def test_unit_assignments_persist_and_renames_keep_their_identity_without_rewriting_item_details(self):
        cans = GroceryUnit("Can")
        units = self.store.units_manager
        self.assertEqual(units.load(), [])
        units.save([cans])
        items = [product(unit_id=cans.unit_id), product(2, "Soup", unit_id=cans.unit_id)]
        self.store.save(items)
        contents = self.store.path.read_bytes()
        reopened = GroceryCatalogManager(self.store.path)
        self.assertEqual(reopened.load(), items)
        renamed = GroceryUnit("Tin", cans.unit_id)
        units.save([renamed])
        self.assertEqual(reopened.units_manager.load(), [renamed])
        self.assertEqual(reopened.load(), items)
        self.assertEqual(self.store.path.read_bytes(), contents)
        with self.assertRaisesRegex(ValueError, "existing grocery unit"):
            self.store.save([product(unit_id="unknown-unit")])
        self.assertEqual(self.store.path.read_bytes(), contents)

    def test_deleted_units_leave_quantities_and_product_details_intact_and_recreating_a_name_does_not_restore_old_assignments(self):
        cans = GroceryUnit("Can")
        self.store.units_manager.save([cans])
        self.store.save([product(unit_id=cans.unit_id)])
        contents = self.store.path.read_bytes()
        self.store.units_manager.save([])
        reopened = GroceryCatalogManager(self.store.path)
        self.assertEqual(reopened.load(), [product()])
        self.assertEqual(reopened.units_manager.load(), [])
        self.assertEqual(self.store.path.read_bytes(), contents)
        replacement = GroceryUnit("Can")
        self.assertNotEqual(replacement.unit_id, cans.unit_id)
        reopened.units_manager.save([replacement])
        self.assertEqual(reopened.load(), [product()])
        reopened.save(reopened.load())
        with reopened.path.open(encoding="utf-8", newline="") as source:
            self.assertEqual(next(csv.DictReader(source))["unit_id"], "")

    def test_invalid_or_failed_unit_edits_preserve_saved_units_and_item_assignments(self):
        units = self.store.units_manager
        cans = GroceryUnit("Can")
        units.save([cans])
        self.store.save([product(unit_id=cans.unit_id)])
        original_units = units.path.read_bytes()
        original_items = self.store.path.read_bytes()
        for name in ("", " ", "!!!", "No unit", " no   UNIT "):
            with self.subTest(name=name), self.assertRaises(ValueError):
                GroceryUnit(name)
        for invalid in ([cans, GroceryUnit(" can ")], [cans, GroceryUnit("Bag", cans.unit_id)]):
            with self.assertRaises(ValueError):
                units.save(invalid)
        with patch("classes.managers.grocery_units_manager.os.replace", side_effect=OSError("Disk full")), \
                self.assertRaisesRegex(OSError, "Disk full"):
            units.save([GroceryUnit("Tin", cans.unit_id)])
        self.assertEqual(units.path.read_bytes(), original_units)
        self.assertEqual(self.store.path.read_bytes(), original_items)
        self.assertEqual(self.store.load(), [product(unit_id=cans.unit_id)])
        self.assertEqual(set(self.workspace.iterdir()), {self.store.path, units.path})
        for contents in ("broken", "[]", '{"version":2,"units":[]}', '{"version":1,"units":[{}]}'):
            with self.subTest(contents=contents):
                units.path.write_text(contents, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Could not read grocery units"):
                    units.load()
                self.assertEqual(units.path.read_text(encoding="utf-8"), contents)

    def test_singular_plural_defaults_and_custom_forms_persist_without_changing_unit_identity(self):
        can = GroceryUnit("  Can  ")
        self.assertEqual((can.singular, can.plural, can.for_count(1), can.for_count(8)), ("Can", "Cans", "Can", "Cans"))
        loaf = GroceryUnit("Loaf", plural="  Loaves  ")
        fish = GroceryUnit("Fish", plural="Fish")
        self.store.units_manager.save([can, loaf, fish])
        reopened = GroceryCatalogManager(self.store.path).units_manager.load()
        self.assertEqual(reopened, [can, loaf, fish])
        self.assertEqual(reopened[1].for_count(2), "Loaves")
        for plural in ("!!!", "No unit", 42):
            with self.subTest(plural=plural), self.assertRaises(ValueError):
                GroceryUnit("Can", plural=plural)
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.store.units_manager.save([can, GroceryUnit("Cans")])

    def test_legacy_units_gain_default_plurals_on_load_without_rewriting_the_file_or_assignments(self):
        units = self.store.units_manager
        original = json.dumps({"version": 1, "units": [{"id": "old-can", "name": "Can"}]})
        units.path.write_text(original, encoding="utf-8")
        self.store.save([product(unit_id="old-can")])
        loaded, = units.load()
        self.assertEqual((loaded.unit_id, loaded.singular, loaded.plural), ("old-can", "Can", "Cans"))
        self.assertEqual(units.path.read_text(encoding="utf-8"), original)
        self.assertEqual(self.store.load()[0].unit_id, "old-can")
        units.save([GroceryUnit("Can", "old-can", "Tin Cans")])
        self.assertEqual(units.load()[0].plural, "Tin Cans")
        self.assertEqual(self.store.load()[0].unit_id, "old-can")


class GroceryItemsPageTests(unittest.TestCase):
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
        self.workspace = Path(self.enterContext(tempfile.TemporaryDirectory(
            prefix="grocery-page-", dir=Path(__file__).resolve().parent)))
        self.store = GroceryCatalogManager(self.workspace / "groceries.csv")
        self.next_page = Mock()
        self.enterContext(patch("classes.pages.child_pages.budget_planning_pages.grocery_prices_page._DOWNLOADS_PATH",
                                self.workspace / "downloads"))
        self.back = Mock()
        self.page = grocery_items_page.GroceryItemsPage(self.root, self.next_page, self.back, self.store)

    def tearDown(self):
        if self.page._editor is not None and self.page._editor.winfo_exists():
            self.page._editor.destroy()
        self.page._root.destroy()

    def hidden_popup(self, *args, **kwargs):
        window = self.toplevel_type(*args, **kwargs)
        window.withdraw()
        return window

    def open_editor(self, existing=None):
        with patch.object(grocery_items_page.tk, "Toplevel", side_effect=self.hidden_popup):
            return self.page._show_item_editor(existing)

    def open_units_manager(self):
        with patch.object(grocery_items_page.tk, "Toplevel", side_effect=self.hidden_popup):
            return self.page._show_units_manager()

    def set_fields(self, name="Breakfast sandwiches", price="12.99", units="8", link="https://example.com/product"):
        for key, value in (("name", name), ("link", link), ("price", price), ("units", units)):
            self.page._editor_values[key].set(value)

    def add_item(self):
        self.open_editor()
        self.set_fields()
        self.page._save_item_button.invoke()

    def test_add_edit_and_optional_name_links_persist_when_reopened(self):
        self.add_item()
        original, = self.store.load()
        cells = self.page._item_table._components[0]
        self.assertEqual([column.text for column in self.page._item_table.columns],
                         ["Name", "Price", "Units per Case", "Actions"])
        self.assertIsInstance(cells[0], TkLink)
        self.assertEqual(cells[1].cget("text"), "$0.00")
        self.assertEqual(cells[2].cget("text"), "8")
        with patch("classes.custom_tk_components.tk_link_class.webbrowser.open") as browser:
            cells[0]._open_link()
        browser.assert_called_once_with("https://example.com/product")
        self.open_editor(original)
        self.assertEqual(self.page._editor_values["link"].get(), original.link)
        self.set_fields(name="Updated sandwiches", price="14.25", units="12", link="")
        self.page._save_item_button.invoke()
        updated, = GroceryCatalogManager(self.store.path).load()
        self.assertEqual(updated.item_id, original.item_id)
        self.assertEqual((updated.name, updated.price, updated.units_per_case, updated.link),
                         ("Updated sandwiches", Decimal("14.25"), 12, ""))
        self.page._items = []
        self.page.activate()
        self.assertEqual(self.page.items, (updated,))
        self.assertNotIsInstance(self.page._item_table._components[0][0], TkLink)

    def test_delete_confirmation_preserves_or_removes_the_saved_row(self):
        self.add_item()
        original = self.store.path.read_bytes()
        delete = self.page._item_table._components[0][3].winfo_children()[1]
        self.assertEqual(delete.cget("fg"), "#B91C1C")
        with patch.object(grocery_items_page.messagebox, "askyesno", return_value=False):
            delete.invoke()
        self.assertEqual(self.store.path.read_bytes(), original)
        with patch.object(grocery_items_page.messagebox, "askyesno", return_value=True):
            delete.invoke()
        self.assertEqual(GroceryCatalogManager(self.store.path).load(), [])
        self.assertEqual(self.page.items, ())

    def test_invalid_values_and_cancel_do_not_change_saved_items(self):
        self.add_item()
        original = self.store.path.read_bytes()
        window = self.open_editor(self.page.items[0])
        self.set_fields(units="0")
        self.page._save_item_button.invoke()
        self.assertTrue(window.winfo_exists())
        self.assertIn("Units per case", self.page._editor_error.cget("text"))
        self.assertEqual(self.store.path.read_bytes(), original)
        self.set_fields(link="bad link")
        self.page._save_item_button.invoke()
        self.assertIn("Product links", self.page._editor_error.cget("text"))
        window.destroy()
        self.assertEqual(self.store.path.read_bytes(), original)

    def test_failed_save_keeps_the_editor_and_data_available_for_retry(self):
        window = self.open_editor()
        self.set_fields()
        with patch.object(self.store, "save", side_effect=OSError("Disk full")), \
                patch.object(grocery_items_page.messagebox, "showerror") as error:
            self.page._save_item_button.invoke()
        self.assertIn("Disk full", error.call_args.args[1])
        self.assertTrue(window.winfo_exists())
        self.assertFalse(self.store.path.exists())
        self.assertEqual(self.page.items, ())
        self.page._save_item_button.invoke()
        self.assertFalse(window.winfo_exists())
        self.assertEqual(len(self.store.load()), 1)

    def test_corrupt_catalog_blocks_edits_but_does_not_block_independent_budget_navigation(self):
        self.store.path.write_text("broken", encoding="utf-8")
        self.page._reload_and_refresh()
        self.assertIn("Could not read grocery items", self.page._status.cget("text"))
        self.assertEqual(str(self.page._add_button.cget("state")), "disabled")
        self.assertIsNone(self.page._show_item_editor())
        self.page._continue_button.invoke()
        self.next_page.assert_called_once_with()
        self.assertEqual(self.store.path.read_text(encoding="utf-8"), "broken")
        self.store.save([product()])
        self.page._reload_and_refresh()
        self.assertEqual(str(self.page._add_button.cget("state")), "normal")
        self.page._back_button.invoke()
        self.back.assert_called_once_with()

    def test_create_select_and_rename_units_updates_all_assigned_items_and_an_open_editor(self):
        self.open_editor()
        self.set_fields()
        window = self.open_units_manager()
        self.page._unit_name_value.set("Can")
        self.page._unit_save_button.invoke()
        cans, = self.store.units_manager.load()
        self.assertEqual(self.page._editor_values["unit"].get(), "Can")
        self.assertIn("Can", self.page._unit_dropdown.cget("values"))
        window.destroy()
        self.page._save_item_button.invoke()
        self.open_editor()
        self.set_fields(name="Soup")
        self.page._editor_values["unit"].set("Can")
        self.page._save_item_button.invoke()
        self.assertTrue(all(row[2].cget("text") == "8 Cans" for row in self.page._item_table._components))
        items_before = self.store.path.read_bytes()

        editor = self.open_editor(self.page.items[0])
        self.page._editor_values["name"].set("Unsaved name")
        window = self.open_units_manager()
        self.page._units_table._components[0][2].winfo_children()[0].invoke()
        self.assertEqual(self.page._unit_save_button.cget("text"), "Save Unit")
        self.page._unit_name_value.set("Tin")
        self.page._unit_save_button.invoke()
        self.assertEqual(self.page._editor_values["unit"].get(), "Tin")
        self.assertEqual(self.page._editor_values["name"].get(), "Unsaved name")
        self.assertTrue(all(row[2].cget("text") == "8 Tins" for row in self.page._item_table._components))
        self.assertEqual(self.store.path.read_bytes(), items_before)
        renamed, = self.store.units_manager.load()
        self.assertEqual(renamed, GroceryUnit("Tin", cans.unit_id))
        window.destroy()
        editor.destroy()
        self.page.activate()
        self.assertTrue(all(item.unit_id == cans.unit_id for item in self.page.items))
        self.assertTrue(all(row[2].cget("text") == "8 Tins" for row in self.page._item_table._components))

    def test_deleting_a_unit_can_be_cancelled_or_clears_assignments_without_deleting_items(self):
        cans = GroceryUnit("Can")
        self.store.units_manager.save([cans])
        self.store.save([product(unit_id=cans.unit_id), product(2, "Soup", unit_id=cans.unit_id)])
        self.page._reload_and_refresh()
        editor = self.open_editor(self.page.items[0])
        window = self.open_units_manager()
        delete = self.page._units_table._components[0][2].winfo_children()[1]
        with patch.object(grocery_items_page.messagebox, "askyesno", return_value=False):
            delete.invoke()
        self.assertEqual(self.page._editor_values["unit"].get(), "Can")
        self.assertEqual(self.store.units_manager.load(), [cans])
        with patch.object(grocery_items_page.messagebox, "askyesno", return_value=True):
            delete.invoke()
        self.assertEqual(self.store.units_manager.load(), [])
        self.assertEqual(self.page._editor_values["unit"].get(), "No unit")
        self.assertTrue(all(item.unit_id is None for item in self.page.items))
        self.assertEqual(len(self.page.items), 2)
        self.assertTrue(all(item.units_per_case == 8 and item.price == Decimal("12.99") for item in self.page.items))
        self.assertTrue(all(row[2].cget("text") == "8" for row in self.page._item_table._components))
        window.destroy()
        editor.destroy()
        self.page.activate()
        self.assertTrue(all(item.unit_id is None for item in self.page.items))

    def test_unit_editor_supports_custom_plurals_and_automatically_formats_item_quantities(self):
        window = self.open_units_manager()
        self.page._unit_name_value.set("Loaf")
        self.assertEqual(self.page._unit_plural_value.get(), "Loafs")
        self.page._unit_plural_value.set("Loaves")
        self.page._unit_name_value.set("Bread Loaf")
        self.assertEqual(self.page._unit_plural_value.get(), "Loaves")
        self.page._unit_name_value.set("Loaf")
        self.page._unit_save_button.invoke()
        loaf, = self.store.units_manager.load()
        self.assertEqual((loaf.name, loaf.plural), ("Loaf", "Loaves"))
        self.store.save([product(units=1, unit_id=loaf.unit_id), product(2, "Bread case", units=2, unit_id=loaf.unit_id)])
        self.page._reload_and_refresh()
        self.assertEqual([row[2].cget("text") for row in self.page._item_table._components], ["1 Loaf", "2 Loaves"])
        item_contents = self.store.path.read_bytes()
        self.page._units_table._components[0][2].winfo_children()[0].invoke()
        self.assertEqual(self.page._unit_plural_value.get(), "Loaves")
        self.page._unit_plural_value.set("Bread Loaves")
        self.page._unit_save_button.invoke()
        renamed, = self.store.units_manager.load()
        self.assertEqual(renamed.unit_id, loaf.unit_id)
        self.assertEqual(renamed.plural, "Bread Loaves")
        self.assertEqual(self.store.path.read_bytes(), item_contents)
        self.assertEqual([row[2].cget("text") for row in self.page._item_table._components], ["1 Loaf", "2 Bread Loaves"])
        window.destroy()

    def test_invalid_duplicate_failed_and_corrupt_unit_edits_keep_assignments_available_for_retry(self):
        self.open_editor()
        self.set_fields()
        window = self.open_units_manager()
        self.page._unit_name_value.set("Can")
        self.page._unit_save_button.invoke()
        cans, = self.store.units_manager.load()
        self.page._unit_name_value.set(" can ")
        self.page._unit_save_button.invoke()
        self.assertIn("already exists", self.page._unit_error_label.cget("text"))
        self.assertEqual(self.page._editor_values["unit"].get(), "Can")
        self.page._rename_unit(cans)
        self.page._unit_name_value.set("Tin")
        with patch.object(self.store.units_manager, "save", side_effect=OSError("Disk full")):
            self.page._unit_save_button.invoke()
        self.assertIn("Disk full", self.page._unit_error_label.cget("text"))
        self.assertEqual(self.store.units_manager.load(), [cans])
        self.assertEqual(self.page._editor_values["unit"].get(), "Can")
        self.page._unit_save_button.invoke()
        self.assertEqual(self.page._editor_values["unit"].get(), "Tin")
        window.destroy()
        self.page._save_item_button.invoke()
        self.store.units_manager.path.write_text("broken", encoding="utf-8")
        self.page._reload_and_refresh()
        self.assertEqual(str(self.page._add_button.cget("state")), "disabled")
        window = self.open_units_manager()
        self.assertIn("Could not read grocery units", self.page._unit_error_label.cget("text"))
        self.assertEqual(str(self.page._unit_save_button.cget("state")), "disabled")
        self.store.units_manager.save([GroceryUnit("Tin", cans.unit_id)])
        self.page._reload_and_refresh()
        self.assertEqual(str(self.page._unit_save_button.cget("state")), "normal")
        self.assertEqual(self.page.items[0].unit_id, cans.unit_id)
        window.destroy()

    def test_grocery_page_precedes_overall_budget_and_catalog_edits_do_not_change_budget_totals(self):
        self.store.save([product(price="9999.99", units=500)])
        jobs = BudgetJobsManager(self.workspace / "jobs.json")
        jobs.save([BudgetJob("Job", "15", "20", (8, 8, 8, 8, 8, 0, 0))])
        with patch("classes.managers.budget_jobs_manager._JOBS_PATH", jobs.path), \
                patch("classes.managers.grocery_catalog_manager._GROCERIES_PATH", self.store.path):
            budget = BudgetPlanningPage(self.root, Mock())
        self.addCleanup(budget._root.destroy)
        budget._income_page._today = lambda: date(2026, 10, 7)
        budget._income_page._reload_and_refresh()
        budget.activate()
        budget.set_planned_expenses([BudgetExpense(BudgetCategories.CAR, "Fuel", "100")])
        before = budget.budget_summary
        self.assertEqual(budget._page_index, 0)
        self.assertIs(budget._pages[0].items_page, budget._grocery_page)
        catalog = budget._grocery_page
        self.assertEqual(catalog.items[0].price, Decimal("9999.99"))
        with patch.object(grocery_items_page.tk, "Toplevel", side_effect=self.hidden_popup):
            catalog._show_item_editor(catalog.items[0])
        self.assertEqual(str(catalog._price_entry.cget("state")), "disabled")
        catalog._editor_values["price"].set("19999.99")
        catalog._editor_values["units"].set("1000")
        catalog._save_item_button.invoke()
        catalog._continue_button.invoke()
        self.assertEqual(budget._page_index, 0)
        self.assertEqual(budget._groceries_page._page_index, 1)
        budget._grocery_prices_page._continue_button.invoke()
        self.assertEqual(budget._page_index, 1)
        budget._foods_page._continue_button.invoke()
        self.assertEqual(budget._page_index, 2)
        budget._daily_use_page._continue_button.invoke()
        self.assertEqual(budget._page_index, 3)
        budget._income_page._continue_button.invoke()
        self.assertEqual(budget._page_index, 4)
        self.assertEqual(budget.budget_summary, before)
        self.assertEqual(budget._overall_page._remaining_label.cget("text"), "$1,916.00")
        budget._overall_page._edit_groceries_button.invoke()
        self.assertEqual(budget._page_index, 0)
        self.assertEqual(budget._groceries_page._page_index, 0)
        self.assertEqual(catalog.items[0].units_per_case, 1000)
        self.assertEqual(catalog.items[0].price, Decimal("9999.99"))
        self.assertEqual(GroceryCatalogManager(self.store.path).load(), list(catalog.items))

    def test_linked_prices_are_locked_and_preserved_and_removing_a_link_allows_manual_edits(self):
        existing = product()
        self.store.save([existing])
        self.page._reload_and_refresh()
        window = self.open_editor(existing)
        self.assertEqual(str(self.page._price_entry.cget("state")), "disabled")
        self.page._price_entry.insert(0, "999")
        self.assertEqual(self.page._editor_values["price"].get(), "12.99")
        self.page._editor_values["price"].set("999")
        self.page._editor_values["name"].set("Renamed")
        self.page._save_item_button.invoke()
        self.assertFalse(window.winfo_exists())
        edited, = self.store.load()
        self.assertEqual(edited.price, existing.price)
        self.assertEqual(edited.name, "Renamed")

        self.open_editor(edited)
        self.page._editor_values["link"].set("")
        self.assertEqual(str(self.page._price_entry.cget("state")), "normal")
        self.page._editor_values["price"].set("14.25")
        self.page._save_item_button.invoke()
        unlinked, = self.store.load()
        self.assertEqual(unlinked.price, Decimal("14.25"))
        self.open_editor(unlinked)
        self.page._editor_values["price"].set("99.99")
        self.page._editor_values["link"].set(existing.link)
        self.assertEqual(str(self.page._price_entry.cget("state")), "disabled")
        self.assertEqual(self.page._editor_values["price"].get(), "14.25")
        self.page._save_item_button.invoke()
        self.assertEqual(self.store.load()[0].price, Decimal("14.25"))

    def test_linked_item_editor_preserves_a_price_imported_while_it_was_open(self):
        original = product()
        self.store.save([original])
        self.page._reload_and_refresh()
        self.open_editor(original)
        self.store.save([product(price="11.59"), product(2, "New product", link="")])
        self.page._editor_values["units"].set("12")
        self.page._save_item_button.invoke()
        saved = self.store.load()
        self.assertEqual(len(saved), 2)
        self.assertEqual(saved[0].price, Decimal("11.59"))
        self.assertEqual(saved[0].units_per_case, 12)


if __name__ == "__main__":
    unittest.main()
