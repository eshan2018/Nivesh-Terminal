"""Capture a real provider payload as a test fixture (M6b-0).

    python -m tools.capture_provider_fixture --instrument reliance --days 400

**Why this exists.** Until M6b-0, every test of the yfinance adapter ran against a
*hand-written* fixture — which proves the adapter parses what we imagined the vendor
sends, not what it actually sends. A recorded real payload closes that gap: the
contract tests then assert against evidence rather than against our own assumptions.

**This is the one place in the repository that touches the live vendor.** It is a
developer tool, never imported by `backend/`, never run in CI (doc 11 forbids
live-vendor dependence in the unit/contract tiers — a network call in CI would forfeit
the reproducibility guarantee everything else rests on). Run it deliberately, commit
the fixture it writes, and the hermetic tests take over from there.

Requires the optional `live` extra:  pip install -e ".[dev,live]"
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "backend/tests/providers/fixtures"


def capture(instrument: str, days: int) -> dict[str, object]:
    """Fetch a real payload through the adapter's own live path.

    Deliberately calls the production `_default_fetch` rather than reimplementing the
    request: a fixture captured by a *different* code path would not be evidence about
    the code path we actually ship.
    """
    from backend.platform.identifiers import InstrumentId
    from backend.providers.yfinance import adapter as yf
    from backend.providers.yfinance.symbology import to_vendor_symbol

    instrument_id = InstrumentId(instrument)
    symbol = to_vendor_symbol(instrument_id)
    raw = yf._default_fetch(symbol, days, "1d")  # the live path, verbatim

    return {
        "_comment": (
            "REAL payload recorded from the live provider by "
            "tools/capture_provider_fixture.py. Do not hand-edit — re-capture instead. "
            "Prices are historical fact and do not change; re-capture only to widen "
            "coverage or after a vendor contract change."
        ),
        "instrument_id": instrument_id.value,
        "vendor_symbol": symbol,
        "interval": "1d",
        "lookback_days": days,
        "captured_at": datetime.now(UTC).isoformat(),
        "raw_contract_version": yf.RAW_CONTRACT_VERSION,
        "columns": list(raw.columns),
        "rows": [dict(row) for row in raw.rows],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--instrument", default="reliance", help="internal instrument id")
    parser.add_argument("--days", type=int, default=400, help="lookback in calendar days")
    parser.add_argument("--out", type=Path, default=None, help="output path")
    args = parser.parse_args(argv)

    try:
        document = capture(args.instrument, args.days)
    except Exception as exc:  # noqa: BLE001 - a tool reports, it does not raise at a user
        print(f"capture failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(
            "\nIf this is an HTTP 429, the provider is rate-limiting this network. "
            "The payload must be captured from a network the provider serves.",
            file=sys.stderr,
        )
        return 1

    if not document["rows"]:
        # An unknown or delisted symbol returns empty rather than raising (M6b-0
        # finding 4). Writing that as a fixture would record nothing useful.
        print("capture produced zero rows — refusing to write an empty fixture", file=sys.stderr)
        return 1

    destination = args.out or FIXTURE_DIR / f"{args.instrument}_1d_real.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    print(f"wrote {destination}  ({len(document['rows'])} bars)")
    return 0


if __name__ == "__main__":  # pragma: no cover - developer entry point
    sys.exit(main())
