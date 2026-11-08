# ledgerlite specification

`ledgerlite` is a small plain-text double-entry accounting library with a command-line
tool. It reads a *journal* file, validates it, and prints reports. Implement it in the
`ledgerlite` package with the Python standard library only (Python 3.9 or newer).

Conventions used below: text in `code` is exact, character for character. "Error `X`"
means the exception's `message` is exactly `X`; `NAME` placeholders are filled in as
described. All quantities are `decimal.Decimal`; never use `float` anywhere. "Sorted by
commodity" means plain Python string ordering of the commodity strings (so `$` sorts
before `AAPL`, which sorts before `EUR`).

## 1. Public Python API

The package `ledgerlite/__init__.py` re-exports every name below.

**`ledgerlite.model`** (already written in the starter; keep these names, fields and
defaults exactly as they are):

- `Amount(quantity, commodity)`: frozen dataclass. `commodity` is the symbol or code string
  (`"$"`, `"USD"`).
- `Posting(account, amount=None, cost=None, cost_type=None, assertion=None, comment="", filename="", lineno=0, inferred=False)`.
  `cost_type` is `None`, `"@"` or `"@@"`; `cost` is the `Amount` written after it.
- `Transaction(date, description="", status="", code="", comment="", postings=[], filename="", lineno=0)`.
  `date` is a `datetime.date`; `status` is `""`, `"*"` or `"!"`.
- `Price(date, commodity, price, filename="", lineno=0)`: one `P` directive; `price` is an `Amount`.
- `Journal(transactions=[], prices=[])`: both lists in *journal order* (section 2.6).
- `LedgerError(filename, lineno, message)` with subclasses `ParseError`, `BalanceError`,
  `AssertionFailure`. Each has the attributes `filename`, `lineno`, `message`, and
  `str(error) == f"{filename}:{lineno}: {message}"`.
- `SYMBOLS = ("$", "€", "£", "¥")`.
- `format_amount(quantity, commodity, precision) -> str`: section 4.1 (to implement).

**`ledgerlite.parser`**:

- `parse_amount(text) -> Amount`: section 2.4; raises `ValueError` if `text` is invalid.
- `parse_date(text) -> datetime.date`: section 2.2; raises `ValueError` if invalid.
- `parse_string(text, filename="<string>") -> Journal`: parse journal text; `filename` is
  the display name used in errors and for resolving includes.
- `parse_file(path) -> Journal`: read the file (UTF-8) and parse it with display name
  `path` exactly as given. A missing file raises `FileNotFoundError`.

**`ledgerlite.engine`**:

- `commodity_precisions(journal) -> dict` (section 3.1), `posting_weight(posting) -> Amount`
  (section 3.2), `build_ledger(journal) -> Ledger` (sections 3.3 to 3.5),
  `load(path) -> Ledger` (section 3.5), and the class `Ledger` (section 3.7).

**`ledgerlite.reports`**:

- `balance_report(ledger, patterns=(), begin=None, end=None, depth=None, empty=False, total=True, exchange=None, cleared=False) -> str`
- `register_report(ledger, patterns=(), begin=None, end=None, exchange=None, cleared=False) -> str`

`begin`/`end` are `datetime.date` or `None`; `patterns` is a sequence of regex strings;
`exchange` is a commodity string or `None`. Each returns the whole report; every line ends
with `"\n"` and carries no trailing spaces.

**`ledgerlite.cli`**: `main(argv=None) -> int` (section 5). `python3 -m ledgerlite` runs
`sys.exit(main())`.

## 2. Journal syntax

### 2.1 Lines

- A journal is UTF-8 text split on `"\n"`; one trailing `"\r"` is removed from each line.
  Line numbers start at 1.
- A line is *blank* if it is empty or contains only spaces and tabs. A line is *indented*
  if its first character is a space or a tab. A *comment line* is a line whose first
  non-whitespace character is `;` or `#`.
- Indented comment lines are ignored everywhere; they never end or start anything.
- A non-indented, non-blank line is, in this order of checks: a comment line (ignored); a
  transaction header if its first character is a digit; an include directive if its
  first whitespace-separated token is exactly `include`; a price directive if that token
  is exactly `P`; otherwise error `unknown directive 'TOKEN'` (TOKEN = that first token).
