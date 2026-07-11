from __future__ import annotations

from .models import Bar, Fill, Order, Position


class LiveBrokerDisabledError(RuntimeError):
    pass


class LiveBrokerStub:
    """Placeholder that prevents accidental real-money execution."""

    starting_cash = 0.0

    @property
    def cash(self) -> float:
        return 0.0

    @property
    def trade_count(self) -> int:
        return 0

    def position(self, symbol: str) -> Position:
        return Position(symbol=symbol)

    def equity(self, prices: dict[str, float]) -> float:
        return 0.0

    def submit_order(self, order: Order, bar: Bar) -> Fill | None:
        raise LiveBrokerDisabledError(
            "Live trading is intentionally disabled. Implement a broker-specific "
            "adapter and require explicit operator approval before enabling it."
        )
