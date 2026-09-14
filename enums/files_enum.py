"""Imports"""
from enum import StrEnum

class Files(StrEnum):
    CREDIT_CARD_PREVIOUS_MONTH_STATEMENT_CSV = "credit_card_previous_month_statement.csv"
    CREDIT_CARD_PREVIOUS_PREVIOUS_MONTH_STATEMENT_CSV = "credit_card_previous_previous_month_statement.csv"
    CHECKING_ACCOUNT_PREVIOUS_MONTH_STATEMENT_PDF = "checking_account_previous_month_statement.pdf"
    RECEIPT_INSTRUCTIONS_TXT = "receipt_instructions.txt"
    RECEIPT_EXAMPLE_JSON = "receipt_example.json"