- A transaction is its header line plus all immediately following indented lines. It ends
  at the first blank line or non-indented line, including a non-indented comment line and
  any directive. An indented non-comment line that does not belong to a transaction is
  error `unexpected indented line`.
- Inline comments: on transaction headers, posting lines and `P` lines, the first `;` and
  everything after it is a comment. The comment text is what follows the `;`, with
  surrounding whitespace removed (`""` if there is no comment). `include` lines have no
  inline comments.

### 2.2 Transaction header

`DATE [STATUS] [(CODE)] [DESCRIPTION] [; COMMENT]`

- First remove the inline comment. DATE is then the first whitespace-separated token.
  Valid forms are `YYYY-MM-DD` and `YYYY/MM/DD`: exactly 4, 2 and 2 digits, the same
  separator used twice, and a real calendar date. Anything else is error
  `invalid date 'TOKEN'`. `parse_date` applies exactly this rule.
- Remove the date, then strip whitespace from what remains. Then:
  - STATUS: if the rest is exactly `*` or `!`, or starts with `*` or `!` followed by a
    space or tab, that character is the status; remove it and strip again. Otherwise the
    status is `""` (so `2024-01-02 *Coffee` has no status and description `*Coffee`).
  - CODE: if the rest now starts with `(` and contains a `)`, the code is the text between
    the `(` and the first `)`, stripped; remove through that `)` and strip again.
    Otherwise the code is `""`.
  - DESCRIPTION is whatever remains (possibly `""`).
- A transaction without any posting line is error `transaction has no postings`, reported
  at the header's line.

### 2.3 Postings

`INDENT ACCOUNT [SEPARATOR AMOUNTS] [; COMMENT]`

- Remove the inline comment, then leading and trailing whitespace. The SEPARATOR is the
  first occurrence of two consecutive spaces or of a tab. Text before it is the account;
  text after it, stripped, is AMOUNTS. With no separator the whole text is the account
  and the amount is omitted (`amount=None`). Account names may contain single spaces, so
  `Assets:Cash $5` (one space) is the account `Assets:Cash $5` with no amount.
- An account name is one or more segments separated by `:`; every segment must be
  non-empty and must not start or end with a space. Otherwise error
  `invalid account name 'NAME'`.
- AMOUNTS is `[AMOUNT] [@ COST | @@ COST] [= ASSERTION]`, split in this order:
  1. If it contains `=`, split at the first `=`. The right part, stripped, is the
     ASSERTION; continue with the left part, stripped. If the left part is empty: error
     `balance assertion requires an explicit amount`.
  2. If the remaining text contains `@@`, split at the first `@@` (`cost_type="@@"`);
     otherwise, if it contains `@`, split at the first `@` (`cost_type="@"`). The left
     part, stripped, is the AMOUNT and the right part, stripped, is the COST.
  3. AMOUNT, COST and ASSERTION are each parsed with `parse_amount`, in that order. The
     first one that fails gives error `invalid amount 'TEXT'` (TEXT is that stripped part,
     which may be empty: `A  @ $5` gives `invalid amount ''`).
  4. A COST with a negative quantity is error `cost must not be negative`. A COST in the
     same commodity as the AMOUNT is error `cost commodity must differ from amount commodity`.

### 2.4 Amounts

`parse_amount` strips surrounding whitespace, then accepts exactly two forms:

- Symbol form: `[-]SYMBOL[-]NUMBER` where SYMBOL is one of `$ € £ ¥`, with no spaces and
  at most one minus sign, either before or after the symbol: `$5`, `-$5`, `$-5`.
- Code form: `[-]NUMBER CODE` with one or more spaces between NUMBER and CODE, where CODE
  matches `[A-Z][A-Z0-9]*`: `12.50 USD`, `-3 AAPL`, `1,000 EUR`.

