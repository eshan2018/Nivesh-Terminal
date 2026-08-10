"""Portfolio risk & return engine (L7).

Doc 11's three mechanisms, applied to a multi-input engine for the first time: reference
values for the cases a human can check by hand, property-based tests for the invariants
nobody thinks to hand-compute, and parity against an independently written
implementation. Plus the refusal paths, which matter more here than for a single-metric
engine — a portfolio has many more ways to be mis-specified.
"""
from __future__ import annotations

import math
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.analytics.portfolio_risk_return import (
    FORMULA_VERSION,
    INSUFFICIENT_OVERLAP,
    METRIC_ID,
    MIXED_CURRENCY,
    NEGATIVE_WEIGHT,
    OVERLAPPING_OBSERVATIONS,
    UNSUPPORTED_INSTRUMENT,
    VOLATILITY_RELATIVE_STANDARD_ERROR,
    WEIGHTS_NOT_NORMALIZED,
    Holding,
    portfolio_risk_return,
    volatility_relative_standard_error,
)
from backend.domain.market_data.sqlite_repository import SqliteMarketDataRepository
from backend.domain.model.analytics import ResultStatus
from backend.domain.model.instruments import (
    REFERENCE_VERSION,
    InstrumentReference,
    InstrumentType,
    reference_for,
)
from backend.domain.model.observations import AuthorityTier, PriceObservation, Provenance
from backend.domain.model.quantities import Currency, IndexLevel, Money, Ratio
from backend.features.portfolio_returns import build_aligned_return_matrix
from backend.ingestion.validation import VALIDATION_VERSION
from backend.platform.identifiers import InstrumentId
from backend.tests.analytics.portfolio_reference_implementation import (
    RATIO_RELATIVE_TOLERANCE,
    annualized_return,
    annualized_volatility,
    portfolio_period_returns,
    sharpe_ratio,
    total_return,
)

RELIANCE, TCS, INFOSYS = (InstrumentId(x) for x in ("reliance", "tcs", "infosys"))
APPLE, NIFTY = InstrumentId("apple"), InstrumentId("nifty-50")
START = datetime(2024, 1, 1, tzinfo=UTC)
AS_OF = datetime(2030, 1, 1, tzinfo=UTC)
COMPUTED_AT = datetime(2026, 7, 22, 12, tzinfo=UTC)
RF = 0.07  # ~India 10Y G-Sec, supplied explicitly as the engine requires
PROVENANCE = Provenance(
    raw_object_key="raw/v1/yfinance/price-history/2024-01/x/abc.json",
    provider="yfinance",
    raw_contract_version="yfinance-ohlcv/v1",
    reference_version=REFERENCE_VERSION,
    validation_version=VALIDATION_VERSION,
)


def _observation(
    instrument: InstrumentId, day: int, close: float, currency: Currency = Currency.INR
) -> PriceObservation:
    price = Money(Decimal(str(round(close, 4))), currency)
    event_time = START + timedelta(days=day)
    return PriceObservation(
        instrument_id=instrument,
        event_time=event_time,
        knowledge_time=event_time,
        interval="1d",
        open=price, high=price, low=price, close=price,
        volume=Decimal("1000"),
        authority=AuthorityTier.AUTHORITATIVE,
        quality_flags=(),
        provenance=PROVENANCE,
    )


@pytest.fixture()
def repo() -> Iterator[SqliteMarketDataRepository]:
    with SqliteMarketDataRepository() as repository:
        yield repository


def _seed(repo, instrument: InstrumentId, prices: Sequence[float], **kw) -> None:
    repo.save_observations(
        [_observation(instrument, day, p, **kw) for day, p in enumerate(prices)]
    )


def _ramp(start: float, n: int, step: float) -> list[float]:
    """A deterministic price path long enough to clear the overlap threshold.

    Rounded to the precision the repository stores, so the values seeded and the values
    an expectation is computed from are the same numbers. Without this, a test compares
    the engine's answer over stored prices against an expectation over unrounded ones
    and reports a storage artifact as an engine defect.
    """
    return [round(start * (1.0 + step) ** i, 4) for i in range(n)]


def _analyse(repo, holdings: Sequence[Holding], *, rf: float = RF):
    ids = [h.instrument_id for h in holdings]
    matrix = build_aligned_return_matrix(repo, ids, as_of=AS_OF)
    references = [reference_for(i) for i in ids]
    return portfolio_risk_return(
        matrix, holdings, references, risk_free_rate=rf, computed_at=COMPUTED_AT
    )


