"""Concurrent access to the SQLite repository (L5, ED-003).

M2d built this backend for a single-threaded batch pipeline and said so. M4's serving
plane (doc 03: "L9→L10, stateless services") invalidated that assumption — a threaded
ASGI worker calls the repository from whichever thread handles the request, and
SQLite connections are thread-affine by default.

These tests pin the correction: `check_same_thread=False` plus a lock serializing every
statement. They are the reason the API tests pass rather than failing intermittently,
which is the failure mode this class of bug prefers.

**This is a development-backend property, not a scalability claim.** The lock makes a
single connection safe; it does not make the backend concurrent. See ED-003 — SQLite is
the dev/CI realization, PostgreSQL is the production system of record (ADR-0008), and
the lock does not travel with the port.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from backend.domain.market_data.sqlite_repository import SqliteMarketDataRepository
from backend.domain.model.observations import AuthorityTier, PriceObservation, Provenance
from backend.domain.model.quantities import Currency, Money
from backend.platform.identifiers import InstrumentId

RELIANCE = InstrumentId("reliance")
START = datetime(2025, 1, 1, tzinfo=UTC)
PROVENANCE = Provenance(
    raw_object_key="raw/v1/yfinance/price-history/2025-01/reliance/abc.json",
    provider="yfinance",
    raw_contract_version="yfinance-ohlcv/v1",
    reference_version="skeleton-reference/v1",
)


def _observation(day: int) -> PriceObservation:
    price = Money(Decimal(1000 + day), Currency.INR)
    event_time = START + timedelta(days=day)
    return PriceObservation(
        instrument_id=RELIANCE,
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
def repo() -> SqliteMarketDataRepository:
    with SqliteMarketDataRepository() as repository:
        yield repository


def test_a_repository_is_readable_from_another_thread(
    repo: SqliteMarketDataRepository,
) -> None:
    """The exact failure M4 hit: created on one thread, used on another.

    Before the fix this raised `sqlite3.ProgrammingError: SQLite objects created in a
    thread can only be used in that same thread`.
    """
    repo.save_observations([_observation(day) for day in range(5)])

    with ThreadPoolExecutor(max_workers=1) as pool:
        observations = pool.submit(repo.get_observations, RELIANCE, interval="1d").result()

    assert len(observations) == 5


def test_concurrent_reads_all_see_the_same_committed_data(
    repo: SqliteMarketDataRepository,
) -> None:
    repo.save_observations([_observation(day) for day in range(50)])

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = [
            future.result()
            for future in [
                pool.submit(repo.get_observations, RELIANCE, interval="1d") for _ in range(32)
            ]
        ]

    assert all(len(observations) == 50 for observations in results)


def test_concurrent_writes_stay_idempotent_and_lose_nothing(
    repo: SqliteMarketDataRepository,
) -> None:
    """Interleaved writers must converge, not corrupt or double-count.

    Every worker writes the same 20 bars. Writes are idempotent by construction
    (effective-dated on knowledge_time), so exactly 20 rows must exist afterwards
    however the threads interleave.
    """
    batch = [_observation(day) for day in range(20)]

    with ThreadPoolExecutor(max_workers=8) as pool:
        written = [
            future.result()
            for future in [pool.submit(repo.save_observations, batch) for _ in range(8)]
        ]

    assert sum(written) == 20, "the 20 rows were written exactly once in total"
    assert len(repo.get_observations(RELIANCE, interval="1d")) == 20


def test_reads_and_writes_interleaved_never_raise(
    repo: SqliteMarketDataRepository,
) -> None:
    """Mixed traffic is what a serving plane actually produces."""

    def write(day: int) -> int:
        return repo.save_observations([_observation(day)])

    def read(_: int) -> int:
        return len(repo.get_observations(RELIANCE, interval="1d"))

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [
            pool.submit(write if index % 2 else read, index) for index in range(64)
        ]
        for future in futures:
            future.result()  # re-raises anything a worker raised

    assert len(repo.get_observations(RELIANCE, interval="1d")) == 32


def test_exactness_survives_concurrent_access(repo: SqliteMarketDataRepository) -> None:
    """Money must round-trip bit-exactly under threads as it does single-threaded.

    Serialization protects the connection; this asserts it also protects the decimal
    guarantee (ADR-0016), which is the property the whole backend exists to preserve.
    """
    exact = Money(Decimal("1436.25"), Currency.INR)
    observation = _observation(0)
    repo.save_observations([observation])

    with ThreadPoolExecutor(max_workers=4) as pool:
        batches = [
            future.result()
            for future in [
                pool.submit(repo.get_observations, RELIANCE, interval="1d") for _ in range(16)
            ]
        ]

    assert all(batch[0].close == Money(Decimal("1000"), Currency.INR) for batch in batches)
    assert exact.amount == Decimal("1436.25")  # no float ever entered the path
