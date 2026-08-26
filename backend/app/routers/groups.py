from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import get_current_user, require_group_membership
from app.models import AddLinkedMemberInput, AddPlaceholderMemberInput, CreateGroupInput, Group
from app.store import StoredUser, store

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("", response_model=list[Group])
def list_groups(current_user: StoredUser = Depends(get_current_user)) -> list[Group]:
    return store.groups_for_user(current_user.id)


@router.post("", response_model=Group, status_code=status.HTTP_201_CREATED)
def create_group(body: CreateGroupInput, current_user: StoredUser = Depends(get_current_user)) -> Group:
    return store.create_group(body.name, current_user)


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
