"""
"""

from fava.ext import FavaExtensionBase
from beancount.core.number import Decimal, D
from beancount.core import data


from fava_envelope.modules.beancount_envelope import BeancountEnvelope

from datetime import date
import collections
import traceback

LoadError = collections.namedtuple('LoadError', 'source message entry')

class EnvelopeBudgetColor(FavaExtensionBase):
    '''
    '''
    report_title = "Envelope Budget (Color)"

    def generate_budget_df(self):

        self.income_tables = None
        self.envelope_tables = None
        self.current_month = None

        self.ledger.errors = list(filter(lambda i: not (type(i) is LoadError), self.ledger.errors))

        try:
            module = BeancountEnvelope(
                self.ledger.entries,
                self.ledger.errors,
                self.ledger.options
            )
            self.income_tables, self.envelope_tables, self.current_month = module.envelope_tables()

        except:
            self.ledger.errors.append(LoadError(data.new_metadata("<fava-envelope2>", 0), traceback.format_exc(), None))

    def get_budgets_months_available(self):
            self.generate_budget_df()
            return [] if self.income_tables is None else self.income_tables.columns

    def get_current_month(self, period):
        today = date.today()

        if period is not None:
            return period
        else:
            year = today.year
            month = today.month
            return f'{year:04}-{month:02}'

    def generate_income_query_tables(self, month):

        income_table_types = []
        income_table_types.append(("Name", str(str)))
        income_table_types.append(("Amount", str(Decimal)))

        income_table_rows = []

        if month is not None and self.income_tables is not None:
            row = {}
            income_table_rows.append({
                "Name": "Funds for month",
                "Amount": self.income_tables[month]["Avail Income"]
            })
            income_table_rows.append({
                "Name": "Overspent in prev month",
                "Amount": self.income_tables[month]["Overspent"]
            })
            income_table_rows.append({
                "Name": "Budgeted for month",
                "Amount": self.income_tables[month]["Budgeted"]
            })
            income_table_rows.append({
                "Name": "To be budgeted for month",
                "Amount": self.income_tables[month]["To Be Budgeted"]
            })
            income_table_rows.append({
                "Name": "Budgeted in the future",
                "Amount": self.income_tables[month]["Budgeted Future"]
            })

        return (income_table_types, income_table_rows)

    def generate_envelope_query_tables(self, month):

        envelope_table_types = []
        envelope_table_types.append(("Account", str(str)))
        envelope_table_types.append(("Budgeted", str(Decimal)))
        envelope_table_types.append(("Activity", str(Decimal)))
        envelope_table_types.append(("Available", str(Decimal)))

        envelope_table_rows = []

        if month is not None and self.envelope_tables is not None:
            for index, e_row in self.envelope_tables.iterrows():
                row = {}
                row["Account"] = index
                row["Budgeted"] = e_row[month, "budgeted"]
                row["Activity"] = e_row[month, "activity"]
                row["Available"] = e_row[month, "available"]
                envelope_table_rows.append(row)

        return (envelope_table_types, envelope_table_rows)
