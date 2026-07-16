from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


from decimal import Decimal

class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    monthly_amount: Decimal = Field(default=Decimal("0.00"), ge=0)


class PortfolioUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    monthly_amount: Decimal | None = Field(default=None, ge=0)


class PortfolioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str
    monthly_amount: Decimal
    created_at: datetime
    updated_at: datetime
