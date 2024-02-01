import argparse
import logging
try:
    import ipdb
    #ipdb.set_trace()
except ImportError:
    pass

from beancount import loader

from src.fava_envelope.modules.beancount_envelope import BeancountEnvelope

def main():
    logging.basicConfig(level=logging.INFO,
                        format='%(levelname)-8s: %(message)s')
    parser = argparse.ArgumentParser(description="beancount_envelope")
    parser.add_argument('filename', help='path to beancount journal file')
    args = parser.parse_args()

    # Read beancount input file
    entries, errors, options_map = loader.load_file(args.filename)
    ext = BeancountEnvelope(entries, options_map, None)
    df1, df2, df3 = ext.envelope_tables()
    #logging.info(df)
    print(df1)
    print(df2)
    print(df3)


if __name__ == '__main__':
    main()