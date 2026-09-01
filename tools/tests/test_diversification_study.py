"""The M7 study's arithmetic, against cases whose answers are known in advance.

A study that gates a milestone has to be checkable by someone who was not there when it
ran. Reproducibility (a fixed seed, a committed program) gets you the same numbers twice;
it does not tell you the numbers are right. These are the cases where the correct answer
is fixed by the definition rather than by the data, so a wrong implementation cannot
agree with them by luck.

The study's agreement with `portfolio-risk-return/v1` is checked by the study itself, on
real data, and reported as `cross_engine_check`.
"""
from __future__ import annotations

import math

import pytest

from tools.diversification_study import (
    BLOCK_LENGTH,
    TRADING_DAYS,
    block_resample,
    covariance,
    interval,
    stats_for,
    universe_mean_correlation,
)

#: Two orthogonal Walsh sequences: equal variance, exactly zero correlation, and no
#: randomness anywhere near them.
ORTHOGONAL_A = [1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 1.0, -1.0]
ORTHOGONAL_B = [1.0, 1.0, -1.0, -1.0, 1.0, 1.0, -1.0, -1.0]


def test_perfectly_correlated_holdings_collapse_to_one() -> None:
    """Two copies of the same series diversify nothing — the definitional floor."""
    matrix = covariance([ORTHOGONAL_A, list(ORTHOGONAL_A)])
    stats = stats_for(matrix, (0, 1))

    assert stats.mean_correlation == pytest.approx(1.0)
    assert stats.diversification_ratio == pytest.approx(1.0)
    assert stats.n_eff == pytest.approx(1.0)


def test_uncorrelated_holdings_do_not_collapse() -> None:
    """Zero correlation, equal volatility: N_eff must equal the holdings count."""
    matrix = covariance([ORTHOGONAL_A, ORTHOGONAL_B])
    stats = stats_for(matrix, (0, 1))

    assert stats.mean_correlation == pytest.approx(0.0, abs=1e-12)
    assert stats.diversification_ratio == pytest.approx(math.sqrt(2.0))
    assert stats.n_eff == pytest.approx(2.0)


def test_n_eff_matches_the_closed_form_for_equal_volatilities() -> None:
    """`D² = k / (1 + (k−1)ρ̄)`.

    Pinned because it is the reason `N_eff` and `ρ̄` may never be reported as two
    agreeing pieces of evidence: under equal weights they are the same number written
    two ways. An identity corroborates nothing.
    """
    matrix = covariance([ORTHOGONAL_A, ORTHOGONAL_B, list(ORTHOGONAL_A)])
    stats = stats_for(matrix, (0, 1, 2))

    count = 3
    closed_form = count / (1.0 + (count - 1) * stats.mean_correlation)
    assert stats.n_eff == pytest.approx(closed_form)


def test_the_statistics_are_scale_free() -> None:
    """Rescaling a holding changes its volatility, never the co-movement description."""
    plain = stats_for(covariance([ORTHOGONAL_A, ORTHOGONAL_B]), (0, 1))
    scaled = stats_for(
        covariance([ORTHOGONAL_A, [v * 7.5 for v in ORTHOGONAL_B]]), (0, 1)
    )

    assert scaled.mean_correlation == pytest.approx(plain.mean_correlation, abs=1e-12)
    # Volatility is not scale-free, and must move.
    assert scaled.volatility > plain.volatility


def test_volatility_is_annualized() -> None:
    """A daily standard deviation reported as an annual figure, by √252."""
    matrix = covariance([ORTHOGONAL_A, list(ORTHOGONAL_A)])
    daily = math.sqrt(matrix[0][0])

    assert stats_for(matrix, (0, 1)).volatility == pytest.approx(
        daily * math.sqrt(TRADING_DAYS)
    )


def test_universe_mean_correlation_averages_every_pair() -> None:
    matrix = covariance([ORTHOGONAL_A, ORTHOGONAL_B, list(ORTHOGONAL_A)])
    pairs = [
        matrix[i][j] / math.sqrt(matrix[i][i] * matrix[j][j])
        for i, j in ((0, 1), (0, 2), (1, 2))
    ]

    assert universe_mean_correlation(matrix) == pytest.approx(sum(pairs) / 3)


def test_the_bootstrap_is_deterministic_for_a_fixed_seed() -> None:
    """A gating result that moves between runs cannot gate anything."""
    import random

    first = block_resample(200, random.Random(7))
    second = block_resample(200, random.Random(7))
    assert first == second
    assert len(first) == 200


def test_resampled_rows_come_in_contiguous_blocks() -> None:
    """Blocks are what carry volatility clustering through a resample.

    An i.i.d. row bootstrap would break the serial dependence that makes real returns
    cluster, and would report intervals narrower than the evidence supports.
    """
    import random

    rows = block_resample(120, random.Random(3))
    starts = range(0, len(rows) - BLOCK_LENGTH, BLOCK_LENGTH)
    assert any(
        all(rows[s + step] == rows[s] + step for step in range(BLOCK_LENGTH))
        for s in starts
    )


def test_the_interval_brackets_the_bulk_of_the_draws() -> None:
    draws = [float(value) for value in range(1000)]
    low, high = interval(draws, 0.95)

    assert low == pytest.approx(25.0, abs=15.0)
    assert high == pytest.approx(975.0, abs=15.0)
    assert low < high
