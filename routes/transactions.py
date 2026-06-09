from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import AuthenticatedUser, get_current_user
from schemas.transaction import TransactionCreate, TransactionRead, TransactionUpdate
from services.transaction_service import (
    create_transaction,
    delete_transaction,
    list_transactions,
    update_transaction,
)

router = APIRouter(
    prefix="/api/portfolios/{portfolio_id}/transactions",
    tags=["transactions"],
)


@router.get("", response_model=list[TransactionRead])
async def get_transactions(
    portfolio_id: UUID,
    type: str | None = Query(
        default=None,
        description="Filtrar por tipo: BUY, SELL, DIVIDEND, DEPOSIT, WITHDRAW",
    ),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[TransactionRead]:
    """Historial de transacciones ordenado por fecha desc, con filtro opcional por tipo."""
    try:
        txns = list_transactions(db, current_user.user_id, portfolio_id, transaction_type=type)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return [TransactionRead.from_orm_with_asset(t) for t in txns]


@router.post("", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
async def create_transaction_endpoint(
    portfolio_id: UUID,
    payload: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> TransactionRead:
    """
    Crea una transacción. Semántica por tipo:
    - **BUY/SELL**: requieren asset_id, quantity, price
    - **DIVIDEND**: requiere asset_id, solo amount
    - **DEPOSIT/WITHDRAW**: solo amount (sin asset requerido)
    """
    try:
        txn = create_transaction(db, current_user.user_id, portfolio_id, payload)
    except ValueError as exc:
        detail = str(exc)
        if "no encontrado" in detail:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail) from exc
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail) from exc

    return TransactionRead.from_orm_with_asset(txn)


@router.patch("/{transaction_id}", response_model=TransactionRead)
async def update_transaction_endpoint(
    portfolio_id: UUID,
    transaction_id: UUID,
    payload: TransactionUpdate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> TransactionRead:
    """Actualiza campos editables de una transacción (fecha, monto, precio, notas)."""
    try:
        txn = update_transaction(db, current_user.user_id, portfolio_id, transaction_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return TransactionRead.from_orm_with_asset(txn)


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction_endpoint(
    portfolio_id: UUID,
    transaction_id: UUID,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> None:
    """Elimina una transacción."""
    try:
        delete_transaction(db, current_user.user_id, portfolio_id, transaction_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
