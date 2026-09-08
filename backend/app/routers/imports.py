"""
CSV transaction import, in three steps. Banks disagree on column names,
amount signs and date formats, so the file is first *inspected* — we hand
back its columns, a few sample rows and our best guess at how to read it.
The user confirms or corrects that, then *uploads* with an explicit
mapping, which parses and stages but creates nothing. Every transaction is
returned for review, with merchants imported before in this group ticked by
default, and only the rows they *confirm* become expenses.

Inspecting doesn't store the file, so the upload re-sends it — a deliberate
trade against retaining statements server-side (product-spec.md non-goals)
that costs one extra transfer of a file capped at 1 MB.

The staged rows stay server-side, so confirming sends nothing but row ids:
the amount, date and dedupe fingerprint are always derived here and never
taken from the client (product-spec.md).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.auth import get_current_user, require_group_membership
from app.csv_import import (
    MAX_UPLOAD_BYTES,
    CsvFormatError,
    detect_mapping,
    fingerprint,
    normalize_merchant,
    parse_csv,
)
from app.csv_import import ColumnMapping as ParserMapping
from app.domain import resolve_splits
from app.models import (
    AmountSign,
    ColumnMapping,
    ConfirmImportInput,
    DateFormat,
    EqualSplitInput,
    Expense,
    FileShape,
    Group,
    ImportPreview,
    ImportResult,
    ReviewRow,
    SkippedRow,
)
from app.store import PendingItem, StoredUser, new_id, store

router = APIRouter(prefix="/groups/{group_id}/imports", tags=["imports"])


def _to_parser(mapping: ColumnMapping) -> ParserMapping:
    """The API schema and the parser's own dataclass carry the same fields."""
    return ParserMapping(
        date_column=mapping.date_column,
        description_column=mapping.description_column,
        amount_column=mapping.amount_column,
        date_format=mapping.date_format,
        amount_sign=mapping.amount_sign,
    )


async def _read_upload(file: UploadFile) -> bytes:
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="That file is too large — please upload a statement under 1 MB.",
        )
    return content


def _uploader_member_id(group: Group, user: StoredUser) -> str:
    """
    The uploader pays for what they import. They're a linked member of this
    group (require_group_membership guarantees it), so this always resolves.
    """
    return next(m.id for m in group.members if m.user_id == user.id)


@router.post("/inspect", response_model=FileShape)
async def inspect_csv(
    file: UploadFile = File(...),
    group: Group = Depends(require_group_membership),
    current_user: StoredUser = Depends(get_current_user),
) -> FileShape:
    """
    Reads only the file's shape — columns, a few sample rows, and a
    suggested mapping seeded from whatever this user last used for this
    group. Creates nothing and stores nothing.
    """
    content = await _read_upload(file)
    previous = store.get_import_mapping(current_user.id, group.id)

    try:
        shape = detect_mapping(content, _to_parser(previous) if previous else None)
    except CsvFormatError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return FileShape(
        columns=shape.columns,
        sample_rows=shape.sample_rows,
        suggested=ColumnMapping(
            date_column=shape.suggested.date_column,
            description_column=shape.suggested.description_column,
            amount_column=shape.suggested.amount_column,
            date_format=shape.suggested.date_format,
            amount_sign=shape.suggested.amount_sign,
        ),
        unresolved=shape.unresolved,
        date_format_ambiguous=shape.date_format_ambiguous,
    )


