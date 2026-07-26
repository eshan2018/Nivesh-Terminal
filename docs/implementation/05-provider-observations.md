# Implementation · 05 · Live Provider Observations (yfinance)

| | |
|---|---|
| **Status** | Living — implementation tier |
| **Owner** | Implementing engineer |
| **Governed by** | [doc 06 Provider Abstraction](../architecture/06-provider-abstraction-layer.md), [ADR-0005](../architecture/18-architecture-decision-records.md#adr-0005--provider-abstraction-via-portsadapters), [doc 11 Testing](../architecture/11-testing-strategy.md) |
| **Recorded** | M6b-0, 2026-07-24 · yfinance 0.2.66 · Python 3.12.4 |
| **Re-capture** | `python -m tools.capture_provider_fixture --instrument reliance --days 400` |

## Why this document exists

**Investor framing:** before an investor can analyse the securities they actually own,
the platform has to be able to *get* those securities' prices — and it had never tried.
Every test from M2 through M6a ran on recorded or synthetic payloads. The live network
path (`_default_fetch`) had **executed zero times** in the project's history.

M6b-0 exercised it deliberately, on the smallest possible scope, so that everything
downstream is built on observed behaviour rather than assumption. Its deliverable is
knowledge and evidence: a real recorded payload, a regression fixture, these findings —
and **zero behavioural change** to `backend/`.

## Findings

### 1 · The provider needs a session handshake, not a URL

A direct HTTPS request to the chart API is refused:

```
GET query1.finance.yahoo.com/v8/finance/chart/RELIANCE.NS  →  HTTP 429 "Edge: Too Many Requests"
```

Consistently, across both `query1`/`query2` hosts, with and without a browser
`User-Agent`, while unrelated hosts (pypi.org) return 200 from the same network. The
same fetch **through `yfinance` succeeds**, because the library performs a cookie/crumb
handshake first.

**Consequence:** the vendor cannot be treated as a plain REST API. A future adapter that
"simplifies" by calling the URL directly would fail — and would fail *only in
production*, since the hermetic tests never touch the network. Recorded here because
that is a mistake a reasonable engineer could otherwise make.

### 2 · Column shape

Returned as a pandas MultiIndex — `('Close', 'RELIANCE.NS')` — which the adapter already
flattens via `get_level_values(0)`. Columns arrive **alphabetically**
(`Close, High, Low, Open, Volume`), not in OHLCV order. `validate_columns` checks
membership rather than sequence, so this passes; a pinned test now guards it, because
order-sensitive parsing would break on real data while still passing the hand-written
fixture.

### 3 · `auto_adjust=True` is genuinely applying retroactive adjustment

Over a 30-day window, adjusted and unadjusted closes were **identical** — no corporate
action occurred, so the flag appeared to do nothing. Over 400 days the difference is
visible: early closes carry many decimal places (`1234.6376953125`,
`1253.078416496042`) while recent closes are round (`1278.0`, `1265.0`).

**Consequences.**
- The methodology catalog's assumption — "`close` is the adjusted close, inherited from
  the vendor" — is now **evidenced rather than assumed**.
- Adjusted prices are **not round rupee values**; they carry the vendor's float
  precision. The platform stores them exactly as decimals, so we are *exact about a
  number that is itself a vendor computation, not a traded price*. That is honest, and
  worth stating plainly rather than implying our decimals make the price authoritative.
- A short test window can hide adjustment entirely. Provider behaviour must be probed
  over windows long enough to contain a corporate action.

### 4 · Sequential fetches are fast and were not rate-limited

Four instruments in sequence with ~1.5 s spacing: **0.22–0.32 s each, no throttling.**

**Consequence for M6b-2:** ingesting ~30 instruments looks feasible without retry,
backoff or dead-lettering — the capabilities [ED-015](01-engineering-decisions.md#ed-015--skeleton-orchestration--stdlib-dag-orchestrator-product-deferred)
deliberately deferred. **This is evidence, not a guarantee:** it was measured on four
polite requests, not thirty. If bulk ingestion is throttled, that is the concrete
trigger to revisit ED-015 — which is exactly how that ED said the decision should be
reopened.

### 5 · ⚠️ An unknown or delisted symbol returns **empty**, it does not raise

```
yf.download("NOTAREALTICKER.NS", ...)  →  empty DataFrame, no exception
```

The library logs an error, but the call succeeds. `_default_fetch` maps an empty frame
to `RawFetch(columns=EXPECTED_COLUMNS, rows=())` — a **well-formed, empty** payload.

**This is the most important risk M6b-0 surfaced.** A typo'd, renamed or delisted ticker
would ingest *silently, producing nothing*, and the failure would only surface far
downstream as "no observations available" — indistinguishable from a legitimately empty
window. That is precisely the conflation the L6 `UnknownInstrument` fix removed at the
feature layer, reappearing at the provider layer.

It is **not** a fabrication risk (we invent no data, so principle 13 holds), but it is a
silence risk, and silence across ~30 instruments is how a portfolio quietly loses a
holding. **M6b-2 must decide** whether an empty payload for a symbol the reference data
claims exists should be an explicit provider-level condition rather than an empty
success. Deliberately *not* fixed in M6b-0 — that would be a behavioural change.

### 6 · Timestamps are timezone-naive midnight

Daily bars arrive as `2026-06-15T00:00:00`, naive. Validation stamps naive timestamps as
UTC, which **preserves the trading date** because the time component is exactly midnight.

If the vendor ever emitted an offset instant instead (e.g. `18:30` for IST midnight),
every bar's date would shift by one day, silently moving every return window. A test now
pins the midnight-naive shape as a tripwire.

### 7 · The fail-closed gate accepts real market data

400 real bars → **400 accepted, 0 quarantined**, and the metric computed cleanly
(Reliance one-year return **−8.12 %**, exact anchor, no quality flags).

This matters in both directions: a fail-closed gate that quarantined legitimate market
history would be safe and useless. The balance holds on first contact with reality.

**Caveat:** the number is not independently verified against a second source. Its *math*
is proven by parity tests; its *data* is trusted from a single vendor. Cross-source
corroboration is a later phase (doc 05), and until then single-vendor trust is the
honest description of what we have.

### 8 · Provider fragility signals

`yfinance` emits pandas deprecation warnings (`Timestamp.utcnow` removal) from its own
internals. Harmless today; a reminder that the library is an **unofficial scraper of a
site that can change without notice**, not a contracted API. [ADR-0005](../architecture/18-architecture-decision-records.md#adr-0005--provider-abstraction-via-portsadapters)'s
port/adapter boundary is what makes that survivable — the fragility is contained to one
package.

## What M6b-0 deliberately did **not** change

No behavioural change to `backend/`. No adapter fix for finding 5. No universe seeding.
`yfinance` is declared only as an **optional `live` extra** — never a runtime dependency,
never installed in CI, because a network call in CI would forfeit the reproducibility
guarantee everything else rests on (doc 11).

## Change log

| Date | Change |
|------|--------|
| 2026-07-24 | Created in M6b-0. First live execution of the provider path in the project's history; findings 1–8 recorded, a 400-bar real payload captured as a regression fixture, and the fixture's implications pinned as contract tests. |
