"""Return-series features for portfolio intelligence (L6, doc 08).

Two features, versioned separately because they fail in different ways:

* **`return_series`** — one instrument's periodic returns. A thin, well-understood
  derivation from the close-price series.
* **`aligned_return_matrix`** — several instruments' returns on a *common* set of dates.
  This is where portfolio correctness quietly dies. Two holdings listed at different
  times, a trading halt, a late-listed stock: any of these leaves gaps, and the
  tempting repairs — forward-filling, zero-filling, interpolating — all invent returns
  that never happened. A fabricated return is exactly as dishonest as a fabricated
  price (principle 13), and it flows straight into volatility and correlation where it
  is invisible.

  So the matrix **intersects** dates rather than filling them, reports the window it
  actually used, and refuses when the overlap is too short to support the statistics
  built on it.

Both features consume `close_price_series`, so the single decimal→float seam (C3)
remains where it is — in `returns.py` — and is not duplicated here.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from backend.domain.market_data.repository import MarketDataRepository
from backend.domain.model.analytics import FeatureRef, ObservationRef
from backend.domain.model.instruments import (
    InstrumentReference,
    InstrumentType,
    reference_for,
)
from backend.features.returns import ClosePriceSeries, build_close_price_series
from backend.platform.identifiers import InstrumentId

RETURN_SERIES_ID = "return_series"
RETURN_SERIES_VERSION = "return-series/v1"

ALIGNED_MATRIX_ID = "aligned_return_matrix"
ALIGNED_MATRIX_VERSION = "aligned-return-matrix/v1"

ALIGNED_REFERENCE_ID = "aligned_reference_return_series"
ALIGNED_REFERENCE_VERSION = "aligned-reference-return-series/v1"

#: The minimum number of overlapping observations before the matrix will report a
#: window at all.
#:
#: **Derived, not chosen.** For returns treated as independent draws, the relative
#: standard error of a sample volatility estimate is approximately ``1/sqrt(2(n-1))``.
#: At n=50 that is ~10% — i.e. a "20% volatility" reading is really 20% ± 2%. Below
#: that the number is too imprecise to put in front of an investor at all.
#:
#: **It is a floor, not a guarantee.** Real returns have fat tails and volatility
#: clustering, so the true error is worse than the i.i.d. approximation. That is why
#: the actual relative standard error is *published* with every result rather than
#: left implicit — the threshold decides whether to answer, the published figure says
#: how much to trust the answer.
MIN_OVERLAP_OBSERVATIONS = 50

#: Instrument kinds a portfolio may hold.
#:
#: Equities and ETFs share the property the return model needs: a continuous, ownable
#: price series whose changes are the holder's actual gain or loss. An **index** is
#: excluded — nobody holds an index. Its level is a unitless statistic; treating it as
#: a holding would report the index's movement as an investor's return, silently
#: omitting the tracking error, fees and dividend treatment of whatever fund they
#: really own.
PORTFOLIO_SUPPORTED_TYPES: frozenset[InstrumentType] = frozenset(
    {InstrumentType.EQUITY, InstrumentType.ETF}
)


@dataclass(frozen=True, slots=True)
class ReturnPoint:
    """One period's simple return, and the date it ended on."""

    event_time: datetime
    value: float


@dataclass(frozen=True, slots=True)
class ReturnSeries:
    """One instrument's periodic simple returns, versioned and lineage-carrying."""

    instrument_id: InstrumentId
    interval: str
    as_of: datetime
    points: tuple[ReturnPoint, ...]
    quality_flags: tuple[str, ...]
    reference_version: str
    lineage: FeatureRef


@dataclass(frozen=True, slots=True)
class AlignedReturnMatrix:
    """Several instruments' returns over a common set of dates.

    `columns` is ordered to match `instrument_ids`, and every column has the same
    length as `dates`. If that invariant fails, downstream covariance is meaningless,
    so it is asserted at construction rather than trusted.
    """

    instrument_ids: tuple[InstrumentId, ...]
    dates: tuple[datetime, ...]
    columns: tuple[tuple[float, ...], ...]
    as_of: datetime
    interval: str
    quality_flags: tuple[str, ...]
    reference_version: str
    lineage: tuple[FeatureRef, ...]

    def __post_init__(self) -> None:
        if len(self.columns) != len(self.instrument_ids):
            raise ValueError("one column per instrument is required")
        for column in self.columns:
            if len(column) != len(self.dates):
                raise ValueError("every column must span exactly the aligned dates")

    @property
    def observation_count(self) -> int:
        return len(self.dates)

    def window(self) -> tuple[datetime, datetime] | None:
        """The first and last aligned dates, or `None` when empty."""
        if not self.dates:
            return None
        return self.dates[0], self.dates[-1]


