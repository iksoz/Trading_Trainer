from unittest import TestCase
from unittest.mock import patch

from trading_trainer.stock_research import DAILY_WATCHLIST_UNIVERSE, analyze_stock, daily_watchlist, evaluate_long_option


class OptionOutcomeTests(TestCase):
    def test_long_call_break_even_and_expiration_scenarios(self) -> None:
        outcome = evaluate_long_option(
            {"type": "call", "strike": 100, "premium": 4.5, "contracts": 2},
            market_price=100,
        )

        self.assertEqual(outcome["break_even"], 104.5)
        self.assertEqual(outcome["cost"], 900)
        self.assertEqual(outcome["max_loss"], 900)
        self.assertEqual(outcome["max_gain"], "Unlimited as the stock rises")
        self.assertTrue(any(item["stock_price"] == 110 for item in outcome["scenarios"]))

    def test_long_put_break_even_and_max_gain(self) -> None:
        outcome = evaluate_long_option(
            {"type": "put", "strike": "75", "premium": "3", "contracts": "1"}
        )

        self.assertEqual(outcome["break_even"], 72)
        self.assertEqual(outcome["max_gain"], 7200)
        self.assertIn("below $72.00", outcome["condition"])

    def test_analyze_stock_includes_headline_and_price_catalysts(self) -> None:
        market = {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "available": True,
            "price": 200.0,
            "previous_close": 198.0,
            "change_pct": 1.01,
            "average_20_day": 198.0,
            "average_60_day": 190.0,
            "trend": "above",
        }
        news = [{"title": "Apple beats revenue expectations", "url": "https://example.test/news", "source": "Example"}]
        with patch("trading_trainer.stock_research._fetch_market_data", return_value=market), patch(
            "trading_trainer.stock_research._fetch_news", return_value=news
        ):
            result = analyze_stock("aapl")

        self.assertEqual(result["symbol"], "AAPL")
        self.assertEqual(result["catalysts"][0]["direction"], "up")
        self.assertTrue(any(item["title"] == "Price trend is constructive" for item in result["catalysts"]))

    def test_daily_watchlist_selects_the_strongest_market_signal_in_each_theme(self) -> None:
        def market(symbol: str) -> dict[str, object]:
            multiplier = 8.0 if symbol in {"AMD", "ORCL", "NFLX", "GS", "UNH"} else 1.0
            return {
                "symbol": symbol,
                "available": True,
                "price": 100.0,
                "average_20_day": 100.0,
                "change_pct": multiplier,
                "trend": "above",
            }

        with patch("trading_trainer.stock_research._fetch_market_data", side_effect=market):
            watchlist = daily_watchlist()

        self.assertEqual(len(watchlist["items"]), 5)
        self.assertEqual([item["symbol"] for item in watchlist["items"]], ["AMD", "ORCL", "NFLX", "GS", "UNH"])
        self.assertTrue(all(item["available"] for item in watchlist["items"]))
        self.assertTrue(all("strongest current price signal" in item["reason"] for item in watchlist["items"]))
