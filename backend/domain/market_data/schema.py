"""The `market_data` module's own schema (L5, doc 07 / ADR-0003).

This module owns these tables; no other module reads them (the guardrail enforces
that). In PostgreSQL these become `market_data.price_observations` and
`market_data.quarantined_bars`; SQLite has no schema namespaces, so the module
name is carried in the table prefix and the shape is otherwise identical.

Two modelling decisions are load-bearing:

* **Money is stored as exact text, never as a float.** SQLite's `REAL` is binary
  floating point and would silently corrupt monetary values; storing the `Decimal`'s
  string form round-trips exactly (ADR-0016). PostgreSQL uses `NUMERIC` for the same
  guarantee.
* **The index/currency invariant is enforced by the database**, not merely by the
  application: a `CHECK` constraint makes it impossible to store an index level with
  a currency — the FX-conversion bug is unrepresentable at rest as well as in memory.

Prices are **effective-dated with versioned corrections** (doc 04 temporal matrix):
the primary key includes `knowledge_time`, so re-ingesting identical data is a no-op
while a later correction inserts a new version. The `knowledge_time` column is
populated from the first row (C1); only the as-of *query* machinery is deferred.
"""
from __future__ import annotations

SCHEMA_VERSION = "market_data/v1"

OBSERVATIONS_TABLE = "market_data_price_observations"
QUARANTINE_TABLE = "market_data_quarantined_bars"

CREATE_OBSERVATIONS = f"""
CREATE TABLE IF NOT EXISTS {OBSERVATIONS_TABLE} (
    instrument_id        TEXT NOT NULL,
    interval             TEXT NOT NULL,
    event_time           TEXT NOT NULL,   -- ISO-8601, UTC, timezone-aware
    knowledge_time       TEXT NOT NULL,   -- ISO-8601, UTC; the version axis (C1)
    value_kind           TEXT NOT NULL,   -- 'MONEY' | 'INDEX_LEVEL'
    currency             TEXT,            -- NULL iff value_kind = 'INDEX_LEVEL'
    open_value           TEXT NOT NULL,   -- exact Decimal, as text
    high_value           TEXT NOT NULL,
    low_value            TEXT NOT NULL,
    close_value          TEXT NOT NULL,
    volume               TEXT,            -- exact Decimal, as text; NULL if absent
    authority            TEXT NOT NULL,
    quality_flags        TEXT NOT NULL,   -- JSON array
    raw_object_key       TEXT NOT NULL,   -- lineage: the immutable raw object
    provider             TEXT NOT NULL,
    raw_contract_version TEXT NOT NULL,
    reference_version    TEXT NOT NULL,
    PRIMARY KEY (instrument_id, interval, event_time, knowledge_time),
    CHECK (
        (value_kind = 'INDEX_LEVEL' AND currency IS NULL)
        OR (value_kind = 'MONEY' AND currency IS NOT NULL)
    )
);
"""

CREATE_QUARANTINE = f"""
CREATE TABLE IF NOT EXISTS {QUARANTINE_TABLE} (
    instrument_id     TEXT NOT NULL,
    raw_object_key    TEXT NOT NULL,
    raw_timestamp     TEXT NOT NULL,   -- verbatim; may be unparseable, hence TEXT
    reasons           TEXT NOT NULL,   -- JSON array
    payload_json      TEXT NOT NULL,   -- the rejected bar, for data-ops triage
    quarantined_at    TEXT NOT NULL,   -- ISO-8601, UTC
    provider          TEXT NOT NULL,
    reference_version TEXT NOT NULL,
    PRIMARY KEY (instrument_id, raw_object_key, raw_timestamp)
);
"""

ALL_DDL: tuple[str, ...] = (CREATE_OBSERVATIONS, CREATE_QUARANTINE)
