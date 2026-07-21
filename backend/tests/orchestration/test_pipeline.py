"""The ingest DAG (doc 16) — idempotence, keying, and lineage recording.

These assert the three properties the skeleton's DAG exists to prove, and nothing more:
tasks are idempotent and keyed, `knowledge_time` comes from the raw envelope rather than
the clock, and the run is recorded as a lineage event. Retries, backfill windows,
scheduling and invalidation are Phase 2 and are deliberately untested because they are
deliberately unbuilt.
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.domain.market_data.sqlite_repository import SqliteMarketDataRepository
from backend.domain.model.instruments import REFERENCE_VERSION, reference_for
from backend.ingestion.filesystem_object_store import FilesystemObjectStore
from backend.orchestration.pipeline import (
    PIPELINE_VERSION,
    TASK_ORDER,
    PipelineRun,
    TaskKey,
    rebuildable_keys,
    run_ingest,
    task_keys,
)
from backend.platform.identifiers import InstrumentId
from backend.providers.ports.price_history import PriceHistoryRequest, RawPriceResponse
from backend.providers.yfinance.adapter import (
    EXPECTED_COLUMNS,
    RawFetch,
    YFinanceAdapter,
)

RELIANCE = InstrumentId("reliance")
REQUESTED_AT = datetime(2026, 7, 22, 6, 0, tzinfo=UTC)

BARS = (
    {"timestamp": "2025-07-01T00:00:00", "Open": 1400.0, "High": 1425.0,
     "Low": 1395.0, "Close": 1410.5, "Volume": 5_200_000.0},
    {"timestamp": "2025-07-02T00:00:00", "Open": 1410.5, "High": 1440.0,
     "Low": 1408.0, "Close": 1436.25, "Volume": 4_800_000.0},
    # One deliberately invalid bar: the gate must reject it on every run, including
    # replays, and it must be retained rather than dropped.
    {"timestamp": "2025-07-03T00:00:00", "Open": 1436.25, "High": 1450.0,
     "Low": 1430.0, "Close": -1.0, "Volume": 100.0},
)


class _FixedAdapter(YFinanceAdapter):
    """The real adapter over a recorded payload, with a pinned `fetched_at`.

    Pinning the fetch time is what makes the whole run deterministic: it becomes the
    `knowledge_time` of every observation, so two runs over the same recorded payload
    are comparable. A live adapter stamps `datetime.now`, which is exactly the
    non-determinism the DAG must not inherit.
    """

    def __init__(self, fetched_at: datetime) -> None:
        super().__init__(fetcher=lambda *_: RawFetch(columns=EXPECTED_COLUMNS, rows=BARS))
        self._fetched_at = fetched_at

    def fetch(self, request: PriceHistoryRequest) -> RawPriceResponse:
        response = super().fetch(request)
        from dataclasses import replace

        return replace(response, fetch=replace(response.fetch, fetched_at=self._fetched_at))


FETCHED_AT = datetime(2026, 7, 20, 3, 30, tzinfo=UTC)


@pytest.fixture()
def workspace(tmp_path: Path) -> Iterator[tuple[FilesystemObjectStore, SqliteMarketDataRepository]]:
    with SqliteMarketDataRepository(tmp_path / "domain.sqlite3") as repository:
        yield FilesystemObjectStore(tmp_path / "raw"), repository


def _run(workspace, requested_at: datetime = REQUESTED_AT) -> PipelineRun:
    store, repository = workspace
    return run_ingest(
        RELIANCE,
        reference_for(RELIANCE),
        provider=_FixedAdapter(FETCHED_AT),
        store=store,
        repository=repository,
        requested_at=requested_at,
    )


# ── The run happens, end to end ───────────────────────────────────────────────


def test_the_dag_ingests_through_every_stage(workspace) -> None:
    run = _run(workspace)

    assert run.observations_written == 2      # two valid bars
    assert run.quarantined_written == 1       # the invalid one, retained
    assert run.pipeline_version == PIPELINE_VERSION
    assert run.reference_version == REFERENCE_VERSION
    assert len(run.raw_object_keys) == 1


def test_the_persisted_observations_are_readable_afterwards(workspace) -> None:
    _run(workspace)
    _, repository = workspace

    observations = repository.get_observations(RELIANCE, interval="1d")

    assert len(observations) == 2
    assert all(o.knowledge_time == FETCHED_AT for o in observations)


# ── knowledge_time comes from the envelope, not the clock ─────────────────────


def test_knowledge_time_is_the_fetch_time_not_the_run_time(workspace) -> None:
    """The property that makes a rebuild reproducible at all.

    If the DAG stamped `datetime.now()` here, every replay would produce different
    observations and a byte-identical recompute would be impossible by construction.
    """
    run = _run(workspace, requested_at=datetime(2030, 1, 1, tzinfo=UTC))

    assert run.knowledge_time == FETCHED_AT
    assert run.knowledge_time != run.requested_at


def test_requested_at_must_be_timezone_aware(workspace) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _run(workspace, requested_at=datetime(2026, 7, 22))  # noqa: DTZ001


# ── Idempotence (doc 16: every task is idempotent and keyed) ──────────────────


def test_running_the_dag_twice_writes_nothing_the_second_time(workspace) -> None:
    first = _run(workspace)
    second = _run(workspace)

    assert first.observations_written == 2
    assert second.observations_written == 0
    assert second.quarantined_written == 0


def test_running_twice_converges_rather_than_duplicating(workspace) -> None:
    _run(workspace)
    _run(workspace)
    _, repository = workspace

    assert len(repository.get_observations(RELIANCE, interval="1d")) == 2
    assert len(repository.get_quarantined(RELIANCE)) == 1


def test_a_repeat_run_reuses_the_same_content_addressed_raw_object(workspace) -> None:
    """Raw capture is idempotent, so a replay does not fork the immutable store."""
    first, second = _run(workspace), _run(workspace)
    store, _ = workspace

    assert first.raw_object_keys == second.raw_object_keys
    assert len(list(store.list_keys())) == 1


def test_a_repeat_run_produces_the_same_run_id(workspace) -> None:
    """Run identity derives from the data, not a counter — so runs are comparable."""
    assert _run(workspace).run_id == _run(workspace).run_id


# ── Task keys ─────────────────────────────────────────────────────────────────


def test_tasks_are_keyed_by_type_scope_window_and_config() -> None:
    keys = task_keys(RELIANCE, interval="1d", lookback_days=365, config_version="cfg/v1")

    assert [key.task for key in keys] == list(TASK_ORDER)
    assert all(key.scope == "reliance" and key.window == "1d/365d" for key in keys)
    assert str(keys[0]) == "fetch:reliance:1d/365d:cfg/v1"


def test_a_different_window_is_a_different_task(workspace) -> None:
    """Keying must distinguish units of work, or a replay would collide them."""
    daily = task_keys(RELIANCE, interval="1d", lookback_days=365, config_version="c")
    weekly = task_keys(RELIANCE, interval="1wk", lookback_days=365, config_version="c")

    assert {str(k) for k in daily}.isdisjoint({str(k) for k in weekly})


def test_a_config_change_is_a_different_task() -> None:
    """A reference or contract version bump must not silently reuse prior work."""
    before = task_keys(RELIANCE, interval="1d", lookback_days=365, config_version="v1")
    after = task_keys(RELIANCE, interval="1d", lookback_days=365, config_version="v2")

    assert {str(k) for k in before}.isdisjoint({str(k) for k in after})


def test_task_keys_render_stably() -> None:
    key = TaskKey(task="persist", scope="apple", window="1d/365d", config_version="c/v1")
    assert str(key) == "persist:apple:1d/365d:c/v1"


# ── The run is a lineage event ────────────────────────────────────────────────


def test_the_run_records_the_versions_doc_16_requires(workspace) -> None:
    run = _run(workspace)

    assert run.pipeline_version == PIPELINE_VERSION          # code version
    assert run.reference_version == REFERENCE_VERSION        # reference snapshot
    assert run.raw_contract_version == "yfinance-ohlcv/v1"   # config version
    assert run.provider == "yfinance"
    assert run.raw_object_keys                               # inputs consumed
    assert run.observations_written == 2                     # outputs produced
    assert list(run.tasks) and len(run.tasks) == len(TASK_ORDER)


def test_a_run_round_trips_through_its_json_form(workspace) -> None:
    """The persistence format is a JSON artifact, not a schema (approved M5 scope)."""
    run = _run(workspace)

    assert PipelineRun.from_json(run.to_json()) == run


def test_the_json_form_is_stable_and_diffable(workspace) -> None:
    import json

    run = _run(workspace)
    document = run.to_json()

    assert document == run.to_json()                       # deterministic
    assert "\n" in document                                # indented, not one line
    keys = list(json.loads(document))
    assert keys == sorted(keys)                            # stable field order


def test_rebuildable_keys_deduplicates_across_runs(workspace) -> None:
    first, second = _run(workspace), _run(workspace)
    assert rebuildable_keys([first, second]) == first.raw_object_keys
