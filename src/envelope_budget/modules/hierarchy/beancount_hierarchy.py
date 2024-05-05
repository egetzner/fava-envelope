
import logging
import pandas as pd

from beancount.core import inventory, account
from beancount.core.number import Decimal


class Bucket(dict):

    __slots__ = ('account', 'is_real', 'balance')

    def __init__(self, account_name, is_real=False, *args, **kwargs):
        """Create a RealAccount instance.

        Args:
          account_name: a string, the name of the account. Maybe not be None.
        """
        super().__init__(*args, **kwargs)
        assert isinstance(account_name, str)
        self.account = account_name
        self.is_real = is_real
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
            real_child = Bucket(account.join(*path), is_real=False)
            real_account[component] = real_child
        real_account = real_child
    return real_account


def get_or_create(bucket, real_account_name):
    if not isinstance(real_account_name, str):
        raise ValueError
    real_child = bucket.get(real_account_name, None)
    if real_child is None:
        real_child = Bucket(real_account_name, is_real=True)
        bucket[real_account_name] = real_child
    return real_child


def map_to_bucket(mappings, name: str):
    for regexp, target_bucket in mappings:
        if regexp.match(name):
            return target_bucket

    return name


def map_accounts_to_bucket(mappings, accounts):
    accounts_to_match = list(accounts)
    buckets = dict()
    for regex, bucket in mappings:
        accounts = [a for a in accounts_to_match if regex.match(a)]
        for a in accounts:
            accounts_to_match.remove(a)

        existing_accounts = buckets.get(bucket)
        existing_accounts = list() if existing_accounts is None else existing_accounts
        existing_accounts.extend(accounts)
        buckets[bucket] = existing_accounts

    # TODO: handle income acounts better
    income = [a for a in accounts_to_match if a.startswith('Income:') or a == 'Income']
    for ia in income:
        accounts_to_match.remove(ia)

    if len(accounts_to_match) > 0:
        logging.warning(f'unmatched accounts: {accounts_to_match}')
        buckets['Unmapped'] = list(accounts_to_match)

    return buckets


def get_hierarchy(buckets_with_accounts, include_children):
    roots = {}
    for name in sorted(buckets_with_accounts.keys()):
        root_name = name.split(':')[0]
        root = roots.get(root_name, Bucket(root_name, False))
        bucket = get_or_create_with_hierarchy(root, name)
        if include_children:
            contained_accounts = buckets_with_accounts.get(name)
            if contained_accounts is not None:
                for acc in contained_accounts:
                    get_or_create(bucket, acc)
        roots[root_name] = root

    # root = [
    #    self.ledger.all_root_account.get('Income'),
    #    self.ledger.all_root_account.get('Expenses'),
    # ]
    return [list(acc.values())[0] for acc in roots.values()]


def get_level_as_dict(multi_level_df, single_level_df: list):
    with_real_accounts = multi_level_df.groupby(level=0).apply(lambda df: list(df.index.get_level_values(level=1).values)).to_dict()

    for df in single_level_df:
        for b in df.index:
            if b not in with_real_accounts:
                with_real_accounts[b] = []

    return with_real_accounts


def add_bucket_levels(single_level_df, hierarchy_index, mappings, lvl_name='account'):
    df = pd.DataFrame(index=hierarchy_index)
    single_level_df.index.name = lvl_name

    # 1. check which accounts are already mapped:
    known_accounts = set(hierarchy_index.get_level_values(level=lvl_name))
    accounts_to_match = set(single_level_df.index.values)

    df = df.join(single_level_df)
    unmatched_accounts = accounts_to_match.difference(known_accounts)

    for name in unmatched_accounts:
        bucket = map_to_bucket(mappings, name)
        row = single_level_df.loc[name]
        df.loc[(bucket, name), :] = row

    return df.fillna(Decimal(0.00))
