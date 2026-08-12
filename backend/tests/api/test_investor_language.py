"""The words an investor sees are an invariant, and invariants get tested (M6c).

**Why this is a source scan rather than a rendering test.** Frontend test infrastructure
is a deliberately deferred item (PROJECT_CONTEXT §10) — no runner exists, and adding one
is an ED-scale decision nobody has taken. But "the product must never phrase a
description as advice" is not a rendering detail; it is the doc 14 no-advice boundary,
and a rule enforced only by reviewer vigilance is a rule that quietly stops holding.

So this scans the source of the module that produces every investor-facing sentence, in
exactly the way `tools/ci/vendor_isolation.py` scans for leaked vendor names. It cannot
prove the pane renders correctly — that needs the deferred runner. It *can* prove the
sentences the pane is built from say nothing they should not, which is the substantive
half and the half that would do real damage.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ANSWER_MODULE = (
    Path(__file__).resolve().parents[3] / "web/components/terminal/portfolioAnswer.ts"
)

#: Words that turn a description of the past into a recommendation (doc 14).
ADVICE_WORDS = (
    "should", "must", "buy", "sell", "reduce", "increase",
    "recommend", "advise", "advice", "rebalance", "trim",
)

#: Words that overstate a volatility measurement as a claim about total risk. The
#: engine compares how much a portfolio *moved*; concentration, liquidity, drawdown
#: depth and single-stock events are all invisible to it.
RISK_WORDS = (
    "riskier", "riskiest", "safer", "safest", "aggressive",
    "conservative", "dangerous",
)


def _investor_sentences() -> list[str]:
    """Every string literal the answer module can put in front of an investor.

    Template literals and quoted strings only — identifiers, type names and the lexicon
    constants themselves are not sentences, and matching them would make this test fail
    on the very lists that exist to prevent the failure.
    """
    source = ANSWER_MODULE.read_text()
    # Drop the exported lexicons: they *contain* the banned words by design.
    source = re.sub(r"export const (ADVICE|RISK)_LEXICON[^;]+;", "", source, flags=re.S)
    # Drop comments: prose explaining the rule may name the words the rule bans.
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    source = re.sub(r"//[^\n]*", "", source)
    return re.findall(r"`([^`]*)`", source) + re.findall(r'"([^"]*)"', source)


def test_the_answer_module_exists_where_the_scan_expects_it() -> None:
    """A moved file must fail loudly rather than silently scanning nothing."""
    assert ANSWER_MODULE.is_file(), f"investor answer module not found at {ANSWER_MODULE}"


def test_there_are_sentences_to_scan() -> None:
    """Guards the way this test could pass while checking nothing."""
    sentences = _investor_sentences()
    assert len(sentences) >= 3
    assert any("Nifty 50" in sentence for sentence in sentences)


@pytest.mark.parametrize("word", ADVICE_WORDS)
def test_no_investor_sentence_gives_advice(word: str) -> None:
    """doc 14's no-advice boundary, enforced on the words rather than on intent."""
    for sentence in _investor_sentences():
        assert not re.search(rf"\b{word}\b", sentence, re.I), (
            f"advice word {word!r} in investor-facing text: {sentence!r}"
        )


@pytest.mark.parametrize("word", RISK_WORDS)
def test_no_investor_sentence_claims_more_than_volatility(word: str) -> None:
    """The judgement characterizes realized volatility; it does not assert total risk."""
    for sentence in _investor_sentences():
        assert not re.search(rf"\b{word}\b", sentence, re.I), (
            f"risk word {word!r} in a volatility comparison: {sentence!r}"
        )


def test_the_inconclusive_answer_blames_the_window_not_the_instrument() -> None:
    """"Measurement error" implies a faulty ruler. The truth is a short sample."""
    sentences = _investor_sentences()
    assert any("not statistically distinguishable" in s for s in sentences)
    assert any("window of this length" in s for s in sentences)
    assert not any("measurement error" in s.lower() for s in sentences)


def test_the_inconclusive_answer_is_never_phrased_as_equality() -> None:
    """Failing to detect a difference is not evidence of equality.

    The sentence may say the two moved by similar *amounts* — an observation — but must
    not assert they are the same, which the test cannot support.
    """
    for sentence in _investor_sentences():
        assert not re.search(r"\b(identical|the same as|equal to)\b", sentence, re.I)
