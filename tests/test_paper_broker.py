from datetime import date
from unittest import TestCase

from trading_trainer.broker import PaperBroker
from trading_trainer.models import Bar, Order, Side


class PaperBrokerTests(TestCase):
    def test_buy_and_sell_updates_cash_and_position(self) -> None:
        broker = PaperBroker(starting_cash=1_000.0, slippage_bps=0.0)
        bar = Bar("AAPL", date(2026, 1, 1), 10.0, 10.0, 10.0, 10.0)

        buy_fill = broker.submit_order(Order("AAPL", Side.BUY, 10), bar)
        self.assertIsNotNone(buy_fill)
        self.assertEqual(broker.position("AAPL").quantity, 10)
        self.assertEqual(broker.cash, 900.0)

        sell_fill = broker.submit_order(Order("AAPL", Side.SELL, 5), bar)
        self.assertIsNotNone(sell_fill)
        self.assertEqual(broker.position("AAPL").quantity, 5)
        self.assertEqual(broker.cash, 950.0)
