from dataclasses import dataclass
from copy import copy
from decimal import Decimal, ROUND_HALF_UP

from classes.financial_transaction_class import FinancialTransaction
from classes.general.dollar_amount_class import DollarAmount
from classes.grocery_item import GroceryItem
from enums.finances.is_essential_enum import IsEssential


@dataclass
class ReceiptTransactionRow:
    transaction: FinancialTransaction
    purchase: FinancialTransaction
    items: tuple[GroceryItem, ...] | None = None


class ReceiptGroupManager:
    @staticmethod
    def rows(purchase: FinancialTransaction) -> list[ReceiptTransactionRow]:
        """Derive receipt groups while preserving the original purchase and its locks."""
        receipt = purchase.receipt
        if receipt is None or not receipt.items:
            return [ReceiptTransactionRow(purchase, purchase)]
        if not any(item.category is not None or item.description is not None or item.is_essential is not None
                   for item in receipt.items):
            return [ReceiptTransactionRow(purchase, purchase)]

        groups = {}
        automatic_descriptions = {}
        for item in receipt.items:
            effective = copy(item)
            if purchase.category is not None:
                effective.category = purchase.category
            if purchase.description is not None:
                effective.description = purchase.description
            if purchase.is_essential is not None:
                effective.is_essential = purchase.is_essential
            # An unchecked receipt checkbox represents non-essential items.
            essential = effective.is_essential if effective.is_essential is not None else IsEssential.NON_ESSENTIAL
            key = (effective.category, effective.description, essential)
            groups.setdefault(key, []).append(item)
            automatic_descriptions[key] = automatic_descriptions.get(key, True) and effective.description_is_autocompleted

        purchase_key = (purchase.category, purchase.description, purchase.is_essential)
        if len(groups) == 1 and purchase_key in groups:
            return [ReceiptTransactionRow(purchase, purchase)]

        grouped_items = list(groups.values())
        amounts = ReceiptGroupManager._amounts(purchase, grouped_items)
        rows = []
        for (category, description, essential), items, amount in zip(groups, grouped_items, amounts):
            transaction = FinancialTransaction(
                date=purchase.date, amount=amount, location=purchase.location,
                description=description, category=category, is_essential=essential,
                receipt=receipt, purchase_title=purchase.purchase_title,
                source=purchase.source,
                excluded_from_totals=purchase.excluded_from_totals,
                hidden=purchase.hidden,
                description_is_autocompleted=(purchase.description_is_autocompleted
                                              or automatic_descriptions[(category, description, essential)]),
            )
            rows.append(ReceiptTransactionRow(transaction, purchase, tuple(items)))
        return rows

    @staticmethod
    def is_hidden(row: ReceiptTransactionRow) -> bool:
        return row.purchase.hidden or row.transaction.hidden

    @staticmethod
    def hidden_receipt_ids(rows: list[ReceiptTransactionRow]) -> set[int]:
        return {id(row.purchase.receipt) for row in rows
                if ReceiptGroupManager.is_hidden(row) and row.purchase.receipt is not None}

    @staticmethod
    def hidden_receipt_files(rows: list[ReceiptTransactionRow]) -> set[str]:
        return {row.purchase.receipt.source_file_name for row in rows
                if ReceiptGroupManager.is_hidden(row) and row.purchase.receipt is not None
                and row.purchase.receipt.source_file_name is not None}

    @staticmethod
    def _amounts(purchase: FinancialTransaction, groups: list[list[GroceryItem]]) -> list[DollarAmount]:
        """Share tax/adjustments proportionally, assigning leftover pennies deterministically."""
        costs = [sum((Decimal(str(item.price)) * Decimal(str(item.quantity)) for item in items), Decimal(0))
                 for items in groups]
        sign = -1 if purchase.amount <= 0 else 1
        cents = [int((sign * cost * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)) for cost in costs]
        total_cents = int((Decimal(str(float(purchase.amount))) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        difference = total_cents - sum(cents)
        weights = [abs(cost) for cost in costs]
        if not any(weights):
            weights = [Decimal(len(items)) for items in groups]
        total_weight = sum(weights)
        shares = [abs(difference) * weight / total_weight for weight in weights]
        allocated = [int(share) for share in shares]
        remainder_order = sorted(range(len(groups)), key=lambda i: shares[i] - allocated[i], reverse=True)
        for index in remainder_order[:abs(difference) - sum(allocated)]:
            allocated[index] += 1
        adjustment_sign = -1 if difference < 0 else 1
        return [DollarAmount((amount + adjustment_sign * extra) / 100)
                for amount, extra in zip(cents, allocated)]
