import argparse
import logging
import datetime
from decimal import Decimal

from dateutil.relativedelta import relativedelta

from fava_envelope.modules.beancount_entries import BeancountEntries
from fava_envelope.modules.goal_envelopes import EnvelopeWrapper, AccountRow

try:
    import ipdb
    #ipdb.set_trace()
except ImportError:
    pass

import pandas as pd
from beancount import loader

from fava_envelope.modules.beancount_envelope import BeancountEnvelope

def main():
    logging.basicConfig(level=logging.INFO,
                        format='%(levelname)-8s: %(message)s')
    parser = argparse.ArgumentParser(description="beancount_envelope")
    parser.add_argument('filename', help='path to beancount journal file')
    args = parser.parse_args()

    # Read beancount input file
    entries, errors, options_map = loader.load_file(args.filename)
    ext = BeancountEnvelope(entries, errors, options_map)
    ge = EnvelopeWrapper(entries, errors, options_map, ext)

    next_month = datetime.datetime.today() + relativedelta(months=1)
    next_month_start = datetime.date(next_month.year, next_month.month, 1)
    eom_balance = ext.query_account_balances(next_month_start.strftime('%Y-%m-%d'))

    logging.info(f"Total Balance Accounts (end of month): {eom_balance}")

    income = ext.income_df.loc[:, ext.current_month]
    budget = ext.envelope_df.xs(key=ext.current_month, axis=1, level=0).sum()

    expected = round(Decimal(budget.available) - income['Budgeted Future'], 2)

    logging.info(f"Total Balance Budgeted (Available + Future): {expected} ({eom_balance - expected})")

    if len(errors) == 0:
        logging.debug('no errors found')

    for e in errors:
        logging.error(e)


if __name__ == '__main__':
    main()
