from enum import Enum

from beancount.core.inventory import Inventory, Amount

import pandas as pd
import datetime
from collections import defaultdict as ddict

from envelope_budget.modules.hierarchy.beancount_entries import TransactionParser
from fava_envelope.modules.beancount_envelope import BeancountEnvelope
from envelope_budget.modules.goals.beancount_goals import EnvelopesWithGoals, merge_all_targets
from envelope_budget.modules.hierarchy.beancount_hierarchy import Bucket, get_hierarchy, get_level_as_dict


def _add_amount(inventory, value, currency='EUR'):
    if not pd.isna(value) and value != 0:
        inventory.add_amount(Amount(value, currency))


def sort_buckets(b: Bucket):
    return "_" if b.account.startswith("Income") else b.account


class RowType(Enum):
    CONTAINER = 1,
    BUCKET = 2,
    ACCOUNT = 3


def parse_target(data, goal_type='NA'):
    amount = data.amount
    reference = data.ref_amount
    if pd.isna(amount) or pd.isna(reference):
        return Target()

    return Target(amount, reference, goal_type)


class Target:
    def __init__(self, target=None, ref_amount=None, goal_type: str = 'NA'):
        self.amount: Inventory = Inventory()
        self.goal_type: str = goal_type
        _add_amount(self.amount, target)
        self.goal_progress = ref_amount / target if target != 0 and ref_amount else 0

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
        self.in_budget: bool = True

        self.budgeted: Inventory = Inventory()
        self.available: Inventory = Inventory()
        self.spent: Inventory = Inventory()
        self.target: Inventory = Inventory()

        self.target: Target = Target()
        self.target_monthly: Target = Target()
        self.goal_monthly: Target = Target()

        self._all_values = dict({'budgeted': self.budgeted, 'spent': self.spent, 'available': self.available})

    @property
    def is_real(self):
        return self.row_type == RowType.ACCOUNT

    @property
    def is_bucket(self):
        return self.row_type == RowType.BUCKET

    @property
    def goal_progress(self):
        if self.display_goal:
            return self.display_goal.goal_progress

        return None

    @property
    def is_fully_funded(self):
        if self.target:
            return self.target.is_funded

        if self.target_monthly:
            return self.target_monthly.is_funded

        if self.goal_monthly:
            return self.goal_monthly.is_funded

        return True

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
        return self.display_goal

    @property
    def display_goal(self):
        if self.target_monthly:
            return self.target if self.target and self.target_monthly.is_funded else self.target_monthly

        if self.target:
            return self.target

        return self.goal_monthly

    @property
    def goal_type(self):
        ref_goal = self.target_monthly if self.target_monthly else self.display_goal

        if ref_goal:
            return f'{ref_goal.goal_type}'

        return ''

    def is_non_budget(self):
        return self.is_real or not self.in_budget

    def set_targets(self, name, data):
        self.target = parse_target(data['t'], 'T')           # Target(data['target_total'], data['progress_total'])
        self.target_monthly = parse_target(data['tm'], 'D' if self.target else 'M')  # Target(data['target_monthly'], data['progress_monthly'])
        self.goal_monthly = parse_target(data['sg'], 'S')    # Target(data.goals, data['goal_progress'])

        if self.row_type == RowType.CONTAINER:
            self.row_type = RowType.BUCKET
            self.name = name

    def set_bucket_row(self, name, e_row):
        self.name = name
        self.row_type = RowType.BUCKET

        avail = e_row.available
        budget = e_row.budgeted
        activity = e_row.activity

        if pd.isna(avail) and pd.isna(budget):
            self.in_budget = False

        _add_amount(self.available, avail)
        _add_amount(self.budgeted, budget)
        _add_amount(self.spent, activity)

    def set_account_row(self, name, row):
        self.name = name
        self.row_type = RowType.ACCOUNT

        _add_amount(self.spent, row["activity"])
        self.goal_monthly = Target(row["goals"], goal_type='S')

    def get(self, name):
        if isinstance(name, str):
            if name == 'budgeted':
                return self.budgeted
            elif name == 'spent':
                return self.spent
            elif name == 'available':
                return self.available
            elif name == "goals":
                return self.display_goal
            elif name == 'target':
                return self.target

        return Inventory()

    def is_empty(self):
        return len([i for i in self._all_values.values() if not i.is_empty()]) == 0 and not self.has_any_goal

    def __str__(self):
        acc = f'{self.name} ({"real" if self.is_real else "bucket" if self.is_bucket else "unknown"})'
        if self.is_empty():
            return f'[{acc}] is empty'
        else:
            return f'[{acc}] Budgeted: {self.budgeted}, Spent: {self.spent} = Available: {self.available}' \
                   f'\n Goals and Targets: {self.target} (monthly: {self.target_monthly}) - goal: {self.goal_monthly}'


class PeriodData:
    def __init__(self, period, account_rows, accounts, is_current_month=False):
        self.period = period
        self.is_current = is_current_month
        self.account_rows = account_rows
        self.accounts = accounts
        self.accounts.sort(key=sort_buckets)

    def account_row(self, a):
        if isinstance(a, Bucket):
            a = a.account

        return self.account_rows[a]

    def is_leaf(self, acc):
        ar: AccountRow = self.account_row(acc)
        return ar.row_type != RowType.CONTAINER

    def get_matching_rows(self, acc):
        is_bucket = True
        if isinstance(acc, Bucket):
            a = acc.account
            is_bucket = not acc.is_real
        else:
            a = acc

        matching = [self.account_rows[ar] for ar in self.account_rows.keys() if ar.startswith(a)]
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

        parser = TransactionParser(entries, errors, options,
                                   currency=module.currency,
                                   budget_accounts=module.budget_accounts,
                                   mappings=module.mappings)

        self.income_tables, envelope_tables, all_activity, self.current_month = module.envelope_tables(parser)

        bg = EnvelopesWithGoals(entries, errors, options, module.currency)
        detail_goals, spending = bg.get_spending_goals(module.date_start, module.date_end, module.mappings,
                                                       all_activity.index, envelope_tables, self.current_month)
        targets, monthly_target = bg.get_targets(module.date_start, module.date_end, envelope_tables)
        self.all_targets = merge_all_targets({'sg': spending, 't': targets, 'tm': monthly_target})

        self.account_data = pd.concat({'activity': all_activity, 'goals': detail_goals}, axis=1).swaplevel(1, 0, axis=1)
        self.bucket_data = envelope_tables

        self.account_to_buckets = get_level_as_dict(self.account_data, [self.bucket_data, self.all_targets])

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

        rows = ddict(AccountRow)

        buckets_by_month = self.bucket_data.xs(key=period, level=0, axis=1, drop_level=True)
        target_by_month = self.all_targets.xs(key=period, level=0, axis=1, drop_level=True)
        accounts_in_month = self.account_data.xs(key=period, level=0, axis=1, drop_level=True).fillna(0)

        for index, e_row in buckets_by_month.iterrows():
            account_row = rows[index]
            account_row.set_bucket_row(index, e_row)

        for index, e_row in target_by_month.iterrows():
            account_row = rows[index]
            account_row.set_targets(index, e_row)

        for index, data in accounts_in_month.iterrows():
            account_row = rows[index[1]]
            account_row.set_account_row(index[1], data)

        acc_hierarchy = get_hierarchy(self.account_to_buckets, include_real_accounts)
        return PeriodData(period, rows, acc_hierarchy, period == self.current_month)

