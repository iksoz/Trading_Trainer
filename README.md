# Trading Trainer

Trading Trainer is an agentic paper-trading lab. The first goal is to let an
agent test strategies in a paper environment, learn from outcomes, and produce
auditable promotion reports.

The project is deliberately designed so that a profitable paper run does not
silently switch to live trading. A live transition should require explicit human
approval, fresh credentials, broker-specific integration, and risk limits.

## Guardrails

- Paper trading first, with every order checked by a risk manager.
- Promotion gates require more than a headline return.
- Live trading adapters are isolated from strategy code.
- The default live adapter is a stub and cannot place real orders.
- Credentials should only be supplied through environment variables or a secret
  manager, never committed to the repo.

## Promotion Criteria

The default promotion evaluator checks:

- At least 150 calendar days of paper-trading history.
- Total return at or above 20%.
- The final 20 trading snapshots remain at or above the return threshold.
- Maximum drawdown does not exceed the configured limit.
- Minimum trade count is reached.
- No recorded risk violations.

These gates are not proof that a system will make money live. They are a
release checklist for deciding whether the system is ready for deeper review.

## Quick Start

```powershell
python -m pip install -e .
python -m unittest discover -s tests
python app.py
```

Then open `http://127.0.0.1:8000`.

## Credentials

Local credentials live in `.env`, which is ignored by git. Use `.env.example`
as the safe template and keep `LIVE_TRADING_ENABLED=false` until the app has a
verified live adapter and an explicit operator approval.

Webull OpenAPI uses one shared `WEBULL_APP_KEY` and `WEBULL_APP_SECRET` for
Trading API and Market Data API access. Keep the app secret server-side only;
do not put it in React or any browser-delivered code.

The current Webull configuration targets production with stocks and ETFs only:
`WEBULL_ALLOWED_PRODUCTS=stocks,etfs`. Market data is set to a free-first policy
so the app should use only data available under the current OpenAPI permissions
until paid quote subscriptions are intentionally added.

## Project Shape

- `src/trading_trainer/models.py` - shared trading data models.
- `src/trading_trainer/broker.py` - broker protocol and paper broker.
- `src/trading_trainer/risk.py` - order and account risk checks.
- `src/trading_trainer/strategy.py` - strategy protocol and example strategy.
- `src/trading_trainer/agent.py` - agent loop that proposes and routes orders.
- `src/trading_trainer/promotion.py` - paper-to-live promotion evaluator.
- `src/trading_trainer/live.py` - intentionally disabled live broker stub.
- `src/trading_trainer/settings.py` - dependency-free `.env` settings loader.
- `app.py` - single Python entrypoint for the dashboard and API.
- `frontend/` - React dashboard served by `app.py`.

## Broker Direction

Keep broker-specific execution behind adapters. Webull Trading API can be the
live adapter once SDK token setup, 2FA handling, account routing, order mapping,
and dashboard approval controls are verified end to end.
