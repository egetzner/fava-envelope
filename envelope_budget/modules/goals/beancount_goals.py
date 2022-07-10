import datetime
from collections import defaultdict
from typing import List, Dict

import pandas as pd
from beancount.core import prices
from beancount.core.data import Custom
from beancount.core.number import Decimal
from beancount.parser import options
from dateutil.relativedelta import relativedelta
from fava.core.budgets import parse_budgets, calculate_budget, Budget, BudgetDict, Interval as FavaInterval

from envelope_budget.modules.goals import SpendingTarget, Target, BaseTarget, Interval as OwnInterval
from envelope_budget.modules.goals.target_types import goal
from envelope_budget.modules.goals.target_types.goal import CustomGoalTargetParser, EnvelopeGoalTargetParser, \
    NeededForSpendingTargetParser
from envelope_budget.modules.hierarchy.beancount_hierarchy import add_bucket_levels


def _get_date_range(start, end):
    return pd.date_range(start, end, freq='MS')  # .to_pydatetime()


def _date_to_string(x):
    return f"{x.year}-{str(x.month).zfill(2)}"


def _month_diff(start_date, end_date):
    if end_date is None or start_date is None:
        return 0
    else:
        return (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)


def compute_monthly_targets(available_envelopes, targets, remaining_months):
    available = available_envelopes.filter(targets.index, axis=0).apply(pd.to_numeric, downcast='float')
    targets.columns = available.columns
    remaining_months.columns = available.columns
    div_months = remaining_months.add(1)

    shifted = targets.apply(pd.to_numeric, downcast='float').add(available.shift(periods=1, axis='columns').mul(-1),
                                                                 fill_value=0)
    target_monthly = shifted[shifted > 0].div(div_months[div_months > 0])

    return target_monthly


def merge_all_targets(data):
    return pd.concat(data, axis=1).swaplevel(0, 1, axis=1).sort_index(axis=0).sort_index(axis=1).reindex(axis=1)


def merge_dfs(dataframes):
    return pd.concat(dataframes, axis=1).swaplevel(0, 1, axis=1).reindex(axis=1)


def compute_progress(target, ref_amount):
    target_df = merge_dfs({'amount': target, 'ref_amount': ref_amount.filter(target.index, axis=0)})
    return target_df.fillna(Decimal('0.00'))


def interval_adapter(interval: OwnInterval) -> FavaInterval:
    if interval == OwnInterval.DAY:
        return FavaInterval.DAY
    if interval == OwnInterval.WEEK:
        return FavaInterval.WEEK
    if interval == OwnInterval.MONTH:
        return FavaInterval.MONTH
    if interval == OwnInterval.QUARTER:
        return FavaInterval.QUARTER
    if interval == OwnInterval.YEAR:
        return FavaInterval.YEAR


def spending_to_fava_budget_adapter(spending_targets: List[BaseTarget]) -> BudgetDict:
    budgets: BudgetDict = defaultdict(list)
    for t in spending_targets:
        b = Budget(account=t.account,
                   date_start=t.start_date,
                   number=t.amount.number,
                   currency=t.amount.currency,
                   period=interval_adapter(t.recur_interval))
        budgets[b.account].append(b)
    return budgets


def get_targets(targets, rem_months, targets_monthly, envelopes):

    #targets, rem_months, targets_monthly = self.parse_budget_goals(date_start, date_end, target_entries)
    available = envelopes.xs(key='available', level=1, axis=1)

    targets_by_month = compute_monthly_targets(available, targets, rem_months)
    targets_monthly = targets_monthly.apply(pd.to_numeric, downcast='float')
    targets_monthly.columns = targets_by_month.columns

    targets_by_month = targets_by_month.add(targets_monthly, fill_value=0)
    t = compute_progress(targets, available)
    t.name = 'target'

    budgeted = envelopes.xs(key='budgeted', level=1, axis=1)
    spent = envelopes.xs(key='activity', level=1, axis=1)

    tm = compute_progress(targets_by_month, budgeted) #.add(spent, fill_value=0))
    tm.name = 'target_m'
    return t.applymap(Decimal), tm.applymap(Decimal)


