"""
SQLAlchemy ORM tables. Every table uses a plain autoincrement integer as
its real primary key (`pk`) plus a separate indexed UUID `id` used in the
API — this is the standard portable pattern (works identically on SQLite
and Postgres) and gives deterministic insertion ordering for free, which
`store.py`'s listing methods rely on.
"""

from __future__ import annotations

from datetime import date as date_type

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class UserRow(Base):
    __tablename__ = "users"

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))


class TokenRow(Base):
    __tablename__ = "tokens"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)


class GroupRow(Base):
    __tablename__ = "groups"

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))

    members: Mapped[list["MemberRow"]] = relationship(
        back_populates="group", cascade="all, delete-orphan", order_by="MemberRow.pk"
    )


class MemberRow(Base):
    __tablename__ = "members"
    __table_args__ = (
        # NULLs (placeholder members) are never considered duplicates by
        # SQL UNIQUE semantics — this only blocks the same real user being
        # linked into the same group twice, as defense-in-depth alongside
        # the application-level check in the router.
        UniqueConstraint("group_id", "user_id", name="uq_member_group_user"),
    )

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("groups.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    group: Mapped["GroupRow"] = relationship(back_populates="members")


class ExpenseRow(Base):
    __tablename__ = "expenses"

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("groups.id"), index=True)
    description: Mapped[str] = mapped_column(String(500))
    amount_cents: Mapped[int] = mapped_column(Integer)
    payer_id: Mapped[str] = mapped_column(String(36))
    date: Mapped[date_type]
    split_method: Mapped[str] = mapped_column(String(20))
    created_by_user_id: Mapped[str] = mapped_column(String(36))

    splits: Mapped[list["ExpenseSplitRow"]] = relationship(
        back_populates="expense", cascade="all, delete-orphan", order_by="ExpenseSplitRow.pk"
    )


class ExpenseSplitRow(Base):
    __tablename__ = "expense_splits"

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    expense_id: Mapped[str] = mapped_column(String(36), ForeignKey("expenses.id"), index=True)
    member_id: Mapped[str] = mapped_column(String(36))
    amount_cents: Mapped[int] = mapped_column(Integer)

    expense: Mapped["ExpenseRow"] = relationship(back_populates="splits")


class RememberedMerchantRow(Base):
    """
    A merchant this user has imported before in this group, so it comes
    pre-selected on their next upload. Scoped to (user, group) — one
    person's history never affects another's, or their own other groups.
    """

    __tablename__ = "remembered_merchants"
    __table_args__ = (
        UniqueConstraint("user_id", "group_id", "merchant", name="uq_remembered_user_group_merchant"),
    )

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("groups.id"), index=True)
    #: Normalized form (see csv_import.normalize_merchant), not the raw description.
    merchant: Mapped[str] = mapped_column(String(500))


class ImportedTransactionRow(Base):
    """
    One row per transaction already turned into an expense, keyed by a
    server-computed fingerprint so re-uploading the same or an overlapping
    statement can never double-import.
    """

    __tablename__ = "imported_transactions"

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("groups.id"), index=True)
    uploader_user_id: Mapped[str] = mapped_column(String(36), index=True)
    expense_id: Mapped[str] = mapped_column(String(36))


class PendingImportRow(Base):
    """
    A parsed-but-not-yet-confirmed upload. Holding the rows server-side
    means the client only ever sends back row ids — it never gets to
    restate (and therefore forge) the amount, date or fingerprint, which
    product-spec.md requires be derived server-side.
    """

    __tablename__ = "pending_imports"

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("groups.id"), index=True)
    uploader_user_id: Mapped[str] = mapped_column(String(36), index=True)

    items: Mapped[list["PendingImportItemRow"]] = relationship(
        back_populates="pending_import", cascade="all, delete-orphan", order_by="PendingImportItemRow.pk"
    )


class PendingImportItemRow(Base):
    __tablename__ = "pending_import_items"

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    import_id: Mapped[str] = mapped_column(String(36), ForeignKey("pending_imports.id"), index=True)
    date: Mapped[date_type]
    description: Mapped[str] = mapped_column(String(500))
    amount_cents: Mapped[int] = mapped_column(Integer)
    fingerprint: Mapped[str] = mapped_column(String(64))
    #: Whether the UI should tick this row by default — a hint, never authority.
    preselected: Mapped[bool] = mapped_column(Boolean, default=False)

    pending_import: Mapped["PendingImportRow"] = relationship(back_populates="items")


class SettlementRow(Base):
    __tablename__ = "settlements"

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("groups.id"), index=True)
    from_member_id: Mapped[str] = mapped_column(String(36))
    to_member_id: Mapped[str] = mapped_column(String(36))
    amount_cents: Mapped[int] = mapped_column(Integer)
    date: Mapped[date_type]
    method: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(String(36))
