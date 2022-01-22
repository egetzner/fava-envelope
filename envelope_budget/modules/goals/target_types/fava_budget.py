from beancount.core.data import Custom

from fava.core.budgets import parse_budgets
from envelope_budget.modules.goals.target_types import TargetParser


class FavaBudgetTargetParser(TargetParser):

    def parse_entries(self, entries):
        custom = [e for e in entries if isinstance(e, Custom)]
        budgets, errors = parse_budgets(custom)

        return budgets
