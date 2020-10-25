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
    def __init__(self, date: datetime.date, account, target: Amount, by_date: datetime.date = None):
        self.start_date = date
        self.account = account
        self.target_date = by_date
        self.amount = target

    def __str__(self):
        base = f'{self.start_date} {self.account} \t{self.amount}'
        if self.target_date is None:
            return base
        return f'{base} by {self.target_date}'


class BeanBudgetGoal(Target):

    def __init__(self, start_date, account, target_amount, target_date, monthly_amount):
        super().__init__(start_date, account, target_amount, target_date)
        if monthly_amount is not None:
            logging.warning('monthly amount for goal not supported currently')

        self.target_amount = self.__get_amount(target_amount)
        self.monthly_amount = self.__get_amount(monthly_amount)
        self.monthly_cum = self.__compute_cumulative()

    def __get_amount(self, amount):
        if isinstance(amount, Amount):
            return amount.number

        return amount

    def __compute_cumulative(self):

        # for each month, compute the goal target.
        months = list()

        for month in range(0, 12):
            months.append(0)

        amount = 0

        # each month, the monthly amount is added. if a target amount/date exists, we stop until then.
        start = 1 if self.start_date is None else self.start_date.month
        end = 12 if self.target_date is None else self.target_date.month

        max_amount = self.target_amount

        # case 1: only monthly amount --> easiest to compute.
        if self.monthly_amount is not None:
            amount = self.monthly_amount
        elif max_amount is not None:
            # we need to compute the number of months:
            duration = end - start
            if duration <= 0:
                amount = max_amount
            else:
                exact = max_amount / duration
                decimals = -1 if exact > 15 else 0
                amount = round(exact, decimals)

        cum_amount = 0

        for idx in range(0, 12):
            month = idx + 1
            if month in range(start, end + 1):

                if max_amount is None or max_amount > cum_amount:
                    cum_amount += amount
                    if max_amount is not None and max_amount < cum_amount:
                        cum_amount = max_amount
                    months[idx] = cum_amount
                else:
                    break

        return months


def _get_budget_goal(start_date: datetime.date, values):
    account = values['account']

    target_amount = None if 'target amount' not in values else values['target amount']
    target_date = None if 'by' not in values else values['by']
    monthly = None if 'monthly' not in values else values['monthly']

    return BeanBudgetGoal(start_date, account, target_amount, target_date, monthly)
