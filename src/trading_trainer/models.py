from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"


@dataclass(frozen=True)
class Bar:
    symbol: str
    day: date
    open: float
    high: float
    low: float
    close: float
    volume: int = 0


@dataclass(frozen=True)
class Order:
    symbol: str
    side: Side
    quantity: int
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    reason: str = ""
    product: str = "stocks"
    multiplier: int = 1

    @property
    def position_key(self) -> str:
        """Keep positions for different product types with the same symbol separate."""
        return f"{self.product}:{self.symbol}"

    def notional_at(self, price: float) -> float:
        return self.quantity * price * self.multiplier


@dataclass(frozen=True)
class Fill:
    order: Order
    price: float
    quantity: int
    timestamp: datetime
    commission: float = 0.0

    @property
    def notional(self) -> float:
        return self.price * self.quantity * self.order.multiplier


@dataclass
class Position:
    symbol: str
    quantity: int = 0
    average_entry_price: float = 0.0
    multiplier: int = 1

    def market_value(self, price: float) -> float:
        return self.quantity * price * self.multiplier


@dataclass(frozen=True)
class PortfolioSnapshot:
    day: date
    equity: float
    cash: float
    positions_value: float
    cumulative_return: float
    max_drawdown: float
    trade_count: int
    risk_violations: int = 0
