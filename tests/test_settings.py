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
                        "WEBULL_ACCOUNT_ID=abc123",
                        "WEBULL_ALLOWED_PRODUCTS=stocks,etfs",
                        "MARKET_DATA_POLICY=free",
                        "LIVE_TRADING_OPERATOR_OVERRIDE=true",
                        "MAX_DAILY_LOSS_PCT=0.02",
                    ]
                ),
                encoding="utf-8",
            )

            settings = load_settings(env_path)

            self.assertEqual(settings.trading_mode, "paper")
            self.assertFalse(settings.live_trading_enabled)
            self.assertEqual(settings.webull_app_key, "app-key")
            self.assertEqual(settings.webull_app_secret, "app-secret")
            self.assertEqual(settings.webull_account_id, "abc123")
            self.assertEqual(settings.webull_allowed_products, ("stocks", "etfs"))
            self.assertEqual(settings.market_data_policy, "free")
            self.assertTrue(settings.live_trading_operator_override)
            self.assertEqual(settings.max_daily_loss_pct, 0.02)
