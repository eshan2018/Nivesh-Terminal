"""The `MarketDataRepository` port (L5, doc 07).

Application code depends on this interface, never on a database driver — the
portability rule that makes the storage engine swappable (doc 07). PostgreSQL is
the production system of record (ADR-0008); the SQLite implementation in this
package is the local/CI backend (ED-003).

Writes are **idempotent**: re-persisting the same observations converges rather than
duplicating, because prices are effective-dated and versioned by `knowledge_time`
(doc 04 temporal matrix). A genuine correction arrives with a later
`knowledge_time` and is stored as a new version alongside the old one — nothing is
overwritten (principle 14).

Reads return the **latest version** of each bar. As-of (point-in-time) querying is
deliberately absent: the architecture defers that machinery to Phase 6, and the
schema already carries `knowledge_time` so adding it later is additive.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from backend.domain.model.observations import PriceObservation, QuarantineRecord
from backend.platform.identifiers import InstrumentId


@runtime_checkable
class MarketDataRepository(Protocol):
    """Persistence for the market-data module's canonical facts."""

    def save_observations(self, observations: Sequence[PriceObservation]) -> int:
        """Persist observations idempotently; return how many rows were newly written."""
        ...

    def get_observations(
        self, instrument_id: InstrumentId, *, interval: str
    ) -> tuple[PriceObservation, ...]:
        """Return the latest version of each bar, ordered by `event_time`."""
        ...

    def save_quarantined(self, records: Sequence[QuarantineRecord]) -> int:
        """Persist quarantined bars idempotently; return how many were newly written."""
        ...

    def get_quarantined(self, instrument_id: InstrumentId) -> tuple[QuarantineRecord, ...]:
        """Return quarantined bars for triage, ordered by `raw_timestamp`."""
        ...
