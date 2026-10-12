import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pymupdf
from reportlab.platypus import SimpleDocTemplate

from classes.financial_transaction_class import FinancialTransaction
from classes.custom_tk_components.tk_table_class import get_location_colors
from classes.general.date_class import Date
from classes.general.dollar_amount_class import DollarAmount
from classes.general.time_class import Time
from classes.grocery_item import GroceryItem
from classes.managers.category_manager import CategoryManager
from classes.managers.expense_review_report import (
    CONTENT_WIDTH, ExpenseReviewReport, ExpenseSummary, ReportGenerationError, _ReportBuilder,
)
from classes.managers.receipt_group_manager import ReceiptGroupManager
from classes.receipt_class import Receipt
from enums.finances.categories_enum import Categories
from enums.finances.descriptions.car_descriptions_enum import CarDescriptions
from enums.finances.descriptions.housing_descriptions_enum import HousingDescriptions
from enums.finances.descriptions.income_descriptions_enum import IncomeDescriptions
from enums.finances.descriptions_enum import Descriptions
from enums.finances.is_essential_enum import IsEssential
from enums.finances.locations_enum import Locations


def transaction(amount, location=Locations.WALMART, category=Categories.SHOPPING,
                description=Descriptions.OTHER, essential=IsEssential.ESSENTIAL, receipt=None):
    return FinancialTransaction(Date(29, 9, 2026), DollarAmount(amount), location=location,
                                category=category, description=description,
                                is_essential=essential, receipt=receipt)


def report_fixture():
    receipt = Receipt("Walmart", Date(29, 9, 2026), Time(11, 6, 6), 15, 1.5, 16.5, [
        GroceryItem("Milk & Bread", 5, "https://example.com/milk", quantity=2,
                    category=Categories.SHOPPING, description=Descriptions.OTHER,
                    is_essential=IsEssential.ESSENTIAL),
        GroceryItem("Toy", 5, category=Categories.DISCRETIONARY_SPENDING),
    ])
    mixed = transaction(-16.5, category=None, description=None, essential=None, receipt=receipt)
    gas_receipt = Receipt("Kwik Trip", Date(26, 9, 2026), Time(4, 5, 0), 19.84, 0, 19.84,
                          [GroceryItem("UNL 88 Gasoline", 19.84)])
    gas = transaction(-19.84, Locations.KWIK_TRIP, Categories.CAR, CarDescriptions.GAS,
                      receipt=gas_receipt)
    excluded = transaction(-999, Locations.FREEDOM_BANK, Categories.HOUSING,
                           essential=IsEssential.NOT_INCLUDED)
    purchases = [transaction(1000, category=Categories.INCOME, description=IncomeDescriptions.PAYCHECK), mixed,
                 transaction(-100, Locations.AMAZON, Categories.HOUSING, HousingDescriptions.RENT),
                 gas, excluded, transaction(3)]
    rows = [row for purchase in purchases for row in ReceiptGroupManager.rows(purchase)]
    return rows, [receipt, gas_receipt], purchases


