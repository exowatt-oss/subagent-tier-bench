# ledgerlite

A small plain-text double-entry accounting library and command-line tool, to be
implemented from `SPEC.md`.

- `SPEC.md`: the complete specification (journal syntax, parse errors, balancing and
  amount inference, display precision, balance assertions, prices and conversion, the
  balance and register reports, and the command line). It is the single source of truth;
  exact strings such as error messages and report layouts matter.
- `ledgerlite/`: the package. `model.py` (data classes, exceptions) is already written;
  the other modules are stubs that raise `NotImplementedError`.
- `examples/`: sample journals, including the one used by the worked example in SPEC.md
  section 6.
- `tests/`: visible tests. Do not edit them.

Run the visible tests from this directory:

    python3 -m unittest discover -s tests -t . -q

Try the CLI:

    python3 -m ledgerlite -f examples/basic.journal balance

Python 3.9 or newer, standard library only.
