from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import get_current_user, require_group_membership
from app.models import (
    AddLinkedMemberInput,
    AddPlaceholderMemberInput,
    CreateGroupInput,
    Group,
    RenameMemberInput,
    UpdateGroupInput,
)
from app.store import StoredUser, store

router = APIRouter(prefix="/groups", tags=["groups"])


def _clean(description: str | None) -> str | None:
    """Blank is stored as no description."""
    return (description or "").strip() or None


@router.get("", response_model=list[Group])
def list_groups(current_user: StoredUser = Depends(get_current_user)) -> list[Group]:
    return store.groups_for_user(current_user.id)


@router.post("", response_model=Group, status_code=status.HTTP_201_CREATED)
def create_group(body: CreateGroupInput, current_user: StoredUser = Depends(get_current_user)) -> Group:
    return store.create_group(body.name.strip(), current_user, _clean(body.description))


@router.get("/{group_id}", response_model=Group)
def get_group(group: Group = Depends(require_group_membership)) -> Group:
    return group


@router.post("/{group_id}/members/linked", response_model=Group)
def add_linked_member(
    body: AddLinkedMemberInput, group: Group = Depends(require_group_membership)
) -> Group:
    target = store.find_user_by_email(body.email)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No account found for that email.")
    if store.is_linked_member(group, target.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That person is already in the group.")

    return store.add_linked_member(group.id, target)


@router.post("/{group_id}/members/placeholder", response_model=Group)
def add_placeholder_member(
    body: AddPlaceholderMemberInput, group: Group = Depends(require_group_membership)
) -> Group:
    return store.add_placeholder_member(group.id, body.display_name.strip())


@router.put("/{group_id}", response_model=Group)
def update_group(body: UpdateGroupInput, group: Group = Depends(require_group_membership)) -> Group:
    return store.update_group(group.id, body.name.strip(), _clean(body.description))


def _find_member(group: Group, member_id: str):
    member = next((m for m in group.members if m.id == member_id), None)
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")
    return member


@router.put("/{group_id}/members/{member_id}", response_model=Group)
def rename_member(
    member_id: str,
    body: RenameMemberInput,
    group: Group = Depends(require_group_membership),
) -> Group:
    member = _find_member(group, member_id)
    if member.user_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only members without an account can be renamed.",
        )
    return store.rename_member(group.id, member.id, body.display_name.strip())


@router.delete("/{group_id}/members/{member_id}", response_model=Group)
def remove_member(
    member_id: str,
    group: Group = Depends(require_group_membership),
    current_user: StoredUser = Depends(get_current_user),
) -> Group:
    member = _find_member(group, member_id)
    if member.user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You can't remove yourself.")
    if store.member_is_referenced(group.id, member.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That member appears in expenses or settlements, so they can't be removed.",
        )
    return store.remove_member(group.id, member.id)
