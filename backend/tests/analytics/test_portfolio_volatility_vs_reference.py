"""The first deterministic judgement (M6c, ED-021).

Two things are under test and they are different: the *comparison* (pure arithmetic over
two volatilities) and the *engine* (refusals, alignment, envelope, lineage). The
comparison is tested directly so the threshold boundaries can be approached from both
sides without constructing a portfolio each time.
"""
from __future__ import annotations

import math
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from backend.analytics.portfolio_volatility_vs_reference import (
    CONFIDENCE_Z,
    METRIC_ID,
    annualized_volatility,
    compare,
    portfolio_volatility_vs_reference,
)
from backend.domain.market_data.sqlite_repository import SqliteMarketDataRepository
from backend.domain.model.analytics import ResultStatus, Verdict
from backend.domain.model.observations import AuthorityTier, PriceObservation, Provenance
from backend.domain.model.quantities import Currency, IndexLevel, Money
from backend.features.portfolio_returns import (
    build_aligned_reference_returns,
    build_aligned_return_matrix,
)
from backend.ingestion.validation import VALIDATION_VERSION
from backend.platform.identifiers import InstrumentId

RELIANCE, TCS = InstrumentId("reliance"), InstrumentId("tcs")
NIFTY = InstrumentId("nifty-50")
START = datetime(2024, 1, 1, tzinfo=UTC)
AS_OF = datetime(2030, 1, 1, tzinfo=UTC)
NOW = datetime(2026, 8, 10, 12, tzinfo=UTC)
PROVENANCE = Provenance(
    raw_object_key="raw/v1/yfinance/price-history/2024-01/x/abc.json",
    provider="yfinance",
    raw_contract_version="yfinance-ohlcv/v1",
    reference_version="instrument-reference/v2",
    validation_version=VALIDATION_VERSION,
)


def _prices(amplitude: float, count: int = 300) -> list[float]:
    """A deterministic sawtooth whose amplitude sets the realized volatility."""
    return [round(1000.0 + amplitude * ((day * 7) % 11 - 5), 4) for day in range(count)]


def _observation(instrument: InstrumentId, day: int, close: float, *, index: bool = False):
    price = IndexLevel(Decimal(str(close))) if index else Money(Decimal(str(close)), Currency.INR)
    event_time = START + timedelta(days=day)
    return PriceObservation(
        instrument_id=instrument, event_time=event_time, knowledge_time=event_time,
        interval="1d", open=price, high=price, low=price, close=price,
        volume=Decimal("1000"), authority=AuthorityTier.AUTHORITATIVE,
        quality_flags=(), provenance=PROVENANCE,
    )


def _repo(**amplitudes: float) -> Iterator[SqliteMarketDataRepository]:
    with SqliteMarketDataRepository() as repo:
        for slug, amp in amplitudes.items():
            instrument = InstrumentId(slug.replace("_", "-"))
            repo.save_observations([
                _observation(instrument, day, price, index=instrument == NIFTY)
                for day, price in enumerate(_prices(amp))
            ])
        yield repo


def _analyse(repo, ids, weights, *, z=CONFIDENCE_Z):
    matrix = build_aligned_return_matrix(repo, ids, as_of=AS_OF)
    reference = build_aligned_reference_returns(repo, NIFTY, matrix.dates, as_of=AS_OF)
    return portfolio_volatility_vs_reference(
        matrix, weights, reference, computed_at=NOW, z_threshold=z
    )


# ── The comparison, in isolation ──────────────────────────────────────────────

def test_identical_volatilities_are_not_distinguishable() -> None:
    c = compare(0.20, 0.20, portfolio_observations=250, reference_observations=250)
    assert c.verdict is Verdict.NOT_DISTINGUISHABLE
    assert c.ratio == pytest.approx(1.0)
    assert c.z == pytest.approx(0.0)
    assert c.ci_low < 1.0 < c.ci_high


def test_a_clearly_higher_volatility_is_called() -> None:
    c = compare(0.30, 0.15, portfolio_observations=250, reference_observations=250)
    assert c.verdict is Verdict.HIGHER_REALIZED_VOLATILITY
    assert c.ratio == pytest.approx(2.0)
    assert c.ci_low > 1.0


