from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import require_group_membership
from app.domain import compute_balances
from app.models import BalancesResult, Group
from app.store import store

router = APIRouter(prefix="/groups/{group_id}/balances", tags=["balances"])


@router.get("", response_model=BalancesResult)
def get_balances(group: Group = Depends(require_group_membership)) -> BalancesResult:
    member_ids = [m.id for m in group.members]
    return compute_balances(member_ids, store.list_expenses(group.id), store.list_settlements(group.id))
