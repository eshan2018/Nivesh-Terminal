"""Tests for the close-price series feature (L6).

Three concerns, in order of how much damage a defect would do: the C3 decimal→float
seam, the as-of/lookahead filter, and the lineage the whole explainability claim rests
on. These run against the real SQLite repository rather than a stub, because "the
feature layer reads the repository" is precisely the boundary under test.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from backend.domain.market_data.sqlite_repository import SqliteMarketDataRepository
from backend.domain.model.instruments import REFERENCE_VERSION, UnknownInstrument
from backend.domain.model.observations import (
    AuthorityTier,
    PriceObservation,
    Provenance,
)
from backend.domain.model.quantities import Currency, IndexLevel, Money
from backend.features.returns import (
    FEATURE_ID,
    FEATURE_VERSION,
    REFERENCE_DRIFT_FLAG,
    build_close_price_series,
    close_price_series_provider,
    to_float,
)
from backend.platform.identifiers import InstrumentId

APPLE = InstrumentId("apple")
NIFTY = InstrumentId("nifty-50")
DAY_ONE = datetime(2025, 1, 2, tzinfo=UTC)
KNOWLEDGE = datetime(2025, 1, 3, tzinfo=UTC)
AS_OF = datetime(2026, 1, 1, tzinfo=UTC)


def _provenance(reference_version: str = REFERENCE_VERSION, key: str = "raw/a.json") -> Provenance:
    return Provenance(
        raw_object_key=key,
        provider="yfinance",
        raw_contract_version="yfinance-ohlcv/v1",
        reference_version=reference_version,
    )


def _observation(
    *,
    day: int = 0,
    close: str = "100.25",
    knowledge_time: datetime = KNOWLEDGE,
    instrument_id: InstrumentId = APPLE,
    index: bool = False,
    quality_flags: tuple[str, ...] = (),
    provenance: Provenance | None = None,
) -> PriceObservation:
    amount = Decimal(close)
    price = IndexLevel(amount) if index else Money(amount, Currency.USD)
    return PriceObservation(
        instrument_id=instrument_id,
        event_time=DAY_ONE + timedelta(days=day),
        knowledge_time=knowledge_time,
        interval="1d",
        open=price,
        high=price,
        low=price,
        close=price,
        volume=Decimal("1000"),
        authority=AuthorityTier.AUTHORITATIVE,
        quality_flags=quality_flags,
        provenance=provenance or _provenance(),
    )


@pytest.fixture()
def repo() -> SqliteMarketDataRepository:
    with SqliteMarketDataRepository() as repository:
        yield repository


# ── The C3 seam ───────────────────────────────────────────────────────────────


def test_seam_converts_money_and_index_levels_to_float() -> None:
    assert to_float(Money(Decimal("100.25"), Currency.USD)) == 100.25
    assert to_float(IndexLevel(Decimal("24500.75"))) == 24500.75


def test_seam_rejects_anything_that_is_not_a_price_quantity() -> None:
    with pytest.raises(TypeError):
        to_float(100.25)  # type: ignore[arg-type]


def test_the_seam_has_no_inverse() -> None:
    """Float→money is forbidden (C3), and the Money type is what enforces it."""
    ratio_like_float = to_float(Money(Decimal("100.25"), Currency.USD))
    with pytest.raises(TypeError, match="never a float"):
        Money(ratio_like_float, Currency.USD)  # type: ignore[arg-type]


def test_series_carries_floats_past_the_seam(repo: SqliteMarketDataRepository) -> None:
    repo.save_observations([_observation(close="123.45")])
    series = build_close_price_series(repo, APPLE, as_of=AS_OF)
    assert [type(point.price) for point in series.points] == [float]
    assert series.points[0].price == 123.45


def test_index_levels_survive_the_seam_without_acquiring_a_currency(
    repo: SqliteMarketDataRepository,
) -> None:
    repo.save_observations([_observation(instrument_id=NIFTY, close="24500.75", index=True)])
    series = build_close_price_series(repo, NIFTY, as_of=AS_OF)
    assert series.points[0].price == 24500.75


# ── As-of / lookahead-freedom ─────────────────────────────────────────────────


def test_excludes_observations_learned_after_as_of(repo: SqliteMarketDataRepository) -> None:
    """The knowledge_time half of the cutoff — what keeps a backtest honest."""
    repo.save_observations(
        [
            _observation(day=0, close="100"),
            _observation(day=1, close="200", knowledge_time=AS_OF + timedelta(days=1)),
        ]
    )
    series = build_close_price_series(repo, APPLE, as_of=AS_OF)
    assert [point.price for point in series.points] == [100.0]


def test_excludes_bars_dated_after_as_of(repo: SqliteMarketDataRepository) -> None:
    repo.save_observations(
        [
            _observation(day=0, close="100"),
            _observation(day=800, close="200", knowledge_time=DAY_ONE),
        ]
    )
    series = build_close_price_series(repo, APPLE, as_of=AS_OF)
    assert [point.price for point in series.points] == [100.0]


def test_points_are_ordered_by_event_time(repo: SqliteMarketDataRepository) -> None:
    repo.save_observations([_observation(day=day) for day in (5, 1, 3)])
    series = build_close_price_series(repo, APPLE, as_of=AS_OF)
    times = [point.event_time for point in series.points]
    assert times == sorted(times)


def test_as_of_must_be_timezone_aware(repo: SqliteMarketDataRepository) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        build_close_price_series(repo, APPLE, as_of=datetime(2026, 1, 1))  # noqa: DTZ001


def test_an_unknown_instrument_raises_rather_than_reporting_no_data(
    repo: SqliteMarketDataRepository,
) -> None:
    """A typo'd id and a known instrument with no data are different answers.

    Reporting the former as an empty series would tell a user "we have no prices for
    this" when the truth is "no such instrument" — and would leave M4 unable to tell
    a 404 from a legitimate `Unavailable`.
    """
    with pytest.raises(UnknownInstrument):
        build_close_price_series(repo, InstrumentId("no-such-thing"), as_of=AS_OF)


def test_a_known_instrument_with_no_data_yields_an_empty_series(
    repo: SqliteMarketDataRepository,
) -> None:
    """Absence *is* a legitimate answer here; the engine turns it into `Unavailable`."""
    series = build_close_price_series(repo, APPLE, as_of=AS_OF)
    assert series.points == ()
    assert series.lineage.inputs == ()


# ── Versioning and lineage ────────────────────────────────────────────────────


def test_series_pins_its_feature_and_reference_versions(
    repo: SqliteMarketDataRepository,
) -> None:
    repo.save_observations([_observation()])
    series = build_close_price_series(repo, APPLE, as_of=AS_OF)
    assert series.feature_id == FEATURE_ID
    assert series.feature_version == FEATURE_VERSION
    assert series.reference_version == REFERENCE_VERSION


def test_lineage_pins_the_parameters_the_feature_was_called_with(
    repo: SqliteMarketDataRepository,
) -> None:
    """Naming the inputs is not enough — the *call* has to be reproducible too.

    Without this, a daily and a weekly series over the same instrument produce
    lineage that cannot be told apart.
    """
    repo.save_observations([_observation()])
    series = build_close_price_series(repo, APPLE, as_of=AS_OF, interval="1d")
    assert series.lineage.parameters == (("interval", "1d"),)


def test_points_and_lineage_inputs_stay_index_aligned(
    repo: SqliteMarketDataRepository,
) -> None:
    """The invariant the engine relies on to name its contributing inputs.

    If these two ever drift apart, an engine would cite the wrong canonical fact as
    the source of a number — lineage that is confidently wrong, which is worse than
    lineage that is absent.
    """
    repo.save_observations([_observation(day=day, close=f"{100 + day}.00") for day in range(5)])
    series = build_close_price_series(repo, APPLE, as_of=AS_OF)

    assert len(series.points) == len(series.lineage.inputs) == 5
    for index, point in enumerate(series.points):
        assert series.input_for(index).event_time == point.event_time


def test_a_bound_provider_yields_the_same_series_as_a_direct_call(
    repo: SqliteMarketDataRepository,
) -> None:
    """The L6 contract L7 consumes must be the feature itself, not a variant of it."""
    repo.save_observations([_observation(day=day) for day in range(3)])
    provider = close_price_series_provider(repo)
    assert provider(APPLE, AS_OF) == build_close_price_series(repo, APPLE, as_of=AS_OF)


def test_lineage_names_every_observation_consumed(repo: SqliteMarketDataRepository) -> None:
    repo.save_observations(
        [
            _observation(day=0, provenance=_provenance(key="raw/one.json")),
            _observation(day=1, provenance=_provenance(key="raw/two.json")),
        ]
    )
    series = build_close_price_series(repo, APPLE, as_of=AS_OF)

    assert len(series.lineage.inputs) == len(series.points)
    assert [ref.event_time for ref in series.lineage.inputs] == [
        point.event_time for point in series.points
    ]
    assert {ref.provenance.raw_object_key for ref in series.lineage.inputs} == {
        "raw/one.json",
        "raw/two.json",
    }


def test_lineage_excludes_observations_the_filter_dropped(
    repo: SqliteMarketDataRepository,
) -> None:
    """Lineage must describe what was used, not what was available."""
    repo.save_observations(
        [
            _observation(day=0, provenance=_provenance(key="raw/used.json")),
            _observation(
                day=1,
                knowledge_time=AS_OF + timedelta(days=1),
                provenance=_provenance(key="raw/unseen.json"),
            ),
        ]
    )
    series = build_close_price_series(repo, APPLE, as_of=AS_OF)
    keys = {ref.provenance.raw_object_key for ref in series.lineage.inputs}
    assert keys == {"raw/used.json"}


def test_quality_flags_propagate_from_observations(repo: SqliteMarketDataRepository) -> None:
    repo.save_observations(
        [
            _observation(day=0, quality_flags=("sparse-series",)),
            _observation(day=1, quality_flags=("wide-spread",)),
        ]
    )
    series = build_close_price_series(repo, APPLE, as_of=AS_OF)
    assert series.quality_flags == ("sparse-series", "wide-spread")


def test_reference_drift_is_flagged_not_silently_accepted(
    repo: SqliteMarketDataRepository,
) -> None:
    repo.save_observations(
        [_observation(provenance=_provenance(reference_version="skeleton-reference/v0"))]
    )
    series = build_close_price_series(repo, APPLE, as_of=AS_OF)
    assert REFERENCE_DRIFT_FLAG in series.quality_flags


def test_matching_reference_versions_raise_no_flag(repo: SqliteMarketDataRepository) -> None:
    repo.save_observations([_observation()])
    series = build_close_price_series(repo, APPLE, as_of=AS_OF)
    assert REFERENCE_DRIFT_FLAG not in series.quality_flags
