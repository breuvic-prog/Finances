"""Read Discover's PDF account-activity export without losing wrapped rows."""

from datetime import datetime
from decimal import Decimal
import re

import pymupdf

from classes.managers.file_managers.pdf_manager import PdfManager
from enums.finances.credit_card.credit_card_headers_enum import CreditCardHeaders


_DATE = re.compile(r"\d{1,2}/\d{1,2}/(?:\d{4}|\d{2})")
_AMOUNT = re.compile(r"\$\s*(?P<sign>-?)\s*(?P<value>(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2})(?:\s+(?P<category>.*))?")
_HEADINGS = {"trans.", "trans. date", "date", "post", "post date", "description", "amount", "category"}
_FOOTERS = ("statement balance", "redemption activity this period", "your cashback bonus", "©")


class DiscoverStatementManager:
    @classmethod
    def open(cls, name: str, path: str) -> list[dict]:
        try:
            pages = PdfManager.open(name=name, path=path)
        except (pymupdf.FileDataError, pymupdf.EmptyFileError) as error:
            raise ValueError("Could not read the Discover PDF. Select a valid PDF account-activity export.") from error
        return cls.parse(pages)

    @staticmethod
    def _date(value: str) -> str:
        pattern = "%m/%d/%Y" if len(value.rsplit("/", 1)[1]) == 4 else "%m/%d/%y"
        try:
            return datetime.strptime(value, pattern).strftime("%m/%d/%Y")
        except ValueError as error:
            raise ValueError(f"Invalid date in Discover PDF: {value}") from error

    @classmethod
    def parse(cls, pages: list[str]) -> list[dict]:
        if not any(re.search(r"^\s*Transactions\s*$", page, re.MULTILINE) for page in pages):
            raise ValueError("Could not find the Transactions table in the Discover PDF. Upload a PDF account-activity export.")
        lines = []
        for page in pages:
            page_lines = [" ".join(line.split()) for line in page.splitlines() if line.strip()]
            if "Transactions" in page_lines:
                page_lines = page_lines[page_lines.index("Transactions") + 1:]
                while page_lines and page_lines[0].casefold() in _HEADINGS:
                    page_lines.pop(0)
            for line in page_lines:
                if line.casefold().startswith(_FOOTERS):
                    break
                lines.append(line)
        rows = []
        index = 0
        while index < len(lines):
            if lines[index].casefold() in ("no transactions", "no transactions this period"):
                index += 1
                continue
            if not _DATE.fullmatch(lines[index]):
                raise ValueError(f"Could not read transaction {len(rows) + 1} in the Discover PDF: expected a transaction date.")
            transaction_date = cls._date(lines[index])
            index += 1
            if index == len(lines) or not _DATE.fullmatch(lines[index]):
                raise ValueError(f"Missing posting date for transaction {len(rows) + 1} in the Discover PDF.")
            posting_date = cls._date(lines[index])
            index += 1
            description = []
            while index < len(lines) and not _AMOUNT.fullmatch(lines[index]) and not _DATE.fullmatch(lines[index]):
                if lines[index].startswith("$"):
                    raise ValueError(f"Invalid amount for transaction {len(rows) + 1} in the Discover PDF.")
                description.append(lines[index])
                index += 1
            amount = _AMOUNT.fullmatch(lines[index]) if index < len(lines) else None
            if amount is None or not description:
                raise ValueError(f"Missing description or amount for transaction {len(rows) + 1} in the Discover PDF.")
            index += 1
            category = [amount["category"]] if amount["category"] else []
            while index < len(lines) and not _DATE.fullmatch(lines[index]):
                if lines[index].startswith("$"):
                    raise ValueError(f"Unexpected extra amount in transaction {len(rows) + 1} in the Discover PDF.")
                category.append(lines[index])
                index += 1
            if not category:
                raise ValueError(f"Missing category for transaction {len(rows) + 1} in the Discover PDF.")
            value = Decimal(amount["sign"] + amount["value"].replace(",", ""))
            rows.append({CreditCardHeaders.TRANS_DATE: transaction_date, CreditCardHeaders.POST_DATE: posting_date,
                         CreditCardHeaders.DESCRIPTION: " ".join(description), CreditCardHeaders.AMOUNT: str(value),
                         CreditCardHeaders.CATEGORY: " ".join(category)})
        return rows