@router.post("", response_model=ImportPreview, status_code=status.HTTP_200_OK)
async def upload_csv(
    file: UploadFile = File(...),
    date_column: str | None = Form(None, alias="dateColumn"),
    description_column: str | None = Form(None, alias="descriptionColumn"),
    amount_column: str | None = Form(None, alias="amountColumn"),
    date_format: DateFormat = Form("iso", alias="dateFormat"),
    amount_sign: AmountSign = Form("positive_is_charge", alias="amountSign"),
    group: Group = Depends(require_group_membership),
    current_user: StoredUser = Depends(get_current_user),
) -> ImportPreview:
    content = await _read_upload(file)

    # The three column names travel together: all of them, or none (in
    # which case the conventional date/description/amount headers are
    # assumed, which is what a client that never inspected would send).
    named = [date_column, description_column, amount_column]
    if any(named) and not all(named):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Name all three columns (date, description, amount) or none of them.",
        )

    mapping = (
        ColumnMapping(
            date_column=date_column,  # type: ignore[arg-type]
            description_column=description_column,  # type: ignore[arg-type]
            amount_column=amount_column,  # type: ignore[arg-type]
            date_format=date_format,
            amount_sign=amount_sign,
        )
        if all(named)
        else None
    )

    try:
        parsed = parse_csv(content, _to_parser(mapping) if mapping else None)
    except CsvFormatError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # Remembered only once the file actually parsed under it, so a mapping
    # that names a nonexistent column never becomes next month's default.
    if mapping is not None:
        store.save_import_mapping(current_user.id, group.id, mapping)

    fingerprints = [
        fingerprint(group.id, current_user.id, row.date, row.description, row.amount_cents)
        for row in parsed.rows
    ]
    already_imported = store.known_fingerprints(group.id, current_user.id, fingerprints)
    remembered = store.remembered_merchants(current_user.id, group.id)

    items: list[PendingItem] = []
    duplicate_count = 0
    seen_in_file: set[str] = set()

    for row, row_fingerprint in zip(parsed.rows, fingerprints):
        # Already imported, or a repeat of an identical row earlier in this
        # same file — either way it must not become a second expense.
        if row_fingerprint in already_imported or row_fingerprint in seen_in_file:
            duplicate_count += 1
            continue
        seen_in_file.add(row_fingerprint)

        items.append(
            PendingItem(
                id=new_id(),
                date=row.date,
                description=row.description,
                amount_cents=row.amount_cents,
                fingerprint=row_fingerprint,
                preselected=normalize_merchant(row.description) in remembered,
            )
        )

    import_id = store.create_pending_import(group.id, current_user.id, items)

    return ImportPreview(
        import_id=import_id,
        rows=[
            ReviewRow(
                id=item.id,
                date=item.date,
                description=item.description,
                amount_cents=item.amount_cents,
                preselected=item.preselected,
            )
            for item in items
        ],
        skipped=[SkippedRow(line=s.line, reason=s.reason) for s in parsed.skipped],
        duplicate_count=duplicate_count,
    )


@router.post("/{import_id}/confirm", response_model=ImportResult)
def confirm_import(
    import_id: str,
    body: ConfirmImportInput,
    group: Group = Depends(require_group_membership),
    current_user: StoredUser = Depends(get_current_user),
) -> ImportResult:
    items = store.get_pending_import(import_id, group.id, current_user.id)
    if items is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That import has expired or was already submitted.")

    by_id = {item.id: item for item in items}
    unknown = [row_id for row_id in body.row_ids if row_id not in by_id]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That transaction isn't part of this import.",
        )

    payer_id = _uploader_member_id(group, current_user)
    member_ids = [m.id for m in group.members]

    imported: list[Expense] = []
    fingerprint_pairs: list[tuple[str, str]] = []
    merchants: set[str] = set()

    # Iterating the staged rows (not the request body) deduplicates the id
    # list for free, so a repeated id can't create the same expense twice.
    selected = set(body.row_ids)
    for item in items:
        if item.id not in selected:
            continue

        expense = Expense(
            id=new_id(),
            group_id=group.id,
            description=item.description,
            amount_cents=item.amount_cents,
            payer_id=payer_id,
            date=item.date,
            split_method="equal",
            splits=resolve_splits(item.amount_cents, EqualSplitInput(method="equal", member_ids=member_ids)),
            created_by_user_id=current_user.id,
        )
        store.add_expense(expense)
        imported.append(expense)
        fingerprint_pairs.append((item.fingerprint, expense.id))
        merchants.add(normalize_merchant(item.description))

    store.record_imported_transactions(group.id, current_user.id, fingerprint_pairs)
    # Importing is what remembers a merchant — there's no separate opt-in.
    # Rows left unticked are simply skipped and change nothing.
    store.remember_merchants(current_user.id, group.id, merchants)
    store.delete_pending_import(import_id)

    return ImportResult(imported=imported)
