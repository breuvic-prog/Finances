import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from classes.managers.review_files_manager import ReviewFilesManager


class ReviewFilesCleanupTests(unittest.TestCase):
    def setUp(self):
        tests_directory = Path(__file__).resolve().parent
        self.workspace = Path(self.enterContext(tempfile.TemporaryDirectory(
            prefix="review-cleanup-", dir=tests_directory))).resolve()
        if self.workspace.parent != tests_directory:
            raise RuntimeError("Unexpected temporary directory location.")
        self.manager = ReviewFilesManager()

    def test_only_registered_working_files_are_removed_and_saved_documents_remain(self):
        project = self.workspace / "project"
        downloads = self.workspace / "Downloads"
        saved = self.workspace / "flash-drive" / "September"
        for directory in (project, downloads, saved):
            directory.mkdir(parents=True)
        inputs = [project / "receipt.json", project / "discover.pdf", project / "bank.pdf",
                  downloads / "instructions.zip"]
        retained = [project / "receipt_example.json", project / "other.pdf", project / "notes.txt",
                    downloads / "original.pdf", downloads / "receipts.zip", saved / "Expense Review.pdf"]
        supporting = saved / "Supporting Documents"
        supporting.mkdir()
        retained.append(supporting / "receipt.json")
        for path in inputs + retained:
            path.write_bytes(b"keep until complete")
        for path in inputs:
            self.manager.track_file(path, path.parent)
        self.manager.cleanup()
        self.assertTrue(all(not path.exists() for path in inputs))
        self.assertTrue(all(path.read_bytes() == b"keep until complete" for path in retained))
        self.assertTrue(project.is_dir())
        self.assertTrue(downloads.is_dir())
        self.manager.cleanup()

    def test_replaced_imports_and_missing_working_files_can_be_cleaned_up(self):
        statement = self.workspace / "statement.pdf"
        statement.write_bytes(b"old")
        self.manager.track_file(statement, self.workspace)
        statement.write_bytes(b"new import")
        self.manager.track_file(statement, self.workspace)
        self.manager.track_file(self.workspace / "already-removed.json", self.workspace)
        self.manager.cleanup()
        self.assertFalse(statement.exists())
        self.assertEqual(self.manager._files, {})

    def test_directory_and_outside_paths_cannot_be_registered_for_deletion(self):
        allowed = self.workspace / "receipts"
        allowed.mkdir()
        outside = self.workspace / "outside.json"
        outside.write_bytes(b"keep")
        for path in (allowed, outside, allowed / ".." / "outside.json"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "outside its working directory"):
                self.manager.track_file(path, allowed)
        self.manager.cleanup()
        self.assertTrue(allowed.is_dir())
        self.assertEqual(outside.read_bytes(), b"keep")

    def test_failure_preserves_pending_files_and_retry_only_removes_those_remaining(self):
        completed = self.workspace / "receipt.json"
        blocked = self.workspace / "statement.pdf"
        for path in (completed, blocked):
            path.write_bytes(b"working file")
            self.manager.track_file(path, self.workspace)
        unlink = Path.unlink

        def remove(path, *args, **kwargs):
            if path == blocked:
                raise PermissionError("File is open")
            return unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", autospec=True, side_effect=remove), \
                self.assertRaisesRegex(OSError, "File is open"):
            self.manager.cleanup()
        self.assertFalse(completed.exists())
        self.assertEqual(blocked.read_bytes(), b"working file")
        self.assertEqual(set(self.manager._files), {blocked})
        self.manager.cleanup()
        self.assertFalse(blocked.exists())
        self.assertEqual(self.manager._files, {})

    def test_resolved_paths_are_rechecked_before_deleting_files(self):
        imported = self.workspace / "imported.json"
        imported.write_bytes(b"keep")
        self.manager.track_file(imported, self.workspace)
        resolve = Path.resolve

        def changed_path(path, *args, **kwargs):
            if path == imported:
                return self.workspace.parent / "outside.json"
            return resolve(path, *args, **kwargs)

        with patch.object(Path, "resolve", autospec=True, side_effect=changed_path), \
                self.assertRaisesRegex(OSError, "outside its working directory"):
            self.manager.cleanup()
        self.assertEqual(imported.read_bytes(), b"keep")
        self.assertIn(imported, self.manager._files)


if __name__ == "__main__":
    unittest.main()
