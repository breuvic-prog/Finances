import unittest
from unittest.mock import patch

from classes.general.dollar_amount_class import DollarAmount
from classes.pages.child_pages.expense_reveiw_pages import final_review_page
from enums.files_enum import Files
from enums.finances.categories_enum import Categories
from enums.finances.is_essential_enum import IsEssential
from enums.finances.locations_enum import Locations
from enums.paths_enum import Paths


TRANSACTIONS_HEADING = "-- ITEMIZED TRANSACTIONS ------------------ DEBITS --- CREDITS -----------------"


def statement(*lines, period="01-SEP-26 THRU 30-SEP-26"):
    return "\n".join(["A STATEMENT OF YOUR ACCOUNT", period, TRANSACTIONS_HEADING, *lines])


def transaction_line(date, description, amount, credit=False):
    amount_column_end = 62 if credit else 50
    return f" {date:>4}  {description}".ljust(amount_column_end - len(amount)) + amount


class CheckingAccountImportTests(unittest.TestCase):
    def import_pages(self, *pages):
        with patch.object(final_review_page.PdfManager, "open", return_value=list(pages)) as reader:
            transactions = final_review_page._import_checking_account_transactions()
        reader.assert_called_once_with(
            name=Files.CHECKING_ACCOUNT_PREVIOUS_MONTH_STATEMENT_PDF,
            path=Paths.ASSETS_PDFS,
        )
        return transactions

    def test_imports_debits_and_credits_from_their_columns(self):
        transactions = self.import_pages(statement(
            transaction_line("9-03", "Deposit by internet", "500.00", credit=True),
            "       From Savings XXXXXXX-123",
            "        9-03-26 15:21:53",
            transaction_line("9-24", "EMPLOYER, PAYROLL", "1,038.98", credit=True),
            transaction_line("9-04", "WALMART.COM", "241.28"),
        ))

        self.assertEqual(len(transactions), 3)
        self.assertEqual([transaction.amount for transaction in transactions], [500.00, 1038.98, -241.28])
        for transaction in transactions:
            self.assertIsInstance(transaction.amount, DollarAmount)
            self.assertEqual(transaction.date.year, 2026)
        self.assertEqual(transactions[0].description, "Deposit by internet From Savings XXXXXXX-123 9-03-26 15:21:53")
        self.assertEqual((transactions[1].date.month, transactions[1].date.day), (9, 24))
        self.assertEqual(transactions[2].location, Locations.WALMART)
        self.assertEqual(transactions[0].location, Locations.FREEDOM_BANK)
        self.assertEqual(transactions[0].category, Categories.NOT_INCLUDED)
        self.assertEqual(transactions[0].is_essential, IsEssential.NOT_INCLUDED)

    def test_ignores_balances_fees_and_check_image_captions(self):
        transactions = self.import_pages(
            statement(
                transaction_line("9-03", "MISC. DEBIT", "63.00"),
                "-- BALANCES --------------------------",
                "         9-03    2,525.74 |         9-16    1,679.08",
                "Total overdraft fees $0.00",
            ),
            "A STATEMENT OF YOUR ACCOUNT\n01-SEP-26 THRU 30-SEP-26\n"
            "-- BALANCES --------------------------\n9-03 2,525.74",
            "Images for Account DDA XXXXXXX\nPage 1\n09/03/2026 $63.00",
        )
        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0].amount, -63.00)
        self.assertEqual(transactions[0].description, "MISC. DEBIT")

    def test_preserves_wrapped_descriptions_and_repeated_page_headers(self):
        transactions = self.import_pages(
            statement(transaction_line("9-03", "CTLP*CANTEEN", "1.90")),
            statement(
                "       VENDING CHARLOTTE NC",
                transaction_line("9-10", "EMPLOYER, PAYROLL", "747.59", credit=True),
                "       ACH REFERENCE123",
                transaction_line("9-23", "DISCOVER,E-PAYMENT", "100.00"),
                "       DC PYMNTS DCIINTNET,260922",
            ),
        )
        self.assertEqual(len(transactions), 3)
        self.assertEqual(transactions[0].description, "CTLP*CANTEEN VENDING CHARLOTTE NC")
        self.assertEqual(transactions[0].location, Locations.VENDING_MACHINE)
        self.assertEqual(transactions[0].is_essential, IsEssential.NON_ESSENTIAL)
        self.assertEqual(transactions[1].description, "EMPLOYER, PAYROLL ACH REFERENCE123")
        self.assertEqual(transactions[2].amount, -100.00)
        self.assertEqual(transactions[2].description, "DISCOVER,E-PAYMENT DC PYMNTS DCIINTNET,260922")

    def test_preserves_separate_transactions_with_the_same_date_and_amount(self):
        row = transaction_line("9-03", "MISC. DEBIT", "63.00")
        transactions = self.import_pages(statement(row, row))
        self.assertEqual(len(transactions), 2)
        self.assertIsNot(transactions[0], transactions[1])

    def test_dates_follow_the_statement_year_across_new_year(self):
        transactions = self.import_pages(statement(
            transaction_line("12-31", "PURCHASE", "25.00"),
            transaction_line("1-02", "DEPOSIT", "500.00", credit=True),
            period="15-DEC-2026 THRU 14-JAN-2027",
        ))
        self.assertEqual((transactions[0].date.year, transactions[0].date.month), (2026, 12))
        self.assertEqual((transactions[1].date.year, transactions[1].date.month), (2027, 1))

    def test_incomplete_row_is_reported_without_consuming_the_next_row(self):
        with self.assertRaisesRegex(ValueError, "row 1"):
            self.import_pages(statement(
                " 9-03  MISSING AMOUNT",
                transaction_line("9-04", "WALMART", "2.81"),
            ))

    def test_invalid_transaction_date_is_reported(self):
        with self.assertRaises(ValueError):
            self.import_pages(statement(transaction_line("9-31", "PURCHASE", "2.81")))

    def test_date_outside_statement_period_is_reported(self):
        with self.assertRaisesRegex(ValueError, "outside the statement period"):
            self.import_pages(statement(transaction_line("8-31", "PURCHASE", "2.81")))

    def test_empty_or_unsupported_pdf_is_reported(self):
        for pages in ([], [""], ["Transactions Trans. Date Post Date Description Amount Category"]):
            with self.subTest(pages=pages), self.assertRaisesRegex(ValueError, "statement period"):
                self.import_pages(*pages)

    def test_missing_transaction_section_is_reported(self):
        with self.assertRaisesRegex(ValueError, "ITEMIZED TRANSACTIONS"):
            self.import_pages("01-SEP-26 THRU 30-SEP-26\n-- BALANCES --\n9-03 2,525.74")

    def test_missing_amount_columns_are_reported(self):
        with self.assertRaisesRegex(ValueError, "debit/credit columns"):
            self.import_pages("01-SEP-26 THRU 30-SEP-26\n-- ITEMIZED TRANSACTIONS --\n")

    def test_statement_with_no_activity_returns_no_transactions(self):
        self.assertEqual(self.import_pages(statement("-- BALANCES --")), [])

    def test_missing_pdf_error_is_preserved(self):
        with patch.object(final_review_page.PdfManager, "open", side_effect=FileNotFoundError):
            with self.assertRaises(FileNotFoundError):
                final_review_page._import_checking_account_transactions()


if __name__ == "__main__":
    unittest.main()
