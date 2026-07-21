# Implementation · 04 · Recompute-from-Raw — Procedure & RTO Measurement

| | |
|---|---|
| **Status** | Living — implementation tier |
| **Owner** | Implementing engineer |
| **Governed by** | Architecture v2.0 — [doc 12 Deployment](../architecture/12-deployment-strategy.md) (RPO/RTO), [ADR-0017](../architecture/18-architecture-decision-records.md#adr-0017--first-class-lineage-with-three-guarantee-tiers) (lineage tiers), [doc 16](../architecture/16-data-orchestration-and-freshness.md) |
| **Implements** | [Walking Skeleton Plan §B6](00-walking-skeleton-plan.md) — the final Phase 0.5 Definition-of-Done item |
| **Regenerate** | `make recompute` · `python -m tools.recompute_rto --samples 20 --json` |

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

Recorded 2026-07-22 (M5). Reproduce with `make recompute` — or
`python -m tools.recompute_rto --samples 20 --json` for the raw figures below.

### Dataset

| | |
|---|---|
| Instrument | `reliance` (1 of the 5 skeleton instruments) |
| Bars ingested | 500 daily bars (~2 calendar years) |
| Observations rebuilt | 500 |
| Raw objects replayed | 1 |
| Raw bytes read | 55,702 |
| Metric | `one-year-total-return/v1` → `0.06121134020618557` |

### Environment

| | |
|---|---|
| Python | 3.12.4 (CPython) |
| OS | Darwin 25.5.0 |
| Machine | arm64 · arm · 8 logical CPUs |
| Raw store | FilesystemObjectStore (local disk) |
| Domain store | SQLite (stdlib, single connection) |
| Concurrency | single process, single thread |

### Results — 20 independent cold rebuilds

Each sample runs in its own temporary workspace, so no run benefits from another's warm
caches or a populated store. Every sample is a full rebuild from raw.

| Statistic | Value |
|---|---|
| **Mean** | **0.0113 s** |
| Min | 0.0108 s |
| Max | 0.0130 s |
| Standard deviation | 0.0006 s |
| Samples | 20 |
| Reproduction | **byte-identical in all 20 samples** |

<details>
<summary>All 20 timings (seconds)</summary>

```
0.0109 · 0.0110 · 0.0109 · 0.0113 · 0.0122 · 0.0110 · 0.0111 · 0.0113 · 0.0114 · 0.0111 · 0.0127 · 0.0108 · 0.0114 · 0.0110 · 0.0114 · 0.0109 · 0.0130 · 0.0112 · 0.0113 · 0.0110
```
</details>

> ### **RTO (local baseline): mean 0.0113 s ± 0.0006 s** over 500 observations, one instrument.

The spread is narrow (σ ≈ 0.0006 s, ~5% of the mean), which is expected for a
single-threaded, in-process rebuild with no network and no contention — and is itself a
reason not to read much into the absolute figure: there is nothing here that production
will actually be slow at.

## What this number is not

It is the **first data point**, not a production RTO. Quoting it without this section
would turn a measurement into a false claim.

- **Storage is local disk.** Production raw capture is S3-compatible object storage
  ([ADR-0009](../architecture/18-architecture-decision-records.md#adr-0009--object-storage-for-immutable-raw-capture-and-deep-history)/[ED-004](01-engineering-decisions.md#ed-004--object-storage-realization)), which adds a network round-trip per object. A rebuild reading
  thousands of objects is dominated by latency, not by the compute measured here.
- **The domain store is SQLite.** Production is PostgreSQL
  ([ADR-0008](../architecture/18-architecture-decision-records.md#adr-0008--postgresql-as-the-primary-system-of-record)/[ED-003](01-engineering-decisions.md#ed-003--postgresql-deployment-realization)); the write path and its concurrency behaviour differ entirely.
- **Scope is one instrument, one metric, one raw object.** Real recovery replays the whole
  universe across every materialized artifact.
- **No network, no contention, no cold page cache, no other tenants.**
- **One machine.** The figures above are specific to the hardware in the table.

**Therefore: re-measure after deploy. Do not extrapolate.** The value of this exercise is
that the *procedure* exists, is repeatable, and passes — the mechanism is proven, and the
figure becomes meaningful when re-run against real infrastructure.

## Change log

| Date | Change |
|------|--------|
| 2026-07-22 | Procedure authored and first measurement recorded (M5). Byte-identical reproduction confirmed in all 20 samples; RTO mean 0.0113 s ± 0.0006 s on the local baseline, with full environment and dataset recorded for reproducibility. |
