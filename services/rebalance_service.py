from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from models import Portfolio, Strategy, Transaction
from services.market_data_service import market_data_service
from services.rebalance_logic import calculate_rebalance_difference


@dataclass(slots=True)
class AssetRebalanceSuggestion:
    asset_id: UUID
    asset_symbol: str
    asset_name: str
    target_percentage: Decimal
    current_value: Decimal
    target_value: Decimal
    difference: Decimal          # positivo = comprar, negativo = vender
    action: str                  # "BUY" | "SELL" | "OK"


@dataclass(slots=True)
class RebalanceResult:
    portfolio_id: UUID
    total_value: Decimal
    is_complete_strategy: bool   # True si la estrategia suma exactamente 100%
    suggestions: list[AssetRebalanceSuggestion]


_OK_THRESHOLD = Decimal("0.01")  # diferencia menor a $0.01 se considera OK


def get_rebalance(
    db: Session,
    user_id: UUID,
    portfolio_id: UUID,
) -> RebalanceResult:
    """
    Calcula el rebalanceo del portfolio para el usuario dado.
    
    Precio actual de cada activo = último transaction.price para ese asset en el portfolio.
    Valor actual = cantidad acumulada (BUY - SELL) * precio más reciente.
    """
    # Verificar ownership
    portfolio = db.scalars(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == user_id,
        )
    ).one_or_none()
    if portfolio is None:
        raise ValueError("Portfolio no encontrado o no pertenece al usuario.")

    # Obtener estrategia con assets
    strategies: list[Strategy] = list(
        db.scalars(
            select(Strategy)
            .where(Strategy.portfolio_id == portfolio_id)
            .options(joinedload(Strategy.asset))
        ).all()
    )
    if not strategies:
        raise ValueError("El portfolio no tiene estrategia definida.")

    # Obtener mapeo de asset_id -> symbol para consulta de market data
    asset_symbols = {s.asset_id: s.asset.symbol for s in strategies if s.asset}

    # Calcular valor actual por activo desde transacciones e incluir precios de mercado
    asset_values = _calculate_asset_values(db, portfolio_id, asset_symbols)

    # Calcular valor total del portfolio (todos los activos presentes)
    total_value = sum(asset_values.values(), Decimal("0"))

    total_strategy_percentage = sum(s.percentage for s in strategies)
    is_complete = total_strategy_percentage == Decimal("100")

    suggestions: list[AssetRebalanceSuggestion] = []
    for strat in strategies:
        asset_id = strat.asset_id
        current_val = asset_values.get(asset_id, Decimal("0"))
        difference = calculate_rebalance_difference(
            total_value, strat.percentage, current_val
        )

        if difference > _OK_THRESHOLD:
            action = "BUY"
        elif difference < -_OK_THRESHOLD:
            action = "SELL"
        else:
            action = "OK"

        target_val = total_value * strat.percentage / Decimal("100")

        suggestions.append(
            AssetRebalanceSuggestion(
                asset_id=asset_id,
                asset_symbol=strat.asset.symbol if strat.asset else "?",
                asset_name=strat.asset.name if strat.asset else "?",
                target_percentage=strat.percentage,
                current_value=current_val,
                target_value=target_val,
                difference=difference,
                action=action,
            )
        )

    # Ordenar: primero BUY, luego SELL, luego OK
    action_order = {"BUY": 0, "SELL": 1, "OK": 2}
    suggestions.sort(key=lambda s: action_order[s.action])

    return RebalanceResult(
        portfolio_id=portfolio_id,
        total_value=total_value,
        is_complete_strategy=is_complete,
        suggestions=suggestions,
    )


def _calculate_asset_values(
    db: Session, 
    portfolio_id: UUID, 
    asset_symbols: dict[UUID, str] = None
) -> dict[UUID, Decimal]:
    """
    Calcula el valor actual de cada activo en el portfolio.
    
    1. Calcula cantidades acumuladas (BUY - SELL).
    2. Obtiene precios: prioridad Mercado (Yahoo) -> última Transacción.
    """
    asset_symbols = asset_symbols or {}
    txns: list[Transaction] = list(
        db.scalars(
            select(Transaction)
            .where(
                Transaction.portfolio_id == portfolio_id,
                Transaction.asset_id.is_not(None),
                Transaction.type.in_(["BUY", "SELL"]),
            )
            .order_by(Transaction.date.asc())
        ).all()
    )

    quantities: dict[UUID, Decimal] = {}
    last_prices: dict[UUID, Decimal] = {}

    for txn in txns:
        asset_id: UUID = txn.asset_id  # type: ignore[assignment]
        qty = txn.quantity or Decimal("0")
        price = txn.price or Decimal("0")

        if txn.type == "BUY":
            quantities[asset_id] = quantities.get(asset_id, Decimal("0")) + qty
        elif txn.type == "SELL":
            quantities[asset_id] = quantities.get(asset_id, Decimal("0")) - qty

        if price > 0:
            last_prices[asset_id] = price

    result = {}
    for asset_id, qty in quantities.items():
        if qty <= 0:
            continue
            
        # Intentar precio de mercado
        symbol = asset_symbols.get(asset_id)
        market_price = None
        if symbol:
            market_price = market_data_service.get_price(symbol)
        
        # Fallback al último precio de transacción
        final_price = market_price if market_price is not None else last_prices.get(asset_id, Decimal("0"))
        
        result[asset_id] = qty * final_price

    return result
