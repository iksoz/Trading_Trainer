from __future__ import annotations

from dataclasses import dataclass, field

from .broker import Broker
from .models import Bar, Fill, PortfolioSnapshot
from .risk import RiskManager
from .strategy import Strategy


@dataclass
class TradingAgent:
    broker: Broker
    strategy: Strategy
    risk_manager: RiskManager
    snapshots: list[PortfolioSnapshot] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)

    def on_bar(self, bar: Bar) -> Fill | None:
        prices = {bar.symbol: bar.close}
        equity_before = self.broker.equity(prices)
        previous_equity = self.snapshots[-1].equity if self.snapshots else equity_before
        daily_return = (equity_before - previous_equity) / previous_equity if previous_equity else 0.0
        max_drawdown = self._max_drawdown(equity_before)

        account_check = self.risk_manager.validate_account_state(max_drawdown, daily_return)
        if not account_check.approved:
            self._snapshot(bar, prices)
            return None

        position = self.broker.position(bar.symbol)
        order = self.strategy.on_bar(bar, position.quantity, equity_before)
        if order is None:
            self._snapshot(bar, prices)
            return None

        order_check = self.risk_manager.validate_order(
            order=order,
            price=bar.close,
            account_equity=equity_before,
            current_position_quantity=position.quantity,
        )
        if not order_check.approved:
            self._snapshot(bar, prices)
            return None

        fill = self.broker.submit_order(order, bar)
        if fill is not None:
            self.fills.append(fill)

        self._snapshot(bar, prices)
        return fill

    def _snapshot(self, bar: Bar, prices: dict[str, float]) -> None:
        equity = self.broker.equity(prices)
        cash = self.broker.cash
        positions_value = equity - cash
        cumulative_return = (equity - self.broker.starting_cash) / self.broker.starting_cash
        self.snapshots.append(
            PortfolioSnapshot(
                day=bar.day,
                equity=equity,
                cash=cash,
                positions_value=positions_value,
                cumulative_return=cumulative_return,
                max_drawdown=self._max_drawdown(equity),
                trade_count=self.broker.trade_count,
                risk_violations=self.risk_manager.violations,
            )
        )

    def _max_drawdown(self, current_equity: float) -> float:
        peak = max([snapshot.equity for snapshot in self.snapshots] + [current_equity])
        return (peak - current_equity) / peak if peak else 0.0
