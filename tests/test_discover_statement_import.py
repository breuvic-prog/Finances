import tempfile
import tkinter as tk
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, call, patch

from classes.managers.discover_statement_manager import DiscoverStatementManager
from classes.pages.child_pages.expense_reveiw_pages import credit_card_expenses_page_class as upload_page
from classes.pages.child_pages.expense_reveiw_pages import checking_account_expenses_page_class as bank_upload_page
from classes.pages.child_pages.expense_reveiw_pages import final_review_page
from enums.files_enum import Files
from enums.folders_enum import Folders
from enums.finances.categories_enum import Categories
from enums.finances.credit_card.credit_card_headers_enum import CreditCardHeaders as H
from enums.finances.descriptions.credit_card_descriptions_enum import CreditCardDescriptions
from enums.finances.is_essential_enum import IsEssential
from enums.finances.locations_enum import Locations
from enums.paths_enum import Paths


EXAMPLE = Path(__file__).resolve().parents[1] / "assets/pdfs/Discover-AccountActivity-20261003.pdf"


def activity(*lines):
    return "\n".join(["Account header", "Transactions", "Trans.", "Date", "Post", "Date",
                      "Description", "Amount", "Category", *lines])


class DiscoverStatementImportTests(unittest.TestCase):
    @unittest.skipUnless(EXAMPLE.is_file(), "User's example PDF is not present")
    def test_example_preserves_all_rows_signs_wrapped_fields_and_duplicate_purchases(self):
        rows = DiscoverStatementManager.open(name=str(EXAMPLE), path="")
        self.assertEqual(len(rows), 64)
        self.assertEqual(sum(Decimal(row[H.AMOUNT]) for row in rows), Decimal("2450.03"))
        self.assertEqual(sum(row[H.TRANS_DATE] == "09/27/2026" and row[H.AMOUNT] == "1.85"
                             for row in rows), 5)
        cashback, = [row for row in rows if "CASHBACK" in row[H.DESCRIPTION]]
        self.assertEqual(cashback[H.DESCRIPTION], "CASHBACK BONUS REDEMPTION PYMT/STMT CRDT")
        self.assertEqual(cashback[H.CATEGORY], "Awards and Rebate Credits")
        self.assertEqual(cashback[H.AMOUNT], "-5.77")
        large, = [row for row in rows if "NEWEGG" in row[H.DESCRIPTION]]
        self.assertEqual(large[H.AMOUNT], "1676.21")
        self.assertEqual(large[H.CATEGORY], "Merchandise")
        documents = [row for row in rows if "PARCHMENT" in row[H.DESCRIPTION]]
        self.assertEqual(len(documents), 2)
        self.assertTrue(any(row[H.DESCRIPTION].endswith("236499825") for row in documents))
        self.assertEqual(rows[-1][H.TRANS_DATE], "09/03/2026")
        self.assertEqual(rows[-1][H.POST_DATE], "09/04/2026")

    def test_wrapped_transaction_continues_across_pages_and_repeated_headers(self):
        rows = DiscoverStatementManager.parse([
            activity("09/03/26", "09/04/26", "LONG STORE NAME"),
            activity("SECOND DESCRIPTION LINE", "$ 1,234.56 Merchandise", "09/05/2026", "09/06/2026",
                     "CASHBACK BONUS REDEMPTION PYMT/STMT", "CRDT", "$ -5.77", "Awards and Rebate",
                     "Credits", "Statement Balance is the total balance", "$ 9,999.99"),
        ])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][H.DESCRIPTION], "LONG STORE NAME SECOND DESCRIPTION LINE")
        self.assertEqual(rows[0][H.AMOUNT], "1234.56")
        self.assertEqual(rows[1][H.CATEGORY], "Awards and Rebate Credits")
        self.assertEqual(rows[1][H.TRANS_DATE], "09/05/2026")

    def test_invalid_or_incomplete_rows_fail_instead_of_importing_partial_activity(self):
        for lines in (
            ("09/03/26", "PURCHASE", "$ 1.00", "Merchandise"),
            ("09/03/26", "09/04/26", "$ 1.00", "Merchandise"),
            ("09/03/26", "09/04/26", "PURCHASE", "09/05/26", "09/06/26", "NEXT", "$ 2.00", "Merchandise"),
            ("09/03/26", "09/04/26", "PURCHASE", "$ 1.0", "$ 2.00", "Merchandise"),
            ("09/03/26", "09/04/26", "PURCHASE", "$ 1.00"),
            ("09/31/26", "10/01/26", "PURCHASE", "$ 1.00", "Merchandise"),
        ):
            with self.subTest(lines=lines), self.assertRaises(ValueError):
                DiscoverStatementManager.parse([activity(*lines)])

    def test_missing_or_scanned_transaction_table_is_reported(self):
        for pages in ([], [""], ["Discover summary without a transaction table"]):
            with self.subTest(pages=pages), self.assertRaisesRegex(ValueError, "Transactions table"):
                DiscoverStatementManager.parse(pages)

    def test_empty_activity_is_supported(self):
        self.assertEqual(DiscoverStatementManager.parse([activity("No transactions this period")]), [])

    def test_corrupt_pdf_is_reported_as_an_upload_validation_error(self):
        with tempfile.TemporaryDirectory(prefix="discover-pdf-", dir=Path(__file__).parent) as workspace:
            invalid = Path(workspace) / "invalid.pdf"
            invalid.write_bytes(b"not a PDF")
            with self.assertRaisesRegex(ValueError, "valid PDF"):
                DiscoverStatementManager.open(str(invalid), "")

    def test_both_pdf_imports_keep_discover_source_negative_expenses_and_payment_defaults(self):
        pages = [activity("09/03/26", "09/04/26", "WALMART.COM", "$ 10.00", "Merchandise"),
                 activity("09/04/26", "09/04/26", "INTERNET PAYMENT - THANK YOU", "$ -100.00",
                          "Payments and Credits", "09/05/26", "09/05/26",
                          "CASHBACK BONUS REDEMPTION PYMT/STMT CRDT", "$ -5.77", "Awards and Rebate Credits")]
        with patch.object(DiscoverStatementManager, "open", side_effect=[DiscoverStatementManager.parse([p])
                                                                       for p in pages]) as reader:
            transactions = final_review_page._import_credit_card_transactions()
        self.assertEqual(reader.call_args_list, [
            call(name=Files.CREDIT_CARD_PREVIOUS_MONTH_STATEMENT_PDF, path=Paths.ASSETS_PDFS),
            call(name=Files.CREDIT_CARD_PREVIOUS_PREVIOUS_MONTH_STATEMENT_PDF, path=Paths.ASSETS_PDFS),
        ])
        self.assertEqual([transaction.amount for transaction in transactions], [-10, 100, 5.77])
        self.assertTrue(all(transaction.source is Locations.DISCOVER for transaction in transactions))
        self.assertIs(transactions[0].location, Locations.WALMART)
        self.assertIs(transactions[1].category, Categories.CREDIT_CARD)
        self.assertIs(transactions[1].description, CreditCardDescriptions.PAYMENT)
        self.assertIs(transactions[1].is_essential, IsEssential.NOT_INCLUDED)
        self.assertIs(transactions[2].location, Locations.DISCOVER)
        self.assertIs(transactions[2].description, CreditCardDescriptions.CASHBACK)
        self.assertIs(transactions[2].is_essential, IsEssential.ESSENTIAL)


