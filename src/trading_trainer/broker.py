from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from .models import Bar, Fill, Order, OrderType, Position, Side


class Broker(Protocol):
    @property
    def starting_cash(self) -> float:
        ...

    @property
    def cash(self) -> float:
        ...

    @property
    def trade_count(self) -> int:
        ...

    def position(self, symbol: str) -> Position:
        ...

    def equity(self, prices: dict[str, float]) -> float:
        ...

    def submit_order(self, order: Order, bar: Bar) -> Fill | None:
        ...


class PaperBroker:
    """Simple deterministic paper broker for strategy development."""

    def __init__(
        self,
        starting_cash: float = 100_000.0,
        commission_per_trade: float = 0.0,
        slippage_bps: float = 1.0,
    ) -> None:
        self.starting_cash = starting_cash
        self._cash = starting_cash
        self._commission_per_trade = commission_per_trade
        self._slippage_bps = slippage_bps
        self._positions: dict[str, Position] = {}
        self._trade_count = 0

    @property
    def cash(self) -> float:
        return self._cash

    @property
    def trade_count(self) -> int:
        return self._trade_count

    def position(self, symbol: str) -> Position:
        return self._positions.setdefault(symbol, Position(symbol=symbol))

    def equity(self, prices: dict[str, float]) -> float:
        positions_value = sum(
            position.market_value(prices.get(symbol, position.average_entry_price))
            for symbol, position in self._positions.items()
        )
        return self._cash + positions_value

    def submit_order(self, order: Order, bar: Bar) -> Fill | None:
        if order.quantity <= 0:
            raise ValueError("Order quantity must be positive.")
        if order.symbol != bar.symbol:
            raise ValueError("Order symbol must match the supplied market bar.")

        fill_price = self._fillable_price(order, bar)
        if fill_price is None:
            return None

        notional = order.quantity * fill_price
        commission = self._commission_per_trade

        if order.side is Side.BUY:
            total_cost = notional + commission
            if total_cost > self._cash:
                raise ValueError("Insufficient paper cash for order.")
            self._cash -= total_cost
            self._add_position(order.symbol, order.quantity, fill_price)
        else:
            position = self.position(order.symbol)
            if order.quantity > position.quantity:
                raise ValueError("Cannot sell more than the paper position holds.")
            self._cash += notional - commission
            self._remove_position(order.symbol, order.quantity)

        self._trade_count += 1
        return Fill(
            order=order,
            price=fill_price,
            quantity=order.quantity,
            timestamp=datetime.combine(bar.day, datetime.min.time()),
            commission=commission,
        )

    def export_state(self) -> dict[str, Any]:
        return {
            "cash": self._cash,
            "trade_count": self._trade_count,
            "positions": [
                {
                    "symbol": position.symbol,
                    "quantity": position.quantity,
                    "average_entry_price": position.average_entry_price,
                }
                for position in self._positions.values()
                if position.quantity
            ],
        }

    def load_state(
        self,
        cash: float,
        trade_count: int,
        positions: list[dict[str, Any]],
    ) -> None:
        self._cash = cash
        self._trade_count = trade_count
        self._positions = {
            str(item["symbol"]): Position(
                symbol=str(item["symbol"]),
                quantity=int(item["quantity"]),
                average_entry_price=float(item["average_entry_price"]),
            )
            for item in positions
        }

    def _fillable_price(self, order: Order, bar: Bar) -> float | None:
        slippage = bar.close * (self._slippage_bps / 10_000)
        if order.order_type is OrderType.MARKET:
            return bar.close + slippage if order.side is Side.BUY else bar.close - slippage

        if order.limit_price is None:
            raise ValueError("Limit orders require a limit price.")
        if order.side is Side.BUY and bar.low <= order.limit_price:
            return min(order.limit_price, bar.close + slippage)
        if order.side is Side.SELL and bar.high >= order.limit_price:
            return max(order.limit_price, bar.close - slippage)
        return None

    def _add_position(self, symbol: str, quantity: int, fill_price: float) -> None:
        position = self.position(symbol)
        previous_cost = position.quantity * position.average_entry_price
        added_cost = quantity * fill_price
        position.quantity += quantity
        position.average_entry_price = (previous_cost + added_cost) / position.quantity

    def _remove_position(self, symbol: str, quantity: int) -> None:
        position = self.position(symbol)
        position.quantity -= quantity
        if position.quantity == 0:
            position.average_entry_price = 0.0