class ExpenseSummaryTests(unittest.TestCase):
    def test_essential_income_and_both_sides_of_card_payments_do_not_inflate_spending(self):
        from classes.pages.child_pages.expense_reveiw_pages.final_review_page import _create_financial_transaction_object
        from enums.finances.credit_card.credit_card_headers_enum import CreditCardHeaders
        from enums.finances.credit_card.credit_card_categories_enum import CreditCardCategories
        purchases = []
        for title, amount, source, statement_category in (
            ("EMPLOYER PAYROLL", 1000, Locations.FREEDOM_BANK, None),
            ("CASHBACK BONUS REDEMPTION", 5, Locations.DISCOVER, CreditCardCategories.AWARDS_AND_REBATE_CREDITS),
            ("DISCOVER,E-PAYMENT", -500, Locations.FREEDOM_BANK, None),
            ("INTERNET PAYMENT - THANK YOU", 500, Locations.DISCOVER, CreditCardCategories.PAYMENTS_AND_CREDITS),
        ):
            purchases.append(_create_financial_transaction_object({
                CreditCardHeaders.TRANS_DATE: "09/03/2026", CreditCardHeaders.DESCRIPTION: title,
                CreditCardHeaders.AMOUNT: amount, CreditCardHeaders.CATEGORY: statement_category,
            }, source=source))
        for purchase in purchases[:2]:
            self.assertIs(purchase.is_essential, IsEssential.ESSENTIAL)
        rows = [row for purchase in purchases for row in ReceiptGroupManager.rows(purchase)]
        for all_positive_income, earned in ((False, 100000), (True, 100500)):
            summary = ExpenseSummary.from_rows(rows, all_positive_income=all_positive_income)
            self.assertEqual((summary.earned, summary.spent, summary.essential, summary.non_essential),
                             (earned, 0, 0, 0))

    def test_summary_uses_split_amounts_tax_and_classifications_without_double_counting(self):
        rows, receipts, purchases = report_fixture()
        summary = ExpenseSummary.from_rows(rows)
        self.assertEqual(summary.earned, 100000)
        self.assertEqual(summary.spent, 13634)
        self.assertEqual(summary.essential, 13084)
        self.assertEqual(summary.non_essential, 550)
        self.assertEqual(summary.essential + summary.non_essential, summary.spent)
        self.assertEqual(summary.essential_categories, {"Shopping": 1100, "Housing": 10000, "Car": 1984})
        self.assertEqual(summary.essential_descriptions["Housing"], {"Rent": 10000})
        self.assertEqual(summary.non_essential_locations, {"Walmart": 550})
        self.assertEqual(ExpenseSummary.from_rows(rows, all_positive_income=True).earned, 100300)
        self.assertEqual(purchases[1].amount, -16.5)
        self.assertIsNone(receipts[1].items[0].category)

    def test_not_included_excludes_rows_with_normal_locations_categories_and_descriptions(self):
        purchases = [transaction(-5, location=Locations.AMAZON, essential=IsEssential.NOT_INCLUDED),
                     transaction(5, category=Categories.INCOME, essential=IsEssential.NOT_INCLUDED),
                     transaction(-5, category=Categories.DISCRETIONARY_SPENDING, essential=IsEssential.NOT_INCLUDED)]
        rows = [row for purchase in purchases for row in ReceiptGroupManager.rows(purchase)]
        for all_positive_income in (False, True):
            summary = ExpenseSummary.from_rows(rows, all_positive_income=all_positive_income)
            self.assertEqual((summary.earned, summary.spent, summary.essential, summary.non_essential), (0, 0, 0, 0))


