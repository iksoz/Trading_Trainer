from __future__ import annotations

from dataclasses import dataclass

from .models import Order, Side


@dataclass(frozen=True)
class RiskLimits:
    max_position_pct: float = 0.25
    max_order_notional_pct: float = 0.10
    max_drawdown_pct: float = 0.15
    max_daily_loss_pct: float = 0.03
    allow_short_selling: bool = False


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str = ""


class RiskManager:
    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()
        self.violations = 0

    def validate_order(
        self,
        order: Order,
        price: float,
        account_equity: float,
        current_position_quantity: int,
    ) -> RiskDecision:
        order_notional = order.notional_at(price)

        if account_equity <= 0:
            return self._reject("Account equity must be positive.")
        if order_notional > account_equity * self.limits.max_order_notional_pct:
            return self._reject("Order notional exceeds max order limit.")
        if order.side is Side.SELL and not self.limits.allow_short_selling:
            if order.quantity > current_position_quantity:
                return self._reject("Short selling is disabled.")

        resulting_quantity = (
            current_position_quantity + order.quantity
            if order.side is Side.BUY
            else current_position_quantity - order.quantity
        )
        resulting_notional = abs(resulting_quantity * price * order.multiplier)
        if resulting_notional > account_equity * self.limits.max_position_pct:
            return self._reject("Resulting position exceeds max position limit.")

        return RiskDecision(approved=True)

    def validate_account_state(self, max_drawdown: float, daily_return: float) -> RiskDecision:
        if max_drawdown > self.limits.max_drawdown_pct:
            return self._reject("Max drawdown limit breached.")
        if daily_return < -self.limits.max_daily_loss_pct:
            return self._reject("Daily loss limit breached.")
        return RiskDecision(approved=True)

    def _reject(self, reason: str) -> RiskDecision:
        self.violations += 1
        return RiskDecision(approved=False, reason=reason)