def test_a_clearly_lower_volatility_is_called() -> None:
    c = compare(0.08, 0.16, portfolio_observations=250, reference_observations=250)
    assert c.verdict is Verdict.LOWER_REALIZED_VOLATILITY
    assert c.ci_high < 1.0


def test_both_boundaries_are_approached_from_both_sides() -> None:
    """The threshold is a decision boundary, so it is tested as one.

    A ratio is constructed to land just inside and just outside |z| = 1.96 on each side;
    an off-by-one in the standard error or a dropped factor of two would move one of
    these four verdicts.
    """
    n = 250
    se = math.sqrt(2.0 / (n - 1) + 2.0 / (n - 1))

    def ratio_for(z: float) -> float:
        return math.exp(z * se / 2.0)

    for epsilon, expected_high, expected_low in (
        (-0.01, Verdict.NOT_DISTINGUISHABLE, Verdict.NOT_DISTINGUISHABLE),
        (+0.01, Verdict.HIGHER_REALIZED_VOLATILITY, Verdict.LOWER_REALIZED_VOLATILITY),
    ):
        z = CONFIDENCE_Z + epsilon
        assert compare(ratio_for(z), 1.0, portfolio_observations=n,
                       reference_observations=n).verdict is expected_high
        assert compare(ratio_for(-z), 1.0, portfolio_observations=n,
                       reference_observations=n).verdict is expected_low


def test_a_shorter_window_widens_the_interval_and_withholds_a_verdict() -> None:
    """Uncertainty is inherited from the evidence, not decided separately.

    The same 1.3x ratio is callable on 250 observations and not on 40 — fewer
    observations, wider interval, no verdict. If this ever inverted, the confidence rule
    would not be doing its job. (At n=60 this ratio is still just callable, z=2.02 —
    which is the rule working, and why the example uses a shorter window.)
    """
    long = compare(0.26, 0.20, portfolio_observations=250, reference_observations=250)
    short = compare(0.26, 0.20, portfolio_observations=40, reference_observations=40)

    assert long.verdict is Verdict.HIGHER_REALIZED_VOLATILITY
    assert short.verdict is Verdict.NOT_DISTINGUISHABLE
    assert (short.ci_high - short.ci_low) > (long.ci_high - long.ci_low)


def test_the_interval_brackets_the_ratio() -> None:
    c = compare(0.25, 0.20, portfolio_observations=200, reference_observations=180)
    assert c.ci_low < c.ratio < c.ci_high


def test_annualized_volatility_matches_a_hand_computation() -> None:
    returns = [0.01, -0.01, 0.02, -0.02, 0.0]
    mean = sum(returns) / len(returns)
    expected = math.sqrt(
        sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    ) * math.sqrt(252)
    assert annualized_volatility(returns, 252) == pytest.approx(expected)


# ── The engine ────────────────────────────────────────────────────────────────

def test_a_more_volatile_portfolio_is_judged_and_carries_its_ratio() -> None:
    for repo in _repo(reliance=6.0, tcs=6.0, **{"nifty_50": 1.0}):
        result = _analyse(repo, [RELIANCE, TCS], [0.5, 0.5])

        assert result.status is ResultStatus.AVAILABLE
        assert result.verdict is Verdict.HIGHER_REALIZED_VOLATILITY
        assert result.metric_id == METRIC_ID
        # ED-021: the quantity the verdict is about travels with the verdict.
        assert result.value is not None
        assert result.value.value > 1.0
        assert dict(result.diagnostics)["volatility_ratio"] == pytest.approx(result.value.value)


def test_a_less_volatile_portfolio_is_judged() -> None:
    for repo in _repo(reliance=1.0, tcs=1.0, **{"nifty_50": 6.0}):
        result = _analyse(repo, [RELIANCE, TCS], [0.5, 0.5])
        assert result.verdict is Verdict.LOWER_REALIZED_VOLATILITY
        assert result.value.value < 1.0


