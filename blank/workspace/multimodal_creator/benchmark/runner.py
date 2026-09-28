"""Benchmark harness for the M2 prototype.

Runs the 30 synthetic cases plus a template-discovery scenario and reports what
actually happened. It measures **protocol and algorithm behaviour** — did the
extractor report the declared structure, did the similarity contract rank the
labeled pairs in the expected direction, did discovery group them without being
told the groups, did the cross-modal geometry come out as declared.

It does not measure model accuracy, because there is no model. A pass means the
prototype behaves as specified on controlled input; it says nothing about
performance on real posts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..clustering.template_discovery import (
    DEFAULT_SIMILARITY_THRESHOLD,
    TemplateDiscovery,
    discover_templates,
)
from ..extraction.cross_modal_candidates import candidates_from_sample
from ..extraction.mock_vision_extractor import MockVisionExtractor
from ..extraction.observation_producer import ObservationProducer
from ..similarity.similarity_contract import pairwise_similarity
from .cases import (
    BenchmarkSuite,
    CrossModalCase,
    LayoutCase,
    SimilarityCase,
)


@dataclass(frozen=True, slots=True)
class CaseResult:
    """The outcome of one benchmark case."""

    case_id: str
    group: str
    passed: bool
    failures: tuple[str, ...] = ()
    observed: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "group": self.group,
            "passed": self.passed,
            "failures": list(self.failures),
            "observed": dict(self.observed),
        }

    def render(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        line = f"[{status}] {self.case_id}"
        if self.failures:
            line += "\n        " + "\n        ".join(self.failures)
        return line


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    """Aggregate benchmark outcome."""

    results: tuple[CaseResult, ...]
    discovery: TemplateDiscovery
    threshold: float

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for result in self.results if result.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def ok(self) -> bool:
        return self.failed == 0

    def failures(self) -> tuple[CaseResult, ...]:
        return tuple(result for result in self.results if not result.passed)

    def by_group(self) -> dict[str, tuple[int, int]]:
        groups: dict[str, list[int]] = {}
        for result in self.results:
            passed, total = groups.get(result.group, [0, 0])
            groups[result.group] = [passed + (1 if result.passed else 0), total + 1]
        return {name: (counts[0], counts[1]) for name, counts in sorted(groups.items())}

    def as_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": "m2.0.0",
            "threshold": self.threshold,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "ok": self.ok,
            "by_group": {
                name: {"passed": passed, "total": total}
                for name, (passed, total) in self.by_group().items()
            },
            "cases": [result.as_dict() for result in self.results],
            "discovery": self.discovery.as_dict(),
        }

    def render(self) -> str:
        lines = [
            f"M2 prototype benchmark — {self.passed}/{self.total} cases passed "
            f"(threshold={self.threshold})",
        ]
        for name, (passed, total) in self.by_group().items():
            lines.append(f"  {name}: {passed}/{total}")
        if self.failures():
            lines.append("")
            lines.extend(result.render() for result in self.failures())
        lines.append("")
        lines.append(self.discovery.summarise())
        return "\n".join(lines)


def _run_layout_case(case: LayoutCase, extractor: MockVisionExtractor) -> CaseResult:
    failures: list[str] = []
    observation = extractor.extract(case.sample)

    if observation.layout_template_class != case.expected_layout_class:
        failures.append(
            f"layout class: expected {case.expected_layout_class!r}, "
            f"got {observation.layout_template_class!r}"
        )

    # Sorted with duplicates: region roles are a multiset. A three-card layout
    # has three ``body`` regions, and collapsing that to a set would hide the
    # very structure the case exists to check.
    observed_roles = tuple(sorted(region["role"] for region in observation.regions))
    if observed_roles != tuple(sorted(case.expected_region_roles)):
        failures.append(
            f"region roles: expected {sorted(case.expected_region_roles)}, "
            f"got {list(observed_roles)}"
        )

    text_count = len(case.sample.text_regions())
    visual_count = len(case.sample.visual_regions())
    if text_count != case.expected_text_region_count:
        failures.append(
            f"text region count: expected {case.expected_text_region_count}, got {text_count}"
        )
    if visual_count != case.expected_visual_region_count:
        failures.append(
            f"visual region count: expected {case.expected_visual_region_count}, "
            f"got {visual_count}"
        )
    if text_count + visual_count > len(observation.regions):
        failures.append("region role partition is inconsistent")

    candidates = candidates_from_sample(case.sample)
    observed_anchor = candidates[0].visual_role if candidates else None
    if case.expected_anchor_role is None:
        if candidates:
            failures.append(
                f"expected no cross-modal candidate, got anchor {observed_anchor!r}"
            )
    elif observed_anchor != case.expected_anchor_role:
        failures.append(
            f"cross-modal anchor: expected {case.expected_anchor_role!r}, "
            f"got {observed_anchor!r}"
        )

    for role in case.expected_roles_include:
        if role not in observation.roles:
            failures.append(f"expected role {role!r} missing from {list(observation.roles)}")
    for kind in case.expected_evidence_include:
        if kind not in observation.evidence_kinds:
            failures.append(
                f"expected evidence {kind!r} missing from {list(observation.evidence_kinds)}"
            )
    if "ocr_text" in observation.evidence_kinds:
        failures.append("observation claims ocr_text; anti-OCR boundary breached")

    return CaseResult(
        case_id=case.case_id,
        group="layout",
        passed=not failures,
        failures=tuple(failures),
        observed={
            "layout_class": observation.layout_template_class,
            "region_roles": list(observed_roles),
            "anchor_role": observed_anchor,
            "evidence_kind_count": len(observation.evidence_kinds),
        },
    )


def _run_similarity_case(case: SimilarityCase) -> CaseResult:
    failures: list[str] = []
    result = pairwise_similarity(case.left, case.right)
    score = result.score

    if not result.comparable:
        failures.append(f"pair not comparable: {result.suppressed_reason}")

    if case.same_family:
        if case.expected_min_score is not None and score < case.expected_min_score:
            failures.append(
                f"same-family score {score:.4f} below expected minimum "
                f"{case.expected_min_score:.4f}"
            )
        if score < DEFAULT_SIMILARITY_THRESHOLD:
            failures.append(
                f"same-family score {score:.4f} below discovery threshold "
                f"{DEFAULT_SIMILARITY_THRESHOLD}"
            )
    else:
        if case.expected_max_score is not None and score > case.expected_max_score:
            failures.append(
                f"different-family score {score:.4f} above expected maximum "
                f"{case.expected_max_score:.4f}"
            )

    for code in case.expected_codes_include:
        if code not in result.codes():
            failures.append(
                f"expected difference code {code!r} missing from {list(result.codes())}"
            )

    decomposition = sum(item.weighted_score for item in result.contributions)
    if abs(decomposition - score) > 1e-6:
        failures.append(
            f"score {score} is not the sum of its weighted contributions {decomposition}"
        )

    return CaseResult(
        case_id=case.case_id,
        group="template_similarity",
        passed=not failures,
        failures=tuple(failures),
        observed={
            "score": score,
            "same_family": case.same_family,
            "dimensions": {item.dimension: item.score for item in result.dimensions},
            "codes": list(result.codes()),
        },
    )


def _run_cross_modal_case(case: CrossModalCase) -> CaseResult:
    failures: list[str] = []
    candidates = candidates_from_sample(case.sample)

    if not candidates:
        failures.append("no cross-modal candidate produced")
        return CaseResult(
            case_id=case.case_id,
            group="cross_modal_alignment",
            passed=False,
            failures=tuple(failures),
        )

    candidate = candidates[0]
    if candidate.geometric_relation != case.expected_geometric_relation:
        failures.append(
            f"geometric relation: expected {case.expected_geometric_relation!r}, "
            f"got {candidate.geometric_relation!r}"
        )
    if candidate.relation != case.expected_semantic_relation:
        failures.append(
            f"semantic relation: expected {case.expected_semantic_relation!r}, "
            f"got {candidate.relation!r}"
        )
    if candidate.visual_role != case.expected_anchor_role:
        failures.append(
            f"anchor role: expected {case.expected_anchor_role!r}, "
            f"got {candidate.visual_role!r}"
        )
    if candidate.declared != case.declared:
        failures.append(
            f"declared flag: expected {case.declared}, got {candidate.declared}"
        )
    if not candidate.text_region_id or not candidate.visual_region_id:
        failures.append("candidate is missing one of its two anchors")

    return CaseResult(
        case_id=case.case_id,
        group="cross_modal_alignment",
        passed=not failures,
        failures=tuple(failures),
        observed={
            "geometric_relation": candidate.geometric_relation,
            "semantic_relation": candidate.relation,
            "anchor_role": candidate.visual_role,
            "declared": candidate.declared,
        },
    )


def run_benchmark(
    suite: BenchmarkSuite | None = None,
    *,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    provenance_mode: str = "cross_provenance",
) -> BenchmarkReport:
    """Run every case and the discovery scenario.

    Discovery runs over every sample in the suite at once, which is the real
    test: the clustering must recover the labeled groupings without ever being
    shown a label.
    """

    active = suite or BenchmarkSuite()
    extractor = MockVisionExtractor()

    results: list[CaseResult] = []
    for layout_case in active.layouts:
        results.append(_run_layout_case(layout_case, extractor))
    for similarity_case in active.similarities:
        results.append(_run_similarity_case(similarity_case))
    for cross_case in active.cross_modal:
        results.append(_run_cross_modal_case(cross_case))

    discovery = discover_templates(
        active.all_samples(), threshold=threshold, provenance_mode=provenance_mode
    )
    return BenchmarkReport(
        results=tuple(results), discovery=discovery, threshold=threshold
    )


def discovery_agreement(report: BenchmarkReport, suite: BenchmarkSuite) -> dict[str, Any]:
    """Check the discovered clusters against the similarity cases' labels.

    This is deliberately a *separate* function from :func:`run_benchmark`: the
    clustering must not see the labels, so the labels are only used here, after
    discovery has already run, to score it.
    """

    same_family_pairs = [
        (case.left.sample_id, case.right.sample_id)
        for case in suite.similarities
        if case.same_family
    ]
    different_pairs = [
        (case.left.sample_id, case.right.sample_id)
        for case in suite.similarities
        if not case.same_family
    ]

    def same_cluster(left: str, right: str) -> bool:
        try:
            return report.discovery.cluster_for(left).cluster_id == report.discovery.cluster_for(
                right
            ).cluster_id
        except Exception:
            return False

    correct = sum(1 for left, right in same_family_pairs if same_cluster(left, right))
    wrong = sum(1 for left, right in different_pairs if same_cluster(left, right))
    return {
        "same_family_pairs": len(same_family_pairs),
        "same_family_grouped": correct,
        "different_family_pairs": len(different_pairs),
        "different_family_merged": wrong,
        "agreement": round(
            (correct + (len(different_pairs) - wrong))
            / max(1, len(same_family_pairs) + len(different_pairs)),
            6,
        ),
    }


def render_report(report: BenchmarkReport) -> str:
    """Render the benchmark plus its label-agreement score."""

    lines = [report.render(), "", "discovery vs labels:"]
    agreement = discovery_agreement(report, BenchmarkSuite())
    for key, value in agreement.items():
        lines.append(f"  {key}: {value}")
    return "\n".join(lines)


__all__ = [
    "BenchmarkReport",
    "CaseResult",
    "discovery_agreement",
    "render_report",
    "run_benchmark",
]
