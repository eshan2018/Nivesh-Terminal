/* The investor-facing answer, as data rather than as JSX (M6c).
 *
 * Separated from the component for one reason: **it is testable this way.** The
 * acceptance criteria for this milestone are about the words — that the answer leads
 * with plain language, that it never uses risk vocabulary for a volatility measurement,
 * and that it never phrases a description as advice. A rule you can only check by
 * reading rendered markup is a rule that quietly stops holding.
 *
 * The narrative here is a deterministic template. No model writes it, and none will:
 * when L8 arrives (Phase 7) its job is to *explain* this verdict, never to author one.
 */

export type Verdict =
  | "HIGHER_REALIZED_VOLATILITY"
  | "NOT_DISTINGUISHABLE"
  | "LOWER_REALIZED_VOLATILITY";

/** Words that would turn a description of the past into a recommendation. */
export const ADVICE_LEXICON = [
  "should", "must", "buy", "sell", "reduce", "increase", "recommend",
  "consider", "advise", "advice", "rebalance", "trim", "add to",
] as const;

/** Words that would overstate a volatility measurement as a claim about total risk. */
export const RISK_LEXICON = [
  "risk", "riskier", "riskiest", "safer", "safest", "safe",
  "aggressive", "conservative", "dangerous",
] as const;

/**
 * The primary answer: one sentence, plain language, no technical vocabulary.
 *
 * It states all three things an investor needs to act on the comparison — direction,
 * magnitude, and the window it covers — and nothing it cannot support. "Moved more than"
 * is a measurement; "riskier than" would be a claim about concentration, liquidity and
 * drawdown that this evidence never saw.
 */
export function primaryAnswer(
  verdict: Verdict,
  ratio: number,
  observations: number,
): string {
  const period = `over the last ${observations} trading days`;
  switch (verdict) {
    case "HIGHER_REALIZED_VOLATILITY":
      return `Your portfolio moved about ${ratio.toFixed(2)}× as much as the Nifty 50 ${period}.`;
    case "LOWER_REALIZED_VOLATILITY":
      return `Your portfolio moved about ${ratio.toFixed(2)}× as much as the Nifty 50 ${period} — less than the index.`;
    case "NOT_DISTINGUISHABLE":
      return `Your portfolio and the Nifty 50 moved by similar amounts ${period}. The difference is not statistically distinguishable over a window of this length.`;
  }
}

/**
 * The qualifier that must never be separated from the verdict.
 *
 * `NOT_DISTINGUISHABLE` is deliberately not called "similar": failing to detect a
 * difference is not evidence of equality, and a short window is the usual reason.
 */
export function confidenceNote(
  verdict: Verdict,
  low: number,
  high: number,
  confidenceLevel: string,
): string {
  if (verdict === "NOT_DISTINGUISHABLE") {
    return `A longer history could still separate them. At ${confidenceLevel} confidence the comparison lies between ${low.toFixed(2)}× and ${high.toFixed(2)}×, which spans 1.00×.`;
  }
  return `At ${confidenceLevel} confidence the comparison lies between ${low.toFixed(2)}× and ${high.toFixed(2)}×.`;
}

/** Every string this module can put in front of an investor, for the lexicon tests. */
export function allAnswerStrings(): string[] {
  const verdicts: Verdict[] = [
    "HIGHER_REALIZED_VOLATILITY",
    "NOT_DISTINGUISHABLE",
    "LOWER_REALIZED_VOLATILITY",
  ];
  return verdicts.flatMap((verdict) => [
    primaryAnswer(verdict, 1.24, 248),
    confidenceNote(verdict, 1.05, 1.46, "95%"),
  ]);
}
