"""Batch ingestion across the seeded universe (doc 16) — and what to call a silence.

`pipeline.run_ingest` ingests one instrument. This runs it over many, and exists mainly
to answer a question one instrument never raised: **what does it mean when the provider
returns nothing?**

## The division of labour

The provider cannot answer that question. An unknown symbol, a delisted one, a newly
listed one, a short window over a holiday — all return the same empty payload, with no
error (doc 05 finding 5). An adapter that raised `NotAvailable` on emptiness would be
asserting knowledge it does not have, and would break legitimate short-window fetches.
So the adapter keeps reporting only what it observed: `bars_fetched`.

Orchestration is the layer that can combine three things the adapter cannot see:

* the **provider observation** — how many bars came back,
* **reference data** — that we claim this instrument exists at all,
* **request context** — how wide a window we asked for.

From those it produces an *execution outcome*, which is an operational judgement rather
than a provider fact.

## Why emptiness is not a correctness bug

Fail-closed already holds: an empty payload puts **nothing** into the canonical model,
and the metric above reports `Unavailable` with a reason rather than zero. Nothing wrong
is ever computed. What was missing before this module is that a run *reported success
while having ingested nothing* — an observability gap, and the way a portfolio silently
loses a holding across twenty instruments.

## The honest limit of the classification

`EMPTY_EXPECTED` vs `EMPTY_UNEXPECTED` rests on **window width alone**. A five-day
window can legitimately contain zero trading days; a year cannot. What it deliberately
does *not* claim is knowledge of the venue's calendar — doc 04 names Exchange/trading
calendar as a canonical entity and it is not built, so this module cannot say "the market
was shut all week." A real calendar would make the distinction exact; until then it is a
declared heuristic, labelled as one, and that is why `EMPTY_EXPECTED` is not treated as
success either.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from backend.domain.market_data.repository import MarketDataRepository
from backend.domain.model.instruments import (
    REFERENCE_VERSION,
    UnknownInstrument,
    reference_for,
)
from backend.ingestion.raw_store import RawStore, RawStoreError
from backend.orchestration.pipeline import PIPELINE_VERSION, run_ingest
from backend.platform.identifiers import InstrumentId
from backend.providers.ports.errors import ProviderError
from backend.providers.ports.price_history import PriceHistoryPort

#: A window at or below this many days may legitimately contain no trading sessions —
#: a long weekend plus a holiday. Deliberately the same 7 days the one-year-return
#: anchor tolerance uses, and for the same stated reason: it spans the longest ordinary
#: exchange closure in scope. It is a proxy for a trading calendar, not a substitute.
EMPTY_WINDOW_TOLERANCE_DAYS = 7


class IngestOutcome(StrEnum):
    """What actually happened for one instrument in a batch."""

    #: The provider returned bars. Writing zero rows is still INGESTED — a replay of an
    #: already-ingested window is a converged idempotent task, not an empty fetch.
    INGESTED = "INGESTED"
    #: No bars, over a window short enough that no bars is plausible.
    EMPTY_EXPECTED = "EMPTY_EXPECTED"
    #: No bars over a window that should have contained trading sessions. The instrument
    #: may be renamed, delisted, or wrong in the symbology. This is the silence M6b-0
    #: warned about, and it must never read as success.
    EMPTY_UNEXPECTED = "EMPTY_UNEXPECTED"
    #: The provider or the store failed, mapped to the doc 06 taxonomy.
    FAILED = "FAILED"


def classify(bars_fetched: int, *, lookback_days: int, tolerance_days: int) -> IngestOutcome:
    """Turn a provider observation plus request context into an execution outcome. Pure."""
    if bars_fetched > 0:
        return IngestOutcome.INGESTED
    if lookback_days <= tolerance_days:
        return IngestOutcome.EMPTY_EXPECTED
    return IngestOutcome.EMPTY_UNEXPECTED


@dataclass(frozen=True, slots=True)
class InstrumentResult:
    """One instrument's outcome within a batch."""

    instrument_id: str
    outcome: IngestOutcome
    bars_fetched: int = 0
    observations_written: int = 0
    quarantined_written: int = 0
    raw_object_key: str | None = None
    #: The doc 06 taxonomy class, never a vendor error type — `RateLimited`, not a
    #: vendor's HTTP wrapper. Vendor knowledge stays at L1 (ADR-0005).
    error: str | None = None
    detail: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "instrument_id": self.instrument_id,
            "outcome": str(self.outcome),
            "bars_fetched": self.bars_fetched,
            "observations_written": self.observations_written,
            "quarantined_written": self.quarantined_written,
            "raw_object_key": self.raw_object_key,
            "error": self.error,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class BatchManifest:
    """The operational record of one batch run.

    **Deliberately not domain data**, for the same reason `PipelineRun` is not: its
    subject is what did *not* happen. Every lineage fact it touches is already durable
    on the observations themselves — each `PriceObservation` carries its raw object key,
    provider, contract version and reference version — so discarding this manifest loses
    no lineage. What it uniquely holds are the absences, and a domain store holds facts,
    not descriptions of non-events. Storing it relationally would also need a schema
    owner: orchestration is not a domain module, and writing into `market_data`'s tables
    is the cross-module access ADR-0003 forbids.

    It becomes stored structure when Phase 2's invalidation cascade needs to read run
    history *forward* — the same trigger ED-015 named for adopting the orchestrator
    product, which brings its own run storage.
    """

    batch_id: str
    pipeline_version: str
    reference_version: str
    requested_at: datetime
    interval: str
    lookback_days: int
    results: tuple[InstrumentResult, ...]

    def counts(self) -> dict[str, int]:
        """How many instruments landed in each outcome, every outcome always present."""
        tally = {str(outcome): 0 for outcome in IngestOutcome}
        for result in self.results:
            tally[str(result.outcome)] += 1
        return tally

    def needs_attention(self) -> tuple[InstrumentResult, ...]:
        """The results a human must look at.

        `EMPTY_EXPECTED` is included on purpose. The classification is a window-width
        heuristic, not a calendar lookup, so "probably fine" is the strongest claim it
        can make — and a batch that ingested nothing anywhere should never be silent
        merely because each window was short.
        """
        return tuple(
            result for result in self.results if result.outcome is not IngestOutcome.INGESTED
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "batch_id": self.batch_id,
                "pipeline_version": self.pipeline_version,
                "reference_version": self.reference_version,
                "requested_at": self.requested_at.isoformat(),
                "interval": self.interval,
                "lookback_days": self.lookback_days,
                "counts": self.counts(),
                "results": [result.as_dict() for result in self.results],
            },
            indent=2,
            sort_keys=True,
        )


