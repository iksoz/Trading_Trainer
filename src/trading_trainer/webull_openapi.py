from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from .models import Bar, Order, OrderType
from .settings import AppSettings


logging.getLogger("webull").setLevel(logging.CRITICAL)
logging.getLogger("webull.core").setLevel(logging.CRITICAL)


class WebullOpenApiError(RuntimeError):
    pass


class WebullSdkMissingError(WebullOpenApiError):
    pass


@dataclass(frozen=True)
class WebullOrderResult:
    accepted: bool
    client_order_id: str
    status_code: int
    payload: Any


class WebullOpenApiClient:
    """Thin adapter around Webull's official Python SDK.

    The SDK owns signature generation, token handling, 2FA verification, and
    endpoint transport. This wrapper keeps the rest of the app isolated from
    vendor-specific imports and response shapes.
    """

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self._api_client = None
        self._trade_client = None
        self._data_client = None

    @property
    def sdk_available(self) -> bool:
        try:
            self._sdk_modules()
        except WebullSdkMissingError:
            return False
        return True

    def verify_account(self) -> dict[str, Any]:
        trade_client = self._get_trade_client()
        response = _sdk_call(
            "Webull account list",
            trade_client.account_v2.get_account_list,
        )
        return self._json_or_raise(response, "Webull account list")

    def fetch_latest_bar(self, symbol: str) -> Bar:
        data_client = self._get_data_client()
        category, timespan = self._market_data_enums()
        response = _sdk_call(
            f"Webull history bar for {symbol}",
            data_client.market_data.get_history_bar,
            symbol.upper(),
            category.US_STOCK.name,
            timespan.M1.name,
            count="1",
        )
        payload = self._json_or_raise(response, f"Webull history bar for {symbol}")
        row = self._latest_bar_row(payload)
        return _row_to_bar(symbol.upper(), row)

    def place_stock_order(self, account_id: str, order: Order) -> WebullOrderResult:
        if not account_id:
            raise WebullOpenApiError("WEBULL_ACCOUNT_ID is required before routing sandbox orders.")

        trade_client = self._get_trade_client()
        client_order_id = uuid.uuid4().hex[:32]
        new_order = {
            "combo_type": "NORMAL",
            "client_order_id": client_order_id,
            "symbol": order.symbol.upper(),
            "instrument_type": "EQUITY",
            "market": "US",
            "order_type": "MARKET" if order.order_type is OrderType.MARKET else "LIMIT",
            "quantity": str(order.quantity),
            "support_trading_session": "CORE",
            "side": order.side.value.upper(),
            "time_in_force": "DAY",
            "entrust_type": "QTY",
        }
        if order.order_type is OrderType.LIMIT and order.limit_price is not None:
            new_order["limit_price"] = f"{order.limit_price:.2f}"

        response = _sdk_call(
            f"Webull order for {order.symbol}",
            trade_client.order_v3.place_order,
            account_id,
            [new_order],
        )
        payload = response.json() if hasattr(response, "json") else response
        status_code = int(getattr(response, "status_code", 200))
        if status_code >= 400:
            raise WebullOpenApiError(f"Webull order rejected with HTTP {status_code}: {payload}")
        return WebullOrderResult(
            accepted=True,
            client_order_id=client_order_id,
            status_code=status_code,
            payload=payload,
        )

    def _get_api_client(self) -> Any:
        if self._api_client is None:
            api_client_cls, _, _ = self._sdk_modules()
            api_client = api_client_cls(
                self.settings.webull_app_key,
                self.settings.webull_app_secret,
                self.settings.webull_region,
            )
            api_client.add_endpoint(self.settings.webull_region, self.settings.webull_api_host)
            self._api_client = api_client
        return self._api_client

    def _get_trade_client(self) -> Any:
        if self._trade_client is None:
            _, trade_client_cls, _ = self._sdk_modules()
            self._trade_client = trade_client_cls(self._get_api_client())
        return self._trade_client

    def _get_data_client(self) -> Any:
        if self._data_client is None:
            _, _, data_client_cls = self._sdk_modules()
            self._data_client = data_client_cls(self._get_api_client())
        return self._data_client

    def _sdk_modules(self) -> tuple[Any, Any, Any]:
        try:
            from webull.core.client import ApiClient
            from webull.data.data_client import DataClient
            from webull.trade.trade_client import TradeClient
        except ModuleNotFoundError as exc:
            raise WebullSdkMissingError(
                "Install webull-openapi-python-sdk before starting Webull paper trading."
            ) from exc
        return ApiClient, TradeClient, DataClient

    def _market_data_enums(self) -> tuple[Any, Any]:
        try:
            from webull.data.common.category import Category
            from webull.data.common.timespan import Timespan
        except ModuleNotFoundError as exc:
            raise WebullSdkMissingError(
                "Install webull-openapi-python-sdk before fetching Webull market data."
            ) from exc
        return Category, Timespan

    def _json_or_raise(self, response: Any, label: str) -> Any:
        status_code = int(getattr(response, "status_code", 200))
        payload = response.json() if hasattr(response, "json") else response
        if status_code >= 400:
            raise WebullOpenApiError(f"{label} failed with HTTP {status_code}: {payload}")
        return payload

    def _latest_bar_row(self, payload: Any) -> dict[str, Any]:
        rows = _flatten_bar_rows(payload)
        if not rows:
            raise WebullOpenApiError("Webull returned no historical bars.")
        return rows[-1]


def _flatten_bar_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("data", "bars", "items", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _flatten_bar_rows(value)
            if nested:
                return nested
    return [payload] if _contains_price(payload) else []


def _sdk_call(label: str, func: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return func(*args, **kwargs)
    except WebullOpenApiError:
        raise
    except Exception as exc:
        raise WebullOpenApiError(f"{label} failed: {_safe_exception_message(exc)}") from exc


def _safe_exception_message(exc: Exception) -> str:
    text = str(exc).replace("\n", " ").strip()
    if not text:
        return exc.__class__.__name__
    return text[:240]


def _contains_price(row: dict[str, Any]) -> bool:
    return any(key in row for key in ("close", "c", "price", "last_price"))


def _row_to_bar(symbol: str, row: dict[str, Any]) -> Bar:
    close = _as_float(_pick(row, "close", "c", "price", "last_price", "lastPrice"))
    open_price = _as_float(_pick(row, "open", "o"), close)
    high = _as_float(_pick(row, "high", "h"), close)
    low = _as_float(_pick(row, "low", "l"), close)
    volume = int(_as_float(_pick(row, "volume", "v"), 0))
    raw_time = _pick(row, "time", "timestamp", "trade_time", "t")

    return Bar(
        symbol=symbol,
        day=_as_date(raw_time),
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def _pick(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _as_float(value: Any, default: float | None = None) -> float:
    if value is None:
        if default is None:
            raise WebullOpenApiError("Webull market data did not include a usable price.")
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        if default is not None:
            return default
        raise WebullOpenApiError(f"Could not parse Webull price value: {value}") from exc


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return datetime.utcnow().date()
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return datetime.utcnow().date()
