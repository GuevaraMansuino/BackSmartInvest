from dataclasses import asdict
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from database import get_db
from dependencies import AuthenticatedUser, get_current_user
from services.rebalance_service import RebalanceResult, get_rebalance

router = APIRouter(prefix="/api/portfolios", tags=["rebalance"])


class AssetSuggestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_id: UUID
    asset_symbol: str
    asset_name: str
    target_percentage: Decimal
    current_value: Decimal
    target_value: Decimal
    difference: Decimal
    action: str  # "BUY" | "SELL" | "OK"


class RebalanceResponse(BaseModel):
    portfolio_id: UUID
    total_value: Decimal
    is_complete_strategy: bool
    suggestions: list[AssetSuggestionResponse]


@router.get("/{portfolio_id}/rebalance", response_model=RebalanceResponse)
async def get_portfolio_rebalance(
    portfolio_id: UUID,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> RebalanceResponse:
    """
    Calcula el rebalanceo sugerido para el portfolio.
    
    - **total_value**: valor total actual del portfolio (en moneda base)
    - **is_complete_strategy**: True si la estrategia suma exactamente 100%
    - **suggestions**: lista ordenada (BUY primero, luego SELL, luego OK)
      - **action**: `BUY` si hay que comprar, `SELL` si hay que vender, `OK` si está en balance
      - **difference**: positivo = falta comprar, negativo = hay que vender
    
    > Nota: el precio de cada activo se toma de la última transacción BUY/SELL del portfolio.
    """
    try:
        result: RebalanceResult = get_rebalance(db, current_user.user_id, portfolio_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return RebalanceResponse(
        portfolio_id=result.portfolio_id,
        total_value=result.total_value,
        is_complete_strategy=result.is_complete_strategy,
        suggestions=[
            AssetSuggestionResponse(**asdict(s)) for s in result.suggestions
        ],
    )
