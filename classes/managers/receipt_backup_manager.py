import ctypes
import os
import re
import shutil
from ctypes import wintypes
from datetime import date, timedelta
from pathlib import Path
from collections.abc import Iterable

from classes.managers.date_manager import DateManager
from classes.managers.file_manager import FileManager
from enums.files_enum import Files


class ReceiptBackupManager:
    DRIVE_LABEL = "PrimaryBckp"
    SUPPORTING_DOCUMENTS_FOLDER = "Supporting Documents"
    STATEMENT_FILES = (Files.CREDIT_CARD_PREVIOUS_MONTH_STATEMENT_PDF,
                       Files.CREDIT_CARD_PREVIOUS_PREVIOUS_MONTH_STATEMENT_PDF,
                       Files.CHECKING_ACCOUNT_PREVIOUS_MONTH_STATEMENT_PDF)

    @classmethod
    def _find_drive(cls) -> Path:
        """Find the backup volume by label, independently of its drive letter."""
        if os.name != "nt":
            raise OSError("The PrimaryBckp backup requires Windows.")
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        logical_drives = kernel32.GetLogicalDrives
        logical_drives.argtypes = []
        logical_drives.restype = wintypes.DWORD
        volume_information = kernel32.GetVolumeInformationW
        volume_information.argtypes = [
            wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD,
        ]
        volume_information.restype = wintypes.BOOL
        drives = logical_drives()
        if not drives:
            raise ctypes.WinError(ctypes.get_last_error())
        for index in range(26):
            if not drives & (1 << index):
                continue
            root = f"{chr(ord('A') + index)}:\\"
            label = ctypes.create_unicode_buffer(261)
            if (volume_information(root, label, len(label), None, None, None, None, 0)
                    and label.value.casefold() == cls.DRIVE_LABEL.casefold()):
                return Path(root)
        raise FileNotFoundError("Connect the PrimaryBckp flash drive and try Finalize again.")

    @classmethod
    def review_directory(cls, current_date: date | None = None) -> Path:
        """Resolve the month folder without creating or changing anything."""
        today = current_date if current_date is not None else date.today()
        review_date = today.replace(day=1) - timedelta(days=1)
        return (cls._find_drive() / "My Stuff" / "Documents" / "Finances" / str(today.year)
                / DateManager.month_number_to_name(review_date.month))

    @classmethod
    def copy_receipts(cls, source: str | Path, current_date: date | None = None,
                      excluded_file_names: Iterable[str] = (), destination: Path | None = None,
                      overwrite: bool = False) -> Path:
        """Back up reviewed receipt JSONs, omitting receipts for hidden purchases."""
        files = cls._receipt_sources(source, current_date, excluded_file_names)
        destination = (Path(destination) if destination is not None
                       else cls.review_directory(current_date) / cls.SUPPORTING_DOCUMENTS_FOLDER)
        return cls._copy_files(files, destination, overwrite)

    @classmethod
    def copy_supporting_documents(cls, receipts_source: str | Path, statements_source: str | Path,
                                  current_date: date | None = None,
                                  excluded_file_names: Iterable[str] = (), destination: Path | None = None,
                                  overwrite: bool = False) -> Path:
        """Save reviewed receipts and all three uploaded statements together."""
        files = cls._receipt_sources(receipts_source, current_date, excluded_file_names)
        for name in cls.STATEMENT_FILES:
            statement = Path(statements_source) / name
            if not statement.is_file():
                raise FileNotFoundError(f"Missing uploaded statement: {statement}")
            files.append(statement)
        destination = (Path(destination) if destination is not None
                       else cls.review_directory(current_date) / cls.SUPPORTING_DOCUMENTS_FOLDER)
        return cls._copy_files(files, destination, overwrite)

    @classmethod
    def _receipt_sources(cls, source: str | Path, current_date: date | None,
                         excluded_file_names: Iterable[str]) -> list[Path]:
        file_names = FileManager.get_files_at_location(str(source))
        excluded = {name.casefold() for name in excluded_file_names}
        today = current_date if current_date is not None else date.today()
        review_date = today.replace(day=1) - timedelta(days=1)
        files = []
        for file_name in file_names:
            receipt_date = cls._receipt_date(file_name)
            if (file_name.casefold() not in excluded and receipt_date is not None
                    and (receipt_date.year, receipt_date.month) == (review_date.year, review_date.month)):
                files.append(Path(source) / file_name)
        return files

    @staticmethod
    def _copy_files(files: list[Path], destination: Path, overwrite: bool) -> Path:
        if destination.parent.exists() and not overwrite:
            raise FileExistsError(f"Confirm replacement before writing to the existing review folder: {destination.parent}")
        destination.mkdir(parents=True, exist_ok=True)
        for source in files:
            shutil.copy2(source, destination / source.name)
        return destination

    @staticmethod
    def _receipt_date(file_name: str) -> date | None:
        match = re.search(r"_(\d{1,2})-(\d{1,2})-(\d{4})(?:_\d{1,2}-\d{1,2}-\d{1,2})?(?:_\d+)?\.json$",
                          file_name, re.IGNORECASE)
        if match is None:
            return None
        month, day, year = map(int, match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None
