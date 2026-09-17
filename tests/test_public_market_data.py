import json
from datetime import date
from unittest import TestCase
from unittest.mock import MagicMock, patch

from trading_trainer.models import Bar
from trading_trainer.paper_worker import PaperTradingWorker
from trading_trainer.public_market_data import fetch_yahoo_latest_bar
from trading_trainer.settings import AppSettings


class PublicMarketDataTests(TestCase):
    @patch("trading_trainer.public_market_data.urllib.request.urlopen")
    def test_fetches_latest_daily_bar_and_converts_class_share_symbol(self, mock_urlopen) -> None:
        response = MagicMock()
        response.read.return_value = json.dumps(
            {
                "chart": {
                    "result": [
                        {
                            "timestamp": [1_704_067_200, 1_704_153_600],
                            "indicators": {
                                "quote": [
                                    {
                                        "open": [350.0, 351.0],
                                        "high": [353.0, 354.0],
                                        "low": [349.0, 350.0],
                                        "close": [352.0, 353.0],
                                        "volume": [100, 125],
                                    }
                                ]
                            },
                        }
                    ]
                }
            }
        ).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = response

        bar = fetch_yahoo_latest_bar("BRK.B")

        self.assertEqual(bar.symbol, "BRK.B")
        self.assertEqual(bar.close, 353.0)
        self.assertEqual(bar.volume, 125)
        self.assertIn("BRK-B", mock_urlopen.call_args.args[0].full_url)

    @patch("trading_trainer.paper_worker.fetch_yahoo_latest_bar")
    def test_worker_uses_public_source_without_calling_webull(self, mock_fetch) -> None:
        expected = Bar("AAPL", date(2024, 1, 2), 1.0, 1.0, 1.0, 1.0, 0)
        mock_fetch.return_value = expected
        client = MagicMock()
        worker = object.__new__(PaperTradingWorker)

        result = worker._fetch_latest_bar(AppSettings(webull_paper_data_source="public_yahoo"), client, "AAPL")

        self.assertIs(result, expected)
        mock_fetch.assert_called_once_with("AAPL")
        client.fetch_latest_bar.assert_not_called()

    def test_worker_preserves_webull_source_for_subscribed_accounts(self) -> None:
        expected = Bar("AAPL", date(2024, 1, 2), 1.0, 1.0, 1.0, 1.0, 0)
        client = MagicMock()
        client.fetch_latest_bar.return_value = expected
        worker = object.__new__(PaperTradingWorker)

        result = worker._fetch_latest_bar(AppSettings(webull_paper_data_source="webull_historical"), client, "AAPL")

        self.assertIs(result, expected)
        client.fetch_latest_bar.assert_called_once_with("AAPL")
