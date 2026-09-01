"""M7 gating study: can a co-movement judgement be made on this evidence? (M7 §4)

    python -m tools.diversification_study                 # run it, print the report
    python -m tools.diversification_study --json          # machine-readable
    python -m tools.diversification_study --replicates 1000

**Why this is a committed tool rather than scratch work.** M6c's decision to drop the
compensation judgement rested on a study of 411 real portfolios that was never committed
and cannot be re-run today. The reasoning survived in the methodology catalog; the
evidence did not. A result that decides whether a milestone ships has to be reproducible
by someone who does not have the author's shell history.

**The question it answers.** Not "what is this portfolio's diversification" — that is a
number, and numbers are cheap. It answers: *is there a statement about how independently
a portfolio's holdings behaved that is both statistically defensible and decisive often
enough to be a product?* M6c established that this is the binding constraint: the
compensation judgement was statistically impeccable and 99.8% inconclusive, which makes
it a constant with lineage attached.

**Pre-registered gates.** G1–G4 below were written into the M7 planning proposal and
approved before any number here was computed. G1 and G2 are *product viability*
thresholds, not statistical truths: nothing about 40% or 85% is derivable from
probability theory. They encode a product judgement — that a verdict which fires on
fewer than two portfolios in five, or which returns the same answer nearly always, is a
constant wearing a verdict's clothes. Because they are conventions, the report shows
where each frame sits as the thresholds move, so the decision can be read off the
sensitivity rather than off a single pass/fail stamp.

**What is deliberately NOT here.** No engine, no envelope, no endpoint. This program
imports the L6 feature layer to obtain returns and does its own arithmetic on top. It is
an investigation, and investigations that quietly become implementations are how
unreviewed methodology enters a system.

## Method

*Common grid.* Every eligible instrument is aligned once, to the dates all of them share,
so that portfolios are compared over an identical window. Aligning per portfolio would
let two portfolios differ because they were measured over different days — a confound
sitting exactly where the signal is meant to be. The per-portfolio alignment cost is
measured separately (adversarial Q5) rather than being mixed into the comparison.

*Statistics.* For an equal-weight portfolio over holdings `i` with covariance `Σ`:

    σ_p       = √(w'Σw)                      portfolio volatility
    D         = (Σ wᵢσᵢ) / σ_p               diversification ratio
    ρ̄         = mean off-diagonal correlation
    N_eff     = D²                            co-movement-adjusted holdings count

`D = 1` exactly when holdings are perfectly correlated, and `N_eff = k` exactly when they
are uncorrelated — both are definitional boundaries, not chosen ones.

**`N_eff` and `ρ̄` are one quantity, not two.** For equal weights and equal volatilities
`D² = k / (1 + (k−1)ρ̄)` exactly — an identity the test suite pins. `N_eff` is a
re-expression of average pairwise correlation, so the two must never be presented as
agreeing with each other: an identity cannot corroborate anything. `N_eff` is carried
here as a research quantity under its own technical name, deliberately not given a
product-facing label.

*Inference.* Moving-block bootstrap over the return rows (block length 10 trading days,
fixed seed). Analytic inference on an *average* of pairwise correlations is awkward —
the estimates are themselves correlated — and the blocks preserve the volatility
clustering that an i.i.d. resample would destroy. Every portfolio and every reference
frame is evaluated on the *same* replicates, so differences are paired and the reference
frame's own sampling error is not double-counted.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path

TRADING_DAYS = 252

#: Moving-block length, in trading days. Long enough to carry volatility clustering
#: through a resample, short enough that ~250 observations still yield varied blocks.
BLOCK_LENGTH = 10

DEFAULT_REPLICATES = 500

#: Fixed so the gating result is reproducible. A study whose verdict moves between runs
#: cannot gate anything.
SEED = 20260830

# ── Pre-registered gates (M7 §4, approved before execution) ───────────────────

#: G1 · a frame must return a directional verdict on at least this share of portfolios.
G1_DECISIVE_RATE = 0.40

#: G2 · no single verdict value may exceed this share of outcomes.
G2_MAX_SINGLE_VERDICT = 0.85

#: The confidence level the gates are evaluated at. Sensitivity is reported around it.
GATE_CONFIDENCE = 0.95
SENSITIVITY_CONFIDENCES = (0.90, 0.95, 0.99)

#: G3 · the named sanity case. If a statistic cannot separate four banks from a
#: deliberately spread portfolio, it cannot see the thing it exists to see.
BANK_PORTFOLIO = ("axis-bank", "hdfc-bank", "icici-bank", "kotak-mahindra-bank")
SPREAD_PORTFOLIO = ("nippon-gold-bees", "hindustan-unilever", "infosys", "reliance")

PORTFOLIO_SIZES = (2, 3, 4, 5, 6, 8)

#: Portfolios sampled per size. C(18,4) alone is 3,060; a deterministic sample keeps the
#: study runnable while leaving the estimates stable.
SAMPLE_PER_SIZE = 300


# ── Portfolio statistics over a covariance matrix ─────────────────────────────

@dataclass(frozen=True, slots=True)
class PortfolioStats:
    """Scale-free descriptions of how jointly a set of holdings moved."""

    volatility: float
    diversification_ratio: float
    mean_correlation: float
    n_eff: float


def covariance(columns: list[list[float]]) -> list[list[float]]:
    """Sample covariance matrix of centred columns. Symmetric, computed once per grid."""
    width, length = len(columns), len(columns[0])
    centred = []
    for column in columns:
        mean = sum(column) / length
        centred.append([value - mean for value in column])

    matrix = [[0.0] * width for _ in range(width)]
    for i in range(width):
        left = centred[i]
        for j in range(i, width):
            total = sum(a * b for a, b in zip(left, centred[j], strict=True))
            matrix[i][j] = matrix[j][i] = total / (length - 1)
    return matrix


def stats_for(matrix: list[list[float]], holdings: tuple[int, ...]) -> PortfolioStats:
    """Equal-weight statistics for a sub-portfolio, read off the full covariance."""
    count = len(holdings)
    weight = 1.0 / count

    variance = sum(matrix[i][j] for i in holdings for j in holdings) * weight * weight
    volatility = math.sqrt(variance) * math.sqrt(TRADING_DAYS)

    sigmas = [math.sqrt(matrix[i][i]) * math.sqrt(TRADING_DAYS) for i in holdings]
    ratio = (weight * sum(sigmas)) / volatility

    correlations = [
        matrix[i][j] / math.sqrt(matrix[i][i] * matrix[j][j])
        for position, i in enumerate(holdings)
        for j in holdings[position + 1:]
    ]
    return PortfolioStats(
        volatility=volatility,
        diversification_ratio=ratio,
        mean_correlation=sum(correlations) / len(correlations),
        n_eff=ratio * ratio,
    )


def universe_mean_correlation(matrix: list[list[float]]) -> float:
    """Average pairwise correlation across every eligible instrument.

    The empirical reference for frame (b): what co-movement looks like in this market
    over this window, rather than a level someone chose.
    """
    width = len(matrix)
    return sum(
        matrix[i][j] / math.sqrt(matrix[i][i] * matrix[j][j])
        for i in range(width)
        for j in range(i + 1, width)
    ) / (width * (width - 1) / 2)


# ── Bootstrap ─────────────────────────────────────────────────────────────────

def block_resample(length: int, rng: random.Random) -> list[int]:
    """Row indices for one moving-block resample."""
    indices: list[int] = []
    last_start = length - BLOCK_LENGTH
    while len(indices) < length:
        start = rng.randint(0, last_start)
        indices.extend(range(start, start + BLOCK_LENGTH))
    return indices[:length]


def bootstrap_matrices(
    columns: list[list[float]], replicates: int, rng: random.Random
) -> list[list[list[float]]]:
    """One covariance matrix per replicate, shared by every portfolio and reference.

    Computing these once is what makes the study tractable: a portfolio's bootstrap
    distribution is then a sub-matrix sum, and any two portfolios (or a portfolio and
    its reference) are automatically paired on the same resampled days.
    """
    length = len(columns[0])
    matrices = []
    for _ in range(replicates):
        rows = block_resample(length, rng)
        matrices.append(covariance([[column[row] for row in rows] for column in columns]))
    return matrices


def interval(values: list[float], confidence: float) -> tuple[float, float]:
    """Percentile bootstrap interval."""
    ordered = sorted(values)
    tail = (1.0 - confidence) / 2.0
    low = ordered[max(0, int(math.floor(tail * len(ordered))))]
    high = ordered[min(len(ordered) - 1, int(math.ceil((1.0 - tail) * len(ordered))) - 1)]
    return low, high


# ── Reference frames ──────────────────────────────────────────────────────────

INDEPENDENT = "BEHAVED_INDEPENDENTLY"
NOT_INDEPENDENT = "DID_NOT_BEHAVE_INDEPENDENTLY"
LESS_CO_MOVEMENT = "LESS_CO_MOVEMENT_THAN_THE_MARKET"
MORE_CO_MOVEMENT = "MORE_CO_MOVEMENT_THAN_THE_MARKET"
UNDECIDED = "NOT_DISTINGUISHABLE"


def verdict_from(low: float, high: float, boundary: float, *, above: str, below: str) -> str:
    """A directional call only when the whole interval sits on one side of the boundary."""
    if low > boundary:
        return above
    if high < boundary:
        return below
    return UNDECIDED


@dataclass
class FrameOutcome:
    """Verdict counts for one reference frame at one confidence level."""

    verdicts: dict[str, int] = field(default_factory=dict)

    def record(self, verdict: str) -> None:
        self.verdicts[verdict] = self.verdicts.get(verdict, 0) + 1

    @property
    def total(self) -> int:
        return sum(self.verdicts.values())

    @property
    def decisive_rate(self) -> float:
        if not self.total:
            return 0.0
        return 1.0 - (self.verdicts.get(UNDECIDED, 0) / self.total)

    @property
    def largest_share(self) -> float:
        if not self.total:
            return 0.0
        return max(self.verdicts.values()) / self.total

    def gates(self) -> dict[str, object]:
        return {
            "decisive_rate": round(self.decisive_rate, 4),
            "largest_single_verdict_share": round(self.largest_share, 4),
            "G1_pass": self.decisive_rate >= G1_DECISIVE_RATE,
            "G2_pass": self.largest_share <= G2_MAX_SINGLE_VERDICT,
            "verdicts": {k: v for k, v in sorted(self.verdicts.items())},
        }


# ── The study ─────────────────────────────────────────────────────────────────

def eligible_instruments() -> list[str]:
    """Holdings a portfolio may actually contain, by the engines' own rules.

    Type is not sufficient: `apple` is an EQUITY and passes `supported_for_portfolio`,
    and is excluded only by the mixed-currency refusal one layer up. Filtering on type
    alone would put a USD instrument into an INR portfolio and call the resulting
    correlation a finding.
    """
    from backend.domain.model.instruments import known_instruments
    from backend.features.portfolio_returns import supported_for_portfolio

    inr = [
        reference for reference in known_instruments()
        if supported_for_portfolio(reference)
        and reference.currency is not None
        and reference.currency.value == "INR"
    ]
    return sorted(reference.instrument_id.value for reference in inr)


def load_grid(database: Path, instruments: list[str], as_of: datetime):
    """Align every eligible instrument onto one common set of dates."""
    from backend.domain.market_data.sqlite_repository import SqliteMarketDataRepository
    from backend.features.portfolio_returns import build_aligned_return_matrix
    from backend.platform.identifiers import InstrumentId

    with SqliteMarketDataRepository(database) as repository:
        matrix = build_aligned_return_matrix(
            repository, [InstrumentId(value) for value in instruments], as_of=as_of
        )
        per_instrument = {}
        for value in instruments:
            single = build_aligned_return_matrix(
                repository, [InstrumentId(value)], as_of=as_of
            )
            per_instrument[value] = single.observation_count
    return matrix, per_instrument


def sample_portfolios(count: int, size: int, limit: int, rng: random.Random):
    """Every combination when there are few, a deterministic sample when there are many."""
    everything = list(combinations(range(count), size))
    if len(everything) <= limit:
        return everything, len(everything)
    return rng.sample(everything, limit), len(everything)


def _agrees_with_shipped_engine(
    database: Path,
    instruments: list[str],
    as_of: datetime,
    observed: list[list[float]],
    index_of: dict[str, int],
) -> dict[str, object]:
    """Compare this study's volatility against `portfolio-risk-return/v1` on real cases."""
    from backend.analytics.portfolio_risk_return import Holding, portfolio_risk_return
    from backend.domain.market_data.sqlite_repository import SqliteMarketDataRepository
    from backend.features.portfolio_returns import (
        build_aligned_return_matrix,
        portfolio_instrument_references,
    )
    from backend.platform.identifiers import InstrumentId

    cases = (BANK_PORTFOLIO, SPREAD_PORTFOLIO, tuple(instruments[:6]))
    worst = 0.0
    checked = []
    with SqliteMarketDataRepository(database) as repository:
        for case in cases:
            ids = [InstrumentId(value) for value in case]
            # The engine must see the same window this study used, or the two numbers
            # would differ for a reason that has nothing to do with the arithmetic.
            grid = build_aligned_return_matrix(
                repository, [InstrumentId(v) for v in instruments], as_of=as_of
            )
            matrix = build_aligned_return_matrix(
                repository, ids, as_of=as_of, restrict_to=grid.dates
            )
            weight = 1.0 / len(case)
            result = portfolio_risk_return(
                matrix,
                [Holding(instrument_id=i, weight=weight) for i in ids],
                portfolio_instrument_references(ids),
                risk_free_rate=0.07,
                computed_at=as_of,
            )
            engine = dict(result.diagnostics).get("annualized_volatility")
            if engine is None:
                for key, value in result.diagnostics:
                    if "volatil" in key and "error" not in key:
                        engine = value
                        break
            mine = stats_for(observed, tuple(index_of[v] for v in case)).volatility
            if engine:
                relative = abs(mine - engine) / engine
                worst = max(worst, relative)
                checked.append({
                    "portfolio": list(case),
                    "study": round(mine, 8),
                    "engine": round(engine, 8),
                    "relative_difference": relative,
                })
    return {
        "cases": checked,
        "worst_relative_difference": worst,
        "agrees": bool(checked) and worst < 1e-9,
    }


