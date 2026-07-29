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

### 9 · Identity metadata is available — and cross-field checking is worth doing

`Ticker.info` exposes enough to verify identity rather than mere existence:

```
RELIANCE.NS   currency INR · exchange NSI / NSE · quoteType EQUITY · isin INE002A01018
^NSEI         currency INR · exchange NSI / NSE · quoteType INDEX  · isin —
NIFTYBEES.NS  currency INR · exchange NSI / NSE · quoteType EQUITY · isin "-"
```

**Two limits worth stating.** `quoteType` distinguishes INDEX from not-INDEX, but **cannot
distinguish an ETF from an equity** — `NIFTYBEES.NS`, unambiguously an ETF, reports `EQUITY`. And
**ISIN is absent for ETFs** (a literal `"-"`). Both are the same pattern: ETF support is
consistently less vendor-corroborated than equity support. Hence [ED-017](01-engineering-decisions.md#ed-017--canonical-instrument-identity--mic-exchange-isin-and-aliases)
records ETF classification as *our own canonical knowledge*.

**A cross-field discrepancy found while probing, and left open on purpose.** `LT.NS` returns
`longName: "Larsen & Toubro Limited"` alongside `isin: INE214T01019`. That ISIN is **not obviously
L&T's** — it may belong to LTIMindtree (formerly L&T Infotech). *This has not been verified from
an authoritative source and is recorded as a question, not a finding.* Either way it demonstrates
the point exactly: **name and ISIN can disagree, and neither field alone would reveal it.** This
is the class of silent identity error M6b-1's verification exists to catch, and the concrete
reason ISIN is worth carrying — it is the only attribute that is globally unique and
machine-checkable.

### 10 · ⚠️ ISIN is **not** in `Ticker.info` — and a green report can still mean nothing

Recorded in M6b-1. `isin` is a separate `Ticker` **property**, not a key in the `.info`
dict:

```
Ticker("RELIANCE.NS").info.get("isin")  →  None
Ticker("RELIANCE.NS").isin              →  "INE002A01018"
```

The first version of `tools/verify_universe.py` read `info["isin"]`. Every instrument
therefore reported "vendor offers nothing", every ISIN check resolved to
`uncorroborated`, and **all twenty rows still came back `OK`** — a completely clean
verification report in which one of the checks had silently asked no question at all.

**This is the finding, not the typo.** A verification suite fails safe only if you can
tell the difference between "the vendor agrees" and "the vendor was never asked", and a
row-level verdict cannot show you that. It was caught by reading the detail column and
noticing that a field finding 9 had *observed working* was now universally empty. Two
consequences were adopted: the report prints every check's detail rather than a verdict
alone, and `uncorroborated` is displayed as a distinct outcome rather than folded into a
pass.

Availability also turns out to be **inconsistent across equities**, which refines finding
9's "absent for ETFs": of 20 seeded instruments, 9 returned a check-digit-valid ISIN and
11 returned the literal `"-"` — including TCS, Infosys, Axis Bank, Bharti Airtel and both
Bajaj entities. There is no evident pattern separating them.

### 11 · The `LT.NS` ISIN discrepancy reproduces

Finding 9 recorded, as an open question, that `LT.NS` returns `longName: "Larsen & Toubro
Limited"` with `isin: INE214T01019` — an identifier that may belong to LTIMindtree
rather than L&T. **The M6b-1 run reproduces it exactly**, so it is a stable vendor
behaviour rather than a transient glitch, and at least one further candidate in the same
run does not match the value we believe that company carries.

Neither value is asserted here, because we hold no authoritative source for either — and
that is the point. The vendor's ISINs are recorded as **candidates awaiting confirmation
against CDSL/NSDL or exchange listing data**, never adopted into the seed. Had M6b-1
seeded ISINs *from* the provider, this run would have verified the provider against
itself, attributed a plausible identifier to the wrong company, and passed.

## What M6b-0 deliberately did **not** change

No behavioural change to `backend/`. No adapter fix for finding 5. No universe seeding.
`yfinance` is declared only as an **optional `live` extra** — never a runtime dependency,
never installed in CI, because a network call in CI would forfeit the reproducibility
guarantee everything else rests on (doc 11).

## Change log

| Date | Change |
|------|--------|
| 2026-07-30 | Findings 10 and 11 added during M6b-1's live verification run. ISIN is a `Ticker` property, not an `.info` key — the first verifier read the wrong field and produced a fully green report in which the ISIN check asked nothing. ISIN availability is inconsistent across equities, not merely absent for ETFs. The `LT.NS` name/ISIN discrepancy reproduces stably. |
| 2026-07-24 | Finding 9 added while designing M6b-1: identity metadata probed; ISIN available for equities but not ETFs; a name/ISIN discrepancy on `LT.NS` recorded as an open question. |
| 2026-07-24 | Created in M6b-0. First live execution of the provider path in the project's history; findings 1–8 recorded, a 400-bar real payload captured as a regression fixture, and the fixture's implications pinned as contract tests. |
