from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from math import sin
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
FRONTEND = ROOT / "frontend"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_trainer.agent import TradingAgent
from trading_trainer.broker import PaperBroker
from trading_trainer.models import Bar
from trading_trainer.promotion import PromotionEvaluator
from trading_trainer.risk import RiskLimits, RiskManager
from trading_trainer.strategy import MovingAverageCrossoverStrategy, StrategyConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the Trading Trainer dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"Trading Trainer dashboard running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Trading Trainer dashboard.")
    finally:
        server.server_close()


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/dashboard":
            self._send_json(build_dashboard_payload())
            return

        requested = parsed.path.lstrip("/") or "index.html"
        file_path = (FRONTEND / requested).resolve()
        if FRONTEND not in file_path.parents and file_path != FRONTEND:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not file_path.exists() or file_path.is_dir():
            file_path = FRONTEND / "index.html"

        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(file_path.read_bytes())

    def log_message(self, format: str, *args: object) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {self.address_string()} {format % args}")

    def _send_json(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def build_dashboard_payload() -> dict[str, object]:
    agent = run_paper_simulation()
    report = PromotionEvaluator().evaluate(agent.snapshots)
    latest = agent.snapshots[-1]
    first = agent.snapshots[0]
    criteria = PromotionEvaluator().criteria

    return {
        "mode": "paper",
        "status": "locked" if not report.approved_for_human_review else "review_ready",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "account": {
            "starting_cash": agent.broker.starting_cash,
            "equity": latest.equity,
            "cash": latest.cash,
            "positions_value": latest.positions_value,
            "total_return": report.total_return,
            "max_drawdown": report.max_drawdown,
            "trade_count": report.trade_count,
            "risk_violations": latest.risk_violations,
            "paper_days": report.calendar_days,
        },
        "promotion": {
            "approved_for_human_review": report.approved_for_human_review,
            "reasons": list(report.reasons),
            "criteria": asdict(criteria),
            "progress": {
                "return_to_goal": min(1.0, max(0.0, report.total_return / criteria.min_total_return)),
                "days_to_goal": min(1.0, report.calendar_days / criteria.min_calendar_days),
                "trades_to_goal": min(1.0, report.trade_count / criteria.min_trades),
                "drawdown_health": max(0.0, 1.0 - (report.max_drawdown / criteria.max_drawdown)),
            },
        },
        "timeline": [
            {
                "day": snapshot.day.isoformat(),
                "equity": round(snapshot.equity, 2),
                "return": snapshot.cumulative_return,
                "drawdown": snapshot.max_drawdown,
            }
            for snapshot in agent.snapshots
        ],
        "fills": [
            {
                "day": fill.timestamp.date().isoformat(),
                "symbol": fill.order.symbol,
                "side": fill.order.side.value,
                "quantity": fill.quantity,
                "price": round(fill.price, 2),
                "notional": round(fill.notional, 2),
                "reason": fill.order.reason,
            }
            for fill in agent.fills[-12:]
        ],
        "run_window": {
            "start": first.day.isoformat(),
            "end": latest.day.isoformat(),
        },
        "agent": {
            "name": "Moving Average Scout",
            "strategy": "5/20 moving-average crossover",
            "learning_state": "simulation replay",
            "next_live_step": "disabled until promotion review passes",
        },
    }


def run_paper_simulation() -> TradingAgent:
    symbol = "DEMO"
    broker = PaperBroker(starting_cash=100_000.0, slippage_bps=1.0)
    strategy = MovingAverageCrossoverStrategy(
        StrategyConfig(symbol=symbol, trade_size=20, short_window=5, long_window=20)
    )
    risk = RiskManager(RiskLimits(max_position_pct=0.20, max_order_notional_pct=0.05))
    agent = TradingAgent(broker=broker, strategy=strategy, risk_manager=risk)

    for bar in demo_bars(symbol=symbol, days=180):
        agent.on_bar(bar)

    return agent


def demo_bars(symbol: str, days: int) -> list[Bar]:
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
