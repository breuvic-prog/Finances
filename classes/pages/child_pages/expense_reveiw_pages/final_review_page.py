"""Imports"""

from classes.custom_tk_components.tk_link_class import TkLink
from classes.custom_tk_components.tk_document_input_class import document_button
from classes.custom_tk_components.tk_table_class import TkTable, get_location_colors
from classes.custom_tk_components.tk_option_dropdown_class import TkOptionLabel
from classes.financial_transaction_class import FinancialTransaction
from classes.general.dollar_amount_class import DollarAmount
from classes.grocery_item import GroceryItem
from classes.managers.category_manager import CategoryManager
from classes.managers.date_manager import DateManager
from classes.managers.discover_statement_manager import DiscoverStatementManager
from classes.managers.description_manager import DescriptionManager
from classes.managers.option_manager import OptionManager
from classes.managers.expense_review_report import ExpenseReviewReport, ReportGenerationError
from classes.managers.receipt_backup_manager import ReceiptBackupManager
from classes.managers.receipt_group_manager import ReceiptGroupManager, ReceiptTransactionRow
from classes.managers.review_files_manager import ReviewFilesManager
from classes.managers.file_manager import FileManager
from classes.managers.file_managers.json_manager import JsonManager
from classes.managers.file_managers.pdf_manager import PdfManager
from classes.managers.string_manager import StringManager
from classes.pages.leaf_page_class import LeafPage
import tkinter as tk
import json
import re
from collections.abc import Callable
from copy import copy
from datetime import datetime
from enum import StrEnum
from classes.general.date_class import Date
from classes.receipt_class import Receipt
from classes.table_column_class import TableColumn
from enums.files_enum import Files
from enums.finances.categories_enum import Categories
from enums.finances.descriptions_enum import Descriptions
from enums.finances.descriptions.car_descriptions_enum import CarDescriptions
from enums.finances.descriptions.income_descriptions_enum import IncomeDescriptions
from enums.finances.descriptions.credit_card_descriptions_enum import CreditCardDescriptions
from enums.finances.credit_card.credit_card_categories_enum import CreditCardCategories
from enums.finances.credit_card.credit_card_headers_enum import CreditCardHeaders
from enums.finances.is_essential_enum import IsEssential
from enums.finances.locations_enum import Locations
from enums.paths_enum import Paths
from classes.general.time_class import Time
from tkinter import font, messagebox, ttk

"""Constants"""
GENERAL = "general"
ITEMS = "items"
SUBTOTAL = "subtotal"
TAX = "tax"
TOTAL = "total"
NAME = "name"
PRICE = "price"
LINK = "link"
CREDIT_CARD_WINDOW_START_DAY = 3
APPLE_RECEIPT_BILLING_DELAY_DAYS = 3
RECEIPT_VIEW_BUTTON_COLORS = {"bg": "#E5EFFB", "fg": "#234E78", "activebackground": "#CADCF2",
                              "activeforeground": "#234E78"}
RECEIPT_ADD_BUTTON_COLORS = {"bg": "#15803D", "fg": "#FFFFFF", "activebackground": "#166534",
                             "activeforeground": "#FFFFFF"}


location_keywords = {
    "cashback bonus redemption":Locations.DISCOVER,
    "cash back bonus redemption":Locations.DISCOVER,
    "deposit by internet":Locations.FREEDOM_BANK,
    "misc. debit":Locations.FREEDOM_BANK,
    "first security":Locations.FIRST_SECURITY_BANK,
    "wal-mart":Locations.WALMART,
    "culver's":Locations.CULVERS,
    "culver’s":Locations.CULVERS,
    "kwik":Locations.KWIK_TRIP,
    "vending":Locations.VENDING_MACHINE
}

"""Functions"""
#Extraction and determination
def _extract_info_from_receipt_name(receipt_file_name: str) -> tuple[str, Date, Time|None]:
    #Extracts info from the name
    parts = StringManager.split(string=receipt_file_name,
                                separator="_")

    #Gets the location
    location = parts[0]

    #Gets the date
    date_parts = StringManager.split(string = parts[1],
                                     separator = "-")
    date = Date(month = int(date_parts[0]),
                day = int(date_parts[1]),
                year = int(date_parts[2]))

    #Gets the time
    time = None
    if len(parts) >= 3:
        time_parts = StringManager.split(string = parts[2],
                                         separator = "-")

        time = Time(hours = int(time_parts[0]),
                    minutes = int(time_parts[1]),
                    seconds = int(time_parts[2]))


    return location, date, time
def _determine_transaction_date(row:dict) -> Date:
    #Splits the original date string
    date_parts = StringManager.split(string = row[CreditCardHeaders.TRANS_DATE],
                                     separator = "/")

    return Date(month = int(date_parts[0]),
                    day = int(date_parts[1]),
                    year = int(date_parts[2]))
def _is_walmart_payroll(row: dict) -> bool:
    description = StringManager.Lowercase(row[CreditCardHeaders.DESCRIPTION])
    return re.search(
        r"\bwal-?mart\s+(?:assocs\.?|associates)\s*,?\s*payroll\b",
        description,
    ) is not None


def _is_internal_movement(row: dict) -> bool:
    """Identify repayments and transfers between owned accounts from statement text."""
    description = re.sub(r"[^a-z0-9]+", " ", str(row[CreditCardHeaders.DESCRIPTION]).casefold()).strip()
    if re.search(r"\bdeposit by internet\b", description):
        return True
    if re.search(r"\b(?:internal transfer|transfer between (?:my |own )?accounts)\b", description):
        return True
    if (re.search(r"\b(?:transfer|xfer|deposit|withdrawal)\b", description)
            and re.search(r"\b(?:from|to) (?:my |own )?(?:savings|checking)(?: account)?\b", description)):
        return True
    # Refunds and rewards come from outside the user's accounts.
    if re.search(r"\b(?:refund|return|reversal|cashback|cash back|rebate|reward|rewards)\b", description):
        return False
    payment = re.search(r"\b(?:payments?|e ?payments?|pymts?|pymnts?|pmts?|autopay)\b", description)
    if payment is None:
        return False
    if row.get(CreditCardHeaders.CATEGORY) == CreditCardCategories.PAYMENTS_AND_CREDITS:
        return True
    return re.search(
        r"\b(?:credit card|creditcard|discover|amex|american express|chase card|chasecard|citi card|citicard)\b",
        description,
    ) is not None

def _determine_transaction_location(row:dict, source:Locations|None = None) -> Locations|None:
    if _is_walmart_payroll(row):
        return Locations.WALMART

    #Finds and lowercases the description
    lowercase_description = " ".join(str(row[CreditCardHeaders.DESCRIPTION]).casefold().split())

    #Checks for specific keywords first
    for keyword in location_keywords:
        if keyword in lowercase_description:
            return source if keyword == "deposit by internet" and source is not None else location_keywords[keyword]

    #Checks if a whole location is included
    for location in list(Locations):
        #Checks for exact matches
        if StringManager.Lowercase(location) in lowercase_description:
            return location

    return source if _is_internal_movement(row) else None
