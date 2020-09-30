import argparse
import logging
try:
    import ipdb
    #ipdb.set_trace()
except ImportError:
    pass

from beancount import loader

from fava_envelope.modules.beancount_envelope import BeancountEnvelope
from fava_envelope.modules.beancount_goals import BeancountGoal

def main():
    logging.basicConfig(level=logging.INFO,
                        format='%(levelname)-8s: %(message)s')
    parser = argparse.ArgumentParser(description="beancount_envelope")
    parser.add_argument('filename', help='path to beancount journal file')
    args = parser.parse_args()

    # Read beancount input file
    entries, errors, options_map = loader.load_file(args.filename)
    ext = BeancountEnvelope(entries, errors, options_map)
    df1, df2, cm, accounts = ext.envelope_tables()

    goals = BeancountGoal(entries, errors, options_map, "EUR")
    gdf = goals.parse_fava_budget(entries, start_date=ext.date_start, end_date=ext.date_end)
    act = goals.parse_transactions(ext.budget_accounts, ext.date_start, ext.date_end)
    mrg = goals.get_merged(ext.budget_accounts, ext.date_start, ext.date_end)
    mapped = goals.map_to_buckets(ext.mappings, mrg)

    original = df2.xs(level=1, key='activity', axis=1)
    from_goals = mapped.xs(level=1, key='activity', axis=1)

    logging.info(act)

    for index, row in original.eq(from_goals).iterrows():
        if not row.all():
            logging.info(f"MISMATCH: {index} in \t"
                         f"original: {index in original.index} "
                         f"goals: {index in from_goals.index}"
                         )

    if len(errors) == 0:
        logging.debug('no errors found')

    for e in errors:
        logging.error(e)


if __name__ == '__main__':
    main()
