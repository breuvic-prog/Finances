import tkinter as tk
import unittest
from tkinter.scrolledtext import ScrolledText
from unittest.mock import Mock, patch

from classes.custom_tk_components.tk_table_class import TkTable
from classes.financial_transaction_class import FinancialTransaction
from classes.general.date_class import Date
from classes.general.dollar_amount_class import DollarAmount
from classes.general.time_class import Time
from classes.grocery_item import GroceryItem
from classes.pages.child_pages.expense_reveiw_pages import final_review_page
from classes.receipt_class import Receipt
from enums.finances.categories_enum import Categories
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


def make_transaction(location=Locations.WALMART, amount=-2.49, day=29, year=2026, receipt=None):
    return FinancialTransaction(
        date=Date(day=day, month=9, year=year),
        amount=DollarAmount(amount),
        location=location,
        description="Purchase",
        receipt=receipt,
    )


class ReceiptMatchingTests(unittest.TestCase):
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
        for location, amount, category in (
            (Locations.KWIK_TRIP, -25, Categories.GROCERIES),
            (Locations.KWIK_TRIP, -24.99, Categories.GROCERIES),
            (Locations.KWIK_TRIP, 0, Categories.GROCERIES),
            (Locations.KWIK_TRIP, 50, Categories.GROCERIES),
            (Locations.WALMART, -50, Categories.GROCERIES),
            (Locations.KWIK_TRIP, -50, Categories.NOT_INCLUDED),
        ):
            with self.subTest(location=location, amount=amount, category=category):
                transaction = make_transaction(location=location, amount=amount)
                transaction.category = category
                transaction.is_essential = IsEssential.NON_ESSENTIAL
                final_review_page._set_transaction_defaults_from_receipts([transaction])
                self.assertEqual(transaction.description, "Purchase")
                self.assertEqual(transaction.category, category)
                self.assertEqual(transaction.is_essential, IsEssential.NON_ESSENTIAL)

    def test_kwik_trip_receipts_without_gas_default_to_discretionary_non_essential(self):
        for location in ("Kwik Trip", "Kwik Star"):
            for total in (2.49, 50):
                with self.subTest(location=location, total=total):
                    receipt = make_receipt(location=location, total=total, item_name="Glazed donut")
                    transaction = make_transaction(location=Locations.KWIK_TRIP, amount=-total)
                    transaction.category = Categories.GROCERIES
                    transaction.is_essential = IsEssential.ESSENTIAL
                    final_review_page._assign_receipts([transaction], [receipt])
                    final_review_page._set_transaction_defaults_from_receipts([transaction])
                    self.assertIs(transaction.receipt, receipt)
                    self.assertEqual(transaction.description, "Purchase")
                    self.assertEqual(transaction.category, Categories.DISCRETIONARY_SPENDING)
                    self.assertEqual(transaction.is_essential, IsEssential.NON_ESSENTIAL)

    def test_kwik_trip_refunds_excluded_payments_and_missing_receipts_preserve_defaults(self):
        for amount, category, receipt in (
            (2.49, Categories.GROCERIES, make_receipt(item_name="Glazed donut")),
            (-2.49, Categories.NOT_INCLUDED, make_receipt(item_name="Glazed donut")),
            (-2.49, Categories.GROCERIES, None),
        ):
            with self.subTest(amount=amount, category=category, receipt=receipt):
                transaction = make_transaction(location=Locations.KWIK_TRIP, amount=amount, receipt=receipt)
                transaction.category = category
                transaction.is_essential = IsEssential.ESSENTIAL
                final_review_page._set_transaction_defaults_from_receipts([transaction])
                self.assertEqual(transaction.category, category)
                self.assertEqual(transaction.is_essential, IsEssential.ESSENTIAL)

    def test_missing_and_unrelated_receipts_preserve_defaults(self):
        for item_name in (None, "Body Wash", "Las Vegas magnet", "Gasket"):
            with self.subTest(item_name=item_name):
                receipt = None if item_name is None else make_receipt(item_name=item_name)
                transaction = make_transaction(receipt=receipt)
                transaction.category = Categories.GROCERIES
                transaction.is_essential = IsEssential.ESSENTIAL
                final_review_page._set_transaction_defaults_from_receipts([transaction])
                self.assertEqual(transaction.category, Categories.GROCERIES)
                self.assertEqual(transaction.is_essential, IsEssential.ESSENTIAL)

    def test_refunds_deposits_and_excluded_payments_preserve_defaults(self):
        for amount, category, essential in (
            (2.49, Categories.CAR, IsEssential.NOT_INCLUDED),
            (2.49, Categories.NOT_INCLUDED, IsEssential.NOT_INCLUDED),
            (0, Categories.GROCERIES, IsEssential.NON_ESSENTIAL),
            (-2.49, Categories.NOT_INCLUDED, IsEssential.NOT_INCLUDED),
        ):
            with self.subTest(amount=amount, category=category):
                transaction = make_transaction(amount=amount, receipt=make_receipt(item_name="Gas"))
                transaction.category = category
                transaction.is_essential = essential
                final_review_page._set_transaction_defaults_from_receipts([transaction])
                self.assertEqual(transaction.category, category)
                self.assertEqual(transaction.is_essential, essential)


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
        self.page = final_review_page.FinalReviewPage(self.root, Mock())

    def tearDown(self):
        self.page._root.destroy()

    def hidden_popup(self, *args, **kwargs):
        window = self.toplevel_type(*args, **kwargs)
        window.withdraw()
        return window

    def receipt_contents(self, window):
        widgets = [window]
        while widgets:
            widget = widgets.pop()
            if isinstance(widget, ScrolledText):
                return widget
            widgets.extend(widget.winfo_children())
        self.fail("Receipt popup has no text viewer")

    def test_receipt_column_has_buttons_only_for_matches_and_opens_each_rows_receipt(self):
        receipts = [make_receipt(), make_receipt(total=4.06)]
        transactions = [make_transaction(), make_transaction(amount=-4.06), make_transaction(amount=-9.99)]
        with patch.object(final_review_page, "_import_receipts", return_value=receipts), \
                patch.object(final_review_page, "_import_transactions", return_value=transactions):
            self.page.activate()

        table = next(widget for widget in self.page._root.winfo_children() if isinstance(widget, TkTable))
        self.assertEqual([column.text for column in table.columns],
                         ["Date", "Time", "Location", "Amount", "Description", "Category", "Is Essential?", "Receipt"])
        self.assertEqual([row[1].cget("text") for row in table._components],
                         ["11:06 AM", "11:06 AM", ""])
        first, second, unmatched = [row[-1] for row in table._components]
        self.assertIsInstance(first, tk.Button)
        self.assertIsInstance(second, tk.Button)
        self.assertIsInstance(unmatched, tk.Label)
        self.assertEqual(unmatched.cget("text"), "")
        self.assertEqual(first.grid_info()["in"], table._body)
        with patch.object(self.page, "_show_receipt", return_value=None) as show:
            first.invoke()
            show.assert_called_once_with(receipts[0])
            second.invoke()
            self.assertEqual(show.call_count, 2)
            show.assert_called_with(receipts[1])

    def test_popup_shows_receipt_metadata_items_links_and_totals_read_only(self):
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            window = self.page._show_receipt(make_receipt())
        contents = self.receipt_contents(window)
        text = contents.get("1.0", "end-1c")
        for value in (
            "Location: Walmart", "Date: 9/29/2026", "Time: 11:06:06 AM",
            "Subtotal: $2.36", "Tax: $0.13", "Total: $2.49",
            "Body Wash", "Price: $2.36", "https://example.com/body-wash",
        ):
            self.assertIn(value, text)
        self.assertEqual(contents.cget("state"), "disabled")
        close = next(widget for widget in window.winfo_children() if isinstance(widget, tk.Button))
        close.invoke()
        self.assertFalse(window.winfo_exists())

    def test_matched_gas_receipt_sets_defaults_before_displaying_transaction(self):
        receipt = make_receipt(location="Kwik Trip", total=19.84, day=26,
                               item_name="UNL 88 Gasoline (4.670 gal @ $4.249/gal)")
        transaction = make_transaction(location=Locations.KWIK_TRIP, amount=-19.84, day=26)
        transaction.category = Categories.GROCERIES
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
        self.assertEqual(table._components[0][4].cget("text"), "Gas")
        self.assertEqual(table._components[0][5].cget("text"), "Car")
        self.assertEqual(table._components[0][6].cget("text"), "Essential")
        self.assertEqual(table._components[0][6].cget("bg"), "green")
        self.assertIsNone(inferred_gas.receipt)
        self.assertEqual(table._components[1][4].cget("text"), "Gas")
        self.assertEqual(table._components[1][5].cget("text"), "Car")
        self.assertEqual(table._components[1][6].cget("text"), "Essential")
        self.assertEqual(table._components[1][6].cget("bg"), "green")

    def test_popup_accepts_receipts_without_time_or_items(self):
        receipt = Receipt("Walmart", Date(day=29, month=9, year=2026), None, 0, 0, 0, [])
        with patch.object(final_review_page.tk, "Toplevel", side_effect=self.hidden_popup):
            window = self.page._show_receipt(receipt)
        text = self.receipt_contents(window).get("1.0", "end-1c")
        self.assertIn("No items listed.", text)
        self.assertIn("Total: $0.00", text)
        self.assertNotIn("Time:", text)


if __name__ == "__main__":
    unittest.main()
