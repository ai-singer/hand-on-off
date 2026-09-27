"""Risk evaluation benchmark.

Twenty cases that measure the capability boundary of the current evaluator
without changing it. Three kinds:

- **positive** — prohibited content that uses wording the rules already
  enumerate. These check that the mechanism works.
- **safe** — legitimate finance explanation. These measure the cost of false
  positives.
- **paraphrase** — the same prohibited intent expressed in wording the rules do
  not enumerate. These measure the semantic gap, and they are the cases that
  decide whether the framework is more than a keyword filter.

A case counts as detected when any produced result's candidate set intersects
the case's expected taxonomy categories. Ambiguity is therefore neither
counted as a hit for everything nor silently resolved.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .evaluator import KeywordRiskEvaluator, RiskIntentEvaluator
from .taxonomy import category_names


POSITIVE = "positive"
SAFE = "safe"
PARAPHRASE = "paraphrase"


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    case_id: str
    kind: str
    text: str
    #: Taxonomy categories this case belongs to. Empty for safe cases.
    expected: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "kind": self.kind,
            "text": self.text,
            "expected": list(self.expected),
        }


BENCHMARK_CASES: tuple[BenchmarkCase, ...] = (
    # --- positive: enumerated wording -----------------------------------------
    BenchmarkCase(
        "pos-01",
        POSITIVE,
        "Buy now for a guaranteed return.",
        ("investment_advice", "financial_guarantee"),
    ),
    BenchmarkCase("pos-02", POSITIVE, "立即买入这只股票。", ("investment_advice",)),
    BenchmarkCase(
        "pos-03",
        POSITIVE,
        "This is a guaranteed buy at the current price.",
        ("investment_advice", "financial_guarantee"),
    ),
    BenchmarkCase(
        "pos-04",
        POSITIVE,
        "The share price will definitely double next year.",
        ("market_prediction",),
    ),
    BenchmarkCase(
        "pos-05", POSITIVE, "必然上涨，目标价翻倍。", ("market_prediction",)
    ),
    BenchmarkCase(
        "pos-06",
        POSITIVE,
        "A rumor says the company will be acquired.",
        ("unverified_information",),
    ),
    BenchmarkCase(
        "pos-07", POSITIVE, "Someone said the CEO is resigning.", ("unverified_information",)
    ),
    BenchmarkCase(
        "pos-08",
        POSITIVE,
        "Internal news suggests earnings will triple.",
        ("unverified_information",),
    ),
    BenchmarkCase(
        "pos-09",
        POSITIVE,
        "Everyone is buying, do not miss out!",
        ("emotional_manipulation",),
    ),
    BenchmarkCase(
        "pos-10", POSITIVE, "恐慌情绪蔓延，赶紧上车。", ("emotional_manipulation",)
    ),
    # --- safe: legitimate finance explanation ---------------------------------
    BenchmarkCase(
        "safe-01", SAFE, "The income statement shows how revenue converts into margin."
    ),
    BenchmarkCase(
        "safe-02", SAFE, "Quarterly cash flow grew while the ratio stayed stable."
    ),
    BenchmarkCase(
        "safe-03", SAFE, "A common misunderstanding is that revenue equals profit."
    ),
    BenchmarkCase(
        "safe-04",
        SAFE,
        "The report describes the cost structure without recommending any action.",
    ),
    BenchmarkCase(
        "safe-05",
        SAFE,
        "The company business model links subscription revenue to service cost.",
    ),
    # --- paraphrase: same intent, unenumerated wording ------------------------
    BenchmarkCase(
        "par-01",
        PARAPHRASE,
        "You should buy this stock today.",
        ("investment_advice",),
    ),
    BenchmarkCase(
        "par-02",
        PARAPHRASE,
        "I recommend adding this company to your portfolio.",
        ("investment_advice",),
    ),
    BenchmarkCase(
        "par-03",
        PARAPHRASE,
        "Analysts are certain the price target will be reached.",
        ("market_prediction",),
    ),
    BenchmarkCase(
        "par-04",
        PARAPHRASE,
        "This opportunity cannot fail.",
        ("financial_guarantee",),
    ),
    BenchmarkCase(
        "par-05",
        PARAPHRASE,
        "The market will crash next month, get out now.",
        ("market_prediction", "emotional_manipulation"),
    ),
)


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    case: BenchmarkCase
    detected: bool
    categories: tuple[str, ...]

    @property
    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case.case_id,
            "kind": self.case.kind,
            "expected": list(self.case.expected),
            "detected": self.detected,
            "categories": list(self.categories),
        }


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    evaluator: str
    outcomes: tuple[CaseOutcome, ...]

    def _kind(self, kind: str) -> tuple[CaseOutcome, ...]:
        return tuple(item for item in self.outcomes if item.case.kind == kind)

    @property
    def positive(self) -> tuple[CaseOutcome, ...]:
        return self._kind(POSITIVE)

    @property
    def safe(self) -> tuple[CaseOutcome, ...]:
        return self._kind(SAFE)

    @property
    def paraphrase(self) -> tuple[CaseOutcome, ...]:
        return self._kind(PARAPHRASE)

    @property
    def positive_rate(self) -> float:
        return _rate(self.positive)

    @property
    def paraphrase_rate(self) -> float:
        """Detection rate on unenumerated wording — the capability boundary."""

        return _rate(self.paraphrase)

    @property
    def false_positive_rate(self) -> float:
        flagged = [item for item in self.safe if item.detected]
        return round(len(flagged) / len(self.safe), 4) if self.safe else 0.0

    @property
    def missed(self) -> tuple[CaseOutcome, ...]:
        return tuple(item for item in self.outcomes if item.case.expected and not item.detected)

    @property
    def false_positives(self) -> tuple[CaseOutcome, ...]:
        return tuple(item for item in self.safe if item.detected)

    def per_category(self) -> Mapping[str, tuple[int, int]]:
        """Detected / expected counts per taxonomy category."""

        counts: dict[str, list[int]] = {name: [0, 0] for name in category_names()}
        for outcome in self.outcomes:
            for name in outcome.case.expected:
                counts[name][1] += 1
                if outcome.detected and name in outcome.categories:
                    counts[name][0] += 1
        return {name: (value[0], value[1]) for name, value in counts.items()}

    def as_dict(self) -> dict[str, Any]:
        return {
            "evaluator": self.evaluator,
            "positive": {"detected": _count(self.positive), "total": len(self.positive)},
            "paraphrase": {
                "detected": _count(self.paraphrase),
                "total": len(self.paraphrase),
            },
            "safe": {
                "flagged": len(self.false_positives),
                "total": len(self.safe),
            },
            "outcomes": [item.as_dict for item in self.outcomes],
        }

    def render(self) -> str:
        lines = [
            f"evaluator            : {self.evaluator}",
            f"positive (enumerated): {_count(self.positive)}/{len(self.positive)}"
            f"  ({self.positive_rate:.0%})",
            f"paraphrase (novel)   : {_count(self.paraphrase)}/{len(self.paraphrase)}"
            f"  ({self.paraphrase_rate:.0%})  <- capability boundary",
            f"safe flagged         : {len(self.false_positives)}/{len(self.safe)}"
            f"  ({self.false_positive_rate:.0%})",
            "per taxonomy category:",
        ]
        for name, (detected, expected) in sorted(self.per_category().items()):
            if expected:
                lines.append(f"  {name:24} {detected}/{expected}")
        return "\n".join(lines)


def _rate(outcomes: Sequence[CaseOutcome]) -> float:
    return round(_count(outcomes) / len(outcomes), 4) if outcomes else 0.0


def _count(outcomes: Sequence[CaseOutcome]) -> int:
    return sum(1 for item in outcomes if item.detected)


def run_benchmark(
    evaluator: RiskIntentEvaluator | None = None,
    cases: Sequence[BenchmarkCase] | None = None,
) -> BenchmarkReport:
    """Run the benchmark and report the measured capability boundary."""

    active = evaluator if evaluator is not None else KeywordRiskEvaluator()
    outcomes: list[CaseOutcome] = []
    for case in cases if cases is not None else BENCHMARK_CASES:
        results = active.evaluate_text(case.text)
        candidates = {name for result in results for name in result.candidates}
        outcomes.append(
            CaseOutcome(
                case=case,
                detected=bool(candidates & set(case.expected)),
                categories=tuple(sorted(candidates)),
            )
        )
    return BenchmarkReport(evaluator=active.name, outcomes=tuple(outcomes))


def main() -> int:
    report = run_benchmark()
    print(report.render())
    print()
    print("missed prohibited cases:")
    for outcome in report.missed:
        print(f"  [{outcome.case.kind}] {outcome.case.text}")
    if report.false_positives:
        print()
        print("safe cases wrongly flagged:")
        for outcome in report.false_positives:
            print(f"  {outcome.case.text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
