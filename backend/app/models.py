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
# CSV import
# ---------------------------------------------------------------------------


DateFormat = Literal["iso", "mdy", "dmy"]
AmountSign = Literal["positive_is_charge", "negative_is_charge"]


class ColumnMapping(ApiModel):
    """
    How to read one bank's export: which column is which, which sign means
    a charge, and what date format the date column uses. Column values are
    header names as they appear in the file.
    """

    date_column: str = Field(min_length=1, alias="dateColumn")
    description_column: str = Field(min_length=1, alias="descriptionColumn")
    amount_column: str = Field(min_length=1, alias="amountColumn")
    date_format: DateFormat = Field(default="iso", alias="dateFormat")
    amount_sign: AmountSign = Field(default="positive_is_charge", alias="amountSign")


class FileShape(ApiModel):
    """
    What a file looks like before any transaction is read from it — enough
    for the user to confirm or correct how it should be read. Nothing is
    parsed into transactions and nothing is stored at this point.
    """

    columns: list[str]
    #: A few raw data rows, keyed by column name, to check the mapping against.
    sample_rows: list[dict[str, str]] = Field(alias="sampleRows")
    suggested: ColumnMapping
    #: Roles ("date"/"description"/"amount") the guess couldn't fill in.
    unresolved: list[str]
    #: True when MM/DD vs DD/MM can't be told apart from this file's data.
    date_format_ambiguous: bool = Field(alias="dateFormatAmbiguous")


class ReviewRow(ApiModel):
    """
    One transaction awaiting the user's yes/no. `preselected` is a UI
    default (the merchant was imported before in this group), never an
    authorization — the confirm call's explicit id list is what counts.
    """

    id: str
    date: date_type
    description: str
    amount_cents: int = Field(alias="amountCents")
    preselected: bool


class SkippedRow(ApiModel):
    line: int
    reason: str


class ImportPreview(ApiModel):
    """Result of an upload. Creates nothing — everything here awaits a confirm."""

    import_id: str = Field(alias="importId")
    rows: list[ReviewRow]
    skipped: list[SkippedRow]
    duplicate_count: int = Field(alias="duplicateCount")


class ConfirmImportInput(ApiModel):
    row_ids: list[str] = Field(alias="rowIds")


class ImportResult(ApiModel):
    imported: list[Expense]


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
