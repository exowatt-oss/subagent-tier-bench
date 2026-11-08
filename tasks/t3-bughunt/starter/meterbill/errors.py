"""Error types shared by every meterbill module."""


class InputError(Exception):
    """Invalid input: a malformed file, an unknown reference or a bad CLI value.

    The CLI turns it into ``error: <message>`` on stderr and exit status 2.
    """
