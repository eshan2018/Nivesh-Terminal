"""The ingest DAG (doc 16) — fetch → capture → validate → normalize → persist.

**Forward-only, by design.** The skeleton proves the *shape* of the orchestration model:
declared task ordering, idempotent keyed tasks, and a run recorded as a lineage event.
Invalidation, corporate-action reprocessing, retries, backfill windows and scheduling
are Phase 2 (doc 16); this module deliberately contains none of them.

**No orchestration framework.** Doc 16 requires the *model* — "all pipeline work runs as
declared DAGs" — and states that "the specific product is a doc 12 selection, not an
application-layer concern", explicitly permitting the skeleton to precede it ("no ad-hoc
cron **above** the walking skeleton"). So the DAG here is a stdlib task graph and ED-005
(Dagster) stays `Proposed`, deferred to the milestone that first needs cross-process
scheduling, retries or backfill — the same pattern by which ED-003 deferred PostgreSQL
and ED-004 deferred S3. See ED-015.

**Every task is idempotent and keyed** (doc 16). A `TaskKey` is
(task type, canonical scope, time window, config version); re-running a key converges
rather than duplicating. That property is not decorative — it is what makes the replay
in `recompute.py` meaningful, and it is inherited from the layers below rather than
bolted on here: raw capture is content-addressed, and `save_observations` is
effective-dated and insert-or-ignore.

**`knowledge_time` comes from the raw envelope, never from the clock.** The platform
learned a bar when it fetched it, so `fetch.fetched_at` *is* the knowledge time — and it
is captured immutably in the raw object. Reading the clock here instead would make every
rebuild stamp a new knowledge_time, and a byte-identical recompute would become
impossible by construction (doc 00 §B6). Time is an input (principle 11).
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from backend.domain.market_data.repository import MarketDataRepository
from backend.domain.model.instruments import REFERENCE_VERSION, InstrumentReference
from backend.ingestion.normalization import (
    normalize_price_history,
    to_quarantine_records,
)
from backend.ingestion.raw_capture import capture_price_history
from backend.ingestion.raw_store import RawStore
from backend.ingestion.validation import validate_price_history
from backend.platform.identifiers import InstrumentId
from backend.providers.ports.price_history import (
    PriceHistoryPort,
    PriceHistoryRequest,
    RawPriceResponse,
)

#: The version of this pipeline's own code path. Part of a run's lineage: a change to
#: task ordering or semantics is a new version, so an old run stays interpretable.
PIPELINE_VERSION = "ingest-dag/v1"

TASK_FETCH = "fetch"
TASK_CAPTURE = "capture"
TASK_VALIDATE = "validate"
TASK_NORMALIZE = "normalize"
TASK_PERSIST = "persist"

#: Declared order. Forward-only: each task consumes the previous one's output.
TASK_ORDER: tuple[str, ...] = (
    TASK_FETCH,
    TASK_CAPTURE,
    TASK_VALIDATE,
    TASK_NORMALIZE,
    TASK_PERSIST,
)


@dataclass(frozen=True, slots=True)
class TaskKey:
    """A task's identity (doc 16): task type, scope, window, config version.

    Two runs producing the same key are the same unit of work, which is what makes a
    replay converge instead of duplicating. Rendered as a stable string so a run
    manifest stays diffable.
    """

    task: str
    scope: str
    window: str
    config_version: str

    def __str__(self) -> str:
        return f"{self.task}:{self.scope}:{self.window}:{self.config_version}"


@dataclass(frozen=True, slots=True)
class PipelineRun:
    """A DAG run, recorded as a lineage event (doc 16).

    Doc 16 requires a run to record "code version, config/policy versions,
    reference-data snapshot version, inputs consumed, outputs produced". This is that
    record as a typed value object; `to_json`/`from_json` are its persistence format.

    **Deliberately not a database table.** Queryable run *history* is what the Phase 2
    invalidation protocol needs, and doc 07 owns lineage storage. Adding a table now
    would also need a schema owner — orchestration is not a domain module, and writing
    into `market_data`'s schema would strain the module-owned-schema rule (ADR-0003).
    A JSON artifact is sufficient for M5, whose job is proving DAG shape and producing
    the recompute number.
    """

    run_id: str
    pipeline_version: str
    instrument_id: str
    requested_at: datetime
    reference_version: str
    raw_contract_version: str
    provider: str
    raw_object_keys: tuple[str, ...]
    observations_written: int
    quarantined_written: int
    knowledge_time: datetime
    tasks: tuple[str, ...] = field(default_factory=tuple)

    def to_json(self) -> str:
        """Sorted and indented so a run manifest reviews as a diff."""
        return json.dumps(
            {
                "run_id": self.run_id,
                "pipeline_version": self.pipeline_version,
                "instrument_id": self.instrument_id,
                "requested_at": self.requested_at.isoformat(),
                "reference_version": self.reference_version,
                "raw_contract_version": self.raw_contract_version,
                "provider": self.provider,
                "raw_object_keys": list(self.raw_object_keys),
                "observations_written": self.observations_written,
                "quarantined_written": self.quarantined_written,
                "knowledge_time": self.knowledge_time.isoformat(),
                "tasks": list(self.tasks),
            },
            indent=2,
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, document: str) -> PipelineRun:
        data = json.loads(document)
        return cls(
            run_id=data["run_id"],
            pipeline_version=data["pipeline_version"],
            instrument_id=data["instrument_id"],
            requested_at=datetime.fromisoformat(data["requested_at"]),
            reference_version=data["reference_version"],
            raw_contract_version=data["raw_contract_version"],
            provider=data["provider"],
            raw_object_keys=tuple(data["raw_object_keys"]),
            observations_written=data["observations_written"],
            quarantined_written=data["quarantined_written"],
            knowledge_time=datetime.fromisoformat(data["knowledge_time"]),
            tasks=tuple(data["tasks"]),
        )


def task_keys(
    instrument_id: InstrumentId, *, interval: str, lookback_days: int, config_version: str
) -> tuple[TaskKey, ...]:
    """The keys this run's tasks are identified by, in declared order."""
    window = f"{interval}/{lookback_days}d"
    return tuple(
        TaskKey(task=task, scope=instrument_id.value, window=window,
                config_version=config_version)
        for task in TASK_ORDER
    )


