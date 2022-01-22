import datetime
import unittest
import textwrap

from beancount import loader
from beancount.core.amount import Amount
from beancount.core.number import D
from beancount.parser import cmptest
from fava.core.budgets import Budget
from fava.util.date import Interval
from pandas._testing import assert_frame_equal

from envelope_budget.modules.goals import Target, SpendingTarget
from envelope_budget.modules.goals.beancount_goals import EnvelopesWithGoals
from envelope_budget.modules.goals.target_types.fava_budget import FavaBudgetTargetParser
from envelope_budget.modules.goals.target_types.goal import EnvelopeGoalTargetParser, NeededForSpendingTargetParser


class TargetFromFavaBudgetTests(cmptest.TestCase):
    def test_spending_target_equal_budgets(self):
        input_text = textwrap.dedent("""
        
            2011-01-01 open Assets:Checking
            2011-01-01 open Assets:Shared
            2011-01-01 open Expenses:Coffee
            2011-01-01 open Expenses:Books
            2011-01-01 open Expenses:Groceries
            2011-01-01 open Expenses:Electricity
            2011-01-01 open Expenses:Holiday
            
            2012-01-01 custom "budget" Expenses:Coffee       "daily"         4.00 EUR
            2013-01-01 custom "budget" Expenses:Books        "weekly"       20.00 EUR
            2014-02-10 custom "budget" Expenses:Groceries    "monthly"      40.00 EUR
            2015-05-01 custom "budget" Expenses:Electricity  "quarterly"    85.00 EUR
            2016-06-01 custom "budget" Expenses:Holiday      "yearly"     2500.00 EUR
            
            2012-01-01 custom "envelope" "spending" Expenses:Coffee       "daily"         4.00 EUR
            2013-01-01 custom "envelope" "spending" Expenses:Books        "weekly"       20.00 EUR
            2014-02-10 custom "envelope" "spending" Expenses:Groceries    "monthly"      40.00 EUR
            2015-05-01 custom "envelope" "spending" Expenses:Electricity  "quarterly"    85.00 EUR
            2016-06-01 custom "envelope" "spending" Expenses:Holiday      "yearly"     2500.00 EUR "by" 2016-12-15
        """)
        entries, errors, options_map = loader.load_string(input_text)
        self.assertFalse(errors)

        bg = EnvelopesWithGoals(entries, errors, options_map, 'EUR')
        df = bg.parse_fava_budget('2022-01-01', '2022-04-01')
        self.assertIsNotNone(df)
        print(df)

        df2 = bg.parse_spending_targets('2022-01-01', '2022-04-01', entries)
        print(df2)

        assert_frame_equal(df, df2)

    def test_spending_target_new(self):
        input_text = textwrap.dedent("""

            2011-01-01 open Assets:Checking
            2011-01-01 open Assets:Shared
            2011-01-01 open Expenses:Coffee
            2011-01-01 open Expenses:Books
            2011-01-01 open Expenses:Groceries
            2011-01-01 open Expenses:Electricity
            2011-01-01 open Expenses:Holiday
            
            2012-01-01 custom "envelope" "spending" Expenses:Coffee       "daily"         4.00 EUR
            2013-01-01 custom "envelope" "spending" Expenses:Books        "weekly"       20.00 EUR
            2014-02-10 custom "envelope" "spending" Expenses:Groceries    "monthly"      40.00 EUR
            2015-05-01 custom "envelope" "spending" Expenses:Electricity  "quarterly"    85.00 EUR
            2016-06-01 custom "envelope" "spending" Expenses:Holiday      "yearly"     2500.00 EUR "by" 2016-12-15

        """)
        entries, errors, options_map = loader.load_string(input_text)
        self.assertFalse(errors)

        parser = NeededForSpendingTargetParser()
        targets = parser.parse_entries(entries)
        self.assertIsNotNone(targets)

        for x in targets:
            print(x)

        expected = [
            SpendingTarget(datetime.date(2012, 1, 1), 'Expenses:Coffee', amount=Amount(D('4.00'), 'EUR'),
                           interval=Interval.DAY),

            SpendingTarget(datetime.date(2013, 1, 1), 'Expenses:Books', amount=Amount(D('20.00'), 'EUR'),
                           interval=Interval.WEEK),

            SpendingTarget(datetime.date(2014, 2, 10), 'Expenses:Groceries', amount=Amount(D('40.00'), 'EUR'),
                           interval=Interval.MONTH),

            SpendingTarget(datetime.date(2015, 5, 1), 'Expenses:Electricity', amount=Amount(D('85.00'), 'EUR'),
                           interval=Interval.QUARTER),

            SpendingTarget(datetime.date(2016, 6, 1), 'Expenses:Holiday', amount=Amount(D('2500.00'), 'EUR'),
                           interval=Interval.YEAR)
        ]

        self.assertCountEqual([f'{e}' for e in expected], [f'{t}' for t in targets])


if __name__ == '__main__':
    unittest.main()
