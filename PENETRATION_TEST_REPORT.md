# Trading Trainer Order-Integrity Penetration Test

**Assessment date:** 2026-09-17  
**Overall risk:** High  
**Scope:** Local dashboard API, manual paper orders, Webull sandbox order routing, market-data ingestion, risk controls, persistence, and audit history.

## Executive summary

The application should not be connected to a real-money broker in its current form. The present implementation intentionally uses Webull sandbox routing and retains a disabled live-broker stub, which limits immediate impact to sandbox orders, the local paper ledger, training results, and promotion decisions. Those controls are valuable, but the order-integrity boundary is not yet suitable for live execution.

The assessment confirmed nine issues. The most important are:

1. Any process or browser able to reach the dashboard can submit orders or change trading controls without authentication.
2. Manual orders use a client-supplied price for risk approval and execution, allowing false fills and risk-limit bypass.
3. The manual-approval control does not apply to manual-order submissions.
4. Non-finite numbers such as `NaN` pass validation and can corrupt in-memory account state.
5. Broker acknowledgement is not reconciled with broker execution; even a rejected acknowledgement can produce a local fill.
6. Stale or duplicated daily market data can reach the sandbox order adapter without freshness checks.
7. Replayed requests create duplicate fills because there is no idempotency key.
8. The SQLite ledger and audit records have no tamper-evident integrity protection.
9. The unauthenticated dashboard exposes account metadata, order history, logs, and the live-override phrase.

## Method and safety constraints

The review combined source inspection with the non-destructive harness at [`security/order_integrity_pentest.py`](security/order_integrity_pentest.py). Every dynamic mutation used a new `TemporaryDirectory`; the harness did not read the repository `.env`, touch `.data`, start the HTTP server, access the network, or call Webull.

The existing unit suite also passed: 25 tests, 0 failures. This means the findings are gaps in the current security requirements rather than regressions detected by the existing tests.

Run the isolated reproduction from the repository root with an available Python 3.11+ interpreter:

```powershell
python security/order_integrity_pentest.py
```

Expected vulnerable-state indicators:

```json
{
  "client_price_accepted": true,
  "client_price_position_quantity": 1000000,
  "manual_approval_bypassed": true,
  "nan_corrupted_in_memory_cash": true,
  "nan_error_after_mutation": "IntegrityError",
  "rejected_broker_ack_still_created_internal_fill": true,
  "replay_created_trade_count": 2,
  "stale_2000_bar_reached_order_adapter": true,
  "temporary_workspace_only": true,
  "unsigned_database_cash_after_reload": 999999999.0
}
```

## Findings

### TT-01 — State-changing trading APIs have no authentication or request-origin protection

**Severity:** High now; Critical if a live broker adapter is enabled  
**Relevant weaknesses:** CWE-306, CWE-352

`DashboardHandler.do_POST` accepts settings changes, manual orders, and worker start/stop actions without authenticating an operator or authorizing an account. It also does not validate `Origin`, `Host`, `Content-Type`, or a CSRF token. Because the handler parses a JSON body regardless of content type, a malicious website can issue a browser “simple request” using `text/plain`; it does not need to read the response to cause a state change.

Evidence:

