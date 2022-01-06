
import collections
import pandas as pd
import datetime

from beancount.core.number import Decimal
from beancount.core import amount, convert, prices, inventory, data, account_types
from beancount.parser import options

from envelope_budget.modules.hierarchy.beancount_hierarchy import map_to_bucket


def _get_date_range(start, end):
    return pd.date_range(start, end, freq='MS')


def _date_to_string(x):
    return f"{x.year}-{str(x.month).zfill(2)}"


class TransactionParser:

    def __init__(self, entries, errors, options_map, currency, budget_accounts, mappings):
        self.entries = entries
        self.errors = errors
        self.options_map = options_map
        self.price_map = prices.build_price_map(entries)
        self.acctypes = options.get_account_types(options_map)
        self.currency = currency
        self.budget_accounts = budget_accounts
        self.mappings = mappings

        decimal_precison = '0.00'
        self.Q = Decimal(decimal_precison)

    def is_income(self, account, income_accounts):
        account_type = account_types.get_account_type(account)
        return account_type == self.acctypes.income or any(regexp.match(account) for regexp in income_accounts)

    def is_budget_account(self, account):
        if any(regexp.match(account) for regexp in self.budget_accounts):
            return True
        return False

    def _get_bucket(self, account):
        for regexp, target_account in self.mappings:
            if regexp.match(account):
                return target_account

        return account

    def parse_transactions(self, start, end, income_accounts):

        balances = self._parse_actual_postings(start, end, income_accounts)
        sbalances = self._sort_and_reduce(balances)
        date_range = _get_date_range(start, end)

        row_index = pd.MultiIndex.from_tuples(sbalances.keys(), names=['bucket', 'account'])
        col_index = [_date_to_string(m) for m in date_range]
        actual_expenses = pd.DataFrame(index=row_index, columns=col_index)

        for month in date_range:
            column = _date_to_string(month)
            for account in sorted(sbalances.keys()):
                total = sbalances[account].get((month.year, month.month), None)
                temp = total.quantize(self.Q) if total else 0.00
                temp *= -1
                actual_expenses.loc[account][column] = Decimal(temp)

        return actual_expenses

    def _parse_actual_postings(self, start_date, end_date, income_accounts):

        # Accumulate expenses for the period
        balances = collections.defaultdict(
            lambda: collections.defaultdict(inventory.Inventory))

        # Check entry in date range
        for entry in data.filter_txns([e for e in self.entries if start_date <= e.date <= end_date]):

            month = (entry.date.year, entry.date.month)

            if not any(self.is_budget_account(p.account) for p in entry.postings):
                continue

            if any(self.is_income(p.account, income_accounts) for p in entry.postings):
                for posting in entry.postings:
                    if posting.units.currency != self.currency:
                        orig=posting.units.number
                        if posting.price is not None:
                            converted=posting.price.number*orig
                            posting=data.Posting(posting.account,amount.Amount(converted,self.currency), posting.cost, None, posting.flag,posting.meta)
                        else:
                            continue
                    if self.is_budget_account(posting.account):
                        continue

                    account_type = account_types.get_account_type(posting.account)
                    if account_type == self.acctypes.income or any(regexp.match(posting.account) for regexp in income_accounts):
                        bucket = "Income"
                    #elif account_type == self.acctypes.expenses:
                    #    bucket = "Income:Deduction"
                    else:
                        bucket = map_to_bucket(self.mappings, posting.account)

                    balances[(bucket, posting.account)][month].add_position(posting)
            else:
                for posting in entry.postings:
                    if posting.units.currency != self.currency:
                        continue
                    if self.is_budget_account(posting.account):
                        continue
                    # TODO Warn of any assets / liabilities left

                    bucket = map_to_bucket(self.mappings, posting.account)
                    # TODO
                    balances[(bucket, posting.account)][month].add_position(posting)

        return balances

    def _sort_and_reduce(self, balances):

        sbalances = collections.defaultdict(dict)
        for account, months in sorted(balances.items()):
            for month, balance in sorted(months.items()):
                year, mth = month
                date = datetime.date(year, mth, 1)
                balance = balance.reduce(convert.get_value, self.price_map, date)
                balance = balance.reduce(
                    convert.convert_position, self.currency, self.price_map, date)
                try:
                    pos = balance.get_only_position()
                except AssertionError:
                    print(balance)
                    raise
                total = pos.units.number if pos and pos.units else None
                sbalances[account][month] = total
        return sbalances
