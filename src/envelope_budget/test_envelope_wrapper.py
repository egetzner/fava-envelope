import logging
import unittest
import datetime as dt
import decimal

from beancount.core.inventory import Inventory

from envelope_budget import EnvelopeWrapper
from envelope_budget.modules.beancount_envelope import BeancountEnvelope
from envelope_budget.modules.goals.beancount_goals import EnvelopesWithGoals, merge_all_targets, get_targets
from envelope_budget.modules.hierarchy.beancount_entries import TransactionParser

try:
    import ipdb
    #ipdb.set_trace()
except ImportError:
    pass

from beancount import loader


class ExtensionTestCase(unittest.TestCase):
    def test_extension_2021(self):
        filename = '../../test/testdata/beancount.2021/root_ledger.beancount'

        # Read beancount input file
        entries, errors, options_map = loader.load_file(filename)
        module = BeancountEnvelope(entries, errors, options_map, budget_postfix='',
                                   today=dt.date(2021, 10, 1))

        ew = EnvelopeWrapper(entries, errors, options_map, module)
        pd = ew.get_inventories('2021-10', include_real_accounts=False)
        fun_money = pd.account_row('Expenses:FunMoney:EatingOut')
        print(fun_money)
        self.assertEqual("(-25.00 EUR)", f"{fun_money.spent}")
        self.assertEqual("(50 EUR)", f"{fun_money.budgeted}")
        self.assertEqual("(191.08 EUR)", f"{fun_money.available}")

    def test_extension_2023(self):
        filename = '../../test/testdata/beancount.2023/root_ledger.beancount'

        # Read beancount input file
        entries, errors, options_map = loader.load_file(filename)
        module = BeancountEnvelope(entries, errors, options_map,
                                   budget_postfix='_private',
                                   today=dt.date(2023, 4, 12))

        ew = EnvelopeWrapper(entries, errors, options_map, module)
        pd = ew.get_inventories('2023-04', include_real_accounts=False)
        self.assertNotEqual(0, len(pd.account_rows))
        print(f"Rows: {len(pd.account_rows)}")
        for row in pd.account_rows:
            print(pd.account_row(row))

    @unittest.skip("integration test, takes too long")
    def test_extension_integration(self):
        filename = '/net/frederick/Documents/Finanzen/beancount/root_ledger.beancount'

        # Read beancount input file
        entries, errors, options_map = loader.load_file(filename)
        module = BeancountEnvelope(entries, errors, options_map,
                                   budget_postfix='EUR',
                                   today=dt.date(2024, 5, 5))

        ew = EnvelopeWrapper(entries, errors, options_map, module)
        pd = ew.get_inventories('2024-04', include_real_accounts=False)
        self.assertNotEqual(0, len(pd.account_rows))

        st = ew.get_summary('2024-04')


if __name__ == '__main__':
    unittest.main()
