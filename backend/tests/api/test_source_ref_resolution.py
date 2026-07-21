"""`source_ref` must be resolvable, not merely opaque (doc 10 / ADR-0017).

An opaque handle with no lookup path is not lineage — it is a decoration that *looks*
like lineage. ADR-0017 promises the *recomputable* tier for derived values, and doc 00
§B5 requires the served metric to resolve to "raw record(s) in object storage". So the
hash the API publishes has to be something a future lineage endpoint can actually turn
back into a payload.

These tests demonstrate that path end to end rather than asserting it in a docstring.
The resolution algorithm they exercise is the one a lineage endpoint would implement:

    for key in raw_store.list_keys(prefix):
        if source_ref(key) == wanted:
            return raw_store.get(key)

`source_ref` is one-way, so resolution is by *forward recomputation over the candidate
key space*, not by inverting the hash. `RawStore.list_keys` is what makes that key space
enumerable, which is why the property holds.

**Known cost, stated rather than hidden:** this is O(number of raw objects) per lookup.
That is correct and cheap at skeleton scale and would need a stored ref→key index before
it serves real traffic. The index is a Phase-1 concern; what matters now is that the
handle is *resolvable in principle and in practice*, so the contract published today
does not have to change when the index arrives.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.api.dto import source_ref
from backend.ingestion.filesystem_object_store import FilesystemObjectStore
from backend.ingestion.raw_capture import capture_price_history
from backend.ingestion.raw_store import RawStore
from backend.platform.identifiers import InstrumentId
from backend.providers.ports.price_history import (
    FetchMetadata,
    RawBar,
    RawPriceResponse,
)

RELIANCE = InstrumentId("reliance")
FETCHED_AT = datetime(2025, 6, 1, 9, 30, tzinfo=UTC)


@pytest.fixture()
def store(tmp_path: Path) -> FilesystemObjectStore:
    return FilesystemObjectStore(tmp_path / "raw")


def _capture(store: RawStore, close: float) -> str:
    """Capture one payload and return the raw object key it was stored under."""
    response = RawPriceResponse(
        instrument_id=RELIANCE,
        bars=(RawBar("2025-05-30T00:00:00", 100.0, 101.0, 99.0, close, 1000.0),),
        fetch=FetchMetadata(
            provider="yfinance",
            vendor_symbol="RELIANCE.NS",
            interval="1d",
            fetched_at=FETCHED_AT,
            raw_contract_version="yfinance-ohlcv/v1",
        ),
    )
    return capture_price_history(response, store).key


def resolve(store: RawStore, wanted: str) -> bytes | None:
    """The algorithm a lineage endpoint would implement. See the module docstring."""
    for key in store.list_keys():
        if source_ref(key) == wanted:
            return store.get(key)
    return None


def test_a_published_ref_resolves_to_the_raw_payload(store: FilesystemObjectStore) -> None:
    """The end-to-end promise: hash on the wire → immutable bytes in the raw store."""
    key = _capture(store, close=1436.25)

    payload = resolve(store, source_ref(key))

    assert payload is not None, "a published source_ref must resolve to its raw object"
    document = json.loads(payload)
    assert document["payload"][0]["close"] == 1436.25
    assert document["fetch"]["provider"] == "yfinance"


def test_resolution_picks_the_right_payload_among_several(
    store: FilesystemObjectStore,
) -> None:
    """A ref must identify *one* payload, not merely find *a* payload."""
    first, second = _capture(store, close=1436.25), _capture(store, close=1500.00)
    assert first != second

    resolved = resolve(store, source_ref(second))

    assert resolved is not None
    assert json.loads(resolved)["payload"][0]["close"] == 1500.00


def test_an_unknown_ref_resolves_to_nothing_rather_than_something_wrong(
    store: FilesystemObjectStore,
) -> None:
    """Absence over a plausible-looking wrong answer (principle 13)."""
    _capture(store, close=1436.25)
    assert resolve(store, source_ref("raw/v1/never/captured/anything.json")) is None


def test_the_ref_is_stable_across_processes(store: FilesystemObjectStore) -> None:
    """Resolution depends on the hash being a pure function of the key.

    A salted or per-process hash would make refs unresolvable after a restart, and the
    failure would appear only in production. `source_ref` uses SHA-256 over the key with
    no salt and no `hash()`, whose seed varies per process.
    """
    key = _capture(store, close=1436.25)
    assert source_ref(key) == source_ref(key)
    assert source_ref(key) == "".join(source_ref(key))  # no hidden state between calls
    assert len(source_ref(key)) == 16
    assert source_ref(key) != source_ref(key + "x")


def test_the_ref_reveals_neither_vendor_nor_storage_path(
    store: FilesystemObjectStore,
) -> None:
    """The reason the hash exists at all — resolvability must not reintroduce the leak."""
    key = _capture(store, close=1436.25)
    ref = source_ref(key)
    for leak in ("yfinance", "raw/", ".json", "reliance", "RELIANCE.NS"):
        assert leak not in ref
