"""Normalization (L4, doc 05 stage 4) — accepted raw bars → canonical observations.

What this stage guarantees:

* **Only accepted bars are normalized.** Quarantined bars never reach the canonical
  model (fail-closed, principle 13).
* **Money is exact and typed.** Vendor numerics become `Decimal` via the sanctioned
  raw→canonical boundary; an equity's prices become `Money` in its own currency and
  an index's become `IndexLevel` in unitless points — so FX conversion of an index is
  type-impossible (doc 04).
* **Currency is preserved, never converted.** Conversion requires an `FXRate`, the
  only sanctioned source of conversion factors (doc 04), and FX is not yet an
  ingested data class. Observations are stored in their native currency; any
  conversion is a later concern with real rates behind it.
* **`knowledge_time` is populated on every observation (C1)** and is an explicit
  input, never read from an ambient clock (principle 11 — time is an input).
* **Provenance pins the versions in force** — the raw object key plus the provider,
  raw-contract and reference versions — which is what makes the lineage recomputable
  rather than merely traceable (review B1).
"""
from __future__ import annotations

import json
from datetime import datetime

from backend.domain.model.instruments import InstrumentReference, InstrumentType
from backend.domain.model.observations import (
    AuthorityTier,
    PriceObservation,
    Provenance,
    QuarantineRecord,
)
from backend.domain.model.quantities import IndexLevel, Money, PriceValue, to_decimal
from backend.ingestion.validation import ValidationOutcome
from backend.providers.ports.price_history import RawPriceResponse


def normalize_price_history(
    response: RawPriceResponse,
    outcome: ValidationOutcome,
    reference: InstrumentReference,
    *,
    knowledge_time: datetime,
    raw_object_key: str,
    reference_version: str,
) -> tuple[PriceObservation, ...]:
    """Normalize the accepted bars of `outcome` into canonical `PriceObservation`s."""
    if knowledge_time.tzinfo is None:
        raise ValueError("knowledge_time must be timezone-aware")

    provenance = Provenance(
        raw_object_key=raw_object_key,
        provider=response.fetch.provider,
        raw_contract_version=response.fetch.raw_contract_version,
        reference_version=reference_version,
        # Taken from the outcome rather than a parameter: the gate that ran is the only
        # honest source for which rules ran.
        validation_version=outcome.validation_version,
    )

    observations = [
        PriceObservation(
            instrument_id=response.instrument_id,
            event_time=validated.event_time,
            knowledge_time=knowledge_time,
            interval=response.fetch.interval,
            open=_price(validated.bar.open, reference),
            high=_price(validated.bar.high, reference),
            low=_price(validated.bar.low, reference),
            close=_price(validated.bar.close, reference),
            volume=None if validated.bar.volume is None else to_decimal(validated.bar.volume),
            authority=AuthorityTier.AUTHORITATIVE,
            quality_flags=tuple(sorted({*validated.quality_flags, *outcome.series_flags})),
            provenance=provenance,
        )
        for validated in outcome.accepted
    ]
    return tuple(sorted(observations, key=lambda o: o.event_time))


def to_quarantine_records(
    response: RawPriceResponse,
    outcome: ValidationOutcome,
    *,
    quarantined_at: datetime,
    raw_object_key: str,
    reference_version: str,
) -> tuple[QuarantineRecord, ...]:
    """Turn the gate's rejects into persistable records.

    Fail-closed means rejected data never reaches the canonical model — not that it
    vanishes. These records keep the rejected bar and its reasons for data-ops triage
    (doc 05/07).
    """
    if quarantined_at.tzinfo is None:
        raise ValueError("quarantined_at must be timezone-aware")

    provenance = Provenance(
        raw_object_key=raw_object_key,
        provider=response.fetch.provider,
        raw_contract_version=response.fetch.raw_contract_version,
        reference_version=reference_version,
        # Taken from the outcome rather than a parameter: the gate that ran is the only
        # honest source for which rules ran.
        validation_version=outcome.validation_version,
    )
    return tuple(
        QuarantineRecord(
            instrument_id=response.instrument_id,
            raw_timestamp=str(rejected.bar.timestamp),
            reasons=rejected.reasons,
            payload_json=json.dumps(
                {
                    "timestamp": rejected.bar.timestamp,
                    "open": rejected.bar.open,
                    "high": rejected.bar.high,
                    "low": rejected.bar.low,
                    "close": rejected.bar.close,
                    "volume": rejected.bar.volume,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            quarantined_at=quarantined_at,
            provenance=provenance,
        )
        for rejected in outcome.quarantined
    )


def _price(value: float | None, reference: InstrumentReference) -> PriceValue:
    """Build the typed price for this instrument's kind.

    Accepted bars always have OHLC present (the gate rejects missing fields), so a
    `None` here would be a gate defect rather than bad vendor data.
    """
    if value is None:
        raise ValueError("accepted bars must have OHLC present; gate invariant violated")
    amount = to_decimal(value)
    if reference.type is InstrumentType.INDEX:
        return IndexLevel(amount)
    assert reference.currency is not None  # enforced by InstrumentReference
    return Money(amount, reference.currency)
