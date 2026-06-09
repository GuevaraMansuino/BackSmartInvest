from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from models import Asset, Portfolio, Strategy
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

    # Eliminar estrategia existente
    existing = (
        db.scalars(select(Strategy).where(Strategy.portfolio_id == portfolio_id))
        .all()
    )
    for row in existing:
        db.delete(row)

    # Insertar nueva estrategia
    new_items: list[Strategy] = []
    for item in payload.items:
        strategy = Strategy(
            portfolio_id=portfolio_id,
            asset_id=item.asset_id,
            percentage=item.percentage,
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
