"""An independent reference implementation of portfolio risk & return (doc 11, B10).

Written to differ from `backend.analytics.portfolio_risk_return` wherever a shared
assumption could hide a shared bug:

* **Different alignment.** The engine intersects date sets. This builds an ordered
  index from the first instrument and filters, which reaches the same window by a
  different route — so a mistake in set intersection would show up as disagreement
  rather than as matching answers.
* **Different aggregation order.** The engine weights returns per period, then
  compounds. This compounds each *holding* first and combines at the end where the
  arithmetic permits, and uses `statistics.fmean`/`stdev` rather than hand-rolled sums —
  so a mis-signed or mis-ordered accumulation separates the two.
* **Different volatility path.** `statistics.stdev` (sample, n-1) instead of an explicit
  variance loop.

**Numeric tolerance policy** — the same one the M3 engine established, restated because
it is enforced here too:

* **Money compares exactly.** No epsilon anywhere money is involved. None is, here:
  every quantity in a portfolio result is a unitless ratio.
* **Ratios compare within a relative 1e-12.** IEEE-754 doubles carry ~2.2e-16 relative
  epsilon; these computations are a few hundred multiply-accumulates over values near
  1.0, so accumulated error stays several orders of magnitude inside that bound. The
  M3 parity exercise measured 3.5e-15 between two implementations of a simpler formula;
  the extra headroom here covers the longer accumulation.

Test-tier only. Never imported by `backend/`.
"""
from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from datetime import datetime

RATIO_RELATIVE_TOLERANCE = 1e-12


def align(series: Sequence[dict[datetime, float]]) -> list[datetime]:
    """Dates present in every series, ascending.

    Deliberately not a set intersection: walk the first series in order and keep the
    dates the others also have.
    """
    if not series:
        return []
    ordered = sorted(series[0])
    return [date for date in ordered if all(date in other for other in series[1:])]


def portfolio_period_returns(
    series: Sequence[dict[datetime, float]], weights: Sequence[float]
) -> list[float]:
    """The weighted portfolio return for each aligned period."""
    dates = align(series)
    return [
        math.fsum(weight * mapping[date] for weight, mapping in zip(weights, series, strict=True))
        for date in dates
    ]


def total_return(period_returns: Sequence[float]) -> float:
    """Compound the period returns. Uses a running product, not `math.prod`."""
    compounded = 1.0
    for value in period_returns:
        compounded *= 1.0 + value
    return compounded - 1.0


def annualized_return(period_returns: Sequence[float], periods_per_year: int) -> float:
    """Geometric annualization of the compounded total."""
    total = total_return(period_returns)
    exponent = periods_per_year / len(period_returns)
    return math.exp(exponent * math.log1p(total)) - 1.0


def annualized_volatility(period_returns: Sequence[float], periods_per_year: int) -> float:
    """Sample standard deviation via `statistics.stdev`, scaled by sqrt(periods)."""
    return statistics.stdev(period_returns) * math.sqrt(periods_per_year)


def sharpe_ratio(
    period_returns: Sequence[float], periods_per_year: int, risk_free_rate: float
) -> float | None:
    """Excess annualized return per unit of annualized volatility, or `None`.

    `None` rather than zero when volatility vanishes: the ratio is undefined, and this
    implementation must agree with the engine about *when there is no answer*, not only
    about values.
    """
    volatility = annualized_volatility(period_returns, periods_per_year)
    if volatility == 0.0:
        return None
    return (annualized_return(period_returns, periods_per_year) - risk_free_rate) / volatility