def run_ingest_batch(
    instrument_ids: Sequence[InstrumentId],
    *,
    provider: PriceHistoryPort,
    store: RawStore,
    repository: MarketDataRepository,
    requested_at: datetime,
    lookback_days: int = 365,
    interval: str = "1d",
    tolerance_days: int = EMPTY_WINDOW_TOLERANCE_DAYS,
) -> BatchManifest:
    """Ingest each instrument in turn, recording an outcome for every one.

    **One instrument's failure does not end the batch.** Nineteen ingested instruments
    plus one recorded failure is a better outcome than an exception at the third, and the
    manifest is what makes that partial success honest rather than hidden.

    **Only data conditions are caught.** Provider taxonomy errors, raw-store errors and
    a missing reference are outcomes. Anything else propagates: an unexpected exception
    is a defect in our code, and swallowing it into a manifest row would turn a bug into
    a data-quality statistic.
    """
    if requested_at.tzinfo is None:
        raise ValueError("requested_at must be timezone-aware")

    results: list[InstrumentResult] = []
    for instrument_id in instrument_ids:
        results.append(
            _ingest_one(
                instrument_id,
                provider=provider,
                store=store,
                repository=repository,
                requested_at=requested_at,
                lookback_days=lookback_days,
                interval=interval,
                tolerance_days=tolerance_days,
            )
        )

    return BatchManifest(
        batch_id=f"{PIPELINE_VERSION}:batch:{requested_at.isoformat()}",
        pipeline_version=PIPELINE_VERSION,
        reference_version=REFERENCE_VERSION,
        requested_at=requested_at,
        interval=interval,
        lookback_days=lookback_days,
        results=tuple(results),
    )


def _ingest_one(
    instrument_id: InstrumentId,
    *,
    provider: PriceHistoryPort,
    store: RawStore,
    repository: MarketDataRepository,
    requested_at: datetime,
    lookback_days: int,
    interval: str,
    tolerance_days: int,
) -> InstrumentResult:
    try:
        reference = reference_for(instrument_id)
    except UnknownInstrument as exc:
        return InstrumentResult(
            instrument_id=instrument_id.value,
            outcome=IngestOutcome.FAILED,
            error="UnknownInstrument",
            detail=str(exc),
        )

    try:
        run = run_ingest(
            instrument_id,
            reference,
            provider=provider,
            store=store,
            repository=repository,
            requested_at=requested_at,
            lookback_days=lookback_days,
            interval=interval,
        )
    except (ProviderError, RawStoreError) as exc:
        return InstrumentResult(
            instrument_id=instrument_id.value,
            outcome=IngestOutcome.FAILED,
            error=type(exc).__name__,
            detail=str(exc),
        )

    return InstrumentResult(
        instrument_id=instrument_id.value,
        outcome=classify(
            run.bars_fetched, lookback_days=lookback_days, tolerance_days=tolerance_days
        ),
        bars_fetched=run.bars_fetched,
        observations_written=run.observations_written,
        quarantined_written=run.quarantined_written,
        raw_object_key=run.raw_object_keys[0] if run.raw_object_keys else None,
    )
