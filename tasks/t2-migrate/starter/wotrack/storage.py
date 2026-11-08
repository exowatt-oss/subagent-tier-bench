"""JSON file storage.

The whole data set lives in one JSON document (see README.md, "Data format
1").  It is loaded completely, changed in memory and written back atomically.
"""

import json
import os
import tempfile

from .errors import NotFoundError, StorageError
from .models import WorkOrder

#: The data format this version reads and writes.
FORMAT_VERSION = 1

#: Data file used when neither ``--file`` nor ``WOTRACK_FILE`` is given.
DEFAULT_FILE = "workorders.json"
FILE_ENV = "WOTRACK_FILE"


def resolve_path(option_value=None):
    """Pick the data file: ``--file`` beats ``WOTRACK_FILE`` beats the default."""
    if option_value:
        return option_value
    from_env = os.environ.get(FILE_ENV, "").strip()
    if from_env:
        return from_env
    return DEFAULT_FILE


class Database:
    """All work orders of one data file, keyed by id."""

    def __init__(self, orders=(), next_id=None):
        self._orders = {}
        for order in orders:
            if order.id in self._orders:
                raise StorageError("duplicate work order id: %d" % order.id)
            self._orders[order.id] = order
        highest = max(self._orders, default=0)
        self.next_id = max(next_id or 1, highest + 1)

    def __len__(self):
        return len(self._orders)

    def __contains__(self, order_id):
        return order_id in self._orders

    def get(self, order_id):
        try:
            return self._orders[order_id]
        except KeyError:
            raise NotFoundError("no such work order: %d" % order_id) from None

    def all(self):
        """Every work order, ordered by id."""
        return [self._orders[key] for key in sorted(self._orders)]

    def allocate_id(self):
        """Reserve and return the next id.  Ids are never reused."""
        order_id = self.next_id
        self.next_id += 1
        return order_id

    def add(self, order):
        if order.id in self._orders:
            raise StorageError("duplicate work order id: %d" % order.id)
        self._orders[order.id] = order
        self.next_id = max(self.next_id, order.id + 1)

    def remove(self, order_id):
        order = self.get(order_id)
        del self._orders[order_id]
        return order


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------


def decode(document):
    """Turn a parsed JSON document into a :class:`Database`."""
    if not isinstance(document, dict):
        raise StorageError("data file must contain a JSON object")
    version = document.get("format", 1)
    if version != FORMAT_VERSION:
        raise StorageError("unsupported data format: %s" % (version,))
    records = document.get("orders", [])
    if not isinstance(records, list):
        raise StorageError("'orders' must be a list")
    try:
        orders = [WorkOrder.from_dict(record) for record in records]
    except (KeyError, TypeError, ValueError) as exc:
        raise StorageError("malformed work order record: %s" % exc) from None
    return Database(orders, next_id=document.get("next_id"))


def encode(database):
    """Turn a :class:`Database` into a JSON-ready document."""
    return {
        "format": FORMAT_VERSION,
        "next_id": database.next_id,
        "orders": [order.to_dict() for order in database.all()],
    }


def dumps(document):
    """Serialise a document exactly as it is written to disk."""
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# File access
# ---------------------------------------------------------------------------


def read_document(path):
    """Read and parse the JSON document at ``path``."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError:
        raise StorageError("cannot read %s: invalid JSON" % path) from None
    except OSError as exc:
        raise StorageError("cannot read %s: %s" % (path, exc.strerror)) from None


def load(path):
    """Load the database at ``path``; a missing file is an empty database."""
    if not os.path.exists(path):
        return Database()
    return decode(read_document(path))


def write_atomic(path, text):
    """Write ``text`` to ``path`` via a temporary file and an atomic rename."""
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(prefix=".wotrack-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_path, path)
    except OSError as exc:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise StorageError("cannot write %s: %s" % (path, exc.strerror)) from None


def save(database, path):
    """Write the database to ``path`` in data format 1."""
    write_atomic(path, dumps(encode(database)))
