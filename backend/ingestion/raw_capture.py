"""Raw capture (L2, doc 05 stage 2) — the object-key layout and the capture stage.

The verbatim provider payload is written to the `RawStore` **before any
transformation**, append-only. This is the root of every lineage chain and the
source for recompute-from-raw.

Object-key layout (backend-independent; identical on filesystem and on S3):

    raw/v1/{provider}/{dataset}/{window}/{instrument_id}/{payload_sha256}.json
    └────┘ └───────┘ └───────┘ └──────┘ └─────────────┘ └───────────────┘
      │        │         │         │            │               └ content address
      │        │         │         │            └ internal InstrumentId (ADR-0006)
      │        │         │         └ YYYY-MM — the crypto-shred scope (doc 17)
      │        │         └ logical dataset
      │        └ provider that produced the payload
      └ layout version, so the layout can evolve unambiguously

Two properties matter:

* **Content-addressed → idempotent.** The key embeds the SHA-256 of the *verbatim
  payload only* (not the fetch metadata), so re-fetching unchanged vendor data
  yields the same key and capture converges instead of accumulating duplicates.
  Idempotent, replayable tasks are required of every pipeline task (doc 16).
* **Shred-scope addressable.** Everything for one provider/dataset/month shares a
  key prefix, so a per-source-window key can be destroyed to crypto-shred that
  window (doc 17) and prefix listing can enumerate it.

The stored object is an envelope of the verbatim payload *plus* the fetch metadata
that produced it, so raw is self-describing for recompute. Because the key is
addressed on payload alone, a repeat capture of identical data keeps the first
capture's metadata; subsequent fetch events are recorded in lineage (a later
milestone), not by rewriting an immutable object.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.ingestion.raw_store import ObjectAlreadyExists, ObjectRef, RawStore
from backend.providers.ports.price_history import RawPriceResponse

KEY_LAYOUT_VERSION = "v1"
DATASET_PRICE_HISTORY = "price-history"

_ALLOWED_SEGMENT_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
)


def _safe_segment(value: str, *, field: str) -> str:
    """Validate one key segment (no separators, no traversal, no surprises)."""
    if not value:
        raise ValueError(f"{field} must not be empty")
    if value in (".", ".."):
        raise ValueError(f"{field} must not be a traversal segment: {value!r}")
    invalid = sorted(set(value) - _ALLOWED_SEGMENT_CHARS)
    if invalid:
        raise ValueError(f"{field} contains characters invalid in an object key: {invalid}")
    return value


def shred_scope_prefix(*, provider: str, dataset: str, window: str) -> str:
    """The key prefix covering one crypto-shred scope (provider/dataset/window)."""
    return (
        f"raw/{KEY_LAYOUT_VERSION}/"
        f"{_safe_segment(provider, field='provider')}/"
        f"{_safe_segment(dataset, field='dataset')}/"
        f"{_safe_segment(window, field='window')}/"
    )


def build_object_key(
    *,
    provider: str,
    dataset: str,
    window: str,
    instrument_id: str,
    payload_sha256: str,
) -> str:
    """Build the deterministic object key for one captured payload."""
    prefix = shred_scope_prefix(provider=provider, dataset=dataset, window=window)
    instrument = _safe_segment(instrument_id, field="instrument_id")
    digest = _safe_segment(payload_sha256, field="payload_sha256")
    return f"{prefix}{instrument}/{digest}.json"


def _canonical_json(document: Any) -> bytes:
    """Deterministic JSON encoding — stable ordering, no incidental whitespace."""
    return json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _payload_document(response: RawPriceResponse) -> list[dict[str, Any]]:
    """The verbatim provider payload — the bars exactly as delivered."""
    return [
        {
            "timestamp": bar.timestamp,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
        for bar in response.bars
    ]


def _envelope(response: RawPriceResponse, payload: list[dict[str, Any]]) -> dict[str, Any]:
    fetch = response.fetch
    return {
        "instrument_id": response.instrument_id.value,
        "payload": payload,
        "fetch": {
            "provider": fetch.provider,
            "vendor_symbol": fetch.vendor_symbol,
            "interval": fetch.interval,
            "fetched_at": fetch.fetched_at.isoformat(),
            "raw_contract_version": fetch.raw_contract_version,
        },
    }


def capture_price_history(response: RawPriceResponse, store: RawStore) -> ObjectRef:
    """Write a price-history response to the raw store; return its object handle.

    Idempotent: capturing identical vendor data twice resolves to the same key and
    leaves the existing immutable object untouched.
    """
    payload = _payload_document(response)
    payload_digest = hashlib.sha256(_canonical_json(payload)).hexdigest()
    key = build_object_key(
        provider=response.fetch.provider,
        dataset=DATASET_PRICE_HISTORY,
        window=response.fetch.fetched_at.strftime("%Y-%m"),
        instrument_id=response.instrument_id.value,
        payload_sha256=payload_digest,
    )
    body = _canonical_json(_envelope(response, payload))
    try:
        return store.put(key, body)
    except ObjectAlreadyExists:
        stored = store.get(key)
        return ObjectRef(
            key=key,
            size_bytes=len(stored),
            sha256=hashlib.sha256(stored).hexdigest(),
        )
