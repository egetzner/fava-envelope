# Debug
try:
    import ipdb
except ImportError:
    pass

import datetime
import traceback
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
from beancount.core import account_types, account
from beancount.query import query
from beancount.core.data import Custom
from beancount.parser import options

BudgetError = collections.namedtuple('BudgetError', 'source message entry')

class Bucket(dict):

    __slots__ = ('account', 'balance')

    def __init__(self, account_name, *args, **kwargs):
        """Create a RealAccount instance.

        Args:
          account_name: a string, the name of the account. Maybe not be None.
        """
        super().__init__(*args, **kwargs)
        assert isinstance(account_name, str)
        self.account = account_name
        self.balance = inventory.Inventory()

    def __eq__(self, other):
        """Equality predicate. All attributes are compared.

        Args:
          other: Another instance of RealAccount.
        Returns:
          A boolean, True if the two real accounts are equal.
        """
        return (dict.__eq__(self, other) and
                self.account == other.account)

    def __ne__(self, other):
        """Not-equality predicate. See __eq__.

        Args:
          other: Another instance of RealAccount.
        Returns:
          A boolean, True if the two real accounts are not equal.
        """
        return not self.__eq__(other)


    def __setitem__(self, key, value):
        """Prevent the setting of non-string or non-empty keys on this dict.

        Args:
          key: The dictionary key. Must be a string.
          value: The value, must be a RealAccount instance.
        Raises:
          KeyError: If the key is not a string, or is invalid.
          ValueError: If the value is not a RealAccount instance.
        """
        if not isinstance(key, str) or not key:
            raise KeyError("Invalid Bucket key: '{}'".format(key))
        if not isinstance(value, Bucket):
            raise ValueError("Invalid Bucket value: '{}'".format(value))
        if not value.account.endswith(key):
            raise ValueError("Bucket name '{}' inconsistent with key: '{}'".format(
                value.account, key))
        return super().__setitem__(key, value)


def get(real_account, account_name, default=None):
    """Fetch the subaccount name from the real_account node.

    Args:
      real_account: An instance of RealAccount, the parent node to look for
        children of.
      account_name: A string, the name of a possibly indirect child leaf
        found down the tree of 'real_account' nodes.
      default: The default value that should be returned if the child
        subaccount is not found.
    Returns:
      A RealAccount instance for the child, or the default value, if the child
      is not found.
    """
    if not isinstance(account_name, str):
        raise ValueError
    components = account.split(account_name)
    for component in components:
        real_child = real_account.get(component, default)
        if real_child is default:
            return default
        real_account = real_child
    return real_account


def get_or_create_with_hierarchy(real_account, account_name):
    """Fetch the subaccount name from the real_account node.

    Args:
      real_account: An instance of RealAccount, the parent node to look for
        children of, or create under.
      account_name: A string, the name of the direct or indirect child leaf
        to get or create.
    Returns:
      A RealAccount instance for the child, or the default value, if the child
      is not found.
    """
    if not isinstance(account_name, str):
        raise ValueError
    components = account.split(account_name)
    path = []
    for component in components:
        path.append(component)
        real_child = real_account.get(component, None)
        if real_child is None:
            real_child = Bucket(account.join(*path))
            real_account[component] = real_child
        real_account = real_child
    return real_account


def get_or_create(bucket, real_account_name):
    if not isinstance(real_account_name, str):
        raise ValueError
    real_child = bucket.get(real_account_name, None)
    if real_child is None:
        real_child = Bucket(real_account_name)
        bucket[real_account_name] = real_child
    return real_child


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

        #if len(budget_accounts) == 0:
        #    self.errors.append(BudgetError(data.new_metadata("<fava-envelope>", 0), 'no budget accounts setup', None))

        return budget_accounts, mappings


    def envelope_tables(self):

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
        column_index = pd.MultiIndex.from_product([months, ['budgeted', 'activity', 'available']], names=['Month','col'])
        self.envelope_df = pd.DataFrame(columns=column_index)
        self.envelope_df.index.name = "Envelopes"

        self.actual_spent, buckets = self._calculate_budget_activity()
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

        self.accounts = self._get_accounts(self.envelope_df.index, buckets)
        self.actual_spent.columns = months
        return self.income_df, self.envelope_df, self.current_month, self.accounts, self.actual_spent


    def _get_accounts(self, names, buckets):

        try:
            roots = {}
            for name in names:
                root_name = name.split(':')[0]
                root = roots.get(root_name) if root_name in roots else Bucket(root_name)
                bucket = get_or_create_with_hierarchy(root, name)
                contained_accounts = buckets.get(name)
                if self.show_real_accounts and contained_accounts is not None:
                    for account in contained_accounts:
                        get_or_create(bucket, account)
                roots[root_name] = root
            return list(roots.values())
        except:
            logging.error(traceback.formatexc())


    def _get_balances(self):

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
                #for regexp, target_account in self.mappings:
                #    if regexp.match(account):
                #        account = target_account
                #        break

                account_type = account_types.get_account_type(account)
                if posting.units.currency != self.currency:
                    continue

                if account_type == self.acctypes.income:
                    account = "Income"
                elif any(regexp.match(posting.account) for regexp in self.budget_accounts):
                    continue
                # TODO WARn of any assets / liabilities left

                # TODO
                balances[account][month].add_position(posting)

        return balances, all_months

    def _sort_and_reduce(self, balances):

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
        return sbalances

    def _calculate_budget_activity(self):

        # Reduce the final balances to numbers
        balances, all_months = self._get_balances()
        sbalances = self._sort_and_reduce(balances)

        # Pivot the table
        header_months = sorted(all_months)
        self.income_df.loc["Avail Income", :] = Decimal(0.00)

        actual_expenses = pd.DataFrame(columns=header_months)
        for account in sorted(sbalances.keys()):
            for month in header_months:
                total = sbalances[account].get(month, None)
                temp = total.quantize(self.Q) if total else 0.00
                # swap sign to be more human readable
                temp *= -1
                actual_expenses.loc[account, month] = Decimal(temp)

        accounts_to_match = list(actual_expenses.index.values)
        buckets = dict()
        for regex, bucket in self.mappings:
            accounts = [a for a in accounts_to_match if regex.match(a)]
            for a in accounts:
                accounts_to_match.remove(a)

            existing_accounts = buckets.get(bucket)
            existing_accounts = list() if existing_accounts is None else existing_accounts
            existing_accounts.extend(accounts)
            buckets[bucket] = existing_accounts

        for account in accounts_to_match:
            buckets[account] = [account]

        for account in sorted(buckets.keys()):
            for month in header_months:
                all = actual_expenses[month].filter(items=buckets[account], axis=0)
                temp = all.sum(axis=0)

                month_str = f"{str(month[0])}-{str(month[1]).zfill(2)}"
                if account == "Income":
                    self.income_df.loc["Avail Income",month_str] = Decimal(temp)
                else:
                    self.envelope_df.loc[account,(month_str,'budgeted')] = Decimal(0.00)
                    self.envelope_df.loc[account,(month_str,'activity')] = Decimal(temp)
                    self.envelope_df.loc[account,(month_str,'available')] = Decimal(0.00)

        return actual_expenses, buckets

    def _calc_budget_budgeted(self):
        rows = {}
        for e in self.entries:
            if isinstance(e, Custom) and e.type == "envelope":
                if e.values[0].value == "allocate":
                    month = f"{e.date.year}-{e.date.month:02}"
                    self.envelope_df.loc[e.values[1].value,(month,'budgeted')] = Decimal(e.values[2].value)
