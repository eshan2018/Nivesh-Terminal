"""Batch ingestion and the empty-payload policy (M6b-2, doc 16).

Hermetic: fake providers, a temporary store and an in-memory repository. The point under
test is not that ingestion works — `test_pipeline.py` owns that — but that the batch
gives every instrument an honest *outcome*, and that a silence is never mistaken for a
success.
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.domain.market_data.sqlite_repository import SqliteMarketDataRepository
from backend.ingestion.filesystem_object_store import FilesystemObjectStore
from backend.orchestration.batch import (
    EMPTY_WINDOW_TOLERANCE_DAYS,
    BatchManifest,
    IngestOutcome,
    classify,
    run_ingest_batch,
)
from backend.platform.identifiers import InstrumentId
from backend.providers.ports.errors import RateLimited
from backend.providers.ports.price_history import (
    FetchMetadata,
    PriceHistoryRequest,
    RawBar,
    RawPriceResponse,
)

RELIANCE = InstrumentId("reliance")
TCS = InstrumentId("tcs")
REQUESTED_AT = datetime(2026, 7, 30, 6, tzinfo=UTC)


def _bar(day: int) -> RawBar:
    return RawBar(
        timestamp=f"2026-06-{day:02d}T00:00:00",
        open=100.0, high=101.0, low=99.0, close=100.5, volume=1000.0,
    )


class FakeProvider:
    """A `PriceHistoryPort` whose behaviour is scripted per instrument."""

    def __init__(
        self,
        bars_by_instrument: dict[str, int],
        raises: dict[str, Exception] | None = None,
    ):
        self._bars = bars_by_instrument
        self._raises = raises or {}

    def fetch(self, request: PriceHistoryRequest) -> RawPriceResponse:
        key = request.instrument_id.value
        if key in self._raises:
            raise self._raises[key]
        count = self._bars.get(key, 0)
        return RawPriceResponse(
            instrument_id=request.instrument_id,
            bars=tuple(_bar(day + 1) for day in range(count)),
            fetch=FetchMetadata(
                provider="yfinance",
                vendor_symbol=f"{key.upper()}.NS",
                interval=request.interval,
                fetched_at=REQUESTED_AT,
                raw_contract_version="yfinance-ohlcv/v1",
            ),
        )


@pytest.fixture()
def repository() -> Iterator[SqliteMarketDataRepository]:
    with SqliteMarketDataRepository() as repo:
        yield repo


def _run(
    provider, repository, tmp_path: Path, *, instruments=None, lookback_days=365
) -> BatchManifest:
    return run_ingest_batch(
        instruments if instruments is not None else [RELIANCE, TCS],
        provider=provider,
        store=FilesystemObjectStore(tmp_path / "raw"),
        repository=repository,
        requested_at=REQUESTED_AT,
        lookback_days=lookback_days,
    )


# ── The classification, in isolation ──────────────────────────────────────────

def test_bars_returned_is_always_an_ingest() -> None:
    assert classify(1, lookback_days=365, tolerance_days=7) is IngestOutcome.INGESTED
    assert classify(400, lookback_days=1, tolerance_days=7) is IngestOutcome.INGESTED


def test_an_empty_short_window_is_expected_and_an_empty_year_is_not() -> None:
    assert classify(0, lookback_days=3, tolerance_days=7) is IngestOutcome.EMPTY_EXPECTED
    assert classify(0, lookback_days=7, tolerance_days=7) is IngestOutcome.EMPTY_EXPECTED
    assert classify(0, lookback_days=8, tolerance_days=7) is IngestOutcome.EMPTY_UNEXPECTED
    assert classify(0, lookback_days=365, tolerance_days=7) is IngestOutcome.EMPTY_UNEXPECTED


def test_the_tolerance_spans_the_longest_ordinary_closure() -> None:
    """Pinned because it is a judgement, not a constant of nature.

    Seven days is the same figure the one-year-return anchor tolerance uses, chosen for
    the same reason. A trading calendar would replace this heuristic with a fact.
    """
    assert EMPTY_WINDOW_TOLERANCE_DAYS == 7


# ── The batch ─────────────────────────────────────────────────────────────────

def test_every_instrument_gets_an_outcome(repository, tmp_path: Path) -> None:
    manifest = _run(FakeProvider({"reliance": 5, "tcs": 5}), repository, tmp_path)

    assert [r.instrument_id for r in manifest.results] == ["reliance", "tcs"]
    assert all(r.outcome is IngestOutcome.INGESTED for r in manifest.results)
    assert manifest.counts()["INGESTED"] == 2
    assert manifest.needs_attention() == ()


def test_an_empty_year_is_flagged_not_counted_as_success(repository, tmp_path: Path) -> None:
    """The failure M6b-0 warned about: a wrong or delisted symbol ingests silently."""
    manifest = _run(FakeProvider({"reliance": 5, "tcs": 0}), repository, tmp_path)

    outcomes = {r.instrument_id: r.outcome for r in manifest.results}
    assert outcomes["reliance"] is IngestOutcome.INGESTED
    assert outcomes["tcs"] is IngestOutcome.EMPTY_UNEXPECTED
    assert [r.instrument_id for r in manifest.needs_attention()] == ["tcs"]


def test_a_replay_of_an_already_ingested_window_is_not_an_empty_fetch(
    repository, tmp_path: Path
) -> None:
    """The distinction `bars_fetched` exists for.

    A second run writes zero rows because the first already wrote them — an idempotent
    task converging, exactly as doc 16 requires. Classifying that on rows *written*
    would report a healthy replay as a silent failure, and every scheduled re-run would
    cry wolf.
    """
    provider = FakeProvider({"reliance": 5, "tcs": 5})
    first = _run(provider, repository, tmp_path)
    second = _run(provider, repository, tmp_path)

    assert all(r.observations_written > 0 for r in first.results)
    assert all(r.observations_written == 0 for r in second.results)
    assert all(r.bars_fetched == 5 for r in second.results)
    assert all(r.outcome is IngestOutcome.INGESTED for r in second.results)
    assert second.needs_attention() == ()


def test_one_failure_does_not_end_the_batch(repository, tmp_path: Path) -> None:
    """Nineteen ingested plus one recorded failure beats an exception at the third."""
    provider = FakeProvider({"reliance": 5}, raises={"tcs": RateLimited("quota exhausted")})

    manifest = _run(provider, repository, tmp_path)

    failed = next(r for r in manifest.results if r.instrument_id == "tcs")
    assert failed.outcome is IngestOutcome.FAILED
    # The doc 06 taxonomy class, never a vendor error type (ADR-0005).
    assert failed.error == "RateLimited"
    assert "quota exhausted" in failed.detail
    assert next(r for r in manifest.results if r.instrument_id == "reliance").bars_fetched == 5


def test_an_unseeded_instrument_fails_rather_than_being_skipped(
    repository, tmp_path: Path
) -> None:
    manifest = _run(
        FakeProvider({}), repository, tmp_path, instruments=[InstrumentId("not-a-thing")]
    )

    assert manifest.results[0].outcome is IngestOutcome.FAILED
    assert manifest.results[0].error == "UnknownInstrument"


def test_an_unexpected_exception_propagates_rather_than_becoming_a_statistic(
    repository, tmp_path: Path
) -> None:
    """A defect in our code must not be absorbed into a data-quality tally."""
    provider = FakeProvider({"reliance": 5}, raises={"tcs": ZeroDivisionError("a real bug")})

    with pytest.raises(ZeroDivisionError):
        _run(provider, repository, tmp_path)


def test_requested_at_must_be_timezone_aware(repository, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        run_ingest_batch(
            [RELIANCE],
            provider=FakeProvider({"reliance": 5}),
            store=FilesystemObjectStore(tmp_path / "raw"),
            repository=repository,
            requested_at=datetime(2026, 7, 30, 6),  # naive
        )


# ── The manifest ──────────────────────────────────────────────────────────────

def test_the_manifest_records_the_versions_a_run_is_interpretable_by(
    repository, tmp_path: Path
) -> None:
    import json

    manifest = _run(FakeProvider({"reliance": 5, "tcs": 0}), repository, tmp_path)
    document = json.loads(manifest.to_json())

    assert document["pipeline_version"] == "ingest-dag/v1"
    assert document["reference_version"] == "instrument-reference/v2"
    assert document["counts"]["EMPTY_UNEXPECTED"] == 1
    # Every outcome appears even at zero, so a consumer never has to distinguish
    # "none of these" from "this key was not written".
    assert set(document["counts"]) == {str(outcome) for outcome in IngestOutcome}
    assert document["results"][0]["raw_object_key"].startswith("raw/v1/yfinance/")


def test_lineage_is_not_lost_when_the_manifest_is_discarded(
    repository, tmp_path: Path
) -> None:
    """Why the manifest is operational rather than domain data.

    Everything traceable in it is already durable on the observations themselves, so
    deleting it costs no lineage — what it uniquely holds are the absences.
    """
    manifest = _run(FakeProvider({"reliance": 5}), repository, tmp_path, instruments=[RELIANCE])

    stored = repository.get_observations(RELIANCE, interval="1d")
    assert stored
    assert {o.provenance.raw_object_key for o in stored} == {manifest.results[0].raw_object_key}
    assert all(o.provenance.reference_version == manifest.reference_version for o in stored)