class EnvelopesWithGoals:
    def __init__(self, entries, errors, options_map, currency):

        self.entries = entries
        self.errors = errors
        self.options_map = options_map
        self.price_map = prices.build_price_map(entries)
        self.acctypes = options.get_account_types(options_map)
        self.currency = currency

        decimal_precison = '0.00'
        self.Q = Decimal(decimal_precison)

    def get_spending_goals(self, date_start, date_end, mappings, multi_level_index, envelopes, current_month, entries=None):
        entries = self.entries if entries is None else entries
        goals_for_accounts = self.parse_spending_targets(date_start, date_end, entries)
        full_hierarchy = add_bucket_levels(goals_for_accounts, multi_level_index, mappings)

        # these are float64 (IF EMPTY)
        spent = envelopes.xs(key='activity', level=1, axis=1)
        # these are decimals
        budgeted = envelopes.xs(key='budgeted', level=1, axis=1)
        available = envelopes.xs(key='available', level=1, axis=1)
        avail_som = available.add(spent.mul(-1), fill_value=0)

        ref_amount = pd.concat([avail_som.filter(items=[c for c in avail_som.columns if c <= current_month]),
                                budgeted.filter(items=[c for c in budgeted.columns if c > current_month])], axis=1)

        spending_goals = compute_progress(full_hierarchy.groupby(level=0, axis=0).sum(numeric_only=False), ref_amount)
        spending_goals.name = 'spend'
        return full_hierarchy, spending_goals


    def budget_to_dataframe(self, start_date, end_date, budgets):
        all_months_data = dict()
        dr = _get_date_range(start_date, end_date)
        for d in dr:
            start = d.date()
            end = start + relativedelta(months=1)
            values = dict()
            for be in budgets:
                # note: calculate_budget_children would also include the sub-categories, which is not what we want here
                cb = calculate_budget(budgets, be, start, end)
                values[be] = cb[self.currency].quantize(self.Q)
            all_months_data[_date_to_string(d)] = values

        return pd.DataFrame(all_months_data).sort_index()

    def parse_fava_budget(self, start_date, end_date):
        custom = [e for e in self.entries if isinstance(e, Custom)]
        budgets, errors = parse_budgets(custom)
        return self.budget_to_dataframe(start_date, end_date, budgets)

    def parse_spending_targets(self, start_date, end_date, target_entries):
        parser = NeededForSpendingTargetParser()
        targets = parser.parse_entries(target_entries)
        budgets = spending_to_fava_budget_adapter(targets)
        return self.budget_to_dataframe(start_date, end_date, budgets)

    def parse_budget_goals(self, start_date, end_date, target_entries):
        dates = _get_date_range(start_date, end_date)
        parser = EnvelopeGoalTargetParser()
        targets = parser.parse_entries(target_entries)

        target_amounts = pd.DataFrame(columns=dates)
        monthly_targets = pd.DataFrame(columns=dates)
        months_remaining = pd.DataFrame(columns=dates)

        for item in targets:
            a = item.account
            if item.target:
                amount = item.target.number
                start = _date_to_string(item.start_date)
                end = _date_to_string(item.target_date) if item.target_date is not None else None
                target_amounts.loc[a, start:end] = amount

                if end is not None:
                    mr = {r: _month_diff(r, item.target_date) for r in dates if
                          item.start_date <= r <= item.target_date}
                    if mr:
                        months_remaining.loc[a, mr.keys()] = mr
            elif item.monthly_target:
                amount = item.monthly_target.number
                start = _date_to_string(item.start_date)
                end = _date_to_string(item.target_date) if item.target_date is not None else None
                monthly_targets.loc[a, start:end] = amount

        return target_amounts.dropna(axis=0, how='all'), months_remaining, monthly_targets
