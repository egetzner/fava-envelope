
from beancount.core.inventory import Inventory, Amount

import pandas as pd
import logging
import datetime
from collections import defaultdict as ddict

from fava_envelope.modules.beancount_entries import BeancountEntries
from fava_envelope.modules.beancount_envelope import BeancountEnvelope
from fava_envelope.modules.beancount_goals import BeancountGoal, compute_targets
from fava_envelope.modules.beancount_hierarchy import Bucket, get_hierarchy, from_accounts_to_hierarchy


def _add_amount(inventory, value, currency='EUR'):
    if value != 0:
        inventory.add_amount(Amount(-value, currency))

class AccountRow:
    def __init__(self):
        self.name: str = "<Unknown>"
        self.is_bucket: bool = False
        self.is_real: bool = False

        self.goal: Inventory = Inventory()
        self.budgeted: Inventory = Inventory()
        self.available: Inventory = Inventory()
        self.spent: Inventory = Inventory()
        self.target: Inventory = Inventory()

        self._all_values = dict({'goal': self.goal, 'budgeted': self.budgeted, 'spent': self.spent, 'available': self.available, 'target': self.target})

    def get(self, name):
        if isinstance(name, str):
            if name == 'budgeted':
                return self.budgeted
            elif name == "goals":
                return self.goal
            elif name == 'spent':
                return self.spent
            elif name == 'available':
                return self.available
            elif name == 'target':
                return self.target

        return Inventory()

    def is_empty(self):
        return len([i for i in self._all_values.values() if not i.is_empty()]) == 0

    def __str__(self):
        acc = f'{self.name} ({"real" if self.is_real else "bucket" if self.is_bucket else "unknown"})'
        if self.is_empty():
            return f'[{acc}] is empty'
        else:
            return f'[{acc}] Goal: {self.goal}, Budgeted: {self.budgeted}, Spent: {self.spent} = Available: {self.available}'

def sort_buckets(b: Bucket):
    return "_" if b.account.startswith("Income") else b.account

class PeriodData:
    def __init__(self, period, bucket_values, account_values, accounts):
        self.period = period
        self.bucket_values = bucket_values
        self.account_values = account_values
        self.accounts = accounts
        self.accounts.sort(key=sort_buckets)

    def account_row(self, a):
        is_bucket = True
        if isinstance(a, Bucket):
            is_bucket = not a.is_real
            a = a.account

        return self.bucket_values[a] if is_bucket else self.account_values[a]

    def get_matching_rows(self, acc):
        is_bucket = True
        values = self.bucket_values
        if isinstance(acc, Bucket):
            a = acc.account
            is_bucket = not acc.is_real
            values = self.bucket_values if is_bucket else self.account_values
        else:
            a = acc

        matching = [values[ar] for ar in values.keys() if ar.startswith(a)]
        return [m for m in matching if m.is_bucket == is_bucket]

    def is_visible(self, a, show_real):
        row: AccountRow = self.account_row(a)
        if row.is_bucket or (show_real and row.is_real):
            return not row.is_empty()

        return True


class EnvelopeWrapper:

    def __init__(self, entries, errors, options, module: BeancountEnvelope):
        self.initialized = module is not None

        if not self.initialized:
            return

        parser = BeancountEntries(entries, errors, options,
                                   currency=module.currency,
                                   budget_accounts=module.budget_accounts,
                                   mappings=module.mappings)

        self.income_tables, envelope_tables, all_activity, current_month = module.envelope_tables(parser)

        bg = BeancountGoal(entries, errors, options, module.currency)
        goals = bg.parse_fava_budget(module.date_start, module.date_end)
        goals_with_buckets = from_accounts_to_hierarchy(module.mappings, all_activity, goals)
        self.bucket_data = compute_targets(envelope_tables, all_activity, goals_with_buckets)
        multi_level_index = goals_with_buckets
        self.mapped_accounts = multi_level_index.groupby(level=0).apply(lambda df: list(df.index.get_level_values(level=1).values)).to_dict()
        self.account_data = pd.concat({'activity': all_activity, 'goals': goals_with_buckets}, axis=1).swaplevel(1, 0, axis=1)

    def get_budgets_months_available(self):
        return [] if not self.initialized else self.income_tables.columns

    def get_inventories(self, period: str, include_real_accounts):

        if not self.initialized:
            return [], period

        include_real_accounts = include_real_accounts if not None else False

        today = datetime.date.today()
        if period is None:
            year = today.year
            month = today.month
            period = f'{year:04}-{month:02}'

        bucket_values = ddict(AccountRow)
        account_values = ddict(AccountRow)

        if self.bucket_data is not None and period in self.bucket_data.columns:
            buckets_by_month = self.bucket_data.xs(key=period, level=0, axis=1, drop_level=True)

            for index, e_row in buckets_by_month.iterrows():
                account_row = bucket_values[index]
                account_row.name = index
                account_row.is_bucket = True

                _add_amount(account_row.available, e_row["available"])
                _add_amount(account_row.budgeted, e_row["budgeted"])
                _add_amount(account_row.spent, e_row["activity"])
                _add_amount(account_row.goal, e_row["goals"])
                _add_amount(account_row.target, e_row["target"])

            if self.account_data is not None and period in self.account_data.columns:
                accounts_in_month = self.account_data.xs(key=period, level=0, axis=1, drop_level=True).fillna(0)

                for index, data in accounts_in_month.iterrows():
                    account_row = account_values[index[1]]
                    account_row.name = index[1]
                    #account_row.bucket = index[0]
                    account_row.is_real = True
                    _add_amount(account_row.spent, data["activity"])
                    _add_amount(account_row.goal, data["goals"])

        acc_hierarchy = get_hierarchy(self.bucket_data.index, self.mapped_accounts, include_real_accounts)
        return PeriodData(period, bucket_values, account_values, acc_hierarchy)

