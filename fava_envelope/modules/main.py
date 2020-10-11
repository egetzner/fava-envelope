import argparse
import logging

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

    logging.info(ge.bucket_data.xs(key='available', axis=1, level=1).dropna())
    logging.info(ge.account_data.xs(key='goals', axis=1, level=1).dropna())
    data = ge.get_inventories('2020-07', include_real_accounts=True)
    logging.info(data.account_row('Income:Deduction'))

    if len(errors) == 0:
        logging.debug('no errors found')

    for e in errors:
        logging.error(e)


if __name__ == '__main__':
    main()
