from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import app


class DashboardPayloadTests(TestCase):
    def test_dashboard_payload_contains_promotion_status(self) -> None:
        payload = app.build_dashboard_payload()

        self.assertEqual(payload["mode"], "paper")
        self.assertIn(payload["status"], {"locked", "review_ready"})
        self.assertGreater(len(payload["timeline"]), 0)
        self.assertIn("promotion", payload)
        self.assertIn("account", payload)

    def test_live_override_requires_confirmation_phrase(self) -> None:
        with TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "LIVE_TRADING_ENABLED=false",
                        "LIVE_TRADING_OPERATOR_OVERRIDE=false",
                        "WEBULL_ALLOWED_PRODUCTS=stocks,etfs",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.object(app, "ENV_PATH", env_path):
                with self.assertRaises(ValueError):
                    app.update_dashboard_settings(
                        {
                            "allowed_products": ["stocks", "etfs"],
                            "live_trading_enabled": True,
                            "live_trading_operator_override": True,
                            "confirmation": "wrong",
                        }
                    )

    def test_updates_allowed_products_and_live_override(self) -> None:
        with TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "LIVE_TRADING_ENABLED=false",
                        "LIVE_TRADING_OPERATOR_OVERRIDE=false",
                        "WEBULL_ALLOWED_PRODUCTS=stocks,etfs",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.object(app, "ENV_PATH", env_path):
                payload = app.update_dashboard_settings(
                    {
                        "allowed_products": ["stocks"],
                        "live_trading_enabled": True,
                        "live_trading_operator_override": True,
                        "confirmation": app.LIVE_CONFIRMATION_PHRASE,
                    }
                )

            self.assertEqual(payload["settings"]["allowed_products"], ["stocks"])
            self.assertTrue(payload["settings"]["live_trading_allowed"])
            self.assertIn("WEBULL_ALLOWED_PRODUCTS=stocks", env_path.read_text(encoding="utf-8"))
