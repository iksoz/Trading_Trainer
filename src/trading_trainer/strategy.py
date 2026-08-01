from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Protocol

from .models import Bar, Order, Side


class Strategy(Protocol):
    def on_bar(self, bar: Bar, current_quantity: int, account_equity: float) -> Order | None:
        ...


@dataclass(frozen=True)
class StrategyConfig:
    symbol: str
    trade_size: int = 10
    short_window: int = 10
    long_window: int = 30


class MovingAverageCrossoverStrategy:
    """Example strategy. Replace this with learned policies later."""

    def __init__(self, config: StrategyConfig) -> None:
        if config.short_window >= config.long_window:
            raise ValueError("short_window must be less than long_window.")
        self.config = config
        self._closes: deque[float] = deque(maxlen=config.long_window)
        self._last_signal: str | None = None

    def on_bar(self, bar: Bar, current_quantity: int, account_equity: float) -> Order | None:
        if bar.symbol != self.config.symbol:
            return None

        self._closes.append(bar.close)
        if len(self._closes) < self.config.long_window:
            return None

        closes = list(self._closes)
        short_average = sum(closes[-self.config.short_window :]) / self.config.short_window
        long_average = sum(closes) / self.config.long_window

        if short_average > long_average and self._last_signal != "long":
            self._last_signal = "long"
            return Order(
                symbol=bar.symbol,
                side=Side.BUY,
                quantity=self.config.trade_size,
                reason="short average crossed above long average",
            )

        if short_average < long_average and current_quantity > 0 and self._last_signal != "flat":
            self._last_signal = "flat"
            return Order(
                symbol=bar.symbol,
                side=Side.SELL,
                quantity=min(self.config.trade_size, current_quantity),
                reason="short average crossed below long average",
            )

        return None


@dataclass(frozen=True)
class ShadowPortfolioConfig:
    symbol: str
    portfolio_name: str
    trade_size: int = 1


class ShadowPortfolioStrategy:
    """Buys the selected portfolio's tracked symbols once for shadow testing."""

    def __init__(self, config: ShadowPortfolioConfig) -> None:
        self.config = config

    def on_bar(self, bar: Bar, current_quantity: int, account_equity: float) -> Order | None:
        if bar.symbol != self.config.symbol or current_quantity > 0:
            return None
        return Order(
            symbol=bar.symbol,
            side=Side.BUY,
            quantity=self.config.trade_size,
            reason=f"shadowing {self.config.portfolio_name} top holdings",
        )