class DiscoverStatementUploadTests(unittest.TestCase):
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
        workspace = self.enterContext(tempfile.TemporaryDirectory(prefix="discover-upload-", dir=Path(__file__).parent))
        self.destination = Path(workspace)
        self.next_page = Mock()
        self.page = upload_page.CreditCardExpensesPage(self.root, self.next_page)
        self.addCleanup(self.page._root.destroy)
        self.page._previous_month_path = str(self.destination / "latest.pdf")
        self.page._previous_previous_month_path = str(self.destination / "previous.pdf")
        self.real_join = upload_page.PathManager.join
        self.join = self.enterContext(patch.object(upload_page.PathManager, "join", return_value=str(self.destination)))
        self.reader = self.enterContext(patch.object(DiscoverStatementManager, "open", return_value=[]))
        self.real_copy = upload_page.FileManager.copy
        self.copy = self.enterContext(patch.object(upload_page.FileManager, "copy"))
        self.confirm = self.enterContext(patch.object(upload_page.messagebox, "askyesno", return_value=False))
        self.error = self.enterContext(patch.object(upload_page.messagebox, "showerror"))

    def test_both_upload_controls_choose_pdfs(self):
        with patch.object(upload_page.filedialog, "askopenfilename", return_value="selected.pdf") as picker:
            self.page._previous_month_file_button.invoke()
            self.page._previous_previous_month_file_button.invoke()
        self.assertEqual(picker.call_count, 2)
        self.assertEqual(picker.call_args.kwargs["filetypes"], [("PDF Files", "*.pdf")])
        self.assertEqual(self.page._previous_month_path, "selected.pdf")
        self.assertEqual(self.page._previous_previous_month_path, "selected.pdf")

    def test_missing_upload_does_not_validate_copy_or_advance(self):
        self.page._previous_previous_month_path = None
        self.page._finalize()
        self.reader.assert_not_called()
        self.copy.assert_not_called()
        self.next_page.assert_not_called()

    def test_invalid_second_pdf_does_not_replace_the_first_or_advance(self):
        self.reader.side_effect = [[], ValueError("Unsupported statement")]
        self.page._finalize()
        self.error.assert_called_once()
        self.copy.assert_not_called()
        self.confirm.assert_not_called()
        self.next_page.assert_not_called()

    def test_valid_new_pdfs_copy_to_pdf_storage_after_both_are_validated(self):
        self.page._finalize()
        self.assertEqual(self.reader.call_args_list, [
            call(name=self.page._previous_month_path, path=""),
            call(name=self.page._previous_previous_month_path, path=""),
        ])
        self.assertEqual(self.copy.call_args_list, [
            call(source_path=self.page._previous_month_path, destination_path=str(self.destination),
                 destination_name=Files.CREDIT_CARD_PREVIOUS_MONTH_STATEMENT_PDF),
            call(source_path=self.page._previous_previous_month_path, destination_path=str(self.destination),
                 destination_name=Files.CREDIT_CARD_PREVIOUS_PREVIOUS_MONTH_STATEMENT_PDF),
        ])
        self.confirm.assert_not_called()
        self.next_page.assert_called_once_with()

    def test_declining_import_replacement_keeps_saved_pdfs(self):
        existing = self.destination / Files.CREDIT_CARD_PREVIOUS_MONTH_STATEMENT_PDF
        existing.write_bytes(b"saved statement")
        self.page._finalize()
        self.confirm.assert_called_once()
        self.assertEqual(self.confirm.call_args.kwargs["default"], "no")
        self.assertEqual(existing.read_bytes(), b"saved statement")
        self.copy.assert_not_called()
        self.next_page.assert_not_called()
        self.page._review_files.cleanup()
        self.assertEqual(existing.read_bytes(), b"saved statement")

    def test_accepting_import_replacement_copies_both_validated_pdfs(self):
        (self.destination / Files.CREDIT_CARD_PREVIOUS_PREVIOUS_MONTH_STATEMENT_PDF).write_bytes(b"saved")
        self.confirm.return_value = True
        self.page._finalize()
        self.confirm.assert_called_once()
        self.assertEqual(self.copy.call_count, 2)
        self.next_page.assert_called_once_with()

    def test_copied_discover_pdfs_are_registered_for_cleanup_without_deleting_original_uploads(self):
        for path in (self.page._previous_month_path, self.page._previous_previous_month_path):
            Path(path).write_bytes(b"original PDF")
        unrelated = self.destination / "unrelated.pdf"
        unrelated.write_bytes(b"keep")
        self.join.side_effect = lambda *parts: (str(self.destination) if parts == (Folders.ASSETS, Folders.PDFS)
                                               else self.real_join(*parts))
        self.copy.side_effect = self.real_copy
        self.page._finalize()
        saved_paths = [self.destination / name for name in (
            Files.CREDIT_CARD_PREVIOUS_MONTH_STATEMENT_PDF,
            Files.CREDIT_CARD_PREVIOUS_PREVIOUS_MONTH_STATEMENT_PDF)]
        self.assertTrue(all(path.read_bytes() == b"original PDF" for path in saved_paths))
        self.page._review_files.cleanup()
        self.assertTrue(all(not path.exists() for path in saved_paths))
        self.assertEqual(Path(self.page._previous_month_path).read_bytes(), b"original PDF")
        self.assertEqual(Path(self.page._previous_previous_month_path).read_bytes(), b"original PDF")
        self.assertEqual(unrelated.read_bytes(), b"keep")

    def test_copied_bank_statement_is_registered_for_cleanup_without_deleting_original_upload(self):
        checking = bank_upload_page.CheckingAccountExpensesPage(self.root, Mock())
        self.addCleanup(checking._root.destroy)
        original = self.destination / "original-bank.pdf"
        original.write_bytes(b"original bank statement")
        checking._previous_month_path = str(original)
        self.join.side_effect = lambda *parts: (str(self.destination) if parts == (Folders.ASSETS, Folders.PDFS)
                                               else self.real_join(*parts))
        self.copy.side_effect = self.real_copy
        checking._finalize()
        saved = self.destination / Files.CHECKING_ACCOUNT_PREVIOUS_MONTH_STATEMENT_PDF
        self.assertEqual(saved.read_bytes(), b"original bank statement")
        checking._review_files.cleanup()
        self.assertFalse(saved.exists())
        self.assertEqual(original.read_bytes(), b"original bank statement")


if __name__ == "__main__":
    unittest.main()
