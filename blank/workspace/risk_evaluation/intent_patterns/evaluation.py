"""The `intent_pattern/v1` benchmark, and the comparisons it exists to make.

Three groups, three different questions:

    positive  an author-voice guarantee       the pattern must fire
    negative  no guarantee relation at all    the pattern must not fire
    boundary  guarantee vocabulary, but conditional, reported or uncertain

**Boundary cases are not negative cases.** The old evaluator misses them and the
new pattern layer fires on them, and neither is the whole answer: a relation
matcher finds relations, and deciding whether a reported or conditional
guarantee is *the article's* guarantee is the attribution layer's job. Scoring
boundary as an error would penalise the pattern layer for a question it does not
ask, and scoring it as a success would hide a real cost. It is reported
separately, and section 6 of the report measures what adding the attribution
layer does to it.

Two scoring views are produced for that reason:

    relation view   positives and negatives only - did the relation matcher work?
    category view   boundary counted as benign - what does it cost before
                    attribution is applied?

The benchmark is versioned here as `v1` and exported to `benchmark_v1.json`. It is
**not registered in the benchmark registry**: Phase 8.4's permitted additions are
this package, tests, benchmarks-as-files and docs, and registering a version is a
governance act on shared code that this phase was not asked to perform.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..semantic_evaluator import SemanticRiskEvaluator
from ..semantic_evaluator_v2 import SemanticRiskEvaluatorV2
from .financial_guarantee import PATTERNS
from .matcher import RelationMatcher
from .model import PatternMatch


BENCHMARK_NAME = "intent_pattern"
BENCHMARK_VERSION = "v1"
BENCHMARK_PATH = Path(__file__).resolve().parent / "benchmark_v1.json"
COMPARISON_PATH = Path(__file__).resolve().parent / "comparison_v1.json"

POSITIVE = "positive"
NEGATIVE = "negative"
BOUNDARY = "boundary"
GROUPS = (POSITIVE, NEGATIVE, BOUNDARY)

CATEGORY = "financial_guarantee"

REQUIRED_GROUP_SIZES: Mapping[str, int] = {
    POSITIVE: 15,
    NEGATIVE: 15,
    BOUNDARY: 10,
}


@dataclass(frozen=True, slots=True)
class PatternBenchmarkCase:
    case_id: str
    group: str
    text: str
    forms: tuple[str, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        if self.group not in GROUPS:
            raise ValueError(f"{self.case_id}: unknown group {self.group!r}")
        if not self.text.strip():
            raise ValueError(f"{self.case_id}: text must not be empty")

    @property
    def expects_relation(self) -> bool:
        """Positives and boundary cases contain the relation."""

        return self.group in (POSITIVE, BOUNDARY)

    @property
    def expects_category(self) -> bool:
        """Only an asserted, author-voice guarantee is the category."""

        return self.group == POSITIVE

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.case_id,
            "group": self.group,
            "text": self.text,
            "forms": list(self.forms),
            "expects_relation": self.expects_relation,
            "expects_category": self.expects_category,
            "note": self.note,
        }


def _case(
    case_id: str,
    group: str,
    text: str,
    forms: Sequence[str] = (),
    note: str = "",
) -> PatternBenchmarkCase:
    return PatternBenchmarkCase(case_id, group, text, tuple(forms), note)


#: 42 cases. Forms are recorded so the benchmark proves its own coverage: the
#: phase requires active, passive and nominal realisations among the positives,
#: and a test asserts each is present.
BENCHMARK_CASES: tuple[PatternBenchmarkCase, ...] = (
    # -- positive: attributive (the only form the old rule matched) -------
    _case("PG-01", POSITIVE, "This is a guaranteed return.", ("attributive",), "the form the old rule matched"),
    _case("PG-02", POSITIVE, "Guaranteed returns are available.", ("attributive",), "prenominal adjective"),
    # -- positive: copular ------------------------------------------------
    _case("PG-03", POSITIVE, "This return is guaranteed.", ("copular",), "Phase 8.1 blind spot"),
    _case("PG-04", POSITIVE, "Returns are guaranteed.", ("copular",), "Phase 8.1 blind spot"),
    _case("PG-05", POSITIVE, "Your capital is guaranteed.", ("copular",), "Phase 8.1 blind spot"),
    _case("PG-06", POSITIVE, "The profit is guaranteed.", ("copular",), "Phase 8.1 blind spot"),
    _case("PG-07", POSITIVE, "The value of your investment is guaranteed.", ("copular",), "object and copula separated by a phrase"),
    # -- positive: active -------------------------------------------------
    _case("PG-08", POSITIVE, "We guarantee this return.", ("active",), "Phase 8.1 blind spot"),
    _case("PG-09", POSITIVE, "The fund guarantees your capital.", ("active",), "Phase 8.1 blind spot"),
    _case("PG-10", POSITIVE, "We guarantee a profit.", ("active",), "verb form with a determiner"),
    # -- positive: passive ------------------------------------------------
    _case("PG-11", POSITIVE, "Your returns are guaranteed by the scheme.", ("passive",), "participle with an agent"),
    _case("PG-12", POSITIVE, "The capital is guaranteed by the issuer.", ("passive",), "participle with an agent"),
    # -- positive: nominal ------------------------------------------------
    _case("PG-13", POSITIVE, "The fund offers a guarantee of returns.", ("nominal",), "noun form with of"),
    _case("PG-14", POSITIVE, "This plan comes with a guarantee of income.", ("nominal",), "noun form with of"),
    _case("PG-15", POSITIVE, "Returns are a guarantee on this product.", ("nominal",), "noun form with on"),
    # -- positive: risk removed without the word guarantee ----------------
    _case("PG-16", POSITIVE, "Your capital is risk-free.", ("risk_removed",), "parity with the old rule"),
    _case("PG-17", POSITIVE, "This fund cannot lose money.", ("risk_removed",), "parity with the old rule"),
    # -- negative: negation -----------------------------------------------
    _case("NG-01", NEGATIVE, "Returns are not guaranteed.", ("negation",), "copular negated"),
    _case("NG-02", NEGATIVE, "This is not a guaranteed return.", ("negation",), "attributive negated"),
    _case("NG-03", NEGATIVE, "We do not guarantee returns.", ("negation",), "active negated"),
    _case("NG-04", NEGATIVE, "Returns cannot be guaranteed.", ("negation",), "negator inside the frame"),
    _case("NG-05", NEGATIVE, "The fund does not guarantee your capital.", ("negation",), "active negated"),
    _case("NG-06", NEGATIVE, "Past performance does not guarantee future results.", ("negation",), "standard disclaimer"),
    _case("NG-07", NEGATIVE, "A guaranteed return is not available.", ("negation",), "negation after the match"),
    _case("NG-08", NEGATIVE, "The fund will not guarantee your capital.", ("negation",), "future negated"),
    # -- negative: education ----------------------------------------------
    _case("NG-09", NEGATIVE, "A price-to-earnings ratio compares price with earnings per share.", ("education",), "definition"),
    _case("NG-10", NEGATIVE, "Diversification spreads risk across assets.", ("education",), "method guidance"),
    _case("NG-11", NEGATIVE, "Compounding means returns are earned on earlier returns.", ("education",), "definition mentioning returns"),
    # -- negative: discussion ---------------------------------------------
    _case("NG-12", NEGATIVE, "The prospectus explains how charges are calculated.", ("discussion",), "neutral statement"),
    _case("NG-13", NEGATIVE, "The article asks whether a guarantee is ever appropriate.", ("discussion",), "guarantee discussed, not made"),
    _case("NG-14", NEGATIVE, "The regulator reviewed how guarantees are described in marketing.", ("discussion",), "guarantee discussed, not made"),
    _case("NG-15", NEGATIVE, "The word guarantee has a specific legal meaning.", ("discussion",), "mention rather than use"),
    # -- boundary: reported or quoted -------------------------------------
    _case("BD-01", BOUNDARY, "Returns are guaranteed, according to the marketing material.", ("quoted",), "attributed to marketing material"),
    _case("BD-02", BOUNDARY, "The promoter said returns are guaranteed.", ("quoted",), "reported speech"),
    _case("BD-03", BOUNDARY, "Some funds claim their returns are guaranteed.", ("quoted",), "reported claim"),
    _case("BD-04", BOUNDARY, "The advert states that capital is guaranteed.", ("quoted",), "reported claim"),
    _case("BD-05", BOUNDARY, "Returns are said to be guaranteed.", ("quoted",), "reported passive"),
    _case("BD-06", BOUNDARY, "Returns are reportedly guaranteed.", ("quoted",), "reporting adverb"),
    # -- boundary: conditional or uncertain -------------------------------
    _case("BD-07", BOUNDARY, "If markets rise, returns are guaranteed.", ("hypothetical",), "conditional outcome"),
    _case("BD-08", BOUNDARY, "Returns could be guaranteed if the scheme performs.", ("hypothetical",), "conditional with a modal"),
    _case("BD-09", BOUNDARY, "Whether returns are guaranteed depends on the scheme.", ("hypothetical",), "framed as a question"),
    _case("BD-10", BOUNDARY, "Returns may be guaranteed.", ("uncertain",), "hedged with a modal"),
)


def group_cases(
    group: str, cases: Sequence[PatternBenchmarkCase] | None = None
) -> tuple[PatternBenchmarkCase, ...]:
    active = cases if cases is not None else BENCHMARK_CASES
    return tuple(case for case in active if case.group == group)


def group_sizes(
    cases: Sequence[PatternBenchmarkCase] | None = None,
) -> Mapping[str, int]:
    active = cases if cases is not None else BENCHMARK_CASES
    return {group: sum(1 for case in active if case.group == group) for group in GROUPS}


def case_index(
    cases: Sequence[PatternBenchmarkCase] | None = None,
) -> Mapping[str, PatternBenchmarkCase]:
    active = cases if cases is not None else BENCHMARK_CASES
    return {case.case_id: case for case in active}


def form_coverage(
    cases: Sequence[PatternBenchmarkCase] | None = None,
) -> Mapping[str, int]:
    counts: dict[str, int] = {}
    for case in cases if cases is not None else BENCHMARK_CASES:
        for form in case.forms:
            counts[form] = counts.get(form, 0) + 1
    return dict(sorted(counts.items()))


# ---------------------------------------------------------------- scoring


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    case: PatternBenchmarkCase
    pattern_fired: bool
    pattern_scanned: bool
    frame_kinds: tuple[str, ...]
    old_categories: tuple[str, ...]
    old_v1_categories: tuple[str, ...]
    match: PatternMatch | None = None

    @property
    def case_id(self) -> str:
        return self.case.case_id

    @property
    def old_fired(self) -> bool:
        return CATEGORY in self.old_categories

    @property
    def relation_correct(self) -> bool:
        return self.pattern_fired == self.case.expects_relation

    @property
    def category_correct(self) -> bool:
        return self.pattern_fired == self.case.expects_category

    @property
    def old_category_correct(self) -> bool:
        return self.old_fired == self.case.expects_category

    @property
    def transition(self) -> str:
        if self.old_category_correct and self.category_correct:
            return "unchanged"
        if not self.old_category_correct and self.category_correct:
            return "fixed"
        if self.old_category_correct and not self.category_correct:
            return "broken"
        return "different"

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "group": self.case.group,
            "text": self.case.text,
            "forms": list(self.case.forms),
            "expects_relation": self.case.expects_relation,
            "expects_category": self.case.expects_category,
            "pattern_fired": self.pattern_fired,
            "pattern_scanned": self.pattern_scanned,
            "frame_kinds": list(self.frame_kinds),
            "old_categories": list(self.old_categories),
            "old_fired": self.old_fired,
            "old_v1_categories": list(self.old_v1_categories),
            "relation_correct": self.relation_correct,
            "category_correct": self.category_correct,
            "transition": self.transition,
        }


def evaluate_case(
    case: PatternBenchmarkCase,
    matcher: RelationMatcher,
    *,
    old: SemanticRiskEvaluatorV2 | None = None,
    old_v1: SemanticRiskEvaluator | None = None,
) -> CaseOutcome:
    match = matcher.match_pattern(case.text, PATTERNS.patterns[0])
    old_evaluator = old if old is not None else SemanticRiskEvaluatorV2()
    v1_evaluator = old_v1 if old_v1 is not None else SemanticRiskEvaluator()
    return CaseOutcome(
        case=case,
        pattern_fired=match.fired,
        pattern_scanned=match.scanned,
        frame_kinds=match.frame_kinds,
        old_categories=tuple(
            sorted({item.category for item in old_evaluator.evaluate_text(case.text)})
        ),
        old_v1_categories=tuple(
            sorted({item.category for item in v1_evaluator.evaluate_text(case.text)})
        ),
        match=match,
    )


@dataclass(frozen=True, slots=True)
class PatternMetrics:
    """Recall, false positives and misses, in the two views."""

    outcomes: tuple[CaseOutcome, ...]
    scope: str

    def _in_scope(self) -> tuple[CaseOutcome, ...]:
        if self.scope == "relation":
            return tuple(item for item in self.outcomes if item.case.group != BOUNDARY)
        return self.outcomes

    @property
    def positives(self) -> tuple[CaseOutcome, ...]:
        return tuple(item for item in self.outcomes if item.case.group == POSITIVE)

    @property
    def negatives(self) -> tuple[CaseOutcome, ...]:
        return tuple(item for item in self.outcomes if item.case.group == NEGATIVE)

    @property
    def boundary(self) -> tuple[CaseOutcome, ...]:
        return tuple(item for item in self.outcomes if item.case.group == BOUNDARY)

    # -- new pattern layer ------------------------------------------------

    @property
    def true_positives(self) -> int:
        return sum(1 for item in self.positives if item.pattern_fired)

    @property
    def false_negatives(self) -> int:
        return len(self.positives) - self.true_positives

    @property
    def false_positives(self) -> int:
        """Negatives flagged, plus boundary cases when the scope includes them."""

        count = sum(1 for item in self.negatives if item.pattern_fired)
        if self.scope == "category":
            count += sum(1 for item in self.boundary if item.pattern_fired)
        return count

    @property
    def true_negatives(self) -> int:
        count = sum(1 for item in self.negatives if not item.pattern_fired)
        if self.scope == "category":
            count += sum(1 for item in self.boundary if not item.pattern_fired)
        return count

    @property
    def recall(self) -> float:
        total = len(self.positives)
        return round(self.true_positives / total, 4) if total else 0.0

    @property
    def false_positive_rate(self) -> float:
        negative_total = len(self.negatives) + (
            len(self.boundary) if self.scope == "category" else 0
        )
        return (
            round(self.false_positives / negative_total, 4) if negative_total else 0.0
        )

    @property
    def precision(self) -> float:
        denominator = self.true_positives + self.false_positives
        return round(self.true_positives / denominator, 4) if denominator else 0.0

    # -- old evaluator ----------------------------------------------------

    @property
    def old_true_positives(self) -> int:
        return sum(1 for item in self.positives if item.old_fired)

    @property
    def old_false_negatives(self) -> int:
        return len(self.positives) - self.old_true_positives

    @property
    def old_false_positives(self) -> int:
        count = sum(1 for item in self.negatives if item.old_fired)
        if self.scope == "category":
            count += sum(1 for item in self.boundary if item.old_fired)
        return count

    @property
    def old_recall(self) -> float:
        total = len(self.positives)
        return round(self.old_true_positives / total, 4) if total else 0.0

    @property
    def miss_reduction(self) -> int:
        """False negatives removed on positive cases."""

        return self.old_false_negatives - self.false_negatives

    @property
    def miss_reduction_rate(self) -> float:
        base = self.old_false_negatives
        return round(self.miss_reduction / base, 4) if base else 0.0

    def by_form(self) -> Mapping[str, Mapping[str, int]]:
        buckets: dict[str, dict[str, int]] = {}
        for item in self.positives:
            for form in item.case.forms:
                bucket = buckets.setdefault(
                    form, {"cases": 0, "pattern": 0, "old": 0}
                )
                bucket["cases"] += 1
                bucket["pattern"] += int(item.pattern_fired)
                bucket["old"] += int(item.old_fired)
        return dict(sorted(buckets.items()))

    def fixed_cases(self) -> tuple[CaseOutcome, ...]:
        return tuple(item for item in self.outcomes if item.transition == "fixed")

    def broken_cases(self) -> tuple[CaseOutcome, ...]:
        return tuple(item for item in self.outcomes if item.transition == "broken")

    def remaining_errors(self) -> tuple[CaseOutcome, ...]:
        return tuple(item for item in self.outcomes if not item.category_correct)

    def as_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "cases": len(self._in_scope()),
            "positives": len(self.positives),
            "negatives": len(self.negatives),
            "boundary": len(self.boundary),
            "recall": self.recall,
            "old_recall": self.old_recall,
            "true_positives": self.true_positives,
            "false_negatives": self.false_negatives,
            "false_positives": self.false_positives,
            "false_positive_rate": self.false_positive_rate,
            "precision": self.precision,
            "old_true_positives": self.old_true_positives,
            "old_false_negatives": self.old_false_negatives,
            "old_false_positives": self.old_false_positives,
            "miss_reduction": self.miss_reduction,
            "miss_reduction_rate": self.miss_reduction_rate,
            "fixed_cases": [item.case_id for item in self.fixed_cases()],
            "broken_cases": [item.case_id for item in self.broken_cases()],
            "remaining_errors": [item.case_id for item in self.remaining_errors()],
            "by_form": {k: dict(v) for k, v in self.by_form().items()},
        }

    def render(self) -> str:
        lines = [
            f"scope            : {self.scope}",
            f"cases            : {len(self._in_scope())} "
            f"({len(self.positives)} positive, {len(self.negatives)} negative, "
            f"{len(self.boundary)} boundary)",
            "",
            f"{'':26}{'old':>10}{'pattern':>10}",
            f"{'recall':26}{self.old_recall:>10.4f}{self.recall:>10.4f}",
            f"{'false positives':26}{self.old_false_positives:>10}{self.false_positives:>10}",
            f"{'false negatives':26}{self.old_false_negatives:>10}{self.false_negatives:>10}",
            "",
            f"miss reduction   : {self.miss_reduction} ({self.miss_reduction_rate:.1%})",
            f"fixed            : {[item.case_id for item in self.fixed_cases()]}",
            f"broken           : {[item.case_id for item in self.broken_cases()]}",
            f"remaining errors : {[item.case_id for item in self.remaining_errors()]}",
        ]
        return "\n".join(lines)


def run_benchmark(
    cases: Sequence[PatternBenchmarkCase] | None = None,
    *,
    matcher: RelationMatcher | None = None,
) -> tuple[PatternMetrics, PatternMetrics]:
    """Both scoring views over the benchmark."""

    active = tuple(cases) if cases is not None else BENCHMARK_CASES
    active_matcher = matcher if matcher is not None else RelationMatcher(PATTERNS)
    old = SemanticRiskEvaluatorV2()
    old_v1 = SemanticRiskEvaluator()
    outcomes = tuple(
        evaluate_case(case, active_matcher, old=old, old_v1=old_v1) for case in active
    )
    return (
        PatternMetrics(outcomes=outcomes, scope="relation"),
        PatternMetrics(outcomes=outcomes, scope="category"),
    )


def evaluate_patterns(
    cases: Sequence[PatternBenchmarkCase] | None = None,
) -> PatternMetrics:
    """The relation view, which is the pattern layer's own question."""

    return run_benchmark(cases)[0]


