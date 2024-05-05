import unittest
from beancount import loader
import envelope_budget.mapping as mapping


class MappingTest(unittest.TestCase):
    def test_mapping(self):

        entries, errors, _ = loader.load_file('../../example.beancount')

        mappings = mapping.retrieve_mappings_from_entries(entries, "envelope")
        accounts_to_map = ['Expenses:Housing:Rent']

        mappings = mapping.map_accounts_to_buckets(accounts_to_map, mappings, 'Expenses:Unmapped')

        self.assertEqual(['Expenses:Rent'], mappings)


if __name__ == '__main__':
    unittest.main()
