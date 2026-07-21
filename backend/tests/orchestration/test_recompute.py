"""Recompute-from-raw (doc 00 §B6) — the last Phase 0.5 Definition-of-Done item.

The claim under test is the one the whole architecture rests on: **canonical and derived
data are derivable from immutable raw.** If that is false, "recomputable lineage"
(ADR-0017) is a slogan, the raw store is dead weight, and the disaster-recovery story
does not exist.

So these tests destroy the canonical store and rebuild everything from raw bytes, then
compare the resulting `AnalyticResult` **in full, timestamps included**. Comparing
all-but-the-timestamps would pass even if the rebuild silently used a different set of
observations — which is precisely the failure worth catching.
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.domain.market_data.sqlite_repository import SqliteMarketDataRepository
from backend.domain.model.analytics import ResultStatus
from backend.domain.model.instruments import reference_for
from backend.ingestion.filesystem_object_store import FilesystemObjectStore
from backend.orchestration.pipeline import run_ingest
from backend.orchestration.recompute import (
    compute_metric,
    recompute_from_raw,
    response_from_raw,
)
from backend.platform.identifiers import InstrumentId
from backend.providers.ports.price_history import PriceHistoryRequest, RawPriceResponse
from backend.providers.yfinance.adapter import (
    EXPECTED_COLUMNS,
    RawFetch,
    YFinanceAdapter,
)

RELIANCE = InstrumentId("reliance")
FETCHED_AT = datetime(2026, 7, 20, 3, 30, tzinfo=UTC)
AS_OF = datetime(2026, 7, 22, 6, 0, tzinfo=UTC)
COMPUTED_AT = datetime(2026, 7, 22, 6, 0, 30, tzinfo=UTC)


def _bars() -> tuple[dict[str, object], ...]:
    """Two years of daily bars, so the one-year metric is actually computable."""
    rows = []
    for day in range(500):
        close = 1400.0 + (day * 3) % 250
        stamp = (datetime(2024, 1, 1, tzinfo=UTC).timestamp() + day * 86400)
        rows.append({
            "timestamp": datetime.fromtimestamp(stamp, UTC).strftime("%Y-%m-%dT00:00:00"),
            "Open": close, "High": close + 5, "Low": close - 5,
            "Close": close, "Volume": 1_000_000.0,
        })
    return tuple(rows)


class _FixedAdapter(YFinanceAdapter):
    """Real adapter, recorded payload, pinned fetch time (see test_pipeline)."""

    def __init__(self) -> None:
        super().__init__(fetcher=lambda *_: RawFetch(columns=EXPECTED_COLUMNS, rows=_bars()))

    def fetch(self, request: PriceHistoryRequest) -> RawPriceResponse:
        from dataclasses import replace

        response = super().fetch(request)
        return replace(response, fetch=replace(response.fetch, fetched_at=FETCHED_AT))


@pytest.fixture()
def ingested(tmp_path: Path) -> Iterator[tuple]:
    """Run the real DAG once, then hand back everything needed to rebuild it."""
    store = FilesystemObjectStore(tmp_path / "raw")
    with SqliteMarketDataRepository(tmp_path / "original.sqlite3") as repository:
        run = run_ingest(
            RELIANCE, reference_for(RELIANCE),
            provider=_FixedAdapter(), store=store,
            repository=repository, requested_at=AS_OF,
        )
        original = compute_metric(
            repository, RELIANCE, as_of=AS_OF, computed_at=COMPUTED_AT
        )
        yield store, run, original, tmp_path


def _rebuild(store, run, original, tmp_path, **overrides):
    """Rebuild into a *fresh* store — "drop canonical data" made literal."""
    databases = iter(tmp_path / f"rebuild-{n}.sqlite3" for n in range(100))

    def factory():
        return SqliteMarketDataRepository(next(databases))

    return recompute_from_raw(
        [run], store=store, rebuild_repository=factory,
        instrument_id=RELIANCE, as_of=AS_OF, computed_at=COMPUTED_AT,
        original=original, **overrides,
    )


# ── The claim: derived data is derivable from raw ─────────────────────────────


def test_the_metric_rebuilds_byte_identically_from_raw_alone(ingested) -> None:
    """The Phase 0.5 deliverable. Full-envelope equality, timestamps included."""
    report = _rebuild(*ingested)

    assert report.reproduced, (
        "a rebuild from immutable raw must reproduce the served value exactly — "
        f"original={report.original} rebuilt={report.rebuilt}"
    )
    assert report.rebuilt == report.original
    assert report.rebuilt is not report.original  # genuinely rebuilt, not the same object


def test_the_rebuild_starts_from_genuinely_empty_state(ingested) -> None:
    """A rebuild that quietly reused the original store would prove nothing."""
    store, run, original, tmp_path = ingested
    report = _rebuild(store, run, original, tmp_path)

    assert report.observations_rebuilt > 0, "the fresh store was populated by the replay"
    assert report.raw_objects_replayed == 1


def test_the_rebuilt_value_is_actually_a_value(ingested) -> None:
    """Guards the vacuous pass: two Unavailable results also compare equal."""
    report = _rebuild(*ingested)

    assert report.original is not None
    assert report.original.status is ResultStatus.AVAILABLE
    assert report.original.value is not None


def test_lineage_still_resolves_after_the_rebuild(ingested) -> None:
    """Rebuilt values must carry lineage, not just the right number."""
    report = _rebuild(*ingested)
    rebuilt = report.rebuilt

    assert rebuilt is not None
    assert rebuilt.lineage.raw_object_keys() == report.original.lineage.raw_object_keys()
    assert rebuilt.lineage.contributing == report.original.lineage.contributing


# ── The measurement ───────────────────────────────────────────────────────────


def test_the_rebuild_is_timed(ingested) -> None:
    """The RTO data point exists and is a real measurement."""
    report = _rebuild(*ingested)

    assert report.elapsed_seconds > 0
    assert "byte-identical" in report.summary()


# ── The raw store really does hold everything ─────────────────────────────────


def test_the_provider_response_round_trips_through_the_raw_store(ingested) -> None:
    """ADR-0009's premise: raw is sufficient, not merely archival."""
    store, run, _, _ = ingested
    (key,) = run.raw_object_keys

    restored = response_from_raw(store.get(key))

    assert restored.instrument_id == RELIANCE
    assert restored.fetch.fetched_at == FETCHED_AT
    assert restored.fetch.raw_contract_version == "yfinance-ohlcv/v1"
    assert len(restored.bars) == 500


