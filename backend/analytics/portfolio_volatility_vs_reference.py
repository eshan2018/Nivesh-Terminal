"""Realized volatility versus a reference index (L7, doc 08).

Catalog: `portfolio-volatility-vs-reference · v1`. The platform's **first deterministic
judgement** — a stage, not a metric with a nicer label.

**Investor question:** *"How did my portfolio's realized volatility compare with the
Nifty 50 over the same period?"*

**What this claims, and what it refuses to claim.** It compares *realized volatility* —
how much the portfolio moved — against a market reference over identical dates. It says
nothing about **risk**, which also includes concentration, liquidity, drawdown depth,
single-stock event risk and credit. "Moved more than the index" is a measurement;
"riskier than the index" is a claim this evidence cannot support, and the vocabulary here
never makes it.

**Why this judgement and not the obvious one.** The first candidate was "were you
compensated for your risk?" — return against the risk-free rate. Tested against 411 real
equal-weight portfolios over roughly a year of daily data, that verdict was
`INCONCLUSIVE` in **99.8%** of cases at 95% confidence (median |t| = 0.23). It is
statistically honest and product-useless: a judgement that is effectively constant. A
sign-only version would have labelled 64% "not compensated" with full lineage attached —
confident labels on differences indistinguishable from noise.

The reason is structural rather than incidental: **first moments are not estimable from
one year of daily data; second moments are.** A volatility estimate from ~250
observations carries roughly 4.5% relative standard error, so a volatility *comparison*
is decidable where a mean-return comparison is not — measured at 72% decisive on the same
portfolios. This engine exists because that is where the evidence actually supports a
judgement.

**The reference frame is empirical, not house convention.** The comparison is against the
market's own realized volatility over the same window — not against a band somebody chose.
The only convention is the confidence level, and it is published as a parameter.

**A deliberately conservative test.** The variance-ratio test below assumes independent
samples, while a portfolio of index constituents is strongly correlated with the index.
Positive correlation makes the true standard error *smaller*, so this understates
significance and errs toward `NOT_DISTINGUISHABLE`. That is the safe direction: the
engine will say "cannot tell" more often than a sharper test would, never less. The exact
paired test (Pitman–Morgan) is a candidate refinement, not adopted in v1.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from backend.domain.model.analytics import AnalyticResult, LineageHandle, Verdict
from backend.domain.model.quantities import Ratio
from backend.features.portfolio_returns import (
    MIN_OVERLAP_OBSERVATIONS,
    AlignedReturnMatrix,
    ReturnSeries,
)
from backend.platform.identifiers import InstrumentId

METRIC_ID = "portfolio_volatility_vs_reference"
FORMULA_VERSION = "portfolio-volatility-vs-reference/v1"

#: Trading periods per year, matching the evidence engine's annualization.
PERIODS_PER_YEAR = {"1d": 252, "1wk": 52}

#: The confidence level at which a difference is called. **This is the one convention in
#: the method** — everything else (the ratio, the standard error, the boundary at "equal
#: volatility") is computed or definitional. Published as an invocation parameter so a
#: reader can see the choice rather than infer it.
CONFIDENCE_Z = 1.96
CONFIDENCE_LABEL = "95%"

# Refusal reasons — shown to an investor in place of a verdict, so each is specific.
NO_HOLDINGS = "no-holdings-supplied"
INSUFFICIENT_OVERLAP = "insufficient-overlapping-history-for-a-reliable-estimate"
REFERENCE_UNAVAILABLE = "no-reference-history-over-the-portfolio-window"
WINDOWS_NOT_ALIGNED = "portfolio-and-reference-windows-do-not-match"
UNSUPPORTED_INTERVAL = "unsupported-interval-for-annualization"
ZERO_REFERENCE_VOLATILITY = "reference-volatility-is-zero-so-a-ratio-does-not-exist"

# Diagnostics (ED-013): typed numbers, never parsed out of flag strings.
VOLATILITY_RATIO = "volatility_ratio"
PORTFOLIO_VOLATILITY = "portfolio_annualized_volatility"
REFERENCE_VOLATILITY = "reference_annualized_volatility"
RATIO_CI_LOW = "volatility_ratio_ci_low"
RATIO_CI_HIGH = "volatility_ratio_ci_high"
Z_STATISTIC = "z_statistic"
PORTFOLIO_OBSERVATIONS = "portfolio_observations"
REFERENCE_OBSERVATIONS = "reference_observations"


@dataclass(frozen=True, slots=True)
class VolatilityComparison:
    """The reasoning stage, exposed so it can be tested without an envelope."""

    ratio: float
    z: float
    ci_low: float
    ci_high: float
    verdict: Verdict


def annualized_volatility(returns: Sequence[float], periods_per_year: int) -> float:
    """Sample standard deviation of periodic returns, annualized by √periods."""
    n = len(returns)
    mean = sum(returns) / n
    variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
    return math.sqrt(variance) * math.sqrt(periods_per_year)


def compare(
    portfolio_volatility: float,
    reference_volatility: float,
    *,
    portfolio_observations: int,
    reference_observations: int,
    z_threshold: float = CONFIDENCE_Z,
) -> VolatilityComparison:
    """Compare two realized volatilities and say whether they are distinguishable. Pure.

    Tests the *variance* ratio on a log scale, where the sampling distribution is
    roughly symmetric, then reports the interval back on the volatility-ratio scale an
    investor can read ("1.2× as much"). The boundary is a ratio of 1 — equal volatility —
    which is definitional, not chosen.
    """
    ratio = portfolio_volatility / reference_volatility
    standard_error = math.sqrt(
        2.0 / (portfolio_observations - 1) + 2.0 / (reference_observations - 1)
    )
    # log of the VARIANCE ratio = 2 * log of the volatility ratio.
    z = (2.0 * math.log(ratio)) / standard_error

    # Back to the volatility scale: halve the log-variance interval before exponentiating.
    half_width = z_threshold * standard_error / 2.0
    ci_low = ratio * math.exp(-half_width)
    ci_high = ratio * math.exp(half_width)

    if z >= z_threshold:
        verdict = Verdict.HIGHER_REALIZED_VOLATILITY
    elif z <= -z_threshold:
        verdict = Verdict.LOWER_REALIZED_VOLATILITY
    else:
        verdict = Verdict.NOT_DISTINGUISHABLE

    return VolatilityComparison(ratio=ratio, z=z, ci_low=ci_low, ci_high=ci_high, verdict=verdict)


def portfolio_volatility_vs_reference(
    matrix: AlignedReturnMatrix,
    weights: Sequence[float],
    reference: ReturnSeries,
    *,
    computed_at: datetime,
    z_threshold: float = CONFIDENCE_Z,
) -> AnalyticResult:
    """Judge the portfolio's realized volatility against the reference's.

    Consumes features and another engine's shape — never a repository (doc 08). The
    reference arrives already aligned to the portfolio's dates by
    `aligned-reference-return-series/v1`; this engine verifies that alignment rather
    than assuming it, because a comparison over mismatched windows answers a different
    question while looking identical.
    """
    if computed_at.tzinfo is None:
        raise ValueError("computed_at must be timezone-aware")

    portfolio_id = InstrumentId("portfolio")
    lineage = LineageHandle(features=(*matrix.lineage, reference.lineage))
    flags = set(matrix.quality_flags) | set(reference.quality_flags)

    def unavailable(reason: str) -> AnalyticResult:
        return AnalyticResult.unavailable(
            metric_id=METRIC_ID,
            instrument_id=portfolio_id,
            reason=reason,
            formula_version=FORMULA_VERSION,
            reference_version=matrix.reference_version,
            as_of=matrix.as_of,
            computed_at=computed_at,
            quality_flags=tuple(sorted(flags)),
            lineage=lineage,
        )

    if not weights or len(weights) != len(matrix.instrument_ids):
        return unavailable(NO_HOLDINGS)
    if matrix.interval not in PERIODS_PER_YEAR:
        return unavailable(UNSUPPORTED_INTERVAL)
    if matrix.observation_count < MIN_OVERLAP_OBSERVATIONS:
        return unavailable(INSUFFICIENT_OVERLAP)
    if len(reference.points) < MIN_OVERLAP_OBSERVATIONS:
        return unavailable(REFERENCE_UNAVAILABLE)
    # Like-for-like or nothing: same count AND the same dates, checked not trusted.
    if len(reference.points) != matrix.observation_count or tuple(
        point.event_time for point in reference.points
    ) != matrix.dates:
        return unavailable(WINDOWS_NOT_ALIGNED)

    periods = PERIODS_PER_YEAR[matrix.interval]
    portfolio_returns = [
        sum(w * column[i] for w, column in zip(weights, matrix.columns, strict=True))
        for i in range(matrix.observation_count)
    ]
    portfolio_vol = annualized_volatility(portfolio_returns, periods)
    reference_vol = annualized_volatility([p.value for p in reference.points], periods)

    # A flat reference has no ratio — absence, not a fabricated number (principle 13).
    if reference_vol == 0.0 or portfolio_vol == 0.0:
        return unavailable(ZERO_REFERENCE_VOLATILITY)

    comparison = compare(
        portfolio_vol,
        reference_vol,
        portfolio_observations=matrix.observation_count,
        reference_observations=len(reference.points),
        z_threshold=z_threshold,
    )

    return AnalyticResult.available(
        metric_id=METRIC_ID,
        instrument_id=portfolio_id,
        # The quantity the verdict is about travels with the verdict, so a reader can
        # always check one against the other (ED-021).
        value=Ratio(comparison.ratio),
        verdict=comparison.verdict,
        formula_version=FORMULA_VERSION,
        reference_version=matrix.reference_version,
        as_of=matrix.as_of,
        computed_at=computed_at,
        quality_flags=tuple(sorted(flags)),
        diagnostics=(
            (VOLATILITY_RATIO, comparison.ratio),
            (PORTFOLIO_VOLATILITY, portfolio_vol),
            (REFERENCE_VOLATILITY, reference_vol),
            (RATIO_CI_LOW, comparison.ci_low),
            (RATIO_CI_HIGH, comparison.ci_high),
            (Z_STATISTIC, comparison.z),
            (PORTFOLIO_OBSERVATIONS, float(matrix.observation_count)),
            (REFERENCE_OBSERVATIONS, float(len(reference.points))),
        ),
        lineage=LineageHandle(
            features=(*matrix.lineage, reference.lineage),
            parameters=(
                ("confidence_level", CONFIDENCE_LABEL),
                ("interval", matrix.interval),
                ("reference_instrument", reference.instrument_id.value),
                ("weights", ",".join(repr(w) for w in weights)),
                ("z_threshold", repr(z_threshold)),
            ),
        ),
    )


def portfolio_volatility_vs_reference_for(
    holdings: Sequence[tuple[InstrumentId, float]],
    matrix_provider: Callable[[Sequence[InstrumentId], datetime], AlignedReturnMatrix],
    reference_provider: Callable[[InstrumentId, Sequence[datetime], datetime], ReturnSeries],
    *,
    reference_id: InstrumentId,
    as_of: datetime,
    computed_at: datetime,
) -> AnalyticResult:
    """Assemble the features this judgement needs and run it (ED-011).

    The entry point hands over bound providers; the assembly — splitting holdings into
    instruments and weights, aligning the reference to the portfolio's own dates — is
    analytics work and lives here rather than in the composition root, which admits no
    control flow.
    """
    instrument_ids = [instrument_id for instrument_id, _ in holdings]
    weights = [weight for _, weight in holdings]

    # Two passes, because the intersection runs both ways. The reference does not trade
    # on exactly the holdings' calendar, so aligning it to the portfolio leaves it
    # shorter; the portfolio is then narrowed to what the reference actually has. One
    # pass would compare two different windows while looking like one — which the
    # engine's alignment check refuses, so this is correctness, not convenience.
    matrix = matrix_provider(instrument_ids, as_of)
    reference = reference_provider(reference_id, matrix.dates, as_of)
    if len(reference.points) != matrix.observation_count:
        common = [point.event_time for point in reference.points]
        matrix = matrix_provider(instrument_ids, as_of, common)

    return portfolio_volatility_vs_reference(
        matrix, weights, reference, computed_at=computed_at
    )
