from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrategyItemCreate(BaseModel):
    asset_id: UUID
    percentage: Decimal = Field(gt=0, le=100, decimal_places=2)
    target_amount: Decimal | None = Field(default=None, ge=0)


class StrategySetRequest(BaseModel):
    """
    Reemplaza la estrategia completa de un portfolio.
    La suma de porcentajes puede ser <= 100 (construcción gradual).
    """

    items: list[StrategyItemCreate] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_no_duplicates(self) -> "StrategySetRequest":
        seen: set[UUID] = set()
        for item in self.items:
            if item.asset_id in seen:
                raise ValueError(f"Asset '{item.asset_id}' aparece más de una vez en la estrategia.")
            seen.add(item.asset_id)
        return self

    @model_validator(mode="after")
    def validate_total_percentage(self) -> "StrategySetRequest":
        total = sum(item.percentage for item in self.items)
        if total > Decimal("100"):
            raise ValueError(
                f"La suma de porcentajes ({total}%) supera el 100%. Revisá los valores."
            )
        return self


class StrategyDepositRequest(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0)


class StrategyItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    portfolio_id: UUID
    asset_id: UUID
    percentage: Decimal
    target_amount: Decimal | None = None
    asset_symbol: str | None = None
    asset_name: str | None = None

    @classmethod
    def from_orm_with_asset(cls, strategy: object) -> "StrategyItemRead":
        """Construye el read incluyendo symbol/name del asset relacionado."""
        from models.entities import Strategy  # evitar import circular

        s: Strategy = strategy  # type: ignore[assignment]
        return cls(
            id=s.id,
            portfolio_id=s.portfolio_id,
            asset_id=s.asset_id,
            percentage=s.percentage,
            target_amount=s.target_amount,
            asset_symbol=s.asset.symbol if s.asset else None,
            asset_name=s.asset.name if s.asset else None,
        )
