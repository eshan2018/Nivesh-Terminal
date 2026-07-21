# Implementation · 04 · Recompute-from-Raw — Procedure & RTO Measurement

| | |
|---|---|
| **Status** | Living — implementation tier |
| **Owner** | Implementing engineer |
| **Governed by** | Architecture v2.0 — [doc 12 Deployment](../architecture/12-deployment-strategy.md) (RPO/RTO), [ADR-0017](../architecture/18-architecture-decision-records.md#adr-0017--first-class-lineage-with-three-guarantee-tiers) (lineage tiers), [doc 16](../architecture/16-data-orchestration-and-freshness.md) |
| **Implements** | [Walking Skeleton Plan §B6](00-walking-skeleton-plan.md) — the final Phase 0.5 Definition-of-Done item |
| **Regenerate** | `make recompute` (or `python -m tools.recompute_rto --json`) |

## Purpose

The architecture claims that **every derived value is recomputable from immutable raw**
([ADR-0017](../architecture/18-architecture-decision-records.md#adr-0017--first-class-lineage-with-three-guarantee-tiers)'s *recomputable* tier; principle 6). Until M5 that was an assertion.
This document records the procedure that tests it, and the number it produced.

If the claim were false, the raw store would be dead weight, "recomputable lineage" would
be marketing, and the disaster-recovery story would not exist.

## The procedure

A program, not a runbook — so it is repeatable and cannot rot:

```bash
make recompute
```

It runs, in one hermetic temporary directory that is deleted afterwards:

1. **Ingest** 500 daily bars through the real DAG (`backend/orchestration/pipeline.py`):
   fetch → capture → validate → normalize → persist.
2. **Compute** the served value: `close_price_series` feature → `one_year_return` engine.
3. **Drop** canonical and derived data — realized by rebuilding into a store that never
   existed. The repository port has no delete method and does not need one: the premise
   under test is that canonical data is *derivable*, so building it again from nothing
   expresses that exactly. Adding destructive methods to a port in order to test a
   rebuild would be the tail wagging the dog.
4. **Replay** the immutable raw record through validate → normalize → persist → feature
   → engine, using the *same code path* as ingestion (`replay_from_raw`) rather than a
   second implementation — a rebuild written twice proves nothing about the pipeline.
5. **Compare** the rebuilt `AnalyticResult` to the original, **in full**.
6. **Report** the wall-clock time.

## What "byte-identical" means here

Two values could differ for reasons that are not defects. Both are handled as **inputs**
rather than excluded from the comparison:

| Field | Why it could drift | How it is pinned |
|---|---|---|
| `knowledge_time` | Stamped at normalization | Taken from the raw envelope's `fetch.fetched_at`, so a replay *recovers* the original instant instead of minting a new one |
| `computed_at` | Supplied to the engine | Passed in from the recorded run, so the replay reproduces rather than re-times |

Comparing everything *except* the timestamps would have been easier — and would still
pass if the rebuild silently used a different set of observations. The full-envelope
comparison is what makes the assertion load-bearing. This is what
[ADR-0017](../architecture/18-architecture-decision-records.md#adr-0017--first-class-lineage-with-three-guarantee-tiers)'s
*bit-reproducible* tier actually claims: pin the code, formula version and reference
snapshot, and the output reproduces exactly.

## The measurement

Recorded 2026-07-22, M5.

```
instrument            reliance
bars ingested         500
raw objects replayed  1
observations rebuilt  500
reproduction          BYTE-IDENTICAL
```

| Run | Recompute time |
|-----|----------------|
| 1 | 0.0113 s |
| 2 | 0.0116 s |
| 3 | 0.0111 s |
| 4 | 0.0114 s |
| 5 | 0.0112 s |

> ### **RTO (local baseline): ~0.011 s** for 500 observations, one instrument.

**Environment:** local filesystem raw store · SQLite domain store · single process ·
one instrument · Python 3.12.

## What this number is not

It is the **first data point**, not a production RTO. Quoting it without this paragraph
would turn a measurement into a false claim.

- **Storage is local.** Production raw capture is S3-compatible object storage
  ([ADR-0009](../architecture/18-architecture-decision-records.md#adr-0009--object-storage-for-immutable-raw-capture-and-deep-history)/[ED-004](01-engineering-decisions.md#ed-004--object-storage-realization)), which adds per-object network latency. A rebuild reading
  thousands of objects is dominated by round-trips, not by the compute measured here.
- **The domain store is SQLite.** Production is PostgreSQL
  ([ADR-0008](../architecture/18-architecture-decision-records.md#adr-0008--postgresql-as-the-primary-system-of-record)/[ED-003](01-engineering-decisions.md#ed-003--postgresql-deployment-realization)); the write path and its concurrency behaviour differ entirely.
- **Scope is one instrument and one metric.** Real recovery replays the whole universe
  across every materialized artifact.
- **No network, no contention, no cold caches.**

**Therefore: re-measure after deploy. Do not extrapolate.** The value of this number is
that the *procedure* exists and passes — the mechanism is proven, and the figure becomes
meaningful when it is re-run against real infrastructure.

## Change log

| Date | Change |
|------|--------|
| 2026-07-22 | Procedure authored and first measurement recorded (M5). Byte-identical reproduction confirmed; RTO ~0.011 s on the local baseline. |
