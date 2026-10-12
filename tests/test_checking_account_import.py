import unittest
from unittest.mock import patch

from classes.general.dollar_amount_class import DollarAmount
from classes.pages.child_pages.expense_reveiw_pages import final_review_page
from enums.files_enum import Files
from enums.finances.categories_enum import Categories
from enums.finances.credit_card.credit_card_categories_enum import CreditCardCategories
from enums.finances.credit_card.credit_card_headers_enum import CreditCardHeaders
from enums.finances.descriptions.car_descriptions_enum import CarDescriptions
from enums.finances.descriptions.income_descriptions_enum import IncomeDescriptions
from enums.finances.descriptions.credit_card_descriptions_enum import CreditCardDescriptions
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
            self.assertIs(transaction.source, Locations.FREEDOM_BANK)
        self.assertEqual(transactions[0].purchase_title, "Deposit by internet From Savings XXXXXXX-123 9-03-26 15:21:53")
        self.assertEqual([transaction.description for transaction in transactions], [None, IncomeDescriptions.PAYCHECK, None])
        self.assertEqual((transactions[1].date.month, transactions[1].date.day), (9, 24))
        self.assertEqual(transactions[2].location, Locations.WALMART)
        self.assertEqual(transactions[0].location, Locations.FREEDOM_BANK)
        self.assertIsNone(transactions[0].category)
        self.assertFalse(transactions[0].is_field_locked("category"))
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
        self.assertEqual(transactions[0].purchase_title, "MISC. DEBIT")
        self.assertIsNone(transactions[0].description)

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
        self.assertEqual(transactions[0].purchase_title, "CTLP*CANTEEN VENDING CHARLOTTE NC")
        self.assertEqual(transactions[0].location, Locations.VENDING_MACHINE)
        self.assertEqual(transactions[0].is_essential, IsEssential.NON_ESSENTIAL)
        self.assertEqual(transactions[1].purchase_title, "EMPLOYER, PAYROLL ACH REFERENCE123")
        self.assertEqual(transactions[2].amount, -100.00)
        self.assertEqual(transactions[2].purchase_title, "DISCOVER,E-PAYMENT DC PYMNTS DCIINTNET,260922")
        self.assertEqual(transactions[2].location, Locations.DISCOVER)
        self.assertIs(transactions[2].category, Categories.CREDIT_CARD)
        self.assertIs(transactions[2].description, CreditCardDescriptions.PAYMENT)
        self.assertEqual(transactions[2].is_essential, IsEssential.NOT_INCLUDED)

    def test_both_statement_sides_of_a_credit_card_repayment_are_excluded(self):
        checking, = self.import_pages(statement(
            transaction_line("9-03", "DISCOVER,E-PAYMENT", "624.95"),
        ))
        credit_row = {
            CreditCardHeaders.TRANS_DATE: "09/03/2026",
            CreditCardHeaders.DESCRIPTION: "INTERNET PAYMENT - THANK YOU",
            CreditCardHeaders.AMOUNT: "-624.95",
            CreditCardHeaders.CATEGORY: CreditCardCategories.PAYMENTS_AND_CREDITS,
        }
        with patch.object(final_review_page.DiscoverStatementManager, "open", side_effect=[[credit_row], []]):
            card, = final_review_page._import_credit_card_transactions()
        self.assertEqual(checking.amount, -624.95)
        self.assertEqual(card.amount, 624.95)
        for transaction in (checking, card):
            self.assertIs(transaction.is_essential, IsEssential.NOT_INCLUDED)
        for transaction in (checking, card):
            self.assertIs(transaction.category, Categories.CREDIT_CARD)
            self.assertIs(transaction.description, CreditCardDescriptions.PAYMENT)
            self.assertTrue(transaction.is_field_locked("category"))
            self.assertTrue(transaction.is_field_locked("description"))
            self.assertTrue(transaction.excluded_from_totals)
        self.assertIs(checking.location, Locations.DISCOVER)
        self.assertIs(checking.source, Locations.FREEDOM_BANK)
        self.assertIs(card.source, Locations.DISCOVER)
        self.assertIs(card.location, Locations.DISCOVER)
        for transaction in (checking, card):
            self.assertTrue(transaction.is_field_locked("location"))
            self.assertTrue(transaction.is_field_locked("is_essential"))

    def test_source_is_only_a_location_fallback_for_internal_movements(self):
        for description, source, expected_location in (
            ("Transfer between own accounts", Locations.FREEDOM_BANK, Locations.FREEDOM_BANK),
            ("INTERNET PAYMENT - THANK YOU", Locations.DISCOVER, Locations.DISCOVER),
            ("DISCOVER,E-PAYMENT", Locations.FREEDOM_BANK, Locations.DISCOVER),
            ("WALMART.COM", Locations.DISCOVER, Locations.WALMART),
            ("UNKNOWN STORE", Locations.DISCOVER, None),
            ("EMPLOYER PAYROLL", Locations.FREEDOM_BANK, None),
        ):
            with self.subTest(description=description):
                row = {CreditCardHeaders.TRANS_DATE: "09/03/2026",
                       CreditCardHeaders.DESCRIPTION: description,
                       CreditCardHeaders.AMOUNT: "-50.00",
                       CreditCardHeaders.CATEGORY: CreditCardCategories.PAYMENTS_AND_CREDITS}
                transaction = final_review_page._create_financial_transaction_object(row, source=source)
                self.assertIs(transaction.source, source)
                self.assertIs(transaction.location, expected_location)
                with self.assertRaises(AttributeError):
                    transaction.source = Locations.AMAZON

    def test_both_credit_card_pdfs_preserve_their_document_source(self):
        rows = [{CreditCardHeaders.TRANS_DATE: day,
                 CreditCardHeaders.DESCRIPTION: "WALMART.COM",
                 CreditCardHeaders.AMOUNT: "5.00"} for day in ("09/03/2026", "09/04/2026")]
        with patch.object(final_review_page.DiscoverStatementManager, "open", side_effect=[[rows[0]], [rows[1]]]):
            transactions = final_review_page._import_credit_card_transactions()
        self.assertEqual(len(transactions), 2)
        self.assertTrue(all(transaction.source is Locations.DISCOVER for transaction in transactions))
        self.assertTrue(all(transaction.location is Locations.WALMART for transaction in transactions))

    def test_only_payroll_defaults_to_income_among_checking_credits(self):
        transactions = self.import_pages(statement(
            transaction_line("9-03", "Deposit by internet From Savings", "500.00", credit=True),
            transaction_line("9-04", "EMPLOYER, PAYROLL", "1000.00", credit=True),
            transaction_line("9-05", "WALMART REFUND", "5.00", credit=True),
            transaction_line("9-06", "FIRST SECURITY BANK REFUND", "5.00", credit=True),
            transaction_line("9-07", "PURCHASE", "5.00"),
        ))
        for transaction in transactions:
            self.assertIs(transaction.source, Locations.FREEDOM_BANK)
        self.assertIs(transactions[1].category, Categories.INCOME)
        self.assertTrue(transactions[1].is_field_locked("category"))
        self.assertIs(transactions[1].is_essential, IsEssential.ESSENTIAL)
        self.assertTrue(transactions[1].is_field_locked("is_essential"))
        for index in (0, 2, 3, 4):
            self.assertIsNone(transactions[index].category)
            self.assertFalse(transactions[index].is_field_locked("category"))
        self.assertIs(transactions[0].is_essential, IsEssential.NOT_INCLUDED)
        self.assertTrue(transactions[0].is_field_locked("is_essential"))
        self.assertIs(transactions[1].description, IncomeDescriptions.PAYCHECK)
        self.assertTrue(transactions[1].is_field_locked("description"))
        self.assertIsNone(transactions[2].description)
        self.assertIsNone(transactions[3].description)
        self.assertIsNone(transactions[4].category)

    def test_card_cashback_and_payments_are_credit_card_and_refunds_stay_unclassified(self):
        descriptions = ("CASHBACK BONUS REDEMPTION PYMT/STMT CRDT", "CULVERS REFUND",
                        "INTERNET PAYMENT - THANK YOU", "WALMART.COM", "ZERO AMOUNT")
        categories = (CreditCardCategories.AWARDS_AND_REBATE_CREDITS, None,
                      CreditCardCategories.PAYMENTS_AND_CREDITS, None, None)
        amounts = ("-5.77", "-5.00", "-100.00", "5.00", "0.00")
        rows = [{CreditCardHeaders.TRANS_DATE: "09/03/2026", CreditCardHeaders.DESCRIPTION: description,
                 CreditCardHeaders.CATEGORY: category, CreditCardHeaders.AMOUNT: amount}
                for description, category, amount in zip(descriptions, categories, amounts)]
        with patch.object(final_review_page.DiscoverStatementManager, "open", side_effect=[rows, []]):
            transactions = final_review_page._import_credit_card_transactions()
        self.assertEqual([transaction.amount for transaction in transactions], [5.77, 5, 100, -5, 0])
        self.assertIs(transactions[0].category, Categories.CREDIT_CARD)
        self.assertIs(transactions[0].description, CreditCardDescriptions.CASHBACK)
        self.assertIs(transactions[0].is_essential, IsEssential.ESSENTIAL)
        self.assertTrue(transactions[0].is_field_locked("category"))
        self.assertIsNone(transactions[1].category)
        self.assertFalse(transactions[1].is_field_locked("category"))
        self.assertIs(transactions[2].category, Categories.CREDIT_CARD)
        self.assertIs(transactions[2].description, CreditCardDescriptions.PAYMENT)
        self.assertTrue(transactions[2].is_field_locked("category"))
        self.assertIsNone(transactions[1].description)
        self.assertIs(transactions[2].is_essential, IsEssential.NOT_INCLUDED)
        self.assertIsNone(transactions[3].category)
        self.assertIsNone(transactions[4].category)

    def test_cashback_bonus_redemptions_default_to_locked_discover_location(self):
        for description in ("CASHBACK BONUS REDEMPTION PYMT/STMT CRDT",
                            "  cashback  bonus\tredemption  ", "Cash Back Bonus Redemption"):
            with self.subTest(description=description):
                row = {CreditCardHeaders.TRANS_DATE: "09/03/2026",
                       CreditCardHeaders.DESCRIPTION: description,
                       CreditCardHeaders.AMOUNT: "-5.77",
                       CreditCardHeaders.CATEGORY: CreditCardCategories.AWARDS_AND_REBATE_CREDITS}
                with patch.object(final_review_page.DiscoverStatementManager, "open", side_effect=[[row], []]):
                    transaction, = final_review_page._import_credit_card_transactions()
                self.assertIs(transaction.location, Locations.DISCOVER)
                self.assertIs(transaction.source, Locations.DISCOVER)
                self.assertTrue(transaction.is_field_locked("location"))
                self.assertEqual(transaction.amount, 5.77)
                self.assertIs(transaction.category, Categories.CREDIT_CARD)
                self.assertIs(transaction.description, CreditCardDescriptions.CASHBACK)
                self.assertIs(transaction.is_essential, IsEssential.ESSENTIAL)
                for field in ("location", "category", "description", "is_essential"):
                    self.assertTrue(transaction.is_field_locked(field))
                self.assertFalse(transaction.excluded_from_totals)
                self.assertIsNot(transaction.is_essential, IsEssential.NOT_INCLUDED)

    def test_card_cashback_uses_credit_card_defaults_but_cash_back_withdrawal_does_not(self):
        row = {CreditCardHeaders.TRANS_DATE: "09/03/2026", CreditCardHeaders.AMOUNT: "5.00",
               CreditCardHeaders.DESCRIPTION: "CASH BACK", CreditCardHeaders.CATEGORY: None}
        card = final_review_page._create_financial_transaction_object(row, source=Locations.DISCOVER)
        self.assertIs(card.category, Categories.CREDIT_CARD)
        self.assertIs(card.location, Locations.DISCOVER)
        self.assertIs(card.description, CreditCardDescriptions.CASHBACK)
        self.assertIs(card.is_essential, IsEssential.ESSENTIAL)
        self.assertTrue(card.is_field_locked("location"))
        withdrawal = final_review_page._create_financial_transaction_object(row, source=Locations.FREEDOM_BANK)
        self.assertIsNone(withdrawal.category)
        self.assertIsNone(withdrawal.description)

    def test_savings_deposit_defaults_tolerate_case_and_extra_whitespace(self):
        row = {
            CreditCardHeaders.TRANS_DATE: "09/03/2026",
            CreditCardHeaders.DESCRIPTION: "  DEPOSIT  by\tINTERNET\n From  Savings XXXXXXX-123",
            CreditCardHeaders.AMOUNT: "500.00",
        }
        transaction = final_review_page._create_financial_transaction_object(row)
        self.assertIs(transaction.location, Locations.FREEDOM_BANK)
        self.assertIs(transaction.is_essential, IsEssential.NOT_INCLUDED)

    def test_internal_account_movements_and_other_card_payment_wordings_are_excluded(self):
        for description, category in (
            ("Transfer from savings account", None),
            ("XFER TO MY CHECKING", None),
            ("Internal transfer", None),
            ("Transfer between own accounts", None),
            ("CHASE CREDIT CARD AUTOPAY", None),
            ("AMEX EPAYMENT", None),
            ("AUTOMATIC PAYMENT - THANK YOU", CreditCardCategories.PAYMENTS_AND_CREDITS),
        ):
            with self.subTest(description=description):
                row = {CreditCardHeaders.TRANS_DATE: "09/03/2026",
                       CreditCardHeaders.DESCRIPTION: description,
                       CreditCardHeaders.AMOUNT: "-50.00", CreditCardHeaders.CATEGORY: category}
                transaction = final_review_page._create_financial_transaction_object(row)
                self.assertIs(transaction.is_essential, IsEssential.NOT_INCLUDED)

    def test_external_credits_and_ordinary_payments_remain_included(self):
        for description, category, amount in (
            ("WALMART REFUND", CreditCardCategories.PAYMENTS_AND_CREDITS, 10),
            ("DISCOVER PAYMENT REVERSAL", CreditCardCategories.PAYMENTS_AND_CREDITS, -10),
            ("CASHBACK BONUS REDEMPTION PYMT/STMT CRDT", CreditCardCategories.AWARDS_AND_REBATE_CREDITS, 5.77),
            ("STORE CREDIT", CreditCardCategories.PAYMENTS_AND_CREDITS, 10),
            ("EMPLOYER PAYROLL", None, 1000),
            ("UTILITY ACH PAYMENT", None, -50),
            ("FIRST SECURITY BANK CAR PAYMENT", None, -200),
            ("TRANSFER TO A FRIEND", None, -25),
        ):
            with self.subTest(description=description):
                row = {CreditCardHeaders.TRANS_DATE: "09/03/2026",
                       CreditCardHeaders.DESCRIPTION: description,
                       CreditCardHeaders.AMOUNT: str(amount), CreditCardHeaders.CATEGORY: category}
                transaction = final_review_page._create_financial_transaction_object(row)
                self.assertIsNot(transaction.is_essential, IsEssential.NOT_INCLUDED)

    def test_car_payment_description_is_autocompleted_instead_of_using_the_purchase_title(self):
        transactions = self.import_pages(statement(
            transaction_line("9-03", "FIRST SECURITY BANK", "200.00"),
        ))
        self.assertEqual(transactions[0].purchase_title, "FIRST SECURITY BANK")
        self.assertIs(transactions[0].description, CarDescriptions.CAR_PAYMENT)
        self.assertTrue(transactions[0].description_is_autocompleted)

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
