from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TransactionType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    DIVIDEND = "DIVIDEND"
    DEPOSIT = "DEPOSIT"
    WITHDRAW = "WITHDRAW"


class TransactionCreate(BaseModel):
    type: TransactionType
    date: datetime
    amount: Decimal = Field(description="Monto total en moneda base (siempre requerido)")
    asset_id: UUID | None = None
    quantity: Decimal | None = Field(default=None, gt=0)
    price: Decimal | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_by_type(self) -> "TransactionCreate":
        t = self.type

        if t in (TransactionType.BUY, TransactionType.SELL):
            missing = []
            if self.asset_id is None:
                missing.append("asset_id")
            if self.quantity is None:
                missing.append("quantity")
            if self.price is None:
                missing.append("price")
            if missing:
                raise ValueError(
                    f"Los campos {missing} son requeridos para el tipo {t}."
                )

        if t == TransactionType.DIVIDEND:
            if self.asset_id is None:
                raise ValueError("DIVIDEND requiere asset_id (el activo que generó el dividendo).")

        # DEPOSIT / WITHDRAW: solo amount es requerido (ya validado por Field)
        return self


class TransactionUpdate(BaseModel):
    """Permite actualizar campos individuales de una transacción."""
    date: datetime | None = None
    amount: Decimal | None = None
    quantity: Decimal | None = Field(default=None, gt=0)
    price: Decimal | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=500)


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    portfolio_id: UUID
    type: str
    date: datetime
    amount: Decimal
    asset_id: UUID | None
    quantity: Decimal | None
    price: Decimal | None
    notes: str | None
    created_at: datetime
    asset_symbol: str | None = None
    asset_name: str | None = None

    @classmethod
    def from_orm_with_asset(cls, txn: object) -> "TransactionRead":
        from models.entities import Transaction  # evitar import circular

        t: Transaction = txn  # type: ignore[assignment]
        return cls(
            id=t.id,
            portfolio_id=t.portfolio_id,
            type=t.type,
            date=t.date,
            amount=t.amount,
            asset_id=t.asset_id,
            quantity=t.quantity,
            price=t.price,
            notes=t.notes,
            created_at=t.created_at,
            asset_symbol=t.asset.symbol if t.asset else None,
            asset_name=t.asset.name if t.asset else None,
        )
