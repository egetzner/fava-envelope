import argparse
import logging

from envelope_budget.modules.beancount_envelope import BeancountEnvelope
from envelope_budget.modules.goals.beancount_goals import EnvelopesWithGoals, merge_all_targets
from envelope_budget.modules.hierarchy.beancount_entries import TransactionParser

try:
    import ipdb
    #ipdb.set_trace()
except ImportError:
    pass

from beancount import loader

def main():
    logging.basicConfig(level=logging.INFO,
                        format='%(levelname)-8s: %(message)s')
    parser = argparse.ArgumentParser(description="beancount_envelope")
    parser.add_argument('filename', help='path to beancount journal file')
    args = parser.parse_args()

    # Read beancount input file
    entries, errors, options_map = loader.load_file(args.filename)
    module = BeancountEnvelope(entries, errors, options_map)
    parser = TransactionParser(entries, errors, options_map,
                               currency=module.currency,
                               budget_accounts=module.budget_accounts,
                               mappings=module.mappings)

    income_tables, envelope_tables, all_activity, current_month = module.envelope_tables(parser)
    bg = EnvelopesWithGoals(entries, errors, options_map, module.currency)

    detail_goals, spending = bg.get_spending_goals(module.date_start, module.date_end, module.mappings, all_activity.index, envelope_tables, current_month)
    targets, monthly_target = bg.get_targets(module.date_start, module.date_end, envelope_tables)
    merged = merge_all_targets({'needed for spending': spending, 'saving balance': targets, 'monthly savings builder': monthly_target})

    logging.info(envelope_tables.loc[:, '2021-10'].to_string())
    logging.info(merged.loc[:, '2021-10'].to_string())

    if len(errors) == 0:
        logging.debug('no errors found')

    for e in errors:
        logging.error(e)


if __name__ == '__main__':
    main()
