import datetime
from decimal import Decimal

import numpy
from beancount import loader

import unittest
import numpy as np
import pandas as pd

from envelope_budget import BeancountEnvelope
from envelope_budget.modules.goals.beancount_goals import compute_monthly_targets, EnvelopesWithGoals
from envelope_budget.modules.hierarchy.beancount_entries import TransactionParser


def print_types(df, name):
    print(f"---- dataframe types: {name} ----")
    for row in df.iterrows():
        print(f'key: {row[0]}')
        for value in row[1].values:
            print(f"value: {value} - type: {type(value)}")
    print(" ------------ ")


class TestGoals(unittest.TestCase):

    def test_get_targets_integration(self):
        entries, errors, options_map = loader.load_file('/data/Documents/beancount/root_ledger.beancount')
        module = BeancountEnvelope(entries, errors, options_map, None)
        parser = TransactionParser(entries, errors, options_map,
                                   currency=module.currency,
                                   budget_accounts=module.budget_accounts,
                                   mappings=module.mappings)

        income_tables, envelope_tables, all_activity, current_month = module.envelope_tables(parser)
        bg = EnvelopesWithGoals(entries, errors, options_map, module.currency)

        detail_goals, spending = bg.get_spending_goals(module.date_start, module.date_end, module.mappings,
                                                       all_activity.index, envelope_tables, current_month)
        targets, monthly_target = bg.get_targets(module.date_start, module.date_end, envelope_tables, entries)

        months = targets.columns.get_level_values(level=0)
        monthly_target_months = monthly_target.columns.get_level_values(level=0)
        self.assertListEqual(list(months.values), list(monthly_target_months.values))

    def test_compute_monthly_targets(self):
        columns = ['2021-01', '2021-02']

        envelopes = pd.DataFrame(data={'Expenses:Bills': [Decimal('-3.90'), Decimal('-13.90')],
                                       'Expenses:Housing': [Decimal('200'), Decimal('500')],
                                       'SinkingFund:Furnishing': [Decimal('0'), Decimal('75')],
                                       'Wishlist:Loungewear': [Decimal('0'), Decimal('63.67')],
                                       'Expenses:IncomeTax': [Decimal('1200'), Decimal('3200')]}).transpose()

        envelopes.columns = columns

        targets = pd.DataFrame(data={'Wishlist:Loungewear': [Decimal(120), Decimal(120)],
                                     'Expenses:IncomeTax': [np.nan, Decimal(3200.0)]}).transpose()
        targets.columns = columns

        remaining_months = pd.DataFrame(data={'Expenses:IncomeTax': [1, 0]}).transpose()
        remaining_months.columns = columns

        print("----------- Arrange ------------")
        print(envelopes)
        print_types(envelopes, "envelopes")
        print(targets)
        print_types(targets, "targets")
        print(remaining_months)
        print_types(remaining_months, "remaining months")

        print("----------- Act ------------")
        tm = compute_monthly_targets(envelopes, targets, remaining_months)
        print("----------- Assert ------------")
        print(tm)
        print_types(tm, "tm")
        assert pd.isna(tm['2021-01']['Expenses:IncomeTax'])
        self.assertIsInstance(tm['2021-01']['Expenses:IncomeTax'], numpy.float64)
        self.assertEqual(tm['2021-02']['Expenses:IncomeTax'], 2000.0)
        self.assertIsInstance(tm['2021-02']['Expenses:IncomeTax'], numpy.float64)
        assert pd.isna(tm['2021-01']['Wishlist:Loungewear'])
        assert pd.isna(tm['2021-02']['Wishlist:Loungewear'])

    def test_monthly_targets_exist_if_line_has_zero_amount_budgeted(self):
        print("----------- Arrange ------------")
        columns = ['2021-01', '2021-02']

        envelopes = pd.DataFrame(data={'Expenses:Bills': [Decimal('-3.90'), Decimal('-13.90')],
                                       'Expenses:IncomeTax': [Decimal('0'), Decimal('0')]}).transpose()

        envelopes.columns = columns

        targets = pd.DataFrame(data={'Expenses:IncomeTax': [np.nan, Decimal(3200.0)]}).transpose()
        targets.columns = columns

        remaining_months = pd.DataFrame(data={'Expenses:IncomeTax': [1, 0]}).transpose()
        remaining_months.columns = columns

        print("----------- Act ------------")
        tm = compute_monthly_targets(envelopes, targets, remaining_months)

        print("----------- Assert ------------")
        print(tm)
        print_types(tm, "tm")
        assert pd.isna(tm['2021-01']['Expenses:IncomeTax'])
        self.assertIsInstance(tm['2021-01']['Expenses:IncomeTax'], numpy.float64)
        self.assertEqual(tm['2021-02']['Expenses:IncomeTax'], 3200)
        self.assertIsInstance(tm['2021-02']['Expenses:IncomeTax'], numpy.float64)

    def test_target_exists_even_if_no_amount_budgeted(self):
        print("----------- Arrange ------------")
        columns = ['2021-01', '2021-02']

        envelopes = pd.DataFrame(data={'Expenses:Bills': [Decimal('-3.90'), Decimal('-13.90')]}).transpose()

        envelopes.columns = columns

        targets = pd.DataFrame(data={'Expenses:IncomeTax': [np.nan, Decimal(3200.0)]}).transpose()
        targets.columns = columns

        remaining_months = pd.DataFrame(data={'Expenses:IncomeTax': [1, 0]}).transpose()
        remaining_months.columns = columns

        print("----------- Act ------------")
        tm = compute_monthly_targets(envelopes, targets, remaining_months)

        print("----------- Assert ------------")
        print(tm)
        print_types(tm, "tm")
        assert pd.isna(tm['2021-01']['Expenses:IncomeTax'])
        self.assertEqual(tm['2021-02']['Expenses:IncomeTax'], 3200)
        self.assertIsInstance(tm['2021-02']['Expenses:IncomeTax'], numpy.float)
