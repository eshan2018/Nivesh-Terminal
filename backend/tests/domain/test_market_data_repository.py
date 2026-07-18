"""Tests for the market-data repository (L5).

These assert the *port's* contract against the SQLite backend: exact money
round-trip, idempotent writes, effective-dated versioning, the index/currency
invariant enforced at rest, and quarantine retention.
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from backend.domain.market_data.repository import MarketDataRepository
from backend.domain.market_data.schema import OBSERVATIONS_TABLE
from backend.domain.market_data.sqlite_repository import SqliteMarketDataRepository
from backend.domain.model.observations import (
    AuthorityTier,
    PriceObservation,
    Provenance,
    QuarantineRecord,
)
from backend.domain.model.quantities import Currency, IndexLevel, Money
from backend.platform.identifiers import InstrumentId

APPLE = InstrumentId("apple")
NIFTY = InstrumentId("nifty-50")
KNOWLEDGE = datetime(2025, 7, 15, 9, 30, tzinfo=UTC)
PROVENANCE = Provenance(
    raw_object_key="raw/v1/yfinance/price-history/2025-07/apple/abc.json",
    provider="yfinance",
    raw_contract_version="yfinance-ohlcv/v1",
    reference_version="skeleton-reference/v1",
)


@pytest.fixture()
def repo() -> SqliteMarketDataRepository:
    with SqliteMarketDataRepository() as repository:
        yield repository


def _money_observation(
    day: int = 1, close: str = "100.50", knowledge_time: datetime = KNOWLEDGE
) -> PriceObservation:
    return PriceObservation(
        instrument_id=APPLE,
        event_time=datetime(2025, 7, day, tzinfo=UTC),
        knowledge_time=knowledge_time,
        interval="1d",
        open=Money(Decimal("100.00"), Currency.USD),
        high=Money(Decimal("110.00"), Currency.USD),
        low=Money(Decimal("90.00"), Currency.USD),
        close=Money(Decimal(close), Currency.USD),
        volume=Decimal("1000"),
        authority=AuthorityTier.AUTHORITATIVE,
        quality_flags=("stale-series",),
        provenance=PROVENANCE,
    )


def _index_observation(day: int = 1) -> PriceObservation:
    level = IndexLevel(Decimal("24500.75"))
    return PriceObservation(
        instrument_id=NIFTY,
        event_time=datetime(2025, 7, day, tzinfo=UTC),
        knowledge_time=KNOWLEDGE,
        interval="1d",
        open=level,
        high=level,
        low=level,
        close=level,
        volume=None,
        authority=AuthorityTier.AUTHORITATIVE,
        quality_flags=(),
        provenance=PROVENANCE,
    )


# ── Port conformance and round-trip ───────────────────────────────────────────

def test_implements_the_port(repo: SqliteMarketDataRepository) -> None:
    assert isinstance(repo, MarketDataRepository)


def test_observation_round_trips_exactly(repo: SqliteMarketDataRepository) -> None:
    original = _money_observation()
    assert repo.save_observations([original]) == 1

    (stored,) = repo.get_observations(APPLE, interval="1d")
    assert stored == original  # frozen dataclasses compare by value


def test_money_survives_as_exact_decimal_not_float(repo: SqliteMarketDataRepository) -> None:
    repo.save_observations([_money_observation(close="0.1")])
    (stored,) = repo.get_observations(APPLE, interval="1d")
    assert isinstance(stored.close, Money)
    assert stored.close.amount == Decimal("0.1")
    assert str(stored.close.amount) == "0.1"  # not 0.1000000000000000055511151231257827


def test_index_round_trips_without_a_currency(repo: SqliteMarketDataRepository) -> None:
    repo.save_observations([_index_observation()])
    (stored,) = repo.get_observations(NIFTY, interval="1d")
    assert isinstance(stored.close, IndexLevel)
    assert stored.close.points == Decimal("24500.75")
    assert not hasattr(stored.close, "currency")


def test_volume_and_flags_round_trip(repo: SqliteMarketDataRepository) -> None:
    repo.save_observations([_money_observation(), _index_observation()])
    (apple,) = repo.get_observations(APPLE, interval="1d")
    (nifty,) = repo.get_observations(NIFTY, interval="1d")
    assert apple.volume == Decimal("1000")
    assert apple.quality_flags == ("stale-series",)
    assert nifty.volume is None
    assert nifty.quality_flags == ()


# ── Idempotency and effective-dated versioning ────────────────────────────────

def test_saving_twice_is_idempotent(repo: SqliteMarketDataRepository) -> None:
    observation = _money_observation()
    assert repo.save_observations([observation]) == 1
    assert repo.save_observations([observation]) == 0  # converges, does not duplicate
    assert len(repo.get_observations(APPLE, interval="1d")) == 1


def test_correction_creates_a_new_version_and_read_returns_the_latest(
    repo: SqliteMarketDataRepository,
) -> None:
    later = KNOWLEDGE + timedelta(days=1)
    repo.save_observations([_money_observation(close="100.50")])
    repo.save_observations([_money_observation(close="101.75", knowledge_time=later)])

    (stored,) = repo.get_observations(APPLE, interval="1d")
    assert stored.close.amount == Decimal("101.75")  # type: ignore[union-attr]
    assert stored.knowledge_time == later

    # The superseded version is retained — nothing is overwritten (principle 14).
    rows = repo._connection.execute(f"SELECT COUNT(*) FROM {OBSERVATIONS_TABLE}").fetchone()
    assert rows[0] == 2


def test_observations_are_returned_in_event_time_order(
    repo: SqliteMarketDataRepository,
) -> None:
    repo.save_observations(
        [_money_observation(day=3), _money_observation(day=1), _money_observation(day=2)]
    )
    days = [o.event_time.day for o in repo.get_observations(APPLE, interval="1d")]
    assert days == [1, 2, 3]


def test_reads_are_scoped_by_instrument_and_interval(repo: SqliteMarketDataRepository) -> None:
    repo.save_observations([_money_observation(), _index_observation()])
    assert len(repo.get_observations(APPLE, interval="1d")) == 1
    assert repo.get_observations(APPLE, interval="1wk") == ()
    assert repo.get_observations(InstrumentId("unknown"), interval="1d") == ()


def test_empty_save_is_a_no_op(repo: SqliteMarketDataRepository) -> None:
    assert repo.save_observations([]) == 0
    assert repo.save_quarantined([]) == 0


# ── The index/currency invariant is enforced at rest ──────────────────────────

def test_database_rejects_an_index_level_carrying_a_currency(
    repo: SqliteMarketDataRepository,
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        repo._connection.execute(
            f"INSERT INTO {OBSERVATIONS_TABLE} (instrument_id, interval, event_time, "
            "knowledge_time, value_kind, currency, open_value, high_value, low_value, "
            "close_value, volume, authority, quality_flags, raw_object_key, provider, "
            "raw_contract_version, reference_version) VALUES "
            "('nifty-50','1d','2025-07-01T00:00:00+00:00','2025-07-15T09:30:00+00:00',"
            "'INDEX_LEVEL','INR','1','1','1','1',NULL,'AUTHORITATIVE','[]','k','p','c','r')"
        )


# ── Quarantine retention ──────────────────────────────────────────────────────

def _quarantine_record(timestamp: str = "not-a-date") -> QuarantineRecord:
    return QuarantineRecord(
        instrument_id=APPLE,
        raw_timestamp=timestamp,
        reasons=("unparseable timestamp 'not-a-date'",),
        payload_json='{"close":null}',
        quarantined_at=KNOWLEDGE,
        provenance=PROVENANCE,
    )


def test_quarantined_records_are_retained_and_idempotent(
    repo: SqliteMarketDataRepository,
) -> None:
    record = _quarantine_record()
    assert repo.save_quarantined([record]) == 1
    assert repo.save_quarantined([record]) == 0

    (stored,) = repo.get_quarantined(APPLE)
    assert stored.raw_timestamp == "not-a-date"
    assert stored.reasons == record.reasons
    assert stored.payload_json == record.payload_json


def test_quarantine_requires_a_reason() -> None:
    with pytest.raises(ValueError, match="at least one reason"):
        QuarantineRecord(
            instrument_id=APPLE,
            raw_timestamp="x",
            reasons=(),
            payload_json="{}",
            quarantined_at=KNOWLEDGE,
            provenance=PROVENANCE,
        )


# ── Durability ────────────────────────────────────────────────────────────────

def test_data_survives_reopening_the_database(tmp_path: Path) -> None:
    database = tmp_path / "market_data.sqlite3"
    with SqliteMarketDataRepository(database) as first:
        first.save_observations([_money_observation()])
    with SqliteMarketDataRepository(database) as second:
        (stored,) = second.get_observations(APPLE, interval="1d")
    assert stored.close.amount == Decimal("100.50")  # type: ignore[union-attr]