def compare_with_old(
    cases: Sequence[PatternBenchmarkCase] | None = None,
) -> Mapping[str, Any]:
    """Old result, new result, per case, with the three required measures."""

    relation, category = run_benchmark(cases)
    return {
        "benchmark": f"{BENCHMARK_NAME}/{BENCHMARK_VERSION}",
        "category": CATEGORY,
        "relation_view": relation.as_dict(),
        "category_view": category.as_dict(),
        "cases": [item.as_dict() for item in relation.outcomes],
    }


# ------------------------------------------------- attribution combination


@dataclass(frozen=True, slots=True)
class CombinationOutcome:
    """One Phase 8.3 case under three stacks."""

    case_id: str
    text: str
    expected: tuple[str, ...]
    baseline: tuple[str, ...]
    attribution_only: tuple[str, ...]
    attribution_plus_pattern: tuple[str, ...]

    def _correct(self, categories: tuple[str, ...]) -> bool:
        return categories == self.expected

    @property
    def baseline_correct(self) -> bool:
        return self._correct(self.baseline)

    @property
    def attribution_correct(self) -> bool:
        return self._correct(self.attribution_only)

    @property
    def combination_correct(self) -> bool:
        return self._correct(self.attribution_plus_pattern)

    @property
    def baseline_missed(self) -> bool:
        return bool(self.expected) and not self.baseline

    @property
    def attribution_missed(self) -> bool:
        return bool(self.expected) and not self.attribution_only

    @property
    def combination_missed(self) -> bool:
        return bool(self.expected) and not self.attribution_plus_pattern

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "text": self.text,
            "expected": list(self.expected),
            "baseline": list(self.baseline),
            "attribution_only": list(self.attribution_only),
            "attribution_plus_pattern": list(self.attribution_plus_pattern),
            "baseline_correct": self.baseline_correct,
            "attribution_correct": self.attribution_correct,
            "combination_correct": self.combination_correct,
        }


