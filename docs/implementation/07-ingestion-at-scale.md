# Implementation · 07 · First Live Ingestion at Scale (M6b-2)

| | |
|---|---|
| **Status** | Evidence — a record of one dated run, not a living document |
| **Governed by** | [doc 05 Market Data](../architecture/05-market-data-architecture.md), [doc 16 Orchestration](../architecture/16-data-orchestration-and-freshness.md), [doc 11 Testing](../architecture/11-testing-strategy.md) |
| **Run** | 2026-07-30 · `make ingest` · yfinance 0.2.66 · Python 3.12.4 |
| **Reproduce** | `make ingest` (live, never CI). Per-run manifests are gitignored. |

## What this milestone was for

Every number this platform had ever produced came from synthetic or recorded data. The
engines were proven, the universe was verified, and nothing had ever been ingested. This
is the run where an investor-facing figure became a fact about a real company rather than
a demonstration that the wiring holds.

## The run

```
20 instruments · 365-day window · daily bars
INGESTED=20   EMPTY_EXPECTED=0   EMPTY_UNEXPECTED=0   FAILED=0
4,976 observations persisted · 18 bars quarantined · 6.7 s wall clock
```

Sample results computed from that data:

```
Reliance Industries Limited        -9.77 %      one-year total return
HDFC Bank Limited                 -26.04 %
ITC Limited                       -26.91 %
Nippon India ETF Nifty 50 BeES     -2.34 %
Apple Inc.                        +60.71 %

Portfolio — equal-weight Reliance / HDFC Bank / ITC / Bharti Airtel, rf 7 %
  total return          -15.47 %      annualized volatility   13.57 %
  annualized return     -15.70 %      Sharpe                  -1.67
  overlapping observations  248       volatility rel. std. err.  4.5 %
```

**These numbers are single-vendor.** Their *math* is proven by property tests and
independent reference implementations; their *data* is trusted from one source. Doc 05
finding 7's caveat stands, and cross-source corroboration remains a Phase 5 concern.

## What the run cost us, and what it bought

Two defects were found that no amount of hermetic testing would have surfaced, because
both live in the gap between what a vendor documents and what it does. Both are recorded
in full in [doc 05](05-provider-observations.md) findings 12 and 13.

**The window meant something else.** `period="365d"` returns 365 *bars* — 537 calendar
days — not 365 days. The first batch ingested ~18 months of history while believing it
had asked for one year. Nothing looks wrong about more data than you requested, which is
why it was caught by arithmetic (NSE trades ~250 days a year, so 365 daily bars in a year
is impossible) rather than by observation.

**The gate could not see NaN.** The vendor returns an all-NaN bar for the current,
still-open session. Every check in the fail-closed gate was a comparison, and every
comparison against NaN is False, so the bar passed untouched, stored as a valid
`Decimal("NaN")`, and produced `one_year_return(reliance) → AVAILABLE, value NaN`.

That second one is worth dwelling on. It was not a gap in coverage — the gate had tests,
and they passed. It was a gap in *kind*: a validation suite assembled from comparisons
has a blind spot exactly the size of NaN, and adding more comparisons never closes it.
The fix is at two levels, because the two do different jobs: the L3 gate **handles** the
bad value (quarantine with a true reason, retained for triage), and the quantity types
**refuse** it at construction, so any future path that bypasses the gate fails loudly
rather than silently emitting a number-shaped non-number.

## What the run confirmed

- **Effective-dated versioning works under real re-ingestion.** A second live fetch of the
  same window writes a new row per bar — a different `knowledge_time`, which is a genuine
  new knowledge event, not a duplicate. The feature layer resolves 500 stored rows back to
  250 series points, one per trading day. The version axis behaves as doc 04/07 specify.
- **Rate limiting did not appear at this scale.** 20 instruments sequentially in 6.7 s,
  plus ~80 identity probes during M6b-1, with no throttling. This strengthens
  [ED-015](01-engineering-decisions.md#ed-015--skeleton-orchestration--stdlib-dag-orchestrator-product-deferred)'s
  deferral of retry/backoff, and it remains evidence rather than a guarantee — 20 polite
  requests is not 200.
- **The gate is balanced, not merely strict.** 4,976 real bars accepted, 18 refused, and
  every refusal was the genuinely defective current-session bar. A gate that quarantined
  legitimate market history would be safe and useless.
- **Recompute-from-raw still holds** at ~0.012 s, byte-identical.

## Deliberate limits of this run

- **`EMPTY_EXPECTED` and `EMPTY_UNEXPECTED` were not exercised live** — every instrument
  returned data, which is the outcome we wanted and also means the classification is
  proven only by hermetic tests, not by a real silence. It will first be exercised in
  anger by a delisting or a rename.
- **The empty/expected split rests on window width alone.** No trading calendar exists yet
  (doc 04 names it as a canonical entity), so the classifier cannot say "the venue was
  shut." Named in the code as a declared heuristic, not dressed up as a fact.
- **Raw payloads and run manifests are not committed.** Bulk vendor data is the
  redistribution question [PROJECT_CONTEXT](../PROJECT_CONTEXT.md) open item 1 defers to a
  Licensing Strategy discussion; committing 5,000 bars of it would prejudge that by
  accident.
- **One provider, one venue's conventions, one working day.** Nothing here says what
  happens across a corporate action, a trading halt, or a vendor outage.