def build_return_series(
    repository: MarketDataRepository,
    instrument_id: InstrumentId,
    *,
    as_of: datetime,
    interval: str = "1d",
) -> ReturnSeries:
    """Periodic simple returns for one instrument: `(P_t / P_{t-1}) - 1`.

    A series of N prices yields N-1 returns; the first price anchors the first return
    rather than producing one of its own. A zero price would make the return undefined,
    so that period is dropped and flagged rather than reported as a fabricated number
    (the gate already rejects non-positive prices, so this guards a data-quality
    regression rather than an expected case).
    """
    prices = build_close_price_series(
        repository, instrument_id, as_of=as_of, interval=interval
    )
    return return_series_from(prices)


def return_series_from(prices: ClosePriceSeries) -> ReturnSeries:
    """Derive returns from an already-built close-price series.

    Separated so the engine layer can compose features it already holds without
    re-reading the repository — L6 remains the only layer that touches storage.
    """
    points: list[ReturnPoint] = []
    inputs: list[ObservationRef] = []
    flags = set(prices.quality_flags)

    for index in range(1, len(prices.points)):
        previous, current = prices.points[index - 1], prices.points[index]
        if previous.price == 0.0:
            flags.add("undefined-return-zero-denominator")
            continue
        points.append(
            ReturnPoint(
                event_time=current.event_time,
                value=current.price / previous.price - 1.0,
            )
        )
        inputs.append(prices.input_for(index))

    return ReturnSeries(
        instrument_id=prices.instrument_id,
        interval=prices.interval,
        as_of=prices.as_of,
        points=tuple(points),
        quality_flags=tuple(sorted(flags)),
        reference_version=prices.reference_version,
        lineage=FeatureRef(
            feature_id=RETURN_SERIES_ID,
            feature_version=RETURN_SERIES_VERSION,
            inputs=tuple(inputs),
            parameters=(("interval", prices.interval),),
        ),
    )


def build_aligned_reference_returns(
    repository: MarketDataRepository,
    reference_id: InstrumentId,
    dates: Sequence[datetime],
    *,
    as_of: datetime,
    interval: str = "1d",
) -> ReturnSeries:
    """A *reference* instrument's returns, restricted to dates a portfolio also has.

    **Why this exists rather than adding the reference as a matrix column.** The matrix
    is a portfolio structure: engines iterate its columns against holding weights, so a
    non-holding column would have to be special-cased inside the very place that mistake
    would be invisible. A reference is not a holding — it is the thing a portfolio is
    compared *against* — and an index is not ownable at all
    (`PORTFOLIO_SUPPORTED_TYPES` excludes it, deliberately).

    **Why the dates are an input.** Comparing two volatilities computed over different
    windows compares two different questions. The caller supplies the portfolio's own
    aligned dates and this restricts the reference to exactly them, so the comparison is
    like-for-like by construction rather than by the caller remembering.

    Intersection, never fill — the same rule the matrix follows. A date the reference
    lacks is dropped rather than invented, and the shortfall is flagged so a comparison
    computed over fewer periods than requested says so.
    """
    series = build_return_series(repository, reference_id, as_of=as_of, interval=interval)
    wanted = set(dates)
    by_date = {point.event_time: point for point in series.points}
    kept = tuple(by_date[date] for date in sorted(wanted & set(by_date)))

    flags = set(series.quality_flags)
    if len(kept) < len(wanted):
        flags.add("reference-window-shortened-by-alignment")

    inputs = {
        point.event_time: ref
        for point, ref in zip(series.points, series.lineage.inputs, strict=True)
    }
    return ReturnSeries(
        instrument_id=series.instrument_id,
        interval=series.interval,
        as_of=series.as_of,
        points=kept,
        quality_flags=tuple(sorted(flags)),
        reference_version=series.reference_version,
        lineage=FeatureRef(
            feature_id=ALIGNED_REFERENCE_ID,
            feature_version=ALIGNED_REFERENCE_VERSION,
            inputs=tuple(inputs[point.event_time] for point in kept),
            parameters=(
                ("interval", series.interval),
                ("reference_instrument", reference_id.value),
            ),
        ),
    )


