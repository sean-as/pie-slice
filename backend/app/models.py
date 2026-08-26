"""
Pydantic schemas mirroring ../openapi.yaml's components/schemas exactly.

Wire format is camelCase (matching the frontend's TypeScript types in
frontend/src/domain/types.ts and services/types.ts); Python code elsewhere
in this app uses snake_case field names — `populate_by_name=True` on every
model makes both work, and FastAPI serializes responses using the alias
(camelCase) by default.
"""

from __future__ import annotations

from datetime import date as date_type
from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class SignupInput(ApiModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str = Field(min_length=1, alias="displayName")


class LoginInput(ApiModel):
    email: EmailStr
    password: str


class User(ApiModel):
    """Never carries a password/passwordHash — this is what's safe to hand to the client."""

    id: str
    email: EmailStr
    display_name: str = Field(alias="displayName")


class AuthResponse(ApiModel):
    user: User
    token: str


# ---------------------------------------------------------------------------
# Groups & members
# ---------------------------------------------------------------------------


class Member(ApiModel):
    id: str
    display_name: str = Field(alias="displayName")
    user_id: str | None = Field(alias="userId")


class Group(ApiModel):
    id: str
    name: str
    members: list[Member]


class CreateGroupInput(ApiModel):
    name: str = Field(min_length=1)


class AddLinkedMemberInput(ApiModel):
    email: EmailStr


class AddPlaceholderMemberInput(ApiModel):
    display_name: str = Field(min_length=1, alias="displayName")


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------

SplitMethod = Literal["equal", "exact", "percent", "shares"]


class Split(ApiModel):
    """Final resolved per-member cents — always present on a stored Expense regardless of splitMethod."""

    member_id: str = Field(alias="memberId")
    amount_cents: int = Field(alias="amountCents")


class EqualSplitInput(ApiModel):
    method: Literal["equal"]
    member_ids: list[str] = Field(min_length=1, alias="memberIds")


class ExactSplitAmount(ApiModel):
    member_id: str = Field(alias="memberId")
    amount_cents: int = Field(alias="amountCents")


class ExactSplitInput(ApiModel):
    method: Literal["exact"]
    amounts: list[ExactSplitAmount] = Field(min_length=1)


class PercentSplitPercentage(ApiModel):
    member_id: str = Field(alias="memberId")
    percent: float


class PercentSplitInput(ApiModel):
    method: Literal["percent"]
    percentages: list[PercentSplitPercentage] = Field(min_length=1)


class SharesSplitShare(ApiModel):
    member_id: str = Field(alias="memberId")
    shares: int = Field(ge=1)


class SharesSplitInput(ApiModel):
    method: Literal["shares"]
    shares: list[SharesSplitShare] = Field(min_length=1)


SplitInput = Union[EqualSplitInput, ExactSplitInput, PercentSplitInput, SharesSplitInput]


class ExpenseInput(ApiModel):
    description: str
    amount_cents: int = Field(gt=0, alias="amountCents")
    payer_id: str = Field(alias="payerId")
    date: date_type
    split_method: SplitMethod = Field(alias="splitMethod")
    split_input: SplitInput = Field(alias="splitInput", discriminator="method")


class Expense(ApiModel):
    id: str
    group_id: str = Field(alias="groupId")
    description: str
    amount_cents: int = Field(alias="amountCents")
    payer_id: str = Field(alias="payerId")
    date: date_type
    split_method: SplitMethod = Field(alias="splitMethod")
    splits: list[Split]
    created_by_user_id: str = Field(alias="createdByUserId")


# ---------------------------------------------------------------------------
# Settlements
# ---------------------------------------------------------------------------


class SettlementInput(ApiModel):
    from_member_id: str = Field(alias="fromMemberId")
    to_member_id: str = Field(alias="toMemberId")
    amount_cents: int = Field(gt=0, alias="amountCents")
    date: date_type
    method: str | None = None


class Settlement(ApiModel):
    id: str
    group_id: str = Field(alias="groupId")
    from_member_id: str = Field(alias="fromMemberId")
    to_member_id: str = Field(alias="toMemberId")
    amount_cents: int = Field(alias="amountCents")
    date: date_type
    method: str | None = None
    created_by_user_id: str = Field(alias="createdByUserId")


# ---------------------------------------------------------------------------
# Balances
# ---------------------------------------------------------------------------


class MemberBalance(ApiModel):
    member_id: str = Field(alias="memberId")
    net_cents: int = Field(alias="netCents")


class SettleUpTransfer(ApiModel):
    from_member_id: str = Field(alias="fromMemberId")
    to_member_id: str = Field(alias="toMemberId")
    amount_cents: int = Field(alias="amountCents")


class BalancesResult(ApiModel):
    balances: list[MemberBalance]
    settle_up: list[SettleUpTransfer] = Field(alias="settleUp")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class Error(ApiModel):
    detail: str
