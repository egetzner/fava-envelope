import argparse
import logging

from fava_envelope.modules.goal_envelopes import EnvelopeWrapper

try:
    import ipdb
    #ipdb.set_trace()
except ImportError:
    pass

import pandas as pd
from beancount import loader

from fava_envelope.modules.beancount_envelope import BeancountEnvelope
from fava_envelope.modules.beancount_goals import BeancountGoal
from fava_envelope.modules.beancount_hierarchy import map_accounts_to_bucket, get_hierarchy, map_df_to_buckets

def main():
    logging.basicConfig(level=logging.INFO,
                        format='%(levelname)-8s: %(message)s')
    parser = argparse.ArgumentParser(description="beancount_envelope")
    parser.add_argument('filename', help='path to beancount journal file')
    args = parser.parse_args()

    # Read beancount input file
    entries, errors, options_map = loader.load_file(args.filename)
    ext = BeancountEnvelope(entries, errors, options_map)
    df1, df2, cm = ext.envelope_tables()

    ge = EnvelopeWrapper(entries, errors, options_map, ext)
    logging.info(ge.mapped_accounts)

    if len(errors) == 0:
        logging.debug('no errors found')

    for e in errors:
        logging.error(e)


if __name__ == '__main__':
    main()
