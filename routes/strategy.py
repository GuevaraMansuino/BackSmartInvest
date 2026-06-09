from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import AuthenticatedUser, get_current_user
from schemas.strategy import StrategyItemRead, StrategySetRequest
from services.strategy_service import (
    delete_strategy_item,
    get_strategy,
    set_strategy,
)

router = APIRouter(prefix="/api/portfolios/{portfolio_id}/strategy", tags=["strategy"])


@router.get("", response_model=list[StrategyItemRead])
async def get_portfolio_strategy(
    portfolio_id: UUID,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[StrategyItemRead]:
    """Devuelve la estrategia objetivo del portfolio."""
    try:
        items = get_strategy(db, current_user.user_id, portfolio_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return [StrategyItemRead.from_orm_with_asset(item) for item in items]


@router.put("", response_model=list[StrategyItemRead], status_code=status.HTTP_200_OK)
async def set_portfolio_strategy(
    portfolio_id: UUID,
    payload: StrategySetRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[StrategyItemRead]:
    """
    Reemplaza la estrategia completa del portfolio.
    La suma de porcentajes puede ser <= 100 (construcción gradual permitida).
    """
    try:
        items = set_strategy(db, current_user.user_id, portfolio_id, payload)
    except ValueError as exc:
        detail = str(exc)
        if "no encontrado" in detail:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail) from exc
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail) from exc

    return [StrategyItemRead.from_orm_with_asset(item) for item in items]


@router.delete(
    "/{strategy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_strategy_item_endpoint(
    portfolio_id: UUID,
    strategy_id: UUID,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> None:
    """Elimina un ítem específico de la estrategia."""
    try:
        delete_strategy_item(db, current_user.user_id, portfolio_id, strategy_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
