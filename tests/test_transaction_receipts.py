import tkinter as tk
import json
import tempfile
import unittest
from enum import StrEnum
from datetime import date
from pathlib import Path
from tkinter import font, ttk
from unittest.mock import Mock, patch

from classes.custom_tk_components.tk_table_class import TkTable
from classes.custom_tk_components.tk_link_class import TkLink
from classes.custom_tk_components import tk_table_class
from classes.financial_transaction_class import FinancialTransaction
from classes.general.date_class import Date
from classes.general.dollar_amount_class import DollarAmount
from classes.general.time_class import Time
from classes.grocery_item import GroceryItem
from classes.managers import category_manager, description_manager, enum_manager, option_manager
from classes.managers.option_manager import OptionManager
from classes.managers.review_files_manager import ReviewFilesManager
from classes.pages.child_pages import expense_reveiw_page_class
from classes.pages.child_pages.expense_reveiw_pages import final_review_page
from classes.receipt_class import Receipt
from classes.table_column_class import TableColumn
from enums.finances.categories_enum import Categories
from enums.finances.credit_card.credit_card_headers_enum import CreditCardHeaders
from enums.finances.descriptions_enum import Descriptions
from enums.finances.descriptions.car_descriptions_enum import CarDescriptions
from enums.finances.descriptions.housing_descriptions_enum import HousingDescriptions
from enums.finances.descriptions.income_descriptions_enum import IncomeDescriptions
from enums.finances.descriptions.credit_card_descriptions_enum import CreditCardDescriptions
from enums.finances.descriptions.discretionary_spending_descriptions_enum import DiscretionarySpendingDescriptions
from enums.finances.is_essential_enum import IsEssential
from enums.finances.locations_enum import Locations


def make_receipt(location="Walmart", total=2.49, day=29, item_name="Body Wash"):
    return Receipt(
        location=location,
        date=Date(day=day, month=9, year=2026),
        time=Time(hours=11, minutes=6, seconds=6),
        subtotal=2.36,
        taxes=0.13,
        total=total,
        items=[GroceryItem(item_name, 2.36, "https://example.com/body-wash")],
    )


def make_transaction(location=Locations.WALMART, amount=-2.49, day=29, year=2026,
                     receipt=None, purchase_title=None):
    return FinancialTransaction(
        date=Date(day=day, month=9, year=year),
        amount=DollarAmount(amount),
        location=location,
        receipt=receipt,
        purchase_title=purchase_title,
    )


def make_statement_row(title):
    return {
        CreditCardHeaders.TRANS_DATE: "9/29/2026",
        CreditCardHeaders.AMOUNT: -2.49,
        CreditCardHeaders.DESCRIPTION: title,
        CreditCardHeaders.CATEGORY: None,
    }


def isolate_choice_enums(test):
    tests_directory = Path(__file__).resolve().parent
    temporary_directory = tempfile.TemporaryDirectory(prefix="receipt-choices-", dir=tests_directory)
    workspace = Path(temporary_directory.name).resolve()
    if workspace.parent != tests_directory:
        raise RuntimeError("Unexpected temporary directory location.")
    test.addCleanup(temporary_directory.cleanup)
    test.enterContext(patch.object(option_manager, "_OPTIONS_PATH", workspace / "options.json"))
    test.enterContext(patch.object(OptionManager, "_loaded_path", None))
    test.enterContext(patch.object(OptionManager, "_preferences", {}))
    test.enterContext(patch.object(OptionManager, "_listeners", set()))
    choices = {}
    sources = [
        (Categories, category_manager, "_CATEGORIES_ENUM_PATH"),
        (Descriptions, description_manager, "_DESCRIPTIONS_ENUM_PATH"),
    ]
    sources.extend((enum_type, None, None) for enum_type, path
                   in description_manager._CATEGORY_DESCRIPTION_SOURCES.values())
    for enum_type, manager, path_attribute in sources:
        members = {member.name: member.value for member in enum_type}
        isolated_enum = StrEnum(enum_type.__name__, members)
        enum_path = workspace / f"{enum_type.__name__.lower()}_enum.py"
        source = f"from enum import StrEnum\n\nclass {enum_type.__name__}(StrEnum):\n"
        source += "".join(f"    {name} = {value!r}\n" for name, value in members.items())
        enum_path.write_text(source, encoding="utf-8", newline="")
        if manager is not None:
            test.enterContext(patch.object(manager, enum_type.__name__, isolated_enum))
            test.enterContext(patch.object(manager, path_attribute, enum_path))
        if hasattr(final_review_page, enum_type.__name__):
            test.enterContext(patch.object(final_review_page, enum_type.__name__, isolated_enum))
        choices[enum_type.__name__] = (enum_path, isolated_enum)
    isolated_sources = {
        category: (choices[enum_type.__name__][1], choices[enum_type.__name__][0])
        for category, (enum_type, path) in description_manager._CATEGORY_DESCRIPTION_SOURCES.items()
    }
    test.enterContext(patch.object(description_manager, "_CATEGORY_DESCRIPTION_SOURCES", isolated_sources))
    test.enterContext(patch.object(description_manager, "_CATEGORY_ENUM_DIRECTORY", workspace))
    test.enterContext(patch.object(description_manager, "Categories", choices["Categories"][1]))
    test.enterContext(patch.object(tk_table_class, "Categories", choices["Categories"][1]))
    return choices


class DescriptionCategoryTests(unittest.TestCase):
    def test_no_category_offers_only_general_descriptions(self):
        self.assertEqual(description_manager.DescriptionManager.choices(), list(Descriptions))
        self.assertIn(CreditCardDescriptions.PAYMENT,
                      description_manager.DescriptionManager.choices(Categories.CREDIT_CARD))
        self.assertNotIn(CreditCardDescriptions.PAYMENT, description_manager.DescriptionManager.choices())
        self.assertIn(CreditCardDescriptions.CASHBACK,
                      description_manager.DescriptionManager.choices(Categories.CREDIT_CARD))
        self.assertNotIn(CreditCardDescriptions.CASHBACK,
                         description_manager.DescriptionManager.choices(Categories.INCOME))

    def test_income_replaces_paycheck_and_keeps_paycheck_as_a_category_description(self):
        self.assertIs(Categories("Paycheck"), Categories.INCOME)
        self.assertIs(Categories(" paycheck "), Categories.INCOME)
        self.assertIn("Income", list(Categories))
        self.assertNotIn("Paycheck", list(Categories))
        self.assertIn(IncomeDescriptions.PAYCHECK, description_manager.DescriptionManager.choices(Categories.INCOME))
        self.assertIn(IncomeDescriptions.SALARY, description_manager.DescriptionManager.choices(Categories.INCOME))
        self.assertIn(IncomeDescriptions.BONUS, description_manager.DescriptionManager.choices(Categories.INCOME))
        self.assertNotIn("Paycheck", description_manager.DescriptionManager.choices(Categories.CAR))
        self.assertNotIn("Paycheck", list(Descriptions))
        self.assertEqual(category_manager.CategoryManager.colors("Paycheck"),
                         category_manager.CategoryManager.colors(Categories.INCOME))
        enum_path, categories = isolate_choice_enums(self)["Categories"]
        original_source = enum_path.read_bytes()
        self.assertIs(category_manager.CategoryManager.create(" paycheck "), categories.INCOME)
        self.assertEqual(enum_path.read_bytes(), original_source)

    def test_shopping_replaces_groceries_and_preserves_saved_categories_and_descriptions(self):
        self.assertIs(Categories("Groceries"), Categories.SHOPPING)
        self.assertIs(Categories(" groceries "), Categories.SHOPPING)
        self.assertIn("Shopping", list(Categories))
        self.assertNotIn("Groceries", list(Categories))
        self.assertIn("food", description_manager.DescriptionManager.choices(Categories.SHOPPING))
        enum_path, categories = isolate_choice_enums(self)["Categories"]
        original_source = enum_path.read_bytes()
        self.assertIs(category_manager.CategoryManager.create(" groceries "), categories.SHOPPING)
        self.assertEqual(enum_path.read_bytes(), original_source)

    def test_not_included_is_only_an_essential_status_and_cannot_be_added_elsewhere(self):
        isolate_choice_enums(self)
        self.assertNotIn("Not Included", list(Categories))
        self.assertNotIn("Not Included", list(Locations))
        self.assertNotIn("Not Included", description_manager.DescriptionManager.choices())
        self.assertIn("Transfer", description_manager.DescriptionManager.choices(Categories.HOUSING))
        self.assertIn("Not Included", list(IsEssential))
        for create in (category_manager.CategoryManager.create, description_manager.DescriptionManager.create):
            with self.subTest(create=create), self.assertRaisesRegex(ValueError, "Is Essential"):
                create(" not   INCLUDED ")

    def test_each_category_has_an_independent_enum_and_only_its_own_choices(self):
        self.assertLessEqual(set(description_manager._CATEGORY_DESCRIPTION_SOURCES), set(Categories))
        general = {member.value for member in Descriptions}
        for category, (enum_type, path) in description_manager._CATEGORY_DESCRIPTION_SOURCES.items():
            with self.subTest(category=category):
                self.assertTrue(issubclass(enum_type, StrEnum))
                self.assertFalse(issubclass(enum_type, Descriptions))
                self.assertTrue(path.is_file())
                self.assertEqual({member.value for member in description_manager.DescriptionManager.choices(category)},
                                 general | {member.value for member in enum_type})
        self.assertNotIn("Gas", description_manager.DescriptionManager.choices(Categories.SHOPPING))
        self.assertNotIn("food", description_manager.DescriptionManager.choices(Categories.CAR))

    def test_general_additions_are_shared_and_category_additions_stay_specific(self):
        choices = isolate_choice_enums(self)
        manager = description_manager.DescriptionManager
        general = manager.create("Replacement")
        specific = manager.create("Car Wash", Categories.CAR)
        self.assertIs(general, choices["Descriptions"][1].REPLACEMENT)
        self.assertIs(specific, choices["CarDescriptions"][1].CAR_WASH)
        self.assertIn(general, manager.choices(Categories.SHOPPING))
        self.assertNotIn(specific, manager.choices(Categories.SHOPPING))
        self.assertIn(specific, manager.choices(Categories.CAR))
        self.assertNotIn(specific, manager.choices())
        original_source = choices["CarDescriptions"][0].read_bytes()
        self.assertIs(manager.create("replacement", Categories.CAR), general)
        self.assertEqual(choices["CarDescriptions"][0].read_bytes(), original_source)

    def test_new_categories_get_persistent_enums_and_reload_their_descriptions(self):
        isolate_choice_enums(self)
        category = category_manager.CategoryManager.create("Pet Supplies")
        manager = description_manager.DescriptionManager
        self.assertEqual(manager.choices(category), list(description_manager.Descriptions))
        for name in ("", "!!!", "___"):
            with self.assertRaises(ValueError):
                manager.create(name, category)
        self.assertNotIn(category, description_manager._CATEGORY_DESCRIPTION_SOURCES)
        saved = manager.create("Pet Food", category)
        enum_type, path = description_manager._CATEGORY_DESCRIPTION_SOURCES.pop(category)
        namespace = {}
        exec(path.read_text(encoding="utf-8"), namespace)
        self.assertEqual(namespace[enum_type.__name__].PET_FOOD.value, "Pet Food")
        self.assertIn(saved.value, manager.choices(category))
        self.assertNotIn(saved.value, manager.choices(Categories.SHOPPING))
        original_source = path.read_bytes()
        self.assertEqual(manager.create("pet food", category).value, "Pet Food")
        self.assertEqual(path.read_bytes(), original_source)


class ReceiptMatchingTests(unittest.TestCase):
    def test_apple_receipts_match_unique_delayed_charges_even_with_repeated_subscription_amounts(self):
        receipts = [make_receipt(Locations.APPLE, total=16.04, day=1),
                    make_receipt(Locations.APPLE, total=1.06, day=2),
                    make_receipt(Locations.APPLE, total=16.04, day=5),
                    make_receipt(Locations.APPLE, total=13.90, day=5)]
        transactions = [make_transaction(Locations.APPLE, amount=-16.04, day=2),
                        make_transaction(Locations.APPLE, amount=-1.06, day=3),
                        make_transaction(Locations.APPLE, amount=-16.04, day=6),
                        make_transaction(Locations.APPLE, amount=-13.90, day=6),
                        make_transaction(Locations.APPLE, amount=-21.39, day=21)]
        final_review_page._assign_receipts(transactions, list(reversed(receipts)))
        for transaction, receipt in zip(transactions, receipts):
            self.assertIs(transaction.receipt, receipt)
        self.assertIsNone(transactions[-1].receipt)

    def test_apple_delay_matching_prefers_an_exact_match(self):
        earlier = make_receipt(Locations.APPLE, day=28)
        exact = make_receipt(Locations.APPLE, day=29)
        transaction = make_transaction(Locations.APPLE, day=29)
        final_review_page._assign_receipts([transaction], [earlier, exact])
        self.assertIs(transaction.receipt, exact)

    def test_apple_delay_matching_does_not_guess_or_reuse_receipts(self):
        cases = [
            ([make_transaction(Locations.APPLE, day=29), make_transaction(Locations.APPLE, day=30)],
             [make_receipt(Locations.APPLE, day=28)]),
            ([make_transaction(Locations.APPLE, day=30)],
             [make_receipt(Locations.APPLE, day=28), make_receipt(Locations.APPLE, day=29)]),
            ([make_transaction(Locations.APPLE, day=29), make_transaction(Locations.APPLE, day=29)],
             [make_receipt(Locations.APPLE, day=29)]),
        ]
        for transactions, receipts in cases:
            with self.subTest(transactions=len(transactions), receipts=len(receipts)):
                final_review_page._assign_receipts(transactions, receipts)
                self.assertTrue(all(transaction.receipt is None for transaction in transactions))
        receipt = make_receipt(Locations.APPLE, day=28)
        attached = make_transaction(Locations.APPLE, receipt=receipt, day=29)
        unattached = make_transaction(Locations.APPLE, day=30)
        final_review_page._assign_receipts([attached, unattached], [receipt])
        self.assertIs(attached.receipt, receipt)
        self.assertIsNone(unattached.receipt)

    def test_apple_delay_is_limited_to_later_debits_with_the_same_amount_and_merchant(self):
        receipt = make_receipt(Locations.APPLE, day=25)
        valid = make_transaction(Locations.APPLE, day=28)
        final_review_page._assign_receipts([valid], [receipt])
        self.assertIs(valid.receipt, receipt)
        for changes in ({"day": 29}, {"day": 24}, {"amount": 2.49}, {"amount": -2.50},
                        {"year": 2025}, {"location": Locations.WALMART}, {"location": None}):
            with self.subTest(changes=changes):
                values = {"location": Locations.APPLE, "day": 26} | changes
                transaction = make_transaction(**values)
                final_review_page._assign_receipts([transaction], [receipt])
                self.assertIsNone(transaction.receipt)

    def test_apple_delay_uses_calendar_dates_across_month_boundaries(self):
        receipt = make_receipt(Locations.APPLE, day=30)
        transaction = FinancialTransaction(Date(1, 10, 2026), DollarAmount(-2.49), location=Locations.APPLE)
        final_review_page._assign_receipts([transaction], [receipt])
        self.assertIs(transaction.receipt, receipt)

    def test_numbered_receipt_filename_preserves_the_date_and_time(self):
        location, date, time = final_review_page._extract_info_from_receipt_name("Apple_9-5-2026_00-00-00_2")
        self.assertEqual(location, "Apple")
        self.assertEqual((date.year, date.month, date.day), (2026, 9, 5))
        self.assertEqual((time.hours, time.minutes, time.seconds), (0, 0, 0))

    def test_assigns_the_receipt_object_to_a_unique_matching_transaction(self):
        receipt = make_receipt()
        transaction = make_transaction()
        final_review_page._assign_receipts([transaction], [receipt])
        self.assertIs(transaction.receipt, receipt)

    def test_matches_receipt_merchant_aliases(self):
        for name, location in (
            ("Culver's", Locations.CULVERS),
            ("Kwik Star", Locations.KWIK_TRIP),
            ("FreedomBank", Locations.FREEDOM_BANK),
            ("WAL-MART", Locations.WALMART),
        ):
            with self.subTest(name=name):
                receipt = make_receipt(location=name)
                transaction = make_transaction(location=location)
                final_review_page._assign_receipts([transaction], [receipt])
                self.assertIs(transaction.receipt, receipt)

    def test_requires_matching_date_year_total_merchant_and_amount_sign(self):
        for changes in (
            {"day": 28},
            {"year": 2025},
            {"amount": -2.50},
            {"location": Locations.AMAZON},
            {"location": None},
            {"amount": 2.49},
        ):
            with self.subTest(changes=changes):
                transaction = make_transaction(**changes)
                final_review_page._assign_receipts([transaction], [make_receipt()])
                self.assertIsNone(transaction.receipt)

    def test_does_not_guess_between_duplicate_transactions(self):
        transactions = [make_transaction(), make_transaction()]
        final_review_page._assign_receipts(transactions, [make_receipt()])
        self.assertTrue(all(transaction.receipt is None for transaction in transactions))

    def test_does_not_guess_between_receipts_with_the_same_match_details(self):
        transaction = make_transaction()
        final_review_page._assign_receipts([transaction], [make_receipt(), make_receipt()])
        self.assertIsNone(transaction.receipt)

    def test_preserves_existing_attachments_and_does_not_reuse_a_receipt(self):
        receipt = make_receipt()
        attached = make_transaction(receipt=receipt)
        unattached = make_transaction()
        final_review_page._assign_receipts([attached, unattached], [receipt])
        self.assertIs(attached.receipt, receipt)
        self.assertIsNone(unattached.receipt)

    def test_compares_money_in_cents(self):
        receipt = make_receipt(total=0.1 + 0.2)
        transaction = make_transaction(amount=-0.3)
        final_review_page._assign_receipts([transaction], [receipt])
        self.assertIs(transaction.receipt, receipt)


