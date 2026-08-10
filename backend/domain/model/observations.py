"""The canonical `PriceObservation` and its provenance (doc 04).

An observation carries both times required by the temporal-policy matrix:

* `event_time` — the bar's own timestamp (when it happened),
* `knowledge_time` — when the platform recorded it. **Populated on every ingestion
  from the first row (audit clarification C1).** Only the as-of *query* machinery is
  deferred to Phase 6; the timestamp itself is captured now because ingestion time
  is free to record and impossible to backfill honestly.

`Provenance` links the observation back to the immutable raw object it was derived
from and pins the reference/contract versions in force at normalization — the
difference between lineage that is merely *traceable* and lineage that is
*recomputable* (principle 6 / review B1).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from backend.domain.model.quantities import PriceValue
from backend.platform.identifiers import InstrumentId


class AuthorityTier(StrEnum):
    """Whether a fact may be served and used as authoritative (doc 04 / review B8)."""

    AUTHORITATIVE = "AUTHORITATIVE"
    CANDIDATE = "CANDIDATE"


@dataclass(frozen=True, slots=True)
class Provenance:
    """Where a canonical fact came from, and under which pinned versions."""

    raw_object_key: str
    provider: str
    raw_contract_version: str
    reference_version: str
    #: Which validation rule set admitted (or rejected) this record. Required, not
    #: defaulted: a fact that cannot say which rules vetted it is exactly the gap this
    #: field closes, and a default would let one exist again.
    validation_version: str


@dataclass(frozen=True, slots=True)
class PriceObservation:
    """One canonical OHLCV bar for an instrument."""

    instrument_id: InstrumentId
    event_time: datetime
    knowledge_time: datetime
    interval: str
    open: PriceValue
    high: PriceValue
    low: PriceValue
    close: PriceValue
    volume: Decimal | None
    authority: AuthorityTier
    quality_flags: tuple[str, ...]
    provenance: Provenance

    def __post_init__(self) -> None:
        if self.event_time.tzinfo is None or self.knowledge_time.tzinfo is None:
            raise ValueError("event_time and knowledge_time must be timezone-aware")


@dataclass(frozen=True, slots=True)
class QuarantineRecord:
    """A bar rejected by the validation gate, retained for data-ops triage (doc 05/07).

    Quarantined data is never silently discarded — fail-closed means it does not reach
    the canonical model, not that it disappears. `raw_timestamp` is kept verbatim as
    text because an unparseable timestamp is itself a reason for rejection.
    """

    instrument_id: InstrumentId
    raw_timestamp: str
    reasons: tuple[str, ...]
    payload_json: str
    quarantined_at: datetime
    provenance: Provenance

    def __post_init__(self) -> None:
        if self.quarantined_at.tzinfo is None:
            raise ValueError("quarantined_at must be timezone-aware")
        if not self.reasons:
            raise ValueError("a quarantined record must carry at least one reason")
