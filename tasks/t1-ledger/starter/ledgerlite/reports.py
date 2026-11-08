"""Balance and register reports (SPEC.md section 4)."""


def balance_report(
    ledger,
    patterns=(),
    begin=None,
    end=None,
    depth=None,
    empty=False,
    total=True,
    exchange=None,
    cleared=False,
):
    """Return the balance report text (SPEC 4.3)."""
    raise NotImplementedError


def register_report(
    ledger, patterns=(), begin=None, end=None, exchange=None, cleared=False
):
    """Return the register report text (SPEC 4.4)."""
    raise NotImplementedError
