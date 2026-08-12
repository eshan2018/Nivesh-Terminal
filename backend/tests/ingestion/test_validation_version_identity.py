"""The validation rule set has an identity, and that identity travels (ED-020).

M6b-2 proved the gap by accident: the NaN fix changed what the gate accepts, so the same
raw payload replayed to an *accepted* observation before it and a *quarantined* one
after — while every recorded version stayed identical. Two runs over the same raw object
produced different canonical data and nothing in the record said why.

These tests pin the chain that closes it, at each link rather than end-to-end only:

    gate stamps its own outcome
      → normalization copies it onto the fact's provenance
      → the repository round-trips it, for accepted AND quarantined records
      → the DAG's config_version includes it, so a rule change is a different task
      → the run record carries it and survives serialization

The distinction this does *not* claim: recording identity is not reproducing historical
behaviour. A replay applies today's rules and says so. Honouring a superseded rule set
would need a versioned rule registry and would change what ADR-0017's bit-reproducible
tier means — deliberately not decided here.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from backend.domain.market_data.sqlite_repository import SqliteMarketDataRepository
from backend.domain.model.instruments import REFERENCE_VERSION, reference_for
from backend.ingestion.normalization import normalize_price_history, to_quarantine_records
from backend.ingestion.validation import VALIDATION_VERSION, validate_price_history
from backend.orchestration.pipeline import PipelineRun, task_keys
from backend.platform.identifiers import InstrumentId
from backend.providers.ports.price_history import (
    FetchMetadata,
    RawBar,
    RawPriceResponse,
)

RELIANCE = InstrumentId("reliance")
REFERENCE = reference_for(RELIANCE)
KNOWLEDGE_TIME = datetime(2026, 7, 30, 6, tzinfo=UTC)
RAW_KEY = "raw/v1/yfinance/price-history/2026-07/reliance/abc.json"


def _bar(day: int, close: float = 100.0) -> RawBar:
    return RawBar(
        timestamp=f"2026-07-{day:02d}T00:00:00",
        open=100.0, high=110.0, low=90.0, close=close, volume=1000.0,
    )


def _response(*bars: RawBar) -> RawPriceResponse:
    return RawPriceResponse(
        instrument_id=RELIANCE,
        bars=bars,
        fetch=FetchMetadata(
            provider="yfinance",
            vendor_symbol="RELIANCE.NS",
            interval="1d",
            fetched_at=KNOWLEDGE_TIME,
            raw_contract_version="yfinance-ohlcv/v1",
        ),
    )


# ── The gate declares and stamps its own identity ─────────────────────────────

def test_the_validation_version_is_pinned() -> None:
    """Pinned so that changing the rules without bumping the version fails here first."""
    assert VALIDATION_VERSION == "price-validation/v1"


def test_the_gate_stamps_its_own_version_on_its_outcome() -> None:
    """The rule set that ran reports itself; no caller asserts it on its behalf.

    This is what makes the claim trustworthy: a run cannot record a rule set it did not
    execute, because the value is produced by the execution.
    """
    outcome = validate_price_history(_response(_bar(1)), REFERENCE)
    assert outcome.validation_version == VALIDATION_VERSION


# ── It reaches the fact, for both dispositions ────────────────────────────────

def test_an_accepted_observation_carries_the_gate_version() -> None:
    outcome = validate_price_history(_response(_bar(1), _bar(2)), REFERENCE)
    observations = normalize_price_history(
        _response(_bar(1), _bar(2)), outcome, REFERENCE,
        knowledge_time=KNOWLEDGE_TIME, raw_object_key=RAW_KEY,
        reference_version=REFERENCE_VERSION,
    )

    assert observations
    assert all(o.provenance.validation_version == VALIDATION_VERSION for o in observations)


def test_a_quarantined_record_carries_the_gate_version_too() -> None:
    """Arguably the more important of the two: the rules are *why* it was rejected."""
    response = _response(_bar(1, close=float("nan")))
    outcome = validate_price_history(response, REFERENCE)
    records = to_quarantine_records(
        response, outcome, quarantined_at=KNOWLEDGE_TIME,
        raw_object_key=RAW_KEY, reference_version=REFERENCE_VERSION,
    )

    assert len(records) == 1
    assert records[0].provenance.validation_version == VALIDATION_VERSION


def test_normalization_takes_the_version_from_the_outcome_not_from_ambient_state() -> None:
    """A fact must report the rules that actually vetted it.

    Handing normalization an outcome stamped by a different rule set must produce
    observations claiming *that* set — otherwise the field records what is currently
    configured rather than what actually ran, which is a different and useless claim.
    """
    response = _response(_bar(1))
    outcome = replace(validate_price_history(response, REFERENCE),
                      validation_version="price-validation/v0-historic")

    observations = normalize_price_history(
        response, outcome, REFERENCE, knowledge_time=KNOWLEDGE_TIME,
        raw_object_key=RAW_KEY, reference_version=REFERENCE_VERSION,
    )

    assert observations[0].provenance.validation_version == "price-validation/v0-historic"


# ── It survives storage ───────────────────────────────────────────────────────

def test_the_version_round_trips_through_the_repository() -> None:
    response = _response(_bar(1), _bar(2, close=float("nan")))
    outcome = validate_price_history(response, REFERENCE)
    observations = normalize_price_history(
        response, outcome, REFERENCE, knowledge_time=KNOWLEDGE_TIME,
        raw_object_key=RAW_KEY, reference_version=REFERENCE_VERSION,
    )
    quarantined = to_quarantine_records(
        response, outcome, quarantined_at=KNOWLEDGE_TIME,
        raw_object_key=RAW_KEY, reference_version=REFERENCE_VERSION,
    )

    with SqliteMarketDataRepository() as repository:
        repository.save_observations(observations)
        repository.save_quarantined(quarantined)

        stored = repository.get_observations(RELIANCE, interval="1d")
        assert stored
        assert all(o.provenance.validation_version == VALIDATION_VERSION for o in stored)

        rejected = repository.get_quarantined(RELIANCE)
        assert rejected
        assert all(r.provenance.validation_version == VALIDATION_VERSION for r in rejected)


# ── It participates in configuration identity ─────────────────────────────────

def test_a_rule_change_produces_different_task_keys() -> None:
    """The point of putting it in `config_version`.

    Doc 16 keys a task by (type, scope, window, config version) so that re-running a key
    converges rather than duplicating. If the rule set is absent from that key, a replay
    under new rules reuses the old key — it looks like the same unit of work while
    producing different canonical data. It is not the same unit of work.
    """
    args = dict(interval="1d", lookback_days=365)
    base = f"{REFERENCE_VERSION}+ohlcv/v1"
    before = task_keys(RELIANCE, config_version=f"{base}+price-validation/v1", **args)
    after = task_keys(RELIANCE, config_version=f"{base}+price-validation/v2", **args)

    assert {str(k) for k in before}.isdisjoint({str(k) for k in after})


def test_the_run_record_carries_the_version_and_survives_serialization() -> None:
    run = PipelineRun(
        run_id="ingest-dag/v1:reliance:2026-07-30T06:00:00+00:00",
        pipeline_version="ingest-dag/v1",
        instrument_id="reliance",
        requested_at=KNOWLEDGE_TIME,
        reference_version=REFERENCE_VERSION,
        raw_contract_version="yfinance-ohlcv/v1",
        validation_version=VALIDATION_VERSION,
        provider="yfinance",
        raw_object_keys=(RAW_KEY,),
        bars_fetched=2,
        observations_written=2,
        quarantined_written=0,
        knowledge_time=KNOWLEDGE_TIME,
    )

    assert PipelineRun.from_json(run.to_json()) == run
    assert f'"validation_version": "{VALIDATION_VERSION}"' in run.to_json()
