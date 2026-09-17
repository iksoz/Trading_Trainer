from unittest import TestCase

from trading_trainer.strategy_library import strategy_library


class StrategyLibraryTests(TestCase):
    def test_library_has_stock_and_options_strategies_with_risk_context(self) -> None:
        strategies = strategy_library()

        self.assertGreaterEqual(len(strategies), 10)
        self.assertIn("Stocks & ETFs", {item["asset_class"] for item in strategies})
        self.assertIn("Options", {item["asset_class"] for item in strategies})
        self.assertTrue(all(item["risk"] for item in strategies))
        self.assertTrue(all(item["name"] and item["structure"] for item in strategies))

    def test_options_reference_links_are_secure_urls(self) -> None:
        options = [item for item in strategy_library() if "Options" in item["asset_class"]]

        self.assertTrue(options)
        self.assertTrue(all(item["source_url"].startswith("https://") for item in options))
