import json
import tempfile
import tkinter as tk
import unittest
from enum import StrEnum
from pathlib import Path
from unittest.mock import Mock, patch

from classes.custom_tk_components import tk_option_dropdown_class, tk_table_class
from classes.custom_tk_components.tk_option_dropdown_class import TkOptionDropdown
from classes.financial_transaction_class import FinancialTransaction
from classes.general.date_class import Date
from classes.general.dollar_amount_class import DollarAmount
from classes.managers import option_manager
from classes.managers.category_manager import CategoryManager
from classes.managers.description_manager import DescriptionManager
from classes.managers.location_manager import LocationManager
from classes.managers.option_manager import OptionManager
from classes.managers.expense_review_report import ExpenseSummary
from classes.managers.receipt_group_manager import ReceiptGroupManager
from classes.table_column_class import TableColumn
from enums.finances.categories_enum import Categories
from enums.finances.descriptions.car_descriptions_enum import CarDescriptions
from enums.finances.descriptions_enum import Descriptions
from enums.finances.locations_enum import Locations
from enums.finances.is_essential_enum import IsEssential


def isolate_preferences(test):
    workspace = test.enterContext(tempfile.TemporaryDirectory(prefix="option-management-", dir=Path(__file__).parent))
    path = Path(workspace) / "options.json"
    test.enterContext(patch.object(option_manager, "_OPTIONS_PATH", path))
    test.enterContext(patch.object(OptionManager, "_loaded_path", None))
    test.enterContext(patch.object(OptionManager, "_preferences", {}))
    test.enterContext(patch.object(OptionManager, "_listeners", set()))
    return path


