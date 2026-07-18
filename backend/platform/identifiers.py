"""Platform identifiers.

`InstrumentId` is Nivesh Terminal's *internal* instrument identifier (ADR-0006):
no vendor symbol, ISIN, or ticker is ever an identity. Vendor symbols are a
cross-reference resolved inside provider adapters (doc 06).

M2 note: this is the minimal identity needed for the L1 provider slice. The full
canonical model (Instrument/Company/Exchange, doc 04) is Phase 1 work.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InstrumentId:
    """An opaque, stable internal instrument identifier."""

    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("InstrumentId.value must be a non-empty string")

    def __str__(self) -> str:
        return self.value