def _determine_transaction_amount(row: dict,
                                  invert_amount: bool) -> DollarAmount:
    # Gets the amount
    amount = float(row[CreditCardHeaders.AMOUNT])

    # Inverts if need be
    if invert_amount:
        amount = -amount

    return DollarAmount(amount)
def _set_transaction_description(existing_object:FinancialTransaction) -> None:
    #Final description
    if existing_object.amount < 0 and existing_object.location == Locations.FIRST_SECURITY_BANK:
        existing_object.autocomplete_description(CarDescriptions.CAR_PAYMENT)

def _set_transaction_category(row: dict,
                              existing_object:FinancialTransaction) -> None:
    description = " ".join(str(row[CreditCardHeaders.DESCRIPTION]).casefold().split())
    if re.search(r"\bpayroll\b", description):
        existing_object.autocomplete_field("category", Categories.INCOME)
        existing_object.autocomplete_description(IncomeDescriptions.PAYCHECK)
    elif re.search(r"\b(?:cashback|cash back)\b", description) and (
        existing_object.location == Locations.DISCOVER or existing_object.source == Locations.DISCOVER
        or row.get(CreditCardHeaders.CATEGORY) == CreditCardCategories.AWARDS_AND_REBATE_CREDITS
        or re.search(r"\bcredit card\b", description)
    ):
        existing_object.autocomplete_field("location", Locations.DISCOVER)
        existing_object.autocomplete_field("category", Categories.CREDIT_CARD)
        existing_object.autocomplete_description(CreditCardDescriptions.CASHBACK)
    elif existing_object.location == Locations.DISCOVER:
        existing_object.autocomplete_field("category", Categories.CREDIT_CARD)
        if _is_internal_movement(row):
            existing_object.autocomplete_description(CreditCardDescriptions.PAYMENT)
    elif existing_object.amount < 0 and existing_object.location == Locations.FIRST_SECURITY_BANK:
        existing_object.autocomplete_field("category", Categories.CAR)
    elif existing_object.amount < 0 and existing_object.location in (
        Locations.CULVERS,
        Locations.PRAIRIE_CINEMA,
        Locations.VENDING_MACHINE,
    ):
        existing_object.autocomplete_field("category", Categories.DISCRETIONARY_SPENDING)

def _set_transaction_is_essential(row: dict,
                                  existing_object:FinancialTransaction) -> None:
    #Checks if the transaction is essential or not by default
    if _is_internal_movement(row):
        existing_object.excluded_from_totals = True
        existing_object.autocomplete_field("is_essential", IsEssential.NOT_INCLUDED)
    elif existing_object.category == Categories.INCOME or (
        existing_object.category == Categories.CREDIT_CARD and existing_object.description == CreditCardDescriptions.CASHBACK
    ):
        existing_object.autocomplete_field("is_essential", IsEssential.ESSENTIAL)
    elif "misc. debit" in StringManager.Lowercase(row[CreditCardHeaders.DESCRIPTION]):
        existing_object.autocomplete_field("is_essential", IsEssential.ESSENTIAL)
    elif _is_walmart_payroll(row):
        existing_object.autocomplete_field("is_essential", IsEssential.ESSENTIAL)
    elif existing_object.location in (
        Locations.VENDING_MACHINE,
        Locations.CULVERS,
        Locations.PRAIRIE_CINEMA,
    ):
        existing_object.autocomplete_field("is_essential", IsEssential.NON_ESSENTIAL)
    elif existing_object.category == Categories.CAR:
        existing_object.autocomplete_field("is_essential", IsEssential.ESSENTIAL)



def _create_financial_transaction_object(row: dict,
                                         invert_amount:bool = False,
                                         source:Locations|None = None) -> FinancialTransaction:
    #Creates the initial object
    financial_transaction = FinancialTransaction(date = _determine_transaction_date(row),
                                                 amount = _determine_transaction_amount(row = row,
                                                                                        invert_amount = invert_amount),
                                                 location = _determine_transaction_location(row, source),
                                                 purchase_title = row[CreditCardHeaders.DESCRIPTION],
                                                 source = source)

    #Sets the description
    _set_transaction_description(existing_object = financial_transaction)

    #Sets the category
    _set_transaction_category(row = row,
                              existing_object = financial_transaction)

    #Sets is essential
    _set_transaction_is_essential(row = row,
                                  existing_object = financial_transaction)

    return financial_transaction

#Importing
def _import_receipts() -> list[Receipt]:
    #Final list of receipts
    receipts = []

    #Goes through all the receipts
    for receipt_file_name in FileManager.get_files_at_location(Paths.RECEIPTS):
        #Extracts info from the name
        location, date, time = _extract_info_from_receipt_name(receipt_file_name[:-5])

        #Gets data from the file
        data = JsonManager.open(name = receipt_file_name,
                                path = Paths.RECEIPTS)

        #Creates the grocery items
        grocery_items = []

        for grocery_item_dict in data[ITEMS]:
            #Checks if a link is provided
            link = None
            if LINK in grocery_item_dict:
                link = grocery_item_dict[LINK]

            category = grocery_item_dict.get("category")
            essential = grocery_item_dict.get("is_essential")
            description = grocery_item_dict.get("description")
            if category is not None and category.strip().casefold() == "paycheck" and description is None:
                description = IncomeDescriptions.PAYCHECK
            # Preserve exclusion when loading receipts saved with the old category.
            if category is not None and category.casefold() == "not included":
                category = None
                essential = IsEssential.NOT_INCLUDED

            if category is not None:
                category = OptionManager.resolve(Categories, category) or Categories(category)
            if description is not None:
                description = (OptionManager.resolve(DescriptionManager.choices(category, include_hidden=True), str(description))
                               or description)

            #Adds the object
            grocery_items.append(GroceryItem(name = grocery_item_dict[NAME],
                                             price = grocery_item_dict[PRICE],
                                             link = link,
                                             quantity = grocery_item_dict.get("quantity", 1),
                                             category = category,
                                             is_essential = IsEssential(essential) if essential is not None else None,
                                             description = description))

        #Creates the receipt object
        receipts.append(Receipt(location = location,
                                date = date,
                                time = time,
                                 subtotal = data[GENERAL][SUBTOTAL],
                                taxes = data[GENERAL][TAX],
                                total = data[GENERAL][TOTAL],
                                items = grocery_items,
                                source_file_name = receipt_file_name,
                                raw_contents = json.dumps(data, indent=2, ensure_ascii=False)))

    return receipts
def _import_credit_card_transactions() -> list[FinancialTransaction]:
    #Final credit card activity
    credit_card_transactions = []

    #Gets the document data
    documents = [Files.CREDIT_CARD_PREVIOUS_MONTH_STATEMENT_PDF,
                 Files.CREDIT_CARD_PREVIOUS_PREVIOUS_MONTH_STATEMENT_PDF]

    for document_name in documents:
        # Opens the document
        data = DiscoverStatementManager.open(name=document_name, path=Paths.ASSETS_PDFS)

        # Goes through all the transactions
        for row in data:
            #Creates the object
            credit_card_transactions.append(_create_financial_transaction_object(row = row,
                                                          invert_amount = True, source = Locations.DISCOVER))

    return credit_card_transactions
