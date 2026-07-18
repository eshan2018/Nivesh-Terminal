"""Walking Skeleton status board — a live, self-verifying view of the build.

    python -m tools.skeleton_status            # status board + a real trace
    python -m tools.skeleton_status --mermaid  # emit the flow diagram as Mermaid

Why a program rather than a document: layer status is **probed from the code**
(does the module and its key symbol actually import?) and the worked example is a
**real run** of the real pipeline — provider → raw store → gate → normalization →
repository — against a recorded fixture. If a layer regresses or a stage changes
shape, this output changes with it. It cannot quietly go stale the way a hand-drawn
diagram does.

Hermetic: no network, no services; the raw store and database are created in a
temporary directory and discarded.
"""
from __future__ import annotations

import argparse
import importlib
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

# ── Layer probes ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Layer:
    ident: str
    name: str
    package: str
    symbol: str | None  # a symbol that must exist for the layer to count as built
    owning_doc: str


LAYERS: tuple[Layer, ...] = (
    Layer("L1", "Provider adapters", "backend.providers.ports.price_history",
          "PriceHistoryPort", "06"),
    Layer("L2", "Raw store", "backend.ingestion.raw_store", "RawStore", "05/07"),
    Layer("L3", "Validation gate", "backend.ingestion.validation",
          "validate_price_history", "05"),
    Layer("L4", "Normalization", "backend.ingestion.normalization",
          "normalize_price_history", "05"),
    Layer("L5", "Domain store", "backend.domain.market_data.repository",
          "MarketDataRepository", "04/07"),
    Layer("L6", "Feature engineering", "backend.features", "returns", "08"),
    Layer("L7", "Analytics engines", "backend.analytics", "one_year_return", "08"),
    Layer("L8", "AI layer", "backend.ai", None, "09"),
    Layer("L9", "REST API", "backend.api", "app", "10"),
    Layer("L10", "Frontend", "web", None, "10"),
)


def layer_is_built(layer: Layer) -> bool:
    """Probe the codebase: the layer counts as built only if its symbol resolves."""
    if layer.symbol is None:
        return False
    try:
        module = importlib.import_module(layer.package)
    except ImportError:
        return False
    return hasattr(module, layer.symbol)


# ── Milestones ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Milestone:
    ident: str
    title: str
    layers: tuple[str, ...]


MILESTONES: tuple[Milestone, ...] = (
    Milestone("M0", "Engineering decisions recorded", ()),
    Milestone("M1", "Guardrails + layer skeleton", ()),
    Milestone("M2", "Provider slice", ("L1",)),
    Milestone("M2b", "Raw store", ("L2",)),
    Milestone("M2c", "Gate + normalization", ("L3", "L4")),
    Milestone("M2d", "Domain store", ("L5",)),
    Milestone("M3", "Compute slice (feature + engine)", ("L6", "L7")),
    Milestone("M4", "Serve slice (API + frontend)", ("L9", "L10")),
    Milestone("M5", "DAG + recompute-from-raw timing", ()),
)

# Milestones with no layer of their own are asserted by the presence of their artifacts.
_ARTIFACTS: dict[str, tuple[str, ...]] = {
    "M0": ("docs/implementation/01-engineering-decisions.md",),
    "M1": ("tools/ci/architecture_map.py", "backend/README.md"),
    "M5": ("backend/orchestration/pipeline.py",),
}


def milestone_is_complete(milestone: Milestone, repo_root: Path) -> bool:
    if milestone.layers:
        return all(
            layer_is_built(layer) for layer in LAYERS if layer.ident in milestone.layers
        )
    return all((repo_root / path).exists() for path in _ARTIFACTS.get(milestone.ident, ()))


# ── The worked example (a real pipeline run) ──────────────────────────────────

_SAMPLE_BARS = (
    {"timestamp": "2025-07-01T00:00:00", "Open": 1400.0, "High": 1425.0,
     "Low": 1395.0, "Close": 1410.5, "Volume": 5_200_000.0},
    {"timestamp": "2025-07-02T00:00:00", "Open": 1410.5, "High": 1440.0,
     "Low": 1408.0, "Close": 1436.25, "Volume": 4_800_000.0},
    # A deliberately invalid bar, to show the gate refusing it rather than repairing it.
    {"timestamp": "2025-07-03T00:00:00", "Open": 1436.25, "High": 1450.0,
     "Low": 1430.0, "Close": -1.0, "Volume": 100.0},
)


