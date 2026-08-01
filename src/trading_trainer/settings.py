from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppSettings:
    app_env: str = "development"
    trading_mode: str = "paper"
    live_trading_enabled: bool = False
    webull_env: str = "sandbox"
    webull_region: str = "us"
    webull_api_host: str = "api.sandbox.webull.com"
    webull_trade_events_host: str = "events-api.sandbox.webull.com"
    webull_data_stream_host: str = "data-api.sandbox.webull.com"
    webull_app_key: str = ""
    webull_app_secret: str = ""
    webull_sandbox_app_key: str = ""
    webull_sandbox_app_secret: str = ""
    webull_access_token: str = ""
    webull_account_id: str = ""
    webull_cash_account_id: str = ""
    webull_margin_account_id: str = ""
    webull_allowed_products: tuple[str, ...] = ("stocks", "etfs")
    market_data_policy: str = "free"
    webull_paper_symbols: tuple[str, ...] = ("AAPL", "SPY")
    webull_paper_fallback_symbols: tuple[str, ...] = ("AAPL",)
    webull_paper_poll_seconds: int = 60
    webull_paper_trade_size: int = 1
    webull_paper_data_source: str = "webull_historical"
    webull_paper_order_routing: str = "sandbox"
    paper_strategy: str = "moving_average"
    shadow_portfolio: str = "warren_buffett"
    paper_history_db_path: str = ".data/paper_history.sqlite3"
    paper_trading_kill_switch: bool = False
    paper_manual_approval_required: bool = False
    max_daily_order_count: int = 10
    live_trading_operator_override: bool = False
    max_daily_loss_pct: float = 0.03
    max_position_pct: float = 0.25
    max_order_notional_pct: float = 0.10


def load_settings(env_path: Path | str = ".env") -> AppSettings:
    values = _read_env_file(Path(env_path))
    merged = {**values, **os.environ}

    return AppSettings(
        app_env=merged.get("APP_ENV", "development"),
        trading_mode=merged.get("TRADING_MODE", "paper"),
        live_trading_enabled=_as_bool(merged.get("LIVE_TRADING_ENABLED", "false")),
        webull_env=merged.get("WEBULL_ENV", "sandbox"),
        webull_region=merged.get("WEBULL_REGION", "us"),
        webull_api_host=merged.get("WEBULL_API_HOST", "api.sandbox.webull.com"),
        webull_trade_events_host=merged.get(
            "WEBULL_TRADE_EVENTS_HOST", "events-api.sandbox.webull.com"
        ),
        webull_data_stream_host=merged.get(
            "WEBULL_DATA_STREAM_HOST", "data-api.sandbox.webull.com"
        ),
        webull_app_key=_active_webull_value(
            merged,
            primary_key="WEBULL_APP_KEY",
            sandbox_key="WEBULL_SANDBOX_APP_KEY",
        ),
        webull_app_secret=_active_webull_value(
            merged,
            primary_key="WEBULL_APP_SECRET",
            sandbox_key="WEBULL_SANDBOX_APP_SECRET",
        ),
        webull_sandbox_app_key=merged.get("WEBULL_SANDBOX_APP_KEY", ""),
        webull_sandbox_app_secret=merged.get("WEBULL_SANDBOX_APP_SECRET", ""),
        webull_access_token=merged.get("WEBULL_ACCESS_TOKEN", ""),
        webull_account_id=merged.get("WEBULL_ACCOUNT_ID", ""),
        webull_cash_account_id=_first_value(
            merged,
            "WEBULL_SANDBOX_ACCOUNT_ID_INV_CASH",
            "WEBULL_SANBOX_ACCOUNT_ID_INV_CASH",
            "WEBULL_CASH_ACCOUNT_ID",
        ),
        webull_margin_account_id=_first_value(
            merged,
            "WEBULL_SANDBOX_ACCOUNT_ID_INV_MARGIN",
            "WEBULL_SANBOX_ACCOUNT_ID_INV_MARGIN",
            "WEBULL_MARGIN_ACCOUNT_ID",
        ),
        webull_allowed_products=_as_csv_tuple(
            merged.get("WEBULL_ALLOWED_PRODUCTS", "stocks,etfs")
        ),
        market_data_policy=merged.get("MARKET_DATA_POLICY", "free"),
        webull_paper_symbols=_as_csv_tuple(merged.get("WEBULL_PAPER_SYMBOLS", "AAPL,SPY")),
        webull_paper_fallback_symbols=_as_csv_tuple(
            merged.get("WEBULL_PAPER_FALLBACK_SYMBOLS", "AAPL")
        ),
        webull_paper_poll_seconds=_as_int(merged.get("WEBULL_PAPER_POLL_SECONDS", "60"), 60),
        webull_paper_trade_size=_as_int(merged.get("WEBULL_PAPER_TRADE_SIZE", "1"), 1),
        webull_paper_data_source=merged.get("WEBULL_PAPER_DATA_SOURCE", "webull_historical"),
        webull_paper_order_routing=merged.get("WEBULL_PAPER_ORDER_ROUTING", "sandbox"),
        paper_strategy=merged.get("PAPER_STRATEGY", "moving_average"),
        shadow_portfolio=merged.get("SHADOW_PORTFOLIO", "warren_buffett"),
        paper_history_db_path=merged.get(
            "PAPER_HISTORY_DB_PATH", ".data/paper_history.sqlite3"
        ),
        paper_trading_kill_switch=_as_bool(
            merged.get("PAPER_TRADING_KILL_SWITCH", "false")
        ),
        paper_manual_approval_required=_as_bool(
            merged.get("PAPER_MANUAL_APPROVAL_REQUIRED", "false")
        ),
        max_daily_order_count=_as_int(merged.get("MAX_DAILY_ORDER_COUNT", "10"), 10),
        live_trading_operator_override=_as_bool(
            merged.get("LIVE_TRADING_OPERATOR_OVERRIDE", "false")
        ),
        max_daily_loss_pct=_as_float(merged.get("MAX_DAILY_LOSS_PCT", "0.03")),
        max_position_pct=_as_float(merged.get("MAX_POSITION_PCT", "0.25")),
        max_order_notional_pct=_as_float(merged.get("MAX_ORDER_NOTIONAL_PCT", "0.10")),
    )


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _active_webull_value(
    values: dict[str, str],
    primary_key: str,
    sandbox_key: str,
) -> str:
    if values.get("WEBULL_ENV", "sandbox").lower() == "sandbox":
        return values.get(sandbox_key) or values.get(primary_key, "")
    return values.get(primary_key, "")


def _first_value(values: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = values.get(key, "")
        if value:
            return value
    return ""


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_float(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return 0.0


def _as_int(value: str, default: int) -> int:
    try:
        return int(value)
    except ValueError:
        return default


def _as_csv_tuple(value: str) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in value.split(",")
        if item.strip()
    )
