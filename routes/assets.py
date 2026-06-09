from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import AuthenticatedUser, get_current_user
from schemas.asset import AssetCreate, AssetRead, AssetUpdate
from services.asset_service import (
    create_asset,
    delete_asset,
    get_asset_by_id,
    get_asset_by_symbol,
    list_assets,
    update_asset,
)

router = APIRouter(prefix="/api/assets", tags=["assets"])


@router.get("", response_model=list[AssetRead])
async def get_assets(
    q: str | None = Query(default=None, description="Filtrar por simbolo o nombre"),
    _: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AssetRead]:
    assets = list_assets(db, query=q)
    return [AssetRead.model_validate(asset) for asset in assets]


@router.post("", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
async def create_asset_endpoint(
    payload: AssetCreate,
    _: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssetRead:
    try:
        asset = create_asset(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return AssetRead.model_validate(asset)


@router.get("/symbol/{symbol}", response_model=AssetRead)
async def get_asset_by_symbol_endpoint(
    symbol: str,
    _: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssetRead:
    asset = get_asset_by_symbol(db, symbol)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activo no encontrado")

    return AssetRead.model_validate(asset)


@router.get("/{asset_id}", response_model=AssetRead)
async def get_asset(
    asset_id: UUID,
    _: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssetRead:
    asset = get_asset_by_id(db, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activo no encontrado")

    return AssetRead.model_validate(asset)


@router.patch("/{asset_id}", response_model=AssetRead)
async def update_asset_endpoint(
    asset_id: UUID,
    payload: AssetUpdate,
    _: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AssetRead:
    asset = get_asset_by_id(db, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activo no encontrado")

    try:
        updated = update_asset(db, asset, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return AssetRead.model_validate(updated)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset_endpoint(
    asset_id: UUID,
    _: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    asset = get_asset_by_id(db, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activo no encontrado")

    try:
        delete_asset(db, asset)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{symbol}/price")
async def get_asset_price(
    symbol: str,
    _: AuthenticatedUser = Depends(get_current_user),
):
    from services.market_data_service import market_data_service

    price = market_data_service.get_price(symbol)
    if price is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se pudo encontrar el precio para {symbol}",
        )
    return {"symbol": symbol, "price": price}
