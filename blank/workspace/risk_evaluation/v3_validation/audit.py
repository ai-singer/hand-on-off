"""Benchmark audit: is `independent_v1` actually independent?

Four checks, and any finding is a FAIL:

    exact overlap        a case whose normalized text appears in an earlier set
    near duplicate       two cases within this set, or against an earlier set,
                         above the Jaccard threshold
    development overlap  text reused from the evaluator or layer development sets
    label completeness   a case missing a label field, or naming an unknown one

The audit does not repair anything. A contaminated benchmark is reported as
contaminated and the phase forbids deleting the contaminated cases and
recomputing; the only honest responses are to publish a decontaminated subset
alongside, as Phase 7.4 did for v1, or to fail.

The historical sets audited against are read from the artifacts the earlier
phases published - `semantic/adversarial/v1` through the registry, Phase 8.2's
annotation set, Phase 8.3's experiment dataset, Phase 8.4's pattern benchmark
and Phase 8.5's composition benchmark - so the check uses what was actually
published rather than a list someone remembered to write down.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ..taxonomy import RISK_TAXONOMY
from .cases import CASES, ValidationCase


AUDIT_PATH = Path(__file__).resolve().parent / "audit_report.json"

EXACT_OVERLAP = "exact_overlap"
NEAR_DUPLICATE = "near_duplicate"
DEVELOPMENT_OVERLAP = "development_overlap"
LABEL_INCOMPLETE = "label_incomplete"
FINDING_KINDS = (
    EXACT_OVERLAP,
    NEAR_DUPLICATE,
    DEVELOPMENT_OVERLAP,
    LABEL_INCOMPLETE,
)

PASS = "PASS"
FAIL = "FAIL"

#: Same threshold Phase 7.4 used, so the two audits are comparable.
NEAR_DUPLICATE_THRESHOLD = 0.8

#: Label fields every case must carry.
REQUIRED_LABEL_FIELDS = ("claims", "speakers", "stances", "relations", "categories")

_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+", re.UNICODE)


def normalize_text(text: str) -> str:
    lowered = _PUNCTUATION.sub(" ", text.lower())
    return _WHITESPACE.sub(" ", lowered).strip()


def token_set(text: str) -> frozenset[str]:
    return frozenset(normalize_text(text).split())


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


@dataclass(frozen=True, slots=True)
class Finding:
    kind: str
    case_ids: tuple[str, ...]
    detail: str
    source: str = ""
    similarity: float | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind,
            "case_ids": list(self.case_ids),
            "detail": self.detail,
            "source": self.source,
        }
        if self.similarity is not None:
            payload["similarity"] = round(self.similarity, 4)
        return payload


def historical_texts() -> Mapping[str, tuple[str, ...]]:
    """Every text published by an earlier phase, keyed by its source."""

    sources: dict[str, list[str]] = {}

    # Phase 7.3/7.4/7.5 and 8.1, through the registry: what was published.
    from ..benchmark_registry import BenchmarkRegistry

    registry = BenchmarkRegistry()
    for record in registry.list_benchmarks():
        key = f"{record.benchmark_id}/{record.version}"
        sources[key] = [str(item["text"]) for item in registry.load_records(record)]

    # Phase 8.2's annotation set.
    from ..attribution.evaluation import ANNOTATION_CASES, COVERAGE_PROBES

    sources["phase-8.2/annotation"] = [row.text for row in ANNOTATION_CASES]
    sources["phase-8.2/coverage-probe"] = [row.text for row in COVERAGE_PROBES]

    # Phase 8.3's experiment dataset.
    from ..attribution_experiment.cases import EXPERIMENT_CASES, REPLAY_CASES

    sources["phase-8.3/experiment"] = [case.text for case in EXPERIMENT_CASES]
    sources["phase-8.3/replay"] = [case.text for case in REPLAY_CASES]

    # Phase 8.4's pattern benchmark.
    from ..intent_patterns.evaluation import BENCHMARK_CASES as PATTERN_CASES

    sources["phase-8.4/intent-pattern"] = [case.text for case in PATTERN_CASES]

    # Phase 8.5's composition benchmark.
    from ..v3.benchmark.cases import BENCHMARK_CASES as V3_CASES

    sources["phase-8.5/composition"] = [case.text for case in V3_CASES]

    # The evaluator and layer development sets.
    from ..benchmark import BENCHMARK_CASES as DEVELOPMENT_CASES
    from ..independent_benchmark import INDEPENDENT_CASES

    sources["development/risk-evaluation"] = [case.text for case in DEVELOPMENT_CASES]
    sources["development/independent"] = [case.text for case in INDEPENDENT_CASES]

    return {name: tuple(texts) for name, texts in sources.items()}


@dataclass(frozen=True, slots=True)
class AuditReport:
    benchmark: str
    case_count: int
    dataset_hash: str
    findings: tuple[Finding, ...]
    sources_checked: tuple[str, ...]
    threshold: float = NEAR_DUPLICATE_THRESHOLD

    @property
    def passed(self) -> bool:
        return not self.findings

    @property
    def status(self) -> str:
        return PASS if self.passed else FAIL

    def counts(self) -> Mapping[str, int]:
        counts = {kind: 0 for kind in FINDING_KINDS}
        for item in self.findings:
            counts[item.kind] = counts.get(item.kind, 0) + 1
        return counts

    @property
    def affected_case_ids(self) -> tuple[str, ...]:
        return tuple(sorted({cid for f in self.findings for cid in f.case_ids}))

    def of_kind(self, kind: str) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.kind == kind)

    def as_dict(self) -> dict[str, Any]:
        return {
            "benchmark": self.benchmark,
            "case_count": self.case_count,
            "dataset_hash": self.dataset_hash,
            "status": self.status,
            "threshold": self.threshold,
            "counts": dict(self.counts()),
            "affected_case_count": len(self.affected_case_ids),
            "sources_checked": list(self.sources_checked),
            "findings": [f.as_dict() for f in self.findings],
        }

    def render(self) -> str:
        lines = [
            f"benchmark      : {self.benchmark}",
            f"cases          : {self.case_count}",
            f"dataset hash   : {self.dataset_hash[:16]}",
            f"sources checked: {len(self.sources_checked)}",
            f"status         : {self.status}",
        ]
        if self.passed:
            lines.append("no contamination detected")
            return "\n".join(lines)
        lines.append(f"findings       : {len(self.findings)}")
        for kind, count in sorted(self.counts().items()):
            if count:
                lines.append(f"  {kind:22} {count}")
        lines.append(f"affected cases : {len(self.affected_case_ids)}")
        return "\n".join(lines)


def _label_findings(case: ValidationCase) -> list[Finding]:
    payload = case.as_dict()["labels"]
    missing = [name for name in REQUIRED_LABEL_FIELDS if name not in payload]
    findings: list[Finding] = []
    if missing:
        findings.append(
            Finding(
                LABEL_INCOMPLETE,
                (case.case_id,),
                f"label fields missing: {missing}",
            )
        )
    known = {entry.name for entry in RISK_TAXONOMY}
    unknown = [name for name in case.categories if name not in known]
    if unknown:
        findings.append(
            Finding(
                LABEL_INCOMPLETE,
                (case.case_id,),
                f"unknown categories: {unknown}",
            )
        )
    if not case.annotation_reason.strip():
        findings.append(
            Finding(LABEL_INCOMPLETE, (case.case_id,), "no annotation reason")
        )
    return findings


def audit(
    cases: Sequence[ValidationCase] | None = None,
    *,
    historical: Mapping[str, Sequence[str]] | None = None,
    threshold: float = NEAR_DUPLICATE_THRESHOLD,
) -> AuditReport:
    """Run all four checks."""

    from ..v3_validation.freeze import dataset_hash

    active = tuple(cases) if cases is not None else CASES
    sources = historical if historical is not None else historical_texts()

    development: dict[str, str] = {}
    for name, texts in sources.items():
        if name.startswith("development/"):
            for text in texts:
                development[normalize_text(text)] = name

    every_other: dict[str, str] = {}
    for name, texts in sources.items():
        if name.startswith("development/"):
            continue
        for text in texts:
            every_other.setdefault(normalize_text(text), name)

    findings: list[Finding] = []
    normalized = {case.case_id: normalize_text(case.text) for case in active}
    tokens = {case.case_id: token_set(case.text) for case in active}
    ordered = [case.case_id for case in active]

    # 1. exact overlap with anything published earlier
    for case_id in ordered:
        source = every_other.get(normalized[case_id])
        if source:
            findings.append(
                Finding(
                    EXACT_OVERLAP,
                    (case_id,),
                    "text also appears verbatim in an earlier benchmark",
                    source=source,
                    similarity=1.0,
                )
            )

    # 2. near duplicates, within this set and against earlier ones
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            if normalized[left] == normalized[right]:
                continue
            similarity = jaccard(tokens[left], tokens[right])
            if similarity >= threshold:
                findings.append(
                    Finding(
                        NEAR_DUPLICATE,
                        (left, right),
                        f"token Jaccard {similarity:.2f} within the benchmark",
                        source="independent_v1",
                        similarity=similarity,
                    )
                )

    for case_id in ordered:
        for name, texts in sources.items():
            if name.startswith("development/"):
                continue
            for text in texts:
                other = token_set(text)
                if normalized[case_id] == normalize_text(text):
                    continue  # already reported as an exact overlap
                similarity = jaccard(tokens[case_id], other)
                if similarity >= threshold:
                    findings.append(
                        Finding(
                            NEAR_DUPLICATE,
                            (case_id,),
                            f"token Jaccard {similarity:.2f} against an earlier benchmark",
                            source=name,
                            similarity=similarity,
                        )
                    )

    # 3. development-set overlap
    for case_id in ordered:
        source = development.get(normalized[case_id])
        if source:
            findings.append(
                Finding(
                    DEVELOPMENT_OVERLAP,
                    (case_id,),
                    "text appears in a development set",
                    source=source,
                    similarity=1.0,
                )
            )

    # 4. label completeness
    for case in active:
        findings.extend(_label_findings(case))

    return AuditReport(
        benchmark="independent_v1",
        case_count=len(active),
        dataset_hash=dataset_hash(active),
        findings=tuple(findings),
        sources_checked=tuple(sorted(sources)),
        threshold=threshold,
    )


def write_report(path: str | Path | None = None, report: AuditReport | None = None) -> Path:
    target = Path(path) if path is not None else AUDIT_PATH
    active = report if report is not None else audit()
    payload = {
        **active.as_dict(),
        "note": (
            "A finding is a FAIL. The phase forbids deleting contaminated cases "
            "and recomputing, so nothing is repaired here."
        ),
    }
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    import sys

    report = audit()
    print(report.render())
    if not report.passed:
        print()
        for finding in report.findings:
            print(f"  {finding.kind}: {finding.case_ids} ({finding.source}) {finding.detail}")
    if "--write" in sys.argv:
        print()
        print(f"wrote {write_report(report=report)}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
