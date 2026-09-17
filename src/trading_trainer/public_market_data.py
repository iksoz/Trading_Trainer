from __future__ import annotations

"""Public, delayed-equity data used by the paper worker's free-first mode."""

import json
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Any

from .models import Bar


REQUEST_HEADERS = {"User-Agent": "Trading-Trainer/0.1 paper worker"}


class PublicMarketDataError(RuntimeError):
    pass


def fetch_yahoo_latest_bar(symbol: str) -> Bar:
    """Fetch the latest available daily OHLCV bar for a U.S. ticker.

    Yahoo uses a dash for class-share tickers (for example, ``BRK-B``), while
    the rest of the application and Webull use a dot (``BRK.B``).  The bar
    retains the application's symbol so strategy and order handling stay
    consistent.
    """
    normalized_symbol = symbol.strip().upper()
    yahoo_symbol = normalized_symbol.replace(".", "-")
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(yahoo_symbol)
    query = urllib.parse.urlencode({"range": "5d", "interval": "1d", "events": "history"})
    payload = _request_json(f"{url}?{query}")
    result = payload.get("chart", {}).get("result", [])
    if not result:
        raise PublicMarketDataError(f"No public price history was returned for {normalized_symbol}.")

    chart = result[0]
    quote = chart.get("indicators", {}).get("quote", [{}])[0]
    closes = quote.get("close", [])
    if not isinstance(closes, list):
        raise PublicMarketDataError(f"Public price history for {normalized_symbol} was incomplete.")
    try:
        index = next(index for index in range(len(closes) - 1, -1, -1) if closes[index] is not None)
        close = float(closes[index])
    except (StopIteration, TypeError, ValueError) as exc:
        raise PublicMarketDataError(f"Public price history for {normalized_symbol} was incomplete.") from exc

    def value(name: str, default: float) -> float:
        values = quote.get(name, [])
        raw_value = values[index] if isinstance(values, list) and index < len(values) else None
        try:
            return float(raw_value) if raw_value is not None else default
        except (TypeError, ValueError):
            return default

    timestamps = chart.get("timestamp", [])
    timestamp = timestamps[index] if isinstance(timestamps, list) and index < len(timestamps) else None
    try:
        day = datetime.fromtimestamp(float(timestamp), UTC).date()
    except (TypeError, ValueError, OSError):
        day = datetime.now(UTC).date()

    return Bar(
        symbol=normalized_symbol,
        day=day,
        open=value("open", close),
        high=value("high", close),
        low=value("low", close),
        close=close,
        volume=int(value("volume", 0.0)),
    )


def _request_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=REQUEST_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise PublicMarketDataError("Public Yahoo Finance price data could not be retrieved.") from exc
    if not isinstance(payload, dict):
        raise PublicMarketDataError("Public Yahoo Finance returned an invalid market-data response.")
    return payload