class ReceiptTransactionDefaultsTests(unittest.TestCase):
    def test_income_defaults_to_locked_essential_until_category_changes(self):
        for purchase in (FinancialTransaction(Date(29, 9, 2026), DollarAmount(50)),
                         GroceryItem("Income", 50)):
            with self.subTest(model=type(purchase).__name__):
                purchase.is_essential = IsEssential.NON_ESSENTIAL
                purchase.category = Categories.INCOME
                self.assertIs(purchase.is_essential, IsEssential.ESSENTIAL)
                self.assertTrue(purchase.is_field_locked("is_essential"))
                purchase.is_essential = IsEssential.NON_ESSENTIAL
                self.assertIs(purchase.is_essential, IsEssential.ESSENTIAL)
                purchase.category = Categories.SHOPPING
                self.assertIsNone(purchase.is_essential)
                self.assertFalse(purchase.is_field_locked("is_essential"))

    def test_discover_location_defaults_to_locked_credit_card_for_both_amount_signs(self):
        for amount in (-50, 50):
            with self.subTest(amount=amount):
                purchase = make_transaction(location=Locations.DISCOVER, amount=amount)
                self.assertIs(purchase.category, Categories.CREDIT_CARD)
                self.assertTrue(purchase.is_field_locked("category"))
                manual = make_transaction(location=None, amount=amount)
                manual.location = Locations.DISCOVER
                self.assertIs(manual.category, Categories.CREDIT_CARD)
                self.assertTrue(manual.is_field_locked("category"))

    def test_positive_amounts_do_not_default_to_income_or_override_supplied_categories(self):
        for category in (None, Categories.CAR, Categories.DISCRETIONARY_SPENDING, Categories.INCOME):
            with self.subTest(category=category):
                transaction = FinancialTransaction(Date(29, 9, 2026), DollarAmount(0.01), category=category,
                                                   source=Locations.DISCOVER)
                self.assertIs(transaction.category, category)
                self.assertEqual(transaction.is_field_locked("category"), category is not None)
                transaction.category = Categories.SHOPPING
                self.assertIs(transaction.category, Categories.SHOPPING)
                self.assertFalse(transaction.is_field_locked("category"))
                self.assertIs(transaction.source, Locations.DISCOVER)
        for amount in (0, -0.01):
            with self.subTest(amount=amount):
                transaction = FinancialTransaction(Date(29, 9, 2026), DollarAmount(amount))
                self.assertIsNone(transaction.category)
                self.assertFalse(transaction.is_field_locked("category"))

    def test_discretionary_category_locks_description_and_non_essential_until_changed(self):
        transaction = FinancialTransaction(
            date=Date(day=29, month=9, year=2026), amount=DollarAmount(-2.49),
            category=Categories.DISCRETIONARY_SPENDING, description=Descriptions.OTHER,
            is_essential=IsEssential.ESSENTIAL,
        )
        item = GroceryItem("Snack", 1.50, category=Categories.DISCRETIONARY_SPENDING,
                           is_essential=IsEssential.ESSENTIAL)
        for purchase in (transaction, item):
            with self.subTest(purchase=type(purchase).__name__):
                self.assertIs(purchase.description, DiscretionarySpendingDescriptions.DISCRETIONARY_SPENDING)
                self.assertTrue(purchase.description_is_autocompleted)
                self.assertIs(purchase.is_essential, IsEssential.NON_ESSENTIAL)
                self.assertTrue(purchase.is_essential_is_autocompleted)
                purchase.is_essential = IsEssential.ESSENTIAL
                purchase.category = Categories.DISCRETIONARY_SPENDING
                self.assertIs(purchase.is_essential, IsEssential.NON_ESSENTIAL)
                purchase.category = Categories.SHOPPING
                self.assertIsNone(purchase.description)
                self.assertFalse(purchase.description_is_autocompleted)
                self.assertIsNone(purchase.is_essential)
                self.assertFalse(purchase.is_essential_is_autocompleted)
                purchase.is_essential = IsEssential.ESSENTIAL
                self.assertIs(purchase.is_essential, IsEssential.ESSENTIAL)

    def test_gas_and_gasoline_purchases_default_to_essential_car_expenses(self):
        for location in (Locations.WALMART, Locations.KWIK_TRIP):
            for item_name in ("Gas", "GAS", "Regular gas",
                              "UNL 88 Gasoline (4.670 gal @ $4.249/gal)", "unleaded gasoline"):
                with self.subTest(location=location, item_name=item_name):
                    transaction = make_transaction(location=location,
                                                   receipt=make_receipt(location=location, item_name=item_name))
                    transaction.category = Categories.DISCRETIONARY_SPENDING
                    transaction.is_essential = IsEssential.NON_ESSENTIAL
                    final_review_page._set_transaction_defaults_from_receipts([transaction])
                    self.assertEqual(transaction.description, "Gas")
                    self.assertEqual(transaction.category, Categories.CAR)
                    self.assertEqual(transaction.is_essential, IsEssential.ESSENTIAL)

    def test_kwik_trip_purchases_over_25_without_receipts_default_to_gas(self):
        for amount in (-25.01, -50):
            with self.subTest(amount=amount):
                transaction = make_transaction(location=Locations.KWIK_TRIP, amount=amount)
                transaction.category = Categories.DISCRETIONARY_SPENDING
                transaction.is_essential = IsEssential.NON_ESSENTIAL
                final_review_page._set_transaction_defaults_from_receipts([transaction])
                self.assertIsNone(transaction.receipt)
                self.assertEqual(transaction.description, "Gas")
                self.assertEqual(transaction.category, Categories.CAR)
                self.assertEqual(transaction.is_essential, IsEssential.ESSENTIAL)

    def test_amount_inference_preserves_defaults_outside_eligible_kwik_trip_purchases(self):
        for location, amount, category, essential in (
            (Locations.KWIK_TRIP, -25, Categories.SHOPPING, IsEssential.NON_ESSENTIAL),
            (Locations.KWIK_TRIP, -24.99, Categories.SHOPPING, IsEssential.NON_ESSENTIAL),
            (Locations.KWIK_TRIP, 0, Categories.SHOPPING, IsEssential.NON_ESSENTIAL),
            (Locations.KWIK_TRIP, 50, Categories.SHOPPING, IsEssential.NON_ESSENTIAL),
            (Locations.WALMART, -50, Categories.SHOPPING, IsEssential.NON_ESSENTIAL),
            (Locations.KWIK_TRIP, -50, Categories.SHOPPING, IsEssential.NOT_INCLUDED),
        ):
            with self.subTest(location=location, amount=amount, category=category):
                transaction = make_transaction(location=location, amount=amount)
                transaction.category = category
                transaction.is_essential = essential
                final_review_page._set_transaction_defaults_from_receipts([transaction])
                self.assertIsNone(transaction.description)
                self.assertEqual(transaction.category, category)
                self.assertEqual(transaction.is_essential, essential)

    def test_kwik_trip_receipts_without_gas_default_to_discretionary_non_essential(self):
        for location in ("Kwik Trip", "Kwik Star"):
            for total in (2.49, 50):
                with self.subTest(location=location, total=total):
                    receipt = make_receipt(location=location, total=total, item_name="Glazed donut")
                    transaction = make_transaction(location=Locations.KWIK_TRIP, amount=-total)
                    transaction.category = Categories.SHOPPING
                    transaction.is_essential = IsEssential.ESSENTIAL
                    final_review_page._assign_receipts([transaction], [receipt])
                    final_review_page._set_transaction_defaults_from_receipts([transaction])
                    self.assertIs(transaction.receipt, receipt)
                    self.assertIs(transaction.description, DiscretionarySpendingDescriptions.DISCRETIONARY_SPENDING)
                    self.assertTrue(transaction.description_is_autocompleted)
                    self.assertEqual(transaction.category, Categories.DISCRETIONARY_SPENDING)
                    self.assertEqual(transaction.is_essential, IsEssential.NON_ESSENTIAL)

    def test_kwik_trip_refunds_excluded_payments_and_missing_receipts_preserve_defaults(self):
        for amount, category, essential, receipt in (
            (2.49, Categories.SHOPPING, IsEssential.ESSENTIAL, make_receipt(item_name="Glazed donut")),
            (-2.49, Categories.SHOPPING, IsEssential.NOT_INCLUDED, make_receipt(item_name="Glazed donut")),
            (-2.49, Categories.SHOPPING, IsEssential.ESSENTIAL, None),
        ):
            with self.subTest(amount=amount, category=category, receipt=receipt):
                transaction = make_transaction(location=Locations.KWIK_TRIP, amount=amount, receipt=receipt)
                transaction.category = category
                transaction.is_essential = essential
                final_review_page._set_transaction_defaults_from_receipts([transaction])
                self.assertEqual(transaction.category, category)
                self.assertEqual(transaction.is_essential, essential)

    def test_missing_and_unrelated_receipts_preserve_defaults(self):
        for item_name in (None, "Body Wash", "Las Vegas magnet", "Gasket"):
            with self.subTest(item_name=item_name):
                receipt = None if item_name is None else make_receipt(item_name=item_name)
                transaction = make_transaction(receipt=receipt)
                transaction.category = Categories.SHOPPING
                transaction.is_essential = IsEssential.ESSENTIAL
                final_review_page._set_transaction_defaults_from_receipts([transaction])
                self.assertEqual(transaction.category, Categories.SHOPPING)
                self.assertEqual(transaction.is_essential, IsEssential.ESSENTIAL)

    def test_refunds_deposits_and_excluded_payments_preserve_defaults(self):
        for amount, category, essential in (
            (2.49, Categories.CAR, IsEssential.NOT_INCLUDED),
            (2.49, Categories.SHOPPING, IsEssential.NOT_INCLUDED),
            (0, Categories.SHOPPING, IsEssential.NON_ESSENTIAL),
            (-2.49, Categories.SHOPPING, IsEssential.NOT_INCLUDED),
        ):
            with self.subTest(amount=amount, category=category):
                transaction = make_transaction(amount=amount, receipt=make_receipt(item_name="Gas"))
                transaction.category = category
                transaction.is_essential = essential
                final_review_page._set_transaction_defaults_from_receipts([transaction])
                self.assertEqual(transaction.category, category)
                self.assertEqual(transaction.is_essential, essential)


class ReceiptImportTests(unittest.TestCase):
    def test_import_keeps_the_original_json_contents_for_manual_attachment_preview(self):
        data = {"general": {"subtotal": 2, "tax": 0, "total": 2, "order_number": "Test order"},
                "items": [{"name": "Original item", "price": 2, "category": "Groceries", "notes": "Original notes"}]}
        with patch.object(final_review_page.FileManager, "get_files_at_location",
                          return_value=["Walmart_9-29-2026.json"]), \
                patch.object(final_review_page.JsonManager, "open", return_value=data):
            receipt, = final_review_page._import_receipts()
        self.assertIs(receipt.items[0].category, Categories.SHOPPING)
        self.assertEqual(receipt.source_file_name, "Walmart_9-29-2026.json")
        self.assertEqual(json.loads(receipt.raw_contents), data)
        receipt.items[0].description = Descriptions.OTHER
        self.assertEqual(json.loads(receipt.raw_contents), data)

    def test_legacy_paycheck_receipts_load_as_income_with_paycheck_description(self):
        data = {"general": {"subtotal": 2, "tax": 0, "total": 2}, "items": [
            {"name": "Legacy paycheck", "price": 1, "category": "Paycheck"},
            {"name": "Legacy bonus", "price": 1, "category": "Paycheck", "description": "Bonus"},
        ]}
        with patch.object(final_review_page.FileManager, "get_files_at_location",
                          return_value=["Walmart_9-29-2026.json"]), \
                patch.object(final_review_page.JsonManager, "open", return_value=data):
            receipt, = final_review_page._import_receipts()
        self.assertTrue(all(item.category is Categories.INCOME for item in receipt.items))
        self.assertEqual([item.description for item in receipt.items], [IncomeDescriptions.PAYCHECK, "Bonus"])
        self.assertTrue(all(item.is_field_locked("category") and item.is_field_locked("description")
                            for item in receipt.items))

    def test_legacy_not_included_category_moves_to_essential_status(self):
        data = {"general": {"subtotal": 1, "tax": 0, "total": 1},
                "items": [{"name": "Transfer", "price": 1, "category": "Not Included"}]}
        with patch.object(final_review_page.FileManager, "get_files_at_location",
                          return_value=["Walmart_9-29-2026.json"]), \
                patch.object(final_review_page.JsonManager, "open", return_value=data):
            receipt, = final_review_page._import_receipts()
        self.assertIsNone(receipt.items[0].category)
        self.assertIs(receipt.items[0].is_essential, IsEssential.NOT_INCLUDED)

    def test_import_preserves_quantities_and_optional_item_classifications(self):
        data = {
            "general": {"subtotal": 8.96, "tax": 0, "total": 8.96},
            "items": [
                {"name": "Body Wash", "price": 2.36, "quantity": 3,
                 "category": "Groceries", "is_essential": "Essential", "description": "Gas"},
                {"name": "Produce", "price": 2, "quantity": 0.5},
                {"name": "Legacy item", "price": 0.88},
            ],
        }
        with patch.object(final_review_page.FileManager, "get_files_at_location",
                          return_value=["Walmart_9-29-2026.json"]), \
                patch.object(final_review_page.JsonManager, "open", return_value=data):
            receipt, = final_review_page._import_receipts()

        self.assertEqual([item.quantity for item in receipt.items], [3, 0.5, 1])
        self.assertAlmostEqual(receipt.items[0].cost, 7.08)
        self.assertEqual(receipt.items[1].cost, 1)
        self.assertEqual(receipt.items[2].cost, 0.88)
        self.assertIs(receipt.items[0].category, Categories.SHOPPING)
        self.assertIs(receipt.items[0].is_essential, IsEssential.ESSENTIAL)
        self.assertEqual(receipt.items[0].description, "Gas")
        self.assertIsNone(receipt.items[2].category)
        self.assertIsNone(receipt.items[2].is_essential)
        self.assertIsNone(receipt.items[2].description)


