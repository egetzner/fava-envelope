from enum import Enum

from beancount.core.inventory import Inventory, Amount

import pandas as pd
import datetime
from collections import defaultdict as ddict

from envelope_budget.modules.hierarchy.beancount_entries import BeancountEntries
from fava_envelope.modules.beancount_envelope import BeancountEnvelope
from envelope_budget.modules.goals.beancount_goals import BeancountGoal, merge_with_multihierarchy, merge_with_targets
from envelope_budget.modules.hierarchy.beancount_hierarchy import Bucket, get_hierarchy, from_accounts_to_hierarchy


def _add_amount(inventory, value, currency='EUR'):
    if not pd.isna(value) and value != 0:
        inventory.add_amount(Amount(value, currency))


def sort_buckets(b: Bucket):
    return "_" if b.account.startswith("Income") else b.account


class RowType(Enum):
    CONTAINER = 1,
    BUCKET = 2,
    ACCOUNT = 3


class Target:
    def __init__(self, amount: int = 0, progress: int = None):
        self.amount: Inventory = Inventory()
        _add_amount(self.amount, amount)
        self.goal_progress = progress
        if pd.isna(progress) or progress is None:
            self.goal_progress = 0 if amount != 0 else None

    def is_empty(self):
        return self.amount.is_empty()

    def __bool__(self):
        return not self.is_empty()

    @property
    def is_funded(self):
        return self.goal_progress is not None and self.goal_progress >= 1

    def __str__(self):
        if self:
            if self.goal_progress is None:
                return f'{self.amount} (no progress)'
            return f'{self.amount}: ({self.goal_progress*100:03.2f}% funded)'
        return 'empty'


class AccountRow:
    def __init__(self):
        self.name: str = "<Unknown>"
        self.row_type = RowType.CONTAINER

        self.is_bucket: bool = False
        self.is_real: bool = False

        self.budgeted: Inventory = Inventory()
        self.available: Inventory = Inventory()
        self.spent: Inventory = Inventory()
        self.target: Inventory = Inventory()

        self.in_budget = True

        self.target: Target = Target()
        self.target_monthly: Target = Target()
        self.goal_monthly: Target = Target()

        self._all_values = dict({'goal': self.goal, 'budgeted': self.budgeted, 'spent': self.spent, 'available': self.available})

    @property
    def is_fully_funded(self):
        if self.target:
            return self.target.is_funded

        if self.goal_monthly:
            return self.goal_monthly.is_funded

        return True

    @property
    def goal_progress(self):
        if self.target_monthly and not self.target_monthly.is_funded:
            return self.target_monthly.goal_progress

        if self.target:
            return self.target.goal_progress

        if self.goal_monthly:
            return self.goal_monthly.goal_progress

        return None

    @property
    def is_underfunded(self):
        if self.target_monthly:
            return not self.target_monthly.is_funded

        # target without monthly target cannot be underfunded
        if self.target:
            return False

        if self.goal_monthly:
            return not self.goal_monthly.is_funded

        #items without goals cannot be underfunded
        return False

    @property
    def is_funded(self):
        if self.target_monthly:
            return self.target_monthly.is_funded

        if self.target:
            return self.target.is_funded
        
        if self.goal_monthly:
            return self.goal_monthly.is_funded

        return None

    @property
    def has_any_goal(self):
        return self.target or self.target_monthly or self.goal_monthly

    def is_non_budget(self):
        return self.is_real or not self.in_budget

    def set_targets(self, data):
        self.target = Target(data['target_total'], data['progress_total'])
        self.target_monthly = Target(data['target_monthly'], data['progress_monthly'])

    def set_bucket_row(self, name, e_row):
        self.name = name
        self.is_bucket = True
        self.row_type = RowType.BUCKET

        avail = e_row.available
        budget = e_row.budgeted
        activity = e_row.activity

        if pd.isna(avail) and pd.isna(budget):
            self.in_budget = False

        _add_amount(self.available, avail)
        _add_amount(self.budgeted, budget)
        _add_amount(self.spent, activity)
        self.goal_monthly = Target(e_row.goals, e_row['goal_progress'])

    def set_account_row(self, name, row):
        self.name = name
        self.is_real = True
        self.in_budget = False
        self.row_type = RowType.ACCOUNT

        _add_amount(self.spent, row["activity"])
        self.goal_monthly = Target(row["goals"])

    @property
    def goal(self):
        if self.target_monthly:
            return self.target_monthly.amount

        if self.target:
            return self.target.amount

        return self.goal_monthly.amount

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
            return f'[{acc}] Budgeted: {self.budgeted}, Spent: {self.spent} = Available: {self.available}' \
                   f'\n Goals and Targets: {self.target} (monthly: {self.target_monthly}) - goal: {self.goal_monthly}'


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

    def is_leaf(self, acc):
        ar: AccountRow = self.account_row(acc)
        return ar.row_type != RowType.CONTAINER

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
        targets, rem_months = bg.parse_budget_goals(module.date_start, module.date_end)
        goals_with_buckets = from_accounts_to_hierarchy(module.mappings, all_activity, goals)
        self.bucket_data = merge_with_multihierarchy(envelope_tables, all_activity, goals_with_buckets, current_month)
        self.targets_with_buckets = merge_with_targets(self.bucket_data, targets, rem_months)
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
            target_by_month = self.targets_with_buckets.xs(key=period, level=0, axis=1, drop_level=True)

            for index, e_row in buckets_by_month.iterrows():
                account_row = bucket_values[index]
                account_row.set_bucket_row(index, e_row)

            for index, e_row in target_by_month.iterrows():
                account_row = bucket_values[index]
                account_row.set_targets(e_row)

            if self.account_data is not None and period in self.account_data.columns:
                accounts_in_month = self.account_data.xs(key=period, level=0, axis=1, drop_level=True).fillna(0)

                for index, data in accounts_in_month.iterrows():
                    account_row = account_values[index[1]]
                    account_row.set_account_row(index[1], data)

        acc_hierarchy = get_hierarchy(self.bucket_data.index, self.mapped_accounts, include_real_accounts)
        return PeriodData(period, bucket_values, account_values, acc_hierarchy)

