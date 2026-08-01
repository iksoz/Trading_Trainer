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

The current Webull configuration targets sandbox paper trading with stocks and
ETFs only: `WEBULL_ALLOWED_PRODUCTS=stocks,etfs`. Market data is set to a
free-first policy so the app should use only data available under the current
OpenAPI permissions until paid quote subscriptions are intentionally added.

For Webull-only paper training, use sandbox credentials and sandbox endpoints:

```env
WEBULL_ENV=sandbox
WEBULL_API_HOST=api.sandbox.webull.com
WEBULL_TRADE_EVENTS_HOST=events-api.sandbox.webull.com
WEBULL_DATA_STREAM_HOST=data-api.sandbox.webull.com
WEBULL_SANDBOX_APP_KEY=
WEBULL_SANDBOX_APP_SECRET=
WEBULL_SANDBOX_ACCOUNT_ID_INV_CASH=
WEBULL_SANDBOX_ACCOUNT_ID_INV_MARGIN=
WEBULL_PAPER_ORDER_ROUTING=sandbox
```

Install the official Webull SDK before starting the Webull Paper worker:

```powershell
python -m pip install -e .[webull]
```

The dashboard exposes separate Webull Paper panels for the individual cash and
individual margin sandbox accounts. Each account starts its own background
worker with an isolated paper ledger, pulls Webull sandbox historical bars, runs
the strategy/risk checks, routes approved stock/ETF orders to that account
through the Webull sandbox Trading API, and reports account-specific metrics.

Paper history is persisted to SQLite at `PAPER_HISTORY_DB_PATH`, defaulting to
`.data/paper_history.sqlite3`. The store saves worker state, positions,
snapshots, fills, and logs so a dashboard restart can keep the paper history
available.

The dashboard Strategies tab can switch between the 5/20 moving-average
strategy and a top-holdings shadow strategy based on Trendlyne's US Superstar
portfolio table. The seeded shadow portfolios include Warren Buffett, Ken
Fisher, Bill Gates, Ray Dalio, Catherine Wood, and Bill Ackman, using the top
holdings exposed on the Trendlyne page as the tracked symbols.

The gear button beside the language switch opens a single status page for
dashboard health, dependency checks, worker errors, broker controls, learner
recommendations, and the decision journal.

The first agentic-learning foundation is deliberately audit-first:

- unsupported symbols are skipped and logged instead of stopping the worker;
- sandbox fallback symbols from `WEBULL_PAPER_FALLBACK_SYMBOLS` are appended so
  a limited Webull sandbox universe can still produce paper snapshots;
- every hold, skip, risk rejection, manual-review queue, and fill is written to
  the SQLite decision journal;
- the evaluator reports return, drawdown, volatility, win rate, risk
  rejections, and decision counts;
- the learner proposes recommendations without applying them automatically;
- policy state can halt, require manual approval, enforce a daily paper order
  limit, or allow autonomous paper routing;
- broker controls are configured with `PAPER_TRADING_KILL_SWITCH`,
  `PAPER_MANUAL_APPROVAL_REQUIRED`, and `MAX_DAILY_ORDER_COUNT`.

## Project Shape

- `src/trading_trainer/models.py` - shared trading data models.
- `src/trading_trainer/broker.py` - broker protocol and paper broker.
- `src/trading_trainer/risk.py` - order and account risk checks.
- `src/trading_trainer/strategy.py` - strategy protocol and example strategy.
- `src/trading_trainer/agent.py` - agent loop that proposes and routes orders.
- `src/trading_trainer/promotion.py` - paper-to-live promotion evaluator.
- `src/trading_trainer/live.py` - intentionally disabled live broker stub.
- `src/trading_trainer/settings.py` - dependency-free `.env` settings loader.
- `src/trading_trainer/storage.py` - SQLite paper history persistence.
- `src/trading_trainer/superstar.py` - seeded Trendlyne superstar portfolio catalog.
- `src/trading_trainer/webull_openapi.py` - official Webull SDK wrapper.
- `src/trading_trainer/paper_worker.py` - Webull sandbox auto paper worker.
- `app.py` - single Python entrypoint for the dashboard and API.
- `frontend/` - React dashboard served by `app.py`.

## Broker Direction

Keep broker-specific execution behind adapters. Webull Trading API can be the
live adapter once SDK token setup, 2FA handling, account routing, order mapping,
and dashboard approval controls are verified end to end.
