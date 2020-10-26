import datetime
import logging

from beancount.core.amount import Amount
from beancount.core.data import Custom
from collections import defaultdict

NAME = 'goal'


def parse_goals(entries):
    by_account = defaultdict(list)
    for e in (e for e in entries if isinstance(e, Custom) and e.type == NAME):
        goal = _get_budget_goal(e.date, parse_goal_values(e.values))
        by_account[goal.account].append(goal)

    return by_account


def parse(e: Custom):
    if e.type == NAME:
        args = parse_goal_values(e.values)
        return _get_budget_goal(e.date, args)
    else:
        raise AttributeError(f"Cannot parse custom directive not of type '{NAME}")


def parse_goal_values(values):
    args = dict()

    account = values[0]
    args['account'] = account.value

    keys = ['target amount', 'by', 'monthly']
    expected = keys.pop(0)

    for i in values[1:]:
        if i.dtype in ['<AccountDummy>', Amount, datetime.date]:
            args[expected] = i.value
            if len(keys) > 0:
                expected = keys.pop(0)
        elif i.dtype == str:
            while expected != i.value and len(keys) > 0:
                expected = keys.pop(0)
            expected = i.value

    return args


class Target:
    def __init__(self, date: datetime.date, account, target: Amount, by_date: datetime.date = None, monthly_amount: Amount = None):
        self.start_date = date
        self.account = account
        self.target_date = by_date
        self.target = target
        self.monthly_target = monthly_amount

    @property
    def target_type(self):
        return 'M' if not self.target else 'D' if self.target_date else 'T'

    def __str__(self):
        base = f'{self.start_date} {self.account} \t{self.target}'

        if self.monthly_target is not None:
            base += f' (monthly {self.monthly_target})'

        if self.target_date is None:
            return base
        return f'{base} by {self.target_date}'

def _get_budget_goal(start_date: datetime.date, values):
    account = values['account']

    target_amount = None if 'target amount' not in values else values['target amount']
    target_date = None if 'by' not in values else values['by']
    monthly = None if 'monthly' not in values else values['monthly']

    return Target(start_date, account, target_amount, target_date, monthly)
