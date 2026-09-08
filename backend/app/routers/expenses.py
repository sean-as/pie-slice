from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import get_current_user, require_group_membership, require_members
from app.domain import SplitValidationError, resolve_splits
from app.models import Expense, ExpenseInput, Group, Split
from app.store import StoredUser, new_id, store

router = APIRouter(prefix="/groups/{group_id}/expenses", tags=["expenses"])


def _resolve_or_400(group: Group, body: ExpenseInput) -> list[Split]:
    """Validates every member id the body names, then resolves the split to final cents."""
    require_members(group, [body.payer_id])
    try:
        splits = resolve_splits(body.amount_cents, body.split_input)
    except SplitValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    require_members(group, [s.member_id for s in splits])
    return splits


def _find_or_404(group_id: str, expense_id: str) -> Expense:
    expense = store.find_expense(group_id, expense_id)
    if expense is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found.")
    return expense


def _require_creator(expense: Expense, current_user: StoredUser) -> None:
    if expense.created_by_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the person who logged this expense can edit it.",
        )


@router.get("", response_model=list[Expense])
def list_expenses(group: Group = Depends(require_group_membership)) -> list[Expense]:
    return store.list_expenses(group.id)


@router.post("", response_model=Expense, status_code=status.HTTP_201_CREATED)
def add_expense(
    body: ExpenseInput,
    group: Group = Depends(require_group_membership),
    current_user: StoredUser = Depends(get_current_user),
) -> Expense:
    splits = _resolve_or_400(group, body)

    expense = Expense(
        id=new_id(),
        group_id=group.id,
        description=body.description,
        amount_cents=body.amount_cents,
        payer_id=body.payer_id,
        date=body.date,
        split_method=body.split_method,
        splits=splits,
        created_by_user_id=current_user.id,
    )
    store.add_expense(expense)
    return expense


@router.put("/{expense_id}", response_model=Expense)
def update_expense(
    expense_id: str,
    body: ExpenseInput,
    group: Group = Depends(require_group_membership),
    current_user: StoredUser = Depends(get_current_user),
) -> Expense:
    existing = _find_or_404(group.id, expense_id)
    _require_creator(existing, current_user)

    splits = _resolve_or_400(group, body)

    updated = existing.model_copy(
        update={
            "description": body.description,
            "amount_cents": body.amount_cents,
            "payer_id": body.payer_id,
            "date": body.date,
            "split_method": body.split_method,
            "splits": splits,
        }
    )
    store.replace_expense(group.id, expense_id, updated)
    return updated


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(
    expense_id: str,
    group: Group = Depends(require_group_membership),
    current_user: StoredUser = Depends(get_current_user),
) -> None:
    existing = _find_or_404(group.id, expense_id)
    _require_creator(existing, current_user)
    store.delete_expense(group.id, expense_id)
