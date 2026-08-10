"""Return-series and alignment features (L6).

Alignment gets the most attention here because it is the quietest failure mode in the
whole portfolio path: a forward-filled or zero-filled gap produces a *plausible* number
that is wrong in the direction of understating risk, and nothing downstream can detect
it. These tests pin the refusal to fill.
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from backend.domain.market_data.sqlite_repository import SqliteMarketDataRepository
from backend.domain.model.instruments import (
    REFERENCE_VERSION,
    InstrumentReference,
    InstrumentType,
)
from backend.domain.model.observations import AuthorityTier, PriceObservation, Provenance
from backend.domain.model.quantities import Currency, Money
from backend.features.portfolio_returns import (
    ALIGNED_MATRIX_VERSION,
    MIN_OVERLAP_OBSERVATIONS,
    RETURN_SERIES_VERSION,
    build_aligned_return_matrix,
    build_return_series,
    supported_for_portfolio,
)
from backend.platform.identifiers import InstrumentId

RELIANCE = InstrumentId("reliance")
TCS = InstrumentId("tcs")
START = datetime(2025, 1, 1, tzinfo=UTC)
AS_OF = datetime(2027, 1, 1, tzinfo=UTC)
PROVENANCE = Provenance(
    raw_object_key="raw/v1/yfinance/price-history/2025-01/x/abc.json",
    provider="yfinance",
    raw_contract_version="yfinance-ohlcv/v1",
    reference_version=REFERENCE_VERSION,
)


def _observation(instrument: InstrumentId, day: int, close: str) -> PriceObservation:
    price = Money(Decimal(close), Currency.INR)
    event_time = START + timedelta(days=day)
    return PriceObservation(
        instrument_id=instrument,
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


@pytest.fixture()
def repo() -> Iterator[SqliteMarketDataRepository]:
    with SqliteMarketDataRepository() as repository:
        yield repository


# ── return_series ─────────────────────────────────────────────────────────────


def test_returns_are_period_over_period(repo: SqliteMarketDataRepository) -> None:
    repo.save_observations([
        _observation(RELIANCE, 0, "100"),
        _observation(RELIANCE, 1, "110"),
        _observation(RELIANCE, 2, "99"),
    ])

    series = build_return_series(repo, RELIANCE, as_of=AS_OF)

    assert [round(p.value, 10) for p in series.points] == [0.1, -0.1]


def test_n_prices_yield_n_minus_one_returns(repo: SqliteMarketDataRepository) -> None:
    """The first price anchors the first return; it does not produce one of its own."""
    repo.save_observations([_observation(RELIANCE, day, "100") for day in range(10)])

    assert len(build_return_series(repo, RELIANCE, as_of=AS_OF).points) == 9


def test_a_single_price_yields_no_returns(repo: SqliteMarketDataRepository) -> None:
    repo.save_observations([_observation(RELIANCE, 0, "100")])
    assert build_return_series(repo, RELIANCE, as_of=AS_OF).points == ()


def test_returns_are_dated_by_the_period_end(repo: SqliteMarketDataRepository) -> None:
    """A return belongs to the day it was realized, not the day it started."""
    repo.save_observations([_observation(RELIANCE, 0, "100"), _observation(RELIANCE, 1, "110")])

    (point,) = build_return_series(repo, RELIANCE, as_of=AS_OF).points

    assert point.event_time == START + timedelta(days=1)


def test_the_series_pins_its_version_and_inputs(repo: SqliteMarketDataRepository) -> None:
    repo.save_observations([_observation(RELIANCE, day, "100") for day in range(3)])

    series = build_return_series(repo, RELIANCE, as_of=AS_OF)

    assert series.lineage.feature_version == RETURN_SERIES_VERSION
    assert len(series.lineage.inputs) == len(series.points)
    assert series.reference_version == REFERENCE_VERSION


# ── alignment ─────────────────────────────────────────────────────────────────


def test_alignment_intersects_dates_rather_than_filling_gaps(
    repo: SqliteMarketDataRepository,
) -> None:
    """The central correctness property of the whole portfolio path.

    TCS is missing day 2. Filling it — forward-fill, zero-fill, interpolate — would
    invent a return that never happened and understate the portfolio's measured risk.
    The date must be dropped for both holdings instead.
    """
    repo.save_observations(
        [_observation(RELIANCE, day, str(100 + day)) for day in range(5)]
        + [_observation(TCS, day, str(200 + day)) for day in (0, 1, 3, 4)]
    )

    matrix = build_aligned_return_matrix(repo, [RELIANCE, TCS], as_of=AS_OF)

    # TCS has returns on days 1, 3(from 1), 4; Reliance on 1,2,3,4. Common: 1, 3, 4.
    assert matrix.dates == tuple(START + timedelta(days=d) for d in (1, 3, 4))
    assert all(len(column) == len(matrix.dates) for column in matrix.columns)


def test_alignment_flags_that_it_shortened_the_window(
    repo: SqliteMarketDataRepository,
) -> None:
    """Losing history is a material fact about the answer, so it is surfaced."""
    repo.save_observations(
        [_observation(RELIANCE, day, str(100 + day)) for day in range(6)]
        + [_observation(TCS, day, str(200 + day)) for day in (0, 1, 2)]
    )

    matrix = build_aligned_return_matrix(repo, [RELIANCE, TCS], as_of=AS_OF)

    assert "window-shortened-by-alignment" in matrix.quality_flags


def test_identical_histories_raise_no_shortening_flag(
    repo: SqliteMarketDataRepository,
) -> None:
    repo.save_observations(
        [_observation(RELIANCE, day, str(100 + day)) for day in range(5)]
        + [_observation(TCS, day, str(200 + day)) for day in range(5)]
    )

    matrix = build_aligned_return_matrix(repo, [RELIANCE, TCS], as_of=AS_OF)

    assert "window-shortened-by-alignment" not in matrix.quality_flags


def test_disjoint_histories_produce_an_empty_window(
    repo: SqliteMarketDataRepository,
) -> None:
    """No overlap is not an error here — the engine turns it into a stated refusal."""
    repo.save_observations(
        [_observation(RELIANCE, day, str(100 + day)) for day in range(3)]
        + [_observation(TCS, day, str(200 + day)) for day in range(50, 53)]
    )

    matrix = build_aligned_return_matrix(repo, [RELIANCE, TCS], as_of=AS_OF)

    assert matrix.observation_count == 0
    assert matrix.window() is None


def test_columns_stay_ordered_with_their_instruments(
    repo: SqliteMarketDataRepository,
) -> None:
    """A transposed or reordered column silently attributes one stock's risk to another."""
    repo.save_observations(
        [_observation(RELIANCE, day, str(100 * (day + 1))) for day in range(3)]
        + [_observation(TCS, day, "200") for day in range(3)]
    )

    matrix = build_aligned_return_matrix(repo, [TCS, RELIANCE], as_of=AS_OF)

    assert matrix.instrument_ids == (TCS, RELIANCE)
    assert matrix.columns[0] == (0.0, 0.0)          # TCS is flat
    assert matrix.columns[1][0] == pytest.approx(1.0)  # Reliance doubled


