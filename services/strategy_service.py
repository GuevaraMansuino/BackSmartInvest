from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from models import Asset, Portfolio, Strategy, Transaction
from schemas.strategy import StrategyItemCreate, StrategySetRequest


def _get_portfolio_for_user(
    db: Session, user_id: UUID, portfolio_id: UUID
) -> Portfolio | None:
    statement = select(Portfolio).where(
        Portfolio.id == portfolio_id,
        Portfolio.user_id == user_id,
    )
    return db.scalars(statement).one_or_none()


def get_strategy(
    db: Session, user_id: UUID, portfolio_id: UUID
) -> list[Strategy]:
    """Devuelve la estrategia del portfolio con el asset eager-loaded."""
    portfolio = _get_portfolio_for_user(db, user_id, portfolio_id)
    if portfolio is None:
        raise ValueError("Portfolio no encontrado o no pertenece al usuario.")

    statement = (
        select(Strategy)
        .where(Strategy.portfolio_id == portfolio_id)
        .options(joinedload(Strategy.asset))
        .order_by(Strategy.percentage.desc())
    )
    return list(db.scalars(statement).all())


def set_strategy(
    db: Session,
    user_id: UUID,
    portfolio_id: UUID,
    payload: StrategySetRequest,
) -> list[Strategy]:
    """
    Reemplaza completamente la estrategia del portfolio.
    Valida que el portfolio pertenezca al usuario y que cada asset_id exista.
    """
    portfolio = _get_portfolio_for_user(db, user_id, portfolio_id)
    if portfolio is None:
        raise ValueError("Portfolio no encontrado o no pertenece al usuario.")

    _validate_assets_exist(db, [item.asset_id for item in payload.items])

    # Eliminar estrategia existente e impactar en DB antes de insertar nuevos para no violar unique constraint
    existing = (
        db.scalars(select(Strategy).where(Strategy.portfolio_id == portfolio_id))
        .all()
    )
    for row in existing:
        db.delete(row)
    db.flush()

    # Insertar nueva estrategia (desduplicando por asset_id si vinieran repetidos)
    seen_assets = set()
    new_items: list[Strategy] = []
    for item in payload.items:
        if item.asset_id in seen_assets:
            continue
        seen_assets.add(item.asset_id)
        strategy = Strategy(
            portfolio_id=portfolio_id,
            asset_id=item.asset_id,
            percentage=item.percentage,
            target_amount=item.target_amount,
        )
        db.add(strategy)
        new_items.append(strategy)

    db.commit()

    # Reload con assets
    return get_strategy(db, user_id, portfolio_id)


def delete_strategy_item(
    db: Session, user_id: UUID, portfolio_id: UUID, strategy_id: UUID
) -> None:
    """Elimina un ítem de la estrategia del portfolio."""
    portfolio = _get_portfolio_for_user(db, user_id, portfolio_id)
    if portfolio is None:
        raise ValueError("Portfolio no encontrado o no pertenece al usuario.")

    statement = select(Strategy).where(
        Strategy.id == strategy_id,
        Strategy.portfolio_id == portfolio_id,
    )
    item = db.scalars(statement).one_or_none()
    if item is None:
        raise LookupError("Ítem de estrategia no encontrado.")

    db.delete(item)
    db.commit()


def _validate_assets_exist(db: Session, asset_ids: list[UUID]) -> None:
    """Lanza ValueError si alguno de los asset_id no existe en la tabla assets."""
    if not asset_ids:
        return

    found = set(
        db.scalars(select(Asset.id).where(Asset.id.in_(asset_ids))).all()
    )
    missing = [str(aid) for aid in asset_ids if aid not in found]
    if missing:
        raise ValueError(
            f"Los siguientes asset_id no existen: {', '.join(missing)}"
        )


def deposit_strategy_budget(
    db: Session,
    user_id: UUID,
    portfolio_id: UUID,
    amount: Decimal | None = None,
) -> list[Transaction]:
    """
    Deposita el presupuesto en la estrategia del portfolio.
    Si amount no se especifica, usa portfolio.monthly_amount.
    Divide el monto a depositar entre los activos de la estrategia según sus porcentajes
    creando transacciones DEPOSIT para cada activo.
    """
    portfolio = _get_portfolio_for_user(db, user_id, portfolio_id)
    if portfolio is None:
        raise ValueError("Portfolio no encontrado o no pertenece al usuario.")

    strategies = get_strategy(db, user_id, portfolio_id)
    if not strategies:
        raise ValueError("El portfolio no tiene una estrategia configurada.")

    deposit_total = amount if amount is not None and amount > 0 else portfolio.monthly_amount
    if deposit_total is None or deposit_total <= 0:
        raise ValueError("No hay un monto mensual configurado ni se especificó un monto válido para depositar.")

    now = datetime.now(timezone.utc)
    created_txns: list[Transaction] = []

    for strat in strategies:
        asset_deposit = (deposit_total * strat.percentage / Decimal("100")).quantize(Decimal("0.01"))
        if asset_deposit > 0:
            txn = Transaction(
                portfolio_id=portfolio_id,
                asset_id=strat.asset_id,
                type="DEPOSIT",
                amount=asset_deposit,
                quantity=None,
                price=None,
                date=now,
                notes=f"Depósito Estrategia ({strat.percentage}%)",
            )
            db.add(txn)
            created_txns.append(txn)

    db.commit()
    for txn in created_txns:
        db.refresh(txn)

    return created_txns
