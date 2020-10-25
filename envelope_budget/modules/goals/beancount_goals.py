from fava.core.budgets import parse_budgets, calculate_budget

import pandas as pd
from dateutil.relativedelta import relativedelta

from beancount.core.number import Decimal
from beancount.core import prices
from beancount.core.data import Custom
from beancount.parser import options

from envelope_budget.modules.goals import goal


def _get_date_range(start, end):
    return pd.date_range(start, end, freq='MS')#.to_pydatetime()


def _date_to_string(x):
    return f"{x.year}-{str(x.month).zfill(2)}"


def _month_diff(start_date, end_date):
    if end_date is None or start_date is None:
        return 0
    else:
        return (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)


def merge_with_targets(buckets, targets, remaining_months):
    available = buckets.xs(key='available', level=1, axis=1).filter(targets.index, axis=0)
    budgeted = buckets.xs(key='budgeted', level=1, axis=1).filter(targets.index, axis=0)
    targets.columns = available.columns  # get rid of the pandas time range for now
    total_progress = available.div(targets)
    remaining_months.columns = available.columns
    div_months = remaining_months.add(1)

    shifted = targets.add(available.shift(periods=1, axis='columns').mul(-1))
    target_monthly = shifted[shifted > 0].div(div_months[div_months > 0])
    monthly_progress = budgeted.div(target_monthly[target_monthly > 0])

    total_merged = pd.concat({'target_total': targets,
                              'target_monthly': target_monthly,
                              'progress_total': total_progress,
                              'progress_monthly': monthly_progress
                              }, axis=1).swaplevel(0, 1, axis=1).sort_index(axis=1).reindex(axis=1)

    return total_merged


def merge_with_multihierarchy(tables, all_activity, goals_with_buckets, current_month):
    goals = goals_with_buckets.sum(axis=0, level=0)
    spent = all_activity.sum(axis=0, level=0)  # tables.xs(key='activity', level=1, axis=1)
    budgeted = tables.xs(key='budgeted', level=1, axis=1)
    available = tables.xs(key='available', level=1, axis=1)
    avail_som = available.add(spent.mul(-1), fill_value=0)

    funded = pd.concat([avail_som.filter(items=[c for c in avail_som.columns if c <= current_month]),
                        budgeted.filter(items=[c for c in budgeted.columns if c > current_month])], axis=1)
    funded = funded.fillna(Decimal(0.00))

    to_be_funded = goals.add(funded.mul(-1)).dropna()
    tbf = funded[funded != 0].div(goals[goals != 0])
    tbf[to_be_funded == 0] = 1
    progress = tbf.astype('float').round(decimals=2)
    is_funded = progress >= 1

    merged = pd.concat({'budgeted': budgeted,
                        'activity': spent,
                        'available': available,
                        'goals': goals,
                        'goal_funded': is_funded,
                        'goal_progress': progress}, axis=1)
    df = merged.swaplevel(0, 1, axis=1).sort_index(axis=1).reindex(axis=1)
    return df


class BeancountGoal:
    def __init__(self, entries, errors, options_map, currency):

        self.entries = entries
        self.errors = errors
        self.options_map = options_map
        self.price_map = prices.build_price_map(entries)
        self.acctypes = options.get_account_types(options_map)
        self.currency = currency

        decimal_precison = '0.00'
        self.Q = Decimal(decimal_precison)

    def parse_fava_budget(self, start_date, end_date):
        custom = [e for e in self.entries if isinstance(e, Custom)]
        budgets, errors = parse_budgets(custom)
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

    def parse_budget_goals(self, start_date, end_date):
        dates = _get_date_range(start_date, end_date)
        goals = goal.parse_goals(self.entries)
        target_amounts = pd.DataFrame(columns=dates)
        months_remaining = pd.DataFrame(columns=dates)

        for a in goals.keys():
            for item in goals[a]:
                amount = item.target_amount
                start = _date_to_string(item.start_date)
                end = _date_to_string(item.target_date) if item.target_date is not None else None
                target_amounts.loc[a, start:end] = amount

                if end is not None:
                    mr = {r: _month_diff(r, item.target_date) for r in dates if item.start_date <= r <= item.target_date}
                    if mr:
                        months_remaining.loc[a, mr.keys()] = mr

        return target_amounts.dropna(axis=0, how='all'), months_remaining

