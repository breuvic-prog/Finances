"""Imports"""
import math

from classes.custom_tk_components.tk_table_class import TkTable
from classes.financial_transaction_class import FinancialTransaction
from classes.general.dollar_amount_class import DollarAmount
from classes.grocery_item import GroceryItem
from classes.managers.date_manager import DateManager
from classes.managers.file_manager import FileManager
from classes.managers.file_managers.csv_manager import CsvManager
from classes.managers.file_managers.json_manager import JsonManager
from classes.managers.string_manager import StringManager
from classes.pages.leaf_page_class import LeafPage
import tkinter as tk
from collections.abc import Callable
from classes.general.date_class import Date
from classes.receipt_class import Receipt
from classes.table_column_class import TableColumn
from enums.files_enum import Files
from enums.finances.categories_enum import Categories
from enums.finances.descriptions_enum import Descriptions
from enums.finances.is_essential_enum import IsEssential
from enums.locations_enum import Locations
from enums.paths_enum import Paths
from classes.general.time_class import Time

"""Constants"""
GENERAL = "general"
ITEMS = "items"
SUBTOTAL = "subtotal"
TAX = "tax"
TOTAL = "total"
NAME = "name"
PRICE = "price"
LINK = "link"
TRANS_DATE = "Trans. Date"
DESCRIPTION = "Description"
AMOUNT = "Amount"

location_keywords = {
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

        time = Time(hours = int(time_parts[0]),
                    minutes = int(time_parts[1]),
                    seconds = int(time_parts[2]))


    return location, date, time
def _determine_transaction_date(row:dict) -> Date:
    #Splits the original date string
    date_parts = StringManager.split(string = row[TRANS_DATE],
                                     separator = "/")

    return Date(month = int(date_parts[0]),
                    day = int(date_parts[1]),
                    year = int(date_parts[2]))
def _determine_transaction_location(row:dict) -> Locations|None:
    #The final location
    location = None

    #Finds and lowercases the description
    lowercase_description = StringManager.Lowercase(row[DESCRIPTION])



    #Checks for specific keywords first
    for keyword in location_keywords:
        if keyword in lowercase_description:
            return location_keywords[keyword]

    #Checks if a whole location is included
    for location in list(Locations):
        #Checks for exact matches
        if location in lowercase_description:
            return location

    return location
def _determine_transaction_amount(row: dict,
                                  invert_amount: bool) -> DollarAmount:
    # Gets the amount
    amount = float(row[AMOUNT])

    # Inverts if need be
    if invert_amount:
        amount = -amount

    return DollarAmount(amount)
def _set_transaction_description(row: dict,
                                 existing_object:FinancialTransaction) -> None:
    #Final description
    if 1 == 2:
        pass
    else:
        existing_object.description = row[DESCRIPTION]

def _set_transaction_category(row: dict,
                              existing_object:FinancialTransaction) -> None:
    category = None

def _set_transaction_is_essential(row: dict,
                                  existing_object:FinancialTransaction) -> None:
    #Checks if the transaction is essential or not by default
    if existing_object.location == Locations.VENDING_MACHINE:
        existing_object.is_essential = IsEssential.NON_ESSENTIAL

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
    #Final checking account transactions
    checking_account_transactions = []

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


class FinalReviewPage(LeafPage):
    def __init__(self, parent_root: tk.Tk | tk.Frame,
                 parent_next_method: Callable):
        #Attributes
        self._receipts = _import_receipts()
        self._transactions:list[FinancialTransaction] = _import_transactions()

        super().__init__(parent_root, parent_next_method)



    def _setup_components(self) -> None:
        #Creates the table component
        table = TkTable(self._root,
                        columns = [TableColumn(text = "Date",
                                               data_type = Date),
                                   TableColumn(text = "Location",
                                               data_type = str),
                                   TableColumn(text = "Amount",
                                               data_type = DollarAmount),
                                   TableColumn(text = "Description",
                                               data_type = str),
                                   TableColumn(text = "Category",
                                               data_type = str),
                                   TableColumn(text = "Is Essential?",
                                               data_type = IsEssential)])
        table.pack(fill="both", expand=True)

        #Goes through all the transactions
        for i, transaction in enumerate(self._transactions):
            #Capitalizes location if not none
            location = transaction.location
            if transaction.location is not None:
                location = StringManager.Capitalize(transaction.location)

            # Capitalizes category if not none
            category = transaction.category
            if transaction.category is not None:
                category = StringManager.Capitalize(transaction.category)


            table.add_row((transaction.date,
                           location,
                           transaction.amount,
                           transaction.description,
                           category,
                           transaction.is_essential))


    def _finalize(self) -> None:
        # Calls parent next method
        self._parent_next_method()
