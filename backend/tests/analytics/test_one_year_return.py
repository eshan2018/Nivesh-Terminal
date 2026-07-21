"""Tests for the `one_year_return` engine (L7).

Doc 11 requires three complementary mechanisms for financial correctness, because
each alone fails: reference values anchor the simple cases, property-based tests catch
the bugs nobody thought to hand-compute, and an independent reference implementation
catches the ones both of those share an assumption about. All three are here, plus the
envelope invariants (never zero, always traced) and determinism.

The tolerance policy the parity assertions use is documented in
`reference_implementation.py`: money exact, ratios within a relative 1e-12.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.analytics.one_year_return import (
    ANCHOR_OFFSET_DAYS,
    FORMULA_VERSION,
    INSUFFICIENT_HISTORY,
    METRIC_ID,
    NO_ANCHOR_IN_TOLERANCE,
    NO_OBSERVATIONS,
    ZERO_ANCHOR_PRICE,
    one_year_return,
)
from backend.domain.model.analytics import AnalyticResult, ResultStatus
from backend.domain.model.instruments import REFERENCE_VERSION
from backend.domain.model.observations import (
    AuthorityTier,
    PriceObservation,
    Provenance,
)
from backend.domain.model.quantities import Currency, IndexLevel, Money, Ratio
from backend.features.returns import ClosePriceSeries, build_close_price_series
from backend.platform.identifiers import InstrumentId
from backend.tests.analytics.fakes import FakeRepository
from backend.tests.analytics.reference_implementation import (
    RATIO_RELATIVE_TOLERANCE,
    reference_one_year_return,
)

RELIANCE = InstrumentId("reliance")
NIFTY = InstrumentId("nifty-50")
START = datetime(2025, 1, 2, tzinfo=UTC)
COMPUTED_AT = datetime(2026, 6, 1, 12, tzinfo=UTC)
FAR_FUTURE = datetime(2030, 1, 1, tzinfo=UTC)
PROVENANCE = Provenance(
    raw_object_key="raw/v1/price-history/reliance.json",
    provider="yfinance",
    raw_contract_version="yfinance-ohlcv/v1",
    reference_version=REFERENCE_VERSION,
)


# ── Fixtures and helpers ──────────────────────────────────────────────────────


def _observations(
    prices: Sequence[Decimal],
    *,
    start: datetime = START,
    step: timedelta = timedelta(days=1),
    index: bool = False,
    instrument_id: InstrumentId = RELIANCE,
) -> tuple[PriceObservation, ...]:
    """Consecutive daily bars with the given closes."""
    bars = []
    for offset, amount in enumerate(prices):
        price = IndexLevel(amount) if index else Money(amount, Currency.INR)
        event_time = start + offset * step
        bars.append(
            PriceObservation(
                instrument_id=instrument_id,
                event_time=event_time,
                knowledge_time=event_time,
                interval="1d",
                open=price,
                high=price,
                low=price,
                close=price,
                volume=Decimal("1000"),
                authority=AuthorityTier.AUTHORITATIVE,
                quality_flags=(),
                provenance=PROVENANCE,
            )
        )
    return tuple(bars)


def _series_from(
    observations: tuple[PriceObservation, ...],
    *,
    as_of: datetime = FAR_FUTURE,
    instrument_id: InstrumentId = RELIANCE,
) -> ClosePriceSeries:
    """Build the real feature from observations, through the real feature layer."""
    return build_close_price_series(
        FakeRepository(observations), instrument_id, as_of=as_of  # type: ignore[arg-type]
    )


def _series_at(
    dated_prices: Sequence[tuple[datetime, str]],
    *,
    as_of: datetime = FAR_FUTURE,
    index: bool = False,
) -> ClosePriceSeries:
    """A series with explicitly dated bars, for the irregular-spacing cases."""
    observations = tuple(
        _observations([Decimal(price)], start=when, index=index)[0]
        for when, price in dated_prices
    )
    return _series_from(observations, as_of=as_of)


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


def _daily(prices: Sequence[str]) -> ClosePriceSeries:
    return _series_from(_observations([Decimal(price) for price in prices]))


def _assert_ratio(result: AnalyticResult, expected: float) -> None:
    """Assert a ratio value within the documented tolerance.

    Reference values are compared with an epsilon, not exactly: `120/100 - 1` is
    `0.19999999999999996` in IEEE-754, and a test that demanded `0.2` exactly would be
    asserting a property of binary floating point rather than of the metric. The
    tolerance is the one declared in `reference_implementation.py`.
    """
    assert result.status is ResultStatus.AVAILABLE
    assert isinstance(result.value, Ratio)
    assert result.value.value == pytest.approx(
        expected, rel=RATIO_RELATIVE_TOLERANCE, abs=RATIO_RELATIVE_TOLERANCE
    )


# ── Reference values (hand-computed) ──────────────────────────────────────────


def test_a_twenty_percent_gain_over_exactly_one_year() -> None:
    result = one_year_return(
        _series_at(
            [
                (_utc(2025, 1, 2), "100.00"),
                (_utc(2026, 1, 2), "120.00"),
            ]
        ),
        computed_at=COMPUTED_AT,
    )
    _assert_ratio(result, 0.2)


def test_a_twenty_percent_loss_over_exactly_one_year() -> None:
    result = one_year_return(
        _series_at(
            [
                (_utc(2025, 1, 2), "100.00"),
                (_utc(2026, 1, 2), "80.00"),
            ]
        ),
        computed_at=COMPUTED_AT,
    )
    _assert_ratio(result, -0.2)


def test_the_metric_is_unitless_so_an_index_computes_the_same_as_an_equity() -> None:
    """The reason 1Y return is safe without FX: a ratio has no currency to convert."""
    dates = [(_utc(2025, 1, 2), "100.00"), (_utc(2026, 1, 2), "115.00")]
    equity = one_year_return(_series_at(dates), computed_at=COMPUTED_AT)
    index = one_year_return(_series_at(dates, index=True), computed_at=COMPUTED_AT)
    _assert_ratio(equity, 0.15)
    assert equity.value == index.value


def test_an_anchor_off_the_target_date_is_used_and_reported_as_a_number() -> None:
    """Markets close; the nearest bar within tolerance is used, and says how far off.

    The offset is a typed diagnostic, not a string inside a quality flag — so a
    consumer reads a number instead of parsing one out of a tag (Decision 2).
    """
    result = one_year_return(
        _series_at(
            [
                (_utc(2025, 1, 2), "100.00"),
                (_utc(2026, 1, 5), "110.00"),
            ]
        ),
        computed_at=COMPUTED_AT,
    )
    _assert_ratio(result, 0.1)
    # Target is 2025-01-05; the anchor sits three days earlier.
    assert dict(result.diagnostics)[ANCHOR_OFFSET_DAYS] == -3.0
    assert result.quality_flags == ()  # flags stay opaque tags


def test_an_exact_anchor_reports_a_zero_offset() -> None:
    result = one_year_return(
        _series_at(
            [
                (_utc(2025, 1, 2), "100.00"),
                (_utc(2026, 1, 2), "110.00"),
            ]
        ),
        computed_at=COMPUTED_AT,
    )
    assert dict(result.diagnostics)[ANCHOR_OFFSET_DAYS] == 0.0


# ── Absence, never fabrication (principle 13) ─────────────────────────────────


@pytest.mark.parametrize(
    ("series", "expected_reason"),
    [
        (_daily([]), NO_OBSERVATIONS),
        (_daily(["100.00"]), INSUFFICIENT_HISTORY),
        (
            _series_at(
                [
                    (_utc(2024, 12, 20), "100.00"),
                    (_utc(2026, 1, 5), "110.00"),
                ]
            ),
            NO_ANCHOR_IN_TOLERANCE,
        ),
        (
            _series_at(
                [
                    (_utc(2025, 1, 2), "0.00"),
                    (_utc(2026, 1, 2), "110.00"),
                ]
            ),
            ZERO_ANCHOR_PRICE,
        ),
    ],
    ids=["empty", "single-bar", "anchor-out-of-tolerance", "zero-anchor"],
)
def test_missing_or_undefined_inputs_yield_unavailable_with_a_reason(
    series: ClosePriceSeries, expected_reason: str
) -> None:
    result = one_year_return(series, computed_at=COMPUTED_AT)
    assert result.status is ResultStatus.UNAVAILABLE
    assert result.unavailable_reason == expected_reason
    assert result.value is None  # never zero, never fabricated


def test_a_short_history_says_so_rather_than_blaming_the_anchor() -> None:
    """The bug this forbids: reporting a 3-month return as if it were a 1-year one.

    The reason matters as much as the refusal — a user with three months of data is
    told the history is short, not that some anchor bar is missing.
    """
    result = one_year_return(_daily(["100.00"] * 90), computed_at=COMPUTED_AT)
    assert result.status is ResultStatus.UNAVAILABLE
    assert result.unavailable_reason == INSUFFICIENT_HISTORY


def test_a_gap_where_the_anchor_belongs_is_reported_as_an_anchor_failure() -> None:
    """History long enough, but no bar near the target: a different diagnosis."""
    result = one_year_return(
        _series_at(
            [
                (_utc(2024, 12, 20), "100.00"),
                (_utc(2025, 1, 20), "101.00"),
                (_utc(2026, 1, 5), "110.00"),
            ]
        ),
        computed_at=COMPUTED_AT,
    )
    assert result.status is ResultStatus.UNAVAILABLE
    assert result.unavailable_reason == NO_ANCHOR_IN_TOLERANCE


def test_an_unavailable_result_is_still_fully_traced() -> None:
    """Absence is auditable too — you can still ask why, and against which versions."""
    result = one_year_return(_daily([]), computed_at=COMPUTED_AT)
    assert result.formula_version == FORMULA_VERSION
    assert result.reference_version == REFERENCE_VERSION
    assert result.lineage.features[0].feature_version == "close-price-series/v1"


# ── The envelope ──────────────────────────────────────────────────────────────


def test_the_result_carries_every_version_and_time_the_envelope_requires() -> None:
    series = _series_at(
        [
            (_utc(2025, 1, 2), "100.00"),
            (_utc(2026, 1, 2), "120.00"),
        ],
        as_of=FAR_FUTURE,
    )
    result = one_year_return(series, computed_at=COMPUTED_AT)

    assert result.metric_id == METRIC_ID
    assert result.instrument_id == RELIANCE
    assert result.formula_version == FORMULA_VERSION
    assert result.reference_version == REFERENCE_VERSION
    assert result.as_of == FAR_FUTURE
    assert result.computed_at == COMPUTED_AT


def test_lineage_resolves_from_the_result_to_the_raw_records() -> None:
    """Doc 00 §B5: result → feature version → observations → raw objects."""
    result = one_year_return(
        _series_at(
            [
                (_utc(2025, 1, 2), "100.00"),
                (_utc(2026, 1, 2), "120.00"),
            ]
        ),
        computed_at=COMPUTED_AT,
    )

    (feature,) = result.lineage.features
    assert feature.feature_id == "close_price_series"
    assert len(feature.inputs) == 2
    assert result.lineage.raw_object_keys() == (PROVENANCE.raw_object_key,)
    assert {ref.provenance.provider for ref in feature.inputs} == {"yfinance"}
    assert {ref.provenance.raw_contract_version for ref in feature.inputs} == {
        "yfinance-ohlcv/v1"
    }


def test_lineage_names_the_two_bars_that_produced_the_value() -> None:
    """Decision 1: contributing inputs, not the whole scanned set.

    400 bars are scanned to find the anchor; two determine the answer. A response
    carrying all 400 would grow with history rather than with the answer.
    """
    prices = [Decimal("100.00")] * 400
    prices[34] = Decimal("200.00")   # the anchor bar: 399 - 365 = index 34
    prices[399] = Decimal("300.00")  # the end bar
    result = one_year_return(_series_from(_observations(prices)), computed_at=COMPUTED_AT)

    assert result.lineage.scanned_count() == 400
    assert len(result.lineage.contributing) == 2
    anchor, end = result.lineage.contributing
    assert anchor.event_time == START + timedelta(days=34)
    assert end.event_time == START + timedelta(days=399)
    _assert_ratio(result, 300.0 / 200.0 - 1.0)


def test_an_unavailable_result_names_no_contributing_inputs() -> None:
    """Nothing produced a value, so nothing can be cited as having produced it."""
    result = one_year_return(_daily(["100.00"]), computed_at=COMPUTED_AT)
    assert result.status is ResultStatus.UNAVAILABLE
    assert result.lineage.contributing == ()


def test_computed_at_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        one_year_return(_daily(["100.00"]), computed_at=datetime(2026, 1, 1))  # noqa: DTZ001


def test_feature_quality_flags_reach_the_result() -> None:
    observations = _observations([Decimal("100.00")], start=_utc(2025, 1, 2))
    drifted = tuple(
        replace(
            o,
            provenance=Provenance(
                raw_object_key=PROVENANCE.raw_object_key,
                provider="yfinance",
                raw_contract_version="yfinance-ohlcv/v1",
                reference_version="skeleton-reference/v0",
            ),
        )
        for o in observations
    )
    result = one_year_return(_series_from(drifted), computed_at=COMPUTED_AT)
    assert "reference-version-drift" in result.quality_flags


# ── Determinism ───────────────────────────────────────────────────────────────


def test_same_inputs_and_versions_produce_an_identical_result() -> None:
    series = _series_at(
        [
            (_utc(2025, 1, 2), "1234.56"),
            (_utc(2026, 1, 2), "1500.00"),
        ]
    )
    first = one_year_return(series, computed_at=COMPUTED_AT)
    second = one_year_return(series, computed_at=COMPUTED_AT)
    assert first == second


def test_the_engine_does_not_mutate_the_feature_it_was_given() -> None:
    series = _daily(["100.00"] * 400)
    before = series.points
    one_year_return(series, computed_at=COMPUTED_AT)
    assert series.points == before


# ── Property-based tests (doc 11) ─────────────────────────────────────────────

_PRICES = st.decimals(
    min_value=Decimal("0.01"), max_value=Decimal("100000"), places=2, allow_nan=False
)
_SERIES = st.lists(_PRICES, min_size=366, max_size=380)


@given(prices=_SERIES)
@settings(max_examples=25)
def test_property_a_flat_series_returns_exactly_zero(prices: list[Decimal]) -> None:
    """Not "close to zero" — exactly zero. A flat series must not produce drift."""
    flat = [prices[0]] * len(prices)
    result = one_year_return(_series_from(_observations(flat)), computed_at=COMPUTED_AT)
    assert result.status is ResultStatus.AVAILABLE
    assert result.value == Ratio(0.0)


_SCALES = st.decimals(min_value=Decimal("0.5"), max_value=Decimal("1000"), places=2)
_BUMPS = st.decimals(min_value=Decimal("0.01"), max_value=Decimal("500"), places=2)


@given(prices=_SERIES, scale=_SCALES)
@settings(max_examples=25)
def test_property_the_return_is_invariant_to_the_scale_of_the_prices(
    prices: list[Decimal], scale: Decimal
) -> None:
    """Currency-scale invariance — the property that guards the C3 seam.

    Re-denominating every price (paise to rupees, a different currency, a share
    split applied uniformly) must not move a ratio. If the decimal→float conversion
    introduced a scale-dependent error, this is where it surfaces.
    """
    base = one_year_return(_series_from(_observations(prices)), computed_at=COMPUTED_AT)
    scaled = one_year_return(
        _series_from(_observations([price * scale for price in prices])),
        computed_at=COMPUTED_AT,
    )
    assert base.status is scaled.status is ResultStatus.AVAILABLE
    assert isinstance(base.value, Ratio)
    assert isinstance(scaled.value, Ratio)
    assert scaled.value.value == pytest.approx(base.value.value, rel=1e-9, abs=1e-12)


@given(prices=_SERIES)
@settings(max_examples=25)
def test_property_the_return_can_never_be_worse_than_total_loss(
    prices: list[Decimal],
) -> None:
    """With positive prices the ratio is bounded below by -1: you cannot lose more
    than everything. A sign error or an inverted division breaks this."""
    result = one_year_return(_series_from(_observations(prices)), computed_at=COMPUTED_AT)
    assert isinstance(result.value, Ratio)
    assert result.value.value >= -1.0


@given(prices=_SERIES, bump=_BUMPS)
@settings(max_examples=25)
def test_property_raising_the_final_price_raises_the_return(
    prices: list[Decimal], bump: Decimal
) -> None:
    base = one_year_return(_series_from(_observations(prices)), computed_at=COMPUTED_AT)
    raised = one_year_return(
        _series_from(_observations([*prices[:-1], prices[-1] + bump])), computed_at=COMPUTED_AT
    )
    assert isinstance(base.value, Ratio)
    assert isinstance(raised.value, Ratio)
    assert raised.value.value > base.value.value


@given(prices=_SERIES)
@settings(max_examples=25)
def test_property_the_result_is_deterministic(prices: list[Decimal]) -> None:
    observations = _observations(prices)
    assert one_year_return(_series_from(observations), computed_at=COMPUTED_AT) == one_year_return(
        _series_from(observations), computed_at=COMPUTED_AT
    )


# ── Parity with the independent reference implementation (doc 11 B10) ─────────


@given(prices=_SERIES)
@settings(max_examples=50)
def test_parity_with_the_independent_reference_implementation(
    prices: list[Decimal],
) -> None:
    observations = _observations(prices)
    result = one_year_return(_series_from(observations), computed_at=COMPUTED_AT)
    expected = reference_one_year_return(observations, FAR_FUTURE)

    assert expected is not None
    assert result.status is ResultStatus.AVAILABLE
    assert isinstance(result.value, Ratio)
    assert result.value.value == pytest.approx(
        float(expected), rel=RATIO_RELATIVE_TOLERANCE, abs=RATIO_RELATIVE_TOLERANCE
    )


@pytest.mark.parametrize(
    "dated_prices",
    [
        [(_utc(2025, 1, 2), "100.00"), (_utc(2026, 1, 2), "120.00")],
        [(_utc(2025, 1, 2), "999.99"), (_utc(2026, 1, 5), "1000.01")],
        [(_utc(2024, 12, 20), "100.00"), (_utc(2026, 1, 5), "110.00")],
        [(_utc(2025, 1, 2), "100.00")],
    ],
    ids=["exact-anchor", "offset-anchor", "out-of-tolerance", "single-bar"],
)
def test_parity_on_the_irregular_cases_including_when_both_decline(
    dated_prices: list[tuple[datetime, str]],
) -> None:
    """Parity covers *availability* too: the two must agree on when there is no answer."""
    observations = tuple(
        _observations([Decimal(price)], start=when)[0] for when, price in dated_prices
    )
    result = one_year_return(_series_from(observations), computed_at=COMPUTED_AT)
    expected = reference_one_year_return(observations, FAR_FUTURE)

    if expected is None:
        assert result.status is ResultStatus.UNAVAILABLE
    else:
        assert isinstance(result.value, Ratio)
        assert result.value.value == pytest.approx(
            float(expected), rel=RATIO_RELATIVE_TOLERANCE, abs=RATIO_RELATIVE_TOLERANCE
        )