def _import_checking_account_transactions() -> list[FinancialTransaction]:
    """Import Freedom Bank's itemized debits and credits, preserving column spacing."""
    pages = PdfManager.open(name=Files.CHECKING_ACCOUNT_PREVIOUS_MONTH_STATEMENT_PDF,
                            path=Paths.ASSETS_PDFS)

    period = re.search(
        r"\b(\d{1,2}-[A-Z]{3}-\d{2}(?:\d{2})?)\s+THRU\s+"
        r"(\d{1,2}-[A-Z]{3}-\d{2}(?:\d{2})?)\b",
        "\n".join(pages),
    )
    if period is None:
        raise ValueError("Could not find the statement period in the checking-account PDF.")
    period_dates = [
        datetime.strptime(value, "%d-%b-%Y" if len(value.rsplit("-", 1)[1]) == 4 else "%d-%b-%y")
        for value in period.groups()
    ]
    statement_start, statement_end = period_dates
    if statement_start > statement_end:
        raise ValueError("The checking-account statement period is reversed.")

    date_pattern = re.compile(r"^\s*\d{1,2}-\d{1,2}(?=\s)")
    row_pattern = re.compile(
        r"^\s*(?P<month>\d{1,2})-(?P<day>\d{1,2})\s+"
        r"(?P<description>.+?)\s+"
        r"(?P<amount>(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2})\s*$"
    )
    rows = []
    found_transactions_section = False
    for page in pages:
        section = re.search(r"^-- ITEMIZED TRANSACTIONS[^\n]*$", page, re.MULTILINE)
        if section is None:
            continue
        heading = section.group()
        if "DEBITS" not in heading or "CREDITS" not in heading:
            raise ValueError("Missing debit/credit columns in the checking-account PDF.")
        found_transactions_section = True
        credit_column = heading.index("CREDITS")

        # Page headers, balance tables, and check-image captions are not transactions.
        for line in page[section.end():].splitlines():
            if line.strip().startswith("--"):
                break
            if date_pattern.match(line):
                match = row_pattern.fullmatch(line)
                if match is None:
                    raise ValueError(f"Could not parse checking-account transaction row {len(rows) + 1}.")

                month = int(match["month"])
                year = statement_start.year if month >= statement_start.month else statement_end.year
                transaction_date = datetime(year, month, int(match["day"]))
                if not statement_start <= transaction_date <= statement_end:
                    raise ValueError("A checking-account transaction date falls outside the statement period.")

                amount = float(match["amount"].replace(",", ""))
                # Amounts are right-aligned; large credits may start left of their heading.
                if match.end("amount") <= credit_column:
                    amount = -amount
                rows.append({
                    CreditCardHeaders.TRANS_DATE: (
                        f"{transaction_date.month}/{transaction_date.day}/{transaction_date.year}"
                    ),
                    CreditCardHeaders.DESCRIPTION: " ".join(match["description"].split()),
                    CreditCardHeaders.AMOUNT: amount,
                    CreditCardHeaders.CATEGORY: None,
                })
            elif rows and line.strip():
                rows[-1][CreditCardHeaders.DESCRIPTION] += " " + " ".join(line.split())

    if not found_transactions_section:
        raise ValueError("Could not find ITEMIZED TRANSACTIONS in the checking-account PDF.")

    return [_create_financial_transaction_object(row=row, source=Locations.FREEDOM_BANK) for row in rows]
def _import_transactions() -> list[FinancialTransaction]:
    #Gets the credit card transactions
    transactions = _import_credit_card_transactions()

    #Adds the checking account transactions
    transactions.extend(_import_checking_account_transactions())

    #Removes all transactions not from the previous month
    previous_month = DateManager.get_current_month() - 1

    i = len(transactions) - 1
    while i >= 0:
        #Checks if the date matches the previous months
        if transactions[i].date.month != previous_month:
            transactions.remove(transactions[i])

        #Decrements the index
        i -= 1

    #Sorts the transactions by date
    transactions.sort(key=lambda transaction: transaction.date)

    return transactions


def _determine_receipt_location(location: str) -> Locations | None:
    renamed = OptionManager.resolve(Locations, location)
    if renamed is not None:
        return renamed
    normalized = re.sub(r"[^a-z0-9]", "", location.lower())
    for candidate in Locations:
        if normalized == re.sub(r"[^a-z0-9]", "", candidate.lower()):
            return candidate
    # Receipt names can use aliases such as Kwik Star instead of Kwik Trip.
    return _determine_transaction_location({CreditCardHeaders.DESCRIPTION: location})


def _assign_receipts(transactions: list[FinancialTransaction], receipts: list[Receipt]) -> None:
    """Prefer exact matches, then allow unique Apple charges shortly after the receipt date."""
    assigned_receipts = {id(transaction.receipt) for transaction in transactions
                         if transaction.receipt is not None}
    receipts_by_key = {}
    for receipt in receipts:
        location = _determine_receipt_location(receipt.location)
        if location is None or id(receipt) in assigned_receipts:
            continue
        key = (receipt.date.year, receipt.date.month, receipt.date.day,
               round(receipt.total * 100), location)
        receipts_by_key.setdefault(key, []).append(receipt)

    transactions_by_key = {}
    for transaction in transactions:
        if transaction.receipt is not None or transaction.location is None:
            continue
        key = (transaction.date.year, transaction.date.month, transaction.date.day,
               round(-transaction.amount * 100), transaction.location)
        transactions_by_key.setdefault(key, []).append(transaction)

    for key, matching_transactions in transactions_by_key.items():
        matching_receipts = receipts_by_key.get(key, [])
        if len(matching_transactions) == len(matching_receipts) == 1:
            matching_transactions[0].receipt = matching_receipts[0]

    # Apple receipt dates can precede the charge date. Keep the amount exact and
    # require a unique candidate in both directions rather than guessing.
    assigned_receipts = {id(transaction.receipt) for transaction in transactions
                         if transaction.receipt is not None}
    apple_receipts = [
        (receipt, datetime(receipt.date.year, receipt.date.month, receipt.date.day))
        for receipt in receipts
        if id(receipt) not in assigned_receipts and _determine_receipt_location(receipt.location) == Locations.APPLE
    ]
    transaction_matches = []
    receipt_match_counts = {}
    for transaction in transactions:
        if transaction.receipt is not None or transaction.location != Locations.APPLE or transaction.amount >= 0:
            continue
        charge_date = datetime(transaction.date.year, transaction.date.month, transaction.date.day)
        matching_receipts = [
            receipt for receipt, receipt_date in apple_receipts
            if round(receipt.total * 100) == round(-transaction.amount * 100)
            and 0 <= (charge_date - receipt_date).days <= APPLE_RECEIPT_BILLING_DELAY_DAYS
        ]
        transaction_matches.append((transaction, matching_receipts))
        for receipt in matching_receipts:
            receipt_match_counts[id(receipt)] = receipt_match_counts.get(id(receipt), 0) + 1
    for transaction, matching_receipts in transaction_matches:
        if len(matching_receipts) == 1 and receipt_match_counts[id(matching_receipts[0])] == 1:
            transaction.receipt = matching_receipts[0]


