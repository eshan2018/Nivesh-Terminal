"""The `RawStore` port — a provider-neutral object-store contract (L2).

Owning docs: 05 (raw capture stage), 07 (Raw Store role), ADR-0009 (raw lives in
object storage, never in the hot relational store, never discarded).

The contract is deliberately object-storage shaped — opaque byte objects addressed
by a string key — so that a filesystem backend and an S3 backend are the *same*
contract with different implementations. Application code depends only on this
port; swapping the backend changes one implementation module and nothing else.

Semantics every implementation must uphold:

* **Append-only / immutable.** `put` never overwrites. Writing an existing key
  raises `ObjectAlreadyExists`. There is no update and no delete in this contract —
  lawful erasure is crypto-shredding by key destruction (doc 17), not object
  mutation.
* **Opaque payloads.** The store knows bytes and keys, nothing about providers,
  datasets, or instruments. Key *layout* is the caller's concern (see raw_capture).
* **Keys are portable.** A key is a `/`-delimited relative path with no leading or
  trailing slash and no `.`/`..` segments, so it maps 1:1 onto an S3 object key and
  onto a relative filesystem path.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class RawStoreError(Exception):
    """Base class for raw-store failures."""


class ObjectAlreadyExists(RawStoreError):
    """A write was attempted against an existing key (objects are immutable)."""


class ObjectNotFound(RawStoreError):
    """The requested key does not exist."""


@dataclass(frozen=True, slots=True)
class ObjectRef:
    """A handle to a stored object — the seed of a lineage chain (doc 05).

    `sha256` is the digest of the stored bytes (the object's own content hash),
    analogous to an S3 ETag. It is not necessarily the digest embedded in the key;
    see `raw_capture` for the key's content-addressing scheme.
    """

    key: str
    size_bytes: int
    sha256: str


def validate_key(key: str) -> str:
    """Return `key` if it is a portable object key, else raise `ValueError`.

    Enforced so that keys are safe as both S3 keys and relative filesystem paths
    (in particular: no absolute paths and no traversal).
    """
    if not key or key.strip() != key:
        raise ValueError("object key must be a non-empty, untrimmed-free string")
    if key.startswith("/") or key.endswith("/"):
        raise ValueError(f"object key must not start or end with '/': {key!r}")
    if "\\" in key:
        raise ValueError(f"object key must use '/' separators: {key!r}")
    segments = key.split("/")
    if any(seg in ("", ".", "..") for seg in segments):
        raise ValueError(f"object key has an empty or traversal segment: {key!r}")
    return key


@runtime_checkable
class RawStore(Protocol):
    """An append-only, immutable object store for verbatim raw captures."""

    def put(self, key: str, data: bytes) -> ObjectRef:
        """Store `data` at `key`.

        Raises `ObjectAlreadyExists` if the key is taken (never overwrites) and
        `ValueError` if the key is not portable.
        """
        ...

    def get(self, key: str) -> bytes:
        """Return the bytes stored at `key`, or raise `ObjectNotFound`."""
        ...

    def exists(self, key: str) -> bool:
        """Whether an object is stored at `key`."""
        ...

    def list_keys(self, prefix: str = "") -> Iterator[str]:
        """Yield stored keys beginning with `prefix`, in lexicographic order.

        Prefix listing is what makes a crypto-shred scope addressable (doc 17) and
        what lets recompute-from-raw enumerate a window.
        """
        ...
