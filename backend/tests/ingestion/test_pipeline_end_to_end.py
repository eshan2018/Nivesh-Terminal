"""End-to-end integration test: Provider → Raw Store → Gate → Normalization → Repository.

This is the first test that exercises every layer built so far in one pass, on a
recorded fixture (hermetic, no network). It is the executable proof that the
skeleton's bones connect, and the harness the recompute-from-raw work will reuse.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from backend.domain.market_data.sqlite_repository import SqliteMarketDataRepository
from backend.domain.model.instruments import REFERENCE_VERSION, reference_for
from backend.domain.model.quantities import IndexLevel, Money
from backend.ingestion.filesystem_object_store import FilesystemObjectStore
from backend.ingestion.normalization import normalize_price_history, to_quarantine_records
from backend.ingestion.raw_capture import capture_price_history
from backend.ingestion.validation import validate_price_history
from backend.platform.identifiers import InstrumentId
from backend.providers.ports.price_history import PriceHistoryRequest
from backend.providers.yfinance.adapter import EXPECTED_COLUMNS, RawFetch, YFinanceAdapter

KNOWLEDGE_TIME = datetime(2025, 7, 15, 9, 30, tzinfo=UTC)


def _fetcher(rows: tuple[dict[str, object], ...]):
    def fetch(symbol: str, lookback_days: int, interval: str) -> RawFetch:
        return RawFetch(columns=EXPECTED_COLUMNS, rows=rows)

    return fetch


def _row(day: int, close: float, volume: float = 1000.0) -> dict[str, object]:
    """One raw vendor row. Keys use the *vendor's* column names, as the adapter sees them."""
    return {
        "timestamp": f"2025-07-{day:02d}T00:00:00",
        "Open": 100.0,
        "High": max(100.0, close) * 1.05,
        "Low": min(100.0, close) * 0.95,
        "Close": close,
        "Volume": volume,
    }


def _run(instrument: str, rows: tuple[dict[str, object], ...], tmp_path: Path):
    """Drive one instrument through every layer and return the persisted state."""
    instrument_id = InstrumentId(instrument)
    reference = reference_for(instrument_id)

    # L1 — provider adapter behind the canonical port
    adapter = YFinanceAdapter(fetcher=_fetcher(rows))
    response = adapter.fetch(PriceHistoryRequest(instrument_id, lookback_days=365))

    # L2 — immutable raw capture
    store = FilesystemObjectStore(tmp_path / "raw")
    raw_ref = capture_price_history(response, store)

    # L3 — the fail-closed gate
    outcome = validate_price_history(response, reference)

    # L4 — normalization to canonical facts
    observations = normalize_price_history(
        response,
        outcome,
        reference,
        knowledge_time=KNOWLEDGE_TIME,
        raw_object_key=raw_ref.key,
        reference_version=REFERENCE_VERSION,
    )
    quarantined = to_quarantine_records(
        response,
        outcome,
        quarantined_at=KNOWLEDGE_TIME,
        raw_object_key=raw_ref.key,
        reference_version=REFERENCE_VERSION,
    )

    # L5 — the domain store
    repo = SqliteMarketDataRepository(tmp_path / "market_data.sqlite3")
    repo.save_observations(observations)
    repo.save_quarantined(quarantined)
    return repo, store, raw_ref, instrument_id


def test_equity_flows_from_provider_to_repository(tmp_path: Path) -> None:
    repo, store, raw_ref, instrument_id = _run(
        "reliance", (_row(1, 1400.0), _row(2, 1425.5)), tmp_path
    )

    stored = repo.get_observations(instrument_id, interval="1d")
    assert len(stored) == 2
    assert all(isinstance(o.close, Money) for o in stored)
    assert stored[1].close.amount == Decimal("1425.5")  # type: ignore[union-attr]
    assert stored[1].close.currency.value == "INR"  # type: ignore[union-attr]

    # Lineage: every stored fact points back at the immutable raw object.
    assert {o.provenance.raw_object_key for o in stored} == {raw_ref.key}
    assert store.exists(raw_ref.key)
    document = json.loads(store.get(raw_ref.key))
    assert len(document["payload"]) == 2
    repo.close()


def test_index_flows_through_without_acquiring_a_currency(tmp_path: Path) -> None:
    repo, _store, _ref, instrument_id = _run("nifty-50", (_row(1, 24500.75),), tmp_path)
    (stored,) = repo.get_observations(instrument_id, interval="1d")
    assert isinstance(stored.close, IndexLevel)
    assert not hasattr(stored.close, "currency")
    repo.close()


def test_bad_bars_are_quarantined_and_never_persisted_as_facts(tmp_path: Path) -> None:
    repo, _store, _ref, instrument_id = _run(
        "apple", (_row(1, 100.0), _row(2, -5.0), _row(3, 102.0)), tmp_path
    )

    stored = repo.get_observations(instrument_id, interval="1d")
    assert len(stored) == 2  # the bad bar is absent, not zero-filled
    quarantined = repo.get_quarantined(instrument_id)
    assert len(quarantined) == 1  # ...and it was retained for triage, not lost
    assert any("must be > 0" in reason for reason in quarantined[0].reasons)
    repo.close()


def test_rerunning_the_whole_pipeline_is_idempotent(tmp_path: Path) -> None:
    rows = (_row(1, 100.0), _row(2, 101.0))
    repo, store, _ref, instrument_id = _run("apple", rows, tmp_path)
    repo.close()

    repo2, store2, _ref2, _ = _run("apple", rows, tmp_path)
    assert len(repo2.get_observations(instrument_id, interval="1d")) == 2
    assert len(list(store2.list_keys())) == 1  # one immutable raw object, not two
    repo2.close()


@pytest.mark.parametrize("instrument", ["reliance", "tcs", "infosys", "apple"])
def test_all_equity_instruments_flow_end_to_end(instrument: str, tmp_path: Path) -> None:
    repo, _store, _ref, instrument_id = _run(instrument, (_row(1, 250.0),), tmp_path)
    (stored,) = repo.get_observations(instrument_id, interval="1d")
    assert isinstance(stored.close, Money)
    assert stored.knowledge_time == KNOWLEDGE_TIME  # C1 populated end-to-end
    repo.close()
