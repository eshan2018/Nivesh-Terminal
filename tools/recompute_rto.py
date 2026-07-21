"""The recompute-from-raw procedure and its RTO measurement (doc 00 §B6).

    python -m tools.recompute_rto                # run the procedure, print the number
    python -m tools.recompute_rto --samples 20   # repeat and report the distribution
    python -m tools.recompute_rto --json         # machine-readable

Doc 00 §B6 asks for "a documented, **repeatable** procedure", not a number someone once
observed. This is that procedure as a program: it ingests through the real DAG, computes
the real metric, throws the canonical store away, rebuilds everything from the immutable
raw records, asserts the rebuilt value is byte-identical, and reports the wall-clock time.

Hermetic and non-destructive: everything happens in a temporary directory that is
deleted afterwards. It touches no real data and needs no services.

**What the number is and is not.** It measures *this* environment — local filesystem raw
store, SQLite domain store, one process, one instrument. It is the first data point for
doc 12's RPO/RTO story, not a production RTO. Object storage adds network latency per
object and PostgreSQL changes the write path entirely, so the figure must be re-measured
after deploy rather than extrapolated. That caveat travels with the number wherever it
is quoted (PROJECT_CONTEXT §5).
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import statistics
import sys
import tempfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

# The measurement is over the recorded fixture, so the payload is fixed and the number
# reflects pipeline cost rather than vendor variability.
FETCHED_AT = datetime(2026, 7, 20, 3, 30, tzinfo=UTC)
AS_OF = datetime(2026, 7, 22, 6, 0, tzinfo=UTC)
COMPUTED_AT = datetime(2026, 7, 22, 6, 0, 30, tzinfo=UTC)
BAR_COUNT = 500


def _bars() -> tuple[dict[str, object], ...]:
    rows = []
    base = datetime(2024, 1, 1, tzinfo=UTC).timestamp()
    for day in range(BAR_COUNT):
        close = 1400.0 + (day * 3) % 250
        stamp = datetime.fromtimestamp(base + day * 86400, UTC)
        rows.append({
            "timestamp": stamp.strftime("%Y-%m-%dT00:00:00"),
            "Open": close, "High": close + 5, "Low": close - 5,
            "Close": close, "Volume": 1_000_000.0,
        })
    return tuple(rows)


def environment() -> dict[str, object]:
    """The facts a reader needs to judge — and reproduce — the number.

    A benchmark without its environment is a rumour: 0.011 s means nothing unless the
    machine, interpreter and dataset are stated alongside it.
    """
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "os": f"{platform.system()} {platform.release()}",
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
        "cpu_count": os.cpu_count(),
        "raw_store": "FilesystemObjectStore (local disk)",
        "domain_store": "SQLite (stdlib, single connection)",
        "concurrency": "single process, single thread",
    }


def measure(workspace: Path) -> dict[str, object]:
    """Run the full procedure once and return its result."""
    from backend.domain.market_data.sqlite_repository import SqliteMarketDataRepository
    from backend.domain.model.instruments import reference_for
    from backend.ingestion.filesystem_object_store import FilesystemObjectStore
    from backend.orchestration.pipeline import run_ingest
    from backend.orchestration.recompute import compute_metric, recompute_from_raw
    from backend.platform.identifiers import InstrumentId
    from backend.providers.ports.price_history import PriceHistoryRequest
    from backend.providers.yfinance.adapter import (
        EXPECTED_COLUMNS,
        RawFetch,
        YFinanceAdapter,
    )

    instrument = InstrumentId("reliance")

    class FixedAdapter(YFinanceAdapter):
        """Real adapter over a recorded payload with a pinned fetch time."""

        def __init__(self) -> None:
            super().__init__(fetcher=lambda *_: RawFetch(EXPECTED_COLUMNS, _bars()))

        def fetch(self, request: PriceHistoryRequest):
            response = super().fetch(request)
            return replace(response, fetch=replace(response.fetch, fetched_at=FETCHED_AT))

    store = FilesystemObjectStore(workspace / "raw")

    # 1 · Ingest through the real DAG and compute the served value.
    with SqliteMarketDataRepository(workspace / "original.sqlite3") as repository:
        run = run_ingest(
            instrument, reference_for(instrument), provider=FixedAdapter(),
            store=store, repository=repository, requested_at=AS_OF,
        )
        original = compute_metric(
            repository, instrument, as_of=AS_OF, computed_at=COMPUTED_AT
        )

    # 2 · Drop canonical + derived data by rebuilding into a store that never existed,
    #     then replay raw → validate → normalize → persist → feature → engine.
    def fresh() -> SqliteMarketDataRepository:
        return SqliteMarketDataRepository(workspace / "rebuilt.sqlite3")

    report = recompute_from_raw(
        [run], store=store, rebuild_repository=fresh, instrument_id=instrument,
        as_of=AS_OF, computed_at=COMPUTED_AT, original=original,
    )

    raw_bytes = sum(len(store.get(key)) for key in run.raw_object_keys)
    value = None if report.rebuilt is None or report.rebuilt.value is None else (
        report.rebuilt.value.value
    )
    return {
        "raw_bytes": raw_bytes,
        "instrument": report.instrument_id,
        "bars_ingested": BAR_COUNT,
        "raw_objects_replayed": report.raw_objects_replayed,
        "observations_rebuilt": report.observations_rebuilt,
        "reproduced_byte_identically": report.reproduced,
        "recompute_seconds": round(report.elapsed_seconds, 4),
        "metric_value": value,
        "formula_version": None if report.rebuilt is None else report.rebuilt.formula_version,
        "run_manifest": json.loads(run.to_json()),
        "environment": "local filesystem raw store · SQLite domain store · single process",
    }


def benchmark(samples: int) -> dict[str, object]:
    """Run the procedure `samples` times and summarize the distribution.

    Each sample gets its own temporary workspace, so no run benefits from another's
    warm caches or populated stores — every one is a cold rebuild from raw.
    """
    timings: list[float] = []
    last: dict[str, object] = {}
    reproduced_every_time = True

    for _ in range(samples):
        workspace = Path(tempfile.mkdtemp(prefix="recompute-rto-"))
        try:
            last = measure(workspace)
        finally:
            shutil.rmtree(workspace, ignore_errors=True)
        timings.append(float(last["recompute_seconds"]))
        reproduced_every_time &= bool(last["reproduced_byte_identically"])

    return {
        "samples": samples,
        "reproduced_byte_identically": reproduced_every_time,
        "timings_seconds": [round(t, 4) for t in timings],
        "mean_seconds": round(statistics.fmean(timings), 4),
        "min_seconds": round(min(timings), 4),
        "max_seconds": round(max(timings), 4),
        # Population stdev needs two points; one sample has no spread to report.
        "stdev_seconds": round(statistics.stdev(timings), 4) if len(timings) > 1 else None,
        "dataset": {
            "instrument": last["instrument"],
            "bars_ingested": last["bars_ingested"],
            "observations_rebuilt": last["observations_rebuilt"],
            "raw_objects": last["raw_objects_replayed"],
            "raw_bytes": last["raw_bytes"],
        },
        "metric_value": last["metric_value"],
        "formula_version": last["formula_version"],
        "environment": environment(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    parser.add_argument(
        "--samples", type=int, default=10,
        help="how many independent cold rebuilds to time (default: 10)",
    )
    args = parser.parse_args(argv)

    result = benchmark(max(1, args.samples))
    ok = bool(result["reproduced_byte_identically"])

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if ok else 1

    dataset = result["dataset"]
    env = result["environment"]
    print()
    print("RECOMPUTE-FROM-RAW · Phase 0.5 RTO benchmark")
    print("─" * 78)
    print("  DATASET")
    print(f"    instrument           {dataset['instrument']}")
    print(f"    bars ingested        {dataset['bars_ingested']}")
    print(f"    observations rebuilt {dataset['observations_rebuilt']}")
    print(f"    raw objects / bytes  {dataset['raw_objects']} / {dataset['raw_bytes']:,}")
    print(f"    metric value         {result['metric_value']}")
    print(f"    formula              {result['formula_version']}")
    print()
    print("  ENVIRONMENT")
    print(f"    python               {env['python']} ({env['implementation']})")
    print(f"    os / machine         {env['os']} · {env['machine']}")
    print(f"    processor / cpus     {env['processor']} · {env['cpu_count']}")
    print(f"    raw store            {env['raw_store']}")
    print(f"    domain store         {env['domain_store']}")
    print(f"    concurrency          {env['concurrency']}")
    print()
    print("  RESULT")
    print(f"    reproduction         {'BYTE-IDENTICAL (all samples)' if ok else 'MISMATCH'}")
    print(f"    samples              {result['samples']}")
    print(f"    mean                 {result['mean_seconds']:.4f} s")
    print(f"    min / max            {result['min_seconds']:.4f} s / {result['max_seconds']:.4f} s")
    stdev = result["stdev_seconds"]
    spread = f"{stdev:.4f} s" if stdev is not None else "n/a (single sample)"
    print(f"    stdev                {spread}")
    print()
    print("  Caveat: a local baseline. Object storage adds per-object network latency")
    print("  and PostgreSQL changes the write path; re-measure after deploy rather")
    print("  than extrapolating (doc 12 RPO/RTO).")
    print()
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
