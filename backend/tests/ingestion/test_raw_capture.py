"""Tests for the raw-capture stage (L2) and its object-key layout."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.ingestion.filesystem_object_store import FilesystemObjectStore
from backend.ingestion.raw_capture import (
    DATASET_PRICE_HISTORY,
    build_object_key,
    capture_price_history,
    shred_scope_prefix,
)
from backend.ingestion.raw_store import validate_key
from backend.platform.identifiers import InstrumentId
from backend.providers.ports.price_history import (
    FetchMetadata,
    RawBar,
    RawPriceResponse,
)

FETCHED_AT = datetime(2025, 7, 15, 9, 30, tzinfo=UTC)


def _response(
    instrument: str = "apple",
    close: float = 101.5,
    fetched_at: datetime = FETCHED_AT,
) -> RawPriceResponse:
    return RawPriceResponse(
        instrument_id=InstrumentId(instrument),
        bars=(
            RawBar("2025-07-01T00:00:00", 100.0, 101.0, 99.0, 100.5, 1000.0),
            RawBar("2025-07-02T00:00:00", 100.5, 102.0, 100.0, close, 1200.0),
        ),
        fetch=FetchMetadata(
            provider="yfinance",
            vendor_symbol="AAPL",
            interval="1d",
            fetched_at=fetched_at,
            raw_contract_version="yfinance-ohlcv/v1",
        ),
    )


@pytest.fixture()
def store(tmp_path: Path) -> FilesystemObjectStore:
    return FilesystemObjectStore(tmp_path / "raw")


# ── Key layout ────────────────────────────────────────────────────────────────

def test_key_layout_is_deterministic_and_portable() -> None:
    kwargs = dict(
        provider="yfinance",
        dataset=DATASET_PRICE_HISTORY,
        window="2025-07",
        instrument_id="apple",
        payload_sha256="a" * 64,
    )
    key = build_object_key(**kwargs)
    assert key == build_object_key(**kwargs)  # deterministic
    assert key == f"raw/v1/yfinance/price-history/2025-07/apple/{'a' * 64}.json"
    validate_key(key)  # portable as an S3 key and a relative path


def test_shred_scope_is_a_prefix_of_the_key() -> None:
    prefix = shred_scope_prefix(
        provider="yfinance", dataset=DATASET_PRICE_HISTORY, window="2025-07"
    )
    key = build_object_key(
        provider="yfinance",
        dataset=DATASET_PRICE_HISTORY,
        window="2025-07",
        instrument_id="apple",
        payload_sha256="b" * 64,
    )
    assert key.startswith(prefix)


@pytest.mark.parametrize("bad", ["with/slash", "..", "", "space bar"])
def test_unsafe_key_segments_are_rejected(bad: str) -> None:
    with pytest.raises(ValueError):
        build_object_key(
            provider="yfinance",
            dataset=DATASET_PRICE_HISTORY,
            window="2025-07",
            instrument_id=bad,
            payload_sha256="c" * 64,
        )


# ── Capture ───────────────────────────────────────────────────────────────────

def test_capture_writes_a_self_describing_envelope(store: FilesystemObjectStore) -> None:
    ref = capture_price_history(_response(), store)

    assert ref.key.startswith("raw/v1/yfinance/price-history/2025-07/apple/")
    document = json.loads(store.get(ref.key))
    assert document["instrument_id"] == "apple"
    assert len(document["payload"]) == 2
    assert document["payload"][1]["close"] == 101.5
    assert document["fetch"]["provider"] == "yfinance"
    assert document["fetch"]["vendor_symbol"] == "AAPL"
    assert document["fetch"]["raw_contract_version"] == "yfinance-ohlcv/v1"


def test_capture_is_idempotent_for_identical_payloads(store: FilesystemObjectStore) -> None:
    first = capture_price_history(_response(), store)
    # A later fetch returning identical vendor data must converge, not duplicate.
    second = capture_price_history(_response(fetched_at=datetime(2025, 7, 20, tzinfo=UTC)), store)

    assert first.key == second.key
    assert first.sha256 == second.sha256
    assert len(list(store.list_keys())) == 1


def test_capture_of_changed_payload_yields_a_distinct_object(
    store: FilesystemObjectStore,
) -> None:
    first = capture_price_history(_response(close=101.5), store)
    second = capture_price_history(_response(close=999.0), store)

    assert first.key != second.key
    assert len(list(store.list_keys())) == 2


def test_capture_partitions_by_instrument_and_window(store: FilesystemObjectStore) -> None:
    capture_price_history(_response(instrument="apple"), store)
    capture_price_history(_response(instrument="tcs"), store)
    capture_price_history(
        _response(instrument="apple", fetched_at=datetime(2025, 8, 1, tzinfo=UTC)), store
    )

    july = shred_scope_prefix(
        provider="yfinance", dataset=DATASET_PRICE_HISTORY, window="2025-07"
    )
    august = shred_scope_prefix(
        provider="yfinance", dataset=DATASET_PRICE_HISTORY, window="2025-08"
    )
    assert len(list(store.list_keys(july))) == 2
    assert len(list(store.list_keys(august))) == 1


def test_stored_object_is_never_mutated_by_recapture(store: FilesystemObjectStore) -> None:
    ref = capture_price_history(_response(), store)
    before = store.get(ref.key)
    capture_price_history(_response(fetched_at=datetime(2026, 1, 1, tzinfo=UTC)), store)
    # Different window -> different key; the original object is byte-identical.
    assert store.get(ref.key) == before
