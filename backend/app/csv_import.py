"""
CSV parsing and merchant normalization — pure functions, no FastAPI and no
store access, in the same spirit as domain.py. Everything here is a plain
function of its arguments so the fiddly parts (header casing, decimal-to-
cents, formula defusal) are testable without a database or a request.

The grammar is fixed by product-spec.md: a header row, then rows of
date / description / amount. Header names are matched case-insensitively
and column order is not assumed.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from datetime import date as date_type
from decimal import Decimal, InvalidOperation

# Small-batch personal-finance tool, not a bulk pipeline (product-spec.md).
MAX_UPLOAD_BYTES = 1_000_000
MAX_ROWS = 2_000

REQUIRED_COLUMNS = ("date", "description", "amount")

# Leading characters a spreadsheet would treat as the start of a formula.
_FORMULA_PREFIXES = ("=", "+", "-", "@")

_WHITESPACE = re.compile(r"\s+")


class CsvFormatError(ValueError):
    """The file as a whole is unusable (bad encoding, no/incomplete header)."""


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


def parse_csv(content: bytes) -> ParseResult:
    """
    Returns the positive-amount rows that parsed, plus a per-line report of
    what was skipped. Unparseable rows never fail the whole upload (the
    spec's stated assumption); only a broken file-level structure does.
    """
    if len(content) > MAX_UPLOAD_BYTES:
        raise CsvFormatError("That file is too large — please upload a statement under 1 MB.")

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvFormatError("That file isn't valid UTF-8 text.") from exc

    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise CsvFormatError("That file is empty.") from None

    # Case-insensitive header lookup; column order is not assumed.
    index_by_column = {name.strip().casefold(): i for i, name in enumerate(header)}
    missing = [column for column in REQUIRED_COLUMNS if column not in index_by_column]
    if missing:
        raise CsvFormatError(
            "The file needs date, description and amount columns — missing: " + ", ".join(missing) + "."
        )

    date_at = index_by_column["date"]
    description_at = index_by_column["description"]
    amount_at = index_by_column["amount"]

    rows: list[ParsedRow] = []
    skipped: list[SkippedRow] = []

    for line, record in enumerate(reader, start=2):
        if not any(cell.strip() for cell in record):
            continue  # blank line
        if len(rows) + len(skipped) >= MAX_ROWS:
            raise CsvFormatError(f"That file has more than {MAX_ROWS} rows — please split it up.")

        try:
            if max(date_at, description_at, amount_at) >= len(record):
                raise ValueError("row has fewer columns than the header")

            row_date = date_type.fromisoformat(record[date_at].strip())
            description = defuse_formula(record[description_at])
            if not description:
                raise ValueError("missing description")
            amount_cents = _parse_amount_cents(record[amount_at])
        except ValueError as exc:
            skipped.append(SkippedRow(line=line, reason=str(exc)))
            continue

        # Payments, credits and refunds aren't expenses — silently dropped,
        # not even shown for review (product-spec.md).
        if amount_cents <= 0:
            continue

        rows.append(ParsedRow(date=row_date, description=description, amount_cents=amount_cents))

    return ParseResult(rows=rows, skipped=skipped)
