from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from models import Asset, Portfolio, Transaction
from schemas.transaction import TransactionCreate, TransactionUpdate


def _get_portfolio_for_user(
    db: Session, user_id: UUID, portfolio_id: UUID
) -> Portfolio | None:
    statement = select(Portfolio).where(
        Portfolio.id == portfolio_id,
        Portfolio.user_id == user_id,
    )
    return db.scalars(statement).one_or_none()


def _validate_asset_exists(db: Session, asset_id: UUID) -> None:
    if db.get(Asset, asset_id) is None:
        raise ValueError(f"El asset '{asset_id}' no existe.")


def list_transactions(
    db: Session,
    user_id: UUID,
    portfolio_id: UUID,
    transaction_type: str | None = None,
) -> list[Transaction]:
    portfolio = _get_portfolio_for_user(db, user_id, portfolio_id)
    if portfolio is None:
        raise ValueError("Portfolio no encontrado o no pertenece al usuario.")

    statement = (
        select(Transaction)
        .where(Transaction.portfolio_id == portfolio_id)
        .options(joinedload(Transaction.asset))
        .order_by(Transaction.date.desc())
    )
    if transaction_type:
        statement = statement.where(Transaction.type == transaction_type.upper())

    return list(db.scalars(statement).all())


def create_transaction(
    db: Session,
    user_id: UUID,
    portfolio_id: UUID,
    payload: TransactionCreate,
) -> Transaction:
    portfolio = _get_portfolio_for_user(db, user_id, portfolio_id)
    if portfolio is None:
        raise ValueError("Portfolio no encontrado o no pertenece al usuario.")

    if payload.asset_id is not None:
        _validate_asset_exists(db, payload.asset_id)

    txn = Transaction(
        portfolio_id=portfolio_id,
        asset_id=payload.asset_id,
        type=payload.type.value,
        date=payload.date,
        amount=payload.amount,
        quantity=payload.quantity,
        price=payload.price,
        notes=payload.notes,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)

    # Reload con asset eager
    return _load_with_asset(db, txn.id)


def update_transaction(
    db: Session,
    user_id: UUID,
    portfolio_id: UUID,
    transaction_id: UUID,
    payload: TransactionUpdate,
) -> Transaction:
    txn = _get_transaction_for_user(db, user_id, portfolio_id, transaction_id)
    if txn is None:
        raise LookupError("Transacción no encontrada.")

    if payload.date is not None:
        txn.date = payload.date
    if payload.amount is not None:
        txn.amount = payload.amount
    if payload.quantity is not None:
        txn.quantity = payload.quantity
    if payload.price is not None:
        txn.price = payload.price
    if payload.notes is not None:
        txn.notes = payload.notes

    db.commit()
    return _load_with_asset(db, txn.id)


def delete_transaction(
    db: Session,
    user_id: UUID,
    portfolio_id: UUID,
    transaction_id: UUID,
) -> None:
    txn = _get_transaction_for_user(db, user_id, portfolio_id, transaction_id)
    if txn is None:
        raise LookupError("Transacción no encontrada.")

    db.delete(txn)
    db.commit()


def _get_transaction_for_user(
    db: Session, user_id: UUID, portfolio_id: UUID, transaction_id: UUID
) -> Transaction | None:
    portfolio = _get_portfolio_for_user(db, user_id, portfolio_id)
    if portfolio is None:
        return None

    statement = select(Transaction).where(
        Transaction.id == transaction_id,
        Transaction.portfolio_id == portfolio_id,
    )
    return db.scalars(statement).one_or_none()


def _load_with_asset(db: Session, transaction_id: UUID) -> Transaction:
    statement = (
        select(Transaction)
        .where(Transaction.id == transaction_id)
        .options(joinedload(Transaction.asset))
    )
    return db.scalars(statement).one()