def run_ingest(
    instrument_id: InstrumentId,
    reference: InstrumentReference,
    *,
    provider: PriceHistoryPort,
    store: RawStore,
    repository: MarketDataRepository,
    requested_at: datetime,
    lookback_days: int = 365,
    interval: str = "1d",
) -> PipelineRun:
    """Run the ingest DAG once for one instrument, returning its lineage record.

    Idempotent end to end: running twice captures to the same content-addressed key and
    writes zero new rows the second time. Nothing here is destructive, so a re-run is
    always safe — the property doc 16 requires of every task.
    """
    if requested_at.tzinfo is None:
        raise ValueError("requested_at must be timezone-aware")

    # fetch
    response = provider.fetch(
        PriceHistoryRequest(instrument_id, lookback_days=lookback_days, interval=interval)
    )

    # capture — content-addressed, so a repeat capture resolves to the same object
    ref = capture_price_history(response, store)

    # The raw envelope is the source of knowledge_time from here on: the platform knew
    # these bars when it fetched them, and that instant is now immutable in the store.
    knowledge_time = response.fetch.fetched_at

    return _persist_from(
        response,
        reference,
        repository=repository,
        raw_object_key=ref.key,
        knowledge_time=knowledge_time,
        requested_at=requested_at,
        lookback_days=lookback_days,
        interval=interval,
    )


def replay_from_raw(
    response: RawPriceResponse,
    reference: InstrumentReference,
    *,
    repository: MarketDataRepository,
    raw_object_key: str,
    requested_at: datetime,
    lookback_days: int = 365,
    interval: str = "1d",
) -> PipelineRun:
    """Re-run validate → normalize → persist over a raw response read back from the store.

    The same code path as `run_ingest` minus fetch and capture — which is the point:
    a rebuild must not be a second implementation of the pipeline, or it would prove
    nothing about the pipeline. `knowledge_time` again comes from the envelope, so the
    rebuilt observations are identical to the originals rather than newly stamped.
    """
    return _persist_from(
        response,
        reference,
        repository=repository,
        raw_object_key=raw_object_key,
        knowledge_time=response.fetch.fetched_at,
        requested_at=requested_at,
        lookback_days=lookback_days,
        interval=interval,
    )


def _persist_from(
    response: RawPriceResponse,
    reference: InstrumentReference,
    *,
    repository: MarketDataRepository,
    raw_object_key: str,
    knowledge_time: datetime,
    requested_at: datetime,
    lookback_days: int,
    interval: str,
) -> PipelineRun:
    """The shared validate → normalize → persist tail of both entry points."""
    outcome = validate_price_history(response, reference)

    observations = normalize_price_history(
        response,
        outcome,
        reference,
        knowledge_time=knowledge_time,
        raw_object_key=raw_object_key,
        reference_version=REFERENCE_VERSION,
    )
    quarantined = to_quarantine_records(
        response,
        outcome,
        quarantined_at=knowledge_time,
        raw_object_key=raw_object_key,
        reference_version=REFERENCE_VERSION,
    )

    written = repository.save_observations(observations)
    quarantined_written = repository.save_quarantined(quarantined)

    config_version = f"{REFERENCE_VERSION}+{response.fetch.raw_contract_version}"
    return PipelineRun(
        run_id=_run_id(response.instrument_id, knowledge_time),
        pipeline_version=PIPELINE_VERSION,
        instrument_id=response.instrument_id.value,
        requested_at=requested_at,
        reference_version=REFERENCE_VERSION,
        raw_contract_version=response.fetch.raw_contract_version,
        provider=response.fetch.provider,
        raw_object_keys=(raw_object_key,),
        observations_written=written,
        quarantined_written=quarantined_written,
        knowledge_time=knowledge_time,
        tasks=tuple(
            str(key)
            for key in task_keys(
                response.instrument_id,
                interval=interval,
                lookback_days=lookback_days,
                config_version=config_version,
            )
        ),
    )


def _run_id(instrument_id: InstrumentId, knowledge_time: datetime) -> str:
    """Derived from the data, not from a counter or a clock.

    A replay of the same raw object therefore produces the same run id — which is what
    lets two runs be compared at all.
    """
    return f"{PIPELINE_VERSION}:{instrument_id.value}:{knowledge_time.isoformat()}"


def rebuildable_keys(runs: Sequence[PipelineRun]) -> tuple[str, ...]:
    """Every raw object the given runs consumed, de-duplicated and ordered."""
    return tuple(sorted({key for run in runs for key in run.raw_object_keys}))
