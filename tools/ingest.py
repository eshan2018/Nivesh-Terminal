"""Run live ingestion across the seeded universe (M6b-2).

    python -m tools.ingest                       # every seeded instrument, 365d daily
    python -m tools.ingest --instrument reliance
    python -m tools.ingest --lookback-days 30 --manifest run.json

**This is the operator's wrapper, not the product.** The batch logic lives in
`backend/orchestration/batch.py` and the wiring in `backend/main.py`; both ship with the
package, because doc 16 requires the DAG to run in production and `tools/` is declared
repo tooling that does not ship. What lives here is argument parsing, the printed
summary and the exit code — the operator interface. An orchestrator would call
`backend.main.create_ingest_runner()` directly and never touch this file.

**The exit code is the point.** A manifest nobody reads cannot be an alarm, so anything
that is not a clean ingest — a failure, or a window that should have contained trading
sessions and did not — leaves here as a non-zero exit and a printed line. The written
manifest is the record; this is the noise.

Requires the optional `live` extra:  pip install -e ".[dev,live]"
"""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--instrument", action="append", default=None,
        help="internal instrument id; repeatable. Defaults to the whole seeded universe.",
    )
    parser.add_argument("--lookback-days", type=int, default=365)
    parser.add_argument("--interval", default="1d")
    parser.add_argument(
        "--manifest", type=Path, default=None,
        help="where to write the run manifest (default: alongside the raw store).",
    )
    args = parser.parse_args(argv)

    from backend.domain.model.instruments import known_instruments
    from backend.main import create_ingest_runner
    from backend.orchestration.batch import IngestOutcome
    from backend.platform.identifiers import InstrumentId

    instrument_ids = (
        [InstrumentId(value) for value in args.instrument]
        if args.instrument
        else [reference.instrument_id for reference in known_instruments()]
    )

    started = datetime.now(UTC)
    manifest = create_ingest_runner()(
        instrument_ids, started, args.lookback_days, args.interval
    )

    for result in manifest.results:
        detail = f"  {result.error}: {result.detail}" if result.error else ""
        print(
            f"{result.outcome:<17} {result.instrument_id:<22} "
            f"{result.bars_fetched:>4} bars  {result.observations_written:>4} written"
            f"{detail}"
        )

    counts = manifest.counts()
    print("\n" + "  ".join(f"{name}={count}" for name, count in counts.items()))

    destination = args.manifest or Path(f"ingest-manifest-{started:%Y%m%dT%H%M%SZ}.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(manifest.to_json() + "\n")
    print(f"wrote {destination}")

    # EMPTY_EXPECTED is reported but does not fail the run: over a short window it is a
    # plausible outcome, and the classification is a window-width heuristic rather than
    # a calendar lookup (see batch.py). Everything else is loud.
    blocking = [
        result
        for result in manifest.needs_attention()
        if result.outcome is not IngestOutcome.EMPTY_EXPECTED
    ]
    if blocking:
        print(
            f"\n{len(blocking)} instrument(s) need attention: "
            + ", ".join(result.instrument_id for result in blocking),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - developer entry point
    sys.exit(main())
