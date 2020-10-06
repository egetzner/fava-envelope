# Debug
try:
    import ipdb
except ImportError:
    pass

from fava_envelope.modules.beancount_entries import BeancountEntries

import datetime
import collections
import logging
import pandas as pd
import re
from dateutil.relativedelta import relativedelta

from beancount.core.number import Decimal
from beancount.core import data
from beancount.core import prices
from beancount.core import convert
from beancount.core import inventory
from beancount.core import account_types
from beancount.query import query
from beancount.core.data import Custom
from beancount.parser import options

BudgetError = collections.namedtuple('BudgetError', 'source message entry')

class BeancountEnvelope:

    def __init__(self, entries, errors, options_map, start_date=None, future_months=0, future_rollover=False, show_real_accounts=True):

        self.entries = entries
        self.errors = errors
        self.options_map = options_map
        self.currency = self._find_currency(options_map)
        self.budget_accounts, self.mappings = self._find_envelop_settings()
        self.show_real_accounts = show_real_accounts

        decimal_precison = '0.00'
        self.Q = Decimal(decimal_precison)

        # Compute start of period
        # TODO get start date from journal
        today = datetime.date.today()
        self.today = today

        self.date_start = datetime.date(today.year, 1, 1) if start_date is None else start_date

        # Compute end of period
        self.date_end = today + relativedelta(months=future_months)
        self.future_rollover = future_rollover

        self.price_map = prices.build_price_map(entries)
        self.acctypes = options.get_account_types(options_map)


    def _find_currency(self, options_map):
        default_currency = 'USD'
        opt_currency = options_map.get("operating_currency")
        currency = opt_currency[0] if opt_currency else default_currency
        if len(currency) == 3:
            return currency

        logging.warning(f"invalid operating currency: {currency}, defaulting to {default_currency}")
        return default_currency


    def _find_envelop_settings(self):
        budget_accounts= []
        mappings = []

        for e in self.entries:
            if isinstance(e, Custom) and e.type == "envelope":
                if e.values[0].value == "budget account":
                    budget_accounts.append(re.compile(e.values[1].value))
                if e.values[0].value == "mapping":
                    map_set = (
                        re.compile(e.values[1].value),
                        e.values[2].value
                    )
                    mappings.append(map_set)

        if len(budget_accounts) == 0:
            self.errors.append(BudgetError(data.new_metadata("<fava-envelope>", 0), 'no budget accounts setup', None))

        return budget_accounts, mappings

    def envelope_tables(self, entry_parser):

        months = []
        date_current = self.date_start
        self.current_month = None

        while date_current <= self.date_end:
            months.append(f"{date_current.year}-{str(date_current.month).zfill(2)}")
            if date_current.year == self.today.year and date_current.month == self.today.month:
                self.current_month = months[-1]
            month = date_current.month - 1 + 1
            year = date_current.year + month // 12
            month = month % 12 + 1
            date_current = datetime.date(year, month,1)

        if self.current_month is None:
            self.current_month = months[-1]

        # Create Income DataFrame
        column_index = pd.MultiIndex.from_product([months], names=['Month'])
        self.income_df = pd.DataFrame(columns=months)

        # Create Envelopes DataFrame
        column_index = pd.MultiIndex.from_product([months, ['activity', 'budgeted', 'available']], names=['Month','col'])
        self.envelope_df = pd.DataFrame(columns=column_index)
        self.envelope_df.index.name = "Envelopes"

        self._calculate_budget_activity(entry_parser)
        self._calc_budget_budgeted()

        # Calculate Starting Balance Income
        starting_balance = Decimal(0.0)
        query_str = f"select account, convert(sum(position),'{self.currency}') from close on {months[0]}-01 group by 1 order by 1;"
        rows = query.run_query(self.entries, self.options_map, query_str, numberify=True)
        for row in rows[1]:
            if any(regexp.match(row[0]) for regexp in self.budget_accounts):
                if row[1] is not None:
                    starting_balance += row[1]
        self.income_df[months[0]]["Avail Income"] += starting_balance

        self.envelope_df.fillna(Decimal(0.00), inplace=True)

        max_index = len(months) if self.future_rollover else months.index(self.current_month)

        # Set available
        for index, row in self.envelope_df.iterrows():
            for index2, month in enumerate(months):
                if index2 == 0:
                    row[month, 'available'] = row[month, 'budgeted'] + row[month, 'activity']
                else:
                    prev_available = row[months[index2-1],'available']
                    rollover = index2 <= max_index
                    if rollover and prev_available > 0:
                        row[month, 'available'] = prev_available + row[month, 'budgeted'] + row[month, 'activity']
                    else:
                        row[month, 'available'] = row[month, 'budgeted'] + row[month, 'activity']

        # Set overspent
        for index, month in enumerate(months):
            if index == 0:
                self.income_df.loc["Overspent", month] = Decimal(0.00)
            else:
                overspent = Decimal(0.00)
                for index2, row in self.envelope_df.iterrows():
                    if row[months[index-1],'available'] < Decimal(0.00):
                        overspent += Decimal(row[months[index-1], 'available'])
                self.income_df.loc["Overspent", month] = overspent

        # Set Budgeted for month
        for month in months:
            self.income_df.loc["Budgeted",month] = Decimal(-1 * self.envelope_df[month,'budgeted'].sum())

        # Adjust Avail Income
        for index, month in enumerate(months):
            if index == 0:
                continue
            else:
                prev_month = months[index-1]
                self.income_df.loc["Avail Income", month] = \
                    self.income_df.loc["Avail Income",month] + \
                    self.income_df.loc["Avail Income", prev_month] + \
                    self.income_df.loc["Overspent", prev_month] + \
                    self.income_df.loc["Budgeted", prev_month]

        # Set Budgeted in the future
        for index, month in enumerate(months):
            sum_total = self.income_df[month].sum()
            if (index == len(months)-1) or sum_total < 0 :
                self.income_df.loc["Budgeted Future", month] = Decimal(0.00)
            else:
                next_month = months[index+1]
                opp_budgeted_next_month = self.income_df.loc["Budgeted",next_month] * -1
                if opp_budgeted_next_month < sum_total:
                    self.income_df.loc["Budgeted Future", month] = Decimal(-1*opp_budgeted_next_month)
                else:
                    self.income_df.loc["Budgeted Future", month] = Decimal(-1*sum_total)

        # Set to be budgeted
        for index, month in enumerate(months):
            self.income_df.loc["To Be Budgeted", month] = Decimal(self.income_df[month].sum())

        return self.income_df, self.envelope_df, self.current_month

    def is_income(self, account):
        account_type = account_types.get_account_type(account)
        return account_type == self.acctypes.income

    def is_budget_account(self, account):
        if any(regexp.match(account) for regexp in self.budget_accounts):
            return True
        return False

    def _get_bucket(self, account):
        for regexp, target_account in self.mappings:
            if regexp.match(account):
                return target_account

        return account

    def _calculate_budget_activity(self, entry_parser: BeancountEntries):
        actual_expenses = entry_parser.parse_transactions(start=self.date_start, end=self.date_end)
        only_buckets = actual_expenses.sum(level=0, axis=0)

        income_columns = ['Income', 'Income:Deduction']
        self.income_df.loc["Avail Income", :] = Decimal(0.00)

        for month in only_buckets.columns:
            for index, row in only_buckets.iterrows():
                if index in income_columns:
                    self.income_df.loc["Avail Income", month] += row[month]
                else:
                    self.envelope_df.loc[index, (month, 'activity')] = row[month]


    def _calc_budget_budgeted(self):
        rows = {}
        for e in self.entries:
            if isinstance(e, Custom) and e.type == "envelope":
                if e.values[0].value == "allocate":
                    month = f"{e.date.year}-{e.date.month:02}"
                    self.envelope_df.loc[e.values[1].value,(month,'budgeted')] = Decimal(e.values[2].value)
