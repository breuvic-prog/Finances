import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zipfile import BadZipFile, ZipFile

from classes.pages.child_pages.expense_reveiw_pages import reciepts_input_page


class ReceiptsInputTests(unittest.TestCase):
    def setUp(self):
        tests_directory = Path(__file__).resolve().parent
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="receipt-import-check-", dir=tests_directory
        )
        self.workspace = Path(self.temporary_directory.name).resolve()
        # Keep temporary-directory cleanup inside this test's workspace.
        if self.workspace.parent != tests_directory:
            raise RuntimeError("Unexpected temporary directory location.")
        self.addCleanup(self.temporary_directory.cleanup)
        self.receipts_directory = self.workspace / "receipts"
        self.receipts_directory.mkdir()
        paths_patch = patch.object(
            reciepts_input_page, "Paths",
            SimpleNamespace(RECEIPTS=str(self.receipts_directory)),
        )
        paths_patch.start()
        self.addCleanup(paths_patch.stop)

        self.page = object.__new__(reciepts_input_page.ReceiptsInputPage)
        self.page._zip_warning_label = Mock()
        self.page._parent_next_method = Mock()
        self.page._zip_path = None

    def make_archive(self):
        archive_path = self.workspace / "new_receipts.zip"
        with ZipFile(archive_path, "w") as archive:
            archive.writestr("New_9-30-2026.json", '{"receipt": "new"}')
        self.page._zip_path = str(archive_path)

    def test_clears_old_jsons_before_extracting_new_receipts(self):
        (self.receipts_directory / "Old_9-01-2026.json").write_text("{}")
        (self.receipts_directory / "Older.JSON").write_text("{}")
        (self.receipts_directory / "notes.txt").write_text("keep")
        self.make_archive()

        real_unzip = reciepts_input_page.FolderManager.unzip

        def extract_after_cleanup(*args, **kwargs):
            self.assertEqual(
                {path.name for path in self.receipts_directory.iterdir()}, {"notes.txt"}
            )
            return real_unzip(*args, **kwargs)

        with patch.object(reciepts_input_page.FolderManager, "unzip", side_effect=extract_after_cleanup):
            self.page._finalize()

        self.assertEqual(
            {path.name for path in self.receipts_directory.iterdir()},
            {"New_9-30-2026.json", "notes.txt"},
        )
        self.assertEqual(
            (self.receipts_directory / "New_9-30-2026.json").read_text(),
            '{"receipt": "new"}',
        )
        self.page._parent_next_method.assert_called_once_with()

    def test_invalid_zip_preserves_existing_receipts(self):
        existing_receipt = self.receipts_directory / "Existing.json"
        existing_receipt.write_text('{"receipt": "existing"}')
        invalid_archive = self.workspace / "invalid.zip"
        invalid_archive.write_text("not a ZIP")
        self.page._zip_path = str(invalid_archive)

        with self.assertRaises(BadZipFile):
            self.page._finalize()

        self.assertEqual(existing_receipt.read_text(), '{"receipt": "existing"}')
        self.page._parent_next_method.assert_not_called()

    def test_no_selected_zip_preserves_existing_receipts(self):
        existing_receipt = self.receipts_directory / "Existing.json"
        existing_receipt.write_text("{}")

        self.page._finalize()

        self.assertTrue(existing_receipt.exists())
        self.page._zip_warning_label.activate.assert_called_once_with()
        self.page._parent_next_method.assert_not_called()

    def test_first_import_creates_receipts_directory(self):
        self.receipts_directory.rmdir()
        self.make_archive()

        self.page._finalize()

        self.assertTrue((self.receipts_directory / "New_9-30-2026.json").is_file())
        self.page._parent_next_method.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
