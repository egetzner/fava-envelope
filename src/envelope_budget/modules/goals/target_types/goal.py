import datetime
from typing import List

from beancount.core.amount import Amount
from beancount.core.data import Custom, Entries

from envelope_budget.modules.goals import Target, Interval, SpendingTarget
from envelope_budget.modules.goals.target_types import TargetParser

NAME = 'goal'

interval_map = {
    "daily": Interval.DAY,
    "weekly": Interval.WEEK,
    "monthly": Interval.MONTH,
    "quarterly": Interval.QUARTER,
    "yearly": Interval.YEAR,
}


def _parse_spending_target(entry):
    interval = interval_map.get(str(entry.values[2].value))
    return SpendingTarget(
        entry.date,
        entry.values[1].value,
        interval=interval,
        amount=Amount(entry.values[3].value.number, entry.values[3].value.currency)
    )


def _parse_goal_values(values):
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


def _get_budget_goal(start_date: datetime.date, values):
    account = values['account']

    target_amount = None if 'target amount' not in values else values['target amount']
    target_date = None if 'by' not in values else values['by']
    interval = None if 'monthly' not in values else values['monthly']

    return Target(start_date, account, target_amount, target_date, interval)


class CustomGoalTargetParser(TargetParser):

    def parse_entries(self, entries):
        targets = list()
        for e in (e for e in entries if isinstance(e, Custom) and e.type == NAME):
            target = _get_budget_goal(e.date, _parse_goal_values(e.values))
            targets.append(target)

        return targets


class EnvelopeGoalTargetParser(TargetParser):

    def parse_entries(self, entries):
        targets = list()

        if entries is None:
            return targets

        for e in (e for e in entries if isinstance(e, Custom) and e.values[0].value == "target"):
            target = _get_budget_goal(e.date, _parse_goal_values(e.values[1:]))
            targets.append(target)

        return targets


class NeededForSpendingTargetParser(TargetParser):

    def parse_entries(self, entries: Entries) -> List[SpendingTarget]:
        filtered = [e for e in entries if isinstance(e, Custom) and e.values[0].value == "spending"]
        return [_parse_spending_target(f) for f in filtered]
