from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import Asset
from schemas.asset import AssetCreate, AssetUpdate


def list_assets(db: Session, query: str | None = None) -> list[Asset]:
    """Return all assets, optionally filtered by symbol or name."""
    statement = select(Asset).order_by(Asset.symbol)

    if query:
        q = f"%{query.strip()}%"
        statement = statement.where(
            or_(
                Asset.symbol.ilike(q),
                Asset.name.ilike(q),
            )
        )

    return list(db.scalars(statement).all())


def get_asset_by_id(db: Session, asset_id: object) -> Asset | None:
    return db.get(Asset, asset_id)


def get_asset_by_symbol(db: Session, symbol: str) -> Asset | None:
    statement = select(Asset).where(Asset.symbol == symbol.strip().upper())
    return db.scalars(statement).one_or_none()


def create_asset(db: Session, payload: AssetCreate) -> Asset:
    asset = Asset(
        symbol=payload.symbol,
        name=payload.name,
    )
    db.add(asset)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError(f"Asset with symbol '{payload.symbol}' already exists.") from exc

    db.refresh(asset)
    return asset


def upsert_asset(db: Session, symbol: str, name: str) -> Asset:
    existing = get_asset_by_symbol(db, symbol)
    if existing:
        return existing

    return create_asset(db, AssetCreate(symbol=symbol, name=name))


def update_asset(db: Session, asset: Asset, payload: AssetUpdate) -> Asset:
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        return asset

    for field, value in changes.items():
        setattr(asset, field, value)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError(
            f"Asset with symbol '{changes.get('symbol', asset.symbol)}' already exists."
        ) from exc

    db.refresh(asset)
    return asset


def delete_asset(db: Session, asset: Asset) -> None:
    db.delete(asset)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError(
            "No se puede eliminar el activo porque esta vinculado a movimientos o estrategias."
        ) from exc
