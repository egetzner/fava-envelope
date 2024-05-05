import re
from typing import List

from beancount.core.data import Custom, Entries


def map_accounts_to_buckets(accounts: List[str], mappings: List,
                            fallback_mapping: str = None) -> List[str]:

    def get_bucket(mappings, account, fallback_value: str = None) -> str:
        for regexp, target_account in mappings:
            if regexp.match(account):
                return target_account

        return fallback_value if not None else account

    return [get_bucket(mappings, a, fallback_mapping) for a in accounts]



def retrieve_mappings_from_entries(entries: Entries, entrytype: str):
    mappings = []

    for e in entries:
        if isinstance(e, Custom) and e.type == entrytype:
            type = e.values[0].value
            if type == "mapping":
                map_set = (
                    re.compile(e.values[1].value),
                    e.values[2].value
                )
                mappings.append(map_set)

    return mappings