class ReceiptViewerTests(unittest.TestCase):
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
        workspace = self.enterContext(tempfile.TemporaryDirectory(prefix="receipt-view-options-", dir=Path(__file__).parent))
        self.workspace = Path(workspace)
        self.enterContext(patch.object(option_manager, "_OPTIONS_PATH", Path(workspace) / "options.json"))
        self.enterContext(patch.object(OptionManager, "_loaded_path", None))
        self.enterContext(patch.object(OptionManager, "_preferences", {}))
        self.enterContext(patch.object(OptionManager, "_listeners", set()))
        self.enterContext(patch.object(tk.Menu, "tk_popup"))
        self.page = final_review_page.FinalReviewPage(self.root, Mock())
        self.month_directory = Path(workspace) / "backup" / "September"
        self.enterContext(patch.object(final_review_page.ReceiptBackupManager, "review_directory",
                                       return_value=self.month_directory))
        self.copy_supporting_documents = final_review_page.ReceiptBackupManager.copy_supporting_documents
        self.generate_report = final_review_page.ExpenseReviewReport.generate
        self.receipt_backup = self.enterContext(patch.object(final_review_page.ReceiptBackupManager,
                                                          "copy_supporting_documents"))
        self.expense_report = self.enterContext(patch.object(final_review_page.ExpenseReviewReport, "generate"))

    def tearDown(self):
        self.page._root.destroy()

    def hidden_popup(self, *args, **kwargs):
        window = self.toplevel_type(*args, **kwargs)
        window.withdraw()
        return window

    def label_texts(self, window):
        texts = []
        widgets = [window]
        while widgets:
            widget = widgets.pop()
            if isinstance(widget, tk.Label):
                texts.append(widget.cget("text"))
            widgets.extend(widget.winfo_children())
        return texts

    def receipt_table(self, window):
        return next(widget for widget in window.winfo_children() if isinstance(widget, TkTable))

    def enum_controls(self, cell):
        dropdown = next(widget for widget in cell.winfo_children() if isinstance(widget, ttk.Combobox))
        button = next(widget for widget in cell.winfo_children() if isinstance(widget, tk.Button))
        return dropdown, button

    def test_hidden_column_defaults_green_and_can_hide_unhide_and_survive_table_refresh(self):
        purchase = make_transaction()
        self.page._transactions = [purchase]
        self.page._setup_components()
        table = self.page._transaction_table
        self.assertEqual(table.columns[-1].text, "Hidden")
        checkbox = table._components[0][8]
        self.assertIsInstance(checkbox, tk.Checkbutton)
        self.assertFalse(purchase.hidden)
        self.assertEqual(checkbox.cget("bg"), "#008000")
        checkbox.invoke()
        self.assertTrue(purchase.hidden)
        self.assertEqual(checkbox.cget("bg"), "#FF0000")
        self.assertEqual(purchase.amount, -2.49)
        self.assertFalse(purchase.excluded_from_totals)
        self.page._refresh_transaction_table()
        checkbox = self.page._transaction_table._components[0][8]
        self.assertTrue(self.page._hidden_variables[0].get())
        self.assertEqual(checkbox.cget("bg"), "#FF0000")
        checkbox.invoke()
        self.assertFalse(purchase.hidden)
        self.assertEqual(checkbox.cget("bg"), "#008000")

    def test_hidden_toggle_synchronizes_all_rows_of_a_split_purchase_and_survives_receipt_changes(self):
        receipt = make_receipt(total=30)
        receipt.items[:] = [GroceryItem("A", 10, is_essential=IsEssential.ESSENTIAL),
                            GroceryItem("B", 20, is_essential=IsEssential.NON_ESSENTIAL)]
        purchase = make_transaction(amount=-30, receipt=receipt)
        other = make_transaction()
        self.page._transactions = [purchase, other]
        self.page._setup_components()
        self.assertEqual(len(self.page._transaction_rows), 3)
        self.page._transaction_table._components[1][8].invoke()
        self.assertTrue(purchase.hidden)
        self.assertFalse(other.hidden)
        self.assertEqual([variable.get() for variable in self.page._hidden_variables.values()], [True, True, False])
        self.assertTrue(all(row.transaction.hidden for row in self.page._transaction_rows[:2]))
        self.page._receipt_changed(receipt)
        self.assertEqual([variable.get() for variable in self.page._hidden_variables.values()], [True, True, False])
        self.page._transaction_table._components[0][8].invoke()
        self.assertFalse(purchase.hidden)
        self.assertEqual([variable.get() for variable in self.page._hidden_variables.values()], [False, False, False])
        self.assertEqual(sum(round(row.transaction.amount * 100) for row in self.page._transaction_rows), -3249)

    def test_finalize_passes_hidden_receipt_files_to_backup_but_keeps_all_rows_for_report_calculations(self):
        hidden_receipt = Receipt("Apple", Date(2, 9, 2026), None, 5, 0, 5, [GroceryItem("Private item", 5)],
                                 source_file_name="Apple_9-2-2026_00-00-00.json")
        hidden_purchase = FinancialTransaction(Date(2, 9, 2026), DollarAmount(-5), location=Locations.APPLE,
                                               category=Categories.SHOPPING, description=Descriptions.OTHER,
                                               is_essential=IsEssential.ESSENTIAL, receipt=hidden_receipt)
        self.page._transactions = [hidden_purchase]
        self.page._receipts = [hidden_receipt]
        self.page._setup_components()
        self.page._transaction_table._components[0][8].invoke()
        with patch.object(final_review_page.messagebox, "askyesno", return_value=True):
            self.page._finalize_button.invoke()
        self.receipt_backup.assert_called_once_with(final_review_page.Paths.RECEIPTS, final_review_page.Paths.ASSETS_PDFS,
                                                    excluded_file_names={hidden_receipt.source_file_name},
                                                    destination=self.month_directory / "Supporting Documents", overwrite=False)
        self.expense_report.assert_called_once_with(self.month_directory / "Expense Review.pdf",
                                                   self.page._transaction_rows, self.page._receipts, overwrite=False)
        self.assertEqual(self.page._transaction_rows[0].transaction.amount, -5)
        self.page._parent_next_method.assert_called_once_with()

    def descendants(self, window):
        widgets = list(window.winfo_children())
        result = []
        while widgets:
            widget = widgets.pop()
            result.append(widget)
            widgets.extend(widget.winfo_children())
        return result

    def open_receipt_picker(self, purchase):
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            return self.page._show_receipt_picker(purchase)

    def open_attachment_preview(self, picker, row=0):
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            self.receipt_picker_card(picker, row)[1].invoke()
        return next(widget for widget in picker.winfo_children() if isinstance(widget, self.toplevel_type))

    def receipt_picker_card(self, picker, row=0):
        card = self.receipt_table(picker)._components[row][0]
        metadata = next(widget for widget in card.winfo_children()
                        if isinstance(widget, tk.Frame) and any(isinstance(child, tk.Label) for child in widget.winfo_children()))
        view = next(widget for widget in card.winfo_children() if isinstance(widget, tk.Button))
        return metadata, view

    def attach_button(self, preview):
        return next(widget for widget in self.descendants(preview)
                    if isinstance(widget, tk.Button) and widget.cget("text") == "Attach Receipt to Purchase")

    def test_matching_receipts_enable_plus_only_for_matching_unattached_rows(self):
        attached = make_receipt()
        attached.items[:] = [GroceryItem("Essential", 1, category=Categories.SHOPPING,
                                        description=Descriptions.OTHER, is_essential=IsEssential.ESSENTIAL),
                             GroceryItem("Nonessential", 1.36, category=Categories.SHOPPING,
                                         description=Descriptions.OTHER, is_essential=IsEssential.NON_ESSENTIAL)]
        remaining = make_receipt(location=Locations.APPLE)
        existing = make_transaction(receipt=attached)
        bank = make_transaction(Locations.FREEDOM_BANK)
        income = make_transaction(amount=2.49)
        income.category = Categories.INCOME
        other = make_transaction(location=None)
        unmatched = make_transaction(amount=-7)
        self.page._receipts = [attached, remaining]
        self.page._transactions = [existing, bank, income, other, unmatched]
        self.page._setup_components()
        self.assertEqual(self.page._unassigned_receipts(), [remaining])
        cells = [row[7] for row in self.page._transaction_table._components]
        self.assertEqual([cell.cget("text") for cell in cells], ["View Receipt", "View Receipt", "+", "+", "+", ""])
        self.assertIsInstance(cells[-1], tk.Label)
        self.assertEqual(cells[-1].cget("bg"), "black")
        self.assertIsNone(self.page._show_receipt_picker(unmatched))
        bank.receipt = remaining
        self.page._refresh_transaction_table()
        self.assertEqual(self.page._unassigned_receipts(), [])
        self.assertEqual([row[7].cget("text") for row in self.page._transaction_table._components],
                         ["View Receipt", "View Receipt", "View Receipt", "", "", ""])
        self.assertTrue(all(row[7].cget("bg") == "black" for row in self.page._transaction_table._components[3:]))
        self.assertIsNone(self.page._show_receipt_picker(other))

    def test_plus_lists_only_matching_unassigned_receipts_and_attachment_refreshes_matching_rows(self):
        assigned = make_receipt(location=Locations.AMAZON, total=1.06)
        available = make_receipt(location=Locations.APPLE, total=1.06)
        unmatched = make_receipt(total=7)
        original_data = {"general": {"subtotal": .99, "tax": .07, "total": 1.06},
                         "items": [{"name": "iCloud+", "price": .99, "quantity": 1}], "order_number": "Test order"}
        available._raw_contents = json.dumps(original_data, indent=2)
        available._subtotal, available._taxes = .99, .07
        available.items[:] = [GroceryItem("iCloud+", .99)]
        attached = make_transaction(Locations.AMAZON, amount=-1.06, receipt=assigned)
        target = make_transaction(location=None, amount=-1.06, purchase_title="Unmatched purchase")
        other_target = make_transaction(amount=-1.06)
        self.page._receipts = [available, assigned, unmatched]
        self.page._transactions = [attached, target, other_target]
        self.page._setup_components()
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            self.page._transaction_table._components[1][7].invoke()
        picker = next(widget for widget in self.page._root.winfo_children() if isinstance(widget, self.toplevel_type))
        rows = self.receipt_table(picker)._components
        self.assertEqual(len(rows), 1)
        metadata, view = self.receipt_picker_card(picker)
        self.assertEqual(set(self.label_texts(metadata)),
                         {"Date: 9/29/2026", "Time: 11:06:06 AM", "Location: Apple", "Total: $1.06"})
        self.assertLess(metadata.grid_info()["column"], view.grid_info()["column"])
        preview = self.open_attachment_preview(picker)
        preview_table = self.receipt_table(preview)
        self.assertEqual([column.text for column in preview_table.columns], ["Item", "Quantity", "Unit Price"])
        self.assertEqual([cell.cget("text") for cell in preview_table._components[0]],
                         ["iCloud+", "1", "-$0.99"])
        self.assertIn("Subtotal: $0.99", self.label_texts(preview))
        self.assertIn("Tax: $0.07", self.label_texts(preview))
        self.assertIn("Total: $1.06", self.label_texts(preview))
        self.assertIsNone(target.receipt)
        self.attach_button(preview).invoke()
        self.assertIs(target.receipt, available)
        self.assertIs(attached.receipt, assigned)
        self.assertFalse(picker.winfo_exists())
        self.assertFalse(preview.winfo_exists())
        self.assertEqual(self.page._unassigned_receipts(), [unmatched])
        self.assertEqual(self.page._transaction_table._components[1][7].cget("text"), "View Receipt")
        self.assertEqual(self.page._transaction_table._components[1][1].cget("text"), "11:06 AM")
        self.assertEqual(target.amount, -1.06)
        self.assertEqual(self.page._transaction_table._components[2][7].cget("bg"), "black")
        self.assertIsNone(self.page._show_receipt_picker(other_target))
        self.assertIsNone(target.location)
        self.assertIsNone(target.category)
        self.assertIsNone(target.description)
        self.assertIsNone(target.is_essential)
        with patch.object(self.page, "_show_receipt") as show:
            self.page._transaction_table._components[1][7].invoke()
            show.assert_called_once_with(available, target)

    def test_attachment_preview_shows_readonly_base_fields_and_closing_leaves_receipts_available(self):
        available = make_receipt(total=7.54)
        available._subtotal, available._taxes = 7.08, .46
        available.items[:] = [GroceryItem("Body Wash", 2.36, "https://example.com/body-wash", quantity=3)]
        available._time = None
        target = make_transaction(amount=-7.54)
        self.page._receipts = [available]
        self.page._transactions = [target]
        self.page._setup_components()
        picker = self.open_receipt_picker(target)
        self.assertIn("Time: Not provided", self.label_texts(picker))
        preview = self.open_attachment_preview(picker)
        row, = self.receipt_table(preview)._components
        self.assertEqual([cell.cget("text") for cell in row], ["Body Wash", "3", "-$2.36"])
        self.assertIsInstance(row[0], TkLink)
        self.assertEqual(row[0]._url, "https://example.com/body-wash")
        self.assertTrue(all(isinstance(cell, tk.Label) for cell in row))
        self.assertFalse(any(isinstance(widget, (ttk.Combobox, tk.Checkbutton, tk.Text))
                             for widget in self.descendants(preview)))
        self.assertIn("Time: Not provided", self.label_texts(preview))
        self.close_receipt(preview)
        self.assertTrue(picker.winfo_exists())
        preview = self.open_attachment_preview(picker)
        self.close_receipt(picker)
        self.assertFalse(preview.winfo_exists())
        self.assertIsNone(target.receipt)
        self.assertEqual(self.page._unassigned_receipts(), [available])
        self.assertEqual(self.page._transaction_table._components[0][7].cget("text"), "+")

    def test_attachment_refuses_reusing_a_receipt_from_a_stale_picker(self):
        available = make_receipt()
        first, second = make_transaction(), make_transaction()
        self.page._receipts = [available]
        self.page._transactions = [first, second]
        self.page._setup_components()
        first_picker = self.open_receipt_picker(first)
        second_picker = self.open_receipt_picker(second)
        first_preview = self.open_attachment_preview(first_picker)
        second_preview = self.open_attachment_preview(second_picker)
        self.attach_button(first_preview).invoke()
        with patch.object(final_review_page.messagebox, "showwarning") as warning:
            self.attach_button(second_preview).invoke()
            warning.assert_called_once()
        self.assertIs(first.receipt, available)
        self.assertIsNone(second.receipt)
        self.close_receipt(second_picker)

    def test_attachment_does_not_replace_a_receipt_that_was_assigned_after_opening_the_picker(self):
        available, other = make_receipt(), make_receipt(total=7)
        target = make_transaction()
        self.page._receipts = [available, other]
        self.page._transactions = [target]
        self.page._setup_components()
        picker = self.open_receipt_picker(target)
        preview = self.open_attachment_preview(picker)
        target.receipt = other
        with patch.object(final_review_page.messagebox, "showwarning") as warning:
            self.attach_button(preview).invoke()
            warning.assert_called_once()
        self.assertIs(target.receipt, other)
        self.assertEqual(self.page._unassigned_receipts(), [available])
        self.close_receipt(picker)

    def test_receipt_picker_scrolls_over_receipt_metadata_and_fits_the_view_buttons(self):
        target = make_transaction()
        self.page._receipts = [make_receipt(day=i + 1) for i in range(20)]
        self.page._transactions = [target]
        self.page._setup_components()
        picker = self.open_receipt_picker(target)
        picker.transient("")
        picker.attributes("-alpha", 0)
        picker.deiconify()
        picker.geometry("600x350")
        picker.update()
        table = self.receipt_table(picker)
        self.assertEqual(len(table._components), 20)
        self.assertLess(table._canvas.yview()[1], 1)
        metadata, view = self.receipt_picker_card(picker)
        self.assertGreater(view.winfo_x(), metadata.winfo_x())
        label = metadata.winfo_children()[0]
        label.event_generate("<MouseWheel>", delta=-120)
        self.assertGreater(table._canvas.yview()[0], 0)
        self.close_receipt(picker)

    def test_receipt_price_matching_uses_cents_and_rejects_a_one_cent_difference(self):
        matching, different = make_receipt(total=.30), make_receipt(total=.31)
        target = make_transaction(amount=-(.1 + .2))
        self.page._receipts = [matching, different]
        self.page._transactions = [target]
        self.assertEqual(self.page._matching_unassigned_receipts(target), [matching])

    def test_attachment_rechecks_the_price_after_opening_the_preview(self):
        available = make_receipt()
        target = make_transaction()
        self.page._receipts = [available]
        self.page._transactions = [target]
        self.page._setup_components()
        picker = self.open_receipt_picker(target)
        preview = self.open_attachment_preview(picker)
        available._total = 2.50
        with patch.object(final_review_page.messagebox, "showwarning") as warning, \
                patch.object(self.page, "_refresh_transaction_table") as refresh:
            self.attach_button(preview).invoke()
            warning.assert_called_once()
            self.assertIn("total must match", warning.call_args.args[1])
            refresh.assert_not_called()
        self.assertIsNone(target.receipt)
        self.assertTrue(picker.winfo_exists())
        self.assertTrue(preview.winfo_exists())
        self.close_receipt(picker)

    def assert_category_colors(self, cell, category):
        dropdown, button = self.enum_controls(cell)
        background, foreground = category_manager.CategoryManager.colors(category) or ("#FFFFFF", "#111111")
        style = ttk.Style(self.root)
        state = (str(dropdown.cget("state")),)
        self.assertEqual(style.lookup(dropdown.cget("style"), "fieldbackground", state), background)
        self.assertEqual(style.lookup(dropdown.cget("style"), "foreground", state), foreground)
        self.assertEqual(cell.cget("bg"), background)
        self.assertEqual(button.cget("bg"), background)

    def test_category_colors_update_in_main_receipt_and_inherited_cells(self):
        theme = ttk.Style(self.root).theme_use()
        receipt = make_receipt()
        transaction = make_transaction(receipt=receipt)
        self.page._transactions = [transaction]
        self.page._setup_components()
        cell = self.page._transaction_table._components[0][4]
        dropdown, _ = self.enum_controls(cell)
        self.assert_category_colors(cell, None)
        for category in (Categories.SHOPPING, Categories.CAR):
            dropdown.set(str(category))
            dropdown.event_generate("<<ComboboxSelected>>")
            self.assert_category_colors(cell, category)
        window = self.open_receipt(receipt, transaction)
        inherited = self.receipt_table(window)._components[0][3]
        self.assertEqual(str(self.enum_controls(inherited)[0].cget("state")), "disabled")
        self.assert_category_colors(inherited, Categories.CAR)
        self.close_receipt(window)
        editable = self.open_receipt(make_receipt())
        receipt_cell = self.receipt_table(editable)._components[0][3]
        receipt_dropdown, _ = self.enum_controls(receipt_cell)
        receipt_dropdown.set("Housing")
        receipt_dropdown.event_generate("<<ComboboxSelected>>")
        self.assert_category_colors(receipt_cell, Categories.HOUSING)
        self.assertEqual(ttk.Style(self.root).theme_use(), theme)

    def test_payroll_income_and_credit_card_cashback_defaults_are_locked_and_essential(self):
        credit = make_statement_row("CASHBACK BONUS REDEMPTION PYMT/STMT CRDT")
        credit[CreditCardHeaders.AMOUNT] = -5.77
        cashback = final_review_page._create_financial_transaction_object(credit, invert_amount=True,
                                                                         source=Locations.DISCOVER)
        payroll = make_statement_row("WALMART ASSOCS,PAYROLL")
        payroll[CreditCardHeaders.AMOUNT] = 1000
        paycheck = final_review_page._create_financial_transaction_object(payroll, source=Locations.FREEDOM_BANK)
        self.page._transactions = [cashback, paycheck]
        self.page._setup_components()
        table = self.page._transaction_table
        for row, category in zip(table._components, (Categories.CREDIT_CARD, Categories.INCOME)):
            self.assertIsInstance(row[4], tk.Label)
            self.assertEqual(row[4].cget("text"), str(category))
            self.assertEqual((row[4].cget("bg"), row[4].cget("fg")),
                             category_manager.CategoryManager.colors(category))
            self.assertIsInstance(row[6], tk.Label)
            self.assertEqual(row[6].cget("text"), "Essential")
            self.assertEqual(row[6].cget("bg"), "green")
        self.page._set_transaction_category(0, Categories.SHOPPING)
        self.assertIs(cashback.category, Categories.CREDIT_CARD)
        description, _ = self.enum_controls(table._components[0][5])
        self.assertEqual(str(description.cget("state")), "disabled")
        self.assertEqual(description.get(), "Cashback")
        self.assertIn("Payment", description.cget("values"))
        self.assertNotIn("Paycheck", description.cget("values"))
        self.assertNotIn("Gas", description.cget("values"))
        self.assertNotIn("food", description.cget("values"))
        description.set("Bonus")
        description.event_generate("<<ComboboxSelected>>")
        self.assertIs(cashback.description, CreditCardDescriptions.CASHBACK)
        self.assertTrue(cashback.is_field_locked("description"))
        description, add = self.enum_controls(table._components[1][5])
        self.assertEqual(description.get(), "Paycheck")
        self.assertEqual(str(description.cget("state")), "disabled")
        self.assertEqual(str(add.cget("state")), "normal")
        self.page._set_transaction_description(1, IncomeDescriptions.BONUS)
        self.assertIs(paycheck.description, IncomeDescriptions.PAYCHECK)

    def test_discover_colors_apply_to_imported_and_manually_selected_locations(self):
        imported = final_review_page._create_financial_transaction_object(
            make_statement_row("CASHBACK BONUS REDEMPTION PYMT/STMT CRDT"), source=Locations.DISCOVER)
        manual = make_transaction(location=None)
        self.page._transactions = [imported, manual]
        self.page._setup_components()
        background, foreground = tk_table_class.get_location_colors(Locations.DISCOVER)
        table = self.page._transaction_table
        location = table._components[0][2]
        self.assertEqual(location.cget("bg"), background)
        self.assertEqual(location.cget("fg"), foreground)
        dropdown, button = self.enum_controls(table._components[1][2])
        dropdown.set("Discover")
        dropdown.event_generate("<<ComboboxSelected>>")
        self.assertIs(manual.location, Locations.DISCOVER)
        dropdown, button = self.enum_controls(self.page._transaction_table._components[1][2])
        self.assertIs(manual.category, Categories.CREDIT_CARD)
        self.assertTrue(manual.is_field_locked("category"))
        self.assertEqual(ttk.Style(self.root).lookup(dropdown.cget("style"), "fieldbackground", ("readonly",)),
                         background)
        self.assertEqual(button.cget("bg"), background)

    def test_is_essential_dropdown_colors_follow_selections_autofills_and_lock_states(self):
        theme = ttk.Style(self.root).theme_use()
        transaction = make_transaction()
        self.page._transactions = [transaction]
        self.page._setup_components()
        table = self.page._transaction_table
        dropdown = table._components[0][6]
        style = ttk.Style(self.root)

        def assert_colors(background, foreground):
            state = (str(dropdown.cget("state")),)
            self.assertEqual(style.lookup(dropdown.cget("style"), "fieldbackground", state), background)
            self.assertEqual(style.lookup(dropdown.cget("style"), "foreground", state), foreground)
            self.assertEqual(table._canvas.cget("bg"), "white")

        assert_colors("#FFFFFF", "#111111")
        for value, background, foreground in ((IsEssential.ESSENTIAL, "#008000", "#FFFFFF"),
                                               (IsEssential.NON_ESSENTIAL, "#FF0000", "#111111"),
                                               (IsEssential.NOT_INCLUDED, "#000000", "#FFFFFF")):
            dropdown.set(str(value))
            dropdown.event_generate("<<ComboboxSelected>>")
            self.assertIs(transaction.is_essential, value)
            assert_colors(background, foreground)
        dropdown.set("Essential")
        dropdown.event_generate("<<ComboboxSelected>>")
        category, _ = self.enum_controls(table._components[0][4])
        category.set("Discretionary Spending")
        category.event_generate("<<ComboboxSelected>>")
        self.assertEqual(str(dropdown.cget("state")), "disabled")
        assert_colors("#FF0000", "#111111")
        self.page._set_transaction_is_essential(0, IsEssential.NOT_INCLUDED)
        self.assertIs(transaction.is_essential, IsEssential.NON_ESSENTIAL)
        assert_colors("#FF0000", "#111111")
        category.set("Shopping")
        category.event_generate("<<ComboboxSelected>>")
        self.assertEqual(str(dropdown.cget("state")), "readonly")
        assert_colors("#FFFFFF", "#111111")
        self.assertEqual(style.theme_use(), theme)

    def test_every_initial_main_classification_is_locked_including_excluded_rows(self):
        transaction = FinancialTransaction(Date(29, 9, 2026), DollarAmount(-5),
            location=Locations.FREEDOM_BANK, category=Categories.HOUSING,
            description=Descriptions.TRANSFER, is_essential=IsEssential.NOT_INCLUDED,
            source=Locations.FREEDOM_BANK)
        self.page._transactions = [transaction]
        self.page._setup_components()
        row = self.page._transaction_table._components[0]
        for column in (0, 1, 2, 3, 4, 6):
            self.assertIsInstance(row[column], tk.Label)
        description, add = self.enum_controls(row[5])
        self.assertEqual(str(description.cget("state")), "disabled")
        self.assertEqual(str(add.cget("state")), "normal")
        self.page._set_transaction_location(0, Locations.AMAZON)
        self.page._set_transaction_category(0, Categories.SHOPPING)
        self.page._set_transaction_description(0, Descriptions.OTHER)
        self.page._set_transaction_is_essential(0, IsEssential.ESSENTIAL)
        self.assertIs(transaction.location, Locations.FREEDOM_BANK)
        self.assertIs(transaction.category, Categories.HOUSING)
        self.assertIs(transaction.description, Descriptions.TRANSFER)
        self.assertIs(transaction.is_essential, IsEssential.NOT_INCLUDED)
        self.page._refresh_transaction_table()
        description, add = self.enum_controls(self.page._transaction_table._components[0][5])
        self.assertEqual(str(description.cget("state")), "disabled")

    def test_initial_receipt_classifications_stay_locked_without_save_after_reopen(self):
        receipt = make_receipt()
        item = GroceryItem("Classified item", 2.36, category=Categories.SHOPPING,
                           description=Descriptions.OTHER, is_essential=IsEssential.ESSENTIAL)
        receipt.items[:] = [item]
        for _ in range(2):
            window = self.open_receipt(receipt)
            row = self.receipt_table(window)._components[0]
            for column in (3, 4):
                dropdown, add = self.enum_controls(row[column])
                self.assertEqual(str(dropdown.cget("state")), "disabled")
                self.assertEqual(str(add.cget("state")), "normal")
                with patch.object(tk_table_class.simpledialog, "askstring") as ask:
                    add.invoke()
                    ask.assert_not_called()
            self.assertEqual(str(row[5].cget("state")), "disabled")
            row[5].invoke()
            self.assert_no_save(window)
            self.close_receipt(window)
        self.assertIs(item.category, Categories.SHOPPING)
        self.assertIs(item.description, Descriptions.OTHER)
        self.assertIs(item.is_essential, IsEssential.ESSENTIAL)

    def test_later_automatic_values_lock_after_rebuilding_the_main_table(self):
        transaction = make_transaction(location=None)
        self.page._transactions = [transaction]
        self.page._setup_components()
        transaction.autocomplete_field("location", Locations.FREEDOM_BANK)
        transaction.autocomplete_field("category", Categories.HOUSING)
        transaction.autocomplete_field("description", Descriptions.TRANSFER)
        transaction.autocomplete_field("is_essential", IsEssential.NOT_INCLUDED)
        self.page._refresh_transaction_table()
        row = self.page._transaction_table._components[0]
        for column in (2, 4, 6):
            self.assertIsInstance(row[column], tk.Label)
        self.assertEqual(str(self.enum_controls(row[5])[0].cget("state")), "disabled")
        self.page._set_transaction_is_essential(0, IsEssential.ESSENTIAL)
        self.assertIs(transaction.is_essential, IsEssential.NOT_INCLUDED)

    def test_cancelled_receipt_draft_does_not_change_field_origins(self):
        receipt = make_receipt()
        window = self.open_receipt(receipt)
        row = self.receipt_table(window)._components[0]
        category, _ = self.enum_controls(row[3])
        category.set("Discretionary Spending")
        category.event_generate("<<ComboboxSelected>>")
        self.assertEqual(str(self.enum_controls(row[4])[0].cget("state")), "disabled")
        self.assertEqual(str(row[5].cget("state")), "disabled")
        self.close_receipt(window)
        item = receipt.items[0]
        for field in ("category", "description", "is_essential"):
            self.assertIsNone(getattr(item, field))
            self.assertFalse(item.is_field_locked(field))
        window = self.open_receipt(receipt)
        row = self.receipt_table(window)._components[0]
        self.assertEqual(str(self.enum_controls(row[4])[0].cget("state")), "readonly")
        self.assertEqual(str(row[5].cget("state")), "normal")

    def test_incomplete_receipt_keeps_save_after_its_fields_are_completed(self):
        receipt = make_receipt()
        purchase = make_transaction(receipt=receipt)
        purchase.category = Categories.SHOPPING
        purchase.is_essential = IsEssential.ESSENTIAL
        window = self.open_receipt(receipt, purchase)
        row = self.receipt_table(window)._components[0]
        description, add = self.enum_controls(row[4])
        self.assertEqual(str(description.cget("state")), "readonly")
        self.assertEqual(str(add.cget("state")), "normal")
        self.assertEqual(set(description.cget("values")),
                         {str(value) for value in description_manager.DescriptionManager.choices(Categories.SHOPPING)})
        save = self.receipt_action(window, "Save")
        description.set("Other")
        description.event_generate("<<ComboboxSelected>>")
        self.assertIs(self.receipt_action(window, "Save"), save)
        self.assertIsNone(receipt.items[0].description)
        self.save_receipt(window)
        self.assertIs(receipt.items[0].description, Descriptions.OTHER)
        reopened = self.open_receipt(receipt, purchase)
        self.assert_no_save(reopened)
        self.assertEqual(str(self.enum_controls(self.receipt_table(reopened)._components[0][4])[0].cget("state")),
                         "disabled")

    def test_mixed_complete_and_incomplete_receipt_items_still_allow_save(self):
        receipt = make_receipt()
        receipt.items[0] = GroceryItem("Classified", 2.36, category=Categories.SHOPPING,
                                      description=Descriptions.OTHER, is_essential=IsEssential.ESSENTIAL)
        receipt.items.append(GroceryItem("Unclassified", 1))
        window = self.open_receipt(receipt)
        self.assertIsInstance(self.receipt_action(window, "Save"), tk.Button)
        rows = self.receipt_table(window)._components
        self.assertEqual(str(self.enum_controls(rows[0][4])[0].cget("state")), "disabled")
        description, add = self.enum_controls(rows[1][4])
        self.assertEqual(str(description.cget("state")), "readonly")
        self.assertEqual(set(description.cget("values")), {str(value) for value in Descriptions})
        self.close_receipt(window)

    def test_selecting_income_in_main_table_autofills_and_locks_essential(self):
        purchase = make_transaction(location=None, amount=20)
        self.page._transactions = [purchase]
        self.page._setup_components()
        row = self.page._transaction_table._components[0]
        category, add = self.enum_controls(row[4])
        self.assertEqual(str(category.cget("state")), "readonly")
        category.set("Income")
        category.event_generate("<<ComboboxSelected>>")
        self.assertIs(purchase.is_essential, IsEssential.ESSENTIAL)
        self.assertEqual(str(row[6].cget("state")), "disabled")
        self.assertEqual(row[6].get(), "Essential")
        self.page._set_transaction_is_essential(0, IsEssential.NON_ESSENTIAL)
        self.assertIs(purchase.is_essential, IsEssential.ESSENTIAL)

    def test_discover_payment_selected_location_refreshes_locked_classifications(self):
        purchase = make_transaction(location=None, amount=-100, purchase_title="DISCOVER,E-PAYMENT")
        self.page._transactions = [purchase]
        self.page._setup_components()
        location, _ = self.enum_controls(self.page._transaction_table._components[0][2])
        location.set("Discover")
        location.event_generate("<<ComboboxSelected>>")
        self.assertIs(purchase.category, Categories.CREDIT_CARD)
        self.assertIs(purchase.description, CreditCardDescriptions.PAYMENT)
        self.assertIs(purchase.is_essential, IsEssential.NOT_INCLUDED)
        self.assertTrue(purchase.excluded_from_totals)
        row = self.page._transaction_table._components[0]
        self.assertIsInstance(row[4], tk.Label)
        self.assertEqual(str(self.enum_controls(row[5])[0].cget("state")), "disabled")
        self.page._set_transaction_category(0, Categories.INCOME)
        self.assertIs(purchase.category, Categories.CREDIT_CARD)


    def receipt_action(self, window, text):
        return next(widget for widget in window.winfo_children()[-1].winfo_children()
                    if isinstance(widget, tk.Button) and widget.cget("text") == text)

    def save_receipt(self, window):
        self.receipt_action(window, "Save").invoke()
        self.assertFalse(window.winfo_exists())

    def assert_no_save(self, window):
        with self.assertRaises(StopIteration):
            self.receipt_action(window, "Save")

    def close_receipt(self, window):
        window.tk.call(window.protocol("WM_DELETE_WINDOW"))
        self.assertFalse(window.winfo_exists())

    def open_receipt(self, receipt, transaction=None):
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            window = self.page._show_receipt(receipt, transaction)
        self.addCleanup(lambda: window.destroy() if window.winfo_exists() else None)
        return window

    def test_finalize_lists_all_incomplete_rows_and_columns_without_advancing(self):
        blank = make_transaction(location=None, purchase_title="PURCHASE NAME")
        partial = make_transaction(location=Locations.AMAZON)
        partial.category = Categories.HOUSING
        partial.description = " \t"
        partial.is_essential = IsEssential.NON_ESSENTIAL
        complete = make_transaction(location=Locations.CULVERS)
        complete.category = Categories.DISCRETIONARY_SPENDING
        self.page._transactions = [blank, partial, complete]
        self.page._setup_components()
        self.assertEqual(self.enum_controls(self.page._transaction_table._components[0][5])[0].get(),
                         "PURCHASE NAME")
        with patch.object(self.page, "_show_incomplete_transactions") as warning, \
                patch.object(final_review_page.messagebox, "askyesno", return_value=True) as confirm:
            self.page._finalize_button.invoke()
        warning.assert_called_once()
        listed_rows = warning.call_args.args[0]
        self.assertEqual([(number, missing) for number, purchase, missing in listed_rows], [
            (1, ["Location", "Category", "Description", "Is Essential?"]),
            (2, ["Description"]),
        ])
        confirm.assert_not_called()
        self.page._parent_next_method.assert_not_called()
        self.receipt_backup.assert_not_called()
        self.expense_report.assert_not_called()

    def test_excluded_rows_allow_metadata_edits_without_clearing_exclusion(self):
        transaction = make_transaction(location=None)
        transaction.location = Locations.FREEDOM_BANK
        transaction.category = Categories.HOUSING
        transaction.description = Descriptions.TRANSFER
        transaction.is_essential = IsEssential.NOT_INCLUDED
        self.page._transactions = [transaction]
        self.page._setup_components()
        row = self.page._transaction_table._components[0]
        location, _ = self.enum_controls(row[2])
        category, _ = self.enum_controls(row[4])
        description, _ = self.enum_controls(row[5])
        for dropdown in (location, category, description):
            self.assertNotIn("Not Included", dropdown.cget("values"))
        self.assertIn("Not Included", row[6].cget("values"))
        for dropdown, selection in ((location, "Amazon"), (category, "Discretionary Spending"),
                                     (category, "Housing"), (description, "Rent")):
            dropdown.set(selection)
            dropdown.event_generate("<<ComboboxSelected>>")
            self.assertIs(transaction.is_essential, IsEssential.NOT_INCLUDED)
        self.assertIs(transaction.location, Locations.AMAZON)
        self.assertIs(transaction.category, Categories.HOUSING)
        self.assertEqual(transaction.description, "Rent")
        row[6].set("Essential")
        row[6].event_generate("<<ComboboxSelected>>")
        self.assertIs(transaction.is_essential, IsEssential.ESSENTIAL)

    def test_finalize_allows_progress_after_the_missing_main_cells_are_selected(self):
        transaction = make_transaction(location=None, purchase_title="PURCHASE NAME")
        self.page._transactions = [transaction]
        self.page._setup_components()
        with patch.object(self.page, "_show_incomplete_transactions") as warning, \
                patch.object(final_review_page.messagebox, "askyesno", return_value=True) as confirm:
            self.page._finalize_button.invoke()
            confirm.assert_not_called()
            warning.assert_called_once()
            row = self.page._transaction_table._components[0]
            for column, selection in ((2, "Amazon"), (4, "Housing"), (5, "Rent")):
                dropdown, _ = self.enum_controls(row[column])
                dropdown.set(selection)
                dropdown.event_generate("<<ComboboxSelected>>")
            row[6].set("Non-Essential")
            row[6].event_generate("<<ComboboxSelected>>")
            warning.reset_mock()
            self.page._finalize_button.invoke()
            warning.assert_not_called()
            confirm.assert_called_once()
        self.page._parent_next_method.assert_called_once_with()
        self.receipt_backup.assert_called_once_with(final_review_page.Paths.RECEIPTS, final_review_page.Paths.ASSETS_PDFS,
                                                    excluded_file_names=set(),
                                                    destination=self.month_directory / "Supporting Documents", overwrite=False)

    def test_finalize_checks_split_receipt_rows_and_waits_for_saved_edits(self):
        receipt = make_receipt(total=5)
        receipt.items[:] = [
            GroceryItem("A", 2, category=Categories.SHOPPING,
                        description=Descriptions.OTHER, is_essential=IsEssential.ESSENTIAL),
            GroceryItem("B", 3, is_essential=IsEssential.NON_ESSENTIAL),
        ]
        purchase = make_transaction(amount=-5, receipt=receipt)
        self.page._transactions = [purchase]
        self.page._setup_components()
        window = self.open_receipt(receipt, purchase)
        item_row = self.receipt_table(window)._components[1]
        for column, selection in ((3, "Housing"), (4, "Rent")):
            dropdown, _ = self.enum_controls(item_row[column])
            dropdown.set(selection)
            dropdown.event_generate("<<ComboboxSelected>>")
        with patch.object(self.page, "_show_incomplete_transactions") as warning, \
                patch.object(final_review_page.messagebox, "askyesno", return_value=True) as confirm:
            self.page._finalize_button.invoke()
            warning.assert_called_once()
            incomplete = warning.call_args.args[0]
            self.assertEqual(len(incomplete), 1)
            number, transaction, missing = incomplete[0]
            self.assertEqual((number, str(transaction.amount), missing), (2, "-$3.00", ["Category", "Description"]))
            confirm.assert_not_called()
            self.page._parent_next_method.assert_not_called()
            self.receipt_backup.assert_not_called()
            self.expense_report.assert_not_called()
            self.save_receipt(window)
            warning.reset_mock()
            self.page._finalize_button.invoke()
            warning.assert_not_called()
            confirm.assert_called_once()
        self.page._parent_next_method.assert_called_once_with()
        self.receipt_backup.assert_called_once_with(final_review_page.Paths.RECEIPTS, final_review_page.Paths.ASSETS_PDFS,
                                                    excluded_file_names=set(),
                                                    destination=self.month_directory / "Supporting Documents", overwrite=False)
        for field in ("category", "description", "is_essential"):
            self.assertIsNone(getattr(purchase, field))

    def test_incomplete_popup_shows_missing_fields_and_replaces_previous_window(self):
        purchase = make_transaction(location=None, purchase_title="Unclassified purchase")
        incomplete = [(3, purchase, ["Location", "Category", "Description", "Is Essential?"])]
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            window = self.page._show_incomplete_transactions(incomplete)
            table = next(widget for widget in window.winfo_children() if isinstance(widget, TkTable))
            self.assertTrue(table._review_style)
            cells = table._components[0]
            self.assertEqual(cells[0].cget("text"), "3")
            self.assertIn("Unknown location", cells[1].cget("text"))
            self.assertIn("Unclassified purchase", cells[1].cget("text"))
            self.assertEqual(cells[2].cget("text"), "Location, Category, Description, Is Essential?")
            self.assertEqual(cells[2].cget("fg"), "#9A3412")
            replacement = self.page._show_incomplete_transactions(incomplete)
            self.assertFalse(window.winfo_exists())
            button = next(widget for widget in replacement.winfo_children()
                          if isinstance(widget, tk.Button) and widget.cget("text") == "Back to Review")
            button.invoke()
            self.assertFalse(replacement.winfo_exists())

    def test_complete_rows_accept_valid_defaults_and_still_require_confirmation(self):
        regular = make_transaction(amount=0)
        regular.category = Categories.SHOPPING
        regular.description = Descriptions.OTHER
        regular.is_essential = IsEssential.ESSENTIAL
        excluded = make_transaction(location=Locations.FREEDOM_BANK)
        excluded.category = Categories.HOUSING
        excluded.description = Descriptions.OTHER
        excluded.is_essential = IsEssential.NOT_INCLUDED
        discretionary = make_transaction(location=Locations.CULVERS)
        discretionary.category = Categories.DISCRETIONARY_SPENDING
        self.page._transactions = [regular, excluded, discretionary]
        self.page._setup_components()
        with patch.object(final_review_page.messagebox, "showwarning") as warning, \
                patch.object(final_review_page.messagebox, "askyesno", side_effect=[False, True]) as confirm:
            self.page._finalize_button.invoke()
            self.page._parent_next_method.assert_not_called()
            self.receipt_backup.assert_not_called()
            self.expense_report.assert_not_called()
            self.page._finalize_button.invoke()
            self.assertEqual(confirm.call_count, 2)
            warning.assert_not_called()
        self.page._parent_next_method.assert_called_once_with()
        self.receipt_backup.assert_called_once_with(final_review_page.Paths.RECEIPTS, final_review_page.Paths.ASSETS_PDFS,
                                                    excluded_file_names=set(),
                                                    destination=self.month_directory / "Supporting Documents", overwrite=False)

    def test_finalize_copies_receipts_after_confirmation_and_before_advancing(self):
        transaction = make_transaction(location=Locations.CULVERS)
        transaction.category = Categories.DISCRETIONARY_SPENDING
        self.page._transactions = [transaction]
        self.page._setup_components()
        events = []

        def confirm(*args, **kwargs):
            events.append("confirmed")
            return True

        def backup(source, statements_source, excluded_file_names, destination, overwrite):
            events.append("copied")
            return destination

        self.receipt_backup.side_effect = backup
        self.expense_report.side_effect = lambda *args, **kwargs: events.append("generated PDF")
        self.page._parent_next_method.side_effect = lambda: events.append("advanced")
        with patch.object(final_review_page.messagebox, "askyesno", side_effect=confirm):
            self.page._finalize_button.invoke()
        self.assertEqual(events, ["confirmed", "copied", "generated PDF", "advanced"])
        self.receipt_backup.assert_called_once_with(final_review_page.Paths.RECEIPTS, final_review_page.Paths.ASSETS_PDFS,
                                                    excluded_file_names=set(),
                                                    destination=self.month_directory / "Supporting Documents", overwrite=False)
        self.expense_report.assert_called_once_with(self.month_directory / "Expense Review.pdf",
                                                   self.page._transaction_rows, self.page._receipts, overwrite=False)

    def test_declining_month_replacement_leaves_every_existing_file_untouched(self):
        transaction = make_transaction(location=Locations.CULVERS)
        transaction.category = Categories.DISCRETIONARY_SPENDING
        self.page._transactions = [transaction]
        self.page._setup_components()
        receipts = self.month_directory / "Supporting Documents"
        receipts.mkdir(parents=True)
        report = self.month_directory / "Expense Review.pdf"
        receipt = receipts / "Apple_9-2-2026.json"
        report.write_bytes(b"saved report")
        receipt.write_bytes(b"saved receipt")
        statement = receipts / final_review_page.Files.CREDIT_CARD_PREVIOUS_MONTH_STATEMENT_PDF
        statement.write_bytes(b"saved statement")
        working = self.workspace / "imported-receipt.json"
        working.write_bytes(b"working receipt")
        self.page._review_files.track_file(working, self.workspace)
        with patch.object(final_review_page.messagebox, "askyesno", side_effect=[True, False]) as confirm:
            self.page._finalize_button.invoke()
        self.assertEqual(confirm.call_count, 2)
        self.assertEqual(confirm.call_args.args[0], "Replace existing monthly review?")
        self.assertEqual(confirm.call_args.kwargs["default"], "no")
        self.assertIn(str(self.month_directory), confirm.call_args.args[1])
        self.assertIn("Supporting Documents", confirm.call_args.args[1])
        self.assertIn("Discover statements", confirm.call_args.args[1])
        self.assertIn("bank statement", confirm.call_args.args[1])
        self.receipt_backup.assert_not_called()
        self.expense_report.assert_not_called()
        self.page._parent_next_method.assert_not_called()
        self.assertEqual(report.read_bytes(), b"saved report")
        self.assertEqual(receipt.read_bytes(), b"saved receipt")
        self.assertEqual(statement.read_bytes(), b"saved statement")
        self.assertEqual(working.read_bytes(), b"working receipt")

    def test_accepting_month_replacement_authorizes_both_outputs(self):
        transaction = make_transaction(location=Locations.CULVERS)
        transaction.category = Categories.DISCRETIONARY_SPENDING
        self.page._transactions = [transaction]
        self.page._setup_components()
        self.month_directory.mkdir(parents=True)
        with patch.object(final_review_page.messagebox, "askyesno", side_effect=[True, True]):
            self.page._finalize_button.invoke()
        self.receipt_backup.assert_called_once_with(final_review_page.Paths.RECEIPTS, final_review_page.Paths.ASSETS_PDFS,
                                                    excluded_file_names=set(),
                                                    destination=self.month_directory / "Supporting Documents", overwrite=True)
        self.expense_report.assert_called_once_with(self.month_directory / "Expense Review.pdf",
                                                   self.page._transaction_rows, self.page._receipts, overwrite=True)
        self.page._parent_next_method.assert_called_once_with()

    def test_backup_errors_keep_the_review_open_and_allow_retrying_finalize(self):
        transaction = make_transaction(location=Locations.CULVERS)
        transaction.category = Categories.DISCRETIONARY_SPENDING
        self.page._transactions = [transaction]
        self.page._setup_components()
        with patch.object(final_review_page.messagebox, "askyesno", return_value=True), \
                patch.object(final_review_page.messagebox, "showerror") as show_error:
            for error in (FileNotFoundError("Connect PrimaryBckp"), OSError("Drive is full")):
                with self.subTest(error=str(error)):
                    self.receipt_backup.side_effect = error
                    self.page._finalize_button.invoke()
                    show_error.assert_called_once()
                    self.assertEqual(show_error.call_args.args[0], "Supporting documents backup failed")
                    self.assertIn(str(error), show_error.call_args.args[1])
                    self.page._parent_next_method.assert_not_called()
                    self.expense_report.assert_not_called()
                    self.assertTrue(self.page._finalize_button.winfo_exists())
                    show_error.reset_mock()
            self.receipt_backup.side_effect = None
            self.page._finalize_button.invoke()
            show_error.assert_not_called()
        self.page._parent_next_method.assert_called_once_with()

    def test_pdf_failure_keeps_the_review_open_and_allows_retrying_finalize(self):
        transaction = make_transaction(location=Locations.CULVERS)
        transaction.category = Categories.DISCRETIONARY_SPENDING
        self.page._transactions = [transaction]
        self.page._setup_components()
        with patch.object(final_review_page.messagebox, "askyesno", return_value=True), \
                patch.object(final_review_page.messagebox, "showerror") as show_error:
            self.expense_report.side_effect = final_review_page.ReportGenerationError("Cannot render report")
            self.page._finalize_button.invoke()
            show_error.assert_called_once()
            self.assertEqual(show_error.call_args.args[0], "Expense review PDF failed")
            self.assertIn("Cannot render report", show_error.call_args.args[1])
            self.page._parent_next_method.assert_not_called()
            self.assertTrue(self.page._finalize_button.winfo_exists())
            self.expense_report.side_effect = None
            show_error.reset_mock()
            self.page._finalize_button.invoke()
            show_error.assert_not_called()
        self.page._parent_next_method.assert_called_once_with()

    def test_review_pages_share_the_same_working_file_tracker(self):
        container = expense_reveiw_page_class.ExpenseReviewPage(self.root, Mock())
        self.addCleanup(container._root.destroy)
        self.assertEqual(len(container._pages), 4)
        self.assertTrue(all(page._review_files is container._review_files for page in container._pages))
        self.assertIsInstance(container._review_files, ReviewFilesManager)

    def test_successful_finalize_saves_all_outputs_before_removing_only_tracked_inputs(self):
        transaction = make_transaction(location=Locations.CULVERS)
        transaction.category = Categories.DISCRETIONARY_SPENDING
        self.page._transactions = [transaction]
        self.page._setup_components()
        source = self.workspace / "receipts"
        statements = self.workspace / "pdfs"
        downloads = self.workspace / "Downloads"
        for directory in (source, statements, downloads):
            directory.mkdir()
        visible = source / "Culver's_9-29-2026.json"
        outside_month = source / "Apple_8-29-2026.json"
        instructions = downloads / "instructions.zip"
        tracked = [visible, outside_month, instructions]
        tracked.extend(statements / name for name in final_review_page.ReceiptBackupManager.STATEMENT_FILES)
        for path in tracked:
            path.write_bytes(f"working {path.name}".encode())
            self.page._review_files.track_file(path, path.parent)
        saved_contents = {path.name: path.read_bytes() for path in tracked
                          if path not in (outside_month, instructions)}
        original = downloads / "original-statement.pdf"
        original.write_bytes(b"original upload")
        unrelated = statements / "unrelated.pdf"
        unrelated.write_bytes(b"unrelated document")
        paths = type("TestPaths", (), {"RECEIPTS": str(source), "ASSETS_PDFS": str(statements)})

        def backup(*args, **kwargs):
            self.assertTrue(all(path.exists() for path in tracked))
            return self.copy_supporting_documents(*args, current_date=date(2026, 10, 3), **kwargs)

        def report(*args, **kwargs):
            self.assertTrue(all(path.exists() for path in tracked))
            return self.generate_report(*args, review_date=date(2026, 9, 1), **kwargs)

        self.receipt_backup.side_effect = backup
        self.expense_report.side_effect = report
        with patch.object(final_review_page, "Paths", paths), \
                patch.object(final_review_page.messagebox, "askyesno", return_value=True):
            self.page._finalize_button.invoke()
        self.assertTrue(all(not path.exists() for path in tracked))
        self.assertEqual(original.read_bytes(), b"original upload")
        self.assertEqual(unrelated.read_bytes(), b"unrelated document")
        supporting = self.month_directory / "Supporting Documents"
        self.assertEqual({path.name: path.read_bytes() for path in supporting.iterdir()}, saved_contents)
        self.assertTrue((self.month_directory / "Expense Review.pdf").read_bytes().startswith(b"%PDF"))
        self.assertEqual({path.name for path in self.month_directory.iterdir()},
                         {"Supporting Documents", "Expense Review.pdf"})
        self.page._parent_next_method.assert_called_once_with()

    def test_canceled_or_failed_saves_never_start_cleanup(self):
        transaction = make_transaction(location=Locations.CULVERS)
        transaction.category = Categories.DISCRETIONARY_SPENDING
        self.page._transactions = [transaction]
        self.page._setup_components()
        with patch.object(self.page._review_files, "cleanup") as cleanup, \
                patch.object(final_review_page.messagebox, "askyesno", side_effect=[False, True, True]), \
                patch.object(final_review_page.messagebox, "showerror"):
            self.page._finalize_button.invoke()
            cleanup.assert_not_called()
            self.receipt_backup.side_effect = OSError("Backup failed")
            self.page._finalize_button.invoke()
            cleanup.assert_not_called()
            self.receipt_backup.side_effect = None
            self.expense_report.side_effect = final_review_page.ReportGenerationError("Render failed")
            self.page._finalize_button.invoke()
            cleanup.assert_not_called()
        self.assertFalse(self.page._outputs_saved)
        self.page._parent_next_method.assert_not_called()

    def test_cleanup_failure_can_be_retried_without_recopying_or_regenerating_saved_outputs(self):
        transaction = make_transaction(location=Locations.CULVERS)
        transaction.category = Categories.DISCRETIONARY_SPENDING
        self.page._transactions = [transaction]
        self.page._setup_components()
        with patch.object(self.page._review_files, "cleanup", side_effect=PermissionError("PDF is open")) as cleanup, \
                patch.object(final_review_page.messagebox, "askyesno", return_value=True) as confirm, \
                patch.object(final_review_page.messagebox, "showerror") as error:
            self.page._finalize_button.invoke()
            self.assertTrue(self.page._outputs_saved)
            self.assertEqual(self.page._finalize_button.cget("text"), "Retry Cleanup")
            self.assertEqual(error.call_args.args[0], "Working file cleanup incomplete")
            self.assertIn("have been saved", error.call_args.args[1])
            self.page._parent_next_method.assert_not_called()
            cleanup.side_effect = None
            self.page._finalize_button.invoke()
            self.assertEqual(cleanup.call_count, 2)
            confirm.assert_called_once()
        self.receipt_backup.assert_called_once()
        self.expense_report.assert_called_once()
        self.page._parent_next_method.assert_called_once_with()

    def test_receipt_footer_stays_visible_at_default_and_minimum_window_sizes(self):
        self.page._transactions = []
        self.page._setup_components()
        receipt = make_receipt()
        receipt.items.extend(GroceryItem(f"Item {i}", 1) for i in range(30))
        window = self.page._show_receipt(receipt)
        self.addCleanup(lambda window=window: window.destroy() if window.winfo_exists() else None)
        # Map the popup independently of the withdrawn test root, without displaying it.
        window.transient("")
        window.attributes("-alpha", 0)
        window.deiconify()
        for size in ("1100x550", "1000x350"):
            with self.subTest(size=size):
                window.geometry(size)
                window.update()
                table = self.receipt_table(window)
                button = self.receipt_action(window, "Save")
                self.assertTrue(button.winfo_ismapped(), f"Save is hidden at {size}")
                self.assertEqual(button.winfo_height(), self.page._finalize_button.winfo_reqheight())
                self.assertEqual(button.winfo_width(), window.winfo_width())
                self.assertEqual(button.winfo_rootx(), window.winfo_rootx())
                self.assertGreaterEqual(button.winfo_rooty(),
                                        table.winfo_rooty() + table.winfo_height())
                self.assertEqual(button.winfo_rooty() + button.winfo_height(),
                                 window.winfo_rooty() + window.winfo_height())
                self.assertEqual([widget.cget("text") for widget in button.master.winfo_children()],
                                 ["Save"])

    def test_receipt_save_splits_and_merges_rows_without_live_updates_or_losing_totals(self):
        receipt = make_receipt(total=42)
        receipt.items[:] = [GroceryItem("A", 10, quantity=2), GroceryItem("B", 5, quantity=2), GroceryItem("C", 10)]
        purchase = make_transaction(amount=-42, receipt=receipt, purchase_title="WALMART PURCHASE")
        other = make_transaction(location=None, amount=-7)
        self.page._transactions = [purchase, other]
        self.page._setup_components()
        original_table = self.page._transaction_table
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            window = self.page._show_receipt(receipt, purchase)
        self.addCleanup(lambda: window.destroy() if window.winfo_exists() else None)
        rows = self.receipt_table(window)._components
        with patch.object(self.page, "_refresh_transaction_table", wraps=self.page._refresh_transaction_table) as refresh:
            rows[0][5].invoke()
            rows[1][5].invoke()
            refresh.assert_not_called()
            self.assertTrue(all(item.is_essential is None for item in receipt.items))
            self.assertIs(self.page._transaction_table, original_table)
            self.assertEqual(len(original_table._components), 2)
            self.save_receipt(window)
            refresh.assert_called_once()
        table = self.page._transaction_table
        self.assertEqual([row[3].cget("text") for row in table._components], ["-$31.50", "-$10.50", "-$7.00"])
        self.assertEqual([row[6].cget("text") for row in table._components[:2]], ["Essential", "Non-Essential"])
        self.assertEqual([row[1].cget("text") for row in table._components[:2]], ["11:06 AM", "11:06 AM"])
        self.assertEqual(sum(round(row.transaction.amount * 100) for row in self.page._transaction_rows), -4900)
        self.assertIsNone(purchase.is_essential)
        self.assertEqual(purchase.amount, -42)
        self.assertFalse(window.winfo_exists())
        location, _ = self.enum_controls(table._components[2][2])
        location.set(str(Locations.AMAZON))
        location.event_generate("<<ComboboxSelected>>")
        self.assertIs(other.location, Locations.AMAZON)
        self.assertIs(purchase.location, Locations.WALMART)
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            table._components[1][7].invoke()
        reopened = next(widget for widget in self.page._root.winfo_children() if isinstance(widget, self.toplevel_type))
        self.addCleanup(lambda: reopened.destroy() if reopened.winfo_exists() else None)
        rows = self.receipt_table(reopened)._components
        self.assertEqual(len(rows), 3)
        self.assertEqual(str(rows[0][5].cget("state")), "normal")
        self.assertEqual(str(rows[1][5].cget("state")), "normal")
        rows[0][5].invoke()
        rows[1][5].invoke()
        self.assertEqual(len(self.page._transaction_table._components), 3)
        self.save_receipt(reopened)
        self.assertEqual([row[3].cget("text") for row in self.page._transaction_table._components], ["-$42.00", "-$7.00"])
        reopened = self.open_receipt(receipt, purchase)
        self.save_receipt(reopened)
        self.assertEqual(len(self.page._transaction_table._components), 2)
        self.assertIs(self.page._transactions[0], purchase)

    def test_closing_receipt_discards_unsaved_edits_and_preserves_the_main_table(self):
        receipt = make_receipt()
        purchase = make_transaction(receipt=receipt)
        self.page._transactions = [purchase]
        self.page._setup_components()
        original_table = self.page._transaction_table
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            window = self.page._show_receipt(receipt, purchase)
        row = self.receipt_table(window)._components[0]
        category, _ = self.enum_controls(row[3])
        category.set("Housing")
        category.event_generate("<<ComboboxSelected>>")
        description, _ = self.enum_controls(row[4])
        description.set("Rent")
        description.event_generate("<<ComboboxSelected>>")
        row[5].invoke()
        with patch.object(self.page, "_receipt_changed") as changed:
            self.close_receipt(window)
            changed.assert_not_called()
        self.assertIsNone(receipt.items[0].category)
        self.assertIsNone(receipt.items[0].description)
        self.assertIsNone(receipt.items[0].is_essential)
        self.assertIs(self.page._transaction_table, original_table)
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            reopened = self.page._show_receipt(receipt, purchase)
        self.addCleanup(lambda: reopened.destroy() if reopened.winfo_exists() else None)
        row = self.receipt_table(reopened)._components[0]
        self.assertEqual(self.enum_controls(row[3])[0].get(), "None")
        self.assertEqual(self.enum_controls(row[4])[0].get(), receipt.items[0].name)
        row[5].invoke()
        self.save_receipt(reopened)
        saved_table = self.page._transaction_table
        self.assertIs(receipt.items[0].is_essential, IsEssential.ESSENTIAL)
        reopened = self.open_receipt(receipt, purchase)
        row = self.receipt_table(reopened)._components[0]
        row[5].invoke()
        self.close_receipt(reopened)
        self.assertIs(receipt.items[0].is_essential, IsEssential.ESSENTIAL)
        self.assertIs(self.page._transaction_table, saved_table)

    def test_main_group_descriptions_are_locked_and_receipt_edits_can_merge_groups(self):
        receipt = make_receipt(total=30)
        receipt.items[:] = [GroceryItem("A", 10), GroceryItem("B", 20)]
        for item, description in zip(receipt.items, (Descriptions.OTHER, CarDescriptions.GAS)):
            item.description = description
            item.is_essential = IsEssential.ESSENTIAL
        purchase = make_transaction(amount=-30, receipt=receipt)
        self.page._transactions = [purchase]
        self.page._setup_components()
        self.assertEqual(len(self.page._transaction_table._components), 2)
        description, _ = self.enum_controls(self.page._transaction_table._components[1][5])
        description.set("Other")
        description.event_generate("<<ComboboxSelected>>")
        self.assertEqual(str(description.cget("state")), "disabled")
        self.assertIs(receipt.items[1].description, CarDescriptions.GAS)
        self.page._set_transaction_description(1, Descriptions.OTHER)
        self.assertIs(receipt.items[1].description, CarDescriptions.GAS)
        window = self.open_receipt(receipt, purchase)
        description, _ = self.enum_controls(self.receipt_table(window)._components[1][4])
        description.set("Other")
        description.event_generate("<<ComboboxSelected>>")
        self.save_receipt(window)
        self.assertIsNone(purchase.description)
        self.assertTrue(all(item.description == Descriptions.OTHER for item in receipt.items))
        self.assertEqual(len(self.page._transaction_table._components), 1)
        self.assertEqual(self.page._transaction_table._components[0][3].cget("text"), "-$30.00")

    def test_receipt_column_has_buttons_only_for_matches_and_opens_each_rows_receipt(self):
        receipts = [make_receipt(), make_receipt(total=4.06)]
        transactions = [make_transaction(), make_transaction(amount=-4.06), make_transaction(amount=-9.99)]
        with patch.object(final_review_page, "_import_receipts", return_value=receipts), \
                patch.object(final_review_page, "_import_transactions", return_value=transactions):
            self.page.activate()

        table = next(widget for widget in self.page._root.winfo_children() if isinstance(widget, TkTable))
        self.assertEqual([column.text for column in table.columns],
                         ["Date", "Time", "Location", "Amount", "Category", "Description", "Is Essential?", "Receipt", "Hidden"])
        self.assertEqual([row[1].cget("text") for row in table._components],
                         ["11:06 AM", "11:06 AM", ""])
        first, second, unmatched = [row[7] for row in table._components]
        self.assertIsInstance(first, tk.Button)
        self.assertIsInstance(second, tk.Button)
        self.assertIsInstance(unmatched, tk.Label)
        self.assertEqual(unmatched.cget("text"), "")
        self.assertEqual(first.grid_info()["in"], table._body)
        with patch.object(self.page, "_show_receipt", return_value=None) as show:
            first.invoke()
            show.assert_called_once_with(receipts[0], transactions[0])
            second.invoke()
            self.assertEqual(show.call_count, 2)
            show.assert_called_with(receipts[1], transactions[1])

    def test_popup_shows_metadata_item_rows_with_total_costs_links_and_receipt_totals(self):
        receipt = make_receipt()
        receipt.items[0] = GroceryItem("Body Wash", 2.36, "https://example.com/body-wash", quantity=3)
        receipt.items.append(GroceryItem("Produce", 2, quantity=0.5))
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            window = self.page._show_receipt(receipt)
        self.addCleanup(lambda: window.destroy() if window.winfo_exists() else None)
        labels = self.label_texts(window)
        for value in (
            "Location: Walmart", "Date: 9/29/2026", "Time: 11:06:06 AM",
            "Subtotal: $2.36", "Tax: $0.13", "Total: $2.49",
        ):
            self.assertIn(value, labels)
        metadata = window.winfo_children()[0]
        metadata_labels = [widget for widget in metadata.winfo_children() if isinstance(widget, tk.Label)]
        self.assertEqual([label.cget("text") for label in metadata_labels],
                         ["Date: 9/29/2026", "Location: Walmart", "Time: 11:06:06 AM",
                          "Subtotal: $2.36", "Tax: $0.13", "Total: $2.49"])
        self.assertEqual([label.grid_info()["column"] for label in metadata_labels[:3]], [0, 1, 2])
        self.assertEqual([label.grid_info()["row"] for label in metadata_labels[3:]], [1, 2, 4])
        self.assertTrue(all(label.grid_info()["columnspan"] == 3 for label in metadata_labels[3:]))
        location_label = next(label for label in metadata_labels
                              if label.cget("text") == "Location: Walmart")
        main_table = TkTable(self.page._root, columns=[TableColumn("Location", Locations)])
        self.addCleanup(main_table.destroy)
        main_table.add_row((Locations.WALMART,))
        for option in ("bg", "fg"):
            self.assertEqual(location_label.cget(option), main_table._components[0][0].cget(option))
        table = self.receipt_table(window)
        self.assertEqual([column.text for column in table.columns],
                         ["Item", "Quantity", "Cost", "Category", "Description", "Is Essential?"])
        first, second = table._components
        self.assertIsInstance(first[0], TkLink)
        self.assertEqual(first[0].cget("text"), "Body Wash")
        self.assertEqual(first[0]._url, "https://example.com/body-wash")
        self.assertEqual([cell.cget("text") for cell in first[1:3]], ["3", "-$7.08"])
        self.assertEqual([cell.cget("text") for cell in second[:3]], ["Produce", "0.5", "-$1.00"])
        self.assertEqual(first[2].cget("fg"), "#B91C1C")
        for cell in first[3:5]:
            dropdown, button = self.enum_controls(cell)
            self.assertEqual(str(dropdown.cget("state")), "readonly")
            self.assertEqual(button.cget("text"), "+")
        self.assertIsInstance(first[5], tk.Checkbutton)
        self.assertEqual(first[5].cget("bg"), "red")
        self.assertEqual(first[0].grid_info()["in"], table._body)
        self.close_receipt(window)

    def test_item_classification_updates_only_the_selected_item_and_survives_reopening(self):
        receipt = make_receipt()
        transaction = make_transaction(receipt=receipt)
        transaction.description = None
        receipt.items.append(GroceryItem("Snack", 1.50,
                                         category=Categories.DISCRETIONARY_SPENDING,
                                         is_essential=IsEssential.NON_ESSENTIAL))
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            window = self.page._show_receipt(receipt, transaction)
        table = self.receipt_table(window)
        description, _ = self.enum_controls(table._components[0][4])
        description.set("Other")
        description.event_generate("<<ComboboxSelected>>")
        category, _ = self.enum_controls(table._components[0][3])
        essential = table._components[0][5]
        category.set("Shopping")
        category.event_generate("<<ComboboxSelected>>")
        essential.invoke()
        for option in ("bg", "activebackground", "selectcolor"):
            self.assertEqual(essential.cget(option), "green")
        self.save_receipt(window)
        self.assertIs(receipt.items[0].category, Categories.SHOPPING)
        self.assertIs(receipt.items[0].is_essential, IsEssential.ESSENTIAL)
        self.assertIs(receipt.items[0].description, Descriptions.OTHER)
        self.assertIs(receipt.items[1].description, DiscretionarySpendingDescriptions.DISCRETIONARY_SPENDING)
        self.assertIs(receipt.items[1].category, Categories.DISCRETIONARY_SPENDING)
        self.assertIs(receipt.items[1].is_essential, IsEssential.NON_ESSENTIAL)
        window = self.open_receipt(receipt, transaction)
        essential = self.receipt_table(window)._components[0][5]
        essential.invoke()
        for option in ("bg", "activebackground", "selectcolor"):
            self.assertEqual(essential.cget(option), "green")
        self.assertEqual(str(essential.cget("state")), "disabled")
        self.assert_no_save(window)
        self.close_receipt(window)
        self.assertIs(receipt.items[0].is_essential, IsEssential.ESSENTIAL)
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            reopened = self.page._show_receipt(receipt, transaction)
        self.addCleanup(lambda reopened=reopened: reopened.destroy() if reopened.winfo_exists() else None)
        rows = self.receipt_table(reopened)._components
        self.assertEqual(self.enum_controls(rows[0][4])[0].get(), "Other")
        self.assertEqual(self.enum_controls(rows[0][3])[0].get(), "Shopping")
        self.assertEqual(self.enum_controls(rows[1][3])[0].get(), "Discretionary Spending")
        self.assertTrue(self.root.getboolean(rows[0][5].getvar(rows[0][5].cget("variable"))))
        self.assertFalse(self.root.getboolean(rows[1][5].getvar(rows[1][5].cget("variable"))))
        self.assertEqual(rows[0][5].cget("bg"), "green")
        self.assertEqual(rows[1][5].cget("bg"), "red")
        rows[1][5].invoke()
        self.assertIs(receipt.items[1].is_essential, IsEssential.NON_ESSENTIAL)
        self.assertIs(receipt.items[0].is_essential, IsEssential.ESSENTIAL)
        self.assertEqual(rows[1][5].cget("bg"), "red")
        self.assertEqual(str(rows[1][5].cget("state")), "disabled")

    def test_receipt_inherits_and_locks_assigned_transaction_fields_for_every_item(self):
        for status, color, checked in (
            (IsEssential.ESSENTIAL, "green", True),
            (IsEssential.NON_ESSENTIAL, "red", False),
            (IsEssential.NOT_INCLUDED, "red", False),
        ):
            with self.subTest(status=status):
                receipt = make_receipt()
                receipt.items[0].category = Categories.SHOPPING
                receipt.items[0].is_essential = IsEssential.NON_ESSENTIAL
                receipt.items.append(GroceryItem("Snack", 1.50,
                                                 category=Categories.DISCRETIONARY_SPENDING,
                                                 is_essential=IsEssential.ESSENTIAL))
                transaction = make_transaction(receipt=receipt)
                transaction.category = Categories.CAR
                transaction.is_essential = status
                transaction.description = CarDescriptions.GAS
                with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
                    window = self.page._show_receipt(receipt, transaction)
                self.addCleanup(lambda window=window: window.destroy() if window.winfo_exists() else None)
                for item, row in zip(receipt.items, self.receipt_table(window)._components):
                    description, description_button = self.enum_controls(row[4])
                    category, category_button = self.enum_controls(row[3])
                    essential = row[5]
                    self.assertEqual(description.get(), "Gas")
                    self.assertEqual(str(description.cget("state")), "disabled")
                    self.assertEqual(str(description_button.cget("state")), "normal")
                    self.assertEqual(str(category_button.cget("state")), "normal")
                    self.assertEqual(category.get(), "Car")
                    self.assertEqual(str(category.cget("state")), "disabled")
                    self.assertEqual(str(essential.cget("state")), "disabled")
                    self.assertEqual(essential.cget("bg"), color)
                    self.assertEqual(self.root.getboolean(essential.getvar(essential.cget("variable"))), checked)
                    essential.invoke()
                self.assert_no_save(window)
                self.close_receipt(window)
                self.assertIs(receipt.items[0].category, Categories.SHOPPING)
                self.assertIsNone(receipt.items[0].description)
                self.assertIs(transaction.category, Categories.CAR)
                self.assertIs(transaction.is_essential, status)
                self.assertIs(transaction.description, CarDescriptions.GAS)

    def test_receipt_locks_only_fields_that_are_assigned_on_the_transaction(self):
        for assigned_category, assigned_essential in (
            (Categories.CAR, None),
            (None, IsEssential.ESSENTIAL),
            (None, IsEssential.NON_ESSENTIAL),
        ):
            with self.subTest(category=assigned_category, essential=assigned_essential):
                receipt = make_receipt()
                transaction = make_transaction(receipt=receipt)
                transaction.category = assigned_category
                transaction.is_essential = assigned_essential
                with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
                    window = self.page._show_receipt(receipt, transaction)
                self.addCleanup(lambda window=window: window.destroy() if window.winfo_exists() else None)
                row = self.receipt_table(window)._components[0]
                category, _ = self.enum_controls(row[3])
                essential = row[5]
                if assigned_category is None:
                    self.assertEqual(str(category.cget("state")), "readonly")
                    category.set("Housing")
                    category.event_generate("<<ComboboxSelected>>")
                else:
                    self.assertEqual(str(category.cget("state")), "disabled")
                self.assertEqual(str(essential.cget("state")),
                                 "normal" if assigned_essential is None else "disabled")
                essential.invoke()
                self.save_receipt(window)
                self.assertIs(receipt.items[0].category,
                              Categories.HOUSING if assigned_category is None else assigned_category)
                if assigned_essential is None:
                    self.assertIs(receipt.items[0].is_essential, IsEssential.ESSENTIAL)
                else:
                    self.assertIs(receipt.items[0].is_essential, assigned_essential)
                self.assertIs(transaction.category, assigned_category)
                self.assertIs(transaction.is_essential, assigned_essential)

    def test_main_row_selections_are_saved_and_inherited_when_its_receipt_button_is_clicked(self):
        receipts = [make_receipt(), make_receipt(total=4.06)]
        transactions = [make_transaction(receipt=receipts[0]),
                        make_transaction(amount=-4.06, receipt=receipts[1])]
        self.page._transactions = transactions
        self.page._setup_components()
        main_table = next(widget for widget in self.page._root.winfo_children() if isinstance(widget, TkTable))
        category = next(widget for widget in main_table._components[1][4].winfo_children()
                        if isinstance(widget, ttk.Combobox))
        category.set("Housing")
        category.event_generate("<<ComboboxSelected>>")
        description, _ = self.enum_controls(main_table._components[1][5])
        description.set("Rent")
        description.event_generate("<<ComboboxSelected>>")
        essential = main_table._components[1][6]
        essential.set("Non-Essential")
        essential.event_generate("<<ComboboxSelected>>")
        self.assertIs(transactions[1].category, Categories.HOUSING)
        self.assertIs(transactions[1].is_essential, IsEssential.NON_ESSENTIAL)
        self.assertIs(transactions[1].description, HousingDescriptions.RENT)
        self.assertIsNone(transactions[0].category)
        self.assertIsNone(transactions[0].is_essential)
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            main_table._components[1][7].invoke()
        window = next(widget for widget in self.page._root.winfo_children()
                      if isinstance(widget, self.toplevel_type))
        self.addCleanup(lambda window=window: window.destroy() if window.winfo_exists() else None)
        row = self.receipt_table(window)._components[0]
        description, description_button = self.enum_controls(row[4])
        category, _ = self.enum_controls(row[3])
        essential = row[5]
        self.assertEqual(description.get(), "Rent")
        self.assertEqual(str(description.cget("state")), "disabled")
        self.assertEqual(str(description_button.cget("state")), "normal")
        self.assertEqual(category.get(), "Housing")
        self.assertEqual(str(category.cget("state")), "disabled")
        self.assert_category_colors(row[3], Categories.HOUSING)
        self.assertEqual(str(essential.cget("state")), "disabled")
        self.assertEqual(essential.cget("bg"), "red")
        self.assert_no_save(window)
        self.close_receipt(window)
        self.assertIsNone(receipts[1].items[0].category)
        self.assertIs(transactions[1].category, Categories.HOUSING)
        self.assertIs(transactions[1].is_essential, IsEssential.NON_ESSENTIAL)
        self.assertIs(transactions[1].description, HousingDescriptions.RENT)
        self.assertIsNone(receipts[0].items[0].category)
        self.assertIsNone(receipts[0].items[0].is_essential)

    def test_receipt_can_create_save_and_select_a_category_for_each_item(self):
        enum_path, categories = isolate_choice_enums(self)["Categories"]
        receipt = make_receipt()
        receipt.items.append(GroceryItem("Snack", 1.50))
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            window = self.page._show_receipt(receipt)
        self.addCleanup(lambda window=window: window.destroy() if window.winfo_exists() else None)
        rows = self.receipt_table(window)._components
        first, add = self.enum_controls(rows[0][3])
        second, _ = self.enum_controls(rows[1][3])
        with patch.object(tk_table_class.simpledialog, "askstring", return_value="Household Supplies"):
            add.invoke()
        self.assertEqual(first.get(), "Household Supplies")
        self.assertIn("Household Supplies", second.cget("values"))
        self.assert_category_colors(rows[0][3], categories.HOUSEHOLD_SUPPLIES)
        self.assert_category_colors(rows[1][3], None)
        self.save_receipt(window)
        self.assertIs(receipt.items[0].category, categories.HOUSEHOLD_SUPPLIES)
        self.assertIsNone(receipt.items[1].category)
        window = self.open_receipt(receipt)
        second, _ = self.enum_controls(self.receipt_table(window)._components[1][3])
        second.set("Household Supplies")
        second.event_generate("<<ComboboxSelected>>")
        self.save_receipt(window)
        self.assertIs(receipt.items[1].category, categories.HOUSEHOLD_SUPPLIES)
        namespace = {}
        exec(enum_path.read_text(encoding="utf-8"), namespace)
        self.assertEqual(namespace["Categories"].HOUSEHOLD_SUPPLIES.value, "Household Supplies")

    def test_purchase_titles_are_editable_prompts_without_confirming_descriptions(self):
        title = "WAL-MART PURCHASE TITLE"
        transaction = final_review_page._create_financial_transaction_object(make_statement_row(title))
        transaction.receipt = make_receipt()
        self.assertEqual(transaction.purchase_title, title)
        self.assertIsNone(transaction.description)
        self.assertFalse(transaction.description_is_autocompleted)
        self.page._transactions = [transaction]
        self.page._setup_components()
        main_table = next(widget for widget in self.page._root.winfo_children() if isinstance(widget, TkTable))
        dropdown, add = self.enum_controls(main_table._components[0][5])
        self.assertEqual(dropdown.get(), title)
        self.assertNotIn(title, dropdown.cget("values"))
        self.assertEqual(str(dropdown.cget("state")), "readonly")
        self.assertEqual(str(add.cget("state")), "normal")
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            main_table._components[0][7].invoke()
        window = next(widget for widget in self.page._root.winfo_children()
                      if isinstance(widget, self.toplevel_type))
        self.addCleanup(lambda window=window: window.destroy() if window.winfo_exists() else None)
        dropdown, add = self.enum_controls(self.receipt_table(window)._components[0][4])
        self.assertEqual(dropdown.get(), transaction.receipt.items[0].name)
        self.assertEqual(str(dropdown.cget("state")), "readonly")
        self.assertEqual(str(add.cget("state")), "normal")
        self.assertIsNone(transaction.receipt.items[0].description)

    def test_autocompleted_car_payment_description_cannot_be_changed_on_the_main_page(self):
        transaction = final_review_page._create_financial_transaction_object(
            make_statement_row("FIRST SECURITY BANK")
        )
        self.page._transactions = [transaction]
        self.page._setup_components()
        table = next(widget for widget in self.page._root.winfo_children() if isinstance(widget, TkTable))
        dropdown, add = self.enum_controls(table._components[0][5])
        self.assertEqual(dropdown.get(), "Car Payment")
        self.assertEqual(str(dropdown.cget("state")), "disabled")
        self.assertEqual(str(add.cget("state")), "normal")
        with patch.object(tk_table_class.simpledialog, "askstring") as ask:
            add.invoke()
            ask.assert_not_called()
        self.page._set_transaction_description(0, CarDescriptions.GAS)
        self.assertIs(transaction.description, CarDescriptions.CAR_PAYMENT)
        self.assertTrue(transaction.description_is_autocompleted)

    def test_main_description_choices_follow_each_category_and_keep_titles_provisional(self):
        title = "WALMART " + "W" * 70
        transactions = [make_transaction(purchase_title=title), make_transaction()]
        transactions[1].category = Categories.SHOPPING
        self.page._transactions = transactions
        self.page._root.place(width=1000, height=700)
        self.page._setup_components()
        table = self.page._transaction_table
        first, _ = self.enum_controls(table._components[0][5])
        second, _ = self.enum_controls(table._components[1][5])
        category, _ = self.enum_controls(table._components[0][4])
        self.assertEqual(first.get(), title)
        self.assertNotIn(title, first.cget("values"))
        self.assertNotIn("Gas", first.cget("values"))
        self.assertEqual(set(first.cget("values")), {str(value) for value in Descriptions})
        self.assertNotIn("Gas", second.cget("values"))
        self.root.update_idletasks()
        self.assertGreater(first.winfo_width(), font.Font(root=self.root, font=first.cget("font")).measure(title))
        category.set("Car")
        category.event_generate("<<ComboboxSelected>>")
        self.assertEqual(set(first.cget("values")), {str(value) for value in description_manager.DescriptionManager.choices(Categories.CAR)})
        self.assertIsNone(transactions[0].description)
        first.set("Gas")
        first.event_generate("<<ComboboxSelected>>")
        self.assertIs(transactions[0].description, CarDescriptions.GAS)
        self.assertFalse(transactions[0].description_is_autocompleted)
        category.set("Shopping")
        category.event_generate("<<ComboboxSelected>>")
        self.assertIsNone(transactions[0].description)
        self.assertEqual(first.get(), title)
        self.assertNotIn("Gas", first.cget("values"))
        self.assertIn("food", first.cget("values"))
        first.set("Other")
        first.event_generate("<<ComboboxSelected>>")
        category.set("Housing")
        category.event_generate("<<ComboboxSelected>>")
        self.assertIs(transactions[0].description, Descriptions.OTHER)
        self.assertEqual(first.get(), "Other")
        self.assertIn("Rent", first.cget("values"))
        self.assertNotIn("food", first.cget("values"))
        self.assertIn("food", second.cget("values"))
        self.assertIsNone(transactions[1].description)

    def test_discretionary_main_category_autocompletes_locks_and_inherits_its_description(self):
        receipt = make_receipt()
        transaction = make_transaction(receipt=receipt, purchase_title="WALMART PURCHASE")
        imported = final_review_page._create_financial_transaction_object(make_statement_row("CULVER'S"))
        self.page._transactions = [transaction, imported]
        self.page._setup_components()
        table = self.page._transaction_table
        description, add = self.enum_controls(table._components[0][5])
        category, _ = self.enum_controls(table._components[0][4])
        description.set("Other")
        description.event_generate("<<ComboboxSelected>>")
        category.set("Discretionary Spending")
        category.event_generate("<<ComboboxSelected>>")
        self.assertIs(transaction.description, DiscretionarySpendingDescriptions.DISCRETIONARY_SPENDING)
        self.assertTrue(transaction.description_is_autocompleted)
        self.assertIs(transaction.is_essential, IsEssential.NON_ESSENTIAL)
        essential = table._components[0][6]
        self.assertEqual(essential.get(), "Non-Essential")
        self.assertEqual(str(essential.cget("state")), "disabled")
        self.assertEqual(description.get(), "Discretionary Spending")
        self.assertEqual(str(description.cget("state")), "disabled")
        self.assertEqual(str(add.cget("state")), "normal")
        imported_description, _ = self.enum_controls(table._components[1][5])
        self.assertEqual(imported_description.get(), "Discretionary Spending")
        self.assertEqual(str(imported_description.cget("state")), "disabled")
        self.assertIsInstance(table._components[1][6], tk.Label)
        self.assertEqual(table._components[1][6].cget("text"), "Non-Essential")
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            table._components[0][7].invoke()
        window = next(widget for widget in self.page._root.winfo_children()
                      if isinstance(widget, self.toplevel_type))
        self.addCleanup(lambda window=window: window.destroy() if window.winfo_exists() else None)
        receipt_row = self.receipt_table(window)._components[0]
        receipt_description, _ = self.enum_controls(receipt_row[4])
        self.assertEqual(receipt_description.get(), "Discretionary Spending")
        self.assertEqual(str(receipt_description.cget("state")), "disabled")
        self.assertEqual(receipt_row[5].cget("bg"), "red")
        self.assertEqual(str(receipt_row[5].cget("state")), "disabled")
        self.assertFalse(self.root.getboolean(receipt_row[5].getvar(receipt_row[5].cget("variable"))))
        self.assert_no_save(window)
        self.close_receipt(window)
        self.assertIsNone(receipt.items[0].description)
        self.assertIsNone(receipt.items[0].is_essential)
        table = self.page._transaction_table
        description, add = self.enum_controls(table._components[0][5])
        category, _ = self.enum_controls(table._components[0][4])
        essential = table._components[0][6]
        self.page._set_transaction_is_essential(0, IsEssential.ESSENTIAL)
        self.assertIs(transaction.is_essential, IsEssential.NON_ESSENTIAL)
        self.page._set_transaction_is_essential(0, IsEssential.NOT_INCLUDED)
        self.assertIs(transaction.is_essential, IsEssential.NON_ESSENTIAL)
        category.set("Car")
        category.event_generate("<<ComboboxSelected>>")
        essential = table._components[0][6]
        self.assertIsNone(transaction.is_essential)
        self.assertEqual(str(essential.cget("state")), "readonly")
        essential.set("Essential")
        essential.event_generate("<<ComboboxSelected>>")
        self.assertIs(transaction.is_essential, IsEssential.ESSENTIAL)
        self.assertIsNone(transaction.description)
        self.assertEqual(description.get(), "WALMART PURCHASE")
        self.assertEqual(str(description.cget("state")), "readonly")
        self.assertEqual(str(add.cget("state")), "normal")
        description.set("Gas")
        description.event_generate("<<ComboboxSelected>>")
        self.assertIs(transaction.description, CarDescriptions.GAS)

    def test_discretionary_category_replaces_an_existing_essential_value_and_unlocks_after_changing(self):
        transaction = make_transaction()
        transaction.is_essential = IsEssential.ESSENTIAL
        self.page._transactions = [transaction]
        self.page._setup_components()
        table = self.page._transaction_table
        category, _ = self.enum_controls(table._components[0][4])
        self.assertEqual(table._components[0][6].get(), "Essential")
        category.set("Discretionary Spending")
        category.event_generate("<<ComboboxSelected>>")
        self.assertIs(transaction.is_essential, IsEssential.NON_ESSENTIAL)
        self.assertEqual(table._components[0][6].get(), "Non-Essential")
        self.assertEqual(str(table._components[0][6].cget("state")), "disabled")
        category.set("Shopping")
        category.event_generate("<<ComboboxSelected>>")
        essential = table._components[0][6]
        self.assertIsInstance(essential, ttk.Combobox)
        self.assertEqual(str(essential.cget("state")), "readonly")
        self.assertIsNone(transaction.is_essential)
        essential.set("Essential")
        essential.event_generate("<<ComboboxSelected>>")
        self.assertIs(transaction.is_essential, IsEssential.ESSENTIAL)
        self.root.update_idletasks()
        self.assertEqual(table._head.grid_bbox(6, 0)[2], table._body.grid_bbox(6, 0)[2])

    def test_receipt_discretionary_description_locks_reopens_and_unlocks_after_category_changes(self):
        receipt = make_receipt()
        receipt.items[0].category = Categories.DISCRETIONARY_SPENDING
        receipt.items.append(GroceryItem("Food", 1.50, category=Categories.SHOPPING))
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            window = self.page._show_receipt(receipt)
        window.destroy()
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            reopened = self.page._show_receipt(receipt)
        self.addCleanup(lambda reopened=reopened: reopened.destroy() if reopened.winfo_exists() else None)
        rows = self.receipt_table(reopened)._components
        description, add = self.enum_controls(rows[0][4])
        category, _ = self.enum_controls(rows[0][3])
        self.assertEqual(description.get(), "Discretionary Spending")
        self.assertEqual(str(description.cget("state")), "disabled")
        self.assertEqual(str(add.cget("state")), "normal")
        category.set("Housing")
        category.event_generate("<<ComboboxSelected>>")
        self.assertEqual(description.get(), receipt.items[0].name)
        self.assertEqual(str(description.cget("state")), "readonly")
        self.assertEqual(str(add.cget("state")), "normal")
        self.assertEqual(str(rows[0][5].cget("state")), "normal")
        self.save_receipt(reopened)
        self.assertIsNone(receipt.items[0].description)
        self.assertIsNone(receipt.items[0].is_essential)
        reopened = self.open_receipt(receipt)
        rows = self.receipt_table(reopened)._components
        rows[0][5].invoke()
        self.assertEqual(rows[0][5].cget("bg"), "green")
        self.save_receipt(reopened)
        self.assertIs(receipt.items[0].is_essential, IsEssential.ESSENTIAL)
        reopened = self.open_receipt(receipt)
        rows = self.receipt_table(reopened)._components
        description, _ = self.enum_controls(rows[0][4])
        description.set("Rent")
        description.event_generate("<<ComboboxSelected>>")
        self.save_receipt(reopened)
        self.assertIs(receipt.items[0].description, HousingDescriptions.RENT)
        reopened = self.open_receipt(receipt)
        rows = self.receipt_table(reopened)._components
        description, _ = self.enum_controls(rows[0][4])
        category, _ = self.enum_controls(rows[0][3])
        category.set("Discretionary Spending")
        category.event_generate("<<ComboboxSelected>>")
        self.assertEqual(description.get(), "Discretionary Spending")
        self.assertEqual(str(description.cget("state")), "disabled")
        self.assertEqual(rows[0][5].cget("bg"), "red")
        self.assertFalse(self.root.getboolean(rows[0][5].getvar(rows[0][5].cget("variable"))))
        rows[0][5].invoke()
        self.assertIs(receipt.items[0].is_essential, IsEssential.ESSENTIAL)
        self.assertEqual(rows[0][5].cget("bg"), "red")
        self.assertEqual(str(rows[0][5].cget("state")), "disabled")
        self.save_receipt(reopened)
        self.assertIs(receipt.items[0].description, DiscretionarySpendingDescriptions.DISCRETIONARY_SPENDING)
        self.assertIs(receipt.items[0].is_essential, IsEssential.NON_ESSENTIAL)
        self.assertIsNone(receipt.items[1].description)

    def test_receipt_filters_each_item_and_saves_additions_in_its_category_enum(self):
        choices = isolate_choice_enums(self)
        enum_path, car_descriptions = choices["CarDescriptions"]
        receipt = make_receipt()
        receipt.items[0].category = Categories.CAR
        receipt.items.extend([GroceryItem("Snack", 1.50, category=Categories.SHOPPING),
                              GroceryItem("Maintenance", 2, category=Categories.CAR)])
        transaction = make_transaction(receipt=receipt, purchase_title="WALMART PURCHASE")
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            window = self.page._show_receipt(receipt, transaction)
        rows = self.receipt_table(window)._components
        first, add = self.enum_controls(rows[0][4])
        second, _ = self.enum_controls(rows[1][4])
        third, _ = self.enum_controls(rows[2][4])
        self.assertEqual(first.get(), receipt.items[0].name)
        self.assertIn("Gas", first.cget("values"))
        self.assertNotIn("Gas", second.cget("values"))
        with patch.object(tk_table_class.simpledialog, "askstring", return_value="Car Wash"):
            add.invoke()
        self.assertIn("Car Wash", third.cget("values"))
        self.assertNotIn("Car Wash", second.cget("values"))
        self.save_receipt(window)
        self.assertIs(receipt.items[0].description, car_descriptions.CAR_WASH)
        self.assertIsNone(receipt.items[1].description)
        self.assertIsNone(receipt.items[2].description)
        self.assertIsNone(transaction.description)
        namespace = {}
        exec(enum_path.read_text(encoding="utf-8"), namespace)
        self.assertEqual(namespace["CarDescriptions"].CAR_WASH.value, "Car Wash")
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            reopened = self.page._show_receipt(receipt, transaction)
        self.addCleanup(lambda reopened=reopened: reopened.destroy() if reopened.winfo_exists() else None)
        rows = self.receipt_table(reopened)._components
        first, _ = self.enum_controls(rows[0][4])
        self.assertEqual(first.get(), "Car Wash")
        self.assertEqual(str(first.cget("state")), "readonly")
        category, _ = self.enum_controls(rows[0][3])
        category.set("Shopping")
        category.event_generate("<<ComboboxSelected>>")
        self.assertEqual(first.get(), receipt.items[0].name)
        self.assertNotIn("Car Wash", first.cget("values"))
        self.assertIn("Other", first.cget("values"))
        self.save_receipt(reopened)
        self.assertIsNone(receipt.items[0].description)

    def test_main_description_dropdown_starts_blank_and_saves_editable_manual_choices(self):
        choices = isolate_choice_enums(self)
        enum_path, descriptions = choices["Descriptions"]
        transactions = [make_transaction(), make_transaction()]
        self.page._transactions = transactions
        self.page._root.place(width=1000, height=700)
        self.page._setup_components()
        table = next(widget for widget in self.page._root.winfo_children() if isinstance(widget, TkTable))
        first, add = self.enum_controls(table._components[0][5])
        second, _ = self.enum_controls(table._components[1][5])
        self.assertEqual(first.get(), "")
        self.assertNotIn("Gas", first.cget("values"))
        self.assertIn("Other", first.cget("values"))
        self.root.update_idletasks()
        original_widths = [table._body.grid_bbox(i, 0)[2] for i in range(len(table.columns))]
        long_description = "Household Purchase " + "W" * 75
        with patch.object(tk_table_class.simpledialog, "askstring", return_value=long_description):
            add.invoke()
        self.root.update_idletasks()
        resized_widths = [table._body.grid_bbox(i, 0)[2] for i in range(len(table.columns))]
        self.assertGreater(resized_widths[5], original_widths[5])
        self.assertEqual(original_widths[:5] + original_widths[6:], resized_widths[:5] + resized_widths[6:])
        text_width = font.Font(root=self.root, font=first.cget("font")).measure(long_description)
        self.assertGreater(first.winfo_width(), text_width)
        self.assertEqual(table._head.grid_bbox(5, 0)[2], resized_widths[5])
        self.assertIs(transactions[0].description, descriptions(long_description))
        self.assertIsNone(transactions[1].description)
        self.assertEqual(second.get(), "")
        self.assertIn(long_description, second.cget("values"))
        second.set("Other")
        second.event_generate("<<ComboboxSelected>>")
        self.assertIs(transactions[1].description, descriptions.OTHER)
        self.assertFalse(transactions[0].description_is_autocompleted)
        self.assertFalse(transactions[1].description_is_autocompleted)
        namespace = {}
        exec(enum_path.read_text(encoding="utf-8"), namespace)
        self.assertEqual(namespace["Descriptions"](long_description).value, long_description)
        table.destroy()
        self.page._setup_components()
        rebuilt = next(widget for widget in self.page._root.winfo_children() if isinstance(widget, TkTable))
        for row in rebuilt._components:
            dropdown, button = self.enum_controls(row[5])
            self.assertEqual(str(dropdown.cget("state")), "readonly")
            self.assertEqual(str(button.cget("state")), "normal")

    def test_receipt_description_additions_update_only_the_selected_item_and_survive_reopening(self):
        enum_path, descriptions = isolate_choice_enums(self)["Descriptions"]
        receipt = make_receipt()
        receipt.items.append(GroceryItem("Snack", 1.50))
        transaction = make_transaction(receipt=receipt)
        transaction.description = None
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            window = self.page._show_receipt(receipt, transaction)
        rows = self.receipt_table(window)._components
        first, _ = self.enum_controls(rows[0][4])
        second, add = self.enum_controls(rows[1][4])
        with patch.object(tk_table_class.simpledialog, "askstring", return_value="Afternoon Snack"):
            add.invoke()
        self.assertEqual(first.get(), receipt.items[0].name)
        self.assertIn("Afternoon Snack", first.cget("values"))
        self.assertEqual(second.get(), "Afternoon Snack")
        self.save_receipt(window)
        self.assertIsNone(receipt.items[0].description)
        self.assertIsNone(transaction.description)
        self.assertIs(receipt.items[1].description, descriptions.AFTERNOON_SNACK)
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            reopened = self.page._show_receipt(receipt, transaction)
        self.addCleanup(lambda reopened=reopened: reopened.destroy() if reopened.winfo_exists() else None)
        dropdown, add = self.enum_controls(self.receipt_table(reopened)._components[1][4])
        self.assertEqual(dropdown.get(), "Afternoon Snack")
        self.assertEqual(str(dropdown.cget("state")), "readonly")
        self.assertEqual(str(add.cget("state")), "normal")
        original_source = enum_path.read_bytes()
        with patch.object(tk_table_class.simpledialog, "askstring", return_value="afternoon snack"):
            add.invoke()
        self.assertEqual(enum_path.read_bytes(), original_source)
        namespace = {}
        exec(enum_path.read_text(encoding="utf-8"), namespace)
        self.assertEqual(namespace["Descriptions"].AFTERNOON_SNACK.value, "Afternoon Snack")

    def test_cancel_invalid_names_and_save_failures_preserve_receipt_choices(self):
        choices = isolate_choice_enums(self)
        receipt = make_receipt()
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            window = self.page._show_receipt(receipt)
        self.addCleanup(lambda window=window: window.destroy() if window.winfo_exists() else None)
        row = self.receipt_table(window)._components[0]
        for enum_name, column, attribute in (("Descriptions", 4, "description"),
                                             ("Categories", 3, "category")):
            enum_path, enum_type = choices[enum_name]
            original_source = enum_path.read_bytes()
            original_members = list(enum_type)
            dropdown, add = self.enum_controls(row[column])
            for name in (None, "", "!!!"):
                with self.subTest(enum=enum_name, name=name), \
                        patch.object(tk_table_class.simpledialog, "askstring", return_value=name), \
                        patch.object(tk_table_class.messagebox, "showerror") as show_error:
                    add.invoke()
                    self.assertEqual(show_error.call_count, 0 if name is None else 1)
            with patch.object(tk_table_class.simpledialog, "askstring", return_value="New Choice"), \
                    patch.object(enum_manager.os, "replace", side_effect=OSError("Cannot save")), \
                    patch.object(tk_table_class.messagebox, "showerror") as show_error:
                add.invoke()
                show_error.assert_called_once()
            self.assertIsNone(getattr(receipt.items[0], attribute))
            self.assertEqual(dropdown.get(), receipt.items[0].name if attribute == "description" else "None")
            self.assertEqual(enum_path.read_bytes(), original_source)
            self.assertEqual(list(enum_type), original_members)

    def test_matched_gas_receipt_sets_defaults_before_displaying_transaction(self):
        receipt = make_receipt(location="Kwik Trip", total=19.84, day=26,
                               item_name="UNL 88 Gasoline (4.670 gal @ $4.249/gal)")
        transaction = make_transaction(location=Locations.KWIK_TRIP, amount=-19.84, day=26)
        transaction.category = Categories.SHOPPING
        transaction.is_essential = IsEssential.NON_ESSENTIAL
        inferred_gas = make_transaction(location=Locations.KWIK_TRIP, amount=-25.01, day=26)
        with patch.object(final_review_page, "_import_receipts", return_value=[receipt]), \
                patch.object(final_review_page, "_import_transactions", return_value=[transaction, inferred_gas]):
            self.page.activate()

        self.assertIs(transaction.receipt, receipt)
        self.assertEqual(transaction.description, "Gas")
        self.assertEqual(transaction.category, Categories.CAR)
        self.assertEqual(transaction.is_essential, IsEssential.ESSENTIAL)
        table = next(widget for widget in self.page._root.winfo_children() if isinstance(widget, TkTable))
        self.assertEqual(self.enum_controls(table._components[0][5])[0].get(), "Gas")
        self.assertEqual(table._components[0][4].cget("text"), "Car")
        self.assertEqual(table._components[0][6].cget("text"), "Essential")
        self.assertEqual(table._components[0][6].cget("bg"), "green")
        self.assertIsNone(inferred_gas.receipt)
        self.assertEqual(self.enum_controls(table._components[1][5])[0].get(), "Gas")
        self.assertEqual(table._components[1][4].cget("text"), "Car")
        self.assertEqual(table._components[1][6].cget("text"), "Essential")
        self.assertEqual(table._components[1][6].cget("bg"), "green")
        for transaction, row in zip((transaction, inferred_gas), table._components):
            dropdown, add = self.enum_controls(row[5])
            self.assertTrue(transaction.description_is_autocompleted)
            self.assertEqual(str(dropdown.cget("state")), "disabled")
            self.assertEqual(str(add.cget("state")), "normal")
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            table._components[0][7].invoke()
        window = next(widget for widget in self.page._root.winfo_children()
                      if isinstance(widget, self.toplevel_type))
        self.addCleanup(lambda window=window: window.destroy() if window.winfo_exists() else None)
        dropdown, add = self.enum_controls(self.receipt_table(window)._components[0][4])
        self.assertEqual(dropdown.get(), "Gas")
        self.assertEqual(str(dropdown.cget("state")), "disabled")
        self.assertEqual(str(add.cget("state")), "normal")
        self.assert_no_save(window)
        self.close_receipt(window)
        self.assertIsNone(receipt.items[0].description)
        self.assertIs(transaction.description, CarDescriptions.GAS)

    def test_popup_accepts_receipts_without_time_or_items(self):
        receipt = Receipt("Walmart", Date(day=29, month=9, year=2026), None, 0, 0, 0, [])
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            window = self.page._show_receipt(receipt)
        self.addCleanup(lambda window=window: window.destroy() if window.winfo_exists() else None)
        labels = self.label_texts(window)
        self.assertIn("No items listed.", labels)
        self.assert_no_save(window)
        self.assertIn("Total: $0.00", labels)
        self.assertIn("Time: Not provided", labels)
        self.assertEqual(self.receipt_table(window)._components, [])


if __name__ == "__main__":
    unittest.main()