NUMBER is either plain digits, or 1 to 3 digits followed by one or more groups of a comma
and exactly 3 digits; either may be followed by `.` and at least one digit. Everything
else is invalid, including `12` (no commodity), `5$`, `USD 5`, `5 usd`, `+$5`, `--$5`,
`.5`, `5.`, `1,23`, `1234,567`, `$ 5`.

The quantity is the number with commas removed and the sign applied, and it keeps the
decimal places as written: `$1,234.50` gives `Decimal("1234.50")`, `-$0.10` gives
`Decimal("-0.10")`, `7 AAPL` gives `Decimal("7")`. A value's *decimal places* is
`max(0, -quantity.as_tuple().exponent)`. A *commodity name* (used by `P` and `-X`) is one
of the four symbols or a CODE.

### 2.5 Directives

- `include PATH`: PATH is the rest of the line after `include`, stripped (it may contain
  spaces; an empty PATH is error `invalid include directive`). The included file's
  transactions and prices are inserted at this point in journal order. Every file has a
  *display name*: the top-level file's is the path given to `parse_file` (or the
  `filename` given to `parse_string`); an included file's is
  `os.path.join(os.path.dirname(PARENT), PATH)`, where PARENT is the including file's
  display name (an absolute PATH therefore stays as written). Display names are never
  normalised; they are used to open the file, in `filename` attributes and in error
  messages. If the display name is not an existing file: error
  `include file not found: PATH`. If the file (compared by `os.path.realpath`) is the
  including file itself or any file further up the current include chain: error
  `include cycle: PATH`. Both errors are reported at the `include` line of the including
  file. Including the same file more than once without a cycle is allowed; its contents
  are inserted each time.
- `P DATE COMMODITY PRICE [; COMMENT]`: after removing the comment, the line is split on
  whitespace into `P`, DATE, COMMODITY and the remaining text (stripped) as PRICE.
  Checked in this order: fewer than four parts is error `invalid price directive`; a bad
  DATE is error `invalid date 'TOKEN'`; a COMMODITY that is not a commodity name is
  error `invalid price directive`; a bad PRICE is error `invalid amount 'TEXT'`; a PRICE
  in the same commodity as COMMODITY is error `invalid price directive`. The directive
  means "one unit of COMMODITY is worth PRICE on DATE".

### 2.6 Parse results and errors

Parsing stops at the first error (in file order) and raises `ParseError(filename, lineno,
message)` with the display name and line of the offending line. Parsed objects record
the `filename` and `lineno` of their own line (a transaction: its header line; a posting:
its line). Journal order is the order of lines after includes are expanded.

## 3. Engine

### 3.1 Display precision

`commodity_precisions(journal)` returns `{commodity: int}` for every commodity that
appears anywhere in the journal (amounts, costs, assertions, `P` commodities and `P`
prices). A commodity's precision is the maximum decimal places among the **posting
amounts and assertion amounts written in the journal** in that commodity. Only if there
are none, it is the maximum decimal places among the cost amounts and `P` prices in that
commodity; if there are none of those either, it is `0`. Omitted (inferred) amounts never
count. Example: `$12.50` in a posting and `@ $1.255` in a cost give `$` precision 2.

### 3.2 Weights

The weight of a posting with an amount, `posting_weight(posting)`, is what it contributes
to balancing:

- no cost: the amount itself;
- `@ COST` (per-unit cost): `Amount(amount.quantity * cost.quantity, cost.commodity)`;
- `@@ COST` (total cost): `cost.quantity` in `cost.commodity`, negated if the amount's
  quantity is negative. `-10 AAPL @@ $1,500` weighs `-$1,500`.

### 3.3 Balancing and amount inference

For each transaction, the residual of commodity C is the exact sum of the weights in C of
the postings that have an amount. A Decimal *rounds to zero* in C if rounding it to C's
precision with `ROUND_HALF_UP` gives zero.

- More than one posting without an amount: error `more than one posting without an amount`.
- Exactly one posting without an amount: take the commodities whose residual does not
  round to zero. If there are none: error `cannot infer amount: transaction already balances`.
  Otherwise the omitted posting is replaced, at its position, by one posting per such
  commodity, sorted by commodity, each with amount `Amount(-residual, C)` (exact, never
  rounded), `inferred=True`, and the omitted posting's account, comment, filename and
  lineno.
