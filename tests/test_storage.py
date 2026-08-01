from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from trading_trainer.models import Fill, Order, PortfolioSnapshot, Side
from trading_trainer.storage import SQLitePaperStore


class SQLitePaperStoreTests(TestCase):
    def test_persists_worker_state_snapshots_logs_and_fills(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLitePaperStore(Path(temp_dir) / "paper.sqlite3")
            snapshot = PortfolioSnapshot(
                day=date(2026, 1, 1),
                equity=101_000.0,
                cash=90_000.0,
                positions_value=11_000.0,
                cumulative_return=0.01,
                max_drawdown=0.0,
                trade_count=1,
                risk_violations=0,
            )
            fill = Fill(
                order=Order("AAPL", Side.BUY, 1, reason="test"),
                price=100.0,
                quantity=1,
                timestamp=datetime(2026, 1, 1),
            )

            store.save_state(
                "cash",
                "Cash",
                {
                    "cash": 90_000.0,
                    "trade_count": 1,
                    "positions": [
                        {
                            "symbol": "AAPL",
                            "quantity": 1,
                            "average_entry_price": 100.0,
                        }
                    ],
                },
                risk_violations=0,
            )
            store.record_snapshot("cash", snapshot)
            store.record_fill("cash", fill)
            store.record_log("cash", "paper worker started")
            store.record_decision(
                "cash",
                symbol="AAPL",
                strategy="moving_average",
                signal="buy",
                confidence=0.7,
                action="routed_and_filled",
                reason="test decision",
                risk_result="approved",
                order_payload={"symbol": "AAPL"},
                metadata={"equity": 101_000.0},
            )
            store.record_memory(
                "cash",
                category="performance",
                note="test memory",
                evidence={"return": 0.01},
            )

            self.assertEqual(store.load_state("cash")["cash"], 90_000.0)
            self.assertEqual(store.load_snapshots("cash")[0].equity, 101_000.0)
            self.assertEqual(store.load_fills("cash")[0].order.symbol, "AAPL")
            self.assertEqual(store.load_logs("cash"), ["paper worker started"])
            self.assertEqual(store.load_decisions("cash")[0]["action"], "routed_and_filled")
            self.assertEqual(store.load_memories("cash")[0]["note"], "test memory")
