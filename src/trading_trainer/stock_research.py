from __future__ import annotations

"""Small, dependency-free stock research helpers for the dashboard.

The output is deliberately descriptive rather than a trading recommendation:
it combines public price history with current news headlines and marks data
that could not be retrieved instead of silently inventing a conclusion.
"""

import json
import re
import statistics
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any


SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")
REQUEST_HEADERS = {"User-Agent": "Trading-Trainer/0.1 research dashboard"}

UP_KEYWORDS = (
    "beat", "raises forecast", "raised forecast", "upgrade", "outperform", "buy rating",
    "approval", "contract", "partnership", "launch", "buyback", "dividend increase",
    "record revenue", "growth",
)
DOWN_KEYWORDS = (
    "miss", "cuts forecast", "cut forecast", "downgrade", "underperform", "sell rating",
    "investigation", "lawsuit", "recall", "offering", "warning", "decline", "layoffs",
)


def analyze_stock(symbol: object, option: object | None = None) -> dict[str, object]:
    ticker = _clean_symbol(symbol)
    errors: list[str] = []
    try:
        market = _fetch_market_data(ticker)
    except RuntimeError as exc:
        market = {"symbol": ticker, "available": False}
        errors.append(str(exc))

    try:
        headlines = _fetch_news(ticker)
    except RuntimeError as exc:
        headlines = []
        errors.append(str(exc))

    catalysts = _build_catalysts(ticker, headlines, market)
    result: dict[str, object] = {
        "symbol": ticker,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "market": market,
        "headlines": headlines,
        "catalysts": catalysts,
        "notice": (
            "Educational market context, not investment advice. Headlines can be incomplete, "
            "stale, or already reflected in price; verify primary company filings and option quotes."
        ),
    }
    if errors:
        result["data_warnings"] = errors
    if option is not None:
        result["option"] = evaluate_long_option(option, market.get("price"))
    return result


def evaluate_long_option(option: object, market_price: object | None = None) -> dict[str, object]:
    if not isinstance(option, dict):
        raise ValueError("Option details must be a JSON object.")
    option_type = str(option.get("type", "")).strip().lower()
    if option_type not in {"call", "put"}:
        raise ValueError("Option type must be 'call' or 'put'.")
    strike = _positive_number(option.get("strike"), "Strike")
    premium = _positive_number(option.get("premium"), "Premium")
    contracts = _positive_integer(option.get("contracts", 1), "Contracts")
    multiplier = 100
    cost = premium * multiplier * contracts
    break_even = strike + premium if option_type == "call" else strike - premium
    if option_type == "put" and break_even <= 0:
        raise ValueError("Put premium must be lower than the strike price.")

    current = _optional_positive_number(option.get("underlying_price"))
    if current is None:
        current = _optional_positive_number(market_price)
    scenarios = []
    if current is not None:
        levels = [current * 0.9, current, break_even, current * 1.1]
        for level in sorted({round(item, 2) for item in levels}):
            scenarios.append({"stock_price": level, "pnl": _option_pnl(option_type, strike, premium, contracts, level)})

    if option_type == "call":
        condition = f"At expiration, the stock must close above ${break_even:,.2f} for this long call to profit."
        max_gain: object = "Unlimited as the stock rises"
    else:
        condition = f"At expiration, the stock must close below ${break_even:,.2f} for this long put to profit."
        max_gain = round((strike - premium) * multiplier * contracts, 2)
    return {
        "type": option_type,
        "strike": strike,
        "premium": premium,
        "contracts": contracts,
        "expiration": str(option.get("expiration", "")).strip(),
        "underlying_price": current,
        "cost": round(cost, 2),
        "break_even": round(break_even, 2),
        "condition": condition,
        "max_loss": round(cost, 2),
        "max_gain": max_gain,
        "scenarios": scenarios,
        "note": "This models one purchased option held to expiration. Before expiration, time decay, implied volatility, spread, and fees also affect profit/loss.",
    }


