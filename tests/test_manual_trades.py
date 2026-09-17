from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from trading_trainer.paper_worker import PaperTradingWorker


class ManualPaperTradeTests(TestCase):
    def test_manual_option_trade_is_account_scoped_and_uses_contract_multiplier(self) -> None:
        with TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "WEBULL_ALLOWED_PRODUCTS=stocks,options",
                        "PAPER_HISTORY_DB_PATH=paper.sqlite3",
                    ]
                ),
                encoding="utf-8",
            )
            worker = PaperTradingWorker(env_path, account_kind="cash", account_label="Cash")

            result = worker.submit_manual_order(
                product="options",
                symbol="AAPL 2027-01-15 C 200",
                side="buy",
                quantity=1,
                order_type="market",
                limit_price=None,
                price=1.0,
            )

            status = worker.status()
            self.assertEqual(result["status"], "filled")
            self.assertEqual(status["fills"][-1]["product"], "options")
            self.assertEqual(status["fills"][-1]["multiplier"], 100)
            self.assertAlmostEqual(status["fills"][-1]["notional"], 100.01, places=2)
            self.assertLess(status["cash"], 100_000.0)

    def test_manual_trade_rejects_products_not_enabled_for_the_account(self) -> None:
        with TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("WEBULL_ALLOWED_PRODUCTS=stocks\n", encoding="utf-8")
            worker = PaperTradingWorker(env_path, account_kind="margin", account_label="Margin")

            with self.assertRaisesRegex(ValueError, "not enabled"):
                worker.submit_manual_order(
                    product="crypto",
                    symbol="BTC-USD",
                    side="buy",
                    quantity=1,
                    order_type="market",
                    limit_price=None,
                    price=100.0,
                )