def _set_transaction_defaults_from_receipts(transactions: list[FinancialTransaction]) -> None:
    for transaction in transactions:
        receipt = transaction.receipt
        if transaction.amount >= 0 or transaction.is_essential == IsEssential.NOT_INCLUDED:
            continue
        if receipt is None:
            has_gas = transaction.location == Locations.KWIK_TRIP and transaction.amount < -25
        else:
            has_gas = any(re.search(r"\bgas(?:oline)?\b", item.name, re.IGNORECASE)
                          for item in receipt.items)
        if has_gas:
            transaction.autocomplete_description(CarDescriptions.GAS)
            transaction.autocomplete_field("category", Categories.CAR)
            transaction.autocomplete_field("is_essential", IsEssential.ESSENTIAL)
        elif receipt is not None and transaction.location == Locations.KWIK_TRIP:
            transaction.autocomplete_field("category", Categories.DISCRETIONARY_SPENDING)
            transaction.autocomplete_field("is_essential", IsEssential.NON_ESSENTIAL)


class FinalReviewPage(LeafPage):
    def __init__(self, parent_root: tk.Tk | tk.Frame,
                 parent_next_method: Callable, review_files: ReviewFilesManager | None = None):
        self._review_files = review_files if review_files is not None else ReviewFilesManager()
        self._outputs_saved = False
        #Attributes
        self._receipts: list[Receipt] = []
        self._transactions: list[FinancialTransaction] | None = None
        self._transaction_rows: list[ReceiptTransactionRow] = []
        self._transaction_table: TkTable | None = None
        self._finalize_button: tk.Button | None = None
        self._review_header: tk.Frame | None = None
        self._review_footer: tk.Frame | None = None

        super().__init__(parent_root, parent_next_method)



    def activate(self) -> None:
        self._outputs_saved = False
        # Read the files after the statement and receipt upload steps finish.
        self._receipts = _import_receipts()
        self._transactions = _import_transactions()
        _assign_receipts(self._transactions, self._receipts)
        _set_transaction_defaults_from_receipts(self._transactions)
        for component in self._root.winfo_children():
            component.destroy()
        self._setup_components()
        super().activate()

    def _setup_components(self) -> None:
        if self._transactions is None:
            return

        for component in (self._review_header, self._review_footer):
            if component is not None and component.winfo_exists():
                component.destroy()
        self._root.configure(bg="#F4F6F9")
        default_font = font.nametofont("TkDefaultFont", root=self._root).actual()
        family, size = default_font["family"], default_font["size"]
        self._transaction_rows = [row for purchase in self._transactions for row in ReceiptGroupManager.rows(purchase)]
        unassigned_count = len(self._unassigned_receipts())
        header = self._review_header = tk.Frame(self._root, bg="#F4F6F9")
        header.pack(fill="x", padx=20, pady=(18, 14))
        header.columnconfigure(0, weight=1)
        tk.Label(header, text="Expense Review", bg="#F4F6F9", fg="#172B4D",
                 font=(family, size + 7, "bold"), anchor="w").grid(row=0, column=0, sticky="w")
        counts = tk.Frame(header, bg="#F4F6F9")
        counts.grid(row=0, column=1, sticky="e")
        for text in (f"{len(self._transaction_rows)} rows", f"{unassigned_count} unassigned receipts"):
            tk.Label(counts, text=text, bg="#E5EFFB", fg="#234E78", padx=10, pady=5,
                     font=(family, size, "bold")).pack(side="left", padx=(8, 0))
        period = ""
        if self._transactions:
            date = self._transactions[0].date
            period = f"{DateManager.month_number_to_name(date.month)} {date.year}  |  "
        tk.Label(header, text=f"{period}Review your transactions and receipts before finalizing.",
                 bg="#F4F6F9", fg="#64748B", anchor="w").grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 0))

        #Creates the table component
        table = TkTable(self._root,
                        stretch_column=5,
                        review_style=True,
                        on_location_changed=self._set_transaction_location,
                        on_category_changed=self._set_transaction_category,
                        on_is_essential_changed=self._set_transaction_is_essential,
                        columns = [TableColumn(text = "Date",
                                               data_type = Date),
                                   TableColumn(text = "Time",
                                               data_type = tk.Widget),
                                   TableColumn(text = "Location",
                                               data_type = Locations),
                                   TableColumn(text = "Amount",
                                               data_type = DollarAmount),
                                   TableColumn(text = "Category",
                                               data_type = Categories),
                                   TableColumn(text = "Description",
                                               data_type = tk.Widget),
                                   TableColumn(text = "Is Essential?",
                                               data_type = IsEssential),
                                   TableColumn(text = "Receipt",
                                               data_type = tk.Widget),
                                   TableColumn(text = "Hidden",
                                               data_type = tk.Widget)])
        self._transaction_table = table
        self._transaction_description_cells = {}
        self._hidden_variables = {}

        #Goes through all the transactions
        for i, transaction_row in enumerate(self._transaction_rows):
            transaction = transaction_row.transaction
            def remains_editable(field, row=transaction_row):
                return not row.transaction.is_field_locked(field)
            # Capitalizes category if not none
            category = transaction.category
            if transaction.category is not None:
                category = transaction.category

            #Capitalizes location if not none
            location = transaction.location
            if transaction.location is not None:
                location = transaction.location


            receipt_component = None
            receipt = transaction.receipt
            if receipt is not None and receipt.time is not None:
                hour = receipt.time.hours % 12 or 12
                period = "AM" if receipt.time.hours < 12 else "PM"
                time_component = tk.Label(
                    table._body, text=f"{hour}:{receipt.time.minutes:02} {period}"
                )
            else:
                time_component = tk.Label(table._body, bg="black")

            if receipt is not None:
                receipt_component = tk.Button(
                    table._body,
                    text="View Receipt",
                    cursor="hand2", **RECEIPT_VIEW_BUTTON_COLORS,
                    command=lambda receipt=receipt, purchase=transaction_row.purchase:
                    self._show_receipt(receipt, purchase),
                )
            elif self._matching_unassigned_receipts(transaction_row.purchase):
                receipt_component = tk.Button(
                    table._body, text="+", width=2, cursor="hand2", **RECEIPT_ADD_BUTTON_COLORS,
                    command=lambda purchase=transaction_row.purchase: self._show_receipt_picker(purchase),
                )
            else:
                receipt_component = tk.Label(table._body, bg="black")

            description = table.create_enum_cell(
                i, Descriptions, "description",
                lambda name, transaction=transaction: DescriptionManager.create(name, transaction.category),
                self._set_transaction_description, value=transaction.description,
                locked=transaction.description_is_autocompleted,
                empty_text=transaction.purchase_title or "", fit_column=5,
                choices=lambda transaction=transaction: DescriptionManager.choices(transaction.category),
                all_choices=lambda transaction=transaction: DescriptionManager.choices(transaction.category, include_hidden=True),
            )
            self._transaction_description_cells[i] = description
            hidden = tk.BooleanVar(master=table, value=transaction_row.purchase.hidden)
            self._hidden_variables[i] = hidden
            hidden_checkbox = tk.Checkbutton(table._body, variable=hidden, text="", cursor="hand2",
                                             command=lambda index=i, variable=hidden:
                                             self._set_transaction_hidden(index, variable.get()))
            def color_hidden(*args, checkbox=hidden_checkbox, variable=hidden):
                background, foreground = ("#FF0000", "#111111") if variable.get() else ("#008000", "#FFFFFF")
                checkbox.configure(bg=background, fg=foreground, activebackground=background,
                                   activeforeground=foreground, selectcolor=background)
            hidden.trace_add("write", color_hidden)
            color_hidden()
            table.add_row((transaction.date,
                           time_component,
                           None if remains_editable("location") else location,
                           transaction.amount,
                           None if remains_editable("category") else category,
                           description,
                           None if remains_editable("is_essential") else transaction.is_essential,
                           receipt_component,
                           hidden_checkbox))
            if remains_editable("location"):
                table.refresh_enum_cell(table._components[i][2], Locations, location)
            if remains_editable("category"):
                table.refresh_enum_cell(table._components[i][4], Categories, category)
            if remains_editable("is_essential"):
                table.refresh_is_essential_cell(i, 6, transaction.is_essential, transaction.is_essential_is_autocompleted)
        footer = self._review_footer = tk.Frame(self._root, bg="#F4F6F9")
        footer.pack(side="bottom", fill="x", padx=20, pady=(12, 18))
        self._finalize_button = tk.Button(footer,
                  text = "Finalize",
                  command = self._finalize,
                  borderwidth=2,
                  relief="flat", bg="#2563EB", fg="white", activebackground="#1D4ED8", activeforeground="white",
                  font=(family, size, "bold"), cursor="hand2",
                  height = 2)
        self._finalize_button.pack(fill="x")
        table.pack(fill="both", expand=True, padx=20)

    def _refresh_transaction_table(self) -> None:
        if self._transactions is None or not self._root.winfo_exists():
            return
        widths = []
        scroll_position = 0.0
        horizontal_position = 0.0
        if self._transaction_table is not None and self._transaction_table.winfo_exists():
            widths = self._transaction_table._column_widths.copy()
            scroll_position = self._transaction_table._canvas.yview()[0]
            horizontal_position = self._transaction_table._canvas.xview()[0]
            self._transaction_table.destroy()
        if self._finalize_button is not None and self._finalize_button.winfo_exists():
            self._finalize_button.destroy()
        self._setup_components()
        for index, width in enumerate(widths):
            self._transaction_table._column_widths[index] = max(width, self._transaction_table._column_widths[index])
        self._transaction_table._resize_content()
        self._transaction_table.update_idletasks()
        self._transaction_table._canvas.yview_moveto(scroll_position)
        self._transaction_table._scroll_horizontal("moveto", horizontal_position)

    def _receipt_changed(self, receipt: Receipt) -> None:
        if self._transactions is not None and any(purchase.receipt is receipt for purchase in self._transactions):
            self._refresh_transaction_table()

    def _set_transaction_hidden(self, row_index: int, hidden: bool) -> None:
        purchase = self._transaction_rows[row_index].purchase
        purchase.hidden = hidden
        for index, row in enumerate(self._transaction_rows):
            if row.purchase is purchase:
                row.transaction.hidden = hidden
                self._hidden_variables[index].set(hidden)

    def _unassigned_receipts(self) -> list[Receipt]:
        assigned = {id(purchase.receipt) for purchase in self._transactions or [] if purchase.receipt is not None}
        return [receipt for receipt in self._receipts if id(receipt) not in assigned]

    def _matching_unassigned_receipts(self, purchase: FinancialTransaction) -> list[Receipt]:
        """Compare monetary totals in cents, allowing negative purchase amounts."""
        amount_cents = round(abs(purchase.amount) * 100)
        return [receipt for receipt in self._unassigned_receipts()
                if round(abs(receipt.total) * 100) == amount_cents]

    def _show_receipt_picker(self, purchase: FinancialTransaction) -> tk.Toplevel | None:
        remaining = self._matching_unassigned_receipts(purchase)
        if purchase.receipt is not None or not remaining:
            return None
        window = tk.Toplevel(self._root)
        window.title("Attach a Receipt")
        window.transient(self._root.winfo_toplevel())
        window.geometry("750x550")
        window.minsize(600, 350)
        background, ink, muted = "#F4F6F9", "#172B4D", "#64748B"
        window.configure(bg=background)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)
        default_font = font.nametofont("TkDefaultFont", root=window).actual()
        family, size = default_font["family"], default_font["size"]
        heading = tk.Frame(window, bg=background)
        heading.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 16))
        heading.columnconfigure(0, weight=1)
        tk.Label(heading, text="Unassigned Receipts", bg=background, fg=ink,
                 font=(family, size + 7, "bold"), anchor="w").grid(row=0, column=0, sticky="w")
        tk.Label(heading, text=f"{len(remaining)} matching", bg="#E5EFFB", fg="#234E78",
                 font=(family, size, "bold"), padx=10, pady=5).grid(row=0, column=1, sticky="e")
        tk.Label(heading, text="Only matching totals are listed. Preview a receipt, then attach it to this purchase.", bg=background,
                 fg=muted, anchor="w").grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 12))
        context = tk.Frame(heading, bg="white", highlightthickness=1, highlightbackground="#DDE4EC", padx=12, pady=10)
        context.grid(row=2, column=0, columnspan=2, sticky="ew")
        tk.Label(context, text="PURCHASE", bg="white", fg=muted,
                 font=(family, max(size - 1, 8), "bold"), anchor="w").pack(fill="x")
        tk.Label(context, text=f"{purchase.date}  |  {OptionManager.display(purchase.location) or 'Unknown location'}  |  {purchase.amount}",
                 bg="white", fg=ink, wraplength=500, justify="left", anchor="w",
                 font=(family, size, "bold")).pack(fill="x", pady=(3, 0))
        table = TkTable(window, stretch_column=0, columns=[
            TableColumn("Receipt", tk.Widget),
        ])
        table.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 18))
        table.configure(bg=background)
        table._head.grid_remove()
        table._canvas.configure(bg=background)
        table._body.configure(bg=background)
        for receipt in sorted(remaining, key=lambda receipt: (receipt.date.year, receipt.date.month,
                                                             receipt.date.day, str(receipt.location), receipt.total)):
            card = tk.Frame(table, bg="white", highlightthickness=1, highlightbackground="#DDE4EC")
            card.columnconfigure(1, weight=1)
            colors = get_location_colors(_determine_receipt_location(receipt.location))
            accent = tk.Frame(card, bg=colors[0] if colors else "#CBD5E1", width=4)
            accent.grid(row=0, column=0, sticky="ns", padx=(0, 12))
            metadata = tk.Frame(card, bg="white", pady=14)
            metadata.grid(row=0, column=1, sticky="ew")
            metadata.columnconfigure(0, weight=1)
            time_text = "Not provided"
            if receipt.time is not None:
                time = receipt.time
                time_text = f"{time.hours % 12 or 12}:{time.minutes:02}:{time.seconds:02} {'AM' if time.hours < 12 else 'PM'}"
            TkOptionLabel(metadata, _determine_receipt_location(receipt.location) or receipt.location,
                          prefix="Location: ", bg="white", fg=ink, wraplength=240,
                     font=(family, size + 1, "bold"), anchor="w", justify="left").grid(row=0, column=0, sticky="w")
            tk.Label(metadata, text=f"Total: {DollarAmount(receipt.total)}", bg="white", fg=ink,
                     font=(family, size + 2, "bold")).grid(row=0, column=1, sticky="e", padx=(12, 8))
            tk.Label(metadata, text=f"Date: {receipt.date}", bg="white", fg=muted,
                     anchor="w").grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 0))
            tk.Label(metadata, text=f"Time: {time_text}", bg="white", fg=muted,
                     anchor="w").grid(row=2, column=0, columnspan=2, sticky="w")
            view = tk.Button(card, text="View", bg="#2563EB", fg="white", activebackground="#1D4ED8",
                             activeforeground="white", relief="flat", borderwidth=0, padx=18, pady=9,
                             font=(family, size, "bold"), cursor="hand2",
                             command=lambda receipt=receipt: self._show_receipt_attachment_preview(receipt, purchase, window))
            view.grid(row=0, column=2, padx=(12, 16))
            table.add_row((card,))
            card.grid_configure(pady=(0, 10), padx=(0, 4))
            for widget in (accent, metadata, view, *metadata.winfo_children()):
                table._bind_mousewheel(widget)
        window.protocol("WM_DELETE_WINDOW", window.destroy)
        window.bind("<Escape>", lambda event: window.destroy())
        return window

    def _show_receipt_attachment_preview(self, receipt: Receipt, purchase: FinancialTransaction,
                                         picker: tk.Toplevel) -> tk.Toplevel:
        window = tk.Toplevel(picker)
        window.title(f"Receipt Preview - {receipt.location} - {receipt.date}")
        window.transient(picker)
        window.geometry("850x600")
        window.minsize(600, 350)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)
        self._add_receipt_metadata(window, receipt)
        table = TkTable(window, review_style=True, stretch_column=0, columns=[
            TableColumn(text="Item", data_type=tk.Widget),
            TableColumn(text="Quantity", data_type=str),
            TableColumn(text="Unit Price", data_type=DollarAmount),
        ])
        table.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        for item in receipt.items:
            if item.link:
                name = TkLink(table._body, text=item.name, url=item.link,
                              wraplength=400, anchor="w", justify="left")
            else:
                name = tk.Label(table._body, text=item.name, wraplength=400,
                                anchor="w", justify="left")
            table.add_row((name, f"{item.quantity:g}", DollarAmount(-item.price)))
        if not receipt.items:
            tk.Label(table._body, text="No items listed.").grid(
                row=0, column=0, columnspan=len(table.columns), sticky="w", padx=8, pady=8
            )
        default_font = font.nametofont("TkDefaultFont", root=window).actual()
        tk.Button(window, text="Attach Receipt to Purchase", height=2, borderwidth=2, relief="flat",
                  bg="#2563EB", fg="white", activebackground="#1D4ED8", activeforeground="white",
                  font=(default_font["family"], default_font["size"], "bold"), cursor="hand2",
                  command=lambda: self._attach_receipt_to_purchase(purchase, receipt, picker)).grid(
            row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        window.protocol("WM_DELETE_WINDOW", window.destroy)
        window.bind("<Escape>", lambda event: window.destroy())
        return window

    def _attach_receipt_to_purchase(self, purchase: FinancialTransaction, receipt: Receipt,
                                    picker: tk.Toplevel) -> None:
        if purchase not in (self._transactions or []) or purchase.receipt is not None:
            messagebox.showwarning("Cannot attach receipt", "This purchase is no longer available for a receipt.",
                                   parent=picker)
            return
        if receipt not in self._unassigned_receipts():
            messagebox.showwarning("Cannot attach receipt", "This receipt has already been attached to another purchase.",
                                   parent=picker)
            return
        if receipt not in self._matching_unassigned_receipts(purchase):
            messagebox.showwarning("Cannot attach receipt", "The receipt total must match the purchase amount.",
                                   parent=picker)
            return
        purchase.receipt = receipt
        self._refresh_transaction_table()
        picker.destroy()

    def _set_transaction_location(self, row_index: int, location: Locations) -> None:
        row = self._transaction_rows[row_index]
        if row.transaction.is_field_locked("location"):
            return
        row.purchase.location = location
        row.transaction.location = location
        if location == Locations.DISCOVER:
            statement_row = {CreditCardHeaders.DESCRIPTION: row.purchase.purchase_title or ""}
            if row.purchase.source == Locations.DISCOVER:
                statement_row[CreditCardHeaders.CATEGORY] = CreditCardCategories.PAYMENTS_AND_CREDITS
            _set_transaction_category(statement_row, row.purchase)
            _set_transaction_is_essential(statement_row, row.purchase)
        if row.items is not None or location == Locations.DISCOVER:
            self._refresh_transaction_table()

    def _set_transaction_category(self, row_index: int, category: Categories) -> None:
        row = self._transaction_rows[row_index]
        transaction = row.transaction
        if transaction.is_field_locked("category"):
            return
        transaction.category = category
        if (transaction.description is not None and not transaction.description_is_autocompleted
                and not DescriptionManager.is_available(transaction.description, category)):
            transaction.description = None
        if row.items is not None:
            if row.purchase.category is not None:
                row.purchase.category = category
                items = row.purchase.receipt.items
            else:
                items = row.items
            for item in items:
                item.autocomplete_field("category", category)
                if (item.description is not None and not item.description_is_autocompleted
                        and not DescriptionManager.is_available(item.description, category)):
                    item.description = None
            self._refresh_transaction_table()
            return
        self._transaction_table.refresh_enum_cell(
            self._transaction_description_cells[row_index], Descriptions,
            transaction.description, transaction.purchase_title or "",
            locked=transaction.description_is_autocompleted
        )
        self._transaction_table.refresh_is_essential_cell(
            row_index, 6, transaction.is_essential, transaction.is_essential_is_autocompleted
        )

    def _set_transaction_description(self, row_index: int, description: StrEnum | str) -> None:
        row = self._transaction_rows[row_index]
        transaction = row.transaction
        if not transaction.description_is_autocompleted:
            transaction.description = description
            if row.items is not None:
                if row.purchase.description is not None:
                    row.purchase.description = description
                    items = row.purchase.receipt.items
                else:
                    items = row.items
                for item in items:
                    item.autocomplete_field("description", description)
                self._refresh_transaction_table()

    def _set_transaction_is_essential(self, row_index: int, is_essential: IsEssential) -> None:
        row = self._transaction_rows[row_index]
        transaction = row.transaction
        if transaction.is_field_locked("is_essential"):
            self._transaction_table.refresh_is_essential_cell(row_index, 6, transaction.is_essential, True)
            return
        transaction.is_essential = is_essential
        if row.items is not None:
            if row.purchase.is_essential is not None:
                row.purchase.is_essential = is_essential
                items = row.purchase.receipt.items
            else:
                items = row.items
            for item in items:
                item.autocomplete_field("is_essential", transaction.is_essential)
            self._refresh_transaction_table()
            return
        essential = self._transaction_table._components[row_index][6]
        if isinstance(essential, ttk.Combobox):
            essential.set(str(transaction.is_essential))

    @staticmethod
    def _add_receipt_metadata(window: tk.Toplevel, receipt: Receipt) -> None:
        metadata = tk.Frame(window)
        metadata.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        default_font = font.nametofont("TkDefaultFont", root=window).actual()
        metadata_font = (default_font["family"], default_font["size"] + 2, "bold")
        amounts_font = (default_font["family"], default_font["size"] + 2, "normal")
        time_text = "Not provided"
        if receipt.time is not None:
            hour = receipt.time.hours % 12 or 12
            period = "AM" if receipt.time.hours < 12 else "PM"
            time_text = f"{hour}:{receipt.time.minutes:02}:{receipt.time.seconds:02} {period}"
        for i, text in enumerate((f"Date: {receipt.date}", f"Location: {receipt.location}",
                                  f"Time: {time_text}")):
            metadata.columnconfigure(i, weight=1, uniform="receipt_metadata")
            if i == 1:
                label = TkOptionLabel(metadata, _determine_receipt_location(receipt.location) or receipt.location,
                                      prefix="Location: ", colorize=True, anchor="center", padx=8, pady=6,
                                      font=metadata_font, borderwidth=2, relief="solid")
                colors = get_location_colors(_determine_receipt_location(receipt.location))
                if colors is not None:
                    label.configure(bg=colors[0], fg=colors[1])
            else:
                label = tk.Label(metadata, text=text, anchor="center", padx=8, pady=6,
                                 font=metadata_font, borderwidth=2, relief="solid")
            label.grid(row=0, column=i, sticky="ew", padx=4)

        for row, text in enumerate((f"Subtotal: {DollarAmount(receipt.subtotal)}",
                                     f"Tax: {DollarAmount(receipt.taxes)}"), start=1):
            tk.Label(metadata, text=text, font=amounts_font, pady=3).grid(
                row=row, column=0, columnspan=3, sticky="ew", padx=4,
                pady=(8, 0) if row == 1 else 0
            )
        ttk.Separator(metadata, orient="horizontal").grid(
            row=3, column=0, columnspan=3, sticky="ew", padx=4, pady=3
        )
        tk.Label(metadata, text=f"Total: {DollarAmount(receipt.total)}",
                 font=metadata_font, pady=3).grid(
            row=4, column=0, columnspan=3, sticky="ew", padx=4
        )

    def _show_receipt(self, receipt: Receipt,
                      transaction: FinancialTransaction | None = None) -> tk.Toplevel:
        inherited_category = transaction.category if transaction is not None else None
        inherited_essential = transaction.is_essential if transaction is not None else None
        inherited_description = transaction.description if transaction is not None else None
        draft_items = [(item, copy(item)) for item in receipt.items]
        for original, item in draft_items:
            for field, value in (("category", inherited_category), ("description", inherited_description),
                                 ("is_essential", inherited_essential)):
                if value is not None:
                    item.autocomplete_field(field, value)
        view_only = all(
            getattr(item, field) is not None and str(getattr(item, field)).strip()
            for original, item in draft_items for field in ("category", "description", "is_essential")
        )
        window = tk.Toplevel(self._root)
        window.title(f"Receipt - {receipt.location} - {receipt.date}")
        window.transient(self._root.winfo_toplevel())
        window.geometry("1100x550")
        window.minsize(1000, 350)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)
        self._add_receipt_metadata(window, receipt)

        table = TkTable(window, review_style=True, stretch_column=4, columns=[
            TableColumn(text="Item", data_type=tk.Widget),
            TableColumn(text="Quantity", data_type=str),
            TableColumn(text="Cost", data_type=DollarAmount),
            TableColumn(text="Category", data_type=tk.Widget),
            TableColumn(text="Description", data_type=tk.Widget),
            TableColumn(text="Is Essential?", data_type=tk.Widget),
        ])
        table.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        for row_index, (original, item) in enumerate(draft_items):
            if item.link:
                name = TkLink(table._body, text=item.name, url=item.link,
                              wraplength=240, anchor="w", justify="left")
            else:
                name = tk.Label(table._body, text=item.name, wraplength=240,
                                anchor="w", justify="left")

            essential_value = tk.BooleanVar(master=table)
            essential = tk.Checkbutton(table._body, variable=essential_value)

            def refresh_essential(item=item, variable=essential_value, checkbox=essential):
                selected = item.is_essential == IsEssential.ESSENTIAL
                variable.set(selected)
                color = "green" if selected else "red"
                locked = view_only or item.is_field_locked("is_essential")
                checkbox.configure(bg=color, activebackground=color, selectcolor=color,
                                   state="disabled" if locked else "normal")

            def toggle_essential(item=item, variable=essential_value, refresh=refresh_essential):
                if view_only or item.is_field_locked("is_essential"):
                    refresh()
                    return
                item.is_essential = IsEssential.ESSENTIAL if variable.get() else IsEssential.NON_ESSENTIAL
                refresh()

            essential.configure(command=toggle_essential)
            refresh_essential()

            def set_item_description(row_index, value, item=item):
                if not view_only and not item.is_field_locked("description"):
                    item.description = value

            description = table.create_enum_cell(
                row_index, Descriptions, "description",
                lambda name, item=item: DescriptionManager.create(name, item.category),
                set_item_description,
                value=item.description,
                locked=view_only or item.is_field_locked("description"),
                empty_text=item.name, fit_column=4,
                choices=lambda item=item: DescriptionManager.choices(item.category),
                all_choices=lambda item=item: DescriptionManager.choices(item.category, include_hidden=True),
            )

            def set_item_category(row_index, value, item=item, description=description,
                                  refresh=refresh_essential):
                if view_only or item.is_field_locked("category"):
                    return
                item.category = value
                if (not item.is_field_locked("description") and item.description is not None
                        and not DescriptionManager.is_available(item.description, value)):
                    item.description = None
                table.refresh_enum_cell(
                    description, Descriptions, item.description, item.name,
                    locked=item.is_field_locked("description")
                )
                refresh()

            category = table.create_enum_cell(
                row_index, Categories, "category", CategoryManager.create,
                set_item_category,
                value=item.category, locked=view_only or item.is_field_locked("category")
            )

            table.add_row((name, f"{item.quantity:g}", DollarAmount(-item.cost), category, description, essential))

        if not receipt.items:
            tk.Label(table._body, text="No items listed.").grid(
                row=0, column=0, columnspan=len(table.columns), sticky="w", padx=8, pady=8
            )

        def save_receipt():
            for original, draft in draft_items:
                original.copy_fields_from(draft, ("category", "description", "is_essential"))
            self._receipt_changed(receipt)
            window.destroy()

        if not view_only:
            actions = tk.Frame(window)
            actions.grid(row=2, column=0, sticky="ew")
            tk.Button(actions, text="Save", command=save_receipt, borderwidth=2,
                      relief="ridge", height=2).pack(fill="x")
        window.protocol("WM_DELETE_WINDOW", window.destroy)
        window.bind("<Escape>", lambda event: window.destroy())
        return window

    def _show_incomplete_transactions(self, incomplete_rows) -> tk.Toplevel:
        previous = getattr(self, "_incomplete_window", None)
        if previous is not None and previous.winfo_exists():
            previous.destroy()
        window = self._incomplete_window = tk.Toplevel(self._root)
        window.title("Incomplete transactions")
        window.transient(self._root.winfo_toplevel())
        window.configure(bg="#F4F6F9")
        window.geometry(f"{min(1000, window.winfo_screenwidth() - 80)}x{min(560, window.winfo_screenheight() - 100)}")
        window.minsize(540, 350)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)
        default = font.nametofont("TkDefaultFont", root=window).actual()
        heading = tk.Frame(window, bg="#F4F6F9")
        heading.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 14))
        heading.columnconfigure(0, weight=1)
        tk.Label(heading, text="A few fields still need attention", bg="#F4F6F9", fg="#172B4D",
                 anchor="w", font=(default["family"], default["size"] + 5, "bold")).grid(row=0, column=0, sticky="w")
        count = len(incomplete_rows)
        tk.Label(heading, text=f"{count} incomplete {'transaction' if count == 1 else 'transactions'}",
                 bg="#FEF3C7", fg="#92400E", padx=10, pady=5).grid(row=0, column=1, sticky="e", padx=(12, 0))
        tk.Label(heading, text="Fill in the fields listed below, then click Finalize again.",
                 bg="#F4F6F9", fg="#64748B", anchor="w").grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        table = TkTable(window, columns=[TableColumn("Row", str), TableColumn("Transaction", tk.Widget),
                                        TableColumn("Missing fields", tk.Widget)], review_style=True, stretch_column=2)
        table.grid(row=1, column=0, sticky="nsew", padx=20)
        for row_number, transaction, missing in incomplete_rows:
            info = (f"{transaction.date}  |  {OptionManager.display(transaction.location) or 'Unknown location'}"
                    f"  |  {transaction.amount}")
            if transaction.purchase_title:
                info += f"\n{transaction.purchase_title}"
            purchase = tk.Label(table._body, text=info, anchor="w", justify="left", wraplength=350,
                                bg="white", fg="#334155", padx=12, pady=10)
            fields = tk.Label(table._body, text=", ".join(missing), anchor="w", justify="left", wraplength=320,
                              bg="#FFF7ED", fg="#9A3412", padx=12, pady=10,
                              font=(default["family"], default["size"], "bold"))
            table.add_row((str(row_number), purchase, fields))
            fields.configure(bg="#FFF7ED", fg="#9A3412", font=(default["family"], default["size"], "bold"))
        document_button(window, "Back to Review", window.destroy, primary=True).grid(
            row=2, column=0, sticky="ew", padx=20, pady=16)
        window.bind("<Escape>", lambda event: window.destroy())
        return window

    def _finalize(self) -> None:
        if self._outputs_saved:
            self._finish_review()
            return
        required_fields = (("location", "Location"), ("category", "Category"),
                           ("description", "Description"), ("is_essential", "Is Essential?"))
        incomplete_rows = []
        for row_number, row in enumerate(self._transaction_rows, start=1):
            transaction = row.transaction
            missing = [label for field, label in required_fields
                       if (value := getattr(transaction, field)) is None or not str(value).strip()]
            if missing:
                incomplete_rows.append((row_number, transaction, missing))
        if incomplete_rows:
            self._show_incomplete_transactions(incomplete_rows)
            return

        previous = getattr(self, "_incomplete_window", None)
        if previous is not None and previous.winfo_exists():
            previous.destroy()

        confirmed = messagebox.askyesno(
            "Confirm",
            "Are you sure you want to finalize these transactions?",
            parent=self._root,
        )

        if confirmed:
            try:
                month_directory = ReceiptBackupManager.review_directory()
                overwrite = False
                if month_directory.exists():
                    overwrite = messagebox.askyesno(
                        "Replace existing monthly review?",
                        f"The review folder already exists:\n{month_directory}\n\n"
                        "Replace Expense Review.pdf and files with matching names in Supporting Documents "
                        "(receipts, Discover statements, and the bank statement)?",
                        parent=self._root, default="no")
                    if not overwrite:
                        return
                excluded_files = ReceiptGroupManager.hidden_receipt_files(self._transaction_rows)
                ReceiptBackupManager.copy_supporting_documents(
                    Paths.RECEIPTS, Paths.ASSETS_PDFS, excluded_file_names=excluded_files,
                    destination=month_directory / ReceiptBackupManager.SUPPORTING_DOCUMENTS_FOLDER,
                    overwrite=overwrite)
            except OSError as error:
                messagebox.showerror(
                    "Supporting documents backup failed",
                    f"Could not copy supporting documents to PrimaryBckp.\n\n{error}\n\n"
                    "Resolve the problem and click Finalize again.",
                    parent=self._root,
                )
                return
            try:
                ExpenseReviewReport.generate(month_directory / "Expense Review.pdf",
                                             self._transaction_rows, self._receipts, overwrite=overwrite)
            except (OSError, ReportGenerationError) as error:
                messagebox.showerror(
                    "Expense review PDF failed",
                    f"Could not save Expense Review.pdf.\n\n{error}\n\n"
                    "Resolve the problem and click Finalize again.",
                    parent=self._root,
                )
                return
            self._outputs_saved = True
            self._finish_review()

    def _finish_review(self) -> None:
        try:
            self._review_files.cleanup()
        except OSError as error:
            messagebox.showerror(
                "Working file cleanup incomplete",
                f"Your expense report and supporting documents have been saved.\n\n{error}\n\n"
                "Close any open working files, then click Retry Cleanup. Saved documents will not be regenerated.",
                parent=self._root,
            )
            self._finalize_button.configure(text="Retry Cleanup")
            return
        self._parent_next_method()
