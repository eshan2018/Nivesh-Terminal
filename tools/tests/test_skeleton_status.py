"""Tests for the Walking Skeleton status board.

The board's value is that it cannot drift from the code, so these tests pin the
probe behaviour and prove the worked example really runs the pipeline.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from tools import skeleton_status as status

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_built_layers_are_detected_by_probing_the_code() -> None:
    built = {layer.ident for layer in status.LAYERS if status.layer_is_built(layer, REPO_ROOT)}
    assert {"L1", "L2", "L3", "L4", "L5", "L6", "L7", "L9", "L10"} <= built


def test_unbuilt_layers_are_reported_pending() -> None:
    built = {layer.ident for layer in status.LAYERS if status.layer_is_built(layer, REPO_ROOT)}
    assert not ({"L8"} & built)


def test_completed_milestones_match_built_layers() -> None:
    complete = {m.ident for m in status.MILESTONES if status.milestone_is_complete(m, REPO_ROOT)}
    assert complete == {m.ident for m in status.MILESTONES}, (
        "every milestone is complete: the Walking Skeleton's Phase 0.5 scope is done"
    )


def test_status_board_renders_without_ansi_when_not_a_tty() -> None:
    out = io.StringIO()
    status.status_board(out, REPO_ROOT)
    text = out.getvalue()
    assert "\033[" not in text
    assert "WALKING SKELETON STATUS" in text
    assert "layers built" in text


@pytest.mark.parametrize("instrument", ["reliance", "apple", "nifty-50"])
def test_trace_runs_the_real_pipeline(instrument: str) -> None:
    out = io.StringIO()
    status.trace(instrument, out)
    text = out.getvalue()

    # Every stage reported, in order.
    for marker in ("Provider adapter", "Raw store", "Validation gate",
                   "Normalization", "Domain store", "Feature engineering",
                   "Analytics engine", "LINEAGE"):
        assert marker in text, f"missing stage: {marker}"

    # The gate really rejected the deliberately invalid bar, and it was retained.
    assert "quarantined       1" in text
    assert "close must be > 0" in text
    assert "quarantine kept   1" in text

    # Persistence really happened and re-running really was idempotent.
    assert "rows written      2" in text
    assert "re-running writes 0" in text


def test_trace_exercises_the_compute_slice_and_refuses_to_fabricate() -> None:
    """The sample spans days, not a year — so the trace must show the metric
    declining with a reason rather than reporting zero."""
    out = io.StringIO()
    status.trace("reliance", out)
    text = out.getvalue()

    assert "close-price-series/v1" in text
    assert "one-year-total-return/v1" in text
    assert "one-way; no inverse exists" in text
    assert "UNAVAILABLE" in text
    assert "insufficient-history-for-a-one-year-window" in text


def test_trace_shows_index_as_unitless_points() -> None:
    out = io.StringIO()
    status.trace("nifty-50", out)
    assert "points (unitless" in out.getvalue()


def test_trace_shows_equity_as_exact_decimal_money() -> None:
    out = io.StringIO()
    status.trace("reliance", out)
    assert "1436.25 INR   [Money]" in out.getvalue()


def test_mermaid_marks_built_and_pending_layers() -> None:
    diagram = status.mermaid(REPO_ROOT)
    assert diagram.startswith("```mermaid")
    assert "L1 · Provider adapters\"]:::built" in diagram
    assert "L6 · Feature engineering\"]:::built" in diagram
    assert "L9 · REST API\"]:::built" in diagram
    assert "L8 · AI layer\"]:::pending" in diagram


def test_the_frontend_layer_is_probed_by_its_artifact_not_a_flag() -> None:
    """L10 is not importable Python, so it is probed by the strangler seam's presence.

    The board's value is that it cannot drift from the tree; a hand-set boolean for the
    one non-Python layer would reintroduce exactly the staleness it exists to prevent.
    """
    l10 = next(layer for layer in status.LAYERS if layer.ident == "L10")
    assert l10.symbol is None and l10.artifact is not None
    assert (REPO_ROOT / l10.artifact).exists()
    assert not status.layer_is_built(l10, REPO_ROOT / "does-not-exist")


def test_cli_entrypoint_succeeds() -> None:
    assert status.main(["--no-trace"]) == 0
    assert status.main(["--mermaid"]) == 0
