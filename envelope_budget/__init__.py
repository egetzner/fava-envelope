"""
"""
import logging

from beancount.core.number import ZERO
from beancount.core.inventory import Inventory, Amount
from beancount.core import convert

import datetime

from fava.ext import FavaExtensionBase
from beancount.core.number import Decimal
from beancount.core import data

from fava_envelope.modules.beancount_envelope import BeancountEnvelope
from envelope_budget.modules.envelope_extension import EnvelopeWrapper, Target

import collections
import traceback

LoadError = collections.namedtuple('LoadError', 'source message entry')


class EnvelopeBudgetColor(FavaExtensionBase):
    '''
    '''
    report_title = "Envelope Budget*"

    def __init__(self, ledger, config=None):
        super().__init__(ledger, config)
        self.display_real_accounts = False
        self.envelopes: EnvelopeWrapper = EnvelopeWrapper([], [], [], None)

        self.income_tables = None

    def generate_budget_df(self):

        self.ledger.errors = list(filter(lambda i: not (type(i) is LoadError), self.ledger.errors))

        try:
            start_date = self.config.get('start')

            if start_date is not None:
                start_date = datetime.date.fromisoformat(start_date)

            future_months = self.config.get('future_months')
            future_rollover = self.config.get('future_rollover')
            show_real_accounts = self.config.get('show_real_accounts')

            module = BeancountEnvelope(
                self.ledger.entries,
                self.ledger.errors,
                self.ledger.options,
                start_date, future_months, future_rollover, show_real_accounts
            )

            self.envelopes = EnvelopeWrapper(self.ledger.entries, self.ledger.errors, self.ledger.options, module)
        except:
            self.ledger.errors.append(
                LoadError(data.new_metadata("<fava-envelope-gen>", 0), traceback.format_exc(), None))

    def is_current(self, period):
        return self.envelopes.current_month == period

    def get_budgets_months_available(self):
        return self.envelopes.get_budgets_months_available()

    def toggle_show_accounts(self):
        self.display_real_accounts = not self.display_real_accounts
        return self.display_real_accounts

    def set_show_accounts(self, show):
        if show:
            self.display_real_accounts = show == "True"
        return self.display_real_accounts

    def get_summary(self, month):
        logging.debug(f'get_summary {month}')
        return self.envelopes.get_summary(month) if self.envelopes.initialized else None

    def generate_income_query_tables(self, month):
        types = [('Amount', str(Decimal)), ('Name', str(str))]
        st = self.get_summary(month)
        return types, [{'Name': x[0], 'Amount': x[1]} for x in st.get_table().iteritems()] if st is not None else []

    # ----

    def make_table(self, period, show_accounts):
        self.ledger.errors = list(filter(lambda i: not (type(i) is LoadError), self.ledger.errors))
        try:
            #logging.info(f"period: {period}, show accounts: {show_accounts}")
            return self._make_table(period, show_accounts)
        except:
            self.ledger.errors.append(
                LoadError(data.new_metadata("<fava-envelope-table>", 0), traceback.format_exc(), None))

    def _make_table(self, period, show_accounts):
        """An account tree based on matching regex patterns."""

        self.set_show_accounts(show_accounts)

        self.generate_budget_df()

        today = datetime.date.today()

        if period is not None:
            year, month = (int(n) for n in period.split('-', 1))
        else:
            year = today.year
            month = today.month
            period = f'{year:04}-{month:02}'

        self.period_start = datetime.date(year, month, 1)
        self.period_end = datetime.date(year + month // 12, month % 12 + 1, 1)

        self.current_period = self.envelopes.get_inventories(period=period, include_real_accounts=self.display_real_accounts)
        return self.current_period, period

    def format_currency(self, value, currency=None, show_if_zero=False):
        if not value and not show_if_zero:
            return ""
        if value == ZERO:
            return self.ledger.format_decimal(ZERO, currency)
        return self.ledger.format_decimal(value, currency)

    def format_amount(self, amount, show_if_zero=False):
        if amount is None:
            return ""
        number, currency = amount
        if number is None:
            return ""
        if currency == "EUR":
            return self.format_currency(number, currency, show_if_zero)
        num = self.format_currency(number, currency, show_if_zero=True).replace('\xa0', '')
        return "{} {}\xa0".format(num, currency)

    def _ordering(self, a):
        return self.ledger.accounts[a.account].meta.get('ordering', 9999)

    def _name(self, a):
        meta = self.ledger.accounts[a.account].meta
        if 'name' in meta:
            return meta.get('name', a.account)

        return a.account.split(':')[-1]

    def _sort_subtree(self, root):
        children = list(root.values())
        children.sort(key=self._ordering)
        return children

    def _only_position(self, inventory):
        if inventory is None or inventory.is_empty():
            return Amount(ZERO, "EUR")
        currency ,= inventory.currencies()
        #currency = 'EUR'
        amount: Amount = inventory.get_currency_units(currency)
        return amount

    def account_row(self, a):
        return self.current_period.account_row(a)

    def _value(self, inventory: Inventory):
        return self._only_position(inventory)

    def _row_children(self, rows, a):
        sum = Inventory()
        all_matching = self.current_period.get_matching_rows(a)
        for sub in all_matching:
            item = sub.get(rows)
            if isinstance(item, Target):
                item = item.amount
            sum.add_inventory(item)
        return self._only_position(sum.reduce(convert.get_weight))

    def _is_leaf(self, a):
        return self.current_period.is_leaf(a)

    def _has_children(self, a):
        return sum(self._is_visible(c) for c in a.values())

    def _is_real_account(self, a):
        is_real = a.account in self.ledger.accounts.keys()
        return is_real

    def _is_visible(self, a):
        return self.current_period.is_visible(a, show_real=self.display_real_accounts)

    def _period_for(self, date):
        return date.strftime('%Y-%m')

    def month_name(self, period, fmt='%b %Y'):
        m = datetime.datetime.strptime(period, '%Y-%m')
        return m.strftime(fmt)

    def _prev_month(self):
        return self._period_for(self.period_start - datetime.timedelta(days=1))

    def _next_month(self):
        return self._period_for(self.period_end)

    def _date_range(self):
        end = self.period_end
        start = self.period_start
        if start.day == 1 and end.day == 1 and (end - start).days in range(28, 32):
            return start.strftime('%b %Y')
        return f'{start} - {end}'
