"""Exception hierarchy for wotrack.

Every expected, user-facing failure is raised as a :class:`WotrackError`
subclass.  The command line catches these, prints ``error: <message>`` to
stderr and exits with the class's ``exit_code``.
"""


class WotrackError(Exception):
    """Base class for all expected, user-facing errors."""

    exit_code = 1


class NotFoundError(WotrackError):
    """A referenced work order does not exist."""


class ValidationError(WotrackError):
    """A field value or a requested change is not allowed."""


class TransitionError(ValidationError):
    """A status change is not permitted by the workflow."""


class StorageError(WotrackError):
    """The data file cannot be read, parsed or written."""
