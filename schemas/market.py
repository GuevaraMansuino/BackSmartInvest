from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class FeaturedAsset(BaseModel):
    symbol: str
    quote_symbol: str | None = None
    name: str
    price: Decimal
    currency: str | None = None
    instrument_type: str | None = None
    change_percent: Optional[Decimal] = None
    change_value: Optional[Decimal] = None