def run(database: Path, replicates: int) -> dict[str, object]:
    instruments = eligible_instruments()
    as_of = datetime.now(UTC)
    grid, per_instrument = load_grid(database, instruments, as_of)

    columns = [list(column) for column in grid.columns]
    observed = covariance(columns)
    rng = random.Random(SEED)
    replicate_matrices = bootstrap_matrices(columns, replicates, rng)

    report: dict[str, object] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "seed": SEED,
        "replicates": replicates,
        "block_length": BLOCK_LENGTH,
        "instruments": instruments,
        "common_observations": grid.observation_count,
        "window": [grid.dates[0].date().isoformat(), grid.dates[-1].date().isoformat()],
        "quality_flags": list(grid.quality_flags),
        "per_instrument_observations": per_instrument,
        "universe_mean_correlation": round(universe_mean_correlation(observed), 4),
    }

    index_of = {value: position for position, value in enumerate(instruments)}
    sampler = random.Random(SEED)

    # ── Spread: is there anything to detect at all? ───────────────────────────
    spread: dict[str, object] = {}
    frames: dict[float, dict[str, FrameOutcome]] = {
        confidence: {
            "a_independence": FrameOutcome(),
            "b_universe_relative": FrameOutcome(),
        }
        for confidence in SENSITIVITY_CONFIDENCES
    }
    by_size: dict[int, dict[str, object]] = {}
    interval_widths: list[float] = []
    gold = index_of.get("nippon-gold-bees")
    with_gold: dict[float, FrameOutcome] = {
        c: FrameOutcome() for c in SENSITIVITY_CONFIDENCES
    }
    without_gold: dict[float, FrameOutcome] = {
        c: FrameOutcome() for c in SENSITIVITY_CONFIDENCES
    }

    universe_replicates = [universe_mean_correlation(m) for m in replicate_matrices]

    for size in PORTFOLIO_SIZES:
        portfolios, population = sample_portfolios(
            len(instruments), size, SAMPLE_PER_SIZE, sampler
        )
        correlations, ratios, effective, widths = [], [], [], []
        size_frames = {
            c: {"a_independence": FrameOutcome(), "b_universe_relative": FrameOutcome()}
            for c in SENSITIVITY_CONFIDENCES
        }

        for holdings in portfolios:
            point = stats_for(observed, holdings)
            correlations.append(point.mean_correlation)
            ratios.append(point.diversification_ratio)
            effective.append(point.n_eff)

            drawn = [stats_for(m, holdings) for m in replicate_matrices]
            rho_draws = [d.mean_correlation for d in drawn]
            n_eff_draws = [d.n_eff for d in drawn]
            relative = [
                d.mean_correlation - u for d, u in zip(drawn, universe_replicates, strict=True)
            ]

            for confidence in SENSITIVITY_CONFIDENCES:
                low, high = interval(rho_draws, confidence)
                frame_a = verdict_from(
                    low, high, 0.0, above=NOT_INDEPENDENT, below=INDEPENDENT
                )
                low_r, high_r = interval(relative, confidence)
                frame_b = verdict_from(
                    low_r, high_r, 0.0,
                    above=MORE_CO_MOVEMENT, below=LESS_CO_MOVEMENT,
                )
                frames[confidence]["a_independence"].record(frame_a)
                frames[confidence]["b_universe_relative"].record(frame_b)
                size_frames[confidence]["a_independence"].record(frame_a)
                size_frames[confidence]["b_universe_relative"].record(frame_b)

                bucket = with_gold if gold in holdings else without_gold
                bucket[confidence].record(frame_b)

            n_eff_low, n_eff_high = interval(n_eff_draws, GATE_CONFIDENCE)
            widths.append((n_eff_high - n_eff_low) / point.n_eff)

        interval_widths.extend(widths)
        by_size[size] = {
            "sampled": len(portfolios),
            "population": population,
            "mean_correlation": {
                "min": round(min(correlations), 4),
                "median": round(statistics.median(correlations), 4),
                "max": round(max(correlations), 4),
                "stdev": round(statistics.pstdev(correlations), 4),
            },
            "n_eff": {
                "min": round(min(effective), 3),
                "median": round(statistics.median(effective), 3),
                "max": round(max(effective), 3),
                "as_share_of_holdings": round(statistics.median(effective) / size, 3),
            },
            "diversification_ratio_median": round(statistics.median(ratios), 4),
            "median_relative_interval_width": round(statistics.median(widths), 3),
            "frames": {
                f"{c:.0%}": {name: outcome.gates() for name, outcome in group.items()}
                for c, group in size_frames.items()
            },
        }

    spread["by_size"] = by_size
    report["spread"] = spread
    report["frames"] = {
        f"{c:.0%}": {name: outcome.gates() for name, outcome in group.items()}
        for c, group in frames.items()
    }
    report["gold_sensitivity"] = {
        f"{c:.0%}": {
            "with_gold": with_gold[c].gates(),
            "without_gold": without_gold[c].gates(),
        }
        for c in SENSITIVITY_CONFIDENCES
    }
    report["descriptive_interval"] = {
        "median_relative_width_of_n_eff_ci": round(
            statistics.median(interval_widths), 3
        ),
        "share_wider_than_half_the_estimate": round(
            sum(1 for w in interval_widths if w > 0.5) / len(interval_widths), 4
        ),
    }

    # ── G3 · the named sanity case ────────────────────────────────────────────
    bank = tuple(index_of[value] for value in BANK_PORTFOLIO)
    diverse = tuple(index_of[value] for value in SPREAD_PORTFOLIO)
    differences = [
        stats_for(m, bank).mean_correlation - stats_for(m, diverse).mean_correlation
        for m in replicate_matrices
    ]
    g3_low, g3_high = interval(differences, GATE_CONFIDENCE)
    report["G3_sanity_case"] = {
        "bank_portfolio": list(BANK_PORTFOLIO),
        "spread_portfolio": list(SPREAD_PORTFOLIO),
        "bank_mean_correlation": round(stats_for(observed, bank).mean_correlation, 4),
        "spread_mean_correlation": round(stats_for(observed, diverse).mean_correlation, 4),
        "bank_n_eff": round(stats_for(observed, bank).n_eff, 3),
        "spread_n_eff": round(stats_for(observed, diverse).n_eff, 3),
        "difference_ci": [round(g3_low, 4), round(g3_high, 4)],
        "G3_pass": g3_low > 0.0,
    }

    # ── Adversarial Q5 · what per-portfolio alignment costs ───────────────────
    report["alignment"] = {
        "common_grid_observations": grid.observation_count,
        "longest_single_instrument": max(per_instrument.values()),
        "shortest_single_instrument": min(per_instrument.values()),
        "days_lost_to_full_universe_alignment":
            max(per_instrument.values()) - grid.observation_count,
        "min_overlap_threshold": 50,
        "portfolios_below_threshold_on_common_grid":
            0 if grid.observation_count >= 50 else "ALL",
    }

    # ── G4 · is the reference frame empirical, or did we build it? ────────────
    #
    # Frame (b) compares a portfolio against "the market", operationalised as the mean
    # pairwise correlation of the eligible universe. That universe is a list *we seeded*.
    # If the reference moves when the list is composed differently, then the verdict an
    # investor reads is a property of our seeding decisions rather than of their
    # portfolio — a house convention with an empirical costume on. This is the test that
    # decides G4, so it perturbs the universe deliberately and counts how many verdicts
    # change sign.
    variants = {
        "full_18": list(range(len(instruments))),
        "no_banks": [
            index_of[v] for v in instruments
            if v not in {"axis-bank", "hdfc-bank", "icici-bank",
                         "kotak-mahindra-bank", "state-bank-of-india", "nippon-bank-bees"}
        ],
        "no_etfs": [
            index_of[v] for v in instruments if not v.startswith("nippon-")
        ],
        "no_gold": [index_of[v] for v in instruments if v != "nippon-gold-bees"],
        "equities_only_ex_banks": [
            index_of[v] for v in instruments
            if not v.startswith("nippon-")
            and v not in {"axis-bank", "hdfc-bank", "icici-bank",
                          "kotak-mahindra-bank", "state-bank-of-india"}
        ],
    }

    def mean_correlation_over(matrix: list[list[float]], members: list[int]) -> float:
        pairs = [
            matrix[i][j] / math.sqrt(matrix[i][i] * matrix[j][j])
            for position, i in enumerate(members)
            for j in members[position + 1:]
        ]
        return sum(pairs) / len(pairs)

    stability_sampler = random.Random(SEED + 1)
    probe, _ = sample_portfolios(len(instruments), 4, 200, stability_sampler)
    variant_verdicts: dict[str, list[str]] = {}
    variant_reference: dict[str, float] = {}

    for name, members in variants.items():
        variant_reference[name] = round(mean_correlation_over(observed, members), 4)
        reference_draws = [mean_correlation_over(m, members) for m in replicate_matrices]
        calls = []
        for holdings in probe:
            relative = [
                stats_for(m, holdings).mean_correlation - r
                for m, r in zip(replicate_matrices, reference_draws, strict=True)
            ]
            low, high = interval(relative, GATE_CONFIDENCE)
            calls.append(
                verdict_from(low, high, 0.0,
                             above=MORE_CO_MOVEMENT, below=LESS_CO_MOVEMENT)
            )
        variant_verdicts[name] = calls

    baseline = variant_verdicts["full_18"]
    flips: dict[str, object] = {}
    for name, calls in variant_verdicts.items():
        if name == "full_18":
            continue
        reversed_count = sum(
            1 for a, b in zip(baseline, calls, strict=True)
            if a != UNDECIDED and b != UNDECIDED and a != b
        )
        changed = sum(1 for a, b in zip(baseline, calls, strict=True) if a != b)
        flips[name] = {
            "reference_mean_correlation": variant_reference[name],
            "verdicts_changed": changed,
            "verdicts_reversed": reversed_count,
            "changed_share": round(changed / len(baseline), 4),
            "reversed_share": round(reversed_count / len(baseline), 4),
        }

    references = list(variant_reference.values())
    report["G4_reference_stability"] = {
        "probe_portfolios": len(probe),
        "reference_by_universe": variant_reference,
        "reference_spread": round(max(references) - min(references), 4),
        "flips": flips,
        "worst_reversed_share": round(
            max(f["reversed_share"] for f in flips.values()), 4  # type: ignore[index]
        ),
        "worst_changed_share": round(
            max(f["changed_share"] for f in flips.values()), 4  # type: ignore[index]
        ),
    }

    # ── Adversarial Q6 · does this study agree with the shipped engine? ───────
    #
    # The study computes portfolio volatility with its own arithmetic, off a covariance
    # matrix, while `portfolio-risk-return/v1` computes it from the weighted return
    # series directly. Both are in the repository and both claim to be the same number.
    # If they disagree, the gate result is worthless regardless of how clean it looks,
    # so the study checks itself against the engine rather than asserting parity.
    report["cross_engine_check"] = _agrees_with_shipped_engine(
        database, instruments, as_of, observed, index_of
    )

    # ── Adversarial Q3 · eigenvalue route, for comparison only ────────────────
    report["note_on_eigenvalues"] = (
        "N_eff is reported from D^2 throughout. The eigenvalue route was not used: "
        "with ~250 observations the smallest eigenvalues of an 8x8 correlation matrix "
        "are systematically understated, which biases a spectrum-based N_eff upward "
        "in exactly the concentrated portfolios the judgement exists to detect."
    )
    return report


