"""Contract tests for the `RawStore` port, exercised via `FilesystemObjectStore`.

These assert the *contract*, not the backend: any future implementation (S3) must
pass the same expectations. Hermetic — a temporary directory, no services.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from backend.ingestion.filesystem_object_store import FilesystemObjectStore
from backend.ingestion.raw_store import (
    ObjectAlreadyExists,
    ObjectNotFound,
    RawStore,
    validate_key,
)

KEY = "raw/v1/yfinance/price-history/2025-07/apple/abc123.json"
DATA = b'{"hello":"world"}'


@pytest.fixture()
def store(tmp_path: Path) -> FilesystemObjectStore:
    return FilesystemObjectStore(tmp_path / "raw")


def test_implements_the_port(store: FilesystemObjectStore) -> None:
    assert isinstance(store, RawStore)


def test_put_then_get_round_trips(store: FilesystemObjectStore) -> None:
    ref = store.put(KEY, DATA)
    assert ref.key == KEY
    assert ref.size_bytes == len(DATA)
    assert ref.sha256 == hashlib.sha256(DATA).hexdigest()
    assert store.get(KEY) == DATA
    assert store.exists(KEY)


def test_objects_are_immutable_put_never_overwrites(store: FilesystemObjectStore) -> None:
    store.put(KEY, DATA)
    with pytest.raises(ObjectAlreadyExists):
        store.put(KEY, b"different bytes")
    assert store.get(KEY) == DATA  # original is untouched


def test_stored_object_is_read_only_on_disk(store: FilesystemObjectStore) -> None:
    store.put(KEY, DATA)
    mode = store.path_for(KEY).stat().st_mode
    assert not mode & 0o222, "stored objects must not be writable"


def test_get_missing_raises_not_found(store: FilesystemObjectStore) -> None:
    with pytest.raises(ObjectNotFound):
        store.get("raw/v1/yfinance/price-history/2025-07/apple/missing.json")
    assert not store.exists("raw/v1/nope.json")


def test_key_maps_one_to_one_onto_a_relative_path(store: FilesystemObjectStore) -> None:
    store.put(KEY, DATA)
    expected = store.root / KEY
    assert expected.is_file()
    assert store.path_for(KEY) == expected
    # The key is exactly the path relative to the root — the S3 mapping guarantee.
    assert expected.relative_to(store.root).as_posix() == KEY


def test_list_keys_by_prefix_and_shred_scope(store: FilesystemObjectStore) -> None:
    july = "raw/v1/yfinance/price-history/2025-07/"
    august = "raw/v1/yfinance/price-history/2025-08/"
    store.put(july + "apple/a.json", b"1")
    store.put(july + "tcs/b.json", b"2")
    store.put(august + "apple/c.json", b"3")

    assert list(store.list_keys()) == sorted(
        [july + "apple/a.json", july + "tcs/b.json", august + "apple/c.json"]
    )
    # A crypto-shred scope is exactly a key prefix (doc 17).
    assert list(store.list_keys(july)) == sorted([july + "apple/a.json", july + "tcs/b.json"])


def test_no_temp_files_are_left_behind(store: FilesystemObjectStore) -> None:
    store.put(KEY, DATA)
    leftovers = [p for p in store.root.rglob("*") if p.is_file() and p.name.endswith(".tmp")]
    assert leftovers == []


def test_writes_are_atomic_no_partial_object_on_failure(
    store: FilesystemObjectStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*args: object, **kwargs: object) -> None:
        raise OSError("simulated failure during publish")

    monkeypatch.setattr(os, "link", explode)
    with pytest.raises(OSError):
        store.put(KEY, DATA)
    assert not store.exists(KEY)  # nothing half-published
    assert [p for p in store.root.rglob("*") if p.is_file()] == []  # no temp residue


@pytest.mark.parametrize(
    "bad_key",
    ["", "/leading", "trailing/", "a//b", "a/../b", "a/./b", "back\\slash"],
)
def test_invalid_keys_are_rejected(store: FilesystemObjectStore, bad_key: str) -> None:
    with pytest.raises(ValueError):
        validate_key(bad_key)
    with pytest.raises(ValueError):
        store.put(bad_key, DATA)
