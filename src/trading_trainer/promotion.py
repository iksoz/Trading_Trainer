from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from .models import PortfolioSnapshot


@dataclass(frozen=True)
class PromotionCriteria:
    min_calendar_days: int = 150
    min_total_return: float = 0.20
    sustained_return_days: int = 20
    max_drawdown: float = 0.15
    min_trades: int = 25
    max_risk_violations: int = 0


@dataclass(frozen=True)
class PromotionReport:
    approved_for_human_review: bool
    reasons: tuple[str, ...]
    total_return: float
    max_drawdown: float
    calendar_days: int
    trade_count: int


class PromotionEvaluator:
    def __init__(self, criteria: PromotionCriteria | None = None) -> None:
        self.criteria = criteria or PromotionCriteria()

    def evaluate(self, snapshots: list[PortfolioSnapshot]) -> PromotionReport:
        if not snapshots:
            return PromotionReport(False, ("No paper-trading history.",), 0.0, 0.0, 0, 0)

        first = snapshots[0]
        last = snapshots[-1]
        calendar_days = (last.day - first.day).days + 1
        max_drawdown = max(snapshot.max_drawdown for snapshot in snapshots)
        risk_violations = max(snapshot.risk_violations for snapshot in snapshots)
        trade_count = last.trade_count
        reasons: list[str] = []

        if calendar_days < self.criteria.min_calendar_days:
            reasons.append(
                f"Needs at least {self.criteria.min_calendar_days} days; saw {calendar_days}."
            )
        if last.cumulative_return < self.criteria.min_total_return:
            reasons.append(
                f"Return {last.cumulative_return:.2%} is below "
                f"{self.criteria.min_total_return:.2%}."
            )
        if max_drawdown > self.criteria.max_drawdown:
            reasons.append(
                f"Max drawdown {max_drawdown:.2%} exceeds {self.criteria.max_drawdown:.2%}."
            )
        if trade_count < self.criteria.min_trades:
            reasons.append(f"Needs at least {self.criteria.min_trades} trades; saw {trade_count}.")
        if risk_violations > self.criteria.max_risk_violations:
            reasons.append(f"Risk violations recorded: {risk_violations}.")
        if not self._sustained_return_met(snapshots):
            reasons.append(
                f"Final {self.criteria.sustained_return_days} snapshots did not all hold "
                f"{self.criteria.min_total_return:.2%}+ return."
            )

        return PromotionReport(
            approved_for_human_review=not reasons,
            reasons=tuple(reasons),
            total_return=last.cumulative_return,
            max_drawdown=max_drawdown,
            calendar_days=calendar_days,
            trade_count=trade_count,
        )

    def _sustained_return_met(self, snapshots: list[PortfolioSnapshot]) -> bool:
        window = snapshots[-self.criteria.sustained_return_days :]
        if len(window) < self.criteria.sustained_return_days:
            return False

        first_window_day = window[0].day
        last_window_day = window[-1].day
        if last_window_day - first_window_day < timedelta(days=self.criteria.sustained_return_days - 1):
            return False

        return all(
            snapshot.cumulative_return >= self.criteria.min_total_return for snapshot in window
        )
