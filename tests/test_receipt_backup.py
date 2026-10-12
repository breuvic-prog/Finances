import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from classes.managers.receipt_backup_manager import ReceiptBackupManager
from enums.files_enum import Files


class ReceiptBackupTests(unittest.TestCase):
    def setUp(self):
        tests_directory = Path(__file__).resolve().parent
        temporary_directory = tempfile.TemporaryDirectory(prefix="receipt-backup-", dir=tests_directory)
        self.workspace = Path(temporary_directory.name).resolve()
        if self.workspace.parent != tests_directory:
            raise RuntimeError("Unexpected temporary directory location.")
        self.addCleanup(temporary_directory.cleanup)
        self.source = self.workspace / "receipts"
        self.source.mkdir()
        self.statements = self.workspace / "statements"
        self.statements.mkdir()
        self.statement_contents = {name: f"uploaded {name}".encode() for name in (
            Files.CREDIT_CARD_PREVIOUS_MONTH_STATEMENT_PDF,
            Files.CREDIT_CARD_PREVIOUS_PREVIOUS_MONTH_STATEMENT_PDF,
            Files.CHECKING_ACCOUNT_PREVIOUS_MONTH_STATEMENT_PDF)}
        for name, content in self.statement_contents.items():
            (self.statements / name).write_bytes(content)
        self.drive = self.workspace / "flash-drive"
        self.drive.mkdir()
        self.drive_lookup = self.enterContext(patch.object(ReceiptBackupManager, "_find_drive",
                                                         return_value=self.drive))

    def test_copies_only_the_review_month_and_year_and_keeps_all_originals(self):
        matching = {"Culver's_9-1-2026.json": b'{"receipt": "one"}',
                    "Walmart_09-30-2026_11-06-06.JSON": b'{"receipt": "two"}',
                    "Apple_9-5-2026_00-00-00_2.json": b'{"receipt": "three"}'}
        excluded = {"Walmart_8-31-2026.json": b"previous month",
                    "Walmart_10-1-2026.json": b"current month",
                    "Walmart_9-1-2025.json": b"previous year",
                    "Walmart_9-1-2027.json": b"next year",
                    "Walmart_9-31-2026.json": b"invalid date",
                    "Walmart receipt.json": b"undated",
                    "Walmart_9-1-2026.png": b"image bytes"}
        originals = matching | excluded
        for name, content in originals.items():
            (self.source / name).write_bytes(content)
        (self.source / "subfolder").mkdir()
        destination = ReceiptBackupManager.copy_receipts(self.source, date(2026, 10, 3))
        self.assertEqual(destination, self.drive / "My Stuff" / "Documents" / "Finances"
                         / "2026" / "September" / "Supporting Documents")
        self.assertEqual({file.name: file.read_bytes() for file in destination.iterdir()}, matching)
        self.assertEqual({file.name: file.read_bytes() for file in self.source.iterdir() if file.is_file()},
                         originals)
        self.drive_lookup.assert_called_once_with()

    def test_january_uses_december_under_the_requested_current_year(self):
        matching_name = "Walmart_12-31-2026_11-06-06.json"
        for name in (matching_name, "Walmart_12-31-2027.json", "Walmart_1-1-2027.json"):
            (self.source / name).write_bytes(b"receipt")
        destination = ReceiptBackupManager.copy_receipts(self.source, date(2027, 1, 3))
        self.assertEqual(destination, self.drive / "My Stuff" / "Documents" / "Finances"
                         / "2027" / "December" / "Supporting Documents")
        self.assertTrue(destination.is_dir())
        self.assertEqual([file.name for file in destination.iterdir()], [matching_name])

    def test_hidden_receipts_are_skipped_without_changing_sources_or_existing_backups(self):
        hidden_name = "Apple_9-5-2026_00-00-00_2.json"
        visible_name = "Apple_9-5-2026_00-00-00.json"
        (self.source / hidden_name).write_bytes(b"hidden receipt")
        (self.source / visible_name).write_bytes(b"visible receipt")
        destination = ReceiptBackupManager.copy_receipts(self.source, date(2026, 10, 3),
                                                        excluded_file_names={hidden_name.upper()})
        self.assertEqual({file.name for file in destination.iterdir()}, {visible_name})
        self.assertEqual((self.source / hidden_name).read_bytes(), b"hidden receipt")
        (destination / hidden_name).write_bytes(b"existing backup")
        ReceiptBackupManager.copy_receipts(self.source, date(2026, 10, 3),
                                           excluded_file_names={hidden_name}, overwrite=True)
        self.assertEqual((destination / hidden_name).read_bytes(), b"existing backup")

    def test_retry_updates_matching_receipts_and_preserves_other_backup_files(self):
        file_name = "Walmart_9-29-2026.json"
        (self.source / file_name).write_bytes(b"original")
        destination = ReceiptBackupManager.copy_receipts(self.source, date(2026, 10, 3))
        (destination / "other.json").write_bytes(b"keep")
        (self.source / file_name).write_bytes(b"updated")
        self.assertEqual(ReceiptBackupManager.copy_receipts(self.source, date(2026, 10, 3), overwrite=True), destination)
        self.assertEqual((destination / file_name).read_bytes(), b"updated")
        self.assertEqual((destination / "other.json").read_bytes(), b"keep")
        self.assertEqual((self.source / file_name).read_bytes(), b"updated")

    def test_missing_drive_leaves_source_files_intact(self):
        file_name = "Walmart_9-29-2026.json"
        (self.source / file_name).write_bytes(b"keep")
        self.drive_lookup.side_effect = FileNotFoundError("Connect PrimaryBckp")
        with self.assertRaisesRegex(FileNotFoundError, "PrimaryBckp"):
            ReceiptBackupManager.copy_receipts(self.source, date(2026, 10, 3))
        self.assertEqual((self.source / file_name).read_bytes(), b"keep")
        self.assertEqual(list(self.drive.iterdir()), [])

    def test_resolving_review_folder_does_not_create_it(self):
        destination = ReceiptBackupManager.review_directory(date(2026, 10, 3))
        self.assertEqual(destination, self.drive / "My Stuff" / "Documents" / "Finances" / "2026" / "September")
        self.assertFalse(destination.exists())
        self.assertEqual(list(self.drive.iterdir()), [])

    def test_existing_month_requires_authorization_even_without_a_receipts_folder(self):
        destination = ReceiptBackupManager.review_directory(date(2026, 10, 3))
        destination.mkdir(parents=True)
        report = destination / "Expense Review.pdf"
        report.write_bytes(b"existing report")
        (self.source / "Apple_9-2-2026.json").write_bytes(b"new receipt")
        with self.assertRaises(FileExistsError):
            ReceiptBackupManager.copy_receipts(self.source, date(2026, 10, 3))
        self.assertEqual(report.read_bytes(), b"existing report")
        self.assertEqual(list(destination.iterdir()), [report])

    def test_existing_receipt_cannot_be_replaced_without_authorization(self):
        name = "Apple_9-2-2026.json"
        (self.source / name).write_bytes(b"original")
        destination = ReceiptBackupManager.copy_receipts(self.source, date(2026, 10, 3))
        (self.source / name).write_bytes(b"updated")
        with self.assertRaises(FileExistsError):
            ReceiptBackupManager.copy_receipts(self.source, date(2026, 10, 3))
        self.assertEqual((destination / name).read_bytes(), b"original")
        self.assertEqual((self.source / name).read_bytes(), b"updated")

    def test_missing_source_does_not_create_a_backup(self):
        with self.assertRaises(FileNotFoundError):
            ReceiptBackupManager.copy_receipts(self.workspace / "missing", date(2026, 10, 3))
        self.drive_lookup.assert_not_called()
        self.assertEqual(list(self.drive.iterdir()), [])

    def test_supporting_documents_combine_receipts_and_only_the_three_uploaded_statements(self):
        visible = "Apple_9-2-2026.json"
        hidden = "Apple_9-3-2026.json"
        for name in (visible, hidden, "Apple_8-2-2026.json", "Apple_9-2-2025.json"):
            (self.source / name).write_bytes(name.encode())
        (self.statements / "Discover-example.pdf").write_bytes(b"unrelated PDF")
        destination = ReceiptBackupManager.copy_supporting_documents(
            self.source, self.statements, date(2026, 10, 3), excluded_file_names={hidden})
        self.assertEqual(destination, self.drive / "My Stuff" / "Documents" / "Finances"
                         / "2026" / "September" / "Supporting Documents")
        self.assertEqual({file.name: file.read_bytes() for file in destination.iterdir()},
                         self.statement_contents | {visible: visible.encode()})
        self.assertEqual(list(destination.parent.iterdir()), [destination])
        self.assertFalse((destination.parent / "Receipts").exists())
        self.assertEqual({file.name: file.read_bytes() for file in self.statements.iterdir()},
                         self.statement_contents | {"Discover-example.pdf": b"unrelated PDF"})
        self.assertEqual((self.source / hidden).read_bytes(), hidden.encode())

    def test_missing_statement_stops_backup_before_creating_or_changing_any_output(self):
        for missing_name in self.statement_contents:
            with self.subTest(statement=missing_name):
                (self.statements / missing_name).unlink()
                with self.assertRaisesRegex(FileNotFoundError, "Missing uploaded statement"):
                    ReceiptBackupManager.copy_supporting_documents(self.source, self.statements, date(2026, 10, 3))
                self.assertEqual(list(self.drive.iterdir()), [])
                (self.statements / missing_name).write_bytes(self.statement_contents[missing_name])
        self.drive_lookup.assert_not_called()

    def test_existing_month_blocks_both_receipt_and_statement_replacement_until_authorized(self):
        name = "Apple_9-2-2026.json"
        (self.source / name).write_bytes(b"original receipt")
        destination = ReceiptBackupManager.copy_supporting_documents(self.source, self.statements, date(2026, 10, 3))
        original_files = {file.name: file.read_bytes() for file in destination.iterdir()}
        report = destination.parent / "Expense Review.pdf"
        report.write_bytes(b"existing report")
        (self.source / name).write_bytes(b"updated receipt")
        (self.statements / Files.CREDIT_CARD_PREVIOUS_MONTH_STATEMENT_PDF).write_bytes(b"updated statement")
        with self.assertRaises(FileExistsError):
            ReceiptBackupManager.copy_supporting_documents(self.source, self.statements, date(2026, 10, 3))
        self.assertEqual({file.name: file.read_bytes() for file in destination.iterdir()}, original_files)
        (destination / "other.txt").write_bytes(b"keep")
        ReceiptBackupManager.copy_supporting_documents(self.source, self.statements, date(2026, 10, 3), overwrite=True)
        self.assertEqual((destination / name).read_bytes(), b"updated receipt")
        self.assertEqual((destination / Files.CREDIT_CARD_PREVIOUS_MONTH_STATEMENT_PDF).read_bytes(), b"updated statement")
        self.assertEqual((destination / "other.txt").read_bytes(), b"keep")
        self.assertEqual(report.read_bytes(), b"existing report")

    def test_supporting_documents_require_confirmation_for_a_month_with_only_an_existing_report(self):
        month = ReceiptBackupManager.review_directory(date(2026, 10, 3))
        month.mkdir(parents=True)
        report = month / "Expense Review.pdf"
        report.write_bytes(b"existing report")
        with self.assertRaises(FileExistsError):
            ReceiptBackupManager.copy_supporting_documents(self.source, self.statements, date(2026, 10, 3))
        self.assertEqual(list(month.iterdir()), [report])
        self.assertEqual(report.read_bytes(), b"existing report")


if __name__ == "__main__":
    unittest.main()
