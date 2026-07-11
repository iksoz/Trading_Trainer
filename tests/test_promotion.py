from datetime import date, timedelta
from unittest import TestCase

from trading_trainer.models import PortfolioSnapshot
from trading_trainer.promotion import PromotionCriteria, PromotionEvaluator


class PromotionEvaluatorTests(TestCase):
    def test_rejects_short_history(self) -> None:
        snapshots = [_snapshot(day=0, cumulative_return=0.25, trade_count=30)]

        report = PromotionEvaluator().evaluate(snapshots)

        self.assertFalse(report.approved_for_human_review)
        self.assertTrue(any("150 days" in reason for reason in report.reasons))

    def test_approves_when_all_gates_pass(self) -> None:
        snapshots = [
            _snapshot(day=day, cumulative_return=0.05 + (day * 0.0012), trade_count=30)
            for day in range(130)
        ]
        snapshots.extend(
            _snapshot(day=day, cumulative_return=0.22, trade_count=30)
            for day in range(130, 160)
        )

        report = PromotionEvaluator(
            PromotionCriteria(min_calendar_days=150, sustained_return_days=20)
        ).evaluate(snapshots)

        self.assertTrue(report.approved_for_human_review)
        self.assertEqual(report.reasons, ())


def _snapshot(day: int, cumulative_return: float, trade_count: int) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        day=date(2026, 1, 1) + timedelta(days=day),
        equity=100_000 * (1 + cumulative_return),
        cash=10_000,
        positions_value=90_000,
        cumulative_return=cumulative_return,
        max_drawdown=0.05,
        trade_count=trade_count,
        risk_violations=0,
    )
