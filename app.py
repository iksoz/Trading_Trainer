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
from trading_trainer.settings import load_settings
from trading_trainer.strategy import MovingAverageCrossoverStrategy, StrategyConfig


ENV_PATH = ROOT / ".env"
ALLOWED_PRODUCT_OPTIONS = ("stocks", "etfs", "options", "futures", "crypto", "event_contracts")
LIVE_CONFIRMATION_PHRASE = "ENABLE LIVE TRADING"


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

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/settings":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length).decode("utf-8") if length else "{}"
            payload = json.loads(raw_body)
            updated = update_dashboard_settings(payload)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        self._send_json(updated)

    def log_message(self, format: str, *args: object) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {self.address_string()} {format % args}")

    def _send_json(
        self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK
    ) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def build_dashboard_payload() -> dict[str, object]:
    settings = load_settings(ENV_PATH)
    agent = run_paper_simulation()
    report = PromotionEvaluator().evaluate(agent.snapshots)
    latest = agent.snapshots[-1]
    first = agent.snapshots[0]
    criteria = PromotionEvaluator().criteria
    live_unlock_source = _live_unlock_source(
        report.approved_for_human_review, settings.live_trading_operator_override
    )
    live_trading_allowed = settings.live_trading_enabled and live_unlock_source != "locked"

    return {
        "mode": "paper",
        "status": "locked" if not report.approved_for_human_review else "review_ready",
        "environment": settings.webull_env,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "account": {
            "webull_account_id": settings.webull_account_id,
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
        "settings": {
            "allowed_products": list(settings.webull_allowed_products),
            "allowed_product_options": list(ALLOWED_PRODUCT_OPTIONS),
            "market_data_policy": settings.market_data_policy,
            "market_data_plan": {
                "mode": "free_first",
                "sources": [
                    "Webull account and position endpoints",
                    "Webull quote snapshots available under current OpenAPI permissions",
                    "Delayed/free historical bars when available",
                ],
                "paid_data_required": [
                    "OpenAPI L1/L2 stock and ETF non-display subscriptions",
                    "OPRA real-time options data",
                    "OpenAPI futures market data",
                ],
            },
            "live_trading_enabled": settings.live_trading_enabled,
            "live_trading_operator_override": settings.live_trading_operator_override,
            "live_trading_allowed": live_trading_allowed,
            "live_unlock_source": live_unlock_source,
            "live_confirmation_phrase": LIVE_CONFIRMATION_PHRASE,
            "requires_2fa_token": True,
        },
    }


def update_dashboard_settings(payload: dict[str, object]) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("Settings payload must be a JSON object.")

    current = build_dashboard_payload()
    promotion = current["promotion"]
    requested_products = _clean_products(payload.get("allowed_products", []))
    live_enabled = bool(payload.get("live_trading_enabled", False))
    operator_override = bool(payload.get("live_trading_operator_override", False))

    if live_enabled and operator_override:
        confirmation = str(payload.get("confirmation", "")).strip()
        if confirmation != LIVE_CONFIRMATION_PHRASE:
            raise ValueError("Live trading override requires the exact confirmation phrase.")

    if live_enabled and not promotion["approved_for_human_review"] and not operator_override:
        raise ValueError("Live trading requires either a passed promotion gate or operator override.")

    updates = {
        "WEBULL_ALLOWED_PRODUCTS": ",".join(requested_products),
        "MARKET_DATA_POLICY": "free",
        "LIVE_TRADING_ENABLED": _bool_env(live_enabled),
        "LIVE_TRADING_OPERATOR_OVERRIDE": _bool_env(operator_override),
    }
    _update_env_file(ENV_PATH, updates)
    return build_dashboard_payload()


def _clean_products(raw_products: object) -> list[str]:
    if not isinstance(raw_products, list):
        raise ValueError("Allowed products must be a list.")
    products = []
    for item in raw_products:
        product = str(item).strip().lower()
        if product not in ALLOWED_PRODUCT_OPTIONS:
            raise ValueError(f"Unsupported product: {product}")
        if product not in products:
            products.append(product)
    if not products:
        raise ValueError("At least one allowed product is required.")
    return products


def _live_unlock_source(gate_passed: bool, operator_override: bool) -> str:
    if gate_passed:
        return "promotion_gate"
    if operator_override:
        return "operator_override"
    return "locked"


def _bool_env(value: bool) -> str:
    return "true" if value else "false"


def _update_env_file(path: Path, updates: dict[str, str]) -> None:
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    next_lines: list[str] = []

    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            next_lines.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in updates:
            next_lines.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            next_lines.append(line)

    for key, value in updates.items():
        if key not in seen:
            next_lines.append(f"{key}={value}")

    path.write_text("\n".join(next_lines) + "\n", encoding="utf-8")


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