- No posting without an amount: every residual must round to zero. Otherwise error
  `transaction does not balance: off by AMOUNTS`, where AMOUNTS lists each residual that
  does not round to zero, sorted by commodity, formatted with `format_amount` at that
  commodity's precision, joined by `", "` (e.g. `off by $0.50, -2 EUR`).

These errors are `BalanceError`s carrying the transaction's header `filename`/`lineno`.

### 3.4 Processing order

`build_ledger(journal)` computes the precisions, then sorts the transactions by date
(stable: transactions with equal dates keep journal order) and balances them in that
order, raising the first `BalanceError` met. It must not modify the journal or any object
in it (the journal still has `amount=None` on omitted postings afterwards).

### 3.5 Balance assertions

Track the running balance of every (account, commodity) pair, using posting **amounts**
(never weights), posting by posting in processing order (sorted transactions; postings in
transaction order, inferred ones included). Right after a posting with an assertion
`= A` is applied, the balance of **exactly that account** (sub-accounts are not
included) in A's commodity, rounded half-up to A's commodity's precision, must equal
A's quantity. Otherwise the result is
`AssertionFailure(filename, lineno, "balance assertion failed for ACCOUNT: expected E, got G")`
at the posting's line, where E and G are the asserted and actual amounts formatted with
`format_amount` at that commodity's precision (a zero balance prints as e.g. `$0.00`).

`build_ledger` does not raise assertion failures; `Ledger.assertion_failures()` returns
all of them, in processing order. `load(path)` is `parse_file`, then `build_ledger`, then
raises the first assertion failure if there is one.

### 3.6 Prices and conversion

`Ledger.price(commodity, target, on_date)` returns a `Decimal` or `None`:

1. If `commodity == target`: `Decimal(1)`.
2. Direct: among the `P` directives for `commodity` priced in `target` dated on or before
   `on_date`, take the latest date; among several on that date, the last one in journal
   order. Return its price quantity.
3. Otherwise inverse: choose a `P` directive for `target` priced in `commodity` the same
   way and return `Decimal(1) / quantity` (default decimal context).
4. Otherwise `None`. There is no chaining through other commodities, and a direct price
   always wins over an inverse one, however recent the inverse one is.

`Ledger.convert(amount, target, on_date)` returns `Amount(amount.quantity * price, target)`,
or the amount unchanged if the price is `None`.

### 3.7 The Ledger object

- `transactions`: the processed transactions in processing order, with inferred postings
  filled in; `prices`: the `Price` objects in journal order; `precisions`: the dict of 3.1.
- `precision(commodity) -> int` (0 for an unknown commodity);
  `format(amount) -> str` is `format_amount(amount.quantity, amount.commodity, self.precision(amount.commodity))`.
- `price(...)`, `convert(...)` (3.6); `assertion_failures()` (3.5);
  `accounts() -> list`: the distinct account names of all postings, sorted (plain
  string order).

## 4. Formatting and reports

### 4.1 Amount formatting

`format_amount(quantity, commodity, precision)`: round to `precision` decimal places with
`ROUND_HALF_UP` (halves go away from zero). A result that is zero has no minus sign. The
integer part is grouped in threes with `,`; when `precision > 0` it is followed by `.` and
exactly `precision` digits. Symbols are written before the number with no space, codes
after it with one space; the minus sign comes first:

| call | result |
|---|---|
| `format_amount(Decimal("1234.5"), "$", 2)` | `$1,234.50` |
| `format_amount(Decimal("-0.125"), "$", 2)` | `-$0.13` |
| `format_amount(Decimal("-0.004"), "€", 2)` | `€0.00` |
| `format_amount(Decimal("-1000"), "USD", 0)` | `-1,000 USD` |
| `format_amount(Decimal("2.5"), "AAPL", 0)` | `3 AAPL` |

A *value* is a set of per-commodity quantities. Its *display components* are its
commodities whose quantity does not round to zero, sorted by commodity, each formatted
with `Ledger.format`. A value without display components is *zero* and prints as the bare
string `0`.

