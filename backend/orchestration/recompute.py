"""Recompute-from-raw: rebuild every derived value from immutable raw, and time it.

This is the Phase 0.5 deliverable doc 00 §B6 requires and the last item in its
Definition of Done: *drop canonical + derived data, replay the raw records through
validate → normalize → persist → feature → engine, assert byte-identical outputs, and
record the wall-clock time.*

**What "byte-identical" means here, precisely.** Two things could make a rebuild differ
for reasons that are not defects, and both are handled as *inputs* rather than excluded
from the comparison:

* `knowledge_time` — taken from the raw envelope's `fetched_at`, so a replay recovers
  the original instant instead of stamping a new one.
* `computed_at` — supplied to the engine by the caller. A replay passes the original
  value recorded at the time, so the whole envelope can be compared rather than
  comparing "everything except the timestamps". That is what ADR-0017's
  *bit-reproducible* tier actually claims: pin the code, the formula version and the
  reference snapshot, and the output reproduces exactly.

Comparing all-but-the-timestamps would have been easier and weaker; it would pass even
if the rebuild silently changed which observations were used.

**"Drop canonical data" is realized as rebuilding into a fresh store**, not by deleting
through the repository port. The port has no delete method and does not need one — the
architecture's premise is that canonical data is *derivable* from raw, so proving that
means building it again from nothing, which a fresh store expresses exactly. Adding
destructive methods to a port to test a rebuild would be the tail wagging the dog.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from backend.analytics.one_year_return import one_year_return
from backend.domain.market_data.repository import MarketDataRepository
from backend.domain.model.analytics import AnalyticResult
from backend.domain.model.instruments import reference_for
from backend.features.returns import build_close_price_series
from backend.ingestion.raw_store import RawStore
from backend.orchestration.pipeline import PipelineRun, replay_from_raw
from backend.platform.identifiers import InstrumentId
from backend.providers.ports.price_history import (
    FetchMetadata,
    RawBar,
    RawPriceResponse,
)


@dataclass(frozen=True, slots=True)
class RecomputeReport:
    """The outcome of a rebuild: did it reproduce, and how long did it take.

    `elapsed_seconds` is the RTO data point. It is a measurement of *this* environment
    (local filesystem raw store, SQLite domain store, single process) and must be
    re-measured against object storage and PostgreSQL before it means anything about
    production — see the caveat carried in the written report.
    """

    instrument_id: str
    raw_objects_replayed: int
    observations_rebuilt: int
    reproduced: bool
    elapsed_seconds: float
    original: AnalyticResult | None
    rebuilt: AnalyticResult | None

    def summary(self) -> str:
        verdict = "byte-identical" if self.reproduced else "MISMATCH"
        return (
            f"{self.instrument_id}: {verdict} · "
            f"{self.raw_objects_replayed} raw object(s) → "
            f"{self.observations_rebuilt} observation(s) in "
            f"{self.elapsed_seconds:.3f}s"
        )


def response_from_raw(document: bytes) -> RawPriceResponse:
    """Reconstruct the provider response from a stored raw envelope.

    The inverse of `raw_capture._envelope`. Reading it back rather than keeping the
    original object in memory is the whole point: it proves the raw store holds
    everything a rebuild needs, which is the claim ADR-0009 rests on.
    """
    envelope = json.loads(document)
    fetch = envelope["fetch"]
    return RawPriceResponse(
        instrument_id=InstrumentId(envelope["instrument_id"]),
        bars=tuple(
            RawBar(
                timestamp=bar["timestamp"],
                open=bar["open"],
                high=bar["high"],
                low=bar["low"],
                close=bar["close"],
                volume=bar["volume"],
            )
            for bar in envelope["payload"]
        ),
        fetch=FetchMetadata(
            provider=fetch["provider"],
            vendor_symbol=fetch["vendor_symbol"],
            interval=fetch["interval"],
            fetched_at=datetime.fromisoformat(fetch["fetched_at"]),
            raw_contract_version=fetch["raw_contract_version"],
        ),
    )


def compute_metric(
    repository: MarketDataRepository,
    instrument_id: InstrumentId,
    *,
    as_of: datetime,
    computed_at: datetime,
    interval: str = "1d",
) -> AnalyticResult:
    """Feature → engine, with both times supplied explicitly so a replay can match."""
    series = build_close_price_series(
        repository, instrument_id, as_of=as_of, interval=interval
    )
    return one_year_return(series, computed_at=computed_at)


def recompute_from_raw(
    runs: Sequence[PipelineRun],
    *,
    store: RawStore,
    rebuild_repository: Callable[[], MarketDataRepository],
    instrument_id: InstrumentId,
    as_of: datetime,
    computed_at: datetime,
    original: AnalyticResult | None = None,
    interval: str = "1d",
) -> RecomputeReport:
    """Rebuild from raw into a fresh store and report reproduction + wall-clock time.

    `rebuild_repository` is a factory rather than a repository so the rebuild starts
    from genuinely empty state — the caller decides where that empty store lives.
    """
    reference = reference_for(instrument_id)
    keys = tuple(sorted({key for run in runs for key in run.raw_object_keys}))

    started = time.perf_counter()
    repository = rebuild_repository()
    observations_rebuilt = 0
    for key in keys:
        response = response_from_raw(store.get(key))
        replay = replay_from_raw(
            response,
            reference,
            repository=repository,
            raw_object_key=key,
            requested_at=as_of,
            interval=interval,
        )
        observations_rebuilt += replay.observations_written

    rebuilt = compute_metric(
        repository, instrument_id, as_of=as_of, computed_at=computed_at, interval=interval
    )
    elapsed = time.perf_counter() - started

    return RecomputeReport(
        instrument_id=instrument_id.value,
        raw_objects_replayed=len(keys),
        observations_rebuilt=observations_rebuilt,
        # Full-envelope equality, timestamps included — see the module docstring.
        reproduced=original is not None and rebuilt == original,
        elapsed_seconds=elapsed,
        original=original,
        rebuilt=rebuilt,
    )
