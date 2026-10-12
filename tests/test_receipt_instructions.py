import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from zipfile import ZipFile

from classes.financial_transaction_class import FinancialTransaction
from classes.general.date_class import Date
from classes.general.dollar_amount_class import DollarAmount
from classes.managers.receipt_instruction_manager import ReceiptInstructionManager
from classes.managers.review_files_manager import ReviewFilesManager
from classes.pages.child_pages.expense_reveiw_pages import final_review_page, reciepts_input_page
from enums.files_enum import Files
from enums.finances.locations_enum import Locations
from enums.paths_enum import Paths


def transaction(location=None, title=None, amount=-10):
    return FinancialTransaction(Date(29, 9, 2026), DollarAmount(amount), location=location,
                                purchase_title=title)


class ReceiptInstructionTests(unittest.TestCase):
    def setUp(self):
        tests_directory = Path(__file__).resolve().parent
        self.workspace = Path(self.enterContext(tempfile.TemporaryDirectory(
            prefix="receipt-instructions-", dir=tests_directory)))
        self.template = (Path(Paths.ASSETS_TXTS) / Files.RECEIPT_INSTRUCTIONS_TXT).read_text(encoding="utf-8")

    def test_no_purchases_or_only_amazon_refunds_omit_amazon_entirely(self):
        for transactions in ([], [transaction(Locations.WALMART)],
                             [transaction(Locations.AMAZON, amount=10)],
                             [transaction(title="AMZN Mktp refund", amount=10)],
                             [transaction(Locations.AMAZON, amount=0)]):
            with self.subTest(transactions=transactions):
                text = ReceiptInstructionManager.render(self.template, transactions)
                self.assertNotIn("amazon", text.casefold())
                self.assertNotIn("[[", text)
                self.assertIn("Apple receipts", text)
                self.assertIn("one final ZIP", text)

    def test_amazon_purchases_include_the_receipt_stage_without_template_markers(self):
        for purchase in (transaction(Locations.AMAZON), transaction(title="AMAZON MKTPL*ORDER"),
                         transaction(title="AMZN Mktp US*ORDER"), transaction(title="amazon.com")):
            with self.subTest(title=purchase.purchase_title, location=purchase.location):
                text = ReceiptInstructionManager.render(self.template, [purchase])
                self.assertIn("Amazon purchase receipts one by one", text)
                self.assertNotIn("[[", text)
                self.assertLess(text.index("Apple receipts"), text.index("Amazon purchase receipts"))
                self.assertLess(text.index("Amazon purchase receipts"), text.index("one final ZIP"))

    def test_downloaded_zip_uses_current_imports_and_does_not_change_the_template(self):
        page = reciepts_input_page.ReceiptsInputPage.__new__(reciepts_input_page.ReceiptsInputPage)
        page._review_files = ReviewFilesManager()
        original = (Path(Paths.ASSETS_TXTS) / Files.RECEIPT_INSTRUCTIONS_TXT).read_bytes()
        paths = type("TestPaths", (), {
            "DOWNLOADS": str(self.workspace), "ASSETS_JSONS": Paths.ASSETS_JSONS,
        })
        for purchase, included in ((transaction(Locations.AMAZON), True),
                                   (transaction(Locations.WALMART), False)):
            with self.subTest(included=included), patch.object(reciepts_input_page, "Paths", paths), \
                    patch.object(final_review_page, "_import_transactions", return_value=[purchase]) as importer:
                page._download_instructions()
                importer.assert_called_once_with()
                with ZipFile(page._instructions_zip_path) as archive:
                    self.assertIn(str(Files.RECEIPT_EXAMPLE_JSON), archive.namelist())
                    text = archive.read(str(Files.RECEIPT_INSTRUCTIONS_TXT)).decode("utf-8")
                    self.assertEqual("amazon" in text.casefold(), included)
                    self.assertNotIn("[[", text)
                    self.assertIn("Apple receipts", text)
                    self.assertIn("one final ZIP", text)
                self.assertEqual((Path(Paths.ASSETS_TXTS) / Files.RECEIPT_INSTRUCTIONS_TXT).read_bytes(), original)
        page._review_files.cleanup()
        self.assertFalse((self.workspace / "instructions.zip").exists())
        self.assertEqual((Path(Paths.ASSETS_TXTS) / Files.RECEIPT_INSTRUCTIONS_TXT).read_bytes(), original)

    def test_activating_page_automatically_generates_zip_after_statement_imports(self):
        page = reciepts_input_page.ReceiptsInputPage.__new__(reciepts_input_page.ReceiptsInputPage)
        page._review_files = ReviewFilesManager()
        page._root = Mock()
        page._instructions_status = Mock()
        page._instructions_zip_path = "Downloads/instructions.zip"
        with patch.object(page, "_download_instructions") as download:
            page.activate()
        page._root.pack.assert_called_once_with(fill="both", expand=True)
        download.assert_called_once_with()
        self.assertIn("ready", page._instructions_status.configure.call_args.kwargs["text"])

    def test_failed_automatic_generation_shows_retry_status_and_keeps_previous_zip(self):
        page = reciepts_input_page.ReceiptsInputPage.__new__(reciepts_input_page.ReceiptsInputPage)
        page._review_files = ReviewFilesManager()
        page._root = Mock()
        page._instructions_status = Mock()
        original = b"previous instructions"
        archive = self.workspace / "instructions.zip"
        archive.write_bytes(original)
        instructions_folder = self.workspace / "instructions"
        instructions_folder.mkdir()
        existing = instructions_folder / "keep.txt"
        existing.write_text("Keep this folder")
        paths = type("TestPaths", (), {"DOWNLOADS": str(self.workspace), "ASSETS_JSONS": Paths.ASSETS_JSONS})
        with patch.object(reciepts_input_page, "Paths", paths), \
                patch.object(reciepts_input_page.ReceiptInstructionManager, "create", side_effect=OSError("Cannot read statements")):
            page.activate()
        self.assertEqual(archive.read_bytes(), original)
        self.assertEqual(existing.read_text(), "Keep this folder")
        self.assertEqual({entry.name for entry in self.workspace.iterdir()}, {"instructions", "instructions.zip"})
        self.assertIn("Regenerate", page._instructions_status.configure.call_args.kwargs["text"])
        self.assertEqual(page._instructions_status.configure.call_args.kwargs["fg"], "#B91C1C")


if __name__ == "__main__":
    unittest.main()
