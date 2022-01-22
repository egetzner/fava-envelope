import unittest
import textwrap

from beancount import loader
from beancount.parser import cmptest

from envelope_budget.modules.goals.beancount_goals import EnvelopesWithGoals


class TargetFromScheduledTransactionTests(cmptest.TestCase):
    def test_target(self):
        input_text = textwrap.dedent("""
        
            2011-01-01 open Assets:Checking
            2011-01-01 open Assets:Shared
            2011-01-01 open Expenses:Rent
            
            2022-01-01 ? "Something" #scheduled
              Expenses:Rent   50 EUR
              Assets:Shared
            
            2022-02-01 ? "Something" #scheduled
              Expenses:Rent   50 EUR
              Assets:Shared
        
            2022-03-01 ? "Something" #scheduled
              Expenses:Rent   50 EUR
              Assets:Shared
        """)
        entries, errors, options_map = loader.load_string(input_text)
        self.assertFalse(errors)
        self.assertEqualEntries("""
    
            2011-01-01 open Assets:Checking
            2011-01-01 open Assets:Shared
            2011-01-01 open Expenses:Rent
    
            2022-01-01 ? "Something" #scheduled
              Expenses:Rent      50 EUR
              Assets:Shared     -50 EUR
            
            2022-02-01 ? "Something" #scheduled
              Expenses:Rent      50 EUR
              Assets:Shared     -50 EUR
        
            2022-03-01 ? "Something" #scheduled
              Expenses:Rent      50 EUR
              Assets:Shared     -50 EUR
        """, entries)

        bg = EnvelopesWithGoals(entries, errors, options_map, 'EUR')
        goals = bg.parse_budget_goals('2022-01-01', '2022-04-01', None)
        self.assertIsNotNone(goals)
        print(goals)

if __name__ == '__main__':
    unittest.main()
