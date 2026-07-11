from __future__ import annotations

import argparse
from datetime import date, timedelta
from math import sin

from .agent import TradingAgent
from .broker import PaperBroker
from .models import Bar
from .promotion import PromotionEvaluator
from .risk import RiskLimits, RiskManager
from .strategy import MovingAverageCrossoverStrategy, StrategyConfig


def main() -> None:
    parser = argparse.ArgumentParser(prog="trading-trainer")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("run-demo", help="Run a deterministic paper-trading demo.")
    args = parser.parse_args()

    if args.command == "run-demo":
        run_demo()


def run_demo() -> None:
    symbol = "DEMO"
    broker = PaperBroker(starting_cash=100_000.0, slippage_bps=1.0)
    strategy = MovingAverageCrossoverStrategy(
        StrategyConfig(symbol=symbol, trade_size=20, short_window=5, long_window=20)
    )
    risk = RiskManager(RiskLimits(max_position_pct=0.20, max_order_notional_pct=0.05))
    agent = TradingAgent(broker=broker, strategy=strategy, risk_manager=risk)

    for bar in _demo_bars(symbol=symbol, days=180):
        agent.on_bar(bar)

    report = PromotionEvaluator().evaluate(agent.snapshots)
    print(f"Final return: {report.total_return:.2%}")
    print(f"Max drawdown: {report.max_drawdown:.2%}")
    print(f"Paper days: {report.calendar_days}")
    print(f"Trades: {report.trade_count}")
    print(f"Approved for human review: {report.approved_for_human_review}")
    if report.reasons:
        print("Reasons:")
        for reason in report.reasons:
            print(f"- {reason}")


def _demo_bars(symbol: str, days: int) -> list[Bar]:
    start = date(2026, 1, 1)
    price = 100.0
    bars: list[Bar] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        trend = 0.08
        cycle = sin(offset / 6) * 0.45
        price = max(1.0, price + trend + cycle)
        bars.append(
            Bar(
                symbol=symbol,
                day=day,
                open=price - 0.4,
                high=price + 0.8,
                low=price - 0.8,
                close=price,
                volume=10_000,
            )
        )
    return bars


if __name__ == "__main__":
    main()
