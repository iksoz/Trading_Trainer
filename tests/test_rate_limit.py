from unittest import TestCase

from trading_trainer.rate_limit import WebullOrderRateLimiter


class WebullOrderRateLimiterTests(TestCase):
    def test_limits_shared_order_attempts_by_spacing_and_minute_window(self) -> None:
        now = [0.0]
        limiter = WebullOrderRateLimiter(clock=lambda: now[0])

        self.assertTrue(
            limiter.acquire(min_interval_seconds=10, max_orders_per_minute=2).allowed
        )
        now[0] = 5.0
        blocked = limiter.acquire(min_interval_seconds=10, max_orders_per_minute=2)
        self.assertFalse(blocked.allowed)
        self.assertEqual(blocked.retry_after_seconds, 5.0)

        now[0] = 10.0
        self.assertTrue(
            limiter.acquire(min_interval_seconds=10, max_orders_per_minute=2).allowed
        )
        now[0] = 20.0
        self.assertFalse(
            limiter.acquire(min_interval_seconds=10, max_orders_per_minute=2).allowed
        )

    def test_cooldown_blocks_new_attempts_after_a_broker_429(self) -> None:
        now = [10.0]
        limiter = WebullOrderRateLimiter(clock=lambda: now[0])
        limiter.cool_down(120)

        blocked = limiter.acquire(min_interval_seconds=1, max_orders_per_minute=10)
        self.assertFalse(blocked.allowed)
        self.assertEqual(blocked.retry_after_seconds, 120.0)
