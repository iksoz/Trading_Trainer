from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Iterator

from .models import Fill, Order, OrderType, PortfolioSnapshot, Side


class SQLitePaperStore:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def load_state(self, account_kind: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT cash, trade_count, risk_violations, positions_json
                FROM worker_state
                WHERE account_kind = ?
                """,
                (account_kind,),
            ).fetchone()
        if row is None:
            return None
        return {
            "cash": float(row["cash"]),
            "trade_count": int(row["trade_count"]),
            "risk_violations": int(row["risk_violations"]),
            "positions": json.loads(row["positions_json"] or "[]"),
        }

    def save_state(
        self,
        account_kind: str,
        account_label: str,
        broker_state: dict[str, Any],
        risk_violations: int,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO worker_state (
                    account_kind, account_label, cash, trade_count,
                    risk_violations, positions_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_kind) DO UPDATE SET
                    account_label = excluded.account_label,
                    cash = excluded.cash,
                    trade_count = excluded.trade_count,
                    risk_violations = excluded.risk_violations,
                    positions_json = excluded.positions_json,
                    updated_at = excluded.updated_at
                """,
                (
                    account_kind,
                    account_label,
                    float(broker_state["cash"]),
                    int(broker_state["trade_count"]),
                    int(risk_violations),
                    json.dumps(broker_state["positions"]),
                    _utc_now(),
                ),
            )

    def load_snapshots(self, account_kind: str, limit: int = 1000) -> list[PortfolioSnapshot]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT day, equity, cash, positions_value, cumulative_return,
                       max_drawdown, trade_count, risk_violations
                FROM snapshots
                WHERE account_kind = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (account_kind, limit),
            ).fetchall()
        return [
            PortfolioSnapshot(
                day=date.fromisoformat(row["day"]),
                equity=float(row["equity"]),
                cash=float(row["cash"]),
                positions_value=float(row["positions_value"]),
                cumulative_return=float(row["cumulative_return"]),
                max_drawdown=float(row["max_drawdown"]),
                trade_count=int(row["trade_count"]),
                risk_violations=int(row["risk_violations"]),
            )
            for row in reversed(rows)
        ]

    def record_snapshot(self, account_kind: str, snapshot: PortfolioSnapshot) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO snapshots (
                    account_kind, day, equity, cash, positions_value,
                    cumulative_return, max_drawdown, trade_count,
                    risk_violations, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account_kind,
                    snapshot.day.isoformat(),
                    snapshot.equity,
                    snapshot.cash,
                    snapshot.positions_value,
                    snapshot.cumulative_return,
                    snapshot.max_drawdown,
                    snapshot.trade_count,
                    snapshot.risk_violations,
                    _utc_now(),
                ),
            )

    def load_fills(self, account_kind: str, limit: int = 500) -> list[Fill]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT symbol, side, quantity, price, commission, reason, timestamp,
                       product, multiplier, order_type, limit_price
                FROM fills
                WHERE account_kind = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (account_kind, limit),
            ).fetchall()
        fills: list[Fill] = []
        for row in reversed(rows):
            order = Order(
                symbol=row["symbol"],
                side=Side(row["side"]),
                quantity=int(row["quantity"]),
                order_type=OrderType(row["order_type"] or "market"),
                limit_price=row["limit_price"],
                reason=row["reason"],
                product=row["product"] or "stocks",
                multiplier=int(row["multiplier"] or 1),
            )
            fills.append(
                Fill(
                    order=order,
                    price=float(row["price"]),
                    quantity=int(row["quantity"]),
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    commission=float(row["commission"]),
                )
            )
        return fills

    def record_fill(self, account_kind: str, fill: Fill) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO fills (
                    account_kind, timestamp, symbol, side, quantity,
                    price, commission, reason, product, multiplier, order_type,
                    limit_price, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account_kind,
                    fill.timestamp.isoformat(timespec="seconds"),
                    fill.order.symbol,
                    fill.order.side.value,
                    fill.quantity,
                    fill.price,
                    fill.commission,
                    fill.order.reason,
                    fill.order.product,
                    fill.order.multiplier,
                    fill.order.order_type.value,
                    fill.order.limit_price,
                    _utc_now(),
                ),
            )

    def load_logs(self, account_kind: str, limit: int = 100) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT line
                FROM logs
                WHERE account_kind = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (account_kind, limit),
            ).fetchall()
        return [str(row["line"]) for row in reversed(rows)]

    def record_log(self, account_kind: str, line: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO logs (account_kind, line, created_at) VALUES (?, ?, ?)",
                (account_kind, line, _utc_now()),
            )

    def record_decision(
        self,
        account_kind: str,
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
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO decisions (
                    account_kind, created_at, symbol, strategy, signal,
                    confidence, action, reason, risk_result, order_json, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account_kind,
                    _utc_now(),
                    symbol,
                    strategy,
                    signal,
                    confidence,
                    action,
                    reason,
                    risk_result,
                    json.dumps(order_payload or {}),
                    json.dumps(metadata or {}),
                ),
            )

    def load_decisions(self, account_kind: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT created_at, symbol, strategy, signal, confidence,
                       action, reason, risk_result, order_json, metadata_json
                FROM decisions
                WHERE account_kind = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (account_kind, limit),
            ).fetchall()
        return [
            {
                "created_at": row["created_at"],
                "symbol": row["symbol"],
                "strategy": row["strategy"],
                "signal": row["signal"],
                "confidence": float(row["confidence"]),
                "action": row["action"],
                "reason": row["reason"],
                "risk_result": row["risk_result"],
                "order": json.loads(row["order_json"] or "{}"),
                "metadata": json.loads(row["metadata_json"] or "{}"),
            }
            for row in reversed(rows)
        ]

    def record_memory(
        self,
        account_kind: str,
        *,
        category: str,
        note: str,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memories (
                    account_kind, created_at, category, note, evidence_json
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    account_kind,
                    _utc_now(),
                    category,
                    note,
                    json.dumps(evidence or {}),
                ),
            )

    def load_memories(self, account_kind: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT created_at, category, note, evidence_json
                FROM memories
                WHERE account_kind = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (account_kind, limit),
            ).fetchall()
        return [
            {
                "created_at": row["created_at"],
                "category": row["category"],
                "note": row["note"],
                "evidence": json.loads(row["evidence_json"] or "{}"),
            }
            for row in reversed(rows)
        ]

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS worker_state (
                    account_kind TEXT PRIMARY KEY,
                    account_label TEXT NOT NULL,
                    cash REAL NOT NULL,
                    trade_count INTEGER NOT NULL,
                    risk_violations INTEGER NOT NULL,
                    positions_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_kind TEXT NOT NULL,
                    day TEXT NOT NULL,
                    equity REAL NOT NULL,
                    cash REAL NOT NULL,
                    positions_value REAL NOT NULL,
                    cumulative_return REAL NOT NULL,
                    max_drawdown REAL NOT NULL,
                    trade_count INTEGER NOT NULL,
                    risk_violations INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS fills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_kind TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    price REAL NOT NULL,
                    commission REAL NOT NULL,
                    reason TEXT NOT NULL,
                    product TEXT NOT NULL DEFAULT 'stocks',
                    multiplier INTEGER NOT NULL DEFAULT 1,
                    order_type TEXT NOT NULL DEFAULT 'market',
                    limit_price REAL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_kind TEXT NOT NULL,
                    line TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_kind TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    signal TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    risk_result TEXT NOT NULL,
                    order_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_kind TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    category TEXT NOT NULL,
                    note TEXT NOT NULL,
                    evidence_json TEXT NOT NULL
                );
                """
            )
            self._ensure_column(conn, "fills", "product", "TEXT NOT NULL DEFAULT 'stocks'")
            self._ensure_column(conn, "fills", "multiplier", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "fills", "order_type", "TEXT NOT NULL DEFAULT 'market'")
            self._ensure_column(conn, "fills", "limit_price", "REAL")

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
