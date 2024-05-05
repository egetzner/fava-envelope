def should_show(self, account: TreeNode) -> bool:
    """Determine whether the account should be shown."""
    from fava.context import g
    if not account.balance_children.is_empty() or any(
            self.should_show(a) for a in account.children
    ):
        return True
    ledger = g.ledger
    filtered = g.filtered
    if account.name not in ledger.accounts:
        return False
    fava_options = ledger.fava_options
    if not fava_options.show_closed_accounts and filtered.account_is_closed(
            account.name,
    ):
        return False
    if (
            not fava_options.show_accounts_with_zero_balance
            and account.balance.is_empty()
    ):
        return False
    if (
            not fava_options.show_accounts_with_zero_transactions
            and not account.has_txns
    ):
        return False
    return True


def collapse_account(self, account_name: str) -> bool:
    """Return true if account should be collapsed."""
    from fava.context import g
    collapse_patterns = g.ledger.fava_options.collapse_pattern
    return any(pattern.match(account_name) for pattern in collapse_patterns)


def cost(self, inventory: CounterInventory) -> SimpleCounterInventory:
    """Get the cost of an inventory."""
    return inventory.reduce(get_cost)


def cost_or_value(
        self,
        inventory: CounterInventory,
        date: date | None = None,
) -> SimpleCounterInventory:
    """Get the cost or value of an inventory."""
    from fava.context import g
    return cost_or_value(inventory, g.conversion, g.ledger.prices, date)