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
    webull_access_token: str = ""
    webull_account_id: str = ""
    webull_allowed_products: tuple[str, ...] = ("stocks", "etfs")
    market_data_policy: str = "free"
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
        webull_app_key=merged.get("WEBULL_APP_KEY", ""),
        webull_app_secret=merged.get("WEBULL_APP_SECRET", ""),
        webull_access_token=merged.get("WEBULL_ACCESS_TOKEN", ""),
        webull_account_id=merged.get("WEBULL_ACCOUNT_ID", ""),
        webull_allowed_products=_as_csv_tuple(
            merged.get("WEBULL_ALLOWED_PRODUCTS", "stocks,etfs")
        ),
        market_data_policy=merged.get("MARKET_DATA_POLICY", "free"),
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


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_float(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return 0.0


def _as_csv_tuple(value: str) -> tuple[str, ...]:
    return tuple(
        item.strip().lower()
        for item in value.split(",")
        if item.strip()
    )