# ── Reference values ──────────────────────────────────────────────────────────


def test_a_single_holding_portfolio_equals_that_holding(repo) -> None:
    """The clearest sanity anchor: 100% in one stock is that stock."""
    prices = _ramp(100.0, 80, 0.001)
    _seed(repo, RELIANCE, prices)

    result = _analyse(repo, [Holding(RELIANCE, 1.0)])

    assert result.status is ResultStatus.AVAILABLE
    assert isinstance(result.value, Ratio)
    assert result.value.value == pytest.approx(prices[-1] / prices[0] - 1.0, rel=1e-9)


def test_two_flat_holdings_return_zero_with_zero_volatility(repo) -> None:
    _seed(repo, RELIANCE, [100.0] * 80)
    _seed(repo, TCS, [200.0] * 80)

    result = _analyse(repo, [Holding(RELIANCE, 0.5), Holding(TCS, 0.5)])

    assert result.value == Ratio(0.0)
    diagnostics = dict(result.diagnostics)
    assert diagnostics["annualized_volatility"] == 0.0
    # Sharpe is undefined, not zero — absence rather than a fabricated ratio.
    assert "sharpe_ratio" not in diagnostics
    assert "sharpe-undefined-zero-volatility" in result.quality_flags


def test_the_portfolio_return_is_weighted_not_averaged(repo) -> None:
    """A 90/10 split must track the heavy holding, not sit midway."""
    _seed(repo, RELIANCE, _ramp(100.0, 80, 0.002))   # grows
    _seed(repo, TCS, [200.0] * 80)                   # flat

    heavy = _analyse(repo, [Holding(RELIANCE, 0.9), Holding(TCS, 0.1)])
    light = _analyse(repo, [Holding(RELIANCE, 0.1), Holding(TCS, 0.9)])

    assert isinstance(heavy.value, Ratio) and isinstance(light.value, Ratio)
    assert heavy.value.value > light.value.value > 0.0


# ── Confidence metadata (adjustment 5) ────────────────────────────────────────


def test_the_result_publishes_the_window_it_actually_used(repo) -> None:
    """"Can I trust this number?" must be answerable from the response itself."""
    _seed(repo, RELIANCE, _ramp(100.0, 80, 0.001))
    _seed(repo, TCS, _ramp(200.0, 80, 0.001))

    result = _analyse(repo, [Holding(RELIANCE, 0.5), Holding(TCS, 0.5)])
    parameters = dict(result.lineage.parameters)
    diagnostics = dict(result.diagnostics)

    assert diagnostics[OVERLAPPING_OBSERVATIONS] == 79.0
    assert diagnostics[VOLATILITY_RELATIVE_STANDARD_ERROR] == pytest.approx(
        volatility_relative_standard_error(79), rel=1e-12
    )
    assert parameters["window_start"] and parameters["window_end"]
    assert parameters["risk_free_rate"] == repr(RF)


def test_the_result_pins_the_weights_that_produced_it(repo) -> None:
    """Same holdings, different weights, different portfolio — the envelope must say which."""
    _seed(repo, RELIANCE, _ramp(100.0, 80, 0.001))
    _seed(repo, TCS, _ramp(200.0, 80, 0.002))

    a = _analyse(repo, [Holding(RELIANCE, 0.25), Holding(TCS, 0.75)])
    b = _analyse(repo, [Holding(RELIANCE, 0.75), Holding(TCS, 0.25)])

    assert dict(a.lineage.parameters)["weights"] != dict(b.lineage.parameters)["weights"]
    assert a.value != b.value


def test_fewer_observations_report_a_larger_standard_error(repo) -> None:
    """Confidence must degrade visibly as the window shrinks."""
    assert volatility_relative_standard_error(51) > volatility_relative_standard_error(501)
    assert volatility_relative_standard_error(1) == math.inf


# ── Refusals ──────────────────────────────────────────────────────────────────


def test_weights_that_do_not_sum_to_one_are_refused(repo) -> None:
    """Silently renormalizing would compute a portfolio the investor never described."""
    _seed(repo, RELIANCE, _ramp(100.0, 80, 0.001))
    _seed(repo, TCS, _ramp(200.0, 80, 0.001))

    result = _analyse(repo, [Holding(RELIANCE, 0.5), Holding(TCS, 0.2)])

    assert result.status is ResultStatus.UNAVAILABLE
    assert result.unavailable_reason == WEIGHTS_NOT_NORMALIZED
    assert result.value is None


