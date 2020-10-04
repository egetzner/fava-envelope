
from fava.core.budgets import parse_budgets, calculate_budget

import logging
import collections
import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta

from beancount.core.number import Decimal
from beancount.core import convert, prices, inventory, data, account_types, account
from beancount.core.data import Custom
from beancount.parser import options

class BeancountGoal:
    def __init__(self, entries, errors, options_map, currency):

        self.entries = entries
        self.errors = errors
        self.options_map = options_map
        self.price_map = prices.build_price_map(entries)
        self.acctypes = options.get_account_types(options_map)
        self.currency = currency

        decimal_precison = '0.00'
        self.Q = Decimal(decimal_precison)

    def _get_date_range(self, start, end):
        return pd.date_range(start, end, freq='MS')#.to_pydatetime()

    def _date_to_string(self, x):
        return f"{x.year}-{str(x.month).zfill(2)}"

    def compute_targets(self, tables):
        goals = tables.xs(key='goals', level=1, axis=1)
        spent = tables.xs(key='activity', level=1, axis=1)
        budgeted = tables.xs(key='budgeted', level=1, axis=1)
        available = tables.xs(key='available', level=1, axis=1)
        originally_available = available + spent*-1
        target = goals - originally_available
        target.name = 'target'
        merged = pd.concat({'budgeted':budgeted, 'activity':spent, 'available':available, 'goals':goals, 'target':target}, axis=1)
        df = merged.swaplevel(0, 1, axis=1).sort_index().fillna(0)
        return df

    def get_merged(self, budget_accounts, start, end):
        gdf = self.parse_fava_budget(self.entries, start_date=start, end_date=end)
        act = self.parse_transactions(budget_accounts, start, end)

        mrg = pd.concat({'goals':gdf, 'activity':act}, axis=1)
        mrg = mrg.swaplevel(0, 1, axis=1).reindex()
        return mrg.sort_index().fillna(0)

    def parse_fava_budget(self, entries, start_date, end_date):
        custom = [e for e in entries if isinstance(e, Custom)]
        budgets, errors = parse_budgets(custom)
        all_months_data = dict()
        dr = self._get_date_range(start_date, end_date)
        for d in dr:
            start = d.date()
            end = start + relativedelta(months=1)
            values = dict()
            for be in budgets:
                # note: calculate_budget_children would also include the sub-categories, which is not what we want here
                cb = calculate_budget(budgets, be, start, end)
                values[be] = cb[self.currency].quantize(self.Q)
            all_months_data[self._date_to_string(d)] = values

        return pd.DataFrame(all_months_data).sort_index()

    def parse_transactions(self, budget_accounts, start, end):

        balances = self._parse_actual_postings(budget_accounts, start, end)
        sbalances = self._sort_and_reduce(balances)
        date_range = self._get_date_range(start, end)

        actual_expenses = pd.DataFrame()
        for account in sorted(sbalances.keys()):
            for month in date_range:
                total = sbalances[account].get((month.year, month.month), None)
                temp = total.quantize(self.Q) if total else 0.00
                # swap sign to be more human readable
                temp *= -1
                actual_expenses.loc[account, self._date_to_string(month)] = Decimal(temp)

        return actual_expenses

    def _parse_actual_postings(self, budget_accounts, start_date, end_date):

        # Accumulate expenses for the period
        balances = collections.defaultdict(
            lambda: collections.defaultdict(inventory.Inventory))

        # Check entry in date range
        for entry in data.filter_txns([e for e in self.entries if start_date <= e.date <= end_date]):

            month = (entry.date.year, entry.date.month)
            contains_budget_accounts = False
            for posting in entry.postings:
                if any(regexp.match(posting.account) for regexp in budget_accounts):
                    contains_budget_accounts = True
                    break

            if not contains_budget_accounts:
                continue

            for posting in entry.postings:

                account = posting.account
                account_type = account_types.get_account_type(account)
                if posting.units.currency != self.currency:
                    continue

                if account_type == self.acctypes.income:
                    account = "Income"
                elif any(regexp.match(posting.account) for regexp in budget_accounts):
                    continue
                # TODO Warn of any assets / liabilities left

                # TODO
                balances[account][month].add_position(posting)

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
