"""
Data-access layer — every router calls methods on the single `store`
instance below and never touches SQLAlchemy directly. Each method opens its
own short-lived session, converts ORM rows to the same Pydantic schemas
used everywhere else in the app (models.py), and returns those — so this
file is the *only* place that knows a database is involved at all.

This used to be plain in-memory dicts; the public API is unchanged, so
nothing in routers/ or auth.py had to change when it was swapped for
SQLAlchemy underneath.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import date as date_type

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base, SessionLocal, engine
from app.db_models import (
    ExpenseRow,
    ExpenseSplitRow,
    GroupRow,
    ImportedTransactionRow,
    ImportMappingRow,
    MemberRow,
    PendingImportItemRow,
    PendingImportRow,
    RememberedMerchantRow,
    SettlementRow,
    TokenRow,
    UserRow,
)
from app.models import ColumnMapping, Expense, Group, Member, Settlement, Split, User


def new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class StoredUser:
    """Internal representation carrying the password hash — never sent to the client (see User in models.py)."""

    id: str
    email: str
    display_name: str
    password_hash: str

    def to_public(self) -> User:
        return User(id=self.id, email=self.email, display_name=self.display_name)


@dataclass
class PendingItem:
    """One staged CSV row. Lives server-side between upload and confirm."""

    id: str
    date: date_type
    description: str
    amount_cents: int
    fingerprint: str
    preselected: bool
    category: str | None = None
    already_imported: bool = False


def _user_row_to_stored(row: UserRow) -> StoredUser:
    return StoredUser(id=row.id, email=row.email, display_name=row.display_name, password_hash=row.password_hash)


def _member_row_to_pydantic(row: MemberRow) -> Member:
    return Member(id=row.id, display_name=row.display_name, user_id=row.user_id)


def _expense_row_to_pydantic(row: ExpenseRow) -> Expense:
    return Expense(
        id=row.id,
        group_id=row.group_id,
        description=row.description,
        amount_cents=row.amount_cents,
        payer_id=row.payer_id,
        date=row.date,
        split_method=row.split_method,
        splits=[Split(member_id=s.member_id, amount_cents=s.amount_cents) for s in row.splits],
        created_by_user_id=row.created_by_user_id,
        category=row.category,
    )


def _settlement_row_to_pydantic(row: SettlementRow) -> Settlement:
    return Settlement(
        id=row.id,
        group_id=row.group_id,
        from_member_id=row.from_member_id,
        to_member_id=row.to_member_id,
        amount_cents=row.amount_cents,
        date=row.date,
        method=row.method,
        created_by_user_id=row.created_by_user_id,
    )


def _group_by_id(session: Session, group_id: str) -> GroupRow | None:
    return session.execute(select(GroupRow).where(GroupRow.id == group_id)).scalar_one_or_none()


def _group_row_to_pydantic(row: GroupRow) -> Group:
    return Group(id=row.id, name=row.name, members=[_member_row_to_pydantic(m) for m in row.members])


class Store:
    # ---- users ----

    def find_user_by_email(self, email: str) -> StoredUser | None:
        normalized = email.strip().lower()
        with SessionLocal() as session:
            row = session.execute(select(UserRow).where(UserRow.email == normalized)).scalar_one_or_none()
            return _user_row_to_stored(row) if row else None

    def create_user(self, email: str, display_name: str, password_hash: str) -> StoredUser:
        with SessionLocal() as session:
            row = UserRow(
                id=new_id(),
                email=email.strip().lower(),
                display_name=display_name.strip(),
                password_hash=password_hash,
            )
            session.add(row)
            session.commit()
            return _user_row_to_stored(row)

    def get_user(self, user_id: str) -> StoredUser | None:
        with SessionLocal() as session:
            row = session.execute(select(UserRow).where(UserRow.id == user_id)).scalar_one_or_none()
            return _user_row_to_stored(row) if row else None

    # ---- tokens ----

    def issue_token(self, user_id: str) -> str:
        token = secrets.token_hex(32)
        with SessionLocal() as session:
            session.add(TokenRow(token=token, user_id=user_id))
            session.commit()
        return token

    def user_id_for_token(self, token: str) -> str | None:
        with SessionLocal() as session:
            row = session.execute(select(TokenRow).where(TokenRow.token == token)).scalar_one_or_none()
            return row.user_id if row else None

    def revoke_token(self, token: str) -> None:
        with SessionLocal() as session:
            row = session.execute(select(TokenRow).where(TokenRow.token == token)).scalar_one_or_none()
            if row is not None:
                session.delete(row)
                session.commit()

    # ---- groups & membership ----

    def is_linked_member(self, group: Group | None, user_id: str) -> bool:
        return group is not None and any(m.user_id == user_id for m in group.members)

    def get_group_for_member(self, group_id: str, user_id: str) -> Group | None:
        """None for both 'doesn't exist' and 'exists but you're not a member' — never leak which."""
        with SessionLocal() as session:
            row = _group_by_id(session, group_id)
            if row is None:
                return None
            group = _group_row_to_pydantic(row)
            return group if self.is_linked_member(group, user_id) else None

    def groups_for_user(self, user_id: str) -> list[Group]:
        with SessionLocal() as session:
            member_group_ids = (
                session.execute(select(MemberRow.group_id).where(MemberRow.user_id == user_id)).scalars().all()
            )
            rows = (
                session.execute(select(GroupRow).where(GroupRow.id.in_(member_group_ids)).order_by(GroupRow.pk))
                .scalars()
                .all()
            )
            return [_group_row_to_pydantic(r) for r in rows]

    def create_group(self, name: str, creator: StoredUser) -> Group:
        with SessionLocal() as session:
            group_row = GroupRow(id=new_id(), name=name)
            session.add(group_row)
            session.flush()
            session.add(
                MemberRow(id=new_id(), group_id=group_row.id, display_name=creator.display_name, user_id=creator.id)
            )
            session.commit()
            session.refresh(group_row)
            return _group_row_to_pydantic(group_row)

    def add_linked_member(self, group_id: str, target: StoredUser) -> Group:
        with SessionLocal() as session:
            session.add(
                MemberRow(id=new_id(), group_id=group_id, display_name=target.display_name, user_id=target.id)
            )
            session.commit()
            row = _group_by_id(session, group_id)
            return _group_row_to_pydantic(row) if row else None  # type: ignore[return-value]

    def add_placeholder_member(self, group_id: str, display_name: str) -> Group:
        with SessionLocal() as session:
            session.add(MemberRow(id=new_id(), group_id=group_id, display_name=display_name, user_id=None))
            session.commit()
            row = _group_by_id(session, group_id)
            return _group_row_to_pydantic(row) if row else None  # type: ignore[return-value]

    # ---- expenses ----

    def list_expenses(self, group_id: str) -> list[Expense]:
        with SessionLocal() as session:
            rows = (
                session.execute(select(ExpenseRow).where(ExpenseRow.group_id == group_id).order_by(ExpenseRow.pk))
                .scalars()
                .all()
            )
            return [_expense_row_to_pydantic(r) for r in rows]

    def add_expense(self, expense: Expense) -> None:
        with SessionLocal() as session:
            row = ExpenseRow(
                id=expense.id,
                group_id=expense.group_id,
                description=expense.description,
                amount_cents=expense.amount_cents,
                payer_id=expense.payer_id,
                date=expense.date,
                split_method=expense.split_method,
                created_by_user_id=expense.created_by_user_id,
                category=expense.category,
            )
            row.splits = [
                ExpenseSplitRow(member_id=s.member_id, amount_cents=s.amount_cents) for s in expense.splits
            ]
            session.add(row)
            session.commit()

    def find_expense(self, group_id: str, expense_id: str) -> Expense | None:
        with SessionLocal() as session:
            row = session.execute(
                select(ExpenseRow).where(ExpenseRow.group_id == group_id, ExpenseRow.id == expense_id)
            ).scalar_one_or_none()
            return _expense_row_to_pydantic(row) if row else None

    def replace_expense(self, group_id: str, expense_id: str, updated: Expense) -> None:
        with SessionLocal() as session:
            row = session.execute(
                select(ExpenseRow).where(ExpenseRow.group_id == group_id, ExpenseRow.id == expense_id)
            ).scalar_one_or_none()
            if row is None:
                return
            row.description = updated.description
            row.amount_cents = updated.amount_cents
            row.payer_id = updated.payer_id
            row.date = updated.date
            row.split_method = updated.split_method
            row.category = updated.category
            row.splits = [
                ExpenseSplitRow(member_id=s.member_id, amount_cents=s.amount_cents) for s in updated.splits
            ]
            session.commit()

    def delete_expense(self, group_id: str, expense_id: str) -> None:
        with SessionLocal() as session:
            row = session.execute(
                select(ExpenseRow).where(ExpenseRow.group_id == group_id, ExpenseRow.id == expense_id)
            ).scalar_one_or_none()
            if row is not None:
                session.delete(row)
                session.commit()

    # ---- settlements ----

    def list_settlements(self, group_id: str) -> list[Settlement]:
        with SessionLocal() as session:
            rows = (
                session.execute(
                    select(SettlementRow).where(SettlementRow.group_id == group_id).order_by(SettlementRow.pk)
                )
                .scalars()
                .all()
            )
            return [_settlement_row_to_pydantic(r) for r in rows]

    def add_settlement(self, settlement: Settlement) -> None:
        with SessionLocal() as session:
            session.add(
                SettlementRow(
                    id=settlement.id,
                    group_id=settlement.group_id,
                    from_member_id=settlement.from_member_id,
                    to_member_id=settlement.to_member_id,
                    amount_cents=settlement.amount_cents,
                    date=settlement.date,
                    method=settlement.method,
                    created_by_user_id=settlement.created_by_user_id,
                )
            )
            session.commit()

    def find_settlement(self, group_id: str, settlement_id: str) -> Settlement | None:
        with SessionLocal() as session:
            row = session.execute(
                select(SettlementRow).where(SettlementRow.group_id == group_id, SettlementRow.id == settlement_id)
            ).scalar_one_or_none()
            return _settlement_row_to_pydantic(row) if row else None

    def replace_settlement(self, group_id: str, settlement_id: str, updated: Settlement) -> None:
        with SessionLocal() as session:
            row = session.execute(
                select(SettlementRow).where(SettlementRow.group_id == group_id, SettlementRow.id == settlement_id)
            ).scalar_one_or_none()
            if row is None:
                return
            row.from_member_id = updated.from_member_id
            row.to_member_id = updated.to_member_id
            row.amount_cents = updated.amount_cents
            row.date = updated.date
            row.method = updated.method
            session.commit()

    def delete_settlement(self, group_id: str, settlement_id: str) -> None:
        with SessionLocal() as session:
            row = session.execute(
                select(SettlementRow).where(SettlementRow.group_id == group_id, SettlementRow.id == settlement_id)
            ).scalar_one_or_none()
            if row is not None:
                session.delete(row)
                session.commit()

    # ---- CSV import ----

    def remembered_merchants(self, user_id: str, group_id: str) -> set[str]:
        with SessionLocal() as session:
            rows = (
                session.execute(
                    select(RememberedMerchantRow.merchant).where(
                        RememberedMerchantRow.user_id == user_id,
                        RememberedMerchantRow.group_id == group_id,
                    )
                )
                .scalars()
                .all()
            )
            return set(rows)

    def remember_merchants(self, user_id: str, group_id: str, merchants: set[str]) -> None:
        """Adds any that aren't already there; re-remembering is a no-op."""
        existing = self.remembered_merchants(user_id, group_id)
        new = merchants - existing
        if not new:
            return
        with SessionLocal() as session:
            for merchant in sorted(new):
                session.add(RememberedMerchantRow(user_id=user_id, group_id=group_id, merchant=merchant))
            session.commit()

    def get_import_mapping(self, user_id: str, group_id: str) -> ColumnMapping | None:
        """The mapping this user last used for this group, if any."""
        with SessionLocal() as session:
            row = session.execute(
                select(ImportMappingRow).where(
                    ImportMappingRow.user_id == user_id, ImportMappingRow.group_id == group_id
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return ColumnMapping(
                date_column=row.date_column,
                description_column=row.description_column,
                amount_column=row.amount_column,
                date_format=row.date_format,  # type: ignore[arg-type]
                amount_sign=row.amount_sign,  # type: ignore[arg-type]
                category_column=row.category_column,
            )

    def save_import_mapping(self, user_id: str, group_id: str, mapping: ColumnMapping) -> None:
        with SessionLocal() as session:
            row = session.execute(
                select(ImportMappingRow).where(
                    ImportMappingRow.user_id == user_id, ImportMappingRow.group_id == group_id
                )
            ).scalar_one_or_none()
            if row is None:
                row = ImportMappingRow(user_id=user_id, group_id=group_id)
                session.add(row)
            row.date_column = mapping.date_column
            row.description_column = mapping.description_column
            row.amount_column = mapping.amount_column
            row.date_format = mapping.date_format
            row.amount_sign = mapping.amount_sign
            row.category_column = mapping.category_column
            session.commit()

    def known_fingerprints(self, group_id: str, uploader_user_id: str, candidates: list[str]) -> set[str]:
        if not candidates:
            return set()
        with SessionLocal() as session:
            rows = (
                session.execute(
                    select(ImportedTransactionRow.fingerprint).where(
                        ImportedTransactionRow.group_id == group_id,
                        ImportedTransactionRow.uploader_user_id == uploader_user_id,
                        ImportedTransactionRow.fingerprint.in_(candidates),
                    )
                )
                .scalars()
                .all()
            )
            return set(rows)

    def create_pending_import(
        self, group_id: str, uploader_user_id: str, items: list[PendingItem]
    ) -> str:
        import_id = new_id()
        with SessionLocal() as session:
            row = PendingImportRow(id=import_id, group_id=group_id, uploader_user_id=uploader_user_id)
            row.items = [
                PendingImportItemRow(
                    id=item.id,
                    import_id=import_id,
                    date=item.date,
                    description=item.description,
                    amount_cents=item.amount_cents,
                    fingerprint=item.fingerprint,
                    preselected=item.preselected,
                    category=item.category,
                    already_imported=item.already_imported,
                )
                for item in items
            ]
            session.add(row)
            session.commit()
        return import_id

    def get_pending_import(self, import_id: str, group_id: str, uploader_user_id: str) -> list[PendingItem] | None:
        """
        Scoped to (import, group, uploader) so one user can never confirm
        another's staged rows. None means "no such pending import for you".
        """
        with SessionLocal() as session:
            row = session.execute(
                select(PendingImportRow).where(
                    PendingImportRow.id == import_id,
                    PendingImportRow.group_id == group_id,
                    PendingImportRow.uploader_user_id == uploader_user_id,
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return [
                PendingItem(
                    id=item.id,
                    date=item.date,
                    description=item.description,
                    amount_cents=item.amount_cents,
                    fingerprint=item.fingerprint,
                    preselected=item.preselected,
                    category=item.category,
                    already_imported=item.already_imported,
                )
                for item in row.items
            ]

    def delete_pending_import(self, import_id: str) -> None:
        with SessionLocal() as session:
            row = session.execute(
                select(PendingImportRow).where(PendingImportRow.id == import_id)
            ).scalar_one_or_none()
            if row is not None:
                session.delete(row)
                session.commit()

    def record_imported_transactions(
        self, group_id: str, uploader_user_id: str, pairs: list[tuple[str, str]]
    ) -> None:
        """pairs: (fingerprint, expense_id) for each row just turned into an expense."""
        if not pairs:
            return
        # A fingerprint may already be recorded: the user can deliberately
        # re-import a flagged duplicate, and one file can hold two identical
        # real charges. The table marks "this has been seen", so the first
        # record stands and later ones are no-ops rather than a constraint
        # violation.
        known = self.known_fingerprints(group_id, uploader_user_id, [f for f, _ in pairs])
        with SessionLocal() as session:
            for fingerprint, expense_id in pairs:
                if fingerprint in known:
                    continue
                known.add(fingerprint)
                session.add(
                    ImportedTransactionRow(
                        fingerprint=fingerprint,
                        group_id=group_id,
                        uploader_user_id=uploader_user_id,
                        expense_id=expense_id,
                    )
                )
            session.commit()

    # ---- test/dev helper ----

    def reset(self) -> None:
        """Drops and recreates every table — used by tests for isolation between cases."""
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)


store = Store()


def seed(target: Store | None = None) -> None:
    """
    Populates demo data so the API has something to show out of the box.
    A no-op if it looks like this has already run — with a persistent
    (file/Postgres) database this is called on every server start, and
    re-inserting alice@example.com would otherwise crash on the unique
    email constraint.
    """
    from datetime import date

    from app.auth import hash_password
    from app.domain import resolve_splits
    from app.models import EqualSplitInput, SharesSplitInput

    s = target if target is not None else store

    if s.find_user_by_email("alice@example.com") is not None:
        return

    alice = s.create_user("alice@example.com", "Alice", hash_password("password123"))
    bob = s.create_user("bob@example.com", "Bob", hash_password("password123"))

    group = s.create_group("Cabin Trip", alice)
    group = s.add_linked_member(group.id, bob)
    group = s.add_placeholder_member(group.id, "Carol")

    alice_member = next(m for m in group.members if m.user_id == alice.id)
    bob_member = next(m for m in group.members if m.user_id == bob.id)
    carol_member = next(m for m in group.members if m.display_name == "Carol")

    groceries = Expense(
        id=new_id(),
        group_id=group.id,
        description="Groceries",
        amount_cents=6000,
        payer_id=alice_member.id,
        date=date(2026, 8, 20),
        split_method="equal",
        splits=resolve_splits(
            6000, EqualSplitInput(method="equal", member_ids=[alice_member.id, bob_member.id, carol_member.id])
        ),
        created_by_user_id=alice.id,
    )
    s.add_expense(groceries)

    cabin_rental = Expense(
        id=new_id(),
        group_id=group.id,
        description="Cabin rental",
        amount_cents=30000,
        payer_id=bob_member.id,
        date=date(2026, 8, 21),
        split_method="shares",
        splits=resolve_splits(
            30000,
            SharesSplitInput(
                method="shares",
                shares=[
                    {"memberId": alice_member.id, "shares": 1},
                    {"memberId": bob_member.id, "shares": 1},
                    {"memberId": carol_member.id, "shares": 1},
                ],
            ),
        ),
        created_by_user_id=bob.id,
    )
    s.add_expense(cabin_rental)

    settlement = Settlement(
        id=new_id(),
        group_id=group.id,
        from_member_id=carol_member.id,
        to_member_id=alice_member.id,
        amount_cents=2000,
        date=date(2026, 8, 22),
        method="Venmo",
        created_by_user_id=alice.id,
    )
    s.add_settlement(settlement)
