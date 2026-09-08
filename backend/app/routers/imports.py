"""
CSV transaction import. Two steps, and the split matters: uploading only
parses and stages — it creates nothing. Every transaction is returned for
review, with merchants this user has imported before in this group ticked
by default, and only the rows they confirm become expenses.

The staged rows stay server-side, so confirming sends nothing but row ids:
the amount, date and dedupe fingerprint are always derived here and never
taken from the client (product-spec.md).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.auth import get_current_user, require_group_membership
from app.csv_import import (
    MAX_UPLOAD_BYTES,
    CsvFormatError,
    fingerprint,
    normalize_merchant,
    parse_csv,
)
from app.domain import resolve_splits
from app.models import (
    ConfirmImportInput,
    EqualSplitInput,
    Expense,
    Group,
    ImportPreview,
    ImportResult,
    ReviewRow,
    SkippedRow,
)
from app.store import PendingItem, StoredUser, new_id, store

router = APIRouter(prefix="/groups/{group_id}/imports", tags=["imports"])


def _uploader_member_id(group: Group, user: StoredUser) -> str:
    """
    The uploader pays for what they import. They're a linked member of this
    group (require_group_membership guarantees it), so this always resolves.
    """
    return next(m.id for m in group.members if m.user_id == user.id)


@router.post("", response_model=ImportPreview, status_code=status.HTTP_200_OK)
async def upload_csv(
    file: UploadFile = File(...),
    group: Group = Depends(require_group_membership),
    current_user: StoredUser = Depends(get_current_user),
) -> ImportPreview:
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="That file is too large — please upload a statement under 1 MB.",
        )

    try:
        parsed = parse_csv(content)
    except CsvFormatError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

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