def _fetch_market_data(symbol: str) -> dict[str, object]:
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(symbol)
    query = urllib.parse.urlencode({"range": "6mo", "interval": "1d", "events": "history"})
    payload = _request_json(f"{url}?{query}", "market data")
    result = payload.get("chart", {}).get("result", [])
    if not result:
        raise RuntimeError(f"No public price history was returned for {symbol}.")
    chart = result[0]
    closes = [float(value) for value in chart.get("indicators", {}).get("quote", [{}])[0].get("close", []) if value is not None]
    if len(closes) < 2:
        raise RuntimeError(f"Public price history for {symbol} was incomplete.")
    meta = chart.get("meta", {})
    price = float(meta.get("regularMarketPrice") or closes[-1])
    previous = float(meta.get("previousClose") or closes[-2])
    change_pct = ((price - previous) / previous) if previous else 0.0
    average_20 = statistics.fmean(closes[-20:])
    average_60 = statistics.fmean(closes[-60:])
    return {
        "symbol": symbol,
        "name": meta.get("longName") or meta.get("shortName") or symbol,
        "available": True,
        "source": "Yahoo Finance public chart data",
        "price": round(price, 2),
        "previous_close": round(previous, 2),
        "change_pct": round(change_pct * 100, 2),
        "average_20_day": round(average_20, 2),
        "average_60_day": round(average_60, 2),
        "trend": "above" if average_20 >= average_60 else "below",
        "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _fetch_news(symbol: str) -> list[dict[str, str]]:
    query = urllib.parse.urlencode({"q": f"{symbol} stock", "hl": "en-US", "gl": "US", "ceid": "US:en"})
    request = urllib.request.Request(
        f"https://news.google.com/rss/search?{query}", headers=REQUEST_HEADERS
    )
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            root = ET.fromstring(response.read())
    except Exception as exc:
        raise RuntimeError("Recent public news headlines could not be retrieved.") from exc
    headlines = []
    for item in root.findall("./channel/item")[:6]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        source = item.find("source")
        if title:
            headlines.append({"title": title, "url": link, "source": source.text.strip() if source is not None and source.text else "News"})
    return headlines


def _build_catalysts(symbol: str, headlines: list[dict[str, str]], market: dict[str, object]) -> list[dict[str, str]]:
    catalysts: list[dict[str, str]] = []
    for headline in headlines:
        lower = headline["title"].lower()
        direction = "up" if any(word in lower for word in UP_KEYWORDS) else "down" if any(word in lower for word in DOWN_KEYWORDS) else "watch"
        catalysts.append({
            "direction": direction,
            "title": headline["title"],
            "detail": f"Recent {headline['source']} headline; assess the underlying facts and whether the news is already priced in.",
            "source_url": headline["url"],
        })
    trend = market.get("trend")
    if trend == "above":
        catalysts.append({"direction": "up", "title": "Price trend is constructive", "detail": "The 20-day average is above the 60-day average. A break below either average could reverse this technical tailwind.", "source_url": ""})
    elif trend == "below":
        catalysts.append({"direction": "down", "title": "Price trend is under pressure", "detail": "The 20-day average is below the 60-day average. A sustained recovery above those levels could improve sentiment.", "source_url": ""})
    catalysts.append({
        "direction": "watch",
        "title": f"{symbol} earnings, guidance, and outlook",
        "detail": "Results and forward guidance can lift shares when demand, margins, or outlook exceed expectations—and pressure them when they disappoint.",
        "source_url": "",
    })
    return catalysts[:6]


def _request_json(url: str, label: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=REQUEST_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Public {label} could not be retrieved.") from exc


def _clean_symbol(raw_symbol: object) -> str:
    symbol = str(raw_symbol or "").strip().upper()
    if not SYMBOL_PATTERN.fullmatch(symbol):
        raise ValueError("Enter a valid stock symbol, such as AAPL or BRK.B.")
    return symbol


def _positive_number(raw_value: object, label: str) -> float:
    value = _optional_positive_number(raw_value)
    if value is None:
        raise ValueError(f"{label} must be a positive number.")
    return value


def _optional_positive_number(raw_value: object) -> float | None:
    if raw_value in (None, ""):
        return None
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _positive_integer(raw_value: object, label: str) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a positive whole number.") from exc
    if value < 1:
        raise ValueError(f"{label} must be a positive whole number.")
    return value


def _option_pnl(option_type: str, strike: float, premium: float, contracts: int, price: float) -> float:
    intrinsic = max(0.0, price - strike) if option_type == "call" else max(0.0, strike - price)
    return round((intrinsic - premium) * 100 * contracts, 2)
