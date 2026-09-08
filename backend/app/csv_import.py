"""
CSV parsing and merchant normalization — pure functions, no FastAPI and no
store access, in the same spirit as domain.py. Everything here is a plain
function of its arguments so the fiddly parts (column mapping, decimal-to-
cents, date formats, formula defusal) are testable without a database or a
request.

Banks agree on almost nothing about their exports, so how to read the file
is a parameter (`ColumnMapping`), not a constant: which column is which,
which sign means a charge, and what date format the date column uses.
`detect_mapping` guesses what it safely can from the header and the data;
whatever it can't is the user's call (product-spec.md).
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

# Small-batch personal-finance tool, not a bulk pipeline (product-spec.md).
MAX_UPLOAD_BYTES = 1_000_000
MAX_ROWS = 2_000

#: Header names we recognize without being told, when a file happens to use them.
DEFAULT_COLUMN_NAMES = {"date": "date", "description": "description", "amount": "amount"}

#: How many data rows to hand back for the user to check their mapping against.
SAMPLE_ROWS = 3

DateFormat = Literal["iso", "mdy", "dmy"]
AmountSign = Literal["positive_is_charge", "negative_is_charge"]

_DATE_FORMAT_PATTERNS: dict[str, str] = {"iso": "%Y-%m-%d", "mdy": "%m/%d/%Y", "dmy": "%d/%m/%Y"}
_DATE_FORMAT_LABELS: dict[str, str] = {"iso": "YYYY-MM-DD", "mdy": "MM/DD/YYYY", "dmy": "DD/MM/YYYY"}

# Leading characters a spreadsheet would treat as the start of a formula.
_FORMULA_PREFIXES = ("=", "+", "-", "@")

_WHITESPACE = re.compile(r"\s+")
_SLASH_DATE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")


class CsvFormatError(ValueError):
    """The file as a whole is unusable (bad encoding, no header, unmapped column)."""


@dataclass(frozen=True)
class ColumnMapping:
    """
    How to read one bank's export. `date_column`/`description_column`/
    `amount_column` are header names as they appear in the file.
    """

    date_column: str
    description_column: str
    amount_column: str
    date_format: DateFormat = "iso"
    amount_sign: AmountSign = "positive_is_charge"


@dataclass(frozen=True)
class ParsedRow:
    date: date_type
    description: str
    amount_cents: int


@dataclass(frozen=True)
class SkippedRow:
    line: int
    reason: str


@dataclass(frozen=True)
class ParseResult:
    rows: list[ParsedRow]
    skipped: list[SkippedRow]


@dataclass(frozen=True)
class FileShape:
    """
    What the file looks like before any transaction is read from it: its
    column names, a few sample rows, and the best mapping guess. Enough for
    the user to confirm or correct how their bank's export should be read.
    """

    columns: list[str]
    sample_rows: list[dict[str, str]]
    suggested: ColumnMapping
    #: Columns the guess couldn't fill in — the user must choose these.
    unresolved: list[str]
    #: True when the date format is a coin flip (see detect_mapping).
    date_format_ambiguous: bool


def normalize_merchant(description: str) -> str:
    """
    Case-folded, whitespace-collapsed. Deliberately literal: the spec rules
    out fuzzy matching, so "AMAZON MKTPLACE" and "AMAZON.COM*A1B2C" stay
    different merchants.
    """
    return _WHITESPACE.sub(" ", description.strip()).casefold()


def defuse_formula(description: str) -> str:
    """
    Prefixes a leading =, +, - or @ with an apostrophe so the text can never
    be evaluated as a formula by a spreadsheet downstream. We never evaluate
    cell contents ourselves; this protects whoever exports this data later.
    """
    stripped = description.strip()
    if stripped.startswith(_FORMULA_PREFIXES):
        return "'" + stripped
    return stripped


def fingerprint(
    group_id: str, uploader_user_id: str, row_date: date_type, description: str, amount_cents: int
) -> str:
    """
    Identifies an already-imported transaction. Always computed server-side
    from parsed values and never accepted from the client (product-spec.md's
    dedupe rule). Uses the normalized description so a re-export with
    different casing/spacing still counts as the same transaction.
    """
    parts = "\x1f".join(
        [group_id, uploader_user_id, row_date.isoformat(), normalize_merchant(description), str(amount_cents)]
    )
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()


def _parse_date(raw: str, date_format: DateFormat) -> date_type:
    """Parses in the user's chosen format only — guessing per-row would let
    one file mix MM/DD and DD/MM silently."""
    text = raw.strip()
    try:
        return datetime.strptime(text, _DATE_FORMAT_PATTERNS[date_format]).date()
    except ValueError as exc:
        expected = _DATE_FORMAT_LABELS[date_format]
        raise ValueError(f"could not read date {text!r} — expected {expected}") from exc


def _parse_amount_cents(raw: str) -> int:
    """
    Decimal, never float — binary floats can't represent most cent values
    exactly, and this is the boundary where dollars become the integer cents
    the rest of the app works in.
    """
    cleaned = raw.strip().replace("$", "").replace(",", "")
    if not cleaned:
        raise ValueError("missing amount")
    try:
        dollars = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"could not read amount {raw.strip()!r}") from exc
    cents = (dollars * 100).to_integral_value()
    if cents != dollars * 100:
        raise ValueError(f"amount {raw.strip()!r} is more precise than whole cents")
    return int(cents)


def _read(content: bytes) -> tuple[list[str], list[tuple[int, list[str]]]]:
    """
    Decodes and splits the file into its header and its data records, each
    paired with its real line number in the file — blank lines are dropped
    but still counted, so a skip report points at the line the user sees.
    """
    if len(content) > MAX_UPLOAD_BYTES:
        raise CsvFormatError("That file is too large — please upload a statement under 1 MB.")

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvFormatError("That file isn't valid UTF-8 text.") from exc

    reader = csv.reader(io.StringIO(text))
    try:
        header = [name.strip() for name in next(reader)]
    except StopIteration:
        raise CsvFormatError("That file is empty.") from None

    if not any(header):
        raise CsvFormatError("That file has no header row naming its columns.")

    records = [
        (line, record) for line, record in enumerate(reader, start=2) if any(cell.strip() for cell in record)
    ]
    if len(records) > MAX_ROWS:
        raise CsvFormatError(f"That file has more than {MAX_ROWS} rows — please split it up.")

    return header, records


def _column_index(header: list[str], column: str, role: str) -> int:
    """Header names are matched case-insensitively but are otherwise literal."""
    wanted = column.strip().casefold()
    for i, name in enumerate(header):
        if name.casefold() == wanted:
            return i
    raise CsvFormatError(f"This file has no column named {column!r} to use as the {role}.")


def detect_mapping(content: bytes, previous: ColumnMapping | None = None) -> FileShape:
    """
    Works out what it safely can about a file: column names, a few sample
    rows, and a suggested mapping. `previous` (the user's last mapping for
    this group) wins wherever its columns still exist in this file, since a
    bank's format doesn't change month to month.

    Deliberately does *not* guess between MM/DD/YYYY and DD/MM/YYYY: for
    days <= 12 they're indistinguishable, and picking wrong would silently
    import transactions on the wrong dates. It reports the ambiguity and
    lets the user decide against the sample rows.
    """
    header, records = _read(content)

    by_lower = {name.casefold(): name for name in header if name}
    suggested: dict[str, str] = {}
    unresolved: list[str] = []

    for role, default_name in DEFAULT_COLUMN_NAMES.items():
        from_previous = getattr(previous, f"{role}_column", None) if previous else None
        if from_previous and from_previous.casefold() in by_lower:
            suggested[role] = by_lower[from_previous.casefold()]
        elif default_name in by_lower:
            suggested[role] = by_lower[default_name]
        else:
            # No safe guess — the user picks. First column is a placeholder
            # so the form has something selected; `unresolved` is what says
            # it needs attention.
            suggested[role] = header[0] if header else ""
            unresolved.append(role)

    sample_rows = [
        {name: (record[i] if i < len(record) else "") for i, name in enumerate(header)}
        for _line, record in records[:SAMPLE_ROWS]
    ]

    date_format: DateFormat = previous.date_format if previous else "iso"
    ambiguous = False

    if "date" not in unresolved:
        date_at = _column_index(header, suggested["date"], "date")
        values = [
            r[date_at].strip() for _line, r in records[:20] if date_at < len(r) and r[date_at].strip()
        ]
        if values and all(_looks_iso(v) for v in values):
            date_format = "iso"
        elif values and all(_SLASH_DATE.match(v) for v in values):
            # Slash dates: only the day-part settles it, and only when some
            # row has a day > 12. Otherwise it's a genuine coin flip.
            inferred = _infer_slash_order(values)
            if inferred is not None:
                date_format = inferred
            else:
                date_format = previous.date_format if previous and previous.date_format != "iso" else "mdy"
                ambiguous = True

    return FileShape(
        columns=header,
        sample_rows=sample_rows,
        suggested=ColumnMapping(
            date_column=suggested["date"],
            description_column=suggested["description"],
            amount_column=suggested["amount"],
            date_format=date_format,
            amount_sign=previous.amount_sign if previous else "positive_is_charge",
        ),
        unresolved=unresolved,
        date_format_ambiguous=ambiguous,
    )


def _looks_iso(value: str) -> bool:
    try:
        date_type.fromisoformat(value)
    except ValueError:
        return False
    return True


def _infer_slash_order(values: list[str]) -> DateFormat | None:
    """
    MM/DD vs DD/MM is decidable only if some row has a part > 12. Returns
    None when every row is ambiguous — the caller must ask.
    """
    first_over_12 = any(int(v.split("/")[0]) > 12 for v in values)
    second_over_12 = any(int(v.split("/")[1]) > 12 for v in values)
    if first_over_12 and not second_over_12:
        return "dmy"
    if second_over_12 and not first_over_12:
        return "mdy"
    return None


def parse_csv(content: bytes, mapping: ColumnMapping | None = None) -> ParseResult:
    """
    Reads the file through `mapping` and returns the rows that are charges,
    plus a per-line report of what was skipped. Unparseable rows never fail
    the whole upload (the spec's stated assumption); only a broken
    file-level structure or an unusable mapping does.

    With no mapping, falls back to the conventional
    `date`/`description`/`amount` header names.
    """
    header, records = _read(content)

    if mapping is None:
        mapping = ColumnMapping(
            date_column=DEFAULT_COLUMN_NAMES["date"],
            description_column=DEFAULT_COLUMN_NAMES["description"],
            amount_column=DEFAULT_COLUMN_NAMES["amount"],
        )

    date_at = _column_index(header, mapping.date_column, "date")
    description_at = _column_index(header, mapping.description_column, "description")
    amount_at = _column_index(header, mapping.amount_column, "amount")

    if mapping.date_format not in _DATE_FORMAT_PATTERNS:
        raise CsvFormatError(f"Unknown date format {mapping.date_format!r}.")

    # A charge is whichever sign the user says it is; the other side of the
    # ledger (payments, credits, refunds) is what gets dropped.
    charge_is_negative = mapping.amount_sign == "negative_is_charge"

    rows: list[ParsedRow] = []
    skipped: list[SkippedRow] = []

    for line, record in records:
        try:
            if max(date_at, description_at, amount_at) >= len(record):
                raise ValueError("row has fewer columns than the header")

            row_date = _parse_date(record[date_at], mapping.date_format)
            description = defuse_formula(record[description_at])
            if not description:
                raise ValueError("missing description")
            amount_cents = _parse_amount_cents(record[amount_at])
        except ValueError as exc:
            skipped.append(SkippedRow(line=line, reason=str(exc)))
            continue

        if charge_is_negative:
            amount_cents = -amount_cents

        # The other side of the ledger isn't an expense — silently dropped,
        # not even shown for review (product-spec.md).
        if amount_cents <= 0:
            continue

        rows.append(ParsedRow(date=row_date, description=description, amount_cents=amount_cents))

    return ParseResult(rows=rows, skipped=skipped)
