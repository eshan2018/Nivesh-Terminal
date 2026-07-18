"""SQLite implementation of `MarketDataRepository` (local/CI backend, ED-003).

Uses only the standard library, so the domain store needs no service and no
dependency. PostgreSQL remains the production system of record (ADR-0008); this
class and a future Postgres class are two implementations of one port, and the
schema shape is deliberately identical (see `schema.py`).

Exactness: monetary values are written as the `Decimal`'s text form and read back
with `Decimal(...)`, so money round-trips bit-exactly. No value ever passes through
a binary float.

Concurrency: a repository owns one connection and is not thread-safe, which matches
the single-process pipeline the skeleton runs. A connection pool is a Postgres-era
concern.
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import TracebackType

from backend.domain.market_data.schema import (
    ALL_DDL,
    OBSERVATIONS_TABLE,
    QUARANTINE_TABLE,
)
from backend.domain.model.observations import (
    AuthorityTier,
    PriceObservation,
    Provenance,
    QuarantineRecord,
)
from backend.domain.model.quantities import Currency, IndexLevel, Money, PriceValue
from backend.platform.identifiers import InstrumentId

_KIND_MONEY = "MONEY"
_KIND_INDEX = "INDEX_LEVEL"

_OBSERVATION_COLUMNS = (
    "instrument_id, interval, event_time, knowledge_time, value_kind, currency, "
    "open_value, high_value, low_value, close_value, volume, authority, quality_flags, "
    "raw_object_key, provider, raw_contract_version, reference_version"
)

_SELECT_LATEST = f"""
SELECT {_OBSERVATION_COLUMNS}
FROM {OBSERVATIONS_TABLE} AS o
WHERE o.instrument_id = ? AND o.interval = ?
  AND o.knowledge_time = (
      SELECT MAX(v.knowledge_time) FROM {OBSERVATIONS_TABLE} AS v
      WHERE v.instrument_id = o.instrument_id
        AND v.interval = o.interval
        AND v.event_time = o.event_time
  )
ORDER BY o.event_time
"""


def _iso(moment: datetime) -> str:
    """Normalize to UTC ISO-8601 so text ordering equals chronological ordering."""
    return moment.astimezone(UTC).isoformat()


class SqliteMarketDataRepository:
    """A `MarketDataRepository` backed by SQLite."""

    def __init__(self, database: Path | str = ":memory:") -> None:
        self._connection = sqlite3.connect(str(database))
        self._connection.row_factory = sqlite3.Row
        with self._connection:
            for statement in ALL_DDL:
                self._connection.execute(statement)

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> SqliteMarketDataRepository:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    # ── observations ──────────────────────────────────────────────────────────

    def save_observations(self, observations: Sequence[PriceObservation]) -> int:
        rows = [self._observation_row(o) for o in observations]
        if not rows:
            return 0
        placeholders = ", ".join(["?"] * 17)
        with self._connection:
            cursor = self._connection.executemany(
                f"INSERT OR IGNORE INTO {OBSERVATIONS_TABLE} ({_OBSERVATION_COLUMNS}) "
                f"VALUES ({placeholders})",
                rows,
            )
            return cursor.rowcount

    def get_observations(
        self, instrument_id: InstrumentId, *, interval: str
    ) -> tuple[PriceObservation, ...]:
        cursor = self._connection.execute(_SELECT_LATEST, (instrument_id.value, interval))
        return tuple(self._observation_from_row(row) for row in cursor.fetchall())

    @staticmethod
    def _observation_row(observation: PriceObservation) -> tuple[object, ...]:
        kind, currency = _kind_and_currency(observation.close)
        return (
            observation.instrument_id.value,
            observation.interval,
            _iso(observation.event_time),
            _iso(observation.knowledge_time),
            kind,
            currency,
            str(_raw_amount(observation.open)),
            str(_raw_amount(observation.high)),
            str(_raw_amount(observation.low)),
            str(_raw_amount(observation.close)),
            None if observation.volume is None else str(observation.volume),
            observation.authority.value,
            json.dumps(list(observation.quality_flags)),
            observation.provenance.raw_object_key,
            observation.provenance.provider,
            observation.provenance.raw_contract_version,
            observation.provenance.reference_version,
        )

    @staticmethod
    def _observation_from_row(row: sqlite3.Row) -> PriceObservation:
        def value(column: str) -> PriceValue:
            amount = Decimal(row[column])
            if row["value_kind"] == _KIND_INDEX:
                return IndexLevel(amount)
            return Money(amount, Currency(row["currency"]))

        return PriceObservation(
            instrument_id=InstrumentId(row["instrument_id"]),
            event_time=datetime.fromisoformat(row["event_time"]),
            knowledge_time=datetime.fromisoformat(row["knowledge_time"]),
            interval=row["interval"],
            open=value("open_value"),
            high=value("high_value"),
            low=value("low_value"),
            close=value("close_value"),
            volume=None if row["volume"] is None else Decimal(row["volume"]),
            authority=AuthorityTier(row["authority"]),
            quality_flags=tuple(json.loads(row["quality_flags"])),
            provenance=Provenance(
                raw_object_key=row["raw_object_key"],
                provider=row["provider"],
                raw_contract_version=row["raw_contract_version"],
                reference_version=row["reference_version"],
            ),
        )

    # ── quarantine ────────────────────────────────────────────────────────────

    def save_quarantined(self, records: Sequence[QuarantineRecord]) -> int:
        rows = [
            (
                record.instrument_id.value,
                record.provenance.raw_object_key,
                record.raw_timestamp,
                json.dumps(list(record.reasons)),
                record.payload_json,
                _iso(record.quarantined_at),
                record.provenance.provider,
                record.provenance.reference_version,
            )
            for record in records
        ]
        if not rows:
            return 0
        with self._connection:
            cursor = self._connection.executemany(
                f"INSERT OR IGNORE INTO {QUARANTINE_TABLE} (instrument_id, raw_object_key, "
                "raw_timestamp, reasons, payload_json, quarantined_at, provider, "
                "reference_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            return cursor.rowcount

    def get_quarantined(self, instrument_id: InstrumentId) -> tuple[QuarantineRecord, ...]:
        cursor = self._connection.execute(
            f"SELECT * FROM {QUARANTINE_TABLE} WHERE instrument_id = ? ORDER BY raw_timestamp",
            (instrument_id.value,),
        )
        return tuple(
            QuarantineRecord(
                instrument_id=InstrumentId(row["instrument_id"]),
                raw_timestamp=row["raw_timestamp"],
                reasons=tuple(json.loads(row["reasons"])),
                payload_json=row["payload_json"],
                quarantined_at=datetime.fromisoformat(row["quarantined_at"]),
                provenance=Provenance(
                    raw_object_key=row["raw_object_key"],
                    provider=row["provider"],
                    raw_contract_version="",  # not part of the quarantine record
                    reference_version=row["reference_version"],
                ),
            )
            for row in cursor.fetchall()
        )


def _kind_and_currency(value: PriceValue) -> tuple[str, str | None]:
    if isinstance(value, IndexLevel):
        return _KIND_INDEX, None
    return _KIND_MONEY, value.currency.value


def _raw_amount(value: PriceValue) -> Decimal:
    return value.points if isinstance(value, IndexLevel) else value.amount
