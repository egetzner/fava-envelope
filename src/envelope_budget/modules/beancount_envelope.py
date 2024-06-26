# Debug
try:
    import ipdb
except ImportError:
    pass

import datetime
import collections
import logging
import pandas as pd
import re
from dateutil.relativedelta import relativedelta

from beancount.core.number import Decimal
from beancount.core import data
from beancount.core import prices, inventory, convert
from beancount.core import account_types
from beancount.core import amount
from beancount.query import query
from beancount.core.data import Custom
from beancount.parser import options

BudgetError = collections.namedtuple('BudgetError', 'source message entry')


class BeancountEnvelope:

    def __init__(self, entries, errors, options_map, budget_postfix,
                 start_date=None, future_months=1, future_rollover=True,
                 show_real_accounts=True, today=None):

        self.entries = entries
        self.errors = errors
        self.options_map = options_map
        self.currency = self._find_currency(options_map)
        self.customentry = "envelope" + budget_postfix if budget_postfix else "envelope"
        (self.budget_accounts, self.mappings, max_date, self.income_accounts, self.allocation_entries,
         self.target_entries) = self._find_envelop_settings()
        self.show_real_accounts = show_real_accounts

        decimal_precison = '0.00'
        self.Q = Decimal(decimal_precison)

        # Compute start of period
        # TODO get start date from journal
        self.today = today if today is not None else datetime.date.today()

        self.date_start = datetime.date(self.today.year, 1, 1) if start_date is None else start_date

        # Compute end of period
        max_date = self.today if max_date is None else max_date
        self.date_end = max_date + relativedelta(months=future_months)
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
        income_accounts = []
        target_entries = []
        allocation_entries = []

        allocation_dates = set()

        for e in self.entries:
            if isinstance(e, Custom) and e.type == self.customentry:
                type = e.values[0].value
                if type == "budget account":
                    budget_accounts.append(re.compile(e.values[1].value))
                elif type == "mapping":
                    map_set = (
                        re.compile(e.values[1].value),
                        e.values[2].value
                    )
                    mappings.append(map_set)
                elif type == "allocate":
                    allocation_dates.add(e.date)
                    allocation_entries.append(e)
                elif type == "currency":
                    self.currency = e.values[1].value
                elif type == "income account":
                    income_accounts.append(re.compile(e.values[1].value))
                elif type == "target" or type == "spending":
                    target_entries.append(e)

        if len(allocation_dates) == 0:
            logging.warning("No envelope entries found")
            max_date = None
        else:
            max_date = max(allocation_dates)

        if len(budget_accounts) == 0:
            logging.warning('no budget accounts setup within given time range.')
            #self.errors.append(BudgetError(data.new_metadata("<fava-envelope>", 0), 'no budget accounts setup', None))

        return budget_accounts, mappings, max_date, income_accounts, allocation_entries, target_entries

    def envelope_tables(self, entry_parser=None):

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
        #row_index = pd.MultiIndex(levels=[[], []], codes=[[], []], names=['bucket', 'account'])
        self.envelope_df = pd.DataFrame(columns=column_index)
        self.envelope_df.index.name = "Envelopes"

        if entry_parser is not None:
            self.actual_expenses = entry_parser.parse_transactions(start=self.date_start, end=self.date_end,
                                                                   income_accounts=self.income_accounts)
            self._calculate_budget_activity_from_actual(self.actual_expenses)
        else:
            self._calculate_budget_activity()
            self.actual_expenses = pd.DataFrame()

        self._calc_budget_budgeted()

        income_df_detail = pd.DataFrame(data=self.income_df)
        income_df_detail = income_df_detail.rename(index={'Avail Income': "Income"})

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

        curr_month_index = months.index(self.current_month)
        max_index = len(months) if self.future_rollover else curr_month_index

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

        remaining = self.income_df.sum(axis=0, numeric_only=False)
        shifted = remaining.shift(+1)
        shifted.iloc[0] = starting_balance
        income_df_detail.loc['Rollover Funds'] = shifted

        spent = self.income_df.filter(items=['Overspent', 'Budgeted'], axis=0).sum(axis=0, numeric_only=False)
        spent_next_month = spent.shift(-1).fillna(0)
        all_future_spending = spent_next_month.loc[::-1].cumsum().loc[::-1]
        future_delta = all_future_spending.add(remaining[all_future_spending < 0], fill_value=Decimal(0))
        max_future_spending = all_future_spending - future_delta

        future_budget = max_future_spending[future_delta < 0].add(all_future_spending[future_delta >= 0], fill_value=Decimal(0))
        future_budget = future_budget[remaining > 0]
        tbb = remaining.add(future_budget, fill_value=Decimal(0))

        cover_next_month = remaining[remaining >= 0] + spent_next_month
        stealing = cover_next_month[cover_next_month < 0]

        self.income_df.loc['To Be Budgeted'] = tbb
        self.income_df.loc['Budgeted Future'] = future_budget
        income_df_detail.loc['Stealing from Future'] = stealing

        summary_info = pd.concat([self.income_df, income_df_detail], axis=0).fillna(Decimal(0))
        return summary_info, self.envelope_df, self.actual_expenses, self.current_month

    #def is_income(self, account):
    #    account_type = account_types.get_account_type(account)
    #    return account_type == self.acctypes.income

    def _get_bucket(self, account):
        for regexp, target_account in self.mappings:
            if regexp.match(account):
                return target_account

        return account

    def _calculate_budget_activity_from_actual(self, actual_expenses: pd.DataFrame):
        buckets_only = actual_expenses.groupby(level=0, axis=0).sum(numeric_only=False)

        income_columns = ['Income', 'Income:Deduction']
        self.income_df.loc["Avail Income", :] = Decimal(0.00)

        for month in buckets_only.columns:
            for index, row in buckets_only.iterrows():
                if index in income_columns:
                    self.income_df.loc["Avail Income", month] += row[month]
                else:
                    self.envelope_df.loc[index, (month, 'activity')] = row[month]

    def _calculate_budget_activity(self):

        # Accumulate expenses for the period
        balances = collections.defaultdict(
            lambda: collections.defaultdict(inventory.Inventory))
        all_months = set()

        for entry in data.filter_txns(self.entries):

            # Check entry in date range
            if entry.date < self.date_start or entry.date > self.date_end:
                continue

            month = (entry.date.year, entry.date.month)
            # TODO domwe handle no transaction in a month?
            all_months.add(month)

            # TODO
            contains_budget_accounts = False
            for posting in entry.postings:
                if any(regexp.match(posting.account) for regexp in self.budget_accounts):
                    contains_budget_accounts = True
                    break

            if not contains_budget_accounts:
                continue

            for posting in entry.postings:

                account = posting.account
                for regexp, target_account in self.mappings:
                    if regexp.match(account):
                        account = target_account
                        break

                account_type = account_types.get_account_type(account)
                if posting.units.currency != self.currency:
                    orig=posting.units.number
                    if posting.price is not None:
                        converted=posting.price.number*orig
                        posting=data.Posting(posting.account,amount.Amount(converted,self.currency), posting.cost, None, posting.flag,posting.meta)
                    else:
                        continue

                if (account_type == self.acctypes.income
                    or (any(regexp.match(account) for regexp in self.income_accounts))):
                    account = "Income"
                elif any(regexp.match(posting.account) for regexp in self.budget_accounts):
                    continue
                # TODO WARn of any assets / liabilities left

                # TODO
                balances[account][month].add_position(posting)

        # Reduce the final balances to numbers
        sbalances = collections.defaultdict(dict)
        for account, months in sorted(balances.items()):
            for month, balance in sorted(months.items()):
                year, mth = month
                date = datetime.date(year, mth, 1)
                balance = balance.reduce(convert.get_value, self.price_map, date)
                balance = balance.reduce(
                    convert.convert_position, self.currency, self.price_map, date)
                try:
                    pos = balance.get_only_position()
                except AssertionError:
                    print(balance)
                    raise
                total = pos.units.number if pos and pos.units else None
                sbalances[account][month] = total

        # Pivot the table
        header_months = sorted(all_months)
        header = ['account'] + ['{}-{:02d}'.format(*m) for m in header_months]
        self.income_df.loc["Avail Income", :] = Decimal(0.00)

        for account in sorted(sbalances.keys()):
            for month in header_months:
                total = sbalances[account].get(month, None)
                temp = total.quantize(self.Q) if total else 0.00
                # swap sign to be more human readable
                temp *= -1

                month_str = f"{str(month[0])}-{str(month[1]).zfill(2)}"
                if account == "Income":
                    self.income_df.loc["Avail Income",month_str] = Decimal(temp)
                else:
                    self.envelope_df.loc[account,(month_str,'budgeted')] = Decimal(0.00)
                    self.envelope_df.loc[account,(month_str,'activity')] = Decimal(temp)
                    self.envelope_df.loc[account,(month_str,'available')] = Decimal(0.00)

    def get_bucket_or_none(self, account):
        for regexp, target_account in self.mappings:
            if regexp.match(account):
                return target_account

        return None

    def _calc_budget_budgeted(self):
        for e in self.allocation_entries:
            if self.date_start <= e.date <= self.date_end:
                month = f"{e.date.year}-{e.date.month:02}"
                bucket = e.values[1].value
                self.envelope_df.loc[bucket, (month, 'budgeted')] = Decimal(e.values[2].value)
