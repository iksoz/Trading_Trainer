from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import app


class DashboardPayloadTests(TestCase):
    def test_dashboard_payload_contains_promotion_status(self) -> None:
        payload = app.build_dashboard_payload()

        self.assertEqual(payload["mode"], "paper")
        self.assertEqual(payload["status"], "locked")
        self.assertIsInstance(payload["timeline"], list)
        self.assertIsInstance(payload["fills"], list)
        self.assertIn("promotion", payload)
        self.assertIn("account", payload)
        self.assertIn("paper_worker", payload)
        self.assertIn("paper_accounts", payload)
        self.assertEqual(
            {account["account_kind"] for account in payload["paper_accounts"]},
            {"cash", "margin"},
        )

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

    def test_updates_paper_strategy_without_requiring_live_fields(self) -> None:
        with TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "LIVE_TRADING_ENABLED=false",
                        "LIVE_TRADING_OPERATOR_OVERRIDE=false",
                        "WEBULL_ALLOWED_PRODUCTS=stocks,etfs",
                        "PAPER_STRATEGY=moving_average",
                        "SHADOW_PORTFOLIO=warren_buffett",
                        "PAPER_TRADING_KILL_SWITCH=false",
                        "PAPER_MANUAL_APPROVAL_REQUIRED=false",
                        "MAX_DAILY_ORDER_COUNT=10",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.object(app, "ENV_PATH", env_path):
                payload = app.update_dashboard_settings(
                    {
                        "paper_strategy": "shadow_portfolio",
                        "shadow_portfolio": "bill_ackman",
                        "paper_trading_kill_switch": True,
                        "paper_manual_approval_required": True,
                        "max_daily_order_count": 4,
                    }
                )

            self.assertEqual(payload["settings"]["paper_strategy"], "shadow_portfolio")
            self.assertEqual(payload["settings"]["shadow_portfolio"], "bill_ackman")
            self.assertTrue(payload["settings"]["paper_trading_kill_switch"])
            self.assertTrue(payload["settings"]["paper_manual_approval_required"])
            self.assertEqual(payload["settings"]["max_daily_order_count"], 4)
            text = env_path.read_text(encoding="utf-8")
            self.assertIn("PAPER_STRATEGY=shadow_portfolio", text)
            self.assertIn("SHADOW_PORTFOLIO=bill_ackman", text)
            self.assertIn("PAPER_TRADING_KILL_SWITCH=true", text)
            self.assertIn("PAPER_MANUAL_APPROVAL_REQUIRED=true", text)
            self.assertIn("MAX_DAILY_ORDER_COUNT=4", text)

    def test_status_payload_contains_health_checks(self) -> None:
        payload = app.build_status_payload()

        self.assertIn("checks", payload)
        self.assertIn("agentic", payload)
        self.assertTrue(any(check["name"] == "Dashboard API" for check in payload["checks"]))
