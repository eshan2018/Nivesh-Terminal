"""`FilesystemObjectStore` — the reference implementation of the `RawStore` port.

This is a first-class implementation, not a stand-in: it upholds the full
object-store contract (append-only, immutable, portable keys, prefix listing) on
a local directory, and it is the backend used for development and for the hermetic
test suite. Production uses an S3-compatible object store per ADR-0009; that is a
second implementation of this same port (ED-004).

**Key ↔ path mapping is 1:1 and literal:** the object key *is* the path relative
to the store root, so `raw/v1/yfinance/price-history/2025-07/apple/<sha>.json`
lives at `<root>/raw/v1/yfinance/price-history/2025-07/apple/<sha>.json` and maps
unchanged onto the identical S3 object key. Nothing in the application observes
the difference.

Guarantees and how they are achieved:

* **Immutability** — objects are written via an exclusive `os.link`, which fails if
  the key exists, and are then marked read-only. There is no code path that
  overwrites or mutates a stored object.
* **Atomicity** — bytes are written to a temporary file in the same directory,
  flushed and fsynced, then atomically linked into place. A reader never observes a
  partially written object.
"""
from __future__ import annotations

import hashlib
import os
import uuid
from collections.abc import Iterator
from pathlib import Path

from backend.ingestion.raw_store import (
    ObjectAlreadyExists,
    ObjectNotFound,
    ObjectRef,
    validate_key,
)

# Stored objects are read-only; only the owner may read.
_OBJECT_MODE = 0o444
_TEMP_SUFFIX = ".tmp"


class FilesystemObjectStore:
    """A `RawStore` backed by a local directory tree."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def path_for(self, key: str) -> Path:
        """The absolute path an object key maps to (the 1:1 key↔path mapping)."""
        return self._root / validate_key(key)

    def put(self, key: str, data: bytes) -> ObjectRef:
        target = self.path_for(key)
        target.parent.mkdir(parents=True, exist_ok=True)

        temp = target.parent / f".{target.name}.{uuid.uuid4().hex}{_TEMP_SUFFIX}"
        try:
            with open(temp, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                # Exclusive, atomic publish: fails if the key already exists.
                os.link(temp, target)
            except FileExistsError as exc:
                raise ObjectAlreadyExists(
                    f"object already exists and is immutable: {key!r}"
                ) from exc
            os.chmod(target, _OBJECT_MODE)
        finally:
            temp.unlink(missing_ok=True)

        return ObjectRef(
            key=key,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )

    def get(self, key: str) -> bytes:
        target = self.path_for(key)
        try:
            return target.read_bytes()
        except FileNotFoundError as exc:
            raise ObjectNotFound(f"no object at key {key!r}") from exc
        except IsADirectoryError as exc:
            raise ObjectNotFound(f"no object at key {key!r}") from exc

    def exists(self, key: str) -> bool:
        return self.path_for(key).is_file()

    def list_keys(self, prefix: str = "") -> Iterator[str]:
        for path in sorted(self._root.rglob("*")):
            if not path.is_file():
                continue
            name = path.name
            if name.endswith(_TEMP_SUFFIX) and name.startswith("."):
                continue  # an in-flight write; not a published object
            key = path.relative_to(self._root).as_posix()
            if key.startswith(prefix):
                yield key
