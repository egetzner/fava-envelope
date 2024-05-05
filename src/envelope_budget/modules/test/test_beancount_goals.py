from decimal import Decimal

import numpy
from beancount import loader

import unittest
import numpy as np
import pandas as pd
import datetime as dt

from envelope_budget import BeancountEnvelope
from envelope_budget.modules.goals.beancount_goals import compute_monthly_targets, EnvelopesWithGoals, get_targets
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
        entries, errors, options_map = (loader
                                        .load_file('../../../../test/testdata/beancount.2022/root_ledger.beancount'))
        module = BeancountEnvelope(entries, errors, options_map, budget_postfix="_private",
                                   today=dt.date(2022,6,10))
        parser = TransactionParser(entries, errors, options_map,
                                   currency=module.currency,
                                   budget_accounts=module.budget_accounts,
                                   mappings=module.mappings)

        income_tables, envelope_tables, all_activity, current_month = module.envelope_tables(parser)

        # IMPORTANT: if this is empty, it defaults to type float64, which cannot be added.
        from_accounts = all_activity.groupby(axis=0, level=0).sum(numeric_only=False)
        # from_buckets = envelope_tables.xs(key='activity', level=1, axis=1)
        # logging.info(from_buckets.eq(from_accounts).all(axis=1))

        budgeted = envelope_tables.xs(key='budgeted', level=1, axis=1)
        available = envelope_tables.xs(key='available', level=1, axis=1)

        all_data = pd.concat({'activity': from_accounts, 'budgeted': budgeted, 'available': available}, axis=1)
        bucket_data = all_data.swaplevel(1, 0, axis=1).fillna(Decimal('0.00'))

        bg = EnvelopesWithGoals(entries, errors, options_map, module.currency)

        detail_goals, spending = bg.get_spending_goals(module.date_start, module.date_end, module.mappings,
                                                       all_activity.index, bucket_data, current_month)

        print(bucket_data['2022-06'])

        targets, rem_months, targets_monthly = bg.parse_budget_goals(module.date_start, module.date_end, entries)

        print(targets)
        print(rem_months)
        print(targets_monthly)
        print(bucket_data)

        targets, monthly_target = get_targets(targets, rem_months, targets_monthly, bucket_data)

        print(targets['2022-06'])
        print(monthly_target['2022-06'])

        months = targets.columns.get_level_values(level=0)
        monthly_target_months = monthly_target.columns.get_level_values(level=0)
        self.assertListEqual(list(months.values), list(monthly_target_months.values))

    def test_monthly_targets_ref_amount(self):
        # arrange
        columns = ['2021-01', '2021-02']

        data = {'Expenses:DiningOut': {'activity': Decimal('-50.10'),
                                       'budgeted': Decimal('30'),
                                       'available': Decimal('37.60')},
                'Expenses:Other': {'activity': Decimal('0.0'),
                                   'budgeted': Decimal('100'),
                                   'available': Decimal('200')}}

        jan = pd.DataFrame(data)
        jan.name = '2021-01'

        data_second = {'Expenses:DiningOut': {'activity': Decimal('-15'),
                                       'budgeted': Decimal('20'),
                                       'available': Decimal('42.6')},
                       'Expenses:Other': {'activity': Decimal('0.0'),
                                          'budgeted': Decimal('101'),
                                          'available': Decimal('301')}}

        feb = pd.DataFrame(data_second)
        feb.name = '2021-02'

        envelopes = pd.concat([jan, feb], keys=columns).transpose()
        print(envelopes)

        targets = pd.DataFrame(data={"Expenses:Other": ['1000', '1000']}).transpose()
        targets.columns=columns

        rem_months = pd.DataFrame(data={"Expenses:Other": [4, 3]}).transpose()
        rem_months.columns=columns

        targets_monthly = pd.DataFrame(data={'Expenses:DiningOut': [Decimal(30), Decimal(30)]}).transpose()
        targets_monthly.columns=columns

        # act
        res_target, res_target_monthly = get_targets(targets, rem_months, targets_monthly, envelopes)

        print("----------- ASSERT -------")
        # assert
        #print(res_target)
        #print(res_target_monthly)
        print(res_target_monthly)
        #print(res_target_monthly.loc['Expenses:Other'])

        #expected
        expected_jan = pd.DataFrame(data={'Expenses:DiningOut': {'amount': Decimal('30'), 'ref_amount': Decimal('30')},
                                          'Expenses:Other': {'amount': Decimal('200'), 'ref_amount': Decimal('100')}}).transpose()
        expected_feb = pd.DataFrame(data={'Expenses:DiningOut': {'amount': Decimal('30'), 'ref_amount': Decimal('20')},
                                          'Expenses:Other': {'amount': Decimal('200'), 'ref_amount': Decimal('101')}}).transpose()

        pd.testing.assert_frame_equal(expected_jan, res_target_monthly['2021-01'])
        pd.testing.assert_frame_equal(expected_feb, res_target_monthly['2021-02'])

    def test_compute_monthly_targets(self):
        # arrange
        columns = ['2021-01', '2021-02']

        envelopes = pd.DataFrame(data={'Expenses:Bills': [Decimal('-3.90'), Decimal('-13.90')],
                                       'Expenses:Housing': [Decimal('200'), Decimal('500')],
                                       'SinkingFund:Furnishing': [Decimal('0'), Decimal('75')],
                                       'Wishlist:Loungewear': [Decimal('0'), Decimal('63.67')],
                                       'Expenses:IncomeTax': [Decimal('1200'), Decimal('3200')]}).transpose()

        envelopes.columns = columns
        envelopes.name = "Envelopes"

        targets = pd.DataFrame(data={'Wishlist:Loungewear': [Decimal(120), Decimal(120)],
                                     'Expenses:IncomeTax': [np.nan, Decimal(3200.0)]}).transpose()
        targets.columns = columns
        targets.name = "Targets"

        remaining_months = pd.DataFrame(data={'Expenses:IncomeTax': [1, 0]}).transpose()
        remaining_months.columns = columns
        remaining_months.name = "Remaining Months"

        print("----------- Arrange ------------")
        print(envelopes.to_string())
        #print_types(envelopes, "envelopes")
        print(targets.to_string())
        #print_types(targets, "targets")
        print(remaining_months.to_string())
        #print_types(remaining_months, "remaining months")

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
        self.assertIsInstance(tm['2021-02']['Expenses:IncomeTax'], float)