### 4.2 Posting selection (both reports)

1. Take `ledger.transactions` (processing order) whose date satisfies `begin <= date`
   (if `begin` is given; inclusive) and `date < end` (if `end` is given; exclusive), and,
   if `cleared` is true, whose status is `*`.
2. From those, take the postings whose account matches at least one pattern, where a match
   is `re.search(pattern, account, re.IGNORECASE)`. No patterns means every posting.

Reports always use posting amounts, never weights or costs.

### 4.3 Balance report

- Tree: every account with at least one selected posting, plus all of its ancestors
  (`A:B:C` has ancestors `A:B` and `A`). An account's depth is its number of segments.
  An account's value is the sum of the selected posting amounts of the account and of
  all its descendants.
- Conversion: with `exchange`, every account value and the total are converted component
  by component with `Ledger.convert(..., exchange, valuation_date)` and re-summed. The
  valuation date is `end - 1 day` if `end` is given, otherwise the latest transaction
  date in the whole ledger (filters do not change it). Unconvertible components stay in
  their own commodity.
- An account is shown if (`depth` is `None` or its depth `<= depth`) and (`empty` is true,
  or its value, after conversion, is not zero, or at least one of its children is shown).
- Order: depth-first; an account comes before its children; siblings are sorted by their
  last segment (plain string order).
- Let W be the larger of 12 and the length of the longest amount string printed in this
  report (account components, `0`, and the total components when the total is printed).
  Each shown account prints one line per display component (or the single string `0` if
  its value is zero). Every line but the last is `f"{component:>{W}}"`; the last is
  `f"{component:>{W}}  {'  ' * (depth - 1)}{last_segment}"`.
- Unless `total` is false, then print `"-" * W` and one `f"{component:>{W}}"` line per
  display component of the total (the sum of all selected posting amounts, converted at
  the valuation date with `exchange`), or `0` if it is zero.
- With no account lines and `total=False` the report is the empty string.

### 4.4 Register report

One line per selected posting, transactions in processing order and postings in
transaction order:
`f"{date:<10} {description:<22} {account:<20} {amount:>12} {running:>12}"`, with trailing
spaces removed.

- `date` (ISO `YYYY-MM-DD`) and `description` appear only on the first selected posting
  of each transaction; later lines of the same transaction use `""` for both.
- A description longer than 22 characters becomes its first 20 characters plus `..`. An
  account name longer than 20 characters becomes `..` plus its last 18 characters.
  Amount strings are never truncated; a longer string simply pushes the line wider.
- `amount` is `Ledger.format` of the posting amount, converted with `exchange` at the
  transaction's date (an amount without a usable price stays as it is); it always shows
  its commodity, even when zero (`$0.00`).
- The running total is a value: the sum of the (converted) amounts of all selected
  postings so far. Its first display component (or `0` when it is zero) goes in the
  `running` column; each further component goes on its own extra line, formatted the
  same way with every other field `""`.
- No selected postings gives the empty string.

## 5. Command line

`python3 -m ledgerlite [-f FILE] COMMAND [OPTIONS] [PATTERN ...]`

- `-f FILE` / `--file FILE` comes before COMMAND. Without it, the environment variable
  `LEDGERLITE_FILE` is used if it is set and non-empty; `-f` wins when both exist.
- Commands: `balance` (alias `bal`), `register` (alias `reg`), `accounts`, `check`.
- Options, given after COMMAND and before the patterns:
  - `balance` and `register`: `-b DATE`/`--begin DATE`, `-e DATE`/`--end DATE`,
    `-C`/`--cleared`, `-X COMMODITY`/`--exchange COMMODITY`.
  - `balance` only: `-d N`/`--depth N` (an integer, at least 1), `-E`/`--empty`,
    `--no-total`.
  - `accounts` and `check` take no options. Patterns are accepted by `balance`,
    `register` and `accounts`; `check` takes none.
- A DATE option is `YYYY-MM-DD`, `YYYY/MM/DD`, `YYYY-MM` (first day of that month) or
  `YYYY` (January 1st), and must be a real date. COMMODITY must be a commodity name.
