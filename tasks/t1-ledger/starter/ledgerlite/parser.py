"""Journal parser (SPEC.md section 2)."""


def parse_amount(text):
    """Parse an amount such as "$1,234.50" or "-3 AAPL" into an Amount (SPEC 2.4).

    Raises ValueError if the text is not a valid amount.
    """
    raise NotImplementedError


def parse_date(text):
    """Parse a journal date, YYYY-MM-DD or YYYY/MM/DD (SPEC 2.2); ValueError if invalid."""
    raise NotImplementedError


def parse_string(text, filename="<string>"):
    """Parse journal text into a Journal (SPEC 2).

    filename is the display name used in errors and for resolving includes.
    """
    raise NotImplementedError


def parse_file(path):
    """Read a UTF-8 journal file and parse it with display name `path` (SPEC 1, 2)."""
    raise NotImplementedError
