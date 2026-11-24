from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from models import Asset, Portfolio, Strategy, Transaction
from schemas.strategy import StrategyItemCreate, StrategyReserveManageRequest, StrategySetRequest


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


def get_portfolio_reserves(
    db: Session, portfolio_id: UUID
) -> tuple[dict[UUID, Decimal], Decimal]:
    """Calcula las reservas actuales por activo y del fondo general cronológicamente."""
    txns = (
        db.scalars(
            select(Transaction)
            .where(Transaction.portfolio_id == portfolio_id)
            .order_by(Transaction.date.asc())
        )
        .all()
    )
    asset_reserves: dict[UUID, Decimal] = {}
    global_reserve = Decimal("0")

    for t in txns:
        amt = Decimal(str(t.amount or 0))
        aid = t.asset_id

        if t.type == "DEPOSIT":
            if aid:
                asset_reserves[aid] = asset_reserves.get(aid, Decimal("0")) + amt
            else:
                global_reserve += amt
        elif t.type == "WITHDRAW":
            if aid:
                curr = asset_reserves.get(aid, Decimal("0"))
                asset_reserves[aid] = max(Decimal("0"), curr - amt)
            else:
                global_reserve = max(Decimal("0"), global_reserve - amt)
        elif t.type == "BUY":
            if aid:
                curr = asset_reserves.get(aid, Decimal("0"))
                from_asset = min(curr, amt)
                asset_reserves[aid] = curr - from_asset
                rem = amt - from_asset
                if rem > Decimal("0") and global_reserve > Decimal("0"):
                    from_global = min(global_reserve, rem)
                    global_reserve -= from_global

    return asset_reserves, global_reserve


def reallocate_reserves(
    db: Session,
    user_id: UUID,
    portfolio_id: UUID,
    payload: StrategyReserveManageRequest,
) -> list[Transaction]:
    """
    Gestiona y reasigna reservas de efectivo:
    - TO_GLOBAL: mueve reserva de un activo al Fondo General
    - TO_ASSET: mueve reserva desde un activo (o Fondo General) a otro activo
    - CLEAR: libera o elimina la reserva remanente de un activo o del Fondo General
    """
    portfolio = _get_portfolio_for_user(db, user_id, portfolio_id)
    if portfolio is None:
        raise ValueError("Portfolio no encontrado o no pertenece al usuario.")

    asset_reserves, global_reserve = get_portfolio_reserves(db, portfolio_id)
    source_aid = payload.source_asset_id

    if source_aid is not None:
        source_asset = db.get(Asset, source_aid)
        if source_asset is None:
            raise ValueError("El activo de origen no existe.")
        source_name = source_asset.symbol
        available_source = asset_reserves.get(source_aid, Decimal("0"))
    else:
        source_name = "Fondo General"
        available_source = global_reserve

    now = datetime.now(timezone.utc)
    created: list[Transaction] = []
    action = payload.action.upper()

    if action == "CLEAR":
        amt_to_clear = (
            payload.amount
            if payload.amount is not None and payload.amount > Decimal("0")
            else available_source
        )
        amt_to_clear = amt_to_clear.quantize(Decimal("0.01"))
        if amt_to_clear <= Decimal("0"):
            raise ValueError(f"No hay reserva disponible para liberar en {source_name}.")
        if amt_to_clear > available_source:
            raise ValueError(
                f"El monto a liberar (${amt_to_clear}) supera la reserva disponible (${available_source})."
            )

        txn = Transaction(
            portfolio_id=portfolio_id,
            asset_id=source_aid,
            type="WITHDRAW",
            amount=amt_to_clear,
            date=now,
            notes=f"Reserva liberada / eliminada de {source_name}",
        )
        db.add(txn)
        created.append(txn)

    elif action == "TO_GLOBAL":
        if source_aid is None:
            raise ValueError("El origen ya es el Fondo General.")
        if payload.amount is None or payload.amount <= Decimal("0"):
            raise ValueError("Debes especificar un monto válido mayor a 0.")
        amt = payload.amount.quantize(Decimal("0.01"))
        if amt > available_source:
            raise ValueError(
                f"El monto (${amt}) supera la reserva disponible en {source_name} (${available_source})."
            )

        txn_withdraw = Transaction(
            portfolio_id=portfolio_id,
            asset_id=source_aid,
            type="WITHDRAW",
            amount=amt,
            date=now,
            notes=f"Reasignado a Fondo General desde {source_name}",
        )
        txn_deposit = Transaction(
            portfolio_id=portfolio_id,
            asset_id=None,
            type="DEPOSIT",
            amount=amt,
            date=now,
            notes=f"Transferido desde reserva de {source_name}",
        )
        db.add(txn_withdraw)
        db.add(txn_deposit)
        created.extend([txn_withdraw, txn_deposit])

    elif action == "TO_ASSET":
        if payload.target_asset_id is None:
            raise ValueError("Debes especificar el activo de destino.")
        target_asset = db.get(Asset, payload.target_asset_id)
        if target_asset is None:
            raise ValueError("El activo de destino no existe.")
        if source_aid == payload.target_asset_id:
            raise ValueError("El activo de origen y destino no pueden ser el mismo.")
        if payload.amount is None or payload.amount <= Decimal("0"):
            raise ValueError("Debes especificar un monto válido mayor a 0.")
        amt = payload.amount.quantize(Decimal("0.01"))
        if amt > available_source:
            raise ValueError(
                f"El monto (${amt}) supera la reserva disponible en {source_name} (${available_source})."
            )

        txn_withdraw = Transaction(
            portfolio_id=portfolio_id,
            asset_id=source_aid,
            type="WITHDRAW",
            amount=amt,
            date=now,
            notes=f"Reasignado a {target_asset.symbol} desde {source_name}",
        )
        txn_deposit = Transaction(
            portfolio_id=portfolio_id,
            asset_id=payload.target_asset_id,
            type="DEPOSIT",
            amount=amt,
            date=now,
            notes=f"Transferido desde {source_name}",
        )
        db.add(txn_withdraw)
        db.add(txn_deposit)
        created.extend([txn_withdraw, txn_deposit])

    else:
        raise ValueError(
            f"Acción no reconocida: '{action}'. Opciones válidas: TO_GLOBAL, TO_ASSET, CLEAR."
        )

    db.commit()
    for t in created:
        db.refresh(t)
    return created

