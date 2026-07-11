from unittest import TestCase

import app


class DashboardPayloadTests(TestCase):
    def test_dashboard_payload_contains_promotion_status(self) -> None:
        payload = app.build_dashboard_payload()

        self.assertEqual(payload["mode"], "paper")
        self.assertIn(payload["status"], {"locked", "review_ready"})
        self.assertGreater(len(payload["timeline"]), 0)
        self.assertIn("promotion", payload)
        self.assertIn("account", payload)
