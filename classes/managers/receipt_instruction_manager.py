import re
from pathlib import Path

from classes.financial_transaction_class import FinancialTransaction
from enums.files_enum import Files
from enums.finances.locations_enum import Locations
from enums.paths_enum import Paths


class ReceiptInstructionManager:
    """Prepare receipt collection instructions from the review's transactions."""

    @staticmethod
    def render(template: str, transactions: list[FinancialTransaction]) -> str:
        has_amazon_purchase = any(
            transaction.amount < 0 and (
                transaction.location == Locations.AMAZON
                or re.search(r"\b(?:amazon|amzn)\b", transaction.purchase_title or "", re.IGNORECASE)
            )
            for transaction in transactions
        )
        before, opening, remainder = template.partition("[[AMAZON_PURCHASES]]\n")
        amazon_section, closing, after = remainder.partition("[[/AMAZON_PURCHASES]]\n")
        if not opening or not closing:
            raise ValueError("The receipt instructions are missing the conditional Amazon section markers.")
        return before + (amazon_section if has_amazon_purchase else "") + after

    @staticmethod
    def create(destination_path: str | Path) -> Path:
        # Use the same statement imports and review-month filtering as the editor.
        from classes.pages.child_pages.expense_reveiw_pages.final_review_page import _import_transactions

        transactions = _import_transactions()
        template_path = Path(Paths.ASSETS_TXTS) / Files.RECEIPT_INSTRUCTIONS_TXT
        instructions = ReceiptInstructionManager.render(template_path.read_text(encoding="utf-8"), transactions)
        destination = Path(destination_path) / Files.RECEIPT_INSTRUCTIONS_TXT
        destination.write_text(instructions, encoding="utf-8")
        return destination
