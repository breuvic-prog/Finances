"""Imports"""

from classes.custom_tk_components.tk_table_class import TkTable
from classes.financial_transaction_class import FinancialTransaction
from classes.general.dollar_amount_class import DollarAmount
from classes.grocery_item import GroceryItem
from classes.managers.date_manager import DateManager
from classes.managers.file_manager import FileManager
from classes.managers.file_managers.csv_manager import CsvManager
from classes.managers.file_managers.json_manager import JsonManager
from classes.managers.file_managers.pdf_manager import PdfManager
from classes.managers.string_manager import StringManager
from classes.pages.leaf_page_class import LeafPage
import tkinter as tk
import re
from collections.abc import Callable
from datetime import datetime
from classes.general.date_class import Date
from classes.receipt_class import Receipt
from classes.table_column_class import TableColumn
from enums.files_enum import Files
from enums.finances.categories_enum import Categories
from enums.finances.descriptions_enum import Descriptions
from enums.finances.credit_card.credit_card_categories_enum import CreditCardCategories
from enums.finances.credit_card.credit_card_headers_enum import CreditCardHeaders
from enums.finances.is_essential_enum import IsEssential
from enums.finances.locations_enum import Locations
from enums.paths_enum import Paths
from classes.general.time_class import Time
from tkinter import messagebox
from tkinter.scrolledtext import ScrolledText

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