def test_a_matching_portfolio_is_not_distinguishable() -> None:
    for repo in _repo(reliance=3.0, tcs=3.0, **{"nifty_50": 3.0}):
        result = _analyse(repo, [RELIANCE, TCS], [0.5, 0.5])
        assert result.verdict is Verdict.NOT_DISTINGUISHABLE
        assert result.status is ResultStatus.AVAILABLE  # an answer, not a failure


def test_holdings_order_does_not_change_the_answer() -> None:
    for repo in _repo(reliance=4.0, tcs=2.0, **{"nifty_50": 3.0}):
        one = _analyse(repo, [RELIANCE, TCS], [0.6, 0.4])
        other = _analyse(repo, [TCS, RELIANCE], [0.4, 0.6])

        assert one.verdict is other.verdict
        assert one.value.value == pytest.approx(other.value.value, rel=1e-12)


def test_insufficient_history_refuses_rather_than_judging() -> None:
    with SqliteMarketDataRepository() as repo:
        for instrument, amp in ((RELIANCE, 5.0), (NIFTY, 2.0)):
            repo.save_observations([
                _observation(instrument, day, price, index=instrument == NIFTY)
                for day, price in enumerate(_prices(amp, count=20))
            ])
        result = _analyse(repo, [RELIANCE], [1.0])

    assert result.status is ResultStatus.UNAVAILABLE
    assert result.verdict is None
    assert "insufficient" in result.unavailable_reason


def test_unavailable_evidence_can_never_become_a_verdict() -> None:
    """The most dangerous path in the milestone, closed structurally.

    The envelope refuses an UNAVAILABLE result that carries a verdict, so this cannot be
    reintroduced by an engine author forgetting to clear it.
    """
    for repo in _repo(reliance=5.0, **{"nifty_50": 2.0}):
        matrix = build_aligned_return_matrix(repo, [RELIANCE], as_of=AS_OF)
        reference = build_aligned_reference_returns(repo, NIFTY, matrix.dates, as_of=AS_OF)
        # No weights => refusal, on evidence that would otherwise have produced a verdict.
        result = portfolio_volatility_vs_reference(matrix, [], reference, computed_at=NOW)

    assert result.status is ResultStatus.UNAVAILABLE
    assert result.verdict is None
    assert result.value is None


def test_mismatched_windows_refuse_rather_than_comparing() -> None:
    """A comparison over different windows answers a different question."""
    for repo in _repo(reliance=5.0, tcs=5.0, **{"nifty_50": 2.0}):
        matrix = build_aligned_return_matrix(repo, [RELIANCE, TCS], as_of=AS_OF)
        reference = build_aligned_reference_returns(repo, NIFTY, matrix.dates, as_of=AS_OF)
        truncated = type(reference)(
            instrument_id=reference.instrument_id, interval=reference.interval,
            as_of=reference.as_of, points=reference.points[:-5],
            quality_flags=reference.quality_flags,
            reference_version=reference.reference_version, lineage=reference.lineage,
        )
        result = portfolio_volatility_vs_reference(matrix, [0.5, 0.5], truncated, computed_at=NOW)

    assert result.status is ResultStatus.UNAVAILABLE
    assert "windows" in result.unavailable_reason


def test_the_judgement_pins_its_convention_and_its_reference_in_lineage() -> None:
    for repo in _repo(reliance=5.0, tcs=5.0, **{"nifty_50": 2.0}):
        result = _analyse(repo, [RELIANCE, TCS], [0.5, 0.5])

    parameters = dict(result.lineage.parameters)
    assert parameters["confidence_level"] == "95%"
    assert parameters["reference_instrument"] == "nifty-50"
    assert parameters["weights"]
    # Both the portfolio features and the reference feature are named.
    versions = {f.feature_version for f in result.lineage.features}
    assert "aligned-reference-return-series/v1" in versions
    assert result.lineage.raw_object_keys()


def test_the_result_is_deterministic() -> None:
    for repo in _repo(reliance=4.0, tcs=2.0, **{"nifty_50": 3.0}):
        first = _analyse(repo, [RELIANCE, TCS], [0.5, 0.5])
        second = _analyse(repo, [RELIANCE, TCS], [0.5, 0.5])
    assert first == second