def trace(instrument: str, out) -> None:
    """Run the real pipeline for `instrument` and narrate each stage."""
    from backend.domain.market_data.sqlite_repository import SqliteMarketDataRepository
    from backend.domain.model.instruments import REFERENCE_VERSION, reference_for
    from backend.ingestion.filesystem_object_store import FilesystemObjectStore
    from backend.ingestion.normalization import (
        normalize_price_history,
        to_quarantine_records,
    )
    from backend.ingestion.raw_capture import capture_price_history
    from backend.ingestion.validation import validate_price_history
    from backend.platform.identifiers import InstrumentId
    from backend.providers.ports.price_history import PriceHistoryRequest
    from backend.providers.yfinance.adapter import (
        EXPECTED_COLUMNS,
        RawFetch,
        YFinanceAdapter,
    )

    workspace = Path(tempfile.mkdtemp(prefix="skeleton-trace-"))
    try:
        instrument_id = InstrumentId(instrument)
        reference = reference_for(instrument_id)
        knowledge_time = datetime.now(UTC)

        _rule(out, f"WORKED EXAMPLE — {reference.name} ({instrument_id.value})")

        # L1
        adapter = YFinanceAdapter(
            fetcher=lambda *_: RawFetch(columns=EXPECTED_COLUMNS, rows=_SAMPLE_BARS)
        )
        response = adapter.fetch(PriceHistoryRequest(instrument_id, lookback_days=365))
        _stage(out, "L1", "Provider adapter", [
            f"internal id       {instrument_id.value}",
            f"vendor symbol     {response.fetch.vendor_symbol}  (resolved by symbology)",
            f"raw contract      {response.fetch.raw_contract_version}",
            f"bars fetched      {len(response.bars)}",
        ])

        # L2
        store = FilesystemObjectStore(workspace / "raw")
        ref = capture_price_history(response, store)
        _stage(out, "L2", "Raw store (immutable)", [
            f"object key        {ref.key}",
            f"size / sha256     {ref.size_bytes} bytes / {ref.sha256[:16]}…",
            "immutability      re-writing this key raises ObjectAlreadyExists",
        ])

        # L3
        outcome = validate_price_history(response, reference)
        rejected = [
            f"{q.bar.timestamp} — {q.reasons[0]}" for q in outcome.quarantined
        ]
        _stage(out, "L3", "Validation gate (fail-closed)", [
            f"accepted          {len(outcome.accepted)}",
            f"quarantined       {len(outcome.quarantined)}",
            *[f"  rejected        {line}" for line in rejected],
            f"series flags      {list(outcome.series_flags) or 'none'}",
        ])

        # L4
        observations = normalize_price_history(
            response, outcome, reference,
            knowledge_time=knowledge_time,
            raw_object_key=ref.key,
            reference_version=REFERENCE_VERSION,
        )
        quarantined = to_quarantine_records(
            response, outcome,
            quarantined_at=knowledge_time,
            raw_object_key=ref.key,
            reference_version=REFERENCE_VERSION,
        )
        sample = observations[-1]
        close = sample.close
        rendered = (
            f"{close.amount} {close.currency.value}"
            if hasattr(close, "currency")
            else f"{close.points} points (unitless — FX-conversion is type-impossible)"
        )
        _stage(out, "L4", "Normalization → canonical", [
            f"observations      {len(observations)}",
            f"close (exact)     {rendered}   [{type(close).__name__}]",
            f"event_time        {sample.event_time.isoformat()}",
            f"knowledge_time    {sample.knowledge_time.isoformat()}   (C1: always populated)",
            f"authority         {sample.authority.value}",
            f"reference version {sample.provenance.reference_version}",
        ])

        # L5
        repository = SqliteMarketDataRepository(workspace / "market_data.sqlite3")
        written = repository.save_observations(observations)
        repository.save_quarantined(quarantined)
        again = repository.save_observations(observations)
        stored = repository.get_observations(instrument_id, interval="1d")
        _stage(out, "L5", "Domain store (repository)", [
            f"rows written      {written}",
            f"re-running writes {again}   (idempotent — effective-dated by knowledge_time)",
            f"read back         {len(stored)} observations",
            f"quarantine kept   {len(repository.get_quarantined(instrument_id))} "
            "(rejected data is retained, not lost)",
        ])
        repository.close()

        # Lineage
        document = json.loads(store.get(stored[0].provenance.raw_object_key))
        _rule(out, "LINEAGE — a stored fact traced back to its source")
        print(
            f"  {stored[0].close.__class__.__name__} {stored[0].event_time.date()}\n"
            f"    ← raw object   {stored[0].provenance.raw_object_key}\n"
            f"    ← provider     {stored[0].provenance.provider} "
            f"({stored[0].provenance.raw_contract_version})\n"
            f"    ← verbatim     {len(document['payload'])} bars captured at "
            f"{document['fetch']['fetched_at']}",
            file=out,
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


# ── Rendering ─────────────────────────────────────────────────────────────────

_BOLD, _RESET = "\033[1m", "\033[0m"


def _bold(text: str, out) -> str:
    """Bold only when writing to a terminal, so piped/captured output stays clean."""
    if hasattr(out, "isatty") and out.isatty():
        return f"{_BOLD}{text}{_RESET}"
    return text


def _rule(out, title: str) -> None:
    print(f"\n{_bold(title, out)}", file=out)
    print("─" * 78, file=out)


def _stage(out, ident: str, name: str, lines: list[str]) -> None:
    print(f"\n  {_bold(ident, out)}  {name}", file=out)
    for line in lines:
        print(f"      {line}", file=out)


def status_board(out, repo_root: Path) -> None:
    _rule(out, "NIVESH TERMINAL — WALKING SKELETON STATUS")
    print("  Architecture v2.0 (frozen) · docs/architecture/", file=out)

    _rule(out, "LAYERS")
    for layer in LAYERS:
        built = layer_is_built(layer)
        mark = "[built]  " if built else "[pending]"
        print(f"  {mark} {layer.ident:<4} {layer.name:<22} doc {layer.owning_doc}", file=out)

    _rule(out, "MILESTONES")
    for milestone in MILESTONES:
        done = milestone_is_complete(milestone, repo_root)
        mark = "[x]" if done else "[ ]"
        print(f"  {mark} {milestone.ident:<4} {milestone.title}", file=out)

    built = sum(1 for layer in LAYERS if layer_is_built(layer))
    complete = sum(1 for m in MILESTONES if milestone_is_complete(m, repo_root))
    print(
        f"\n  {built}/{len(LAYERS)} layers built · "
        f"{complete}/{len(MILESTONES)} milestones complete",
        file=out,
    )


def mermaid(repo_root: Path) -> str:
    """Emit the current pipeline as a Mermaid diagram (built vs pending)."""
    lines = [
        "```mermaid",
        "flowchart TD",
        "    classDef built fill:#1b5e20,stroke:#66bb6a,color:#ffffff;",
        "    classDef pending fill:#37474f,stroke:#90a4ae,color:#cfd8dc,stroke-dasharray:4 3;",
        "",
        "    V[(yfinance)]:::pending",
    ]
    previous = "V"
    for layer in LAYERS:
        node = layer.ident
        style = "built" if layer_is_built(layer) else "pending"
        lines.append(f"    {node}[\"{layer.ident} · {layer.name}\"]:::{style}")
        lines.append(f"    {previous} --> {node}")
        previous = node
    lines.append("```")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Walking Skeleton status board.")
    parser.add_argument("--mermaid", action="store_true", help="emit a Mermaid diagram")
    parser.add_argument(
        "--instrument", default="reliance", help="instrument to trace (default: reliance)"
    )
    parser.add_argument("--no-trace", action="store_true", help="status board only")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    if args.mermaid:
        print(mermaid(repo_root))
        return 0

    status_board(sys.stdout, repo_root)
    if not args.no_trace:
        trace(args.instrument, sys.stdout)
    print(file=sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