location_keywords = {
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
    if len(parts) == 3:
        time_parts = StringManager.split(string = parts[2],
                                         separator = "-")
        print(time_parts)

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

def _determine_transaction_location(row:dict) -> Locations|None:
    if _is_walmart_payroll(row):
        return Locations.WALMART

    #Finds and lowercases the description
    lowercase_description = StringManager.Lowercase(row[CreditCardHeaders.DESCRIPTION])

    #Checks for specific keywords first
    for keyword in location_keywords:
        if keyword in lowercase_description:
            return location_keywords[keyword]

    #Checks if a whole location is included
    for location in list(Locations):
        #Checks for exact matches
        if StringManager.Lowercase(location) in lowercase_description:
            return location

    return None
def _determine_transaction_amount(row: dict,
                                  invert_amount: bool) -> DollarAmount:
    # Gets the amount
    amount = float(row[CreditCardHeaders.AMOUNT])

    # Inverts if need be
    if invert_amount:
        amount = -amount

    return DollarAmount(amount)
def _set_transaction_description(row: dict,
                                 existing_object:FinancialTransaction) -> None:
    #Final description
    if existing_object.location == Locations.FIRST_SECURITY_BANK:
        existing_object.description = Descriptions.CAR_PAYMENT
    else:
        existing_object.description = row[CreditCardHeaders.DESCRIPTION]

def _set_transaction_category(row: dict,
                              existing_object:FinancialTransaction) -> None:
    if "deposit by internet" in StringManager.Lowercase(row[CreditCardHeaders.DESCRIPTION]):
        existing_object.category = Categories.NOT_INCLUDED
    elif _is_walmart_payroll(row):
        existing_object.category = Categories.PAYCHECK
    elif existing_object.location == Locations.FIRST_SECURITY_BANK:
        existing_object.category = Categories.CAR
    elif existing_object.location in (
        Locations.CULVERS,
        Locations.PRAIRIE_CINEMA,
        Locations.VENDING_MACHINE,
    ):
        existing_object.category = Categories.DISCRETIONARY_SPENDING

def _set_transaction_is_essential(row: dict,
                                  existing_object:FinancialTransaction) -> None:
    #Checks if the transaction is essential or not by default
    if "deposit by internet" in StringManager.Lowercase(row[CreditCardHeaders.DESCRIPTION]):
        existing_object.is_essential = IsEssential.NOT_INCLUDED
    elif "misc. debit" in StringManager.Lowercase(row[CreditCardHeaders.DESCRIPTION]):
        existing_object.is_essential = IsEssential.ESSENTIAL
    elif _is_walmart_payroll(row):
        existing_object.is_essential = IsEssential.ESSENTIAL
    elif existing_object.location in (
        Locations.VENDING_MACHINE,
        Locations.CULVERS,
        Locations.PRAIRIE_CINEMA,
    ):
        existing_object.is_essential = IsEssential.NON_ESSENTIAL
    elif existing_object.category == Categories.CAR:
        existing_object.is_essential = IsEssential.ESSENTIAL
    elif (row[CreditCardHeaders.CATEGORY] == CreditCardCategories.PAYMENTS_AND_CREDITS or
          row[CreditCardHeaders.CATEGORY] == CreditCardCategories.AWARDS_AND_REBATE_CREDITS):
        existing_object.location = Locations.NOT_INCLUDED
        existing_object.category = Categories.NOT_INCLUDED
        existing_object.is_essential = IsEssential.NOT_INCLUDED



def _create_financial_transaction_object(row: dict,
                                         invert_amount:bool = False) -> FinancialTransaction:
    #Creates the initial object
    financial_transaction = FinancialTransaction(date = _determine_transaction_date(row),
                                                 amount = _determine_transaction_amount(row = row,
                                                                                        invert_amount = invert_amount),
                                                 location = _determine_transaction_location(row))

    #Sets the description
    _set_transaction_description(row = row,
                                 existing_object = financial_transaction)

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

            #Adds the object
            grocery_items.append(GroceryItem(name = grocery_item_dict[NAME],
                                             price = grocery_item_dict[PRICE],
                                             link = link))

        #Creates the receipt object
        receipts.append(Receipt(location = location,
                                date = date,
                                time = time,
                                 subtotal = data[GENERAL][SUBTOTAL],
                                taxes = data[GENERAL][TAX],
                                total = data[GENERAL][TOTAL],
                                items = grocery_items))

    return receipts
def _import_credit_card_transactions() -> list[FinancialTransaction]:
    #Final credit card activity
    credit_card_transactions = []

    #Gets the previous month
    previous_month = DateManager.get_current_month() - 1

    #Gets the document data
    documents = [Files.CREDIT_CARD_PREVIOUS_MONTH_STATEMENT_CSV,
                 Files.CREDIT_CARD_PREVIOUS_PREVIOUS_MONTH_STATEMENT_CSV]

    for document_name in documents:
        # Opens the document
        data = CsvManager.open(name = document_name,
                               path = Paths.ASSETS_CSVS)

        # Goes through all the transactions
        for row in data:
            #Creates the object
            credit_card_transactions.append(_create_financial_transaction_object(row = row,
                                                          invert_amount = True))

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

    checking_account_transactions = []
    for row in rows:
        transaction = _create_financial_transaction_object(row=row)
        description = StringManager.Lowercase(row[CreditCardHeaders.DESCRIPTION])
        if re.search(r"\bdiscover\s*,?\s*e[-\s]payments?\b", description):
            transaction.location = Locations.NOT_INCLUDED
            transaction.category = Categories.NOT_INCLUDED
            transaction.is_essential = IsEssential.NOT_INCLUDED
        checking_account_transactions.append(transaction)

    return checking_account_transactions
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
    normalized = re.sub(r"[^a-z0-9]", "", location.lower())
    for candidate in Locations:
        if normalized == re.sub(r"[^a-z0-9]", "", candidate.lower()):
            return candidate
    # Receipt names can use aliases such as Kwik Star instead of Kwik Trip.
    return _determine_transaction_location({CreditCardHeaders.DESCRIPTION: location})


def _assign_receipts(transactions: list[FinancialTransaction], receipts: list[Receipt]) -> None:
    """Attach unique matches by merchant, full date, and total in cents."""
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


def _set_transaction_defaults_from_receipts(transactions: list[FinancialTransaction]) -> None:
    for transaction in transactions:
        receipt = transaction.receipt
        if transaction.amount >= 0 or transaction.category == Categories.NOT_INCLUDED:
            continue
        if receipt is None:
            has_gas = transaction.location == Locations.KWIK_TRIP and transaction.amount < -25
        else:
            has_gas = any(re.search(r"\bgas(?:oline)?\b", item.name, re.IGNORECASE)
                          for item in receipt.items)
        if has_gas:
            transaction.description = Descriptions.GAS
            transaction.category = Categories.CAR
            transaction.is_essential = IsEssential.ESSENTIAL
        elif receipt is not None and transaction.location == Locations.KWIK_TRIP:
            transaction.category = Categories.DISCRETIONARY_SPENDING
            transaction.is_essential = IsEssential.NON_ESSENTIAL


class FinalReviewPage(LeafPage):
    def __init__(self, parent_root: tk.Tk | tk.Frame,
                 parent_next_method: Callable):
        #Attributes
        self._receipts: list[Receipt] = []
        self._transactions: list[FinancialTransaction] | None = None

        super().__init__(parent_root, parent_next_method)
        #TODO:Still need to figure out what to do or if to do anything with payments from credit->debit
        #TODO:Maybe move certain things into one method for determining things where it makes sense, like payments



    def activate(self) -> None:
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

        #Creates the table component
        table = TkTable(self._root,
                        on_location_changed=self._set_transaction_location,
                        on_category_changed=self._set_transaction_category,
                        columns = [TableColumn(text = "Date",
                                               data_type = Date),
                                   TableColumn(text = "Time",
                                               data_type = tk.Widget),
                                   TableColumn(text = "Location",
                                               data_type = Locations),
                                   TableColumn(text = "Amount",
                                               data_type = DollarAmount),
                                   TableColumn(text = "Description",
                                               data_type = str),
                                   TableColumn(text = "Category",
                                               data_type = Categories),
                                   TableColumn(text = "Is Essential?",
                                               data_type = IsEssential),
                                   TableColumn(text = "Receipt",
                                               data_type = tk.Widget)])
        table.pack(fill="both", expand=True)

        #Goes through all the transactions
        for i, transaction in enumerate(self._transactions):
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
                    table, text=f"{hour}:{receipt.time.minutes:02} {period}"
                )
            else:
                time_component = tk.Label(table, bg="black")

            if (
                transaction.location in (
                    Locations.VENDING_MACHINE,
                    Locations.FREEDOM_BANK,
                    Locations.FIRST_SECURITY_BANK,
                )
                or transaction.category in (Categories.PAYCHECK, Categories.NOT_INCLUDED)
            ):
                receipt_component = tk.Label(table, bg="black")
            elif receipt is not None:
                receipt_component = tk.Button(
                    table,
                    text="View Receipt",
                    command=lambda receipt=receipt: self._show_receipt(receipt),
                )

            table.add_row((transaction.date,
                           time_component,
                           location,
                           transaction.amount,
                           transaction.description,
                           category,
                           transaction.is_essential,
                           receipt_component))
        tk.Button(self._root,
                  text = "Finalize",
                  command = self._finalize,
                  borderwidth=2,
                  relief="ridge",
                  height = 2).pack(fill="both", expand=True)

    def _set_transaction_location(self, row_index: int, location: Locations) -> None:
        self._transactions[row_index].location = location

    def _set_transaction_category(self, row_index: int, category: Categories) -> None:
        self._transactions[row_index].category = category

    def _show_receipt(self, receipt: Receipt) -> tk.Toplevel:
        window = tk.Toplevel(self._root)
        window.title(f"Receipt - {receipt.location} - {receipt.date}")
        window.transient(self._root.winfo_toplevel())
        window.geometry("700x500")
        window.minsize(400, 300)

        details = [f"Location: {receipt.location}", f"Date: {receipt.date}"]
        if receipt.time is not None:
            hour = receipt.time.hours % 12 or 12
            period = "AM" if receipt.time.hours < 12 else "PM"
            details.append(
                f"Time: {hour}:{receipt.time.minutes:02}:{receipt.time.seconds:02} {period}"
            )
        details.extend([
            "",
            f"Subtotal: {DollarAmount(receipt.subtotal)}",
            f"Tax: {DollarAmount(receipt.taxes)}",
            f"Total: {DollarAmount(receipt.total)}",
            "",
            "Items:",
        ])
        if not receipt.items:
            details.append("No items listed.")
        for i, item in enumerate(receipt.items, start=1):
            details.extend([f"{i}. {item.name}", f"   Price: {DollarAmount(item.price)}"])
            if item.link:
                details.append(f"   Link: {item.link}")
            details.append("")

        contents = ScrolledText(window, wrap=tk.WORD, font="TkDefaultFont")
        contents.pack(fill="both", expand=True, padx=12, pady=12)
        contents.insert("1.0", "\n".join(details))
        contents.configure(state="disabled")
        tk.Button(window, text="Close", command=window.destroy).pack(
            anchor="e", padx=12, pady=(0, 12)
        )
        window.bind("<Escape>", lambda event: window.destroy())
        return window

    def _finalize(self) -> None:
        #Need to check if everything's been assigned first
        confirmed = messagebox.askyesno(
            "Confirm",
            "Are you sure you want to finalize these transactions?",
            parent=self._root,
        )

        if confirmed:
            self._parent_next_method()
