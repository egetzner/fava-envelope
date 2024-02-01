import unittest

from beancount.core.number import D

from envelope_budget import Target


class MyTestCase(unittest.TestCase):
    def test_Target(self):

        # arrange
        for gt in ['T', 'D', 'M', 'S']:
            # act
            t = Target(target=D('100'), ref_amount=D('50'), goal_type=gt)

            # assert
            self.assertEqual(t.goal_progress, D('0.5'))
            self.assertEqual('(100 EUR): (50.00% funded)', f'{t}')
            self.assertFalse(t.is_overfunded)
            self.assertFalse(t.is_funded)


if __name__ == '__main__':
    unittest.main()
