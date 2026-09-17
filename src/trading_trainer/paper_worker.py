from __future__ import annotations

import threading
from math import ceil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .broker import PaperBroker
from .models import Bar, Fill, Order, OrderType, PortfolioSnapshot, Side
from .public_market_data import PublicMarketDataError, fetch_yahoo_latest_bar
from .rate_limit import WebullOrderRateLimiter
from .learning import (
    evaluate_history,
    learner_recommendations,
    memory_notes,
    optimizer_grid,
    policy_state,
)
from .risk import RiskManager
from .settings import AppSettings, load_settings
from .storage import SQLitePaperStore
from .strategy import (
    MovingAverageCrossoverStrategy,
    ShadowPortfolioConfig,
    ShadowPortfolioStrategy,
    Strategy,
    StrategyConfig,
)
from .superstar import get_superstar_portfolio
from .webull_openapi import WebullOpenApiClient, WebullOpenApiError, WebullSdkMissingError


class PaperWorkerError(RuntimeError):
    pass


# Both Cash and Margin workers share one broker allowance.
WEBULL_ORDER_RATE_LIMITER = WebullOrderRateLimiter()


class PaperTradingWorker:
    def __init__(self, env_path: Path, account_kind: str, account_label: str) -> None:
        self.env_path = env_path
        self.account_kind = account_kind
        self.account_label = account_label
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._broker = PaperBroker(starting_cash=100_000.0, slippage_bps=1.0)
        self._risk = RiskManager()
        self._strategies: dict[str, Strategy] = {}
        self._latest_prices: dict[str, float] = {}
        self._snapshots: list[PortfolioSnapshot] = []
        self._fills: list[Fill] = []
        self._logs: list[str] = []
        self._last_error = ""
        self._last_tick: datetime | None = None
        self._tick_count = 0
        self._orders_routed = 0
        self._symbol_errors: dict[str, str] = {}
        settings = load_settings(self.env_path)
        self._store = SQLitePaperStore(_history_db_path(self.env_path, settings))
        self._load_persisted_history()

    def start(self) -> dict[str, Any]:
        with self._lock:
            settings = load_settings(self.env_path)
            self._validate_start(settings)
            if self._thread and self._thread.is_alive():
                return self.status()

            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="webull-paper-worker",
                daemon=True,
            )
            self._thread.start()
            self._log(f"Webull sandbox {self.account_label} paper worker started.")
            return self.status()

    def stop(self) -> dict[str, Any]:
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=3)
        with self._lock:
            self._log(f"Webull sandbox {self.account_label} paper worker stopped.")
            return self.status()

    def submit_manual_order(
        self,
        *,
        product: str,
        symbol: str,
        side: str,
        quantity: int,
        order_type: str,
        limit_price: float | None,
        price: float,
    ) -> dict[str, Any]:
        """Execute a user-entered paper trade in this worker's isolated ledger."""
        with self._lock:
            settings = load_settings(self.env_path)
            normalized_product = product.strip().lower()
            normalized_symbol = symbol.strip().upper()
            try:
                parsed_side = Side(side.strip().lower())
                parsed_order_type = OrderType(order_type.strip().lower())
            except ValueError as exc:
                raise ValueError("Side must be buy or sell and order type must be market or limit.") from exc
            if normalized_product not in {item.lower() for item in settings.webull_allowed_products}:
                raise ValueError(f"{normalized_product} is not enabled in Allowed Products.")
            if not normalized_symbol:
                raise ValueError("Symbol is required.")
            if quantity < 1:
                raise ValueError("Quantity must be a positive whole number.")
            if price <= 0:
                raise ValueError("Reference price must be greater than zero.")
            if parsed_order_type is OrderType.LIMIT and (limit_price is None or limit_price <= 0):
                raise ValueError("Limit orders require a limit price greater than zero.")
            if settings.paper_trading_kill_switch:
                raise ValueError("Paper trading kill switch is enabled.")
            if self._orders_today() >= settings.max_daily_order_count:
                raise ValueError("Daily paper order limit has been reached.")

            multiplier = 100 if normalized_product == "options" else 1
            order = Order(
                symbol=normalized_symbol,
                side=parsed_side,
                quantity=quantity,
                order_type=parsed_order_type,
                limit_price=limit_price,
                reason="manual dashboard trade",
                product=normalized_product,
                multiplier=multiplier,
            )
            bar = Bar(
                symbol=normalized_symbol,
                day=datetime.now(UTC).date(),
                open=price,
                high=price,
                low=price,
                close=price,
            )
            equity_before = self._broker.equity(self._latest_prices)
            account_check = self._risk.validate_account_state(
                self._max_drawdown(equity_before), 0.0
            )
            if not account_check.approved:
                raise ValueError(account_check.reason)
            position = self._broker.position(order.position_key, order.multiplier)
            order_check = self._risk.validate_order(
                order=order,
                price=price,
                account_equity=equity_before,
                current_position_quantity=position.quantity,
            )
            if not order_check.approved:
                self._record_decision(
                    symbol=normalized_symbol,
                    strategy="manual",
                    signal=parsed_side.value,
                    confidence=1.0,
                    action="manual_risk_rejected",
                    reason=order_check.reason,
                    risk_result="rejected",
                    order_payload=_order_payload(order),
                    metadata={"product": normalized_product, "reference_price": price},
                )
                raise ValueError(order_check.reason)

            fill = self._broker.submit_order(order, bar)
            if fill is None:
                self._record_decision(
                    symbol=normalized_symbol,
                    strategy="manual",
                    signal=parsed_side.value,
                    confidence=1.0,
                    action="manual_limit_open",
                    reason="limit price was not reached at the supplied reference price",
                    risk_result="approved",
                    order_payload=_order_payload(order),
                    metadata={"product": normalized_product, "reference_price": price},
                )
                self._log(f"Manual {normalized_product} limit order remains open: {normalized_symbol}.")
                return {"status": "open", "message": "Limit price was not reached; no paper fill recorded."}

            self._latest_prices[order.position_key] = fill.price
            self._fills.append(fill)
            self._store.record_fill(self.account_kind, fill)
            self._record_decision(
                symbol=normalized_symbol,
                strategy="manual",
                signal=parsed_side.value,
                confidence=1.0,
                action="manual_filled",
                reason=order.reason,
                risk_result="approved",
                order_payload=_order_payload(order),
                metadata={
                    "product": normalized_product,
                    "reference_price": price,
                    "account_equity": equity_before,
                },
            )
            self._snapshot(bar)
            self._refresh_memory()
            self._log(
                f"Manual {normalized_product} paper fill: {parsed_side.value} "
                f"{quantity} {normalized_symbol} in {self.account_label}."
            )
            return {"status": "filled", "message": "Manual paper trade filled."}

    def status(self) -> dict[str, Any]:
        with self._lock:
            settings = load_settings(self.env_path)
            active = bool(self._thread and self._thread.is_alive())
            latest = self._snapshots[-1] if self._snapshots else None
            sdk_available = WebullOpenApiClient(settings).sdk_available
            decisions = self._store.load_decisions(self.account_kind)
            evaluation = evaluate_history(self._snapshots, self._fills, decisions)
            policy = policy_state(
                evaluation,
                kill_switch=settings.paper_trading_kill_switch,
                manual_approval_required=settings.paper_manual_approval_required,
                max_daily_order_count=settings.max_daily_order_count,
                orders_today=self._orders_today(),
            )
            return {
                "active": active,
                "mode": "webull_sandbox",
                "account_kind": self.account_kind,
                "account_label": self.account_label,
                "account_id_configured": bool(self._account_id(settings)),
                "environment": settings.webull_env,
                "api_host": settings.webull_api_host,
                "symbols": list(settings.webull_paper_symbols),
                "active_symbols": list(self._active_symbols(settings)),
                "candidate_symbols": list(self._candidate_symbols(settings)),
                "fallback_symbols": list(settings.webull_paper_fallback_symbols),
                "poll_seconds": settings.webull_paper_poll_seconds,
                "trade_size": settings.webull_paper_trade_size,
                "data_source": settings.webull_paper_data_source,
                "order_routing": settings.webull_paper_order_routing,
                "strategy": settings.paper_strategy,
                "shadow_portfolio": get_superstar_portfolio(settings.shadow_portfolio).payload(),
                "history_db_path": str(self._store.db_path),
                "sdk_available": sdk_available,
                "account_configured": bool(self._account_id(settings)),
                "credentials_configured": bool(settings.webull_app_key and settings.webull_app_secret),
                "last_error": self._last_error,
                "last_tick": self._last_tick.isoformat(timespec="seconds") if self._last_tick else "",
                "tick_count": self._tick_count,
                "orders_routed": self._orders_routed,
                "symbol_errors": dict(self._symbol_errors),
                "equity": latest.equity if latest else self._broker.starting_cash,
                "cash": self._broker.cash,
                "positions_value": (latest.positions_value if latest else 0.0),
                "total_return": (latest.cumulative_return if latest else 0.0),
                "risk_violations": self._risk.violations,
                "snapshots": [_snapshot_payload(snapshot) for snapshot in self._snapshots[-120:]],
                "fills": [_fill_payload(fill) for fill in self._fills[-20:]],
                "logs": list(self._logs[-20:]),
                "decisions": decisions[-30:],
                "memories": self._store.load_memories(self.account_kind)[-20:],
                "evaluation": evaluation.payload(),
                "recommendations": [
                    recommendation.payload()
                    for recommendation in learner_recommendations(evaluation)
                ],
                "optimizer_grid": optimizer_grid(),
                "policy": policy,
                "broker_controls": {
                    "kill_switch": settings.paper_trading_kill_switch,
                    "manual_approval_required": settings.paper_manual_approval_required,
                    "max_daily_order_count": settings.max_daily_order_count,
                    "orders_today": self._orders_today(),
                },
            }

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            settings = load_settings(self.env_path)
            try:
                self._run_once(settings)
            except Exception as exc:  # worker must report errors without killing dashboard
                with self._lock:
                    self._last_error = str(exc)
                    self._log(f"Worker error: {exc}")
            wait_seconds = max(5, settings.webull_paper_poll_seconds)
            self._stop_event.wait(wait_seconds)

    def _run_once(self, settings: AppSettings) -> None:
        self._validate_start(settings)
        client = WebullOpenApiClient(settings)
        symbols = [symbol.upper() for symbol in self._candidate_symbols(settings)]
        successful_bars = 0
        for symbol in symbols:
            try:
                bar = self._fetch_latest_bar(settings, client, symbol)
            except (WebullOpenApiError, PublicMarketDataError) as exc:
                self._symbol_errors[symbol] = str(exc)
                self._record_decision(
                    symbol=symbol,
                    strategy=settings.paper_strategy,
                    signal="data_unavailable",
                    confidence=0.0,
                    action="skip_symbol",
                    reason=str(exc),
                    risk_result="not_checked",
                )
                self._log(f"Skipped {symbol}: {exc}")
                continue
            self._symbol_errors.pop(symbol, None)
            self._process_bar(settings, client, bar)
            successful_bars += 1

        with self._lock:
            if successful_bars:
                self._last_error = ""
                self._last_tick = datetime.now(UTC)
                self._tick_count += 1
                self._refresh_memory()
            elif self._symbol_errors:
                self._last_error = "All active symbols failed market-data fetch."

    def _fetch_latest_bar(
        self,
        settings: AppSettings,
        client: WebullOpenApiClient,
        symbol: str,
    ) -> Bar:
        source = settings.webull_paper_data_source.strip().lower()
        if source == "public_yahoo":
            return fetch_yahoo_latest_bar(symbol)
        if source == "webull_historical":
            return client.fetch_latest_bar(symbol)
        raise PaperWorkerError(
            "WEBULL_PAPER_DATA_SOURCE must be 'public_yahoo' or 'webull_historical'."
        )

    def _process_bar(
        self,
        settings: AppSettings,
        client: WebullOpenApiClient,
        bar: Bar,
    ) -> None:
        strategy = self._strategy_for(bar.symbol, settings)
        self._latest_prices[f"stocks:{bar.symbol}"] = bar.close
        equity_before = self._broker.equity(self._latest_prices)
        previous_equity = self._snapshots[-1].equity if self._snapshots else equity_before
        daily_return = (equity_before - previous_equity) / previous_equity if previous_equity else 0.0
        max_drawdown = self._max_drawdown(equity_before)

        account_check = self._risk.validate_account_state(max_drawdown, daily_return)
        if not account_check.approved:
            self._snapshot(bar)
            self._record_decision(
                symbol=bar.symbol,
                strategy=settings.paper_strategy,
                signal="account_risk_block",
                confidence=0.0,
                action="block",
                reason=account_check.reason,
                risk_result="rejected",
            )
            self._log(f"Risk blocked account action: {account_check.reason}")
            return

        position = self._broker.position(f"stocks:{bar.symbol}")
        order = strategy.on_bar(bar, position.quantity, equity_before)
        if order is None:
            self._snapshot(bar)
            self._record_decision(
                symbol=bar.symbol,
                strategy=settings.paper_strategy,
                signal="hold",
                confidence=0.45,
                action="hold",
                reason="strategy produced no order",
                risk_result="not_checked",
                metadata={"equity": equity_before, "position": position.quantity},
            )
            return

        if settings.paper_trading_kill_switch:
            self._snapshot(bar)
            self._record_decision(
                symbol=bar.symbol,
                strategy=settings.paper_strategy,
                signal=order.side.value,
                confidence=0.0,
                action="blocked_by_kill_switch",
                reason="paper trading kill switch is enabled",
                risk_result="not_checked",
                order_payload=_order_payload(order),
            )
            self._log(f"Kill switch blocked {order.side.value} {order.symbol}.")
            return

        if self._orders_today() >= settings.max_daily_order_count:
            self._snapshot(bar)
            self._record_decision(
                symbol=bar.symbol,
                strategy=settings.paper_strategy,
                signal=order.side.value,
                confidence=0.35,
                action="blocked_by_order_limit",
                reason="daily paper order limit reached",
                risk_result="not_checked",
                order_payload=_order_payload(order),
            )
            self._log(f"Daily order limit blocked {order.side.value} {order.symbol}.")
            return

        order_check = self._risk.validate_order(
            order=order,
            price=bar.close,
            account_equity=equity_before,
            current_position_quantity=position.quantity,
        )
        if not order_check.approved:
            self._snapshot(bar)
            self._record_decision(
                symbol=bar.symbol,
                strategy=settings.paper_strategy,
                signal=order.side.value,
                confidence=0.3,
                action="risk_rejected",
                reason=order_check.reason,
                risk_result="rejected",
                order_payload=_order_payload(order),
            )
            self._log(f"Risk blocked {order.side.value} {order.symbol}: {order_check.reason}")
            return

        if settings.paper_manual_approval_required:
            self._snapshot(bar)
            self._record_decision(
                symbol=bar.symbol,
                strategy=settings.paper_strategy,
                signal=order.side.value,
                confidence=0.65,
                action="queued_for_manual_review",
                reason="manual approval mode is enabled",
                risk_result="approved",
                order_payload=_order_payload(order),
            )
            self._log(f"Manual approval queued {order.side.value} {order.quantity} {order.symbol}.")
            return

        if settings.webull_paper_order_routing == "sandbox":
            rate_limit = WEBULL_ORDER_RATE_LIMITER.acquire(
                min_interval_seconds=settings.webull_order_min_interval_seconds,
                max_orders_per_minute=settings.webull_order_max_per_minute,
            )
            if not rate_limit.allowed:
                retry_after = max(1, ceil(rate_limit.retry_after_seconds))
                reason = f"Webull order throttle active; retry in about {retry_after} seconds."
                self._snapshot(bar)
                self._record_decision(
                    symbol=bar.symbol,
                    strategy=settings.paper_strategy,
                    signal=order.side.value,
                    confidence=0.5,
                    action="blocked_by_broker_rate_limit",
                    reason=reason,
                    risk_result="approved",
                    order_payload=_order_payload(order),
                )
                self._log(f"{reason} Blocked {order.side.value} {order.symbol}.")
                return
            try:
                result = client.place_stock_order(self._account_id(settings), order)
            except WebullOpenApiError as exc:
                if _is_broker_rate_limited(str(exc)):
                    WEBULL_ORDER_RATE_LIMITER.cool_down(
                        settings.webull_order_429_cooldown_seconds
                    )
                self._snapshot(bar)
                self._record_decision(
                    symbol=bar.symbol,
                    strategy=settings.paper_strategy,
                    signal=order.side.value,
                    confidence=0.5,
                    action="broker_rejected",
                    reason=str(exc),
                    risk_result="approved",
                    order_payload=_order_payload(order),
                )
                self._log(f"Broker rejected {order.side.value} {order.quantity} {order.symbol}: {exc}")
                return
            self._orders_routed += 1 if result.accepted else 0
            self._log(
                f"{self.account_label} sandbox order {result.client_order_id} accepted for "
                f"{order.side.value} {order.quantity} {order.symbol}."
            )

        fill = self._broker.submit_order(order, bar)
        if fill is not None:
            self._fills.append(fill)
            self._store.record_fill(self.account_kind, fill)
            self._record_decision(
                symbol=bar.symbol,
                strategy=settings.paper_strategy,
                signal=order.side.value,
                confidence=0.7,
                action="routed_and_filled",
                reason=order.reason,
                risk_result="approved",
                order_payload=_order_payload(order),
                metadata={"fill_price": fill.price, "account_equity": equity_before},
            )
            self._log(f"Paper ledger filled {fill.order.side.value} {fill.quantity} {fill.order.symbol}.")
        self._snapshot(bar)

    def _strategy_for(self, symbol: str, settings: AppSettings) -> Strategy:
        key = f"{settings.paper_strategy}:{settings.shadow_portfolio}:{symbol}:{settings.webull_paper_trade_size}"
        if key not in self._strategies:
            portfolio = get_superstar_portfolio(settings.shadow_portfolio)
            if settings.paper_strategy == "shadow_portfolio":
                self._strategies[key] = ShadowPortfolioStrategy(
                    ShadowPortfolioConfig(
                        symbol=symbol,
                        portfolio_name=portfolio.name,
                        trade_size=settings.webull_paper_trade_size,
                    )
                )
            else:
                self._strategies[key] = MovingAverageCrossoverStrategy(
                    StrategyConfig(
                        symbol=symbol,
                        trade_size=settings.webull_paper_trade_size,
                        short_window=5,
                        long_window=20,
                    )
                )
        return self._strategies[key]

    def _active_symbols(self, settings: AppSettings) -> tuple[str, ...]:
        if settings.paper_strategy == "shadow_portfolio":
            return get_superstar_portfolio(settings.shadow_portfolio).symbols()
        return settings.webull_paper_symbols

    def _candidate_symbols(self, settings: AppSettings) -> tuple[str, ...]:
        symbols = list(self._active_symbols(settings))
        if settings.webull_env.lower() == "sandbox":
            for fallback_symbol in settings.webull_paper_fallback_symbols:
                if fallback_symbol not in symbols:
                    symbols.append(fallback_symbol)
        return tuple(symbols)

    def _load_persisted_history(self) -> None:
        state = self._store.load_state(self.account_kind)
        if state is not None:
            self._broker.load_state(
                cash=float(state["cash"]),
                trade_count=int(state["trade_count"]),
                positions=list(state["positions"]),
            )
            self._risk.violations = int(state["risk_violations"])
        self._snapshots = self._store.load_snapshots(self.account_kind)
        self._fills = self._store.load_fills(self.account_kind)
        self._logs = self._store.load_logs(self.account_kind)

    def _snapshot(self, bar: Bar) -> None:
        equity = self._broker.equity(self._latest_prices)
        cash = self._broker.cash
        positions_value = equity - cash
        cumulative_return = (equity - self._broker.starting_cash) / self._broker.starting_cash
        snapshot = PortfolioSnapshot(
            day=bar.day,
            equity=equity,
            cash=cash,
            positions_value=positions_value,
            cumulative_return=cumulative_return,
            max_drawdown=self._max_drawdown(equity),
            trade_count=self._broker.trade_count,
            risk_violations=self._risk.violations,
        )
        self._snapshots.append(snapshot)
        self._store.record_snapshot(self.account_kind, snapshot)
        self._store.save_state(
            self.account_kind,
            self.account_label,
            self._broker.export_state(),
            self._risk.violations,
        )

    def _max_drawdown(self, current_equity: float) -> float:
        peak = max([snapshot.equity for snapshot in self._snapshots] + [current_equity])
        return (peak - current_equity) / peak if peak else 0.0

    def _orders_today(self) -> int:
        today = datetime.now(UTC).date()
        return sum(1 for fill in self._fills if fill.timestamp.date() == today)

    def _record_decision(
        self,
        *,
        symbol: str,
        strategy: str,
        signal: str,
        confidence: float,
        action: str,
        reason: str,
        risk_result: str,
        order_payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._store.record_decision(
            self.account_kind,
            symbol=symbol,
            strategy=strategy,
            signal=signal,
            confidence=confidence,
            action=action,
            reason=reason,
            risk_result=risk_result,
            order_payload=order_payload,
            metadata=metadata,
        )

    def _refresh_memory(self) -> None:
        decisions = self._store.load_decisions(self.account_kind)
        report = evaluate_history(self._snapshots, self._fills, decisions)
        for note in memory_notes(report):
            self._store.record_memory(
                self.account_kind,
                category=str(note["category"]),
                note=str(note["note"]),
                evidence=dict(note["evidence"]),
            )

    def _validate_start(self, settings: AppSettings) -> None:
        if settings.webull_env.lower() != "sandbox":
            raise PaperWorkerError("Paper worker only runs when WEBULL_ENV=sandbox.")
        if "sandbox" not in settings.webull_api_host:
            raise PaperWorkerError("Paper worker requires the Webull sandbox API host.")
        if not settings.webull_app_key or not settings.webull_app_secret:
            raise PaperWorkerError("WEBULL_APP_KEY and WEBULL_APP_SECRET are required.")
        if not self._account_id(settings):
            raise PaperWorkerError(
                f"Webull {self.account_label} sandbox account ID is required for paper routing."
            )
        if "stocks" not in {product.lower() for product in settings.webull_allowed_products}:
            raise PaperWorkerError("Stocks must be enabled in allowed products.")
        if settings.webull_paper_order_routing != "sandbox":
            raise PaperWorkerError("Only Webull sandbox order routing is enabled for paper trading.")
        if not WebullOpenApiClient(settings).sdk_available:
            raise WebullSdkMissingError(
                "Install webull-openapi-python-sdk before starting Webull paper trading."
            )

    def _account_id(self, settings: AppSettings) -> str:
        if self.account_kind == "cash":
            return settings.webull_cash_account_id or settings.webull_account_id
        if self.account_kind == "margin":
            return settings.webull_margin_account_id
        return settings.webull_account_id

    def _log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._logs.append(f"{timestamp} {message}")
        self._logs = self._logs[-100:]
        self._store.record_log(self.account_kind, self._logs[-1])


def _history_db_path(env_path: Path, settings: AppSettings) -> Path:
    configured = Path(settings.paper_history_db_path)
    if configured.is_absolute():
        return configured
    return env_path.resolve().parent / configured


def _fill_payload(fill: Fill) -> dict[str, Any]:
    return {
        "day": fill.timestamp.date().isoformat(),
        "symbol": fill.order.symbol,
        "product": fill.order.product,
        "multiplier": fill.order.multiplier,
        "side": fill.order.side.value,
        "quantity": fill.quantity,
        "price": round(fill.price, 2),
        "notional": round(fill.notional, 2),
        "reason": fill.order.reason,
        "kind": "sandbox" if fill.order.side in (Side.BUY, Side.SELL) else "paper",
    }


def _order_payload(order: Any) -> dict[str, Any]:
    return {
        "symbol": order.symbol,
        "side": order.side.value,
        "quantity": order.quantity,
        "order_type": order.order_type.value,
        "limit_price": order.limit_price,
        "reason": order.reason,
        "product": order.product,
        "multiplier": order.multiplier,
    }


def _is_broker_rate_limited(message: str) -> bool:
    normalized = message.upper()
    return "429" in normalized or "TOO_MANY_REQUESTS" in normalized


def _snapshot_payload(snapshot: PortfolioSnapshot) -> dict[str, Any]:
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
