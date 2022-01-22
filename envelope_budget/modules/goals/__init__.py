import datetime
import enum

from beancount.core.amount import Amount


class Interval(enum.Enum):
    """The possible intervals."""

    YEAR = "year"
    QUARTER = "quarter"
    MONTH = "month"
    WEEK = "week"
    DAY = "day"


class BaseTarget:
    def __init__(self, account: str, date: datetime.date, amount: Amount = None, by_date: datetime.date = None,
                 recur: Interval = None):
        self.account = account
        self.start_date = date
        self.target_date = by_date
        self.amount = amount
        self.recur_interval = recur

    def __eq__(self, other):

        return self.start_date == other.start_date and self.account == other.account and self.amount == other.amount \
               and self.target_date == other.target_date and self.recur_interval == other.recur_interval

    def __str__(self):
        base = f'{self.start_date} {self.account} \t{self.amount}'

        if self.recur_interval is not None:
            base += f' ({self.recur_interval})'

        if self.target_date is None:
            return base

        return f'{base} by {self.target_date}'

    @property
    def target_type(self):
        return f'{self.recur_interval}'[0] if self.recur_interval else 'D' if self.target_date else 'T'


class Target(BaseTarget):
    def __init__(self, date: datetime.date, account, target: Amount = None, by_date: datetime.date = None, monthly_amount: Amount = None):
        super().__init__(account, date, target if target else monthly_amount, by_date, recur=Interval.MONTH if monthly_amount else None)
        self.target = target
        self.monthly_target = monthly_amount

    def __eq__(self, other):
        if not isinstance(other, Target):
            # don't attempt to compare against unrelated types
            return NotImplemented

        return self.start_date == other.start_date and self.account == other.account and self.target == other.target \
               and self.target_date == other.start_date and self.monthly_target == other.monthly_target

    def __str__(self):
        return super().__str__()


class SpendingTarget(BaseTarget):
    def __init__(self, date: datetime.date, account, amount: Amount = None, by_date: datetime.date = None, interval: Interval = None):
        super().__init__(account, date, amount, by_date, interval)

    def __eq__(self, other):
        if not isinstance(other, SpendingTarget):
            # don't attempt to compare against unrelated types
            return NotImplemented

        return super().__eq__(other)

    def __str__(self):
        return super().__str__()