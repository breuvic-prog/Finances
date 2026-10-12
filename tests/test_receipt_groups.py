import unittest

from classes.financial_transaction_class import FinancialTransaction
from classes.general.date_class import Date
from classes.general.dollar_amount_class import DollarAmount
from classes.general.time_class import Time
from classes.grocery_item import GroceryItem
from classes.managers.receipt_group_manager import ReceiptGroupManager
from classes.receipt_class import Receipt
from enums.finances.categories_enum import Categories
from enums.finances.descriptions_enum import Descriptions
from enums.finances.is_essential_enum import IsEssential
from enums.finances.locations_enum import Locations


def purchase_with(items, total):
    date = Date(day=29, month=9, year=2026)
    subtotal = sum(item.cost for item in items)
    receipt = Receipt("Walmart", date, Time(hours=11, minutes=6, seconds=6),
                      subtotal, total - subtotal, total, items)
    return FinancialTransaction(date, DollarAmount(-total), location=Locations.WALMART,
                                receipt=receipt, purchase_title="WALMART PURCHASE")


class ReceiptGroupTests(unittest.TestCase):
    def test_hidden_purchase_flag_survives_splitting_without_changing_the_amounts(self):
        purchase = purchase_with([GroceryItem("A", 10, is_essential=IsEssential.ESSENTIAL),
                                  GroceryItem("B", 20, is_essential=IsEssential.NON_ESSENTIAL)], 31.50)
        purchase.hidden = True
        rows = ReceiptGroupManager.rows(purchase)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row.transaction.hidden and ReceiptGroupManager.is_hidden(row) for row in rows))
        self.assertEqual(sum(round(row.transaction.amount * 100) for row in rows), -3150)
        self.assertTrue(all(not row.transaction.excluded_from_totals for row in rows))
        purchase.hidden = False
        self.assertTrue(all(not row.transaction.hidden for row in ReceiptGroupManager.rows(purchase)))

    def test_groups_by_all_classification_fields_and_combines_matching_items(self):
        items = [
            GroceryItem("A", 10, category=Categories.SHOPPING, description=Descriptions.OTHER,
                        is_essential=IsEssential.ESSENTIAL),
            GroceryItem("B", 5, category=Categories.SHOPPING, description=Descriptions.OTHER,
                        is_essential=IsEssential.ESSENTIAL),
            GroceryItem("C", 7, category=Categories.SHOPPING, description="Basics",
                        is_essential=IsEssential.ESSENTIAL),
            GroceryItem("D", 9, category=Categories.HOUSING, description=Descriptions.OTHER,
                        is_essential=IsEssential.ESSENTIAL),
            GroceryItem("E", 11, category=Categories.HOUSING, description=Descriptions.OTHER,
                        is_essential=IsEssential.NON_ESSENTIAL),
        ]
        purchase = purchase_with(items, 42)
        rows = ReceiptGroupManager.rows(purchase)
        self.assertEqual(len(rows), 4)
        self.assertEqual([row.transaction.amount for row in rows], [-15, -7, -9, -11])
        self.assertEqual(rows[0].items, tuple(items[:2]))
        for row in rows:
            self.assertIs(row.purchase, purchase)
            self.assertIs(row.transaction.receipt, purchase.receipt)
            self.assertIs(row.transaction.date, purchase.date)
            self.assertEqual(row.transaction.location, Locations.WALMART)
            self.assertEqual(row.transaction.purchase_title, purchase.purchase_title)
        self.assertIsNone(purchase.category)
        self.assertIsNone(purchase.description)
        self.assertIsNone(purchase.is_essential)
        self.assertEqual(purchase.amount, -42)

    def test_shares_tax_by_item_cost_and_preserves_the_total(self):
        purchase = purchase_with([GroceryItem("A", 10, is_essential=IsEssential.ESSENTIAL),
                                  GroceryItem("B", 20, is_essential=IsEssential.NON_ESSENTIAL)], 31.50)
        rows = ReceiptGroupManager.rows(purchase)
        self.assertEqual([str(row.transaction.amount) for row in rows], ["-$10.50", "-$21.00"])
        self.assertEqual(sum(round(row.transaction.amount * 100) for row in rows), -3150)

    def test_quantities_fractional_quantities_and_discounts_are_included(self):
        for total, expected in ((8.89, [-779, -110]), (7.27, [-637, -90])):
            with self.subTest(total=total):
                purchase = purchase_with([
                    GroceryItem("A", 2.36, quantity=3, is_essential=IsEssential.ESSENTIAL),
                    GroceryItem("B", 2, quantity=0.5, is_essential=IsEssential.NON_ESSENTIAL),
                ], total)
                rows = ReceiptGroupManager.rows(purchase)
                self.assertEqual([round(row.transaction.amount * 100) for row in rows], expected)
                self.assertEqual(sum(expected), round(purchase.amount * 100))

    def test_rounding_assigns_each_penny_once_and_is_stable(self):
        purchase = purchase_with([GroceryItem(name, 1, description=name) for name in ("A", "B", "C")], 3.01)
        for _ in range(3):
            rows = ReceiptGroupManager.rows(purchase)
            self.assertEqual([round(row.transaction.amount * 100) for row in rows], [-101, -100, -100])
            self.assertEqual(sum(round(row.transaction.amount * 100) for row in rows), -301)

    def test_zero_cost_items_and_refunds_keep_the_original_total(self):
        purchase = purchase_with([GroceryItem("A", 0, is_essential=IsEssential.ESSENTIAL),
                                  GroceryItem("B", 0, is_essential=IsEssential.NON_ESSENTIAL)], 0.03)
        self.assertEqual([round(row.transaction.amount * 100) for row in ReceiptGroupManager.rows(purchase)], [-2, -1])
        refund = purchase_with([GroceryItem("A", 10, is_essential=IsEssential.ESSENTIAL),
                                GroceryItem("B", 20, is_essential=IsEssential.NON_ESSENTIAL)], -31.50)
        self.assertEqual([str(row.transaction.amount) for row in ReceiptGroupManager.rows(refund)], ["$10.50", "$21.00"])

    def test_absent_empty_and_unclassified_receipts_keep_one_original_row(self):
        purchases = [FinancialTransaction(Date(day=29, month=9, year=2026), DollarAmount(-5)),
                     purchase_with([], 5),
                     purchase_with([GroceryItem("A", 2), GroceryItem("B", 3)], 5)]
        for purchase in purchases:
            with self.subTest(receipt=purchase.receipt):
                row, = ReceiptGroupManager.rows(purchase)
                self.assertIs(row.transaction, purchase)
                self.assertIsNone(row.items)

    def test_whole_purchase_fields_override_items_without_mutating_the_receipt(self):
        first = GroceryItem("A", 2, category=Categories.HOUSING, is_essential=IsEssential.NON_ESSENTIAL)
        second = GroceryItem("B", 3, category=Categories.CAR, description="Gas")
        purchase = purchase_with([first, second], 5)
        purchase.category = Categories.SHOPPING
        purchase.description = Descriptions.OTHER
        purchase.is_essential = IsEssential.ESSENTIAL
        row, = ReceiptGroupManager.rows(purchase)
        self.assertIs(row.transaction, purchase)
        self.assertIs(first.category, Categories.HOUSING)
        self.assertIs(first.is_essential, IsEssential.NON_ESSENTIAL)
        self.assertIs(second.category, Categories.CAR)
        self.assertEqual(second.description, "Gas")

    def test_matching_items_form_one_classified_row_without_locking_the_purchase(self):
        purchase = purchase_with([GroceryItem("A", 2, is_essential=IsEssential.ESSENTIAL),
                                  GroceryItem("B", 3, is_essential=IsEssential.ESSENTIAL)], 5.20)
        row, = ReceiptGroupManager.rows(purchase)
        self.assertEqual(row.transaction.amount, -5.20)
        self.assertIs(row.transaction.is_essential, IsEssential.ESSENTIAL)
        self.assertIsNone(purchase.is_essential)
        self.assertEqual(row.items, tuple(purchase.receipt.items))

    def test_group_rows_keep_the_document_source_and_lock_values_from_receipt_items(self):
        item = GroceryItem("A", 5)
        item.category = Categories.SHOPPING
        item.description = Descriptions.OTHER
        item.is_essential = IsEssential.ESSENTIAL
        purchase = FinancialTransaction(Date(29, 9, 2026), DollarAmount(-5),
                                        receipt=Receipt("Walmart", Date(29, 9, 2026), None, 5, 0, 5, [item]),
                                        source=Locations.DISCOVER)
        row, = ReceiptGroupManager.rows(purchase)
        self.assertIs(row.transaction.source, Locations.DISCOVER)
        for field in ("category", "description", "is_essential"):
            self.assertTrue(row.transaction.is_field_locked(field))
            self.assertFalse(item.is_field_locked(field))
            self.assertIsNone(getattr(purchase, field))


if __name__ == "__main__":
    unittest.main()