- [`app.py:100`](app.py#L100) exposes all mutating routes.
- [`app.py:112`](app.py#L112) parses the body without an authentication or origin gate.
- [`app.py:47`](app.py#L47) permits a non-loopback bind through `--host`; loopback is only the default.

Impact includes false manual orders, kill-switch changes, approval-policy changes, inflated daily limits, and starting the sandbox order worker. On a developer machine, the practical threat includes other local processes, browser-based cross-site requests, and any network peer if the service is bound beyond loopback.

**Remediation:**

- Require an authenticated operator session or short-lived bearer credential on every `/api/*` route.
- Apply role and account authorization to order, settings, and worker-control actions.
- Require a CSRF token for cookie sessions; reject untrusted `Origin`/`Referer` values.
- Enforce an exact allowed `Host` list and `Content-Type: application/json`.
- Keep the service loopback-only by default; require TLS and explicit configuration for remote access.
- Make live-order routes deny-by-default even after general dashboard authentication.

### TT-02 — Browser-supplied price controls risk approval and the simulated fill

**Severity:** High  
**Relevant weaknesses:** CWE-20, CWE-602

The manual-order API accepts `price` from the caller, uses it to construct all OHLC values, uses it for the notional and position risk checks, and then fills against that same fabricated bar.

Evidence:

- [`app.py:580`](app.py#L580) accepts the caller's price.
- [`src/trading_trainer/paper_worker.py:139`](src/trading_trainer/paper_worker.py#L139) turns that value into the market bar.
- [`src/trading_trainer/paper_worker.py:154`](src/trading_trainer/paper_worker.py#L154) uses it for risk approval.
- [`src/trading_trainer/paper_worker.py:174`](src/trading_trainer/paper_worker.py#L174) fills against the fabricated bar.

The isolated proof submitted a one-million-share AAPL order at `$0.01`. It passed the 10% order-notional and 25% position limits and produced a one-million-share paper position. This can poison fills, returns, strategy learning, and promotion results.

**Remediation:** Treat caller price as display-only. Resolve the instrument server-side and obtain a trusted quote with a provider timestamp. For a market order, calculate pre-trade risk using a conservative collar (for example, current ask plus a configured volatility/slippage buffer). For a limit order, validate both the authoritative market price and limit price. Reject excessive quote divergence and fail closed when the quote is missing or stale.

### TT-03 — Manual approval does not guard manual submissions, and safeguards are remotely mutable

**Severity:** High  
**Relevant weaknesses:** CWE-285, CWE-863

`PAPER_MANUAL_APPROVAL_REQUIRED` is checked only in the automated strategy path. `submit_manual_order` never checks it. The proof configured approval as required and still received a filled result. Separately, the unauthenticated settings endpoint can disable the kill switch, disable approval, and set an arbitrarily large daily order count.

Evidence:

- [`src/trading_trainer/paper_worker.py:92`](src/trading_trainer/paper_worker.py#L92) is the manual path and contains no approval check.
- [`src/trading_trainer/paper_worker.py:439`](src/trading_trainer/paper_worker.py#L439) applies approval only to strategy-generated orders.
- [`app.py:616`](app.py#L616) accepts mutable safety controls.
- [`app.py:625`](app.py#L625) validates only that the daily limit is positive; there is no safe upper bound.

**Remediation:** Implement a server-side order state machine: `draft -> pending_approval -> approved -> submitted -> filled/rejected`. Bind approval to a canonical order digest containing account, instrument ID, side, quantity, type, limit, authoritative quote, expiry, and request ID. Require a distinct authorized approver or step-up reauthentication for high-risk orders. Re-check the kill switch, approval, quote freshness, limits, and digest immediately before broker submission.

### TT-04 — `NaN` passes numeric validation and causes partial state corruption

**Severity:** High  
**Relevant weakness:** CWE-20

Python's JSON parser accepts non-standard `NaN` by default. `_clean_positive_float` converts the value and tests only `value <= 0`; every comparison with `NaN` is false. Risk comparisons also fail open. The broker mutates cash and positions before SQLite rejects the non-finite value, leaving in-memory state corrupted even though persistence failed.

Evidence:

- [`app.py:726`](app.py#L726) does not call `math.isfinite`.
- [`src/trading_trainer/risk.py:35`](src/trading_trainer/risk.py#L35) compares untrusted floating-point results without a finite check.
- [`src/trading_trainer/broker.py:84`](src/trading_trainer/broker.py#L84) mutates account state before durable recording.
- [`src/trading_trainer/paper_worker.py:190`](src/trading_trainer/paper_worker.py#L190) updates memory before persistence and snapshot completion.

The proof observed `IntegrityError` after the worker's cash had already become `NaN`.

**Remediation:**

- Reject JSON constants with `json.loads(..., parse_constant=...)`.
- Require `math.isfinite` for every price, OHLC value, percentage, and monetary field.
- Use `Decimal` with explicit precision and instrument tick-size rules for money.
- Validate complete order and fill objects before any state mutation.
- Make broker-state mutation and persistence atomic, or restore the prior state on any failure.

### TT-05 — Broker acknowledgement and the local fill ledger can diverge

**Severity:** High  
**Relevant weaknesses:** CWE-252, CWE-754

The Webull adapter reports `accepted=True` for every response below HTTP 400 without validating a broker business status. The worker then creates an immediate local fill from its own bar rather than waiting for a broker execution report. It does this even if a client implementation returns `accepted=False`.

Evidence:

- [`src/trading_trainer/webull_openapi.py:106`](src/trading_trainer/webull_openapi.py#L106) checks only HTTP status.
- [`src/trading_trainer/webull_openapi.py:110`](src/trading_trainer/webull_openapi.py#L110) unconditionally sets `accepted=True`.
- [`src/trading_trainer/paper_worker.py:495`](src/trading_trainer/paper_worker.py#L495) records the acknowledgement.
- [`src/trading_trainer/paper_worker.py:501`](src/trading_trainer/paper_worker.py#L501) independently simulates a fill.

The isolated proof returned an explicit rejected acknowledgement from the mocked broker client; the local ledger still recorded one trade. Real outcomes such as pending, rejected, canceled, partial fill, different fill price, or later execution will therefore diverge from the application's positions and performance history.

**Remediation:** Parse and validate the vendor's business response and broker order ID. Store submission as `submitted` or `pending`, not `filled`. Consume authenticated execution events or poll order status, record partial fills individually, and reconcile open orders, fills, cash, and positions with the broker before strategy learning or promotion calculations. Halt routing on any reconciliation mismatch.

### TT-06 — Stale, duplicate, or malformed market data can influence order creation

**Severity:** High for automated sandbox integrity; Critical if reused for live orders  
**Relevant weaknesses:** CWE-20, CWE-345

Neither ingestion nor `_process_bar` enforces maximum age, monotonic timestamps, market session, positive finite OHLC values, or `low <= open/close <= high`. The proof supplied an AAPL bar dated 2000-01-03 and it reached the order adapter.

The default public source returns daily Yahoo bars, while the worker polls every minute. The moving-average strategy appends every fetched close without deduplicating by trading date, so the same daily observation can be counted repeatedly as if it were multiple independent bars.

Evidence:

- [`src/trading_trainer/public_market_data.py:21`](src/trading_trainer/public_market_data.py#L21) returns the most recent available daily bar without an age policy.
- [`src/trading_trainer/paper_worker.py:295`](src/trading_trainer/paper_worker.py#L295) processes every successful fetch.
- [`src/trading_trainer/paper_worker.py:344`](src/trading_trainer/paper_worker.py#L344) has no freshness or schema gate before strategy evaluation.
- [`src/trading_trainer/strategy.py:31`](src/trading_trainer/strategy.py#L31) appends every close, including duplicates for the same date.

**Remediation:** Validate symbol binding, provider, sequence, timestamp, maximum age, session, finite positive values, OHLC invariants, and reasonable price-change bands. Track the last processed provider timestamp per symbol and reject duplicate or non-monotonic bars. Process daily strategies once per trading date. Before broker submission, reprice with a broker-authoritative current quote and enforce a maximum divergence collar. Use a circuit breaker and human review on data anomalies.

### TT-07 — Order requests are replayable and not idempotent

**Severity:** Medium  
**Relevant weakness:** CWE-799

The manual endpoint has no request ID, nonce, expiry, or idempotency key. Two identical submissions produce two fills. The isolated proof observed a trade count of two. The daily limit reduces default blast radius, but TT-01 allows the same caller to raise that limit.

**Remediation:** Require an `Idempotency-Key` for every order intent, store it with a canonical request hash and final response, and enforce a unique database constraint scoped to operator/account. Return the original response for an exact retry and reject key reuse with a different payload. Include a short expiry for signed approval intents, but retain executed keys long enough to cover client and network retries.

### TT-08 — Ledger and audit records are not tamper-evident

**Severity:** Medium  
**Relevant weakness:** CWE-353

The SQLite store trusts `worker_state`, snapshots, fills, decisions, logs, and memories without a signature, hash chain, external checkpoint, or broker reconciliation. The proof edited a temporary `worker_state.cash` value to `999999999`; a new worker trusted it on startup.

Evidence:

- [`src/trading_trainer/storage.py:19`](src/trading_trainer/storage.py#L19) loads account state directly.
- [`src/trading_trainer/storage.py:124`](src/trading_trainer/storage.py#L124) loads fills directly.
- [`src/trading_trainer/storage.py:247`](src/trading_trainer/storage.py#L247) loads decisions directly.

This matters because promotion and learning use the local history. A same-user process, stolen workstation session, malicious extension, or backup/restore error can silently fabricate performance and order history.

**Remediation:** Run the service under a dedicated OS identity; restrict database and `.env` ACLs; separate the dashboard from the execution service; append audit events with a hash chain or HMAC anchored in a key outside the database; periodically checkpoint to an append-only remote log; and reconcile broker-routed orders with broker records. Fail closed on verification errors.

### TT-09 — Unauthenticated dashboard discloses trading metadata and the override phrase

**Severity:** Medium  
**Relevant weakness:** CWE-200

`GET /api/dashboard` is unauthenticated and includes the Webull account ID, fills, decisions, logs, safety settings, and `LIVE_CONFIRMATION_PHRASE`. A fixed phrase returned to the caller is confirmation text, not an authentication factor.

Evidence:

- [`app.py:77`](app.py#L77) exposes the dashboard response without authentication.
- [`app.py:172`](app.py#L172) returns the account identifier.
- [`app.py:204`](app.py#L204) returns fill history.
- [`app.py:263`](app.py#L263) returns the override phrase.

**Remediation:** Authenticate read APIs, minimize returned fields, redact account identifiers, remove internal errors and broker payloads from user-facing responses, and replace the fixed phrase with step-up operator authentication plus a short-lived server challenge bound to the exact action.

## Required security regression tests

The following tests should become release gates before enabling any live adapter:

| Test | Expected result |
|---|---|
| Unauthenticated `POST /api/manual-trade` | `401` with no state change |
| Authenticated user without trader role | `403` with no state change |
| Cross-origin `text/plain` order POST | `403` with no state change |
| Caller supplies a fake reference price | Value ignored or request rejected; risk uses server quote |
| `NaN`, `Infinity`, negative, zero, or excessive numeric value | `400`; cash, positions, audit, and database unchanged |
| Approval-required order without valid approval digest | Remains pending; broker adapter not called |
| Same idempotency key and payload sent twice | One broker submission and one fill |
| Same idempotency key with changed payload | Conflict response; no new submission |
| Duplicate or non-monotonic market-data timestamp | Strategy and broker adapter not called |
| Stale or invalid OHLC bar | Circuit breaker/alert; broker adapter not called |
| Broker returns rejected or pending | No local fill |
| Broker returns partial fills | Exact partial quantities/prices recorded from execution reports |
| Broker and local positions diverge | Routing halted and operator alerted |
| Ledger row is modified offline | Integrity verification fails closed on startup |
| Concurrent settings/order requests | No lost safety-setting update or partial account mutation |

## Remediation priority

1. **Immediate:** Keep Webull in sandbox and keep the live adapter disabled. Bind the dashboard to loopback only.
2. **Before shared use:** Add authentication, authorization, origin/CSRF protections, strict JSON handling, finite-number validation, and bounded inputs.
3. **Before relying on paper results:** Replace caller prices, enforce approval on every path, add idempotency, deduplicate/freshness-check market data, and make account updates atomic.
4. **Before any live pilot:** Implement broker execution-state reconciliation, tamper-evident audit logging, independent risk checks, step-up approval, and the full regression matrix above.

## Existing controls that reduce risk

- The server defaults to `127.0.0.1`.
- Worker startup requires `WEBULL_ENV=sandbox`, a sandbox-looking host, and sandbox order routing.
- Real-money submission remains disabled by `LiveBrokerStub`.
- The Webull SDK is delegated signature and token handling.
- Risk limits, short-sale prevention, a kill switch, daily order caps, and an automated-order rate limiter exist.
- SQL values are parameterized, reducing SQL-injection risk.

These controls should be retained, but they do not compensate for the order-authenticity, pricing, reconciliation, and persistence-integrity gaps above.