def test_the_replay_recovers_knowledge_time_rather_than_restamping(ingested) -> None:
    """The property the whole reproduction rests on.

    A replay that stamped `now` would produce different observations, and the
    byte-identical assertion above would be impossible rather than merely failing.
    """
    store, run, original, tmp_path = ingested
    rebuilt_db = tmp_path / "knowledge.sqlite3"

    def factory():
        return SqliteMarketDataRepository(rebuilt_db)

    recompute_from_raw(
        [run], store=store, rebuild_repository=factory, instrument_id=RELIANCE,
        as_of=AS_OF, computed_at=COMPUTED_AT, original=original,
    )

    with SqliteMarketDataRepository(rebuilt_db) as repository:
        observations = repository.get_observations(RELIANCE, interval="1d")

    assert observations
    assert all(o.knowledge_time == FETCHED_AT for o in observations)


def test_a_mismatch_is_reported_rather_than_hidden(ingested) -> None:
    """The harness must be able to fail.

    Rebuilding against a different `computed_at` produces a different envelope, and the
    report must say so — a comparison that always passes tests nothing.
    """
    store, run, original, tmp_path = ingested

    def factory():
        return SqliteMarketDataRepository(tmp_path / "mismatch.sqlite3")

    report = recompute_from_raw(
        [run], store=store, rebuild_repository=factory, instrument_id=RELIANCE,
        as_of=AS_OF, computed_at=datetime(2027, 1, 1, tzinfo=UTC), original=original,
    )

    assert not report.reproduced
    assert "MISMATCH" in report.summary()
