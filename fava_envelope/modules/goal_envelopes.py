
from beancount.core.inventory import Inventory, Amount

import logging
import datetime
from collections import defaultdict as ddict

from fava_envelope.modules.beancount_entries import BeancountEntries
from fava_envelope.modules.beancount_envelope import BeancountEnvelope
from fava_envelope.modules.beancount_goals import BeancountGoal
from fava_envelope.modules.beancount_hierarchy import Bucket, get_hierarchy, map_accounts_to_bucket, map_df_to_buckets, merge_envelope_tables

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

        self._all_values = dict({'goal': self.goal, 'budgeted': self.budgeted, 'spent': self.spent, 'available': self.available})

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


class PeriodData:
    def __init__(self, period, content, accounts):
        self.period = period
        self.values = content
        self.accounts = accounts

    def _account_row(self, a):
        if isinstance(a, Bucket):
            a = a.account
        return self.values[a]

    def is_visible(self, a, show_real):
        row: AccountRow = self._account_row(a)
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

        self.income_tables, self.envelope_tables, current_month = module.envelope_tables(parser)

        goals = BeancountGoal(entries, errors, options, module.currency)
        self.actual_accounts = goals.get_merged(parser, module.date_start, module.date_end)
        merged_envelope_tables = merge_envelope_tables(module.mappings, self.envelope_tables, self.actual_accounts)
        self.envelope_tables_with_goals = goals.compute_targets(merged_envelope_tables)
        self.mapped_accounts = map_accounts_to_bucket(module.mappings, self.actual_accounts.index)

    def get_budgets_months_available(self):
        return [] if not self.initialized else self.income_tables.columns

    def get_inventories(self, period, include_real_accounts):

        if not self.initialized:
            return [], period

        include_real_accounts = include_real_accounts if not None else False

        today = datetime.date.today()
        if period is None:
            year = today.year
            month = today.month
            period = f'{year:04}-{month:02}'

        all_values = ddict(AccountRow)

        if period is not None and self.envelope_tables_with_goals is not None:
            for index, e_row in self.envelope_tables_with_goals.iterrows():
                account_row = all_values[index]
                account_row.name = index
                account_row.is_bucket = True

                _add_amount(account_row.available, e_row[period, "available"])
                _add_amount(account_row.budgeted, e_row[period, "budgeted"])
                _add_amount(account_row.spent, e_row[period, "activity"])
                _add_amount(account_row.goal, e_row[period, "goals"])
                _add_amount(account_row.target, e_row[period, "target"])

            if self.actual_accounts is not None:
                for index, data in self.actual_accounts.iterrows():
                    account_row = all_values[index]
                    account_row.name = index
                    account_row.is_real = True
                    _add_amount(account_row.spent, data[period, "activity"])
                    _add_amount(account_row.goal, data[period, "goals"])

        acc_hierarchy = get_hierarchy(self.envelope_tables_with_goals.index, self.mapped_accounts, include_real_accounts)
        return PeriodData(period, all_values, acc_hierarchy)

