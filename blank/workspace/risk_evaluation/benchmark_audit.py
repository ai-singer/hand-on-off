"""Benchmark contamination audit.

Three checks, each answering a different way a benchmark can be unfair:

1. **exact duplicate** — the same text twice inside one benchmark. Inflates the
   weight of whatever the duplicated case happens to test.
2. **near duplicate** — two cases that differ only in punctuation or a word, so
   they measure the same thing twice.
3. **development overlap** — a case whose text also appears in the benchmark
   that was used to design the evaluator. This is the contamination Phase 7.3
   discovered after the fact.

The audit is deliberately harsh: any finding makes the benchmark's status
`FAIL`. Detecting contamination is the whole point, so a report that found
something and still passed would be useless.

Near-duplicate detection uses token-set Jaccard similarity with a documented
threshold rather than an embedding model, so it is deterministic, dependency
free and inspectable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from .benchmark import BENCHMARK_CASES
from .benchmark_registry import BenchmarkRecord, BenchmarkRegistry


#: Jaccard similarity at or above this value counts as a near duplicate.
NEAR_DUPLICATE_THRESHOLD = 0.8

EXACT_DUPLICATE = "exact_duplicate"
NEAR_DUPLICATE = "near_duplicate"
DEVELOPMENT_OVERLAP = "development_overlap"

FINDING_KINDS = (EXACT_DUPLICATE, NEAR_DUPLICATE, DEVELOPMENT_OVERLAP)

PASS = "PASS"
FAIL = "FAIL"

_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+", re.UNICODE)


def normalize_text(text: str) -> str:
    """Casefold, drop punctuation and collapse whitespace."""

    without_punctuation = _PUNCTUATION.sub(" ", text.casefold())
    return _WHITESPACE.sub(" ", without_punctuation).strip()


def token_set(text: str) -> frozenset[str]:
    normalized = normalize_text(text)
    return frozenset(normalized.split())


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    if not union:
        return 0.0
    return round(len(left & right) / len(union), 4)


@dataclass(frozen=True, slots=True)
class ContaminationFinding:
    kind: str
    case_ids: tuple[str, ...]
    detail: str
    similarity: float | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind,
            "case_ids": list(self.case_ids),
            "detail": self.detail,
        }
        if self.similarity is not None:
            payload["similarity"] = self.similarity
        return payload


@dataclass(frozen=True, slots=True)
class ContaminationReport:
    benchmark_id: str
    version: str
    case_count: int
    dataset_hash: str
    findings: tuple[ContaminationFinding, ...]

    @property
    def contaminated(self) -> bool:
        return bool(self.findings)

    @property
    def status(self) -> str:
        return FAIL if self.contaminated else PASS

    @property
    def affected_case_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted({case_id for item in self.findings for case_id in item.case_ids})
        )

    def counts(self) -> Mapping[str, int]:
        counts = {kind: 0 for kind in FINDING_KINDS}
        for item in self.findings:
            counts[item.kind] = counts.get(item.kind, 0) + 1
        return counts

    def as_dict(self) -> dict[str, Any]:
        return {
            "benchmark_id": self.benchmark_id,
            "version": self.version,
            "case_count": self.case_count,
            "dataset_hash": self.dataset_hash,
            "status": self.status,
            "counts": dict(self.counts()),
            "affected_case_count": len(self.affected_case_ids),
            "findings": [item.as_dict() for item in self.findings],
        }

    def render(self) -> str:
        lines = [
            f"benchmark      : {self.benchmark_id}/{self.version}",
            f"cases          : {self.case_count}",
            f"dataset hash   : {self.dataset_hash[:16]}",
            f"status         : {self.status}",
        ]
        if not self.contaminated:
            lines.append("no contamination detected")
            return "\n".join(lines)
        lines.append(f"findings       : {len(self.findings)}")
        for kind, count in sorted(self.counts().items()):
            if count:
                lines.append(f"  {kind:22} {count}")
        lines.append(f"affected cases : {len(self.affected_case_ids)}")
        return "\n".join(lines)


def development_texts() -> frozenset[str]:
    """Normalized texts of the benchmark used to design the evaluators."""

    return frozenset(normalize_text(case.text) for case in BENCHMARK_CASES)


def audit_records(
    records: Sequence[Mapping[str, Any]],
    *,
    benchmark_id: str,
    version: str,
    dataset_hash: str = "",
    development: Iterable[str] | None = None,
    near_duplicate_threshold: float = NEAR_DUPLICATE_THRESHOLD,
) -> ContaminationReport:
    """Run all three checks over annotation records."""

    known = (
        frozenset(normalize_text(text) for text in development)
        if development is not None
        else development_texts()
    )

    findings: list[ContaminationFinding] = []
    normalized: dict[str, str] = {}
    tokens: dict[str, frozenset[str]] = {}

    for record in records:
        case_id = str(record["id"])
        text = str(record["text"])
        normalized[case_id] = normalize_text(text)
        tokens[case_id] = token_set(text)

    ordered = [str(record["id"]) for record in records]

    # 1. exact duplicates inside the benchmark
    seen: dict[str, list[str]] = {}
    for case_id in ordered:
        seen.setdefault(normalized[case_id], []).append(case_id)
    for text, case_ids in seen.items():
        if len(case_ids) > 1:
            findings.append(
                ContaminationFinding(
                    EXACT_DUPLICATE,
                    tuple(case_ids),
                    f"{len(case_ids)} cases share identical normalized text",
                    1.0,
                )
            )

    # 2. near duplicates inside the benchmark
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            if normalized[left] == normalized[right]:
                continue  # already reported as an exact duplicate
            similarity = jaccard(tokens[left], tokens[right])
            if similarity >= near_duplicate_threshold:
                findings.append(
                    ContaminationFinding(
                        NEAR_DUPLICATE,
                        (left, right),
                        f"token Jaccard {similarity:.2f} at or above "
                        f"{near_duplicate_threshold:.2f}",
                        similarity,
                    )
                )

    # 3. overlap with the evaluator development benchmark
    for case_id in ordered:
        if normalized[case_id] in known:
            findings.append(
                ContaminationFinding(
                    DEVELOPMENT_OVERLAP,
                    (case_id,),
                    "text also appears in the evaluator development benchmark",
                    1.0,
                )
            )

    return ContaminationReport(
        benchmark_id=benchmark_id,
        version=version,
        case_count=len(records),
        dataset_hash=dataset_hash,
        findings=tuple(findings),
    )


def audit_benchmark(
    record: BenchmarkRecord,
    registry: BenchmarkRegistry | None = None,
    *,
    development: Iterable[str] | None = None,
) -> ContaminationReport:
    """Audit one registered version."""

    active = registry if registry is not None else BenchmarkRegistry()
    return audit_records(
        active.load_records(record),
        benchmark_id=record.benchmark_id,
        version=record.version,
        dataset_hash=record.dataset_hash,
        development=development,
    )


def audit_all(
    registry: BenchmarkRegistry | None = None,
) -> Mapping[str, ContaminationReport]:
    active = registry if registry is not None else BenchmarkRegistry()
    return {
        f"{record.benchmark_id}/{record.version}": audit_benchmark(record, active)
        for record in active.list_benchmarks()
    }


def main() -> int:
    reports = audit_all()
    exit_code = 0
    for name, report in reports.items():
        print(f"=== {name} ===")
        print(report.render())
        print()
        if report.status == FAIL:
            exit_code = 1
    failing = [name for name, report in reports.items() if report.status == FAIL]
    print("contaminated benchmarks:", failing or "none")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
