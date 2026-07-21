"""The recompute-from-raw procedure and its RTO measurement (doc 00 §B6).

    python -m tools.recompute_rto            # run the procedure, print the number
    python -m tools.recompute_rto --json     # machine-readable

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
import shutil
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

    value = None if report.rebuilt is None or report.rebuilt.value is None else (
        report.rebuilt.value.value
    )
    return {
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = parser.parse_args(argv)

    workspace = Path(tempfile.mkdtemp(prefix="recompute-rto-"))
    try:
        result = measure(workspace)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["reproduced_byte_identically"] else 1

    ok = result["reproduced_byte_identically"]
    print()
    print("RECOMPUTE-FROM-RAW · Phase 0.5 RTO measurement")
    print("─" * 78)
    print(f"  instrument            {result['instrument']}")
    print(f"  bars ingested         {result['bars_ingested']}")
    print(f"  raw objects replayed  {result['raw_objects_replayed']}")
    print(f"  observations rebuilt  {result['observations_rebuilt']}")
    print(f"  metric value          {result['metric_value']}")
    print(f"  reproduction          {'BYTE-IDENTICAL' if ok else 'MISMATCH'}")
    print()
    print(f"  RECOMPUTE TIME        {result['recompute_seconds']:.4f} s")
    print(f"  environment           {result['environment']}")
    print()
    print("  Caveat: a local baseline. Object storage adds per-object network latency")
    print("  and PostgreSQL changes the write path; re-measure after deploy rather")
    print("  than extrapolating (doc 12 RPO/RTO).")
    print()
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
