from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import AuthenticatedUser, get_current_user
from schemas import PortfolioCreate, PortfolioRead, PortfolioUpdate
from services.portfolio_service import (
    create_portfolio,
    delete_portfolio,
    get_portfolio_or_none,
    list_portfolios,
    update_portfolio,
)

router = APIRouter(prefix="/api/portfolios", tags=["portfolios"])


def _map_portfolio_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    if detail == "Authenticated user email is missing.":
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


@router.get("", response_model=list[PortfolioRead])
async def get_portfolios(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[PortfolioRead]:
    try:
        portfolios = list_portfolios(db, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return [PortfolioRead.model_validate(portfolio) for portfolio in portfolios]


@router.post("", response_model=PortfolioRead, status_code=status.HTTP_201_CREATED)
async def create_portfolio_endpoint(
    payload: PortfolioCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> PortfolioRead:
    try:
        portfolio = create_portfolio(db, current_user, payload)
    except ValueError as exc:
        raise _map_portfolio_error(exc) from exc

    return PortfolioRead.model_validate(portfolio)


@router.get("/{portfolio_id}", response_model=PortfolioRead)
async def get_portfolio(
    portfolio_id: UUID,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> PortfolioRead:
    portfolio = get_portfolio_or_none(db, current_user, portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found.")

    return PortfolioRead.model_validate(portfolio)


@router.patch("/{portfolio_id}", response_model=PortfolioRead)
async def update_portfolio_endpoint(
    portfolio_id: UUID,
    payload: PortfolioUpdate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> PortfolioRead:
    portfolio = get_portfolio_or_none(db, current_user, portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found.")

    try:
        updated = update_portfolio(db, portfolio, payload)
    except ValueError as exc:
        raise _map_portfolio_error(exc) from exc

    return PortfolioRead.model_validate(updated)


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_portfolio_endpoint(
    portfolio_id: UUID,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> None:
    portfolio = get_portfolio_or_none(db, current_user, portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found.")

    delete_portfolio(db, portfolio)