class OptionManagementTests(unittest.TestCase):
    def setUp(self):
        self.path = isolate_preferences(self)

    def test_rename_survives_reload_and_preserves_member_identity_and_brand_color(self):
        original = Locations.APPLE.value
        original_colors = CategoryManager.colors(Categories.SHOPPING)
        OptionManager.rename(Locations.APPLE, 'Apple "Store"', Locations)
        OptionManager.rename(Categories.SHOPPING, "Everyday Shopping", Categories)
        self.assertEqual(Locations.APPLE.value, original)
        self.assertIs(OptionManager.resolve(Locations, 'Apple "Store"'), Locations.APPLE)
        self.assertIs(OptionManager.resolve(Locations, original), Locations.APPLE)
        OptionManager._loaded_path = None
        self.assertEqual(OptionManager.display(Locations.APPLE), 'Apple "Store"')
        self.assertEqual(CategoryManager.colors("Everyday Shopping"), original_colors)
        self.assertEqual(json.loads(self.path.read_text())["Locations.APPLE"]["label"], 'Apple "Store"')

    def test_invalid_or_duplicate_renames_leave_preferences_unchanged(self):
        for name in ("", "!!!", "Not Included", "None", " walmart "):
            with self.subTest(name=name), self.assertRaises(ValueError):
                OptionManager.rename(Locations.APPLE, name, Locations)
        self.assertFalse(self.path.exists())
        self.assertEqual(OptionManager.display(Locations.APPLE), "Apple")

    def test_deleted_choices_stay_hidden_after_reload_and_can_be_restored_by_adding_the_name(self):
        OptionManager.rename(Locations.APPLE, "Apple Store", Locations)
        OptionManager.delete(Locations.APPLE)
        OptionManager._loaded_path = None
        self.assertNotIn(Locations.APPLE, OptionManager.available(Locations))
        self.assertEqual(OptionManager.display(Locations.APPLE), "Apple Store")
        self.assertIs(LocationManager.create("Apple Store"), Locations.APPLE)
        self.assertIn(Locations.APPLE, OptionManager.available(Locations))

    def test_category_descriptions_keep_their_scope_after_rename_and_delete(self):
        choices = DescriptionManager.choices(Categories.CAR)
        OptionManager.rename(CarDescriptions.GAS, "Fuel", choices)
        self.assertEqual(DescriptionManager.display("Gas", Categories.CAR), "Fuel")
        self.assertNotIn(CarDescriptions.GAS, DescriptionManager.choices())
        self.assertNotIn(CarDescriptions.GAS, DescriptionManager.choices(Categories.SHOPPING))
        OptionManager.delete(CarDescriptions.GAS)
        self.assertNotIn(CarDescriptions.GAS, DescriptionManager.choices(Categories.CAR))
        self.assertIn(CarDescriptions.GAS, DescriptionManager.choices(Categories.CAR, include_hidden=True))
        self.assertEqual(DescriptionManager.display(CarDescriptions.GAS, Categories.CAR), "Fuel")
        self.assertIs(DescriptionManager.create("Fuel", Categories.CAR), CarDescriptions.GAS)
        self.assertIn(CarDescriptions.GAS, DescriptionManager.choices(Categories.CAR))

    def test_failed_save_preserves_preferences_file_and_runtime_choices(self):
        OptionManager.rename(Locations.APPLE, "Apple Store", Locations)
        original = self.path.read_bytes()
        with patch.object(option_manager.os, "replace", side_effect=OSError("Cannot save")):
            with self.assertRaises(OSError):
                OptionManager.delete(Locations.APPLE)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertIn(Locations.APPLE, OptionManager.available(Locations))
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_hidden_names_and_legacy_category_aliases_cannot_be_reused_by_a_rename(self):
        OptionManager.delete(Locations.APPLE)
        for option, name, choices in ((Locations.MICROSOFT, "Apple", OptionManager.available(Locations)),
                                      (Categories.HOUSING, "Groceries", Categories),
                                      (Categories.HOUSING, "Paycheck", Categories)):
            with self.subTest(name=name), self.assertRaises(ValueError):
                OptionManager.rename(option, name, choices)
        self.assertIs(OptionManager.resolve(Categories, "Groceries"), Categories.SHOPPING)
        self.assertIs(OptionManager.resolve(Categories, "Paycheck"), Categories.INCOME)

    def test_description_rename_checks_hidden_options_in_the_same_category(self):
        OptionManager.delete(CarDescriptions.GAS)
        with self.assertRaises(ValueError):
            OptionManager.rename(Descriptions.OTHER, "Gas", DescriptionManager.choices(Categories.CAR, include_hidden=True))
        self.assertEqual(DescriptionManager.display("Gas", Categories.CAR), "Gas")

    def test_report_group_names_follow_renames_and_preserve_totals_and_classifications(self):
        purchase = FinancialTransaction(Date(29, 9, 2026), DollarAmount(-10), location=Locations.KWIK_TRIP,
                                        category=Categories.CAR, description="Gas", is_essential=IsEssential.ESSENTIAL)
        income = FinancialTransaction(Date(29, 9, 2026), DollarAmount(100), category=Categories.INCOME)
        OptionManager.rename(Categories.CAR, "Transportation", Categories)
        OptionManager.rename(CarDescriptions.GAS, "Fuel", DescriptionManager.choices(Categories.CAR))
        OptionManager.rename(Categories.INCOME, "Earnings", Categories)
        summary = ExpenseSummary.from_rows([*ReceiptGroupManager.rows(purchase), *ReceiptGroupManager.rows(income)])
        self.assertEqual((summary.earned, summary.spent, summary.essential), (10000, 1000, 1000))
        self.assertEqual(dict(summary.essential_categories), {"Transportation": 1000})
        self.assertEqual(dict(summary.essential_descriptions["Transportation"]), {"Fuel": 1000})
        self.assertIs(purchase.category, Categories.CAR)
        self.assertIs(income.category, Categories.INCOME)

    def test_edited_colors_persist_with_renames_and_hidden_options_and_readable_text(self):
        OptionManager.rename(Locations.APPLE, "Apple Store", Locations)
        OptionManager.set_color(Locations.APPLE, "#abcdef")
        OptionManager.delete(Locations.APPLE)
        OptionManager._loaded_path = None
        self.assertEqual(OptionManager.colors(Locations.APPLE), ("#ABCDEF", "#111111"))
        self.assertEqual(OptionManager.display(Locations.APPLE), "Apple Store")
        self.assertNotIn(Locations.APPLE, OptionManager.available(Locations))
        OptionManager.set_color(Locations.APPLE, "#001122")
        self.assertEqual(OptionManager.colors(Locations.APPLE), ("#001122", "#FFFFFF"))
        for color in ("red", "#123", "#GGGGGG"):
            with self.subTest(color=color), self.assertRaises(ValueError):
                OptionManager.set_color(Locations.APPLE, color)

    def test_new_option_colors_avoid_existing_colors_even_when_hidden_and_survive_reload(self):
        options = StrEnum("NewOptions", {"FIRST": "First", "SECOND": "Second", "THIRD": "Third"})
        used = {OptionManager.colors(member)[0] for member in [*Locations, *Categories]}
        OptionManager.set_color(Locations.APPLE, "#EBA2A2")
        OptionManager.delete(Locations.APPLE)
        used.add("#EBA2A2")
        assigned = set()
        for option in options:
            OptionManager.assign_unused_color(option, options)
            color = OptionManager.colors(option)[0]
            self.assertNotIn(color, used | assigned)
            assigned.add(color)
        OptionManager._loaded_path = None
        self.assertEqual({OptionManager.colors(option)[0] for option in options}, assigned)


class OptionManagementWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.path = isolate_preferences(self)
        self.changed = Mock()
        self.table = tk_table_class.TkTable(self.root, columns=[TableColumn("Location", Locations)],
                                          on_location_changed=self.changed, review_style=True)
        self.addCleanup(self.table.destroy)
        self.table.add_row((None,))
        self.table.add_row((Locations.APPLE,))
        self.dropdown = next(widget for widget in self.table._components[0][0].winfo_children()
                             if isinstance(widget, TkOptionDropdown))

    def open_dropdown(self, dropdown=None):
        dropdown = dropdown or self.dropdown
        original = tk.Toplevel

        def invisible_popup(*args, **kwargs):
            popup = original(*args, **kwargs)
            popup.attributes("-alpha", 0)
            return popup

        with patch.object(tk_option_dropdown_class.tk, "Toplevel", side_effect=invisible_popup):
            dropdown._open_dropdown()
        self.root.update_idletasks()
        self.addCleanup(dropdown.close_dropdown)
        return dropdown

    def test_popup_selects_a_row_and_menu_click_does_not_change_the_selection(self):
        dropdown = self.open_dropdown()
        index = list(dropdown.cget("values")).index("Apple")
        with patch.object(tk.Menu, "tk_popup") as post_menu:
            dots = dropdown._menu_buttons[index]
            dots.invoke()
            post_menu.assert_called_once_with(dots.winfo_rootx() + dots.winfo_width(), dots.winfo_rooty())
            self.assertEqual(dropdown._menu.entrycget(0, "label"), "Rename")
            self.assertEqual(dropdown._menu.entrycget(1, "label"), "Edit Color")
            self.assertEqual(dropdown._menu.entrycget(2, "label"), "Delete")
        self.assertEqual(dropdown.get(), "None")
        self.changed.assert_not_called()
        dropdown.close_dropdown()
        dropdown = self.open_dropdown()
        dropdown._choice_buttons[index].invoke()
        self.changed.assert_called_once_with(0, Locations.APPLE)
        self.assertEqual(dropdown.get(), "Apple")
        self.assertIsNone(dropdown._popup)

    def test_menu_rename_updates_other_tables_and_locked_labels_without_reassigning_fields(self):
        other_table = tk_table_class.TkTable(self.root, columns=[TableColumn("Location", Locations)])
        self.addCleanup(other_table.destroy)
        other_table.add_row((None,))
        other_dropdown = next(widget for widget in other_table._components[0][0].winfo_children()
                              if isinstance(widget, TkOptionDropdown))
        self.table._set_enum_value(self.dropdown, 0, Locations.APPLE, self.changed)
        self.changed.reset_mock()
        dropdown = self.open_dropdown()
        index = list(dropdown.cget("values")).index("Apple")
        with patch.object(tk.Menu, "tk_popup"), \
                patch.object(tk_table_class.simpledialog, "askstring", return_value="Apple Store"):
            dropdown._menu_buttons[index].invoke()
            dropdown._menu.invoke(0)
            self.root.update_idletasks()
        self.assertEqual(dropdown.get(), "Apple Store")
        self.assertEqual(self.table._components[1][0].cget("text"), "Apple Store")
        self.assertIn("Apple Store", other_dropdown.cget("values"))
        self.assertNotIn("Apple", other_dropdown.cget("values"))
        self.changed.assert_not_called()

    def test_menu_delete_preserves_selected_values_and_hides_the_option_in_every_dropdown(self):
        self.table._set_enum_value(self.dropdown, 0, Locations.APPLE, self.changed)
        self.changed.reset_mock()
        dropdown = self.open_dropdown()
        index = list(dropdown.cget("values")).index("Apple")
        with patch.object(tk.Menu, "tk_popup"):
            dropdown._menu_buttons[index].invoke()
            dropdown._menu.invoke(2)
            self.root.update_idletasks()
        self.assertEqual(dropdown.get(), "Apple")
        self.assertEqual(self.table._components[1][0].cget("text"), "Apple")
        self.assertNotIn("Apple", dropdown.cget("values"))
        self.changed.assert_not_called()

    def test_locked_dropdown_never_opens_or_manages_options(self):
        self.dropdown.configure(state="disabled")
        dropdown = self.open_dropdown()
        self.assertIsNone(dropdown._popup)
        self.assertEqual(dropdown._choice_buttons, [])
        self.assertEqual(dropdown.get(), "None")
        self.changed.assert_not_called()
        self.table._manage_enum_option(dropdown, Locations, "location", "Apple", "delete")
        self.assertIn("Apple", dropdown.cget("values"))
        self.assertEqual(dropdown.get(), "None")
        self.assertEqual(str(dropdown.cget("state")), "disabled")

    def test_adjacent_button_switches_from_add_to_menu_and_back_as_selection_changes(self):
        cell = self.table._components[0][0]
        button = next(widget for widget in cell.winfo_children() if isinstance(widget, tk.Button))
        self.assertEqual(button.cget("text"), "+")
        self.dropdown.set("Apple")
        self.dropdown.event_generate("<<ComboboxSelected>>")
        self.assertEqual(button.cget("text"), "\u22ee")
        self.table.refresh_enum_cell(cell, Locations, None)
        self.assertEqual(button.cget("text"), "+")

    def test_selected_locked_cell_can_edit_its_option_without_unlocking_or_opening_dropdown(self):
        cell = self.table._components[0][0]
        self.table.refresh_enum_cell(cell, Locations, Locations.APPLE, locked=True)
        button = next(widget for widget in cell.winfo_children() if isinstance(widget, tk.Button))
        self.assertEqual(button.cget("text"), "\u22ee")
        self.assertEqual(str(button.cget("state")), "normal")
        with patch.object(tk.Menu, "tk_popup") as post_menu, \
                patch.object(tk_table_class.colorchooser, "askcolor", return_value=((17, 34, 51), "#112233")):
            button.invoke()
            post_menu.assert_called_once_with(button.winfo_rootx() + button.winfo_width(), button.winfo_rooty())
            self.assertEqual(self.table._selection_menu.entrycget(1, "label"), "Edit Color")
            self.table._selection_menu.invoke(1)
            self.root.update_idletasks()
        self.assertEqual(OptionManager.colors(Locations.APPLE), ("#112233", "#FFFFFF"))
        self.assertEqual(self.dropdown.get(), "Apple")
        self.assertEqual(str(self.dropdown.cget("state")), "disabled")
        self.dropdown._open_dropdown()
        self.assertIsNone(self.dropdown._popup)
        self.changed.assert_not_called()

    def test_locked_location_label_has_a_menu_that_can_rename_and_recolor_its_selection(self):
        label = self.table._components[1][0]
        button = next(widget for widget in label.winfo_children() if isinstance(widget, tk.Button))
        with patch.object(tk.Menu, "tk_popup"), \
                patch.object(tk_table_class.simpledialog, "askstring", return_value="Apple Store"):
            button.invoke()
            self.table._selection_menu.invoke(0)
            self.root.update_idletasks()
        self.assertEqual(label.cget("text"), "Apple Store")
        with patch.object(tk.Menu, "tk_popup"), \
                patch.object(tk_table_class.colorchooser, "askcolor", return_value=((17, 34, 51), "#112233")):
            button.invoke()
            self.table._selection_menu.invoke(1)
            self.root.update_idletasks()
        self.assertEqual(label.cget("bg"), "#112233")
        self.assertEqual(button.cget("bg"), "#112233")
        self.changed.assert_not_called()

    def test_category_and_description_menus_keep_scoped_choices_and_automatic_locks(self):
        table = tk_table_class.TkTable(self.root, columns=[TableColumn("Category", tk.Widget),
                                                         TableColumn("Description", tk.Widget)])
        self.addCleanup(table.destroy)
        category = table.create_enum_cell(0, Categories, "category", CategoryManager.create, None, value=Categories.CAR)
        description = table.create_enum_cell(
            0, Descriptions, "description", lambda name: DescriptionManager.create(name, Categories.CAR), None,
            value=CarDescriptions.GAS, locked=True, choices=lambda: DescriptionManager.choices(Categories.CAR),
        )
        table.add_row((category, description))
        dropdown = next(widget for widget in description.winfo_children() if isinstance(widget, TkOptionDropdown))
        category_dropdown = next(widget for widget in category.winfo_children() if isinstance(widget, TkOptionDropdown))
        OptionManager.rename(CarDescriptions.GAS, "Fuel", DescriptionManager.choices(Categories.CAR))
        self.assertEqual(dropdown.get(), "Fuel")
        self.assertEqual(str(dropdown.cget("state")), "disabled")
        OptionManager.rename(Categories.CAR, "Transportation", Categories)
        self.assertEqual(category_dropdown.get(), "Transportation")
        self.assertIn("Fuel", dropdown.cget("values"))
        self.assertNotIn(CarDescriptions.GAS, DescriptionManager.choices())

    def test_option_rows_and_selected_cells_use_colors_and_menu_edits_update_locked_labels(self):
        self.table._set_enum_value(self.dropdown, 0, Locations.APPLE, self.changed)
        self.changed.reset_mock()
        dropdown = self.open_dropdown()
        index = list(dropdown.cget("values")).index("Apple")
        self.assertEqual(dropdown._choice_buttons[index].cget("bg"), OptionManager.colors(Locations.APPLE)[0])
        self.assertEqual(dropdown._menu_buttons[index].cget("bg"), OptionManager.colors(Locations.APPLE)[0])
        with patch.object(tk.Menu, "tk_popup"), \
                patch.object(tk_table_class.colorchooser, "askcolor", return_value=((0, 17, 34), "#001122")):
            dropdown._menu_buttons[index].invoke()
            dropdown._menu.invoke(1)
            self.root.update_idletasks()
        self.assertEqual(self.table._components[1][0].cget("bg"), "#001122")
        self.assertEqual(dropdown.master.cget("bg"), "#001122")
        self.changed.assert_not_called()
        self.open_dropdown()
        self.assertEqual(dropdown._choice_buttons[index].cget("bg"), "#001122")

    def test_outside_click_closes_dropdown_and_preserves_other_page_bindings(self):
        self.root.attributes("-alpha", 0)
        self.root.geometry("800x700+20+20")
        self.root.deiconify()
        self.addCleanup(self.root.withdraw)
        self.table.pack(fill="both", expand=True)
        outside = tk.Label(self.root, text="Outside")
        outside.pack()
        self.addCleanup(outside.destroy)
        self.root.update()
        callback = Mock()
        binding = self.root.bind("<ButtonPress-1>", callback, add="+")
        self.addCleanup(lambda: self.root.unbind("<ButtonPress-1>", binding))
        dropdown = self.open_dropdown()
        self.assertIsNotNone(dropdown._outside_binding)
        outside.event_generate("<ButtonPress-1>", x=0, y=0)
        self.root.update_idletasks()
        self.assertIsNone(dropdown._popup)
        callback.assert_called_once()
        self.assertIn(binding, self.root.bind("<ButtonPress-1>"))

    def test_is_essential_list_is_colored_and_locked_dropdown_does_not_open(self):
        table = tk_table_class.TkTable(self.root, columns=[TableColumn("Is Essential", IsEssential)])
        self.addCleanup(table.destroy)
        table.add_row((None,))
        dropdown = self.open_dropdown(table._components[0][0])
        self.assertEqual([button.cget("bg") for button in dropdown._choice_buttons],
                         ["#008000", "#FF0000", "#000000"])
        self.assertEqual(dropdown._menu_buttons, [])
        table.refresh_is_essential_cell(0, 0, IsEssential.ESSENTIAL, locked=True)
        self.assertIsNone(dropdown._popup)
        dropdown._open_dropdown()
        self.assertIsNone(dropdown._popup)
