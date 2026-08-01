from __future__ import annotations

from dataclasses import asdict, dataclass
from math import sqrt
from typing import Any

from .models import Fill, PortfolioSnapshot


@dataclass(frozen=True)
class EvaluationReport:
    snapshot_count: int
    trade_count: int
    total_return: float
    max_drawdown: float
    average_daily_return: float
    volatility: float
    sharpe_like: float
    win_rate: float
    decision_count: int
    risk_rejection_count: int
    symbols_traded: tuple[str, ...]

    def payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LearnerRecommendation:
    title: str
    detail: str
    action: str
    confidence: float

    def payload(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_history(
    snapshots: list[PortfolioSnapshot],
    fills: list[Fill],
    decisions: list[dict[str, Any]],
) -> EvaluationReport:
    returns = _daily_returns(snapshots)
    total_return = snapshots[-1].cumulative_return if snapshots else 0.0
    max_drawdown = max((snapshot.max_drawdown for snapshot in snapshots), default=0.0)
    average_return = sum(returns) / len(returns) if returns else 0.0
    volatility = _stddev(returns)
    sharpe_like = (average_return / volatility * sqrt(252)) if volatility else 0.0
    risk_rejections = sum(1 for decision in decisions if decision.get("risk_result") == "rejected")
    symbols = tuple(sorted({fill.order.symbol for fill in fills}))

    return EvaluationReport(
        snapshot_count=len(snapshots),
        trade_count=len(fills),
        total_return=total_return,
        max_drawdown=max_drawdown,
        average_daily_return=average_return,
        volatility=volatility,
        sharpe_like=sharpe_like,
        win_rate=_win_rate(fills),
        decision_count=len(decisions),
        risk_rejection_count=risk_rejections,
        symbols_traded=symbols,
    )


def learner_recommendations(report: EvaluationReport) -> list[LearnerRecommendation]:
    recommendations: list[LearnerRecommendation] = []
    if report.snapshot_count < 20:
        recommendations.append(
            LearnerRecommendation(
                title="Collect more paper history",
                detail="The learner needs at least 20 snapshots before tuning strategy parameters.",
                action="keep_paper_running",
                confidence=0.9,
            )
        )
    if report.max_drawdown > 0.10:
        recommendations.append(
            LearnerRecommendation(
                title="Reduce exposure after drawdown",
                detail="Drawdown is above 10%; lower trade size or pause new buys until recovery.",
                action="reduce_trade_size",
                confidence=0.75,
            )
        )
    if report.risk_rejection_count:
        recommendations.append(
            LearnerRecommendation(
                title="Review rejected decisions",
                detail="Risk checks have rejected recent decisions; tune order size or position limits.",
                action="review_risk_rejections",
                confidence=0.8,
            )
        )
    if report.trade_count >= 10 and report.win_rate < 0.4:
        recommendations.append(
            LearnerRecommendation(
                title="Test slower signals",
                detail="Win rate is below 40%; compare longer moving-average windows before trading more.",
                action="test_longer_windows",
                confidence=0.62,
            )
        )
    if not recommendations:
        recommendations.append(
            LearnerRecommendation(
                title="Maintain current policy",
                detail="No severe risk or performance issue is visible in the current paper history.",
                action="maintain_policy",
                confidence=0.55,
            )
        )
    return recommendations


def optimizer_grid() -> list[dict[str, Any]]:
    return [
        {"strategy": "moving_average", "short_window": 5, "long_window": 20, "risk": "baseline"},
        {"strategy": "moving_average", "short_window": 8, "long_window": 30, "risk": "slower"},
        {"strategy": "moving_average", "short_window": 13, "long_window": 50, "risk": "defensive"},
        {"strategy": "shadow_portfolio", "rebalance": "buy_once", "risk": "portfolio_shadow"},
    ]


def policy_state(
    report: EvaluationReport,
    *,
    kill_switch: bool,
    manual_approval_required: bool,
    max_daily_order_count: int,
    orders_today: int,
) -> dict[str, Any]:
    if kill_switch:
        mode = "halted"
        reason = "Paper trading kill switch is enabled."
    elif manual_approval_required:
        mode = "manual_review"
        reason = "Manual approval mode records decisions but blocks routing."
    elif orders_today >= max_daily_order_count:
        mode = "order_limited"
        reason = "Daily paper order limit has been reached."
    elif report.max_drawdown > 0.15:
        mode = "defensive"
        reason = "Max drawdown exceeds the defensive threshold."
    else:
        mode = "autonomous_paper"
        reason = "Paper policy can route approved sandbox orders."

    return {
        "mode": mode,
        "reason": reason,
        "orders_today": orders_today,
        "max_daily_order_count": max_daily_order_count,
        "kill_switch": kill_switch,
        "manual_approval_required": manual_approval_required,
    }


def memory_notes(report: EvaluationReport) -> list[dict[str, Any]]:
    if report.snapshot_count == 0:
        return [
            {
                "category": "startup",
                "note": "No paper snapshots are available yet; learner memory is waiting for evidence.",
                "evidence": {},
            }
        ]
    return [
        {
            "category": "performance",
            "note": (
                f"Paper return is {report.total_return:.2%} with "
                f"{report.max_drawdown:.2%} max drawdown across {report.snapshot_count} snapshots."
            ),
            "evidence": report.payload(),
        }
    ]


def _daily_returns(snapshots: list[PortfolioSnapshot]) -> list[float]:
    returns: list[float] = []
    for previous, current in zip(snapshots, snapshots[1:]):
        if previous.equity:
            returns.append((current.equity - previous.equity) / previous.equity)
    return returns


def _stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    average = sum(values) / len(values)
    variance = sum((value - average) ** 2 for value in values) / (len(values) - 1)
    return sqrt(variance)


def _win_rate(fills: list[Fill]) -> float:
    buy_prices: dict[str, list[float]] = {}
    closed_trades = 0
    wins = 0
    for fill in fills:
        symbol = fill.order.symbol
        if fill.order.side.value == "buy":
            buy_prices.setdefault(symbol, []).append(fill.price)
            continue
        entries = buy_prices.get(symbol, [])
        if not entries:
            continue
        entry_price = entries.pop(0)
        closed_trades += 1
        if fill.price > entry_price:
            wins += 1
    if not closed_trades:
        return 0.0
    return wins / closed_trades
