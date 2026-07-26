"""Portfolio risk & return (L7, doc 08). Catalog: `portfolio-risk-return · v1`.

**Investor question:** *How has my portfolio performed, and how much risk did I take to
get there?* Not "compute portfolio statistics" — the engine exists because an investor
holding four stocks cannot tell from four individual return figures whether the whole
was steady or violent, or whether the return justified the ride.

The answer is three numbers over one honest window: what the portfolio returned, how
volatile it was, and the return earned per unit of risk (Sharpe).

**What it refuses to do, and why each refusal beats a plausible number:**

* **Mixed currencies.** Weighting a USD holding's local return alongside an INR one
  silently omits the exchange-rate movement, which is often the larger effect. `FXRate`
  is the only sanctioned conversion source (doc 04) and is not yet an ingested data
  class, so the honest answer is a refusal rather than a confident wrong figure.
* **Unsupported instrument kinds.** An index is not ownable; reporting its movement as
  an investor's return omits the tracking error and fees of the fund actually held.
* **Weights that do not sum to one.** Normalizing them silently would compute a
  portfolio the investor did not describe.
* **Too little overlapping history.** Volatility from a handful of observations is
  noise wearing a decimal point.

**Confidence is published, not implied.** Every available result carries the effective
window, the number of overlapping observations, and the estimated relative standard
error of its own volatility figure — so "can I trust this number?" is answerable from
the response rather than from folklore.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from backend.domain.model.analytics import AnalyticResult, LineageHandle
from backend.domain.model.instruments import InstrumentReference
from backend.domain.model.quantities import Ratio
from backend.features.portfolio_returns import (
    MIN_OVERLAP_OBSERVATIONS,
    AlignedReturnMatrix,
    supported_for_portfolio,
)
from backend.platform.identifiers import InstrumentId

METRIC_ID = "portfolio_risk_return"
FORMULA_VERSION = "portfolio-risk-return/v1"

#: Trading periods per year for daily bars, used to annualize volatility (σ_daily × √252).
#: The conventional Indian and US equity-market count; weekly series would use 52.
PERIODS_PER_YEAR = {"1d": 252, "1wk": 52}

#: Weights must sum to 1 within this tolerance. Loose enough to absorb the rounding of
#: percentages entered by a human ("33.33% × 3"), tight enough that a genuinely
#: mis-specified portfolio is rejected rather than quietly renormalized.
WEIGHT_SUM_TOLERANCE = 1e-6

# Refusal reasons — specific, because each is shown to an investor in place of a number.
NO_HOLDINGS = "no-holdings-supplied"
WEIGHTS_MISMATCHED = "weights-do-not-match-holdings"
WEIGHTS_NOT_NORMALIZED = "weights-must-sum-to-one"
NEGATIVE_WEIGHT = "negative-weights-unsupported-no-short-positions"
MIXED_CURRENCY = "mixed-currency-portfolio-unsupported-pending-fx-data"
UNSUPPORTED_INSTRUMENT = "portfolio-supports-equities-and-etfs-only"
INSUFFICIENT_OVERLAP = "insufficient-overlapping-history-for-a-reliable-estimate"
UNSUPPORTED_INTERVAL = "unsupported-interval-for-annualization"

# Confidence diagnostics (ED-013): typed numbers, never parsed out of flag strings.
OVERLAPPING_OBSERVATIONS = "overlapping_observations"
VOLATILITY_RELATIVE_STANDARD_ERROR = "volatility_relative_standard_error"
PERIODS_PER_YEAR_USED = "periods_per_year"
HOLDINGS_COUNT = "holdings_count"


@dataclass(frozen=True, slots=True)
class Holding:
    """One position: what is held, and what fraction of the portfolio it is."""

    instrument_id: InstrumentId
    weight: float


def volatility_relative_standard_error(observations: int) -> float:
    """Approximate relative standard error of a volatility estimate from `n` samples.

    `1/sqrt(2(n-1))`, the standard result for the sample standard deviation of
    independent draws. Real returns are neither independent nor normal — fat tails and
    volatility clustering both make the true error larger — so this is an optimistic
    lower bound, published to convey precision honestly rather than to certify it.
    """
    if observations < 2:
        return float("inf")
    return 1.0 / math.sqrt(2.0 * (observations - 1))


def portfolio_risk_return(
    matrix: AlignedReturnMatrix,
    holdings: Sequence[Holding],
    references: Sequence[InstrumentReference],
    *,
    risk_free_rate: float,
    computed_at: datetime,
) -> AnalyticResult:
    """Portfolio return, volatility and Sharpe over the aligned window.

    `risk_free_rate` is an **annualized** rate supplied by the caller and recorded in
    lineage. It is an explicit input rather than an internal default because there is
    no `EconomicSeries` yet: inventing a rate would embed an unstated methodology
    choice — rf=0 flatters every Sharpe in an economy with ~7% government yields.
    """
    if computed_at.tzinfo is None:
        raise ValueError("computed_at must be timezone-aware")

    portfolio_id = InstrumentId("portfolio")
    lineage = LineageHandle(features=matrix.lineage)

    def unavailable(reason: str) -> AnalyticResult:
        return AnalyticResult.unavailable(
            metric_id=METRIC_ID,
            instrument_id=portfolio_id,
            reason=reason,
            formula_version=FORMULA_VERSION,
            reference_version=matrix.reference_version,
            as_of=matrix.as_of,
            computed_at=computed_at,
            quality_flags=matrix.quality_flags,
            lineage=lineage,
        )

    if not holdings:
        return unavailable(NO_HOLDINGS)
    if len(holdings) != len(matrix.instrument_ids) or len(references) != len(holdings):
        return unavailable(WEIGHTS_MISMATCHED)
    if any(holding.weight < 0.0 for holding in holdings):
        return unavailable(NEGATIVE_WEIGHT)
    if abs(sum(holding.weight for holding in holdings) - 1.0) > WEIGHT_SUM_TOLERANCE:
        return unavailable(WEIGHTS_NOT_NORMALIZED)
    if not all(supported_for_portfolio(reference) for reference in references):
        return unavailable(UNSUPPORTED_INSTRUMENT)
    if len({reference.currency for reference in references}) > 1:
        return unavailable(MIXED_CURRENCY)
    if matrix.interval not in PERIODS_PER_YEAR:
        return unavailable(UNSUPPORTED_INTERVAL)
    if matrix.observation_count < MIN_OVERLAP_OBSERVATIONS:
        return unavailable(INSUFFICIENT_OVERLAP)

    weights = tuple(holding.weight for holding in holdings)
    # The portfolio's return in each period is the weighted sum of its holdings'
    # returns — a fixed-weight (continuously rebalanced) portfolio. Stated in the
    # catalog as an assumption: a real buy-and-hold portfolio drifts from its weights.
    period_returns = [
        sum(weight * column[index] for weight, column in zip(weights, matrix.columns, strict=True))
        for index in range(matrix.observation_count)
    ]

    periods = PERIODS_PER_YEAR[matrix.interval]
    observations = matrix.observation_count

    # Total return compounds the actual period returns — exact, no assumption.
    total_return = math.prod(1.0 + r for r in period_returns) - 1.0
    # Annualized geometrically from that total (CAGR), not by compounding the arithmetic
    # mean, which systematically overstates when returns vary.
    annualized_return = (1.0 + total_return) ** (periods / observations) - 1.0

    mean = sum(period_returns) / observations
    # Sample variance (n-1): these returns are a sample of the return process, not the
    # whole population of it.
    variance = sum((r - mean) ** 2 for r in period_returns) / (observations - 1)
    annualized_volatility = math.sqrt(variance) * math.sqrt(periods)

    diagnostics: list[tuple[str, float]] = [
        ("total_return", total_return),
        ("annualized_return", annualized_return),
        ("annualized_volatility", annualized_volatility),
        (OVERLAPPING_OBSERVATIONS, float(observations)),
        (VOLATILITY_RELATIVE_STANDARD_ERROR, volatility_relative_standard_error(observations)),
        (PERIODS_PER_YEAR_USED, float(periods)),
        (HOLDINGS_COUNT, float(len(holdings))),
    ]
    flags = set(matrix.quality_flags)

    # A perfectly flat portfolio has undefined Sharpe, not zero Sharpe. Reporting 0.0
    # would state "no excess return per unit of risk" when the truth is "the ratio does
    # not exist here" — absence, not a fabricated value (principle 13).
    if annualized_volatility == 0.0:
        flags.add("sharpe-undefined-zero-volatility")
    else:
        diagnostics.append(
            ("sharpe_ratio", (annualized_return - risk_free_rate) / annualized_volatility)
        )

    window = matrix.window()
    parameters: list[tuple[str, str]] = [
        ("risk_free_rate", repr(risk_free_rate)),
        ("weights", ",".join(f"{h.instrument_id.value}={h.weight!r}" for h in holdings)),
        ("interval", matrix.interval),
    ]
    if window is not None:
        parameters.extend(
            [("window_start", window[0].isoformat()), ("window_end", window[1].isoformat())]
        )

    return AnalyticResult.available(
        metric_id=METRIC_ID,
        instrument_id=portfolio_id,
        # The headline value is the total return over the window. Volatility and Sharpe
        # travel as diagnostics: one envelope carries one value plus the context needed
        # to judge it, rather than three envelopes a client must correlate.
        value=Ratio(total_return),
        formula_version=FORMULA_VERSION,
        reference_version=matrix.reference_version,
        as_of=matrix.as_of,
        computed_at=computed_at,
        quality_flags=tuple(sorted(flags)),
        diagnostics=tuple(diagnostics),
        # Engine parameters are pinned alongside the features: without the weights and
        # the risk-free rate, this envelope names its inputs but not the invocation, and
        # the number is not reproducible from it (ED-016).
        lineage=LineageHandle(features=matrix.lineage, parameters=tuple(parameters)),
    )