class ExpenseReviewPdfTests(unittest.TestCase):
    def setUp(self):
        tests_directory = Path(__file__).resolve().parent
        temporary_directory = tempfile.TemporaryDirectory(prefix="expense-pdf-", dir=tests_directory)
        self.workspace = Path(temporary_directory.name).resolve()
        if self.workspace.parent != tests_directory:
            raise RuntimeError("Unexpected temporary directory location.")
        self.addCleanup(temporary_directory.cleanup)
        self.destination = self.workspace / "Expense Review.pdf"

    def generate(self, rows, receipts):
        return ExpenseReviewReport.generate(self.destination, rows, receipts, date(2026, 9, 1), overwrite=True)

    def test_hidden_income_and_split_purchase_keep_totals_but_omit_expense_rows_and_receipt_details(self):
        rows, receipts, purchases = report_fixture()
        baseline = ExpenseSummary.from_rows(rows)
        purchases[0].hidden = True
        purchases[1].hidden = True
        builder = _ReportBuilder(rows, receipts, date(2026, 9, 1), False)
        self.assertEqual(builder.summary, baseline)
        self.assertTrue(all(row.purchase not in purchases[:2] for row in builder.visible_rows))
        self.assertEqual(builder.receipts, [receipts[1]])
        self.assertNotIn(id(receipts[0]), builder.receipt_numbers)
        self.generate(rows, receipts)
        with pymupdf.open(self.destination) as document:
            text = "\n".join(page.get_text() for page in document)
        for missing in ("Milk & Bread", "Toy", "Paycheck", "11:06", "-$11.00", "-$5.50", "$16.50"):
            self.assertNotIn(missing, text)
        self.assertIn("Amount earned: $1,000.00", text)
        self.assertIn("Amount spent: $136.34", text)
        self.assertIn("UNL 88 Gasoline", text)

    def test_all_hidden_transactions_still_generate_summary_with_empty_details_and_receipts(self):
        rows, receipts, purchases = report_fixture()
        for purchase in purchases:
            purchase.hidden = True
        self.generate(rows, receipts)
        with pymupdf.open(self.destination) as document:
            text = "\n".join(page.get_text() for page in document)
        self.assertIn("Amount earned: $1,000.00", text)
        self.assertIn("Amount spent: $136.34", text)
        self.assertIn("No visible transactions", text)
        self.assertIn("No receipts", text)
        self.assertNotIn("UNL 88 Gasoline", text)

    def test_discover_location_uses_the_editor_colors_in_the_exported_pdf(self):
        purchase = transaction(5.77, location=Locations.DISCOVER)
        self.generate(ReceiptGroupManager.rows(purchase), [])
        background, foreground = get_location_colors(Locations.DISCOVER)
        expected_fill = tuple(int(background[index:index + 2], 16) / 255 for index in (1, 3, 5))
        with pymupdf.open(self.destination) as document:
            page = next(page for page in document if "Expenses\n" in page.get_text())
            cell, = page.search_for("Discover")
            self.assertTrue(any(drawing["rect"].contains(cell) and drawing["fill"] is not None
                                and all(abs(actual - expected) < .01
                                        for actual, expected in zip(drawing["fill"], expected_fill))
                                for drawing in page.get_drawings()))
            spans = [span for block in page.get_text("dict")["blocks"] if "lines" in block
                     for line in block["lines"] for span in line["spans"] if span["text"] == "Discover"]
            self.assertEqual(spans[0]["color"], int(foreground[1:], 16))

    def test_pdf_contains_all_sections_charts_rows_receipts_and_navigation(self):
        rows, receipts, purchases = report_fixture()
        result = self.generate(rows, receipts)
        self.assertEqual(result, self.destination)
        with pymupdf.open(result) as document:
            text = "\n".join(page.get_text() for page in document)
            for value in ("Expense Review, September 2026", "Amount earned: $1,000.00",
                          "Amount spent: $136.34", "Difference: $863.66", "Essential vs Non-Essential Spending",
                          "Essential Spending", "Shopping - by description", "Car - by description",
                          "Housing - by description", "Non-Essential Spending", "Expenses", "Receipts",
                          "$130.84", "$5.50", "96.0%", "4.0%", "Not Included", "-$999.00",
                          "Receipt 1: Kwik Trip", "Receipt 2: Walmart", "Milk & Bread", "UNL 88 Gasoline",
                          "-$10.00", "Subtotal: $15.00", "Tax: $1.50", "Total: $16.50", "Income", "Paycheck",
                          "positive Income transactions"):
                with self.subTest(value=value):
                    self.assertIn(value, text)
            self.assertEqual(text.count("Receipt 1: Kwik Trip"), 1)
            self.assertEqual(text.count("Receipt 2: Walmart"), 1)
            links = [link for page in document for link in page.get_links()]
            self.assertTrue(any(link.get("uri") == "https://example.com/milk" for link in links))
            self.assertTrue(any(link["kind"] == pymupdf.LINK_GOTO for link in links))
            self.assertEqual(document.metadata["title"], "Expense Review, September 2026")
            self.assertTrue(all(page.rect.height > page.rect.width for page in document))
            fills = [drawing["fill"] for page in document for drawing in page.get_drawings() if drawing["fill"]]
            self.assertTrue(any(abs(color[0] - 0) < .01 and abs(color[1] - .502) < .01 and abs(color[2]) < .01
                                for color in fills))
            self.assertTrue(any(color[0] > .99 and color[1] < .01 and color[2] < .01 for color in fills))
            self.assertTrue(any(color[0] < .01 and abs(color[1] - .325) < .01 and abs(color[2] - .886) < .01
                                for color in fills))
            for page in document:
                words = page.get_text("words")
                for word in words:
                    pair = CategoryManager.colors(word[4]) if word[4] in ("Shopping", "Housing", "Car", "Income") else None
                    if pair is None or "Expenses\n" not in page.get_text() and "Receipt 1:" not in page.get_text():
                        continue
                    cell = pymupdf.Rect(word[:4])
                    expected = tuple(int(pair[0][index:index + 2], 16) / 255 for index in (1, 3, 5))
                    self.assertTrue(any(drawing["rect"].contains(cell) and drawing["fill"] is not None
                                        and all(abs(actual - target) < .01 for actual, target
                                                in zip(drawing["fill"], expected))
                                        for drawing in page.get_drawings()), word[4])
            title_words = [span for page in document for block in page.get_text("dict")["blocks"]
                           if "lines" in block for line in block["lines"] for span in line["spans"]
                           if span["size"] >= 13 and span["text"].strip().lower() in ("essential", "non-essential")]
            self.assertTrue(any(span["text"].strip() == "Essential" for span in title_words))
            self.assertTrue(any(span["text"].strip() == "Non-Essential" for span in title_words))
            for span in title_words:
                expected = 0xFF0000 if span["text"].strip().lower() == "non-essential" else 0x008000
                self.assertEqual(span["color"], expected)
        self.assertIsNone(receipts[1].items[0].description)
        self.assertIsNone(receipts[1].items[0].category)
        self.assertIsNone(purchases[1].description)

    def test_category_charts_use_the_same_colors_as_the_editor_and_report_tables(self):
        rows, receipts, _ = report_fixture()
        self.generate(rows, receipts)
        with pymupdf.open(self.destination) as document:
            page = next(page for page in document if "Essential spending by category" in page.get_text())
            fills = [drawing["fill"] for drawing in page.get_drawings() if drawing["fill"]]
            for category in ExpenseSummary.from_rows(rows).essential_categories:
                background, _ = CategoryManager.colors(category)
                expected = tuple(int(background[index:index + 2], 16) / 255 for index in (1, 3, 5))
                # Each category has a matching pie slice and bar in the exported PDF.
                self.assertGreaterEqual(sum(all(abs(actual - target) < .01
                                                for actual, target in zip(fill, expected))
                                            for fill in fills), 2, category)

    def test_short_receipts_share_a_portrait_page_with_a_visible_divider_and_yes_no_cells(self):
        rows, receipts, _ = report_fixture()
        self.generate(rows, receipts)
        with pymupdf.open(self.destination) as document:
            page = next(page for page in document if "Receipt 1: Kwik Trip" in page.get_text())
            self.assertIn("Receipt 2: Walmart", page.get_text())
            self.assertNotIn("Expenses\n", page.get_text())
            expenses_page = next(value for value in document if "Expenses\n" in value.get_text())
            self.assertEqual(page.number, expenses_page.number + 1)
            self.assertLess(page.search_for("Receipts")[0].y0, 60)
            first = page.search_for("Receipt 1: Kwik Trip")[0]
            second = page.search_for("Receipt 2: Walmart")[0]
            first_item, = page.search_for("UNL 88 Gasoline")
            self.assertTrue(any(first_item.y1 + 6 < drawing["rect"].y0 < second.y0
                                and drawing["rect"].width > 500 and drawing["width"] >= 3
                                and drawing["color"] == (0, 0, 0)
                                for drawing in page.get_drawings()))
            for word, expected in (("Yes", (0, .502, 0)), ("No", (1, 0, 0))):
                cells = [pymupdf.Rect(value[:4]) for value in page.get_text("words") if value[4] == word]
                self.assertTrue(cells)
                for cell in cells:
                    self.assertTrue(any(drawing["rect"].contains(cell)
                                        and drawing["fill"] is not None
                                        and all(abs(actual - target) < .01
                                                for actual, target in zip(drawing["fill"], expected))
                                        for drawing in page.get_drawings()))
            for section in (first, second):
                category = next(cell for cell in page.search_for("Category") if cell.y0 > section.y0)
                description = next(cell for cell in page.search_for("Description") if cell.y0 > section.y0)
                self.assertLess(category.x0, description.x0)

    def test_missing_receipt_cells_are_black_and_columns_stay_within_portrait_margins(self):
        rows, receipts, _ = report_fixture()
        self.generate(rows, receipts)
        with pymupdf.open(self.destination) as document:
            page = next(page for page in document if "Expenses\n" in page.get_text())
            category = page.search_for("Category")[0]
            description = page.search_for("Description")[0]
            self.assertLess(category.x0, description.x0)
            fills = [drawing for drawing in page.get_drawings() if drawing["fill"] is not None]
            for row in rows:
                value = float(row.transaction.amount)
                amount = page.search_for(f"{'-' if value < 0 else ''}${abs(value):,.2f}")[0]
                center = pymupdf.Point(548, (amount.y0 + amount.y1) / 2)
                black = any(drawing["rect"].contains(center)
                            and max(drawing["fill"]) < .01 for drawing in fills)
                self.assertEqual(black, row.transaction.receipt is None)
            self.assertTrue(all(35 <= drawing["rect"].x0 <= drawing["rect"].x1 <= page.rect.width - 35
                                for drawing in fills))

    def test_small_slice_labels_are_outside_and_many_callouts_do_not_overlap(self):
        builder = _ReportBuilder([], [], date(2026, 9, 1), False)
        values = {"Large group": 100000}
        values.update({f"Small group {index}": index for index in range(1, 13)})
        chart = builder.pie_with_legend(values, CONTENT_WIDTH)
        document = SimpleDocTemplate(str(self.destination), pagesize=(612, 792),
                                     leftMargin=36, rightMargin=36)
        document.build([chart])
        with pymupdf.open(self.destination) as document:
            page = document[0]
            pie = max((drawing["rect"] for drawing in page.get_drawings()
                       if drawing["fill"] is not None and drawing["rect"].width > 100),
                      key=lambda rectangle: rectangle.width * rectangle.height)
            large, = page.search_for("$1,000.00")
            self.assertTrue(pie.contains(large))
            labels = []
            for index in range(1, 13):
                label, = page.search_for(f"$0.{index:02}")
                self.assertFalse(pie.intersects(label))
                self.assertGreaterEqual(label.x0, 36)
                self.assertLessEqual(label.x1, 576)
                labels.append(label)
            self.assertFalse(any(first.intersects(second)
                                 for index, first in enumerate(labels) for second in labels[index + 1:]))

    def test_description_charts_are_side_by_side_and_several_categories_share_a_page(self):
        rows, receipts, _ = report_fixture()
        self.generate(rows, receipts)
        with pymupdf.open(self.destination) as document:
            page = next(page for page in document if "Car - by description" in page.get_text())
            for category in ("Car", "Shopping", "Housing"):
                self.assertIn(f"{category} - by description", page.get_text())
            fills = [drawing["rect"] for drawing in page.get_drawings() if drawing["fill"] is not None]
            headings = [page.search_for(f"{category} - by description")[0]
                        for category in ("Car", "Shopping", "Housing")]
            headings.sort(key=lambda rectangle: rectangle.y0)
            for index, heading in enumerate(headings):
                lower = headings[index + 1].y0 if index + 1 < len(headings) else page.rect.height - 36
                pie = next(rectangle for rectangle in fills
                           if heading.y1 < rectangle.y0 < lower and rectangle.x1 < 300
                           and rectangle.width > 100 and abs(rectangle.width - rectangle.height) < 1)
                bar = next(rectangle for rectangle in fills
                           if heading.y1 < rectangle.y0 < lower and rectangle.x0 > 400)
                self.assertLess(pie.x1, bar.x0)
                self.assertLess(abs((pie.y0 + pie.y1 - bar.y0 - bar.y1) / 2), 20)
                self.assertLessEqual(bar.x1, page.rect.width - 36)

    def test_compact_chart_callouts_remain_legible_and_within_their_column(self):
        builder = _ReportBuilder([], [], date(2026, 9, 1), False)
        values = {"Large group": 100000, **{f"Small {index}": index for index in range(1, 12)}}
        chart = builder.paired_charts(values, side_by_side=True)
        document = SimpleDocTemplate(str(self.destination), pagesize=(612, 792),
                                     leftMargin=36, rightMargin=36)
        document.build([chart])
        with pymupdf.open(self.destination) as document:
            page = document[0]
            labels = []
            for index in range(1, 12):
                matches = page.search_for(f"$0.{index:02}")
                self.assertEqual(len(matches), 2)
                label = min(matches, key=lambda rectangle: rectangle.x0)
                self.assertGreaterEqual(label.x0, 36)
                self.assertLess(label.x1, 330)
                self.assertGreaterEqual(label.y0, 36)
                labels.append(label)
            self.assertFalse(any(first.intersects(second)
                                 for index, first in enumerate(labels) for second in labels[index + 1:]))

    def test_long_receipt_header_and_first_item_stay_together(self):
        earlier = Receipt("Earlier store", Date(28, 9, 2026), None, 15, 0, 15,
                          [GroceryItem(f"Earlier item {index}", 1) for index in range(15)])
        receipt = Receipt("Walmart", Date(29, 9, 2026), None, 50, 0, 50,
                          [GroceryItem(f"Long-receipt-item-{index:02}", 1) for index in range(50)])
        self.generate([], [earlier, receipt])
        with pymupdf.open(self.destination) as document:
            first = next(page for page in document if "Receipt 2: Walmart" in page.get_text())
            self.assertIn("Long-receipt-item-00", first.get_text())
            self.assertIn("Subtotal: $50.00", first.get_text())
            self.assertIn("Long-receipt-item-49", "\n".join(page.get_text() for page in document))

    def test_empty_sections_and_receipts_outside_the_review_period_are_handled(self):
        earlier = Receipt("Outside review month", Date(1, 8, 2026), None, 0, 0, 0, [])
        older = Receipt("Outside review year", Date(1, 9, 2025), None, 0, 0, 0, [])
        self.generate([], [earlier, older])
        with pymupdf.open(self.destination) as document:
            text = "\n".join(page.get_text() for page in document)
        self.assertIn("Amount spent: $0.00", text)
        self.assertIn("No spending in this section.", text)
        self.assertIn("No transactions in this review.", text)
        self.assertIn("No receipts for this review month.", text)
        self.assertNotIn("Outside review", text)

    def test_negative_difference_is_red_and_a_zero_spending_share_is_listed(self):
        purchase = transaction(-100)
        self.generate(ReceiptGroupManager.rows(purchase), [])
        with pymupdf.open(self.destination) as document:
            page = document[0]
            self.assertIn("Non-Essential: 0.0%", page.get_text())
            spans = [span for block in page.get_text("dict")["blocks"] if "lines" in block
                     for line in block["lines"] for span in line["spans"]]
            difference = next(span for span in spans if "Difference:" in span["text"])
            self.assertEqual(difference["text"], "Difference: -$100.00")
            self.assertEqual(difference["color"], 0xFF0000)

    def test_long_tables_paginate_and_preserve_every_transaction_and_receipt_item(self):
        items = [GroceryItem(f"Item-{index:03}: " + "Long item name " * 10, 1,
                             category=Categories.SHOPPING, description=Descriptions.OTHER,
                             is_essential=IsEssential.ESSENTIAL) for index in range(100)]
        receipt = Receipt("Walmart", Date(29, 9, 2026), None, 100, 0, 100, items)
        purchases = [transaction(-1, description=f"Transaction-{index:03}: " + "Long description " * 6)
                     for index in range(100)]
        purchases.append(transaction(-100, receipt=receipt))
        rows = [row for purchase in purchases for row in ReceiptGroupManager.rows(purchase)]
        self.generate(rows, [receipt])
        with pymupdf.open(self.destination) as document:
            text = "\n".join(page.get_text() for page in document)
            self.assertGreater(len(document), 10)
            for index in range(100):
                self.assertIn(f"Transaction-{index:03}:", text)
                self.assertIn(f"Item-{index:03}:", text)
            self.assertGreater(text.count("Quantity"), 1)
            self.assertGreater(text.count("Is Essential?"), 2)
            self.assertIn("Other groups (combined)", " ".join(text.split()))
            self.assertIn("Groups 97-101 of 101", text)
            first_description_page = next(page for page in document if "Shopping - by description" in page.get_text())
            self.assertIn("Groups 1-12 of 101", first_description_page.get_text())

    def test_failed_render_preserves_an_existing_report(self):
        self.destination.write_bytes(b"original report")
        with patch("classes.managers.expense_review_report.SimpleDocTemplate.build",
                   side_effect=ValueError("Cannot render")), \
                self.assertRaisesRegex(ReportGenerationError, "Cannot render"):
            self.generate([], [])
        self.assertEqual(self.destination.read_bytes(), b"original report")
        self.assertEqual(list(self.workspace.iterdir()), [self.destination])

    def test_existing_report_requires_authorization_before_rendering_or_writing(self):
        self.destination.write_bytes(b"original report")
        with patch("classes.managers.expense_review_report.SimpleDocTemplate.build") as render, \
                self.assertRaises(FileExistsError):
            ExpenseReviewReport.generate(self.destination, [], [])
        render.assert_not_called()
        self.assertEqual(self.destination.read_bytes(), b"original report")
        self.assertEqual(list(self.workspace.iterdir()), [self.destination])

    def test_new_report_is_written_without_overwrite_authorization(self):
        ExpenseReviewReport.generate(self.destination, [], [], date(2026, 9, 1))
        with pymupdf.open(self.destination) as document:
            self.assertIn("Expense Review, September 2026", document[0].get_text())
        self.assertEqual(list(self.workspace.iterdir()), [self.destination])

    def test_failed_replace_preserves_an_existing_report_and_removes_the_temporary_file(self):
        self.destination.write_bytes(b"original report")
        with patch("classes.managers.expense_review_report.os.replace", side_effect=OSError("Drive is full")), \
                self.assertRaisesRegex(OSError, "Drive is full"):
            self.generate([], [])
        self.assertEqual(self.destination.read_bytes(), b"original report")
        self.assertEqual(list(self.workspace.iterdir()), [self.destination])


if __name__ == "__main__":
    unittest.main()