def _pattern_result(match: PatternMatch, category: str) -> Any:
    """A result object for a category only the pattern layer found.

    The merge works from evaluator results, so a category with no result object
    is silently dropped however firmly the decision kept it. This makes the
    pattern's finding a first-class result: its `evaluator` field names the
    pattern, so a merged report can still say which layer produced what.
    """

    from ..model import RiskEvaluationResult
    from ..taxonomy import category as taxonomy_category

    entry = taxonomy_category(category)
    kinds = ",".join(match.frame_kinds) or "frame"
    return RiskEvaluationResult(
        category=entry.name,
        intent=entry.intent,
        confidence=match.confidence,
        evidence_required=entry.evidence_required,
        severity=entry.severity,
        action=entry.action,
        evaluator=match.pattern_id,
        detail=(
            f"{entry.name}: relational pattern {match.pattern_id} "
            f"frames={kinds} confidence={match.confidence}"
        ),
        candidates=(entry.name,),
    )


def attribution_combination(
    *,
    matcher: RelationMatcher | None = None,
) -> tuple[CombinationOutcome, ...]:
    """Phase 8.3's cases under baseline, attribution-only, and both layers.

    The attribution column is Phase 8.3's own `AttributionAwareEvaluator`, not a
    reimplementation. That matters: it carries the decision policy the phase
    already measured, including the rule that `unverified_information` survives
    regardless of voice because `taxonomy_v2` says it does. Re-deriving the
    policy here produced a variant that dropped that category and reported four
    spurious misses; reusing the tested one removes the discrepancy rather than
    papering over it.

    The pattern layer runs **per claim**, and its findings go through the same
    decision policy as the baseline's. That second part is not decoration:
    adding pattern findings to the merged result *after* the policy
    reintroduces exactly the false positives Phase 8.3 removed. `We disagree
    with the view that this fund cannot lose money.` is `author/rejected`, the
    pattern layer correctly finds the guarantee relation in it, and R3 is what
    stops that becoming the article's risk. Composing without the policy broke
    two cases; routing through it broke none.
    """

    from ..attribution_experiment.decision import STRICT, decide_claim, merge_results
    from ..attribution_experiment.evaluator import AttributionAwareEvaluator

    active_matcher = matcher if matcher is not None else RelationMatcher(PATTERNS)
    evaluator = AttributionAwareEvaluator()
    pattern = PATTERNS.patterns[0]

    from ..attribution_experiment.cases import EXPERIMENT_CASES

    outcomes: list[CombinationOutcome] = []
    for case in EXPERIMENT_CASES:
        result = evaluator.evaluate(case.text)

        decisions = []
        per_claim: dict[str, tuple[Any, ...]] = {}
        for claim in result.attribution.claims:
            results = list(result.claim_results.get(claim.claim_id, ()))
            detected = {item.category for item in results}
            match = active_matcher.match_pattern(claim.text, pattern)
            if match.fired and CATEGORY not in detected:
                results.append(_pattern_result(match, CATEGORY))
                detected.add(CATEGORY)
            per_claim[claim.claim_id] = tuple(results)
            decisions.append(decide_claim(claim, sorted(detected), policy=STRICT))
        merged = merge_results(decisions, per_claim)
        combined = tuple(sorted({item.category for item in merged}))

        outcomes.append(
            CombinationOutcome(
                case_id=case.case_id,
                text=case.text,
                expected=case.expected_categories,
                baseline=result.baseline_categories,
                attribution_only=result.categories,
                attribution_plus_pattern=combined,
            )
        )
    return tuple(outcomes)


