import csv
import io
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile

from classes.grocery_catalog_item_class import GroceryCatalogItem
from classes.grocery_unit_class import GroceryUnit
from classes.managers.grocery_catalog_manager import GroceryCatalogManager
from classes.managers.grocery_price_updates_manager import GroceryPriceUpdatesManager, PRICE_CHECK_INSTRUCTIONS
from classes.pages.child_pages.budget_planning_page_class import BudgetPlanningPage
from classes.pages.child_pages.budget_planning_pages import grocery_prices_page


def read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        return reader.fieldnames, list(reader)


def write_rows(path, fields, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class GroceryPriceUpdatesTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Path(self.enterContext(tempfile.TemporaryDirectory(
            prefix="grocery-prices-", dir=Path(__file__).resolve().parent)))
        self.store = GroceryCatalogManager(self.workspace / "groceries.csv")
        self.cans = GroceryUnit("Can")
        self.store.units_manager.save([self.cans])
        self.items = [GroceryCatalogItem(4, 'Soup, "Café"', "12.99", 8, "https://example.com/soup", self.cans.unit_id),
                      GroceryCatalogItem(9, "Bread", "4.50", 1)]
        self.store.save(self.items)
        self.manager = GroceryPriceUpdatesManager(self.store)
        self.csv_path = self.workspace / "price-check.csv"
        self.manager.export_csv(self.csv_path)
        self.fields, self.rows = read_rows(self.csv_path)

    def test_export_contains_all_products_case_units_and_links_with_no_catalogue_changes(self):
        original = self.store.path.read_bytes()
        self.assertEqual(self.manager.export_csv(self.csv_path), 2)
        self.assertEqual(self.rows[0], {"id": "4", "name": 'Soup, "Café"', "num_items": "8",
                                       "unit_id": self.cans.unit_id, "unit": "Cans",
                                       "link": "https://example.com/soup", "current_price": "12.99", "updated_price": ""})
        self.assertEqual(self.rows[1]["link"], "")
        self.assertEqual(self.rows[1]["current_price"], "4.50")
        self.assertEqual(self.store.path.read_bytes(), original)

    def test_reordered_returned_rows_update_prices_only_and_persist_after_restart(self):
        self.rows[0]["updated_price"] = "11.59"
        self.rows[1]["updated_price"] = "5.25"
        write_rows(self.csv_path, list(reversed(self.fields)), list(reversed(self.rows)))
        updates = self.manager.read_updates(self.csv_path)
        self.assertEqual(self.store.load(), self.items)  # Preview has no side effects.
        self.assertEqual(self.manager.apply_updates(updates), 2)
        reopened = GroceryCatalogManager(self.store.path)
        self.assertEqual(reopened.load(), [replace(self.items[0], price="11.59"), replace(self.items[1], price="5.25")])
        self.assertEqual(reopened.units_manager.load(), [self.cans])

    def test_blank_unchanged_and_partial_prices_keep_existing_products(self):
        self.assertEqual(self.manager.read_updates(self.csv_path), ())
        self.rows[0]["updated_price"] = " 12.99 "
        self.rows[1]["updated_price"] = "  "
        write_rows(self.csv_path, self.fields, self.rows)
        self.assertEqual(self.manager.read_updates(self.csv_path), ())
        self.rows[0]["updated_price"] = "0.00"
        write_rows(self.csv_path, self.fields, self.rows[:1])
        self.manager.apply_updates(self.manager.read_updates(self.csv_path))
        self.assertEqual(self.store.load(), [replace(self.items[0], price=0), self.items[1]])

    def test_invalid_price_in_any_row_rejects_entire_import_without_writing(self):
        original = self.store.path.read_bytes()
        self.rows[0]["updated_price"] = "10.00"
        for price in ("-1", "NaN", "Infinity", "1.234", "$4.59", "1,000.00", "unavailable"):
            with self.subTest(price=price):
                self.rows[1]["updated_price"] = price
                write_rows(self.csv_path, self.fields, self.rows)
                with self.assertRaisesRegex(ValueError, "Row 3"):
                    self.manager.read_updates(self.csv_path)
                self.assertEqual(self.store.path.read_bytes(), original)

    def test_unknown_duplicate_and_changed_product_rows_are_rejected(self):
        original = self.store.path.read_bytes()
        for key, value in (("id", "999"), ("id", "4.5"), ("id", "NaN"), ("name", "Different product"),
                           ("num_items", "16"), ("unit_id", "different-unit"),
                           ("link", "https://example.com/different"), ("current_price", "14.00")):
            with self.subTest(key=key, value=value):
                rows = [dict(self.rows[0], **{key: value, "updated_price": "1.00"})]
                write_rows(self.csv_path, self.fields, rows)
                with self.assertRaisesRegex(ValueError, "Row 2"):
                    self.manager.read_updates(self.csv_path)
                self.assertEqual(self.store.path.read_bytes(), original)
        write_rows(self.csv_path, self.fields, [self.rows[0], self.rows[0]])
        with self.assertRaisesRegex(ValueError, "Duplicate item ID"):
            self.manager.read_updates(self.csv_path)

    def test_missing_duplicate_columns_or_malformed_rows_are_rejected(self):
        original = self.store.path.read_bytes()
        valid_text = self.csv_path.read_text(encoding="utf-8-sig")
        for contents in ("wrong,header\n", ",".join([*self.fields[:-1], "id"]) + "\n",
                         ",".join(self.fields) + "\n4,Incomplete\n", valid_text + "4,too,many,columns,here,1,2,3,4\n"):
            with self.subTest(contents=contents):
                self.csv_path.write_text(contents, encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.manager.read_updates(self.csv_path)
                self.assertEqual(self.store.path.read_bytes(), original)

    def test_changes_between_export_import_and_apply_are_detected(self):
        self.rows[0]["updated_price"] = "10.00"
        write_rows(self.csv_path, self.fields, self.rows)
        self.store.save([replace(self.items[0], link="https://example.com/new"), self.items[1]])
        with self.assertRaisesRegex(ValueError, "fresh CSV"):
            self.manager.read_updates(self.csv_path)
        self.store.save(self.items)
        updates = self.manager.read_updates(self.csv_path)
        self.store.save([replace(self.items[0], price="13.50"), self.items[1]])
        changed = self.store.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "after importing"):
            self.manager.apply_updates(updates)
        self.assertEqual(self.store.path.read_bytes(), changed)
        self.store.save([self.items[1]])
        with self.assertRaisesRegex(ValueError, "after importing"):
            self.manager.apply_updates(updates)

    def test_failed_price_save_preserves_catalogue_and_updates_can_be_retried(self):
        self.rows[0]["updated_price"] = "10.00"
        write_rows(self.csv_path, self.fields, self.rows)
        updates = self.manager.read_updates(self.csv_path)
        original = self.store.path.read_bytes()
        with patch("classes.managers.grocery_catalog_manager.os.replace", side_effect=OSError("Disk full")), \
                self.assertRaisesRegex(OSError, "Disk full"):
            self.manager.apply_updates(updates)
        self.assertEqual(self.store.path.read_bytes(), original)
        self.assertFalse(list(self.workspace.glob("*.tmp")))
        self.manager.apply_updates(updates)
        self.assertEqual(self.store.load()[0].price, Decimal("10"))

    def test_export_cannot_overwrite_saved_products_or_units_and_failed_exports_preserve_file(self):
        original = self.store.path.read_bytes()
        for path in (self.store.path, self.store.units_manager.path):
            with self.assertRaisesRegex(ValueError, "separate file"):
                self.manager.export_csv(path)
        self.assertEqual(self.store.path.read_bytes(), original)
        original_export = self.csv_path.read_bytes()
        with patch("classes.managers.grocery_price_updates_manager.os.replace", side_effect=OSError("Disk full")), \
                self.assertRaises(OSError):
            self.manager.export_csv(self.csv_path)
        self.assertEqual(self.csv_path.read_bytes(), original_export)
        self.assertFalse(list(self.workspace.glob("*.tmp")))

    def test_zip_contains_instructions_and_all_products_with_the_shipping_exception(self):
        downloads = self.workspace / "downloads"
        archive_path = self.manager.download_package(downloads)
        self.assertEqual(list(downloads.iterdir()), [archive_path])
        with ZipFile(archive_path) as archive:
            self.assertEqual(set(archive.namelist()), {"instructions.txt", "groceries.csv"})
            instructions = archive.read("instructions.txt").decode("utf-8")
            self.assertEqual(instructions, PRICE_CHECK_INSTRUCTIONS)
            self.assertIn("Gamer Supps", instructions)
            self.assertIn("product price PLUS its standard shipping cost", instructions)
            self.assertIn("Return a downloadable UTF-8 CSV", instructions)
            rows = list(csv.DictReader(io.StringIO(archive.read("groceries.csv").decode("utf-8-sig"))))
        self.assertEqual(rows, self.rows)
        self.assertEqual(self.store.load(), self.items)
        self.store.save([replace(self.items[0], price="11.59"), self.items[1]])
        self.manager.download_package(downloads)
        with ZipFile(archive_path) as archive:
            rows = list(csv.DictReader(io.StringIO(archive.read("groceries.csv").decode("utf-8-sig"))))
        self.assertEqual(rows[0]["current_price"], "11.59")

    def test_failed_zip_regeneration_keeps_the_previous_package_and_cleans_temporary_files(self):
        downloads = self.workspace / "downloads"
        archive_path = self.manager.download_package(downloads)
        previous = archive_path.read_bytes()
        with patch("classes.managers.grocery_price_updates_manager.ZipFile", side_effect=OSError("Disk full")), \
                self.assertRaisesRegex(OSError, "Disk full"):
            self.manager.download_package(downloads)
        self.assertEqual(archive_path.read_bytes(), previous)
        self.assertEqual(list(downloads.iterdir()), [archive_path])

    def test_export_uses_singular_or_custom_plural_according_to_each_case_size(self):
        self.store.units_manager.save([GroceryUnit("Loaf", self.cans.unit_id, "Loaves")])
        self.store.save([replace(self.items[0], units_per_case=1), replace(self.items[1], units_per_case=2, unit_id=self.cans.unit_id)])
        self.manager.export_csv(self.csv_path)
        _, rows = read_rows(self.csv_path)
        self.assertEqual([row["unit"] for row in rows], ["Loaf", "Loaves"])


class GroceryPricesPageTests(unittest.TestCase):
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
        self.workspace = Path(self.enterContext(tempfile.TemporaryDirectory(
            prefix="grocery-price-page-", dir=Path(__file__).resolve().parent)))
        self.downloads = self.workspace / "downloads"
        self.enterContext(patch.object(grocery_prices_page, "_DOWNLOADS_PATH", self.downloads))
        self.store = GroceryCatalogManager(self.workspace / "groceries.csv")
        self.item = GroceryCatalogItem(1, "Soup", "12.99", 8, "https://example.com/soup")
        self.store.save([self.item])
        self.next_page, self.back = Mock(), Mock()
        self.page = grocery_prices_page.GroceryPricesPage(self.root, self.next_page, self.back, self.store)
        self.csv_path = self.workspace / "checked.csv"

    def tearDown(self):
        self.page._root.destroy()

    def import_price(self, price="11.59"):
        self.page._price_updates.export_csv(self.csv_path)
        fields, rows = read_rows(self.csv_path)
        rows[0]["updated_price"] = price
        write_rows(self.csv_path, fields, rows)
        with patch.object(grocery_prices_page.filedialog, "askopenfilename", return_value=str(self.csv_path)):
            self.page._import_button.invoke()

    def test_zip_downloads_on_activation_and_selecting_csv_automatically_applies_prices(self):
        self.assertFalse(self.downloads.exists())
        self.page.activate()
        archive_path = self.downloads / "instructions.zip"
        self.assertEqual(self.page._instructions_zip_path, archive_path)
        with ZipFile(archive_path) as archive:
            self.assertEqual(set(archive.namelist()), {"instructions.txt", "groceries.csv"})
        self.assertFalse(hasattr(self.page, "_apply_button"))
        self.import_price()
        row = self.page._preview_table._components[0]
        self.assertEqual([cell.cget("text") for cell in row[:3]], ["Soup", "$12.99", "$11.59"])
        self.assertEqual(GroceryCatalogManager(self.store.path).load()[0].price, Decimal("11.59"))
        self.assertIn("Saved 1", self.page._status.cget("text"))
        self.assertEqual(str(self.page._continue_button.cget("state")), "normal")
        self.page._continue_button.invoke()
        self.next_page.assert_called_once_with()

    def test_failed_import_or_save_preserves_existing_prices_and_can_be_retried_by_selecting_csv(self):
        self.import_price()
        valid_updates = self.page._last_updates
        saved = self.store.path.read_bytes()
        self.csv_path.write_text("bad CSV", encoding="utf-8")
        with patch.object(grocery_prices_page.filedialog, "askopenfilename", return_value=str(self.csv_path)):
            self.page._import_button.invoke()
        self.assertEqual(self.page._last_updates, valid_updates)
        self.assertEqual(self.store.path.read_bytes(), saved)
        with patch.object(self.store, "save", side_effect=OSError("Disk full")):
            self.import_price("10.99")
        self.assertIn("Disk full", self.page._status.cget("text"))
        self.assertEqual(self.page._last_updates, valid_updates)
        self.assertEqual(self.store.path.read_bytes(), saved)
        with patch.object(grocery_prices_page.filedialog, "askopenfilename", return_value=str(self.csv_path)):
            self.page._import_button.invoke()
        self.assertEqual(self.store.load()[0].price, Decimal("10.99"))

    def test_cancelled_csv_selection_and_optional_skip_do_not_save_prices(self):
        with patch.object(grocery_prices_page.filedialog, "askopenfilename", return_value=""):
            self.page._import_button.invoke()
        self.assertFalse(self.csv_path.exists())
        self.assertEqual(self.store.load(), [self.item])
        self.page._continue_button.invoke()
        self.next_page.assert_called_once_with()

    def test_corrupt_catalogue_blocks_price_exchange_but_keeps_budget_accessible(self):
        self.store.path.write_text("bad CSV", encoding="utf-8")
        self.page.activate()
        self.assertIn("Could not read grocery items", self.page._status.cget("text"))
        self.assertEqual(str(self.page._export_button.cget("state")), "disabled")
        self.assertEqual(str(self.page._import_button.cget("state")), "disabled")
        self.page._continue_button.invoke()
        self.next_page.assert_called_once_with()
        self.assertEqual(self.store.path.read_text(encoding="utf-8"), "bad CSV")

    def test_groceries_are_first_and_navigation_reloads_imported_prices_in_item_list(self):
        with patch("classes.managers.grocery_catalog_manager._GROCERIES_PATH", self.store.path), \
                patch("classes.managers.budget_jobs_manager._JOBS_PATH", self.workspace / "jobs.json"):
            budget = BudgetPlanningPage(self.root, Mock())
        self.addCleanup(budget._root.destroy)
        budget.activate()
        items, prices, income = budget._grocery_page, budget._grocery_prices_page, budget._income_page
        self.assertEqual((budget._page_index, budget._groceries_page._page_index), (0, 0))
        self.assertFalse(hasattr(items, "_back_button"))
        items._continue_button.invoke()
        self.assertEqual((budget._page_index, budget._groceries_page._page_index), (0, 1))
        prices._price_updates.export_csv(self.csv_path)
        fields, rows = read_rows(self.csv_path)
        rows[0]["updated_price"] = "11.59"
        write_rows(self.csv_path, fields, rows)
        with patch.object(grocery_prices_page.filedialog, "askopenfilename", return_value=str(self.csv_path)):
            prices._import_button.invoke()
        prices._on_back()
        self.assertEqual(items.items[0].price, Decimal("11.59"))
        self.assertEqual(budget._groceries_page._page_index, 0)
        items._continue_button.invoke()
        prices._continue_button.invoke()
        self.assertEqual(budget._page_index, 1)
        budget._foods_page._continue_button.invoke()
        self.assertEqual(budget._page_index, 2)
        budget._daily_use_page._continue_button.invoke()
        self.assertEqual(budget._page_index, 3)
        income._back_button.invoke()
        self.assertEqual(budget._page_index, 2)
        budget._daily_use_page._back_button.invoke()
        self.assertEqual(budget._page_index, 1)
        budget._foods_page._back_button.invoke()
        self.assertEqual((budget._page_index, budget._groceries_page._page_index), (0, 1))
        prices._continue_button.invoke()
        budget._foods_page._continue_button.invoke()
        budget._daily_use_page._continue_button.invoke()
        income._continue_button.invoke()
        self.assertEqual(budget._page_index, 4)
        self.assertEqual(budget.budget_summary.total_expenses, 0)
        budget._overall_page._edit_groceries_button.invoke()
        self.assertEqual((budget._page_index, budget._groceries_page._page_index), (0, 0))

    def test_download_failure_is_shown_and_regenerate_retries_without_blocking_navigation(self):
        with patch.object(self.page._price_updates, "download_package", side_effect=OSError("Disk full")):
            self.page.activate()
        self.assertIn("Disk full", self.page._instructions_status.cget("text"))
        self.assertIsNone(self.page._instructions_zip_path)
        self.page._export_button.invoke()
        self.assertTrue(self.page._instructions_zip_path.exists())
        self.assertEqual(self.page._instructions_status.cget("fg"), "#15803D")

    def test_bad_price_in_any_returned_row_prevents_all_automatic_updates(self):
        self.store.save([self.item, GroceryCatalogItem(2, "Bread", "4.50")])
        self.page._reload_catalog()
        self.page._price_updates.export_csv(self.csv_path)
        fields, rows = read_rows(self.csv_path)
        rows[0]["updated_price"] = "11.59"
        rows[1]["updated_price"] = "NaN"
        write_rows(self.csv_path, fields, rows)
        before = self.store.path.read_bytes()
        with patch.object(grocery_prices_page.filedialog, "askopenfilename", return_value=str(self.csv_path)):
            self.page._import_button.invoke()
        self.assertIn("Row 3", self.page._status.cget("text"))
        self.assertEqual(self.store.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