def test_negative_weights_are_refused(repo) -> None:
    _seed(repo, RELIANCE, _ramp(100.0, 80, 0.001))
    _seed(repo, TCS, _ramp(200.0, 80, 0.001))

    result = _analyse(repo, [Holding(RELIANCE, 1.5), Holding(TCS, -0.5)])

    assert result.unavailable_reason == NEGATIVE_WEIGHT


def test_a_mixed_currency_portfolio_is_refused(repo) -> None:
    """Weighting local returns across currencies omits the FX move — often the larger one."""
    _seed(repo, RELIANCE, _ramp(100.0, 80, 0.001))
    _seed(repo, APPLE, _ramp(200.0, 80, 0.001), currency=Currency.USD)

    result = _analyse(repo, [Holding(RELIANCE, 0.5), Holding(APPLE, 0.5)])

    assert result.unavailable_reason == MIXED_CURRENCY


def test_an_index_cannot_be_held(repo) -> None:
    """Nobody owns an index; reporting its level as a return hides fees and tracking error."""
    _seed(repo, RELIANCE, _ramp(100.0, 80, 0.001))
    level = IndexLevel(Decimal("24000"))
    repo.save_observations([
        PriceObservation(
            instrument_id=NIFTY,
            event_time=START + timedelta(days=day),
            knowledge_time=START + timedelta(days=day),
            interval="1d",
            open=level, high=level, low=level, close=level,
            volume=Decimal("1000"),
            authority=AuthorityTier.AUTHORITATIVE,
            quality_flags=(),
            provenance=PROVENANCE,
        )
        for day in range(80)
    ])

    result = _analyse(repo, [Holding(RELIANCE, 0.5), Holding(NIFTY, 0.5)])

    assert result.unavailable_reason == UNSUPPORTED_INSTRUMENT


def test_too_little_overlapping_history_is_refused(repo) -> None:
    """Volatility from a handful of points is noise wearing a decimal point."""
    _seed(repo, RELIANCE, _ramp(100.0, 20, 0.001))
    _seed(repo, TCS, _ramp(200.0, 20, 0.001))

    result = _analyse(repo, [Holding(RELIANCE, 0.5), Holding(TCS, 0.5)])

    assert result.unavailable_reason == INSUFFICIENT_OVERLAP
    assert result.value is None


def test_an_etf_may_be_held_alongside_an_equity() -> None:
    """Adjustment 2: supported asset classes, not equities-only."""
    from backend.features.portfolio_returns import supported_for_portfolio

    etf = InstrumentReference(
        InstrumentId("niftybees"), "NiftyBees", InstrumentType.ETF, Currency.INR, "XNSE"
    )
    assert supported_for_portfolio(etf)


def test_a_refusal_is_still_fully_traced(repo) -> None:
    _seed(repo, RELIANCE, _ramp(100.0, 20, 0.001))

    result = _analyse(repo, [Holding(RELIANCE, 1.0)])

    assert result.status is ResultStatus.UNAVAILABLE
    assert result.formula_version == FORMULA_VERSION
    assert result.metric_id == METRIC_ID
    assert result.lineage.features


# ── Properties ────────────────────────────────────────────────────────────────

_PRICE_STEPS = st.lists(
    st.floats(min_value=-0.05, max_value=0.05, allow_nan=False, allow_infinity=False),
    min_size=60, max_size=90,
)


def _path(steps: Sequence[float], start: float = 100.0) -> list[float]:
    """A price path from relative steps, rounded to stored precision (see `_ramp`)."""
    prices, level = [round(start, 4)], start
    for step in steps:
        level *= 1.0 + step
        prices.append(round(level, 4))
    return prices


@given(steps=_PRICE_STEPS)
@settings(max_examples=25, deadline=None)
def test_property_a_hundred_percent_holding_reproduces_the_asset(steps) -> None:
    with SqliteMarketDataRepository() as repo:
        prices = _path(steps)
        _seed(repo, RELIANCE, prices)
        result = _analyse(repo, [Holding(RELIANCE, 1.0)])

        assert isinstance(result.value, Ratio)
        assert result.value.value == pytest.approx(prices[-1] / prices[0] - 1.0, rel=1e-9)