def combination_summary(
    outcomes: Sequence[CombinationOutcome],
) -> Mapping[str, Any]:
    return {
        "cases": len(outcomes),
        "baseline_misses": sum(1 for item in outcomes if item.baseline_missed),
        "attribution_misses": sum(1 for item in outcomes if item.attribution_missed),
        "combination_misses": sum(
            1 for item in outcomes if item.combination_missed
        ),
        "baseline_correct": sum(1 for item in outcomes if item.baseline_correct),
        "attribution_correct": sum(1 for item in outcomes if item.attribution_correct),
        "combination_correct": sum(1 for item in outcomes if item.combination_correct),
        "changed_by_pattern": [
            item.case_id
            for item in outcomes
            if item.attribution_plus_pattern != item.attribution_only
        ],
    }


# ------------------------------------------------------------- artifacts


def benchmark_payload(
    cases: Sequence[PatternBenchmarkCase] | None = None,
) -> dict[str, Any]:
    active = tuple(cases) if cases is not None else BENCHMARK_CASES
    return {
        "benchmark": BENCHMARK_NAME,
        "version": BENCHMARK_VERSION,
        "category": CATEGORY,
        "case_count": len(active),
        "groups": dict(group_sizes(active)),
        "required_group_sizes": dict(REQUIRED_GROUP_SIZES),
        "form_coverage": dict(form_coverage(active)),
        "cases": [case.as_dict() for case in active],
    }


