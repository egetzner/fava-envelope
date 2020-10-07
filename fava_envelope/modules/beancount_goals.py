
from fava.core.budgets import parse_budgets, calculate_budget

import logging
import collections
import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta

from beancount.core.number import Decimal
from beancount.core import convert, prices, inventory, data, account_types, account
from beancount.core.data import Custom
from beancount.parser import options

from fava_envelope.modules.beancount_entries import BeancountEntries


def _get_date_range(start, end):
    return pd.date_range(start, end, freq='MS')#.to_pydatetime()


def _date_to_string(x):
    return f"{x.year}-{str(x.month).zfill(2)}"


def compute_targets(tables, goals_with_buckets):
    goals = goals_with_buckets.sum(axis=0, level=0)
    spent = tables.xs(key='activity', level=1, axis=1)
    budgeted = tables.xs(key='budgeted', level=1, axis=1)
    available = tables.xs(key='available', level=1, axis=1)
    originally_available = available + spent*-1
    target = goals - originally_available
    target.name = 'target'
    merged = pd.concat({'budgeted':budgeted, 'activity':spent, 'available':available, 'goals':goals, 'target':target}, axis=1)
    df = merged.swaplevel(0, 1, axis=1).sort_index(axis=1).reindex(axis=1).fillna(0)
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

    def get_merged(self, module: BeancountEntries, start, end):
        gdf = self.parse_fava_budget(start_date=start, end_date=end)
        act = module.parse_transactions(start, end)

        mrg = pd.concat({'goals': gdf, 'activity': act.sum(level=1, axis=0)}, axis=1)
        mrg = mrg.swaplevel(0, 1, axis=1).reindex()
        return mrg.sort_index().fillna(0)

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
