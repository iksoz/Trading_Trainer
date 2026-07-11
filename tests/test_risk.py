from unittest import TestCase

from trading_trainer.models import Order, Side
from trading_trainer.risk import RiskLimits, RiskManager


class RiskManagerTests(TestCase):
    def test_rejects_oversized_order(self) -> None:
        risk = RiskManager(RiskLimits(max_order_notional_pct=0.10))
        order = Order("AAPL", Side.BUY, 200)

        decision = risk.validate_order(
            order=order,
            price=100.0,
            account_equity=100_000.0,
            current_position_quantity=0,
        )

        self.assertFalse(decision.approved)
        self.assertEqual(risk.violations, 1)

    def test_rejects_short_selling_when_disabled(self) -> None:
        risk = RiskManager(RiskLimits(allow_short_selling=False))
        order = Order("AAPL", Side.SELL, 1)

        decision = risk.validate_order(
            order=order,
            price=100.0,
            account_equity=100_000.0,
            current_position_quantity=0,
        )

        self.assertFalse(decision.approved)
