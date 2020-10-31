import argparse
import logging
import coloredlogs

from envelope_budget.modules.envelope_extension import EnvelopeWrapper

try:
    import ipdb
    #ipdb.set_trace()
except ImportError:
    pass

from beancount import loader

from fava_envelope.modules.beancount_envelope import BeancountEnvelope

def main():
    logging.basicConfig(level=logging.DEBUG,
                        format='%(levelname)-8s:\n%(message)s')

    coloredlogs.install(level=logging.DEBUG, fmt='%(asctime)s,%(msecs)03d %(hostname)s %(name)s[%(process)d] %(levelname)s\n%(message)s')

    parser = argparse.ArgumentParser(description="beancount_envelope")
    parser.add_argument('filename', help='path to beancount journal file')
    args = parser.parse_args()

    # Read beancount input file
    entries, errors, options_map = loader.load_file(args.filename)
    ext = BeancountEnvelope(entries, errors, options_map)
    ge = EnvelopeWrapper(entries, errors, options_map, ext)

    summary = ge.get_summary("2020-10")
    logging.debug(summary)
    logging.debug(summary.to_be_budgeted)

    summary = ge.get_summary("2020-12")
    logging.debug(summary.to_be_budgeted)

    if len(errors) == 0:
        logging.debug('no errors found')

    for e in errors:
        logging.error(e)


if __name__ == '__main__':
    main()
