from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from trading_trainer.settings import load_settings


class SettingsTests(TestCase):
    def test_loads_env_file_values(self) -> None:
        with TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "TRADING_MODE=paper",
                        "LIVE_TRADING_ENABLED=false",
                        "WEBULL_APP_KEY=app-key",
                        "WEBULL_APP_SECRET=app-secret",
                        "WEBULL_SANDBOX_APP_KEY=sandbox-key",
                        "WEBULL_SANDBOX_APP_SECRET=sandbox-secret",
                        "WEBULL_ACCOUNT_ID=abc123",
                        "WEBULL_SANDBOX_ACCOUNT_ID_INV_CASH=cash123",
                        "WEBULL_SANBOX_ACCOUNT_ID_INV_MARGIN=margin123",
                        "WEBULL_ALLOWED_PRODUCTS=stocks,etfs",
                        "MARKET_DATA_POLICY=free",
                        "WEBULL_PAPER_SYMBOLS=AAPL,SPY",
                        "WEBULL_PAPER_FALLBACK_SYMBOLS=AAPL",
                        "WEBULL_PAPER_POLL_SECONDS=30",
                        "WEBULL_PAPER_TRADE_SIZE=2",
                        "PAPER_STRATEGY=shadow_portfolio",
                        "SHADOW_PORTFOLIO=bill_ackman",
                        "PAPER_HISTORY_DB_PATH=.data/test.sqlite3",
                        "PAPER_TRADING_KILL_SWITCH=true",
                        "PAPER_MANUAL_APPROVAL_REQUIRED=true",
                        "MAX_DAILY_ORDER_COUNT=3",
                        "MAX_RISK_VIOLATIONS=2",
                        "LIVE_TRADING_OPERATOR_OVERRIDE=true",
                        "MAX_DAILY_LOSS_PCT=0.02",
                    ]
                ),
                encoding="utf-8",
            )

            settings = load_settings(env_path)

            self.assertEqual(settings.trading_mode, "paper")
            self.assertFalse(settings.live_trading_enabled)
            self.assertEqual(settings.webull_app_key, "sandbox-key")
            self.assertEqual(settings.webull_app_secret, "sandbox-secret")
            self.assertEqual(settings.webull_sandbox_app_key, "sandbox-key")
            self.assertEqual(settings.webull_sandbox_app_secret, "sandbox-secret")
            self.assertEqual(settings.webull_account_id, "abc123")
            self.assertEqual(settings.webull_cash_account_id, "cash123")
            self.assertEqual(settings.webull_margin_account_id, "margin123")
            self.assertEqual(settings.webull_allowed_products, ("stocks", "etfs"))
            self.assertEqual(settings.market_data_policy, "free")
            self.assertEqual(settings.webull_paper_symbols, ("AAPL", "SPY"))
            self.assertEqual(settings.webull_paper_fallback_symbols, ("AAPL",))
            self.assertEqual(settings.webull_paper_poll_seconds, 30)
            self.assertEqual(settings.webull_paper_trade_size, 2)
            self.assertEqual(settings.paper_strategy, "shadow_portfolio")
            self.assertEqual(settings.shadow_portfolio, "bill_ackman")
            self.assertEqual(settings.paper_history_db_path, ".data/test.sqlite3")
            self.assertTrue(settings.paper_trading_kill_switch)
            self.assertTrue(settings.paper_manual_approval_required)
            self.assertEqual(settings.max_daily_order_count, 3)
            self.assertEqual(settings.max_risk_violations, 2)
            self.assertTrue(settings.live_trading_operator_override)
            self.assertEqual(settings.max_daily_loss_pct, 0.02)