def write_benchmark(path: str | Path | None = None) -> Path:
    target = Path(path) if path is not None else BENCHMARK_PATH
    target.write_text(
        json.dumps(benchmark_payload(), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    return target


def write_comparison(path: str | Path | None = None) -> Path:
    target = Path(path) if path is not None else COMPARISON_PATH
    payload = {
        **compare_with_old(),
        "combination": combination_summary(attribution_combination()),
        "note": (
            "Boundary cases contain the relation but are not the article's "
            "guarantee, so they are excluded from the relation view and counted "
            "as benign in the category view."
        ),
    }
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    import sys

    print(f"{BENCHMARK_NAME}/{BENCHMARK_VERSION}")
    for group, size in group_sizes().items():
        required = REQUIRED_GROUP_SIZES[group]
        mark = "ok" if size >= required else "SHORT"
        print(f"  {group:10} {size:3} / {required:3} {mark}")
    print(f"  total      {len(BENCHMARK_CASES):3}")
    print(f"  forms      {dict(form_coverage())}")
    print()
    relation, category = run_benchmark()
    print("=== relation view ===")
    print(relation.render())
    print()
    print("=== category view (boundary counted as benign) ===")
    print(category.render())
    print()
    print("=== attribution combination (Phase 8.3 cases) ===")
    print(json.dumps(combination_summary(attribution_combination()), indent=2))
    if "--write" in sys.argv:
        print()
        print(f"wrote {write_benchmark()}")
        print(f"wrote {write_comparison()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