@given(steps=_PRICE_STEPS)
@settings(max_examples=25, deadline=None)
def test_property_volatility_is_never_negative(steps) -> None:
    with SqliteMarketDataRepository() as repo:
        _seed(repo, RELIANCE, _path(steps))
        _seed(repo, TCS, _path(list(reversed(steps)), start=250.0))
        result = _analyse(repo, [Holding(RELIANCE, 0.5), Holding(TCS, 0.5)])

        assert dict(result.diagnostics)["annualized_volatility"] >= 0.0


@given(steps=_PRICE_STEPS)
@settings(max_examples=25, deadline=None)
def test_property_holding_order_does_not_change_the_answer(steps) -> None:
    """A portfolio is a set of positions; listing order is presentation, not meaning."""
    with SqliteMarketDataRepository() as repo:
        _seed(repo, RELIANCE, _path(steps))
        _seed(repo, TCS, _path(list(reversed(steps)), start=250.0))

        forward = _analyse(repo, [Holding(RELIANCE, 0.3), Holding(TCS, 0.7)])
        backward = _analyse(repo, [Holding(TCS, 0.7), Holding(RELIANCE, 0.3)])

        assert isinstance(forward.value, Ratio) and isinstance(backward.value, Ratio)
        assert forward.value.value == pytest.approx(backward.value.value, rel=1e-12)


@given(steps=_PRICE_STEPS)
@settings(max_examples=25, deadline=None)
def test_property_the_result_is_deterministic(steps) -> None:
    with SqliteMarketDataRepository() as repo:
        _seed(repo, RELIANCE, _path(steps))
        _seed(repo, TCS, _path(list(reversed(steps)), start=250.0))
        holdings = [Holding(RELIANCE, 0.4), Holding(TCS, 0.6)]

        assert _analyse(repo, holdings) == _analyse(repo, holdings)


@given(steps=_PRICE_STEPS)
@settings(max_examples=25, deadline=None)
def test_property_a_diversified_pair_is_no_riskier_than_its_worst_holding(steps) -> None:
    """Diversification cannot manufacture risk — the investor-facing meaning of covariance."""
    with SqliteMarketDataRepository() as repo:
        _seed(repo, RELIANCE, _path(steps))
        _seed(repo, TCS, _path(list(reversed(steps)), start=250.0))

        blend = dict(_analyse(repo, [Holding(RELIANCE, 0.5), Holding(TCS, 0.5)]).diagnostics)
        first = dict(_analyse(repo, [Holding(RELIANCE, 1.0)]).diagnostics)
        second = dict(_analyse(repo, [Holding(TCS, 1.0)]).diagnostics)

        worst = max(first["annualized_volatility"], second["annualized_volatility"])
        assert blend["annualized_volatility"] <= worst * (1.0 + 1e-9)


# ── Parity with the independent implementation ────────────────────────────────


@given(steps=_PRICE_STEPS)
@settings(max_examples=40, deadline=None)
def test_parity_with_the_independent_reference_implementation(steps) -> None:
    with SqliteMarketDataRepository() as repo:
        prices_a, prices_b = _path(steps), _path(list(reversed(steps)), start=250.0)
        _seed(repo, RELIANCE, prices_a)
        _seed(repo, TCS, prices_b)
        weights = [0.4, 0.6]

        result = _analyse(repo, [Holding(RELIANCE, 0.4), Holding(TCS, 0.6)])

        series = [
            {
                START + timedelta(days=i): prices[i] / prices[i - 1] - 1.0
                for i in range(1, len(prices))
            }
            for prices in (prices_a, prices_b)
        ]
        expected = portfolio_period_returns(series, weights)

        assert isinstance(result.value, Ratio)
        diagnostics = dict(result.diagnostics)
        assert result.value.value == pytest.approx(
            total_return(expected), rel=RATIO_RELATIVE_TOLERANCE, abs=RATIO_RELATIVE_TOLERANCE
        )
        assert diagnostics["annualized_return"] == pytest.approx(
            annualized_return(expected, 252), rel=1e-9
        )
        assert diagnostics["annualized_volatility"] == pytest.approx(
            annualized_volatility(expected, 252), rel=1e-9
        )
        reference_sharpe = sharpe_ratio(expected, 252, RF)
        if reference_sharpe is None:
            assert "sharpe_ratio" not in diagnostics
        else:
            assert diagnostics["sharpe_ratio"] == pytest.approx(reference_sharpe, rel=1e-9)
