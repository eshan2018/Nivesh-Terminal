# Implementation · 02 · Methodology Catalog

| | |
|---|---|
| **Status** | Living — implementation tier (established in M1; populated from M3) |
| **Owner** | Quantitative Systems Architect / implementing engineer |
| **Governed by** | Architecture v2.0 — [doc 08 Analytics Framework](../architecture/08-analytics-framework.md) |

## Purpose
The versioned, user-facing home for **every feature definition and analytics formula** the
platform ships — definition, assumptions, references, known limitations, and `formula_version`.
Doc 08 requires this catalog to exist; it is a compliance artifact (doc 14 — "quantitative,
not advice") and the raw material for the explainability "why?" panel.

## Rules (from doc 08 / doc 11)
1. **Every feature and formula has an entry** with a `version`. Changing a formula is a **new
   version**, never a silent edit.
2. **Golden-master provenance ([doc 11](../architecture/11-testing-strategy.md), B10):** a formula's first golden test is seeded
   **only after** it passes property-based tests and parity with an independent reference
   implementation. A golden must never enshrine a first-write bug.
3. **Determinism:** entries state any seed/parameters so results are reproducible ([doc 08](../architecture/08-analytics-framework.md)).
4. **Limitations are mandatory**, not optional — the honest boundary of each metric.
5. **Every entry names its investor question.** Nivesh Terminal is portfolio *intelligence*,
   not a formula library: each engine exists to answer something an investor actually asks
   ("How healthy is my portfolio?", "What risk am I taking?", "Can I trust this number?").
   An entry that cannot name its question is a candidate for deletion, not documentation.

## Entry template
```markdown
### <feature-or-formula-id> · v<N>
- **Kind:** feature (L6) | engine formula (L7)
- **Investor question:** the question a real investor is asking that this answers. An
  engine that answers none does not ship — a formula existing is not a reason to build it.
- **Definition:** the precise computation, in words + notation.
- **Inputs:** canonical entities / features consumed (with units).
- **Output:** value + unit/currency (or ratio); AnalyticResult envelope fields populated.
- **Assumptions:** what must hold for the result to be meaningful.
- **Limitations:** where it misleads; what it is NOT.
- **References:** sources for the method.
- **Determinism:** seeds/params, if any.
- **Tests:** reference values, property tests, reference-impl parity (doc 11).
```

## Catalog

### close_price_series · v1
- **Kind:** feature (L6) — `backend/features/returns.py`
- **Version string:** `close-price-series/v1`
- **Definition:** For an instrument, an interval, and a knowledge cutoff `as_of`, the ordered
  sequence of `(event_time, close)` pairs drawn from the canonical `PriceObservation`s that were
  known at `as_of`. An observation is admitted only if **both** `event_time ≤ as_of` **and**
  `knowledge_time ≤ as_of`. Points are ordered by `event_time`, ascending.
- **Inputs:** `PriceObservation.close` — `Money(Decimal, currency)` for equities,
  `IndexLevel(Decimal)` (unitless points) for indices — read through `MarketDataRepository`.
- **Output:** `ClosePriceSeries`; each `PricePoint.price` is a `float`. The lineage
  `FeatureRef` pins the feature version, every observation consumed, **and the parameters the
  feature was called with** (`interval`), so the invocation is reproducible and a daily series is
  distinguishable from a weekly one.
- **Unknown instrument:** raises `UnknownInstrument` rather than returning an empty series. A
  mistyped identifier and a known instrument with no data are different answers to "why is this
  blank?", and only the second is an `Unavailable`.
- **The C3 seam:** this feature performs the platform's **single, one-way decimal→float
  conversion**, in `returns.to_float`. Money is exact `Decimal` at rest, in the domain and at the
  API; it becomes `float` here, once, for statistical consumption. There is deliberately no
  inverse — converting a statistical float back into money is forbidden (doc 04 / ADR-0016).
- **Assumptions:**
  1. `close` is the **adjusted** close. The provider is fetched with `auto_adjust=True`
     (`backend/providers/yfinance/adapter.py`), so splits and dividends are already reflected in
     the series by the vendor.
  2. All observations for an instrument share a reference-data snapshot version.
- **Limitations:**
  1. **Adjustment is inherited, not verified.** The platform does not compute its own corporate
     -action adjustment — `CorporateAction` is not an ingested data class in the skeleton — so
     the series trusts the vendor's adjustment. A provider change, or `auto_adjust=False`, would
     silently change the meaning of `close` without changing this feature's version. The
     canonical model also has no distinct `adjusted_close` field to make the distinction
     explicit; adding one is Phase 1 model-hardening work.
  2. **The as-of filter sits above a latest-version read.** The repository returns the latest
     version of each bar (as-of query machinery is deferred to Phase 6, doc 04). If a bar was
     later corrected and that correction's `knowledge_time` is after `as_of`, the bar is dropped
     rather than falling back to the version known at the time. That is fail-closed — absence
     rather than a value we could not have seen — but narrower than a true as-of read.
  3. Mixed reference-snapshot versions across observations are flagged
     (`reference-version-drift`), not reconciled.
- **Determinism:** pure given `(repository contents, instrument_id, interval, as_of)`. No clock,
  no randomness. `as_of` is an explicit input (principle 11).
- **Tests:** `backend/tests/features/test_returns.py` — seam conversion in both price types and
  the absence of an inverse; the lookahead filter on both time axes; lineage completeness and
  the exclusion of filtered-out observations; version pinning; drift flagging.

### one-year-total-return · v1
- **Kind:** engine formula (L7) — `backend/analytics/one_year_return.py`
- **Version string:** `one-year-total-return/v1`
- **Definition:** Let `S` be a `close_price_series` evaluated at `as_of`, with at least two
  points. Let `P_end` be the last point and `t_end` its `event_time`. Let the target be
  `t_target = t_end − 365 calendar days`, and let `P_start` be the point of `S` whose
  `event_time` is nearest `t_target`, ties resolving to the **earlier** bar. If
  `|event_time(P_start) − t_target| > 7 days`, the metric is `Unavailable`. Otherwise:

  > **one_year_return = (P_end / P_start) − 1**

  The result is a unitless `Ratio`, unrounded.
- **Inputs:** the `close_price_series` feature (L6). **No repository access** — engines consume
  features and other engines' results only (doc 08 / ADR-0014), enforced by the CI dependency
  lint.
- **Output:** `AnalyticResult` with `value: Ratio`, `formula_version`, `reference_version`,
  `as_of`, `computed_at`, `quality_flags`, and a `LineageHandle` resolving to the feature
  version → the observations consumed → their raw object keys, provider and contract version.
- **Assumptions:**
  1. A **365-calendar-day** window, not a 252-trading-day one, so the window means the same
     thing across exchanges with different holiday calendars.
  2. The nearest bar within **7 calendar days** of the target is an acceptable anchor. Seven
     days spans the longest ordinary closure on the exchanges in scope, and accommodates weekly
     bars (worst-case distance 3.5 days).
  3. Prices are adjusted (inherited from the feature's assumption 1), so the figure is a **total**
     return including dividends, not a price return.
  4. The series is denominated in a single currency throughout the window.
- **Limitations:**
  1. **It is a point-to-point return, not an annualized or risk-adjusted one.** It says nothing
     about the path, the drawdown, or the volatility between the two dates.
  2. **The anchor is approximate whenever the target date has no bar.** The actual offset is
     published as a `anchor-offset-days:N` quality flag; a non-zero offset means a window
     slightly longer or shorter than a year was measured. Ignoring that flag overstates precision.
  3. **No currency conversion is applied or needed** — a ratio is FX-invariant — but comparing
     this metric across instruments in different currencies compares *local* returns, which is
     not the same as an investor's realized return after FX.
  4. **Vendor-adjusted inputs** (feature limitation 1) mean an adjustment error at the provider
     propagates here undetected.
  5. **Not advice.** A quantitative measure of past price change; it has no predictive claim
     (doc 14).
- **Unavailable reasons** (a missing input is never zero — principle 13). The reason is shown to
  the user in place of the number, so each names a distinct, actionable condition:
  | Reason | Condition |
  |---|---|
  | `no-observations-available-at-as-of` | The series is empty at the knowledge cutoff. |
  | `insufficient-history-for-a-one-year-window` | Fewer than two points, **or** the earliest bar is later than `t_target + 7 days` — the history does not reach back a year. The common case for a newly listed instrument or a short backfill. |
  | `no-observation-within-tolerance-of-the-one-year-anchor` | The history *does* reach back far enough, but there is a gap where the anchor belongs. |
  | `anchor-price-is-zero-so-the-return-is-undefined` | Division by zero (the prototype's `safe_div` discipline). |
- **References:** the prototype's `shared/calculations.py::get_return` is the **reference for the
  shape** of this calculation, ported behind the engine contract rather than lifted (ADR-0014).
  Three deliberate differences: the anchor tolerance is tightened from 45 days to 7 (a 45-day
  error on the anchor is a materially different metric); the result is an unrounded ratio rather
  than a percentage rounded to 2dp, because rounding is presentation and belongs at the API edge;
  and the answer arrives in a traced envelope instead of as a bare float.
- **Determinism:** pure. No I/O, no clock, no randomness, therefore no seed. `as_of` arrives on
  the feature and `computed_at` is an explicit argument. Same inputs + same versions ⇒
  bit-identical output.
- **Tests:** `backend/tests/analytics/`
  - *Reference values:* ±20% over an exact year; the unitless-ness of an index vs an equity; an
    off-target anchor and its flag.
  - *Property-based* (hypothesis, `derandomize=True`): a flat series returns exactly zero;
    **currency-scale invariance** (the property guarding the C3 seam); the return is bounded
    below by −1; raising the final price raises the return; determinism.
  - *Independent reference implementation:* `reference_implementation.py` — `Decimal` arithmetic
    straight from the canonical amounts (bypassing the seam) and an outward day-by-day anchor
    search against a time-keyed map, rather than the engine's float arithmetic and global
    minimum-distance scan. Parity asserted on value **and on availability**.
  - *Numeric tolerance policy:* **money compares exactly**; **ratios within a relative 1e-12**.
    Observed divergence between the two implementations on the golden fixture is **3.5e-15**, so
    the tolerance carries ~2.5 orders of magnitude of headroom over measured reality while
    remaining far tighter than any real methodology error (a one-day anchor shift moves the
    answer by basis points).

#### Golden-master seeding record (doc 11 B10 — governed provenance)
| | |
|---|---|
| **Golden** | `backend/tests/analytics/golden/one_year_return_v1.json` |
| **Seeded** | 2026-07-18, during M3 |
| **Procedure** | 1. Property tests and reference-implementation parity written and run **first**. 2. Suite green (27 tests) with **no golden present**. 3. Engine output on the fixed 400-bar fixture cross-checked against the independent reference implementation: relative difference **3.5e-15**, inside the 1e-12 policy. 4. Only then was the golden written, from the code that had passed. |
| **Guards** | Unintended methodology drift — the anchor rule, tolerance, tie-break, and envelope shape. Not correctness; the tests above own that. |
| **Change rule** | Changing the golden requires a `formula_version` bump and review. Editing the values to match new output without one is the failure mode B10 exists to prevent. |


### return_series · v1
- **Kind:** feature (L6) — `backend/features/portfolio_returns.py`
- **Investor question:** *(enabling)* — not user-facing on its own; it is the input every
  risk statistic needs, because risk is a property of changes, not of price levels.
- **Version string:** `return-series/v1`
- **Definition:** From a `close_price_series`, the simple period return
  `r_t = (P_t / P_{t-1}) − 1` for each consecutive pair. N prices yield N−1 returns; each
  return is dated by the period **end**.
- **Inputs:** `close_price_series/v1` (already past the C3 decimal→float seam).
- **Output:** `ReturnSeries` — unitless floats, versioned, lineage-carrying.
- **Assumptions:** consecutive observations represent consecutive trading periods; the
  price series is adjusted (inherited from `close_price_series`).
- **Limitations:**
  1. **Simple, not log returns.** Simple returns aggregate correctly *across holdings* in
     a portfolio, which is what this feeds; log returns aggregate correctly across *time*.
     Using simple returns means the compounding step is explicit rather than additive.
  2. A zero price makes a return undefined; that period is dropped and flagged
     (`undefined-return-zero-denominator`) rather than reported as a number. The validation
     gate rejects non-positive prices, so this guards a regression rather than normal data.
- **Determinism:** pure given the price series. No clock, no randomness.
- **Tests:** `backend/tests/features/test_portfolio_returns.py`.

### aligned_return_matrix · v1
- **Kind:** feature (L6) — `backend/features/portfolio_returns.py`
- **Investor question:** *(enabling)* — "are these holdings even comparable over the same
  period?" Getting this wrong is the quietest way to publish a wrong risk number.
- **Version string:** `aligned-return-matrix/v1`
- **Definition:** For N instruments, the return series of each restricted to the dates
  present in **every** series (set intersection), ordered ascending. Column *i* corresponds
  to instrument *i*; every column has exactly the length of the aligned date vector.
- **Output:** `AlignedReturnMatrix`, carrying its effective window and one `FeatureRef`
  per holding.
- **Assumptions:** a date present for every holding represents the same trading session.
- **Limitations:**
  1. **Intersection, never fill.** Forward-filling, zero-filling or interpolating a missing
     date would invent a return that never happened and would flow into volatility and
     correlation undetected — understating risk. The date is dropped for all holdings
     instead, and `window-shortened-by-alignment` is flagged when that discards data.
  2. **A short-history holding shortens the whole window.** Adding a recently listed stock
     to a long-established portfolio measures every holding over the newcomer's brief life.
     That is visible in the published window and observation count, not hidden.
  3. No survivorship handling: a delisted instrument simply has no later observations.
- **Determinism:** pure given the repository contents and `as_of`.
- **Tests:** as above — alignment has the largest share of them, deliberately.

### portfolio-risk-return · v1
- **Kind:** engine formula (L7) — `backend/analytics/portfolio_risk_return.py`
- **Investor question:** **"How has my portfolio performed, and how much risk did I take to
  get there?"** Four individual return figures do not tell an investor whether the whole was
  steady or violent, or whether the return justified the ride.
- **Version string:** `portfolio-risk-return/v1`
- **Definition:** Given an aligned return matrix, weights `w` summing to 1, and an
  annualized risk-free rate `rf`:

  > **portfolio period return** `r_p,t = Σ_i w_i · r_i,t`
  > **total return** `Π_t (1 + r_p,t) − 1`
  > **annualized return** `(1 + total)^(periods/n) − 1`  *(geometric / CAGR)*
  > **annualized volatility** `stdev(r_p, sample n−1) × √periods`
  > **Sharpe** `(annualized return − rf) / annualized volatility`

  `periods` = 252 for daily bars, 52 for weekly.
- **Inputs:** `aligned_return_matrix/v1` + explicit parameters (weights, `rf`). **No
  repository access** (doc 08 / ADR-0014).
- **Output:** `AnalyticResult` whose **value is the total return**; annualized return,
  volatility, Sharpe and the confidence figures travel as typed `diagnostics` (ED-013), and
  the weights, `rf` and effective window are pinned in `lineage.parameters` (ED-016).
- **Assumptions:**
  1. **Fixed weights (continuously rebalanced).** The portfolio is assumed held at constant
     weights throughout the window.
  2. Returns are treated as a sample of a stationary process for the volatility estimate.
  3. `rf` is annualized, supplied by the caller, and recorded — the platform does not
     invent one.
- **Limitations:**
  1. **A real buy-and-hold portfolio drifts from its weights.** As holdings move, actual
     weights diverge from the stated ones; this measures the rebalanced portfolio, which
     will differ — sometimes materially — from an untouched one.
  2. **Volatility is backward-looking** and is not a forecast. Its own imprecision is
     published as `volatility_relative_standard_error`.
  3. **Sharpe is undefined at zero volatility** and is then omitted, with the flag
     `sharpe-undefined-zero-volatility` — never reported as 0.0.
  4. **No short positions** (negative weights refused) and **no mixed currencies** (refused
     pending `FXRate`): weighting local-currency returns across currencies silently omits
     the exchange-rate move, often the larger effect.
  5. **Equities and ETFs only.** An index is not ownable; treating one as a holding would
     report the index's movement while omitting the fees and tracking error of the fund an
     investor actually holds.
  6. **Not advice**, and not a forecast (doc 14).
- **Refusal reasons** (absence with a reason, never a fabricated number — principle 13):
  | Reason | Condition |
  |---|---|
  | `no-holdings-supplied` | Empty portfolio. |
  | `weights-do-not-match-holdings` | Weight/holding/reference counts disagree. |
  | `weights-must-sum-to-one` | Sum outside 1 ± 1e-6. Never silently renormalized. |
  | `negative-weights-unsupported-no-short-positions` | Any weight < 0. |
  | `mixed-currency-portfolio-unsupported-pending-fx-data` | More than one currency. |
  | `portfolio-supports-equities-and-etfs-only` | Any holding is not EQUITY or ETF. |
  | `insufficient-overlapping-history-for-a-reliable-estimate` | Fewer than 50 aligned observations (derivation below). |
  | `unsupported-interval-for-annualization` | Interval outside {1d, 1wk}. |
- **The 50-observation threshold is derived, not chosen.** For returns treated as
  independent draws, the relative standard error of a sample volatility estimate is
  ≈ `1/√(2(n−1))`. At n = 50 that is ~10.1% — a "20% volatility" reading is really 20% ± 2%.
  Below that the estimate is too imprecise to show. **It is a floor, not a guarantee:** real
  returns have fat tails and volatility clustering, so the true error is larger. That is
  precisely why the actual figure is *published* with every result — the threshold decides
  whether to answer; the published error says how far to trust the answer.
- **Confidence metadata published with every available result:** `overlapping_observations`,
  `volatility_relative_standard_error`, `periods_per_year`, `holdings_count`, plus
  `window_start`/`window_end` and the weights and `rf` in lineage parameters.
- **References:** the prototype's `compute_portfolio_frontier` / `portfolio_stats` are the
  reference for shape, **ported behind the engine contract, not lifted** (ADR-0014).
  Deliberate differences: geometric rather than mean-compounded annualization; Sharpe
  omitted rather than zeroed when undefined; explicit `rf` rather than an embedded default.
- **Determinism:** pure. No I/O, clock or randomness; `computed_at` is an explicit argument.
- **Tests:** `backend/tests/analytics/test_portfolio_risk_return.py` — reference values,
  five properties (single-holding identity, non-negative volatility, order invariance,
  determinism, diversification never adds risk), parity with an independently written
  implementation, and every refusal path.

#### Golden-master seeding record (doc 11 B10)
| | |
|---|---|
| **Golden** | `backend/tests/analytics/golden/portfolio_risk_return_v1.json` |
| **Seeded** | 2026-07-22, during M6a |
| **Procedure** | Property and parity tests written and green **first** (`make check` at 282 tests, no golden present); engine then cross-checked against the independent implementation on the golden fixture — **relative difference 0.000e+00**; only then was the golden written. |
| **Change rule** | Changing it requires a `formula_version` bump and review. |

## Change log
| Date | Change |
|------|--------|
| 2026-07-17 | Catalog established (M1, Phase 0 convention). No entries yet; first entry lands in M3. |
| 2026-07-18 | **First entries authored (M3):** `close_price_series · v1` (L6, the C3 seam) and `one-year-total-return · v1` (L7). Golden-master seeding record added after property + parity tests passed. |
| 2026-07-22 | **M6a entries added:** `return_series · v1`, `aligned_return_matrix · v1`, `portfolio-risk-return · v1`. Entry template gains a mandatory **Investor question** field — Nivesh Terminal ships portfolio intelligence, not a formula library, so an engine that answers no investor question does not ship. |