def test_the_matrix_carries_one_feature_ref_per_holding(
    repo: SqliteMarketDataRepository,
) -> None:
    repo.save_observations(
        [_observation(RELIANCE, day, "100") for day in range(3)]
        + [_observation(TCS, day, "200") for day in range(3)]
    )

    matrix = build_aligned_return_matrix(repo, [RELIANCE, TCS], as_of=AS_OF)

    assert len(matrix.lineage) == 2
    assert {ref.feature_version for ref in matrix.lineage} == {RETURN_SERIES_VERSION}


def test_an_empty_holdings_list_is_a_caller_error(repo: SqliteMarketDataRepository) -> None:
    with pytest.raises(ValueError, match="at least one instrument"):
        build_aligned_return_matrix(repo, [], as_of=AS_OF)


def test_the_matrix_rejects_ragged_columns() -> None:
    """The invariant covariance depends on, asserted at construction."""
    from backend.domain.model.analytics import FeatureRef
    from backend.features.portfolio_returns import AlignedReturnMatrix

    with pytest.raises(ValueError, match="span exactly the aligned dates"):
        AlignedReturnMatrix(
            instrument_ids=(RELIANCE,),
            dates=(START, START + timedelta(days=1)),
            columns=((0.1,),),
            as_of=AS_OF,
            interval="1d",
            quality_flags=(),
            reference_version=REFERENCE_VERSION,
            lineage=(FeatureRef(RETURN_SERIES_ID_FOR_TEST, ALIGNED_MATRIX_VERSION, ()),),
        )


RETURN_SERIES_ID_FOR_TEST = "return_series"


# ── supported asset classes ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("kind", "currency", "supported"),
    [
        (InstrumentType.EQUITY, Currency.INR, True),
        (InstrumentType.ETF, Currency.INR, True),
        (InstrumentType.INDEX, None, False),
    ],
    ids=["equity", "etf", "index"],
)
def test_portfolios_hold_ownable_instruments_only(
    kind: InstrumentType, currency: Currency | None, supported: bool
) -> None:
    """An ETF is ownable and behaves like an equity; an index is a statistic."""
    reference = InstrumentReference(InstrumentId("x"), "X", kind, currency, "XNSE")
    assert supported_for_portfolio(reference) is supported


def test_the_overlap_threshold_is_derived_not_arbitrary() -> None:
    """50 observations is the point where volatility's relative standard error is ~10%.

    Pinned so the constant cannot drift away from the derivation documented alongside it.
    """
    from backend.analytics.portfolio_risk_return import volatility_relative_standard_error

    assert MIN_OVERLAP_OBSERVATIONS == 50
    assert volatility_relative_standard_error(MIN_OVERLAP_OBSERVATIONS) == pytest.approx(
        0.101, abs=0.001
    )
