import tempfile
import tkinter as tk
import unittest
from enum import StrEnum
from pathlib import Path
from tkinter import ttk
from unittest.mock import Mock, patch

from classes.custom_tk_components import tk_table_class
from classes.financial_transaction_class import FinancialTransaction
from classes.general.date_class import Date
from classes.general.dollar_amount_class import DollarAmount
from classes.managers import enum_manager, location_manager
from classes.pages.child_pages.expense_reveiw_pages import final_review_page
from enums.finances.locations_enum import Locations


def isolate_locations(test):
    tests_directory = Path(__file__).resolve().parent
    temporary_directory = tempfile.TemporaryDirectory(prefix="location-creation-check-", dir=tests_directory)
    workspace = Path(temporary_directory.name).resolve()
    if workspace.parent != tests_directory:
        raise RuntimeError("Unexpected temporary directory location.")
    test.addCleanup(temporary_directory.cleanup)
    enum_path = workspace / "locations_enum.py"
    members = {location.name: location.value for location in Locations}
    source = "from enum import StrEnum\n\nclass Locations(StrEnum):\n"
    source += "".join(f"    {name} = {value!r}\n" for name, value in members.items())
    enum_path.write_text(source, encoding="utf-8", newline="")
    isolated_enum = StrEnum("Locations", members)
    test.enterContext(patch.object(location_manager, "Locations", isolated_enum))
    test.enterContext(patch.object(location_manager, "_LOCATIONS_ENUM_PATH", enum_path))
    return enum_path, isolated_enum


