import argparse
import logging

from fava_envelope.modules.beancount_entries import BeancountEntries
from fava_envelope.modules.goal_envelopes import EnvelopeWrapper

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
    #parser = BeancountEntries(entries, errors, options_map, ext.currency, ext.budget_accounts, ext.mappings)
    #df1, df2, cm = ext.envelope_tables(parser)

    #logging.info(df1.loc['Avail Income'])
    #logging.info(df2.xs(axis=1, key='activity', level=1))

    ge = EnvelopeWrapper(entries, errors, options_map, ext)

    data = ge.get_inventories('2020-01', include_real_accounts=True)

    for k in data.values.keys():
        logging.info(k)

    logging.info(ge.mapped_accounts.get('Income'))
    logging.info(ge.mapped_accounts.get('IncomeDeductions'))

    if len(errors) == 0:
        logging.debug('no errors found')

    for e in errors:
        logging.error(e)


if __name__ == '__main__':
    main()
