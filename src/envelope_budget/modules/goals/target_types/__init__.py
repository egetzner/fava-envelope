from abc import ABC

from beancount.core.data import Entries


class TargetParser(ABC):

    def parse_entries(self, entries: Entries):
        pass