# ── Reporting ─────────────────────────────────────────────────────────────────

def render(report: dict[str, object]) -> str:
    out: list[str] = []
    add = out.append
    add("M7 gating study — co-movement judgement viability")
    add("=" * 64)
    add(f"  instruments        {len(report['instruments'])} eligible (INR, holdable)")
    add(f"  common grid        {report['common_observations']} observations "
        f"{report['window'][0]} .. {report['window'][1]}")
    add(f"  bootstrap          {report['replicates']} replicates, "
        f"block {report['block_length']}d, seed {report['seed']}")
    add(f"  universe mean rho  {report['universe_mean_correlation']}")
    add("")

    add("SPREAD — is there anything to detect?")
    add(f"  {'size':>4}  {'sampled':>7}  {'rho median':>10}  {'rho range':>16}  "
        f"{'N_eff':>7}  {'N_eff/k':>7}")
    for size, block in report["spread"]["by_size"].items():  # type: ignore[index]
        rho = block["mean_correlation"]
        bets = block["n_eff"]
        add(f"  {size:>4}  {block['sampled']:>7}  {rho['median']:>10.4f}  "
            f"{rho['min']:>7.3f}..{rho['max']:<7.3f}  "
            f"{bets['median']:>7.3f}  {bets['as_share_of_holdings']:>7.3f}")
    add("")

    add("GATES G1/G2 by reference frame (product viability, not statistical truth)")
    for level, group in report["frames"].items():  # type: ignore[union-attr]
        add(f"  at {level} confidence")
        for name, gates in group.items():
            flag = "PASS" if gates["G1_pass"] and gates["G2_pass"] else "FAIL"
            add(f"    {name:<22} decisive {gates['decisive_rate']:>6.1%}  "
                f"largest {gates['largest_single_verdict_share']:>6.1%}  "
                f"G1 {'ok' if gates['G1_pass'] else 'NO':<3} "
                f"G2 {'ok' if gates['G2_pass'] else 'NO':<3} {flag}")
            for verdict, count in gates["verdicts"].items():
                add(f"        {verdict:<34} {count}")
    add("")

    g3 = report["G3_sanity_case"]
    add("G3 — named sanity case (four banks vs a spread portfolio)")
    add(f"  banks   rho {g3['bank_mean_correlation']:.4f}   "
        f"N_eff {g3['bank_n_eff']:.3f} of 4")
    add(f"  spread  rho {g3['spread_mean_correlation']:.4f}   "
        f"N_eff {g3['spread_n_eff']:.3f} of 4")
    add(f"  difference 95% CI {g3['difference_ci']}   "
        f"G3 {'PASS' if g3['G3_pass'] else 'FAIL'}")
    add("")

    add("SENSITIVITY — gold (adversarial Q4), frame b")
    for level, block in report["gold_sensitivity"].items():  # type: ignore[union-attr]
        w, wo = block["with_gold"], block["without_gold"]
        add(f"  {level}: with gold decisive {w['decisive_rate']:.1%} "
            f"(n={w['verdicts'] and sum(w['verdicts'].values())})   "
            f"without gold decisive {wo['decisive_rate']:.1%} "
            f"(n={sum(wo['verdicts'].values())})")
    add("")

    desc = report["descriptive_interval"]
    add("RESEARCH FINDING (not a product judgement) — N_eff with an interval")
    add(f"  median 95% CI width, relative to the estimate  "
        f"{desc['median_relative_width_of_n_eff_ci']:.3f}")
    add(f"  share of portfolios whose CI is wider than half the estimate  "
        f"{desc['share_wider_than_half_the_estimate']:.1%}")
    add("")

    g4 = report["G4_reference_stability"]
    add("G4 — is the reference empirical, or did we build it?")
    add(f"  probe: {g4['probe_portfolios']} four-holding portfolios, verdict recomputed "
        f"under each universe definition")
    add(f"  {'universe':<24} {'reference rho':>13}  {'changed':>8}  {'reversed':>9}")
    for name, reference in g4["reference_by_universe"].items():  # type: ignore[union-attr]
        if name == "full_18":
            add(f"  {name:<24} {reference:>13.4f}  {'baseline':>8}  {'':>9}")
            continue
        block = g4["flips"][name]  # type: ignore[index]
        add(f"  {name:<24} {reference:>13.4f}  "
            f"{block['changed_share']:>7.1%}  {block['reversed_share']:>8.1%}")
    add(f"  reference spread across universes  {g4['reference_spread']:.4f}")
    add(f"  worst outright reversal            {g4['worst_reversed_share']:.1%}")
    add("")

    align = report["alignment"]
    add("ALIGNMENT (adversarial Q5)")
    add(f"  single-instrument observations   "
        f"{align['shortest_single_instrument']}..{align['longest_single_instrument']}")
    add(f"  common grid across all 18        {align['common_grid_observations']} "
        f"({align['days_lost_to_full_universe_alignment']} lost)")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--database", type=Path, default=Path("nivesh.sqlite3"))
    parser.add_argument("--replicates", type=int, default=DEFAULT_REPLICATES)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--out", type=Path, default=None, help="also write JSON here")
    args = parser.parse_args(argv)

    if not args.database.exists():
        print(f"no database at {args.database} — run `make ingest` first", file=sys.stderr)
        return 2

    report = run(args.database, args.replicates)
    if args.out:
        args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
