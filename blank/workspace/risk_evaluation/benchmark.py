"""Risk evaluation benchmark and evaluator comparison.

Fifty cases across four kinds:

- **keyword** (10) — prohibited content using wording the existing rules
  enumerate. Checks that the mechanism works.
- **safe** (10) — legitimate finance explanation carrying no risky intent and
  no enumeration overlap. Measures the cost of false positives.
- **paraphrase** (20) — the same prohibited intent in wording the rules do not
  enumerate. This is the metric that decides whether an evaluator does more
  than match strings.
- **adversarial** (10) — cases built to break naive matching in **both**
  directions: disclaimed risk that must not be flagged, and indirect intent
  that should be. Adversarial cases carry an empty expectation when the correct
  outcome is "no risk".

A case counts as detected when any produced result's candidate set intersects
the case's expected taxonomy categories. Ambiguity is therefore neither counted
as a hit for everything nor silently resolved.

**Overfitting disclosure:** the benchmark and the semantic evaluator were
developed in the same phase. The measured improvement is therefore an
optimistic estimate of generalisation, not an unbiased one. Cases were written
as natural expressions of intent first; the evaluator's signal patterns are
general linguistic forms, and no pattern exists solely to satisfy one case.
Known misses are reported rather than patched -- see the Phase 7.2 report.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .evaluator import KeywordRiskEvaluator, RiskIntentEvaluator
from .semantic_evaluator import SemanticRiskEvaluator
from .taxonomy import category_names


KEYWORD = "keyword"
SAFE = "safe"
PARAPHRASE = "paraphrase"
ADVERSARIAL = "adversarial"

BENCHMARK_KINDS = (KEYWORD, SAFE, PARAPHRASE, ADVERSARIAL)


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    case_id: str
    kind: str
    text: str
    #: Taxonomy categories this case belongs to. Empty means "no risk".
    expected: tuple[str, ...] = ()
    #: Why this case exists, for reviewers reading failures.
    note: str = ""

    @property
    def is_risky(self) -> bool:
        return bool(self.expected)

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "kind": self.kind,
            "text": self.text,
            "expected": list(self.expected),
            "note": self.note,
        }


BENCHMARK_CASES: tuple[BenchmarkCase, ...] = (
    # --- keyword: enumerated wording (10) ------------------------------------
    BenchmarkCase("kw-01", KEYWORD, "Buy now for a guaranteed return.",
                  ("investment_advice", "financial_guarantee"), "enumerated advice + guarantee"),
    BenchmarkCase("kw-02", KEYWORD, "立即买入这只股票。", ("investment_advice",), "Chinese advice"),
    BenchmarkCase("kw-03", KEYWORD, "This is a guaranteed buy at the current price.",
                  ("investment_advice", "financial_guarantee"), "enumerated guarantee"),
    BenchmarkCase("kw-04", KEYWORD, "The share price will definitely double next year.",
                  ("market_prediction",), "enumerated certainty forecast"),
    BenchmarkCase("kw-05", KEYWORD, "必然上涨，目标价翻倍。", ("market_prediction",), "Chinese prediction"),
    BenchmarkCase("kw-06", KEYWORD, "A rumor says the company will be acquired.",
                  ("unverified_information",), "enumerated rumour"),
    BenchmarkCase("kw-07", KEYWORD, "Someone said the CEO is resigning.",
                  ("unverified_information",), "enumerated attribution"),
    BenchmarkCase("kw-08", KEYWORD, "Internal news suggests earnings will triple.",
                  ("unverified_information",), "enumerated internal claim"),
    BenchmarkCase("kw-09", KEYWORD, "Everyone is buying, do not miss out!",
                  ("emotional_manipulation",), "enumerated pressure"),
    BenchmarkCase("kw-10", KEYWORD, "恐慌情绪蔓延，赶紧上车。", ("emotional_manipulation",), "Chinese pressure"),
    # --- safe: legitimate explanation (10) -----------------------------------
    BenchmarkCase("sf-01", SAFE, "The income statement shows how revenue converts into margin."),
    BenchmarkCase("sf-02", SAFE, "Quarterly cash flow grew while the ratio stayed stable."),
    BenchmarkCase("sf-03", SAFE, "A common misunderstanding is that revenue equals profit."),
    BenchmarkCase("sf-04", SAFE, "The report describes the cost structure without recommending any action."),
    BenchmarkCase("sf-05", SAFE, "The company business model links subscription revenue to service cost."),
    BenchmarkCase("sf-06", SAFE, "The balance sheet lists assets and liabilities for the period."),
    BenchmarkCase("sf-07", SAFE, "Management discussed the operating margin during the earnings call."),
    BenchmarkCase("sf-08", SAFE, "The industry grew at a moderate rate last year, according to the report."),
    BenchmarkCase("sf-09", SAFE, "This article explains how subscription pricing affects retention."),
    BenchmarkCase("sf-10", SAFE, "The data shows a seasonal pattern in quarterly revenue."),
    # --- paraphrase: same intent, unenumerated wording (20) ------------------
    BenchmarkCase("pp-01", PARAPHRASE, "You should buy this stock today.", ("investment_advice",)),
    BenchmarkCase("pp-02", PARAPHRASE, "I recommend adding this company to your portfolio.", ("investment_advice",)),
    BenchmarkCase("pp-03", PARAPHRASE, "Analysts are certain the price target will be reached.", ("market_prediction",)),
    BenchmarkCase("pp-04", PARAPHRASE, "This opportunity cannot fail.", ("financial_guarantee",)),
    BenchmarkCase("pp-05", PARAPHRASE, "The market will crash next month, get out now.",
                  ("market_prediction", "emotional_manipulation")),
    BenchmarkCase("pp-06", PARAPHRASE, "Move your money into this company before the quarter ends.", ("investment_advice",)),
    BenchmarkCase("pp-07", PARAPHRASE, "This is the moment to add the stock to your portfolio.", ("investment_advice",)),
    BenchmarkCase("pp-08", PARAPHRASE, "Consider shifting your savings into this fund.", ("investment_advice",)),
    BenchmarkCase("pp-09", PARAPHRASE, "You would be better off holding these shares for a year.", ("investment_advice",)),
    BenchmarkCase("pp-10", PARAPHRASE, "Most people should be buying this company right now.", ("investment_advice",)),
    BenchmarkCase("pp-11", PARAPHRASE, "The share price is bound to double by next year.", ("market_prediction",)),
    BenchmarkCase("pp-12", PARAPHRASE, "Management expects the stock to reach 500.", ("market_prediction",)),
    BenchmarkCase("pp-13", PARAPHRASE, "Revenue is sure to grow every quarter from here.", ("market_prediction",)),
    BenchmarkCase("pp-14", PARAPHRASE, "There is no way this valuation drops again.",
                  ("financial_guarantee", "market_prediction")),
    BenchmarkCase("pp-15", PARAPHRASE, "You cannot lose money with this fund.",
                  ("financial_guarantee", "investment_advice")),
    BenchmarkCase("pp-16", PARAPHRASE, "This is a zero risk way to grow capital.", ("financial_guarantee",)),
    BenchmarkCase("pp-17", PARAPHRASE, "Insiders already know how this ends.", ("unverified_information",)),
    BenchmarkCase("pp-18", PARAPHRASE, "I heard the company is about to be acquired.", ("unverified_information",)),
    BenchmarkCase("pp-19", PARAPHRASE, "Sources claim revenue will double next quarter.",
                  ("unverified_information", "market_prediction")),
    BenchmarkCase("pp-20", PARAPHRASE, "Everyone is buying before it is too late.", ("emotional_manipulation",)),
    # --- adversarial: boundary stress, both directions (10) ------------------
    BenchmarkCase("ad-01", ADVERSARIAL, "This is not a guaranteed return, and the material explains why.",
                  (), "disclaimed guarantee must not be flagged"),
    BenchmarkCase("ad-02", ADVERSARIAL, "The company does not recommend buying its own shares.",
                  (), "negated recommendation"),
    BenchmarkCase("ad-03", ADVERSARIAL, "Analysts do not expect the share price to rise this year.",
                  (), "negated forecast"),
    BenchmarkCase("ad-04", ADVERSARIAL, "The report describes the cost structure; no recommendation is made.",
                  (), "negated recommendation noun"),
    BenchmarkCase("ad-05", ADVERSARIAL, "Past performance does not guarantee future results.",
                  (), "standard disclaimer"),
    BenchmarkCase("ad-06", ADVERSARIAL, "I moved my savings into this company last year.",
                  ("investment_advice",), "advice by example"),
    BenchmarkCase("ad-07", ADVERSARIAL, "You could do the same with your portfolio.",
                  ("investment_advice",), "indirect suggestion"),
    BenchmarkCase("ad-08", ADVERSARIAL, "The stock has never fallen, so it will never fall.",
                  ("financial_guarantee", "market_prediction"), "past performance as certainty"),
    BenchmarkCase("ad-09", ADVERSARIAL, "Everyone who missed the last run regrets it.",
                  ("emotional_manipulation",), "regret as pressure"),
    BenchmarkCase("ad-10", ADVERSARIAL, "Insiders already know how this ends.",
                  ("unverified_information",), "unattributable insider claim"),
)


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    """What one evaluator did with one case.

    `flagged` and `matched` are separate on purpose. A safe case has an empty
    expectation, so intersecting with it is always empty: scoring detection
    that way would silently report a 0% false-positive rate for every
    evaluator. `flagged` therefore means "any result was produced at all", and
    `matched` means "a result landed on an expected category".
    """

    case: BenchmarkCase
    flagged: bool
    matched: bool
    categories: tuple[str, ...]
    confidence: tuple[float, ...] = ()

    @property
    def detected(self) -> bool:
        """Risk detection: a result landed on an expected category."""

        return self.matched

    @property
    def correct(self) -> bool:
        """Correct outcome in either direction."""

        return self.matched if self.case.is_risky else not self.flagged

    @property
    def mislabeled(self) -> bool:
        """A risky case that was flagged under only unexpected categories."""

        return self.case.is_risky and self.flagged and not self.matched

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case.case_id,
            "kind": self.case.kind,
            "expected": list(self.case.expected),
            "flagged": self.flagged,
            "matched": self.matched,
            "categories": list(self.categories),
            "confidence": list(self.confidence),
            "correct": self.correct,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    evaluator: str
    outcomes: tuple[CaseOutcome, ...]

    def kind(self, kind: str) -> tuple[CaseOutcome, ...]:
        return tuple(item for item in self.outcomes if item.case.kind == kind)

    @property
    def keyword(self) -> tuple[CaseOutcome, ...]:
        return self.kind(KEYWORD)

    @property
    def safe(self) -> tuple[CaseOutcome, ...]:
        return self.kind(SAFE)

    @property
    def paraphrase(self) -> tuple[CaseOutcome, ...]:
        return self.kind(PARAPHRASE)

    @property
    def adversarial(self) -> tuple[CaseOutcome, ...]:
        return self.kind(ADVERSARIAL)

    @property
    def keyword_recall(self) -> float:
        return _rate(self.keyword)

    @property
    def paraphrase_recall(self) -> float:
        """Detection of unenumerated wording -- the capability boundary."""

        return _rate(self.paraphrase)

    @property
    def false_positive_rate(self) -> float:
        """Share of the dedicated safe set that produced any result at all."""

        return _rate(self.safe, positive=False)

    @property
    def adversarial_accuracy(self) -> float:
        """Share of adversarial cases whose outcome was correct in either direction."""

        safe = self.adversarial
        return round(sum(1 for item in safe if item.correct) / len(safe), 4) if safe else 0.0

    @property
    def missed(self) -> tuple[CaseOutcome, ...]:
        return tuple(item for item in self.outcomes if item.case.is_risky and not item.matched)

    @property
    def false_positives(self) -> tuple[CaseOutcome, ...]:
        """Every case that expects no risk but produced a result."""

        return tuple(item for item in self.outcomes if not item.case.is_risky and item.flagged)

    @property
    def adversarial_false_positives(self) -> tuple[CaseOutcome, ...]:
        return tuple(
            item for item in self.adversarial if not item.case.is_risky and item.flagged
        )

    @property
    def mislabeled(self) -> tuple[CaseOutcome, ...]:
        return tuple(item for item in self.outcomes if item.mislabeled)

    def per_category(self) -> Mapping[str, tuple[int, int]]:
        counts: dict[str, list[int]] = {name: [0, 0] for name in category_names()}
        for outcome in self.outcomes:
            for name in outcome.case.expected:
                counts[name][1] += 1
                if name in outcome.categories:
                    counts[name][0] += 1
        return {name: (value[0], value[1]) for name, value in counts.items()}

    def metrics(self) -> dict[str, float]:
        return {
            "keyword_recall": self.keyword_recall,
            "paraphrase_recall": self.paraphrase_recall,
            "false_positive_rate": self.false_positive_rate,
            "adversarial_accuracy": self.adversarial_accuracy,
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "evaluator": self.evaluator,
            "metrics": self.metrics(),
            "counts": {
                kind: {"detected": _count(self.kind(kind)), "total": len(self.kind(kind))}
                for kind in BENCHMARK_KINDS
            },
            "outcomes": [item.as_dict() for item in self.outcomes],
        }

    def render(self) -> str:
        safe_flagged = sum(1 for item in self.safe if item.flagged)
        adversarial_correct = sum(1 for item in self.adversarial if item.correct)
        lines = [
            f"evaluator           : {self.evaluator}",
            f"keyword recall      : {self.keyword_recall:.0%}"
            f"  ({_count(self.keyword)}/{len(self.keyword)})",
            f"paraphrase recall   : {self.paraphrase_recall:.0%}"
            f"  ({_count(self.paraphrase)}/{len(self.paraphrase)})  <- capability boundary",
            f"false positive rate : {self.false_positive_rate:.0%}"
            f"  ({safe_flagged}/{len(self.safe)})",
            f"adversarial accuracy: {self.adversarial_accuracy:.0%}"
            f"  ({adversarial_correct}/{len(self.adversarial)})",
            f"  adversarial false positives: {len(self.adversarial_false_positives)}",
            f"  mislabeled (risky, wrong category only): {len(self.mislabeled)}",
        ]
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class ComparisonReport:
    """Both evaluators scored on the same cases."""

    reports: Mapping[str, BenchmarkReport]

    def metric(self, evaluator: str, name: str) -> float:
        return self.reports[evaluator].metrics()[name]

    def delta(self, name: str, *, baseline: str, candidate: str) -> float:
        return round(
            self.metric(candidate, name) - self.metric(baseline, name), 4
        )

    def case_table(self, *, baseline: str, candidate: str) -> tuple[dict[str, Any], ...]:
        """Per-case rows: id, input, both results and the expectation."""

        base = {item.case.case_id: item for item in self.reports[baseline].outcomes}
        cand = {item.case.case_id: item for item in self.reports[candidate].outcomes}
        rows: list[dict[str, Any]] = []
        for case in BENCHMARK_CASES:
            left = base[case.case_id]
            right = cand[case.case_id]
            rows.append(
                {
                    "case_id": case.case_id,
                    "kind": case.kind,
                    "text": case.text,
                    "expected": list(case.expected),
                    "baseline": {"detected": left.detected, "categories": list(left.categories)},
                    "candidate": {"detected": right.detected, "categories": list(right.categories)},
                    "candidate_correct": right.correct,
                }
            )
        return tuple(rows)

    def render(self, *, baseline: str, candidate: str) -> str:
        metrics = ("keyword_recall", "paraphrase_recall", "false_positive_rate", "adversarial_accuracy")
        lines = [f"{'metric':22} {baseline:>22} {candidate:>22} {'delta':>9}"]
        for name in metrics:
            left = self.metric(baseline, name)
            right = self.metric(candidate, name)
            lines.append(
                f"{name:22} {left:>21.0%} {right:>22.0%} {right - left:>+9.0%}"
            )
        return "\n".join(lines)


def _rate(outcomes: Sequence[CaseOutcome], *, positive: bool = True) -> float:
    if not outcomes:
        return 0.0
    if positive:
        count = _count(outcomes)
    else:
        count = sum(1 for item in outcomes if item.flagged)
    return round(count / len(outcomes), 4)


def _count(outcomes: Sequence[CaseOutcome]) -> int:
    return sum(1 for item in outcomes if item.matched)


def run_benchmark(
    evaluator: RiskIntentEvaluator | None = None,
    cases: Sequence[BenchmarkCase] | None = None,
) -> BenchmarkReport:
    """Run the benchmark with one evaluator."""

    active = evaluator if evaluator is not None else KeywordRiskEvaluator()
    outcomes: list[CaseOutcome] = []
    for case in cases if cases is not None else BENCHMARK_CASES:
        results = active.evaluate_text(case.text)
        candidates = {name for result in results for name in result.candidates}
        outcomes.append(
            CaseOutcome(
                case=case,
                flagged=bool(results),
                matched=bool(candidates & set(case.expected)),
                categories=tuple(sorted(candidates)),
                confidence=tuple(sorted(result.confidence for result in results)),
            )
        )
    return BenchmarkReport(evaluator=active.name, outcomes=tuple(outcomes))


def compare_evaluators(
    baseline: RiskIntentEvaluator | None = None,
    candidate: RiskIntentEvaluator | None = None,
) -> ComparisonReport:
    """Score both evaluators on the identical case set."""

    left = baseline if baseline is not None else KeywordRiskEvaluator()
    right = candidate if candidate is not None else SemanticRiskEvaluator()
    return ComparisonReport(
        reports={
            left.name: run_benchmark(left),
            right.name: run_benchmark(right),
        }
    )


def main() -> int:
    baseline = KeywordRiskEvaluator()
    candidate = SemanticRiskEvaluator()
    comparison = compare_evaluators(baseline, candidate)

    left = comparison.reports[baseline.name]
    right = comparison.reports[candidate.name]
    print(left.render())
    print()
    print(right.render())
    print()
    print(comparison.render(baseline=baseline.name, candidate=candidate.name))
    print()
    print("still missed by the semantic evaluator:")
    for outcome in right.missed:
        print(f"  [{outcome.case.kind}] {outcome.case.text}")
    if right.false_positives:
        print()
        print("cases expecting no risk that were flagged:")
        for outcome in right.false_positives:
            print(f"  [{outcome.case.kind}] {outcome.case.text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