- Every command loads the whole journal (parse, build, assertions) first; options and
  patterns never affect validation.
- Output on success (exit 0, nothing on stderr): `balance` and `register` write their
  report string to stdout exactly as returned (no extra newline; an empty report writes
  nothing); `accounts` writes the names from `ledger.accounts()` that match at least one
  pattern (as in 4.2; all if none given), each followed by a newline; `check` writes
  `OK transactions=T postings=N assertions=A prices=P` and a newline, where T is the
  number of transactions, N the number of postings after inference, A the number of
  postings with an assertion, and P the number of `P` directives.
- Exit 1 (journal error): on `ParseError`, `BalanceError` or an assertion failure, print
  nothing on stdout and print `error: ` + `str(error)` + newline on stderr. `check`
  prints one such line for **every** assertion failure (in processing order); the other
  commands print only the first.
- Exit 2 (usage error): unknown or missing command, unknown option, missing or invalid
  option value (DATE, COMMODITY, depth), an invalid regular expression pattern, patterns
  given to `check`, or no journal file given. stdout stays empty; the message goes to
  stderr (its wording is free). Usage errors are detected before the journal is read.
  If the top-level journal file does not exist, stderr is exactly
  `error: journal file not found: FILE` (FILE as given) and the exit code is 2. A missing
  *included* file is a `ParseError` (exit 1).

## 6. Worked example

`examples/basic.journal`:

```
; Example journal for ledgerlite
P 2024-01-01 EUR $1.10

2024-01-01 * Opening balance
    Assets:Bank:Checking        $1,000.00
    Equity:Opening

2024-01-05 * (1001) Grocery store  ; weekly shop
    Expenses:Food:Groceries        $45.20
    Assets:Bank:Checking

2024-01-07 ! Coffee with a colleague from accounting
    Expenses:Food:Dining Out        $4.50
    Assets:Cash

2024-01-10 Salary
    Assets:Bank:Checking        $2,500.00 = $3,454.80
    Income:Salary

2024-01-12 * Currency exchange
    Assets:Bank:Euro            100.00 EUR @ $1.12
    Assets:Bank:Checking
```

`python3 -m ledgerlite -f examples/basic.journal balance` prints:

```
   $3,338.30
  100.00 EUR  Assets
   $3,342.80
  100.00 EUR    Bank
   $3,342.80      Checking
  100.00 EUR      Euro
      -$4.50    Cash
  -$1,000.00  Equity
  -$1,000.00    Opening
      $49.70  Expenses
      $49.70    Food
       $4.50      Dining Out
      $45.20      Groceries
  -$2,500.00  Income
  -$2,500.00    Salary
------------
    -$112.00
  100.00 EUR
```

`python3 -m ledgerlite -f examples/basic.journal register` prints:

```
2024-01-01 Opening balance        Assets:Bank:Checking    $1,000.00    $1,000.00
                                  Equity:Opening         -$1,000.00            0
2024-01-05 Grocery store          ..ses:Food:Groceries       $45.20       $45.20
                                  Assets:Bank:Checking      -$45.20            0
2024-01-07 Coffee with a collea.. ..es:Food:Dining Out        $4.50        $4.50
                                  Assets:Cash                -$4.50            0
2024-01-10 Salary                 Assets:Bank:Checking    $2,500.00    $2,500.00
                                  Income:Salary          -$2,500.00            0
2024-01-12 Currency exchange      Assets:Bank:Euro       100.00 EUR   100.00 EUR
                                  Assets:Bank:Checking     -$112.00     -$112.00
                                                                      100.00 EUR
```

`python3 -m ledgerlite -f examples/basic.journal balance --depth 1 -X EUR` prints:

```
 3,134.82 EUR  Assets
  -909.09 EUR  Equity
    45.18 EUR  Expenses
-2,272.73 EUR  Income
-------------
    -1.82 EUR
```

`python3 -m ledgerlite -f examples/basic.journal check` prints
`OK transactions=5 postings=10 assertions=1 prices=1`.
