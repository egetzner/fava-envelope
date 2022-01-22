import datetime
import unittest
import textwrap

from beancount import loader
from beancount.core.amount import Amount
from beancount.core.number import D
from beancount.parser import cmptest

from envelope_budget.modules.goals import Target
from envelope_budget.modules.goals.beancount_goals import EnvelopesWithGoals
from envelope_budget.modules.goals.target_types.goal import EnvelopeGoalTargetParser


class TargetFromEnvelopeGoalsTests(cmptest.TestCase):
    def test_target_existing(self):
        input_text = textwrap.dedent("""
        
            2011-01-01 open Assets:Checking
            2011-01-01 open Assets:Shared
            2011-01-01 open Expenses:Rent
            2011-01-01 open Assets:EmergencyFund
            2011-01-01 open Expenses:Holiday
            
            2020-01-01 custom "envelope_private" "target" Assets:EmergencyFund 5000 EUR
            2020-01-01 custom "envelope_private" "target" Expenses:Holiday 150 EUR "by" 2020-12-15
            2020-01-01 custom "envelope_shared" "target" Expenses:Rent "monthly" 1000 EUR
            
        """)
        entries, errors, options_map = loader.load_string(input_text)
        self.assertFalse(errors)

        bg = EnvelopesWithGoals(entries, errors, options_map, 'EUR')
        (df1, df2, df3) = bg.parse_budget_goals('2022-01-01', '2022-04-01', entries)
        self.assertIsNotNone(df1)
        self.assertIsNotNone(df2)  # TODO: Holiday goal is not reflected, maybe because we don't have a budget.
        self.assertIsNotNone(df3)
        print(df1)
        print(df2)
        print(df3)

    def test_target_new(self):
        input_text = textwrap.dedent("""

            2011-01-01 open Assets:Checking
            2011-01-01 open Assets:Shared
            2011-01-01 open Expenses:Rent
            2011-01-01 open Assets:EmergencyFund
            2011-01-01 open Expenses:Holiday

            2020-01-01 custom "envelope_private" "target" Assets:EmergencyFund 5000 EUR
            2020-01-01 custom "envelope_private" "target" Expenses:Holiday 150 EUR "by" 2020-12-15
            2020-01-01 custom "envelope_shared" "target" Expenses:Rent "monthly" 1000 EUR

        """)
        entries, errors, options_map = loader.load_string(input_text)
        self.assertFalse(errors)

        targetParser = EnvelopeGoalTargetParser()
        targets = targetParser.parse_entries(entries)

        expected = [Target(datetime.date(2020, 1, 1), 'Assets:EmergencyFund', Amount(D(5000), 'EUR')),
                    Target(datetime.date(2020, 1, 1), 'Expenses:Rent', monthly_amount=Amount(D(1000), 'EUR')),
                    Target(datetime.date(2020, 1, 1), 'Expenses:Holiday', Amount(D(150), 'EUR'), by_date=datetime.date(2020, 12, 15))]

        for x in targets:
            print(x)

        self.assertEqual(3, len(targets))
        self.assertCountEqual([f'{x}' for x in expected],[f'{x}' for x in targets])


if __name__ == '__main__':
    unittest.main()
