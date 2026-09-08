from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import get_current_user, require_group_membership, require_members
from app.models import Group, Settlement, SettlementInput
from app.store import StoredUser, new_id, store

router = APIRouter(prefix="/groups/{group_id}/settlements", tags=["settlements"])


def _validate_or_400(group: Group, body: SettlementInput) -> None:
    require_members(group, [body.from_member_id, body.to_member_id])
    if body.from_member_id == body.to_member_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A settlement needs two different members.",
        )


def _find_or_404(group_id: str, settlement_id: str) -> Settlement:
    settlement = store.find_settlement(group_id, settlement_id)
    if settlement is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Settlement not found.")
    return settlement


def _require_creator(settlement: Settlement, current_user: StoredUser) -> None:
    if settlement.created_by_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the person who recorded this settlement can edit it.",
        )


@router.get("", response_model=list[Settlement])
def list_settlements(group: Group = Depends(require_group_membership)) -> list[Settlement]:
    return store.list_settlements(group.id)


@router.post("", response_model=Settlement, status_code=status.HTTP_201_CREATED)
def add_settlement(
    body: SettlementInput,
    group: Group = Depends(require_group_membership),
    current_user: StoredUser = Depends(get_current_user),
) -> Settlement:
    _validate_or_400(group, body)

    settlement = Settlement(
        id=new_id(),
        group_id=group.id,
        from_member_id=body.from_member_id,
        to_member_id=body.to_member_id,
        amount_cents=body.amount_cents,
        date=body.date,
        method=body.method,
        created_by_user_id=current_user.id,
    )
    store.add_settlement(settlement)
    return settlement


@router.put("/{settlement_id}", response_model=Settlement)
def update_settlement(
    settlement_id: str,
    body: SettlementInput,
    group: Group = Depends(require_group_membership),
    current_user: StoredUser = Depends(get_current_user),
) -> Settlement:
    existing = _find_or_404(group.id, settlement_id)
    _require_creator(existing, current_user)
    _validate_or_400(group, body)

    updated = existing.model_copy(
        update={
            "from_member_id": body.from_member_id,
            "to_member_id": body.to_member_id,
            "amount_cents": body.amount_cents,
            "date": body.date,
            "method": body.method,
        }
    )
    store.replace_settlement(group.id, settlement_id, updated)
    return updated


@router.delete("/{settlement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_settlement(
    settlement_id: str,
    group: Group = Depends(require_group_membership),
    current_user: StoredUser = Depends(get_current_user),
) -> None:
    existing = _find_or_404(group.id, settlement_id)
    _require_creator(existing, current_user)
    store.delete_settlement(group.id, settlement_id)