def portfolio_matrix_provider(
    repository: MarketDataRepository,
) -> Callable[..., AlignedReturnMatrix]:
    """Bind the repository into the matrix feature (ED-011).

    The repository is held inside the only layer permitted to hold one; callers above
    receive a function and never see storage.
    """
    def provide(
        instrument_ids: Sequence[InstrumentId],
        as_of: datetime,
        restrict_to: Sequence[datetime] | None = None,
    ) -> AlignedReturnMatrix:
        return build_aligned_return_matrix(
            repository, instrument_ids, as_of=as_of, restrict_to=restrict_to
        )

    return provide


def aligned_reference_provider(
    repository: MarketDataRepository,
) -> Callable[[InstrumentId, Sequence[datetime], datetime], ReturnSeries]:
    """Bind the repository into the aligned-reference feature (ED-011)."""
    def provide(
        reference_id: InstrumentId, dates: Sequence[datetime], as_of: datetime
    ) -> ReturnSeries:
        return build_aligned_reference_returns(repository, reference_id, dates, as_of=as_of)

    return provide


def supported_for_portfolio(reference: InstrumentReference) -> bool:
    """Whether this instrument may be held in a portfolio (see the type set above)."""
    return reference.type in PORTFOLIO_SUPPORTED_TYPES


def build_aligned_return_matrix(
    repository: MarketDataRepository,
    instrument_ids: Sequence[InstrumentId],
    *,
    as_of: datetime,
    interval: str = "1d",
    restrict_to: Sequence[datetime] | None = None,
) -> AlignedReturnMatrix:
    """Returns for several instruments, restricted to dates every instrument has.

    Alignment is an intersection, never a fill. A date missing for one holding is
    dropped for all of them: the alternative is inventing that holding's return, which
    would flow into covariance undetected.

    `restrict_to` narrows the result further, to dates some *other* series also has. It
    exists because comparing a portfolio against a reference needs the intersection of
    both, and a reference does not trade on exactly the holdings' calendar — the Nifty 50
    has four fewer usable days than a four-stock portfolio over a year of real data. A
    one-directional alignment can therefore never match, which is a comparison over two
    different windows wearing the appearance of one.
    """
    if not instrument_ids:
        raise ValueError("a portfolio needs at least one instrument")

    series = [
        build_return_series(repository, instrument_id, as_of=as_of, interval=interval)
        for instrument_id in instrument_ids
    ]

    by_instrument = [{point.event_time: point.value for point in s.points} for s in series]
    common = set(by_instrument[0])
    for mapping in by_instrument[1:]:
        common &= set(mapping)
    if restrict_to is not None:
        common &= set(restrict_to)
    dates = tuple(sorted(common))

    flags = {flag for s in series for flag in s.quality_flags}
    # Say so when alignment discarded data: a portfolio measured over a much shorter
    # window than its longest holding is a materially different statement, and the
    # investor should be able to see that happened.
    if any(len(mapping) > len(dates) for mapping in by_instrument):
        flags.add("window-shortened-by-alignment")

    return AlignedReturnMatrix(
        instrument_ids=tuple(instrument_ids),
        dates=dates,
        columns=tuple(
            tuple(mapping[date] for date in dates) for mapping in by_instrument
        ),
        as_of=as_of,
        interval=interval,
        quality_flags=tuple(sorted(flags)),
        reference_version=series[0].reference_version,
        lineage=tuple(s.lineage for s in series),
    )


def portfolio_instrument_references(
    instrument_ids: Sequence[InstrumentId],
) -> tuple[InstrumentReference, ...]:
    """Resolve reference data for holdings, raising `UnknownInstrument` on a bad id."""
    return tuple(reference_for(instrument_id) for instrument_id in instrument_ids)
