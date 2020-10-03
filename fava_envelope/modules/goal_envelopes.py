
from beancount.core.inventory import Inventory, Amount

import datetime
from collections import defaultdict as ddict

from fava_envelope.modules.beancount_envelope import BeancountEnvelope
from fava_envelope.modules.beancount_goals import BeancountGoal
from fava_envelope.modules.beancount_hierarchy import Bucket, get_hierarchy, map_accounts_to_bucket, map_df_to_buckets



def _add_amount(inventory, value, currency='EUR'):
    if value != 0:
        inventory.add_amount(Amount(-value, currency))

class AccountRow:
    def __init__(self):
        self.goal: Inventory = Inventory()
        self.budgeted: Inventory = Inventory()
        self.available: Inventory = Inventory()
        self.spent: Inventory = Inventory()

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

        return Inventory()

    def __str__(self):
        return f'Goal: {self.goal}, Budgeted: {self.budgeted}, Spent: {self.budgeted} = Available: {self.available}'

class PeriodData:
    def __init__(self, period, content, accounts):
        self.period = period
        self.values = content
        self.accounts = accounts

class EnvelopeWrapper:

    def __init__(self, entries, errors, options, module: BeancountEnvelope):
        self.initialized = module is not None

        if not self.initialized:
            return

        goals = BeancountGoal(entries, errors, options, module.currency)
        self.income_tables, self.envelope_tables, current_month = module.envelope_tables()
        self.actual_accounts = goals.get_merged(module.budget_accounts, module.date_start, module.date_end)
        self.mapped_tables = map_df_to_buckets(module.mappings, self.actual_accounts)
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

        # budget rows
        self.midbrows = ddict(Inventory)
        # spent rows
        self.midsrows = ddict(Inventory)
        # available rows
        self.midvrows = ddict(Inventory)

        self.actsrows = ddict(Inventory)
        self.goalrows = ddict(Inventory)

        self.all_values = ddict(AccountRow)

        if period is not None and self.envelope_tables is not None:
            for index, e_row in self.envelope_tables.iterrows():
                _add_amount(self.all_values[index].available, e_row[period, "available"])
                _add_amount(self.all_values[index].budgeted, e_row[period, "budgeted"])
                _add_amount(self.all_values[index].spent, e_row[period, "activity"])

            if self.actual_accounts is not None:
                for index, data in self.actual_accounts.iterrows():
                    _add_amount(self.all_values[index].spent, data[period, "activity"])
                    _add_amount(self.all_values[index].goal, data[period, "goals"])

            if self.mapped_tables is not None:
                for index, data in self.mapped_tables.iterrows():
                    _add_amount(self.all_values[index].goal, data[period, "goals"])

        acc_hierarchy = get_hierarchy(self.mapped_accounts, include_real_accounts)
        return PeriodData(period, self.all_values, acc_hierarchy)

    def is_visible_bucket(self, a, period):
        if a.account in self.envelope_tables.index:
            row = self.envelope_tables.loc[a.account][period]
            non_zero = [x for x in row if x != 0]
            return len(non_zero) > 0

        return False

    def is_visible_account(self, a, period):
        if a.account in self.actual_accounts.index:
            row = self.actual_accounts.loc[a.account][period]
            non_zero = [x for x in row if x != 0]
            return len(non_zero) > 0

        return False
