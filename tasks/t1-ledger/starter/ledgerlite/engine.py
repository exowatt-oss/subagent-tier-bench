"""Balancing, amount inference, assertions and prices (SPEC.md section 3)."""


def commodity_precisions(journal):
    """Return {commodity: display precision} for the journal (SPEC 3.1)."""
    raise NotImplementedError


def posting_weight(posting):
    """Return the Amount a posting contributes to balancing (SPEC 3.2)."""
    raise NotImplementedError


class Ledger:
    """A validated journal, as returned by build_ledger (SPEC 3.7).

    Attributes: transactions, prices, precisions.
    """

    def __init__(self, *args, **kwargs):
        raise NotImplementedError

    def precision(self, commodity):
        raise NotImplementedError

    def format(self, amount):
        raise NotImplementedError

    def price(self, commodity, target, on_date):
        raise NotImplementedError

    def convert(self, amount, target, on_date):
        raise NotImplementedError

    def accounts(self):
        raise NotImplementedError

    def assertion_failures(self):
        raise NotImplementedError


def build_ledger(journal):
    """Balance every transaction and infer omitted amounts (SPEC 3.3-3.4)."""
    raise NotImplementedError


def load(path):
    """parse_file, build_ledger, then raise the first assertion failure (SPEC 3.5)."""
    raise NotImplementedError