class LocationCreationTests(unittest.TestCase):
    def setUp(self):
        self.enum_path, self.locations = isolate_locations(self)

    def test_saves_a_new_member_and_makes_it_available_now_and_after_restart(self):
        name = "Joe's \"Quick\" Shop"
        location = location_manager.LocationManager.create(name)
        self.assertIsInstance(location, self.locations)
        self.assertEqual(location.value, name)
        self.assertIs(self.locations(location.value), location)
        self.assertIs(self.locations[location.name], location)
        self.assertIn(location, list(self.locations))
        self.assertEqual(location.name, "JOE_S_QUICK_SHOP")
        namespace = {}
        exec(self.enum_path.read_text(encoding="utf-8"), namespace)
        self.assertEqual(namespace["Locations"][location.name].value, name)
        self.assertEqual(namespace["Locations"].WALMART.value, "Walmart")

    def test_existing_names_reuse_members_without_rewriting_the_enum(self):
        original_source = self.enum_path.read_bytes()
        location = location_manager.LocationManager.create("  wAlMaRt  ")
        self.assertIs(location, self.locations.WALMART)
        self.assertEqual(self.enum_path.read_bytes(), original_source)

    def test_generates_identifiers_for_numbers_accents_and_name_collisions(self):
        for display_name, member_name in (
            ("7-Eleven", "LOCATION_7_ELEVEN"),
            ("Café Shop", "CAFE_SHOP"),
            ("Cafe-Shop", "CAFE_SHOP_2"),
        ):
            with self.subTest(display_name=display_name):
                location = location_manager.LocationManager.create(display_name)
                self.assertEqual(location.name, member_name)
                self.assertEqual(location.value, display_name)
        namespace = {}
        exec(self.enum_path.read_text(encoding="utf-8"), namespace)
        self.assertEqual(len(namespace["Locations"]), len(self.locations))

    def test_rejects_empty_or_unusable_names_without_changing_source_or_members(self):
        original_source = self.enum_path.read_bytes()
        original_members = list(self.locations)
        for name in ("", " \t\n", "!!!"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                location_manager.LocationManager.create(name)
        self.assertEqual(self.enum_path.read_bytes(), original_source)
        self.assertEqual(list(self.locations), original_members)

    def test_failed_save_preserves_the_original_file_and_runtime_enum(self):
        original_source = self.enum_path.read_bytes()
        original_members = list(self.locations)
        with patch.object(enum_manager.os, "replace", side_effect=OSError("Cannot save")):
            with self.assertRaises(OSError):
                location_manager.LocationManager.create("New Shop")
        self.assertEqual(self.enum_path.read_bytes(), original_source)
        self.assertEqual(list(self.locations), original_members)
        self.assertEqual(list(self.enum_path.parent.iterdir()), [self.enum_path])

    def test_preserves_line_endings_and_source_outside_the_enum(self):
        source = self.enum_path.read_text(encoding="utf-8")
        source += "\n# Keep this comment.\nAFTER_ENUM = 123\n"
        self.enum_path.write_bytes(source.replace("\n", "\r\n").encode("utf-8"))
        location_manager.LocationManager.create("New Shop")
        saved_source = self.enum_path.read_bytes()
        self.assertNotIn(b"\n", saved_source.replace(b"\r\n", b""))
        self.assertTrue(saved_source.endswith(b"# Keep this comment.\r\nAFTER_ENUM = 123\r\n"))
        namespace = {}
        exec(saved_source.decode("utf-8"), namespace)
        self.assertEqual(namespace["Locations"].NEW_SHOP.value, "New Shop")
        self.assertEqual(namespace["AFTER_ENUM"], 123)

    def test_can_use_a_location_already_saved_since_the_enum_was_imported(self):
        with self.enum_path.open("a", encoding="utf-8") as enum_file:
            enum_file.write("    SAVED_SHOP = 'Saved Shop'\n")
        original_source = self.enum_path.read_bytes()
        location = location_manager.LocationManager.create("Saved Shop")
        self.assertIs(location, self.locations.SAVED_SHOP)
        self.assertEqual(self.enum_path.read_bytes(), original_source)


class LocationCreationWidgetTests(unittest.TestCase):
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
        self.enum_path, self.locations = isolate_locations(self)
        self.enterContext(patch.object(tk_table_class, "Locations", self.locations))
        self.enterContext(patch.object(final_review_page, "Locations", self.locations))
        self.page = final_review_page.FinalReviewPage(self.root, Mock())
        self.addCleanup(self.page._root.destroy)
        self.transactions = [FinancialTransaction(
            date=Date(day=29, month=9, year=2026), amount=DollarAmount(-1), description="Purchase",
            location=location,
        ) for location in (None, None, self.locations.WALMART, self.locations.NOT_INCLUDED)]
        self.page._transactions = self.transactions
        self.page._setup_components()
        self.table = next(widget for widget in self.page._root.winfo_children()
                          if isinstance(widget, tk_table_class.TkTable))

    def location_controls(self, row_index):
        cell = self.table._components[row_index][2]
        dropdown = next(widget for widget in cell.winfo_children() if isinstance(widget, ttk.Combobox))
        button = next(widget for widget in cell.winfo_children() if isinstance(widget, tk.Button))
        return dropdown, button

    def test_plus_button_is_to_the_right_of_each_unassigned_location(self):
        for row_index in (0, 1):
            dropdown, button = self.location_controls(row_index)
            self.assertEqual(dropdown.get(), "None")
            self.assertEqual(button.cget("text"), "+")
            self.assertEqual(dropdown.grid_info()["row"], button.grid_info()["row"])
            self.assertGreater(button.grid_info()["column"], dropdown.grid_info()["column"])
        self.assertIsInstance(self.table._components[2][2], tk.Label)
        self.assertEqual(self.table._components[2][2].cget("text"), "Walmart")
        excluded = self.table._components[3][2]
        self.assertIsInstance(excluded, tk.Label)
        self.assertEqual(excluded.cget("text"), "")
        self.assertEqual(excluded.cget("bg"), "black")

    def test_creates_persists_and_assigns_a_location_only_to_the_clicked_row(self):
        first_dropdown, first_button = self.location_controls(0)
        second_dropdown, second_button = self.location_controls(1)
        with patch.object(tk_table_class.simpledialog, "askstring", return_value="New Shop"):
            first_button.invoke()
        location = self.locations.NEW_SHOP
        self.assertIs(self.transactions[0].location, location)
        self.assertIsNone(self.transactions[1].location)
        self.assertEqual(first_dropdown.get(), "New Shop")
        self.assertEqual(second_dropdown.get(), "None")
        for dropdown in (first_dropdown, second_dropdown):
            self.assertIn("New Shop", dropdown.cget("values"))
        namespace = {}
        exec(self.enum_path.read_text(encoding="utf-8"), namespace)
        self.assertEqual(namespace["Locations"].NEW_SHOP.value, "New Shop")
        second_dropdown.set("New Shop")
        second_dropdown.event_generate("<<ComboboxSelected>>")
        self.assertIs(self.transactions[1].location, location)

    def test_selecting_an_existing_location_updates_the_correct_transaction(self):
        dropdown, button = self.location_controls(1)
        dropdown.set("Kwik Trip")
        dropdown.event_generate("<<ComboboxSelected>>")
        self.assertIs(self.transactions[1].location, self.locations.KWIK_TRIP)
        self.assertIsNone(self.transactions[0].location)

    def test_cancel_or_invalid_names_leave_the_transaction_and_enum_unchanged(self):
        dropdown, button = self.location_controls(0)
        original_source = self.enum_path.read_bytes()
        for name in (None, "", "!!!"):
            with self.subTest(name=name), \
                    patch.object(tk_table_class.simpledialog, "askstring", return_value=name), \
                    patch.object(tk_table_class.messagebox, "showerror") as show_error:
                button.invoke()
                self.assertIsNone(self.transactions[0].location)
                self.assertEqual(dropdown.get(), "None")
                self.assertEqual(self.enum_path.read_bytes(), original_source)
                self.assertEqual(show_error.call_count, 0 if name is None else 1)

    def test_save_failure_shows_an_error_and_does_not_assign_the_location(self):
        dropdown, button = self.location_controls(0)
        original_source = self.enum_path.read_bytes()
        with patch.object(tk_table_class.simpledialog, "askstring", return_value="New Shop"), \
                patch.object(enum_manager.os, "replace", side_effect=OSError("Cannot save")), \
                patch.object(tk_table_class.messagebox, "showerror") as show_error:
            button.invoke()
        show_error.assert_called_once()
        self.assertIsNone(self.transactions[0].location)
        self.assertEqual(dropdown.get(), "None")
        self.assertEqual(self.enum_path.read_bytes(), original_source)
        self.assertNotIn("New Shop", dropdown.cget("values"))

    def test_entering_an_existing_name_assigns_it_without_adding_a_duplicate(self):
        dropdown, button = self.location_controls(0)
        original_source = self.enum_path.read_bytes()
        with patch.object(tk_table_class.simpledialog, "askstring", return_value="walmart"):
            button.invoke()
        self.assertIs(self.transactions[0].location, self.locations.WALMART)
        self.assertEqual(dropdown.get(), "Walmart")
        self.assertEqual(self.enum_path.read_bytes(), original_source)


if __name__ == "__main__":
    unittest.main()
