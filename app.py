from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import threading
import webbrowser
from dataclasses import asdict
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
FRONTEND = ROOT / "frontend"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_trainer.models import PortfolioSnapshot
from trading_trainer.paper_worker import PaperTradingWorker
from trading_trainer.promotion import PromotionEvaluator
from trading_trainer.settings import load_settings
from trading_trainer.stock_research import analyze_stock
from trading_trainer.superstar import (
    get_superstar_portfolio,
    superstar_portfolio_keys,
    superstar_portfolios_payload,
)


ENV_PATH = ROOT / ".env"
ALLOWED_PRODUCT_OPTIONS = ("stocks", "etfs", "options", "futures", "crypto", "event_contracts")
PAPER_STRATEGY_OPTIONS = ("moving_average", "shadow_portfolio")
LIVE_CONFIRMATION_PHRASE = "ENABLE LIVE TRADING"
PAPER_WORKERS = {
    "cash": PaperTradingWorker(ENV_PATH, account_kind="cash", account_label="Cash"),
    "margin": PaperTradingWorker(ENV_PATH, account_kind="margin", account_label="Margin"),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the Trading Trainer dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Start the dashboard without opening it in a browser.",
    )
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    dashboard_url = _dashboard_url(args.host, args.port)
    print(f"Trading Trainer dashboard running at {dashboard_url}")
    if not args.no_browser:
        threading.Timer(0.2, webbrowser.open, args=(dashboard_url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Trading Trainer dashboard.")
    finally:
        server.server_close()


def _dashboard_url(host: str, port: int) -> str:
    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    return f"http://{browser_host}:{port}/"


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/dashboard":
            self._send_json(build_dashboard_payload())
            return
        if parsed.path == "/api/status":
            self._send_json(build_status_payload())
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
        if (
            parsed.path != "/api/settings"
            and parsed.path != "/api/stock-analysis"
            and not parsed.path.startswith("/api/paper/")
        ):
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length).decode("utf-8") if length else "{}"
            payload = json.loads(raw_body)
            if parsed.path == "/api/settings":
                updated = update_dashboard_settings(payload)
            elif parsed.path == "/api/stock-analysis":
                if not isinstance(payload, dict):
                    raise ValueError("Stock analysis payload must be a JSON object.")
                updated = analyze_stock(payload.get("symbol"), payload.get("option"))
            else:
                updated = run_paper_action(parsed.path)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        except RuntimeError as exc:
            self._send_json({"error": str(exc), "dashboard": build_dashboard_payload()}, status=HTTPStatus.BAD_REQUEST)
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
    paper_accounts = _paper_account_statuses()
    paper_worker = _aggregate_paper_status(paper_accounts)
    snapshots = _aggregate_snapshots(paper_accounts)
    report = PromotionEvaluator().evaluate(snapshots)
    latest = snapshots[-1] if snapshots else None
    first = snapshots[0] if snapshots else None
    criteria = PromotionEvaluator().criteria
    live_unlock_source = _live_unlock_source(
        report.approved_for_human_review, settings.live_trading_operator_override
    )
    live_trading_allowed = settings.live_trading_enabled and live_unlock_source != "locked"
    selected_portfolio = get_superstar_portfolio(settings.shadow_portfolio)

    return {
        "mode": "paper",
        "status": "locked" if not report.approved_for_human_review else "review_ready",
        "environment": settings.webull_env,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "account": {
            "webull_account_id": settings.webull_account_id,
            "starting_cash": paper_worker["starting_cash"],
            "equity": paper_worker["equity"],
            "cash": paper_worker["cash"],
            "positions_value": paper_worker["positions_value"],
            "total_return": report.total_return,
            "max_drawdown": report.max_drawdown,
            "trade_count": report.trade_count,
            "risk_violations": paper_worker["risk_violations"],
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
            for snapshot in snapshots
        ],
        "fills": paper_worker["fills"],
        "run_window": {
            "start": first.day.isoformat() if first else "",
            "end": latest.day.isoformat() if latest else "",
        },
        "agent": {
            "name": "Moving Average Scout",
            "strategy": _strategy_label(settings.paper_strategy, selected_portfolio.name),
            "learning_state": (
                "webull sandbox paper trading active"
                if paper_worker["active"]
                else "waiting for Webull sandbox paper worker"
            ),
            "next_live_step": "disabled until Webull paper promotion review passes",
        },
        "paper_worker": paper_worker,
        "paper_accounts": paper_accounts,
        "system_status": build_status_payload(settings, paper_accounts, paper_worker),
        "agentic": {
            "evaluation": paper_worker["evaluation"],
            "recommendations": paper_worker["recommendations"],
            "optimizer_grid": paper_worker["optimizer_grid"],
            "policy": paper_worker["policy"],
            "decisions": paper_worker["decisions"],
            "memories": paper_worker["memories"],
        },
        "settings": {
            "allowed_products": list(settings.webull_allowed_products),
            "allowed_product_options": list(ALLOWED_PRODUCT_OPTIONS),
            "paper_strategy": settings.paper_strategy,
            "paper_strategy_options": list(PAPER_STRATEGY_OPTIONS),
            "shadow_portfolio": selected_portfolio.key,
            "shadow_portfolio_detail": selected_portfolio.payload(),
            "shadow_portfolio_options": superstar_portfolios_payload(),
            "paper_history_db_path": settings.paper_history_db_path,
            "webull_paper_fallback_symbols": list(settings.webull_paper_fallback_symbols),
            "paper_trading_kill_switch": settings.paper_trading_kill_switch,
            "paper_manual_approval_required": settings.paper_manual_approval_required,
            "max_daily_order_count": settings.max_daily_order_count,
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


def _worker_snapshots(worker_status: dict[str, object]) -> list[PortfolioSnapshot]:
    snapshots: list[PortfolioSnapshot] = []
    for item in worker_status.get("snapshots", []):
        if not isinstance(item, dict):
            continue
        snapshots.append(
            PortfolioSnapshot(
                day=date.fromisoformat(str(item["day"])),
                equity=float(item["equity"]),
                cash=float(item["cash"]),
                positions_value=float(item["positions_value"]),
                cumulative_return=float(item["cumulative_return"]),
                max_drawdown=float(item["max_drawdown"]),
                trade_count=int(item["trade_count"]),
                risk_violations=int(item["risk_violations"]),
            )
        )
    return snapshots


def _paper_account_statuses() -> list[dict[str, object]]:
    return [worker.status() for worker in PAPER_WORKERS.values()]


def _aggregate_paper_status(accounts: list[dict[str, object]]) -> dict[str, object]:
    fills = [
        {**fill, "account_label": account["account_label"], "account_kind": account["account_kind"]}
        for account in accounts
        for fill in account.get("fills", [])
        if isinstance(fill, dict)
    ]
    fills.sort(key=lambda item: str(item.get("day", "")))
    decisions = [
        {**decision, "account_label": account["account_label"], "account_kind": account["account_kind"]}
        for account in accounts
        for decision in account.get("decisions", [])
        if isinstance(decision, dict)
    ]
    decisions.sort(key=lambda item: str(item.get("created_at", "")))
    memories = [
        {**memory, "account_label": account["account_label"], "account_kind": account["account_kind"]}
        for account in accounts
        for memory in account.get("memories", [])
        if isinstance(memory, dict)
    ]
    memories.sort(key=lambda item: str(item.get("created_at", "")))
    recommendations = [
        {**recommendation, "account_label": account["account_label"], "account_kind": account["account_kind"]}
        for account in accounts
        for recommendation in account.get("recommendations", [])
        if isinstance(recommendation, dict)
    ]
    symbol_errors = {
        f"{account['account_label']}:{symbol}": error
        for account in accounts
        for symbol, error in dict(account.get("symbol_errors", {})).items()
    }
    starting_cash = 100_000.0 * len(accounts)
    return {
        "active": any(bool(account["active"]) for account in accounts),
        "mode": "webull_sandbox_multi_account",
        "account_kind": "aggregate",
        "account_label": "All Accounts",
        "account_id_configured": all(bool(account["account_id_configured"]) for account in accounts),
        "environment": accounts[0]["environment"] if accounts else "sandbox",
        "api_host": accounts[0]["api_host"] if accounts else "",
        "symbols": accounts[0]["symbols"] if accounts else [],
        "active_symbols": accounts[0]["active_symbols"] if accounts else [],
        "candidate_symbols": accounts[0]["candidate_symbols"] if accounts else [],
        "fallback_symbols": accounts[0]["fallback_symbols"] if accounts else [],
        "poll_seconds": accounts[0]["poll_seconds"] if accounts else 0,
        "trade_size": accounts[0]["trade_size"] if accounts else 0,
        "data_source": accounts[0]["data_source"] if accounts else "",
        "order_routing": accounts[0]["order_routing"] if accounts else "",
        "strategy": accounts[0]["strategy"] if accounts else "moving_average",
        "shadow_portfolio": accounts[0]["shadow_portfolio"] if accounts else {},
        "history_db_path": accounts[0]["history_db_path"] if accounts else "",
        "sdk_available": all(bool(account["sdk_available"]) for account in accounts),
        "account_configured": all(bool(account["account_configured"]) for account in accounts),
        "credentials_configured": all(bool(account["credentials_configured"]) for account in accounts),
        "last_error": " | ".join(
            f"{account['account_label']}: {account['last_error']}"
            for account in accounts
            if account.get("last_error")
        ),
        "last_tick": max((str(account.get("last_tick", "")) for account in accounts), default=""),
        "tick_count": sum(int(account["tick_count"]) for account in accounts),
        "orders_routed": sum(int(account["orders_routed"]) for account in accounts),
        "symbol_errors": symbol_errors,
        "starting_cash": starting_cash,
        "equity": sum(float(account["equity"]) for account in accounts),
        "cash": sum(float(account["cash"]) for account in accounts),
        "positions_value": sum(float(account["positions_value"]) for account in accounts),
        "total_return": (
            (sum(float(account["equity"]) for account in accounts) - starting_cash) / starting_cash
            if starting_cash
            else 0.0
        ),
        "risk_violations": sum(int(account["risk_violations"]) for account in accounts),
        "snapshots": [_snapshot_payload(snapshot) for snapshot in _aggregate_snapshots(accounts)],
        "fills": fills[-40:],
        "decisions": decisions[-50:],
        "memories": memories[-30:],
        "recommendations": recommendations[-20:],
        "optimizer_grid": accounts[0]["optimizer_grid"] if accounts else [],
        "evaluation": _aggregate_evaluation(accounts),
        "policy": _aggregate_policy(accounts),
        "broker_controls": accounts[0]["broker_controls"] if accounts else {},
        "logs": [
            f"{account['account_label']}: {line}"
            for account in accounts
            for line in account.get("logs", [])
        ][-40:],
    }


def _aggregate_evaluation(accounts: list[dict[str, object]]) -> dict[str, object]:
    evaluations = [
        account.get("evaluation", {})
        for account in accounts
        if isinstance(account.get("evaluation", {}), dict)
    ]
    if not evaluations:
        return {}
    return {
        "snapshot_count": sum(int(item.get("snapshot_count", 0)) for item in evaluations),
        "trade_count": sum(int(item.get("trade_count", 0)) for item in evaluations),
        "total_return": sum(float(account.get("total_return", 0.0)) for account in accounts) / max(1, len(accounts)),
        "max_drawdown": max(float(item.get("max_drawdown", 0.0)) for item in evaluations),
        "decision_count": sum(int(item.get("decision_count", 0)) for item in evaluations),
        "risk_rejection_count": sum(int(item.get("risk_rejection_count", 0)) for item in evaluations),
        "symbols_traded": sorted(
            {
                symbol
                for item in evaluations
                for symbol in item.get("symbols_traded", [])
            }
        ),
    }


def _aggregate_policy(accounts: list[dict[str, object]]) -> dict[str, object]:
    policies = [
        account.get("policy", {})
        for account in accounts
        if isinstance(account.get("policy", {}), dict)
    ]
    if not policies:
        return {}
    severe_order = ("halted", "manual_review", "order_limited", "defensive", "autonomous_paper")
    selected = sorted(
        policies,
        key=lambda item: severe_order.index(str(item.get("mode", "autonomous_paper"))),
    )[0]
    return {
        **selected,
        "orders_today": sum(int(item.get("orders_today", 0)) for item in policies),
    }


def build_status_payload(
    settings: object | None = None,
    paper_accounts: list[dict[str, object]] | None = None,
    paper_worker: dict[str, object] | None = None,
) -> dict[str, object]:
    loaded_settings = settings or load_settings(ENV_PATH)
    accounts = paper_accounts or _paper_account_statuses()
    aggregate = paper_worker or _aggregate_paper_status(accounts)
    history_path = _history_db_path(loaded_settings.paper_history_db_path)
    checks = [
        _status_check("Dashboard API", True, "Responding from /api/dashboard."),
        _status_check("Frontend files", (FRONTEND / "index.html").exists(), "index.html is present."),
        _status_check("Settings file", ENV_PATH.exists(), ".env is present."),
        _status_check("SQLite history", history_path.exists() or history_path.parent.exists(), str(history_path)),
        _status_check("Webull SDK", bool(aggregate["sdk_available"]), "webull-openapi-python-sdk import check."),
        _status_check("Webull credentials", bool(aggregate["credentials_configured"]), "Sandbox app key and secret presence."),
        _status_check("Webull account IDs", bool(aggregate["account_configured"]), "Cash and margin account IDs presence."),
        _status_check("Paper worker", bool(aggregate["active"]), "At least one worker is running."),
        _status_check("Symbol health", not bool(aggregate["symbol_errors"]), "No active symbol fetch errors."),
    ]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "overall": "ok" if all(check["ok"] for check in checks[:7]) else "attention",
        "checks": checks,
        "workers": [
            {
                "account_kind": account["account_kind"],
                "account_label": account["account_label"],
                "active": account["active"],
                "last_error": account["last_error"],
                "tick_count": account["tick_count"],
                "orders_routed": account["orders_routed"],
                "symbol_errors": account.get("symbol_errors", {}),
                "policy": account.get("policy", {}),
            }
            for account in accounts
        ],
        "broker_controls": aggregate["broker_controls"],
        "agentic": {
            "policy": aggregate["policy"],
            "evaluation": aggregate["evaluation"],
            "recommendations": aggregate["recommendations"],
            "decision_count": aggregate["evaluation"].get("decision_count", 0),
            "memory_count": len(aggregate["memories"]),
        },
    }


def _aggregate_snapshots(accounts: list[dict[str, object]]) -> list[PortfolioSnapshot]:
    account_snapshots = [
        _worker_snapshots(account)
        for account in accounts
    ]
    days = sorted(
        {
            snapshot.day
            for snapshots in account_snapshots
            for snapshot in snapshots
        }
    )
    if not days:
        return []

    starting_cash = 100_000.0 * len(accounts)
    aggregate: list[PortfolioSnapshot] = []
    latest_by_account: list[PortfolioSnapshot | None] = [None for _ in accounts]
    for day in days:
        for index, snapshots in enumerate(account_snapshots):
            for snapshot in snapshots:
                if snapshot.day <= day:
                    latest_by_account[index] = snapshot

        equity = sum(snapshot.equity if snapshot else 100_000.0 for snapshot in latest_by_account)
        cash = sum(snapshot.cash if snapshot else 100_000.0 for snapshot in latest_by_account)
        positions_value = sum(snapshot.positions_value if snapshot else 0.0 for snapshot in latest_by_account)
        cumulative_return = (equity - starting_cash) / starting_cash if starting_cash else 0.0
        peak = max([snapshot.equity for snapshot in aggregate] + [equity])
        max_drawdown = (peak - equity) / peak if peak else 0.0
        aggregate.append(
            PortfolioSnapshot(
                day=day,
                equity=equity,
                cash=cash,
                positions_value=positions_value,
                cumulative_return=cumulative_return,
                max_drawdown=max_drawdown,
                trade_count=sum(snapshot.trade_count if snapshot else 0 for snapshot in latest_by_account),
                risk_violations=sum(
                    snapshot.risk_violations if snapshot else 0 for snapshot in latest_by_account
                ),
            )
        )
    return aggregate


def _snapshot_payload(snapshot: PortfolioSnapshot) -> dict[str, object]:
    return {
        "day": snapshot.day.isoformat(),
        "equity": round(snapshot.equity, 2),
        "cash": round(snapshot.cash, 2),
        "positions_value": round(snapshot.positions_value, 2),
        "cumulative_return": snapshot.cumulative_return,
        "max_drawdown": snapshot.max_drawdown,
        "trade_count": snapshot.trade_count,
        "risk_violations": snapshot.risk_violations,
    }


def run_paper_action(path: str) -> dict[str, object]:
    parts = path.strip("/").split("/")
    if len(parts) == 3:
        action = parts[2]
        workers = PAPER_WORKERS.values()
    elif len(parts) == 4:
        account_kind = parts[2]
        action = parts[3]
        if account_kind not in PAPER_WORKERS:
            raise ValueError(f"Unknown paper account: {account_kind}")
        workers = [PAPER_WORKERS[account_kind]]
    else:
        raise ValueError("Unsupported paper worker action.")

    if action not in {"start", "stop"}:
        raise ValueError(f"Unsupported paper worker action: {action}")

    for worker in workers:
        if action == "start":
            worker.start()
        else:
            worker.stop()
    return {
        "paper_accounts": _paper_account_statuses(),
        "dashboard": build_dashboard_payload(),
    }


def update_dashboard_settings(payload: dict[str, object]) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("Settings payload must be a JSON object.")

    current = build_dashboard_payload()
    promotion = current["promotion"]
    current_settings = load_settings(ENV_PATH)
    requested_products = _clean_products(
        payload.get("allowed_products", list(current_settings.webull_allowed_products))
    )
    requested_strategy = _clean_strategy(
        payload.get("paper_strategy", current_settings.paper_strategy)
    )
    requested_shadow_portfolio = _clean_shadow_portfolio(
        payload.get("shadow_portfolio", current_settings.shadow_portfolio)
    )
    kill_switch = bool(
        payload.get("paper_trading_kill_switch", current_settings.paper_trading_kill_switch)
    )
    manual_approval = bool(
        payload.get(
            "paper_manual_approval_required",
            current_settings.paper_manual_approval_required,
        )
    )
    max_daily_order_count = _clean_positive_int(
        payload.get("max_daily_order_count", current_settings.max_daily_order_count),
        "max_daily_order_count",
    )
    live_enabled = bool(
        payload.get("live_trading_enabled", current_settings.live_trading_enabled)
    )
    operator_override = bool(
        payload.get(
            "live_trading_operator_override",
            current_settings.live_trading_operator_override,
        )
    )

    if live_enabled and operator_override:
        confirmation = str(payload.get("confirmation", "")).strip()
        if confirmation != LIVE_CONFIRMATION_PHRASE:
            raise ValueError("Live trading override requires the exact confirmation phrase.")

    if live_enabled and not promotion["approved_for_human_review"] and not operator_override:
        raise ValueError("Live trading requires either a passed promotion gate or operator override.")

    updates = {
        "WEBULL_ALLOWED_PRODUCTS": ",".join(requested_products),
        "MARKET_DATA_POLICY": "free",
        "PAPER_STRATEGY": requested_strategy,
        "SHADOW_PORTFOLIO": requested_shadow_portfolio,
        "PAPER_TRADING_KILL_SWITCH": _bool_env(kill_switch),
        "PAPER_MANUAL_APPROVAL_REQUIRED": _bool_env(manual_approval),
        "MAX_DAILY_ORDER_COUNT": str(max_daily_order_count),
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


def _clean_strategy(raw_strategy: object) -> str:
    strategy = str(raw_strategy).strip().lower()
    if strategy not in PAPER_STRATEGY_OPTIONS:
        raise ValueError(f"Unsupported paper strategy: {strategy}")
    return strategy


def _clean_shadow_portfolio(raw_portfolio: object) -> str:
    portfolio = str(raw_portfolio).strip().lower()
    if portfolio not in superstar_portfolio_keys():
        raise ValueError(f"Unsupported shadow portfolio: {portfolio}")
    return portfolio


def _strategy_label(strategy: str, portfolio_name: str) -> str:
    if strategy == "shadow_portfolio":
        return f"Shadow {portfolio_name} top holdings"
    return "5/20 moving-average crossover"


def _clean_positive_int(raw_value: object, label: str) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a positive integer.") from exc
    if value < 1:
        raise ValueError(f"{label} must be a positive integer.")
    return value


def _history_db_path(configured_path: str) -> Path:
    path = Path(configured_path)
    if path.is_absolute():
        return path
    return ROOT / path


def _status_check(name: str, ok: bool, detail: str) -> dict[str, object]:
    return {
        "name": name,
        "ok": ok,
        "status": "ok" if ok else "attention",
        "detail": detail,
    }


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


if __name__ == "__main__":
    main()
