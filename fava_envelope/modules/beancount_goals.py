
from fava.core.budgets import parse_budgets, calculate_budget

import logging
import pandas as pd
from dateutil.relativedelta import relativedelta

from beancount.core.number import Decimal
from beancount.core import prices
from beancount.core.data import Custom
from beancount.parser import options


def _get_date_range(start, end):
    return pd.date_range(start, end, freq='MS')#.to_pydatetime()


def _date_to_string(x):
    return f"{x.year}-{str(x.month).zfill(2)}"


def compute_targets(tables, all_activity, goals_with_buckets, current_month):
    goals = goals_with_buckets.sum(axis=0, level=0)
    spent = all_activity.sum(axis=0, level=0)  # tables.xs(key='activity', level=1, axis=1)
    budgeted = tables.xs(key='budgeted', level=1, axis=1)
    available = tables.xs(key='available', level=1, axis=1)
    avail_som = available.add(spent.mul(-1), fill_value=Decimal(0.0))

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
