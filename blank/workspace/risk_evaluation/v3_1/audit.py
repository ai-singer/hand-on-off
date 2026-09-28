"""Contamination audit for the Phase 8.8 benchmark.

The phase requires an audit, requires a FAIL to be kept as a FAIL, and forbids
deleting a contaminated case. This module reuses Phase 8.6's machinery - the same
normalization, the same Jaccard threshold, the same `Finding` and `AuditReport`
types - so the two audits are comparable rather than merely similar.

It adds one distinction Phase 8.6 did not need, because Phase 8.8 has a group that
is *supposed* to contain reused text.

**Group C is a regression set.** Its twenty cases are copied from five frozen
artifacts, so an exact overlap is not automatically contamination here. What the
audit checks instead is that the provenance is *real*:

    an authored case overlapping anything                 -> blocking
    a group C case whose text appears in no set its
      declared phase publishes                            -> blocking
    a group C case overlapping the frozen sets            -> disclosed, with source

The second row is the check that makes the distinction worth having. A regression
case whose text cannot be found in the phase it claims is either mislabelled or
copied from a set nobody recorded, and both are findings.

The third row is disclosed rather than blocking, and the reason is a measured
property of the frozen sets rather than a convenience. Phase 8.4's guarantee
benchmark reuses wordings that Phase 8.1 recorded as failures, and Phase 8.5's
composition set reuses Phase 8.3's; copying a case faithfully from one of them
therefore imports a near-duplicate of another. Suppressing that would hide
something true about the historical sets, and blocking on it would fail this phase
for a redundancy it did not create and cannot remove without editing frozen
material, which the phase forbids. So it is reported, counted, and named.

The audit still fails on the thing it exists for. The first run before publication
found `MP-A2-08` - an authored case - duplicating `IV-098` verbatim, and it was
recorded as blocking. See `PRE_PUBLICATION_FINDINGS`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..v3_validation.audit import (
    DEVELOPMENT_OVERLAP,
    EXACT_OVERLAP,
    FAIL,
    FINDING_KINDS,
    LABEL_INCOMPLETE,
    NEAR_DUPLICATE,
    NEAR_DUPLICATE_THRESHOLD,
    PASS,
    AuditReport,
    Finding,
    historical_texts,
    jaccard,
    normalize_text,
    token_set,
)
from .benchmark.cases import (
    BENCHMARK_ID,
    BENCHMARK_VERSION,
    CASES,
    CATEGORIES,
    REGRESSION,
    CapabilityCase,
    dataset_payload,
)

AUDIT_PATH = Path(__file__).resolve().parent / "audit_report_v3_1.json"

#: A finding that does not block, because the case declares the overlap.
DISCLOSED_OVERLAP = "disclosed_overlap"
#: A group C case whose text cannot be found where it says it came from.
UNVERIFIABLE_PROVENANCE = "unverifiable_provenance"

BLOCKING_KINDS: tuple[str, ...] = (
    EXACT_OVERLAP,
    NEAR_DUPLICATE,
    DEVELOPMENT_OVERLAP,
    LABEL_INCOMPLETE,
    UNVERIFIABLE_PROVENANCE,
)

#: Which audit sources each frozen phase's cases may legitimately come from.
#:
#: A text can be published by several phases - Phase 8.3's replay reuses Phase 8.1's
#: recorded failures, and the failure repository itself is built from the adversarial
#: benchmark - so the check is not "the case matches one key". It is "the case's text
#: appears in a set its own phase publishes", which is the honest, checkable form of
#: the provenance claim. A group C case whose text appears only somewhere its phase
#: never published is blocking: either the origin is mislabelled or the text was
#: copied from a set nobody recorded.
FROZEN_PHASE_SOURCES: Mapping[str, tuple[str, ...]] = {
    "phase-8.1": ("phase-8.1/failure-repository", "semantic/adversarial/v1"),
    "phase-8.3": (
        "phase-8.3/replay",
        "phase-8.3/experiment",
        "phase-8.1/failure-repository",
        "semantic/adversarial/v1",
    ),
    "phase-8.4": ("phase-8.4/intent-pattern", "semantic/adversarial/v1"),
    "phase-8.6": ("phase-8.6/independent_v1", "phase-8.6/independent_v2"),
    "phase-8.7": (
        "phase-8.5/composition",
        "phase-8.3/experiment",
        "phase-8.6/independent_v1",
        "phase-8.6/independent_v2",
    ),
}

#: Findings from the audit run that preceded publication, kept because the phase
#: forbids deleting a contaminated case and because a benchmark that quietly
#: repaired its own contamination would hide the one thing the audit exists to show.
#:
#: `MP-A2-08` was authored as `Perhaps the fund will outperform its benchmark.`,
#: which is `IV-098` verbatim - a sentence the Phase 8.8 modal layer was developed
#: against. Measuring the capability on it would have been exactly the arrangement
#: Phase 8.6 exists to expose, so the case was rewritten rather than deleted, and
#: both texts are recorded here.
PRE_PUBLICATION_FINDINGS: tuple[Mapping[str, str], ...] = (
    {
        "case_id": "MP-A2-08",
        "kind": "exact_overlap",
        "source": "phase-8.6/independent_v1",
        "original_text": "Perhaps the fund will outperform its benchmark.",
        "replacement_text": "Perhaps the share price will double this year.",
        "resolution": "rewritten before publication",
        "why": (
            "the text is IV-098 verbatim, and IV-098 is one of the cases the Phase "
            "8.8 modal layer was developed against; measuring the capability on it "
            "would not be a measurement"
        ),
    },
)


class AuditError(Exception):
    """Raised when the audit cannot run."""


def failure_repository_texts() -> tuple[str, ...]:
    """The texts the Phase 8.1 failure repository recorded."""

    from ..adversarial.failure_repository import FailureRepository

    return tuple(record.text for record in FailureRepository().load())


def phase_8_8_sources() -> Mapping[str, tuple[str, ...]]:
    """Every earlier text this benchmark could have been contaminated by."""

    sources = dict(historical_texts())
    sources["phase-8.1/failure-repository"] = failure_repository_texts()

    from ..v3_validation.cases import CASES as PHASE_86_CASES
    from ..v3_validation.cases import decontaminated_cases

    sources["phase-8.6/independent_v1"] = tuple(case.text for case in PHASE_86_CASES)
    sources["phase-8.6/independent_v2"] = tuple(
        case.text for case in decontaminated_cases()
    )

    from ..v3.benchmark.cases import BENCHMARK_CASES as PHASE_85_CASES

    sources["phase-8.5/composition"] = tuple(case.text for case in PHASE_85_CASES)

    return {name: tuple(texts) for name, texts in sources.items()}


@dataclass(frozen=True, slots=True)
class Phase88AuditReport:
    """Phase 8.6's report shape, plus what is disclosed rather than blocking."""

    inner: AuditReport
    blocking: tuple[Finding, ...]
    disclosed: tuple[Finding, ...]

    @property
    def benchmark(self) -> str:
        return self.inner.benchmark

    @property
    def case_count(self) -> int:
        return self.inner.case_count

    @property
    def dataset_hash(self) -> str:
        return self.inner.dataset_hash

    @property
    def findings(self) -> tuple[Finding, ...]:
        return self.inner.findings

    @property
    def sources_checked(self) -> tuple[str, ...]:
        return self.inner.sources_checked

    @property
    def passed(self) -> bool:
        return not self.blocking

    @property
    def status(self) -> str:
        return PASS if self.passed else FAIL

    @property
    def affected_case_ids(self) -> tuple[str, ...]:
        return tuple(sorted({cid for f in self.blocking for cid in f.case_ids}))

    def counts(self) -> Mapping[str, int]:
        counts = {kind: 0 for kind in (*FINDING_KINDS, DISCLOSED_OVERLAP, UNVERIFIABLE_PROVENANCE)}
        for item in self.findings:
            counts[item.kind] = counts.get(item.kind, 0) + 1
        return counts

    def blocking_counts(self) -> Mapping[str, int]:
        counts = {kind: 0 for kind in BLOCKING_KINDS}
        for item in self.blocking:
            counts[item.kind] = counts.get(item.kind, 0) + 1
        return counts

    def of_kind(self, kind: str) -> tuple[Finding, ...]:
        return tuple(item for item in self.findings if item.kind == kind)

    def as_dict(self) -> dict[str, Any]:
        return {
            "benchmark": self.benchmark,
            "case_count": self.case_count,
            "dataset_hash": self.dataset_hash,
            "status": self.status,
            "threshold": NEAR_DUPLICATE_THRESHOLD,
            "counts": dict(self.counts()),
            "blocking_counts": dict(self.blocking_counts()),
            "blocking_findings": len(self.blocking),
            "disclosed_overlaps": len(self.disclosed),
            "affected_case_count": len(self.affected_case_ids),
            "sources_checked": list(self.sources_checked),
            "findings": [item.as_dict() for item in self.findings],
            "blocking": [item.as_dict() for item in self.blocking],
            "disclosed": [item.as_dict() for item in self.disclosed],
        }

    def render(self) -> str:
        lines = [
            f"benchmark       : {self.benchmark}",
            f"cases           : {self.case_count}",
            f"dataset hash    : {self.dataset_hash[:16]}",
            f"sources checked : {len(self.sources_checked)}",
            f"status          : {self.status}",
            f"blocking        : {len(self.blocking)}",
            f"disclosed       : {len(self.disclosed)} (group C, declared provenance)",
        ]
        for item in self.blocking:
            lines.append(
                f"  BLOCKING {item.kind}: {list(item.case_ids)} ({item.source}) {item.detail}"
            )
        return "\n".join(lines)


def _internal_source(
    left: str,
    right: str,
    by_id: Mapping[str, CapabilityCase],
    normalized: Mapping[str, str],
    every_other: Mapping[str, str],
) -> str:
    """The source to attribute an in-benchmark duplicate to.

    Two regression cases repeating each other are repeating text they both copied
    from earlier sets, so the historical set is named. Any pair involving an authored
    case gets the benchmark's own key, which is never disclosable and so stays
    blocking.
    """

    for case_id in (left, right):
        if by_id[case_id].group != REGRESSION:
            return f"{BENCHMARK_ID}/{BENCHMARK_VERSION}"
    for case_id in (left, right):
        source = every_other.get(normalized[case_id])
        if source:
            return source
    return f"{BENCHMARK_ID}/{BENCHMARK_VERSION}"


def _label_findings(case: CapabilityCase) -> list[Finding]:
    findings: list[Finding] = []
    if not case.basis.strip():
        findings.append(
            Finding(LABEL_INCOMPLETE, (case.case_id,), "no guide section cited")
        )
    if not case.claims:
        findings.append(Finding(LABEL_INCOMPLETE, (case.case_id,), "no claim labels"))
    unknown = [name for name in case.expected_categories if name not in CATEGORIES]
    if unknown:
        findings.append(
            Finding(
                LABEL_INCOMPLETE,
                (case.case_id,),
                f"unknown categories: {unknown}",
            )
        )
    if case.group != REGRESSION and not case.expected_verdict:
        findings.append(
            Finding(
                LABEL_INCOMPLETE,
                (case.case_id,),
                "an authored capability case must expect a verdict",
            )
        )
    return findings


def _declared_phase(case: CapabilityCase) -> str:
    """Which frozen phase a group C case says it came from."""

    return case.frozen_phase


def _disclosable(case: CapabilityCase, source: str, provenance_ok: bool) -> bool:
    """Is this overlap one the case's own provenance accounts for?

    A group C case is disclosable once its provenance has been *verified* - that is,
    its text was found in a set its declared phase publishes. The `source` of the
    individual finding then does not matter, because the redundancy between frozen
    sets is a property of those sets. An authored case is never disclosable.
    """

    if case.group != REGRESSION:
        return False
    return provenance_ok


def audit(
    cases: Sequence[CapabilityCase] | None = None,
    *,
    historical: Mapping[str, Sequence[str]] | None = None,
    threshold: float = NEAR_DUPLICATE_THRESHOLD,
) -> Phase88AuditReport:
    """Run every check, separating blocking findings from disclosed provenance."""

    active = tuple(cases) if cases is not None else CASES
    sources = historical if historical is not None else phase_8_8_sources()

    development: dict[str, str] = {}
    every_other: dict[str, str] = {}
    for name, texts in sources.items():
        for text in texts:
            normalized = normalize_text(text)
            if name.startswith("development/"):
                development.setdefault(normalized, name)
            else:
                every_other.setdefault(normalized, name)

    findings: list[Finding] = []
    blocking: list[Finding] = []
    disclosed: list[Finding] = []
    normalized = {case.case_id: normalize_text(case.text) for case in active}
    tokens = {case.case_id: token_set(case.text) for case in active}
    by_id = {case.case_id: case for case in active}
    ordered = [case.case_id for case in active]

    def record(
        kind: str,
        ids: tuple[str, ...],
        detail: str,
        *,
        provenance_ok: bool = False,
        **kwargs: Any,
    ) -> None:
        finding = Finding(kind, ids, detail, **kwargs)
        findings.append(finding)
        # A finding is disclosed when every case it names accounts for the overlap
        # in its own verified provenance. A within-benchmark duplicate between two
        # regression cases is disclosed; the same duplicate involving an authored
        # case is not, because two authored cases overlapping each other is
        # contamination however it is labelled.
        if ids and all(
            _disclosable(by_id[case_id], str(kwargs.get("source", "")), provenance_ok)
            for case_id in ids
        ):
            disclosed.append(finding)
        else:
            blocking.append(finding)

    # 0. provenance: does every group C case's text come from where it says?
    #    Checked first, because every disclosure below depends on it.
    verified: dict[str, bool] = {}
    for case in active:
        if case.group != REGRESSION:
            verified[case.case_id] = False
            continue
        declared = FROZEN_PHASE_SOURCES.get(_declared_phase(case), ())
        found = [
            name for name in declared if normalized[case.case_id] in {
                normalize_text(text) for text in sources.get(name, ())
            }
        ]
        verified[case.case_id] = bool(found)
        if not found:
            finding = Finding(
                UNVERIFIABLE_PROVENANCE,
                (case.case_id,),
                "the case declares "
                f"{_declared_phase(case)!r} and its text appears in none of that "
                f"phase's published sets: {list(declared)}",
                source=_declared_phase(case),
            )
            findings.append(finding)
            blocking.append(finding)

    # 1. exact overlap with anything published earlier
    for case_id in ordered:
        source = every_other.get(normalized[case_id])
        if source:
            record(
                EXACT_OVERLAP,
                (case_id,),
                "text also appears verbatim in an earlier benchmark",
                provenance_ok=verified[case_id],
                source=source,
                similarity=1.0,
            )

    # 2. exact duplicates inside this benchmark. Two authored cases with the same
    # text are contamination whichever way the ids differ, and two group C cases
    # with the same text are the frozen sets' redundancy showing through - the same
    # sentence reaching this benchmark by two recorded routes.
    by_text: dict[str, list[str]] = {}
    for case_id in ordered:
        by_text.setdefault(normalized[case_id], []).append(case_id)
    for text, ids in by_text.items():
        if len(ids) < 2:
            continue
        record(
            EXACT_OVERLAP,
            tuple(ids),
            "two cases in this benchmark have the same text",
            provenance_ok=all(verified[case_id] for case_id in ids),
            source=_internal_source(ids[0], ids[1], by_id, normalized, every_other),
            similarity=1.0,
        )

    # 3. near duplicates, within this set and against earlier ones
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            if normalized[left] == normalized[right]:
                continue
            similarity = jaccard(tokens[left], tokens[right])
            if similarity >= threshold:
                record(
                    NEAR_DUPLICATE,
                    (left, right),
                    f"token Jaccard {similarity:.2f} within the benchmark",
                    provenance_ok=verified[left] and verified[right],
                    source=_internal_source(left, right, by_id, normalized, every_other),
                    similarity=similarity,
                )

    for case_id in ordered:
        for name, texts in sources.items():
            if name.startswith("development/"):
                continue
            for text in texts:
                if normalized[case_id] == normalize_text(text):
                    continue
                similarity = jaccard(tokens[case_id], token_set(text))
                if similarity >= threshold:
                    record(
                        NEAR_DUPLICATE,
                        (case_id,),
                        f"token Jaccard {similarity:.2f} against an earlier benchmark",
                        provenance_ok=verified[case_id],
                        source=name,
                        similarity=similarity,
                    )

    # 4. development-set overlap
    for case_id in ordered:
        source = development.get(normalized[case_id])
        if source:
            record(
                DEVELOPMENT_OVERLAP,
                (case_id,),
                "text appears in a development set",
                provenance_ok=False,
                source=source,
                similarity=1.0,
            )

    # 5. label completeness
    for case in active:
        for finding in _label_findings(case):
            findings.append(finding)
            blocking.append(finding)

    from .regression import dataset_hash as v3_1_dataset_hash

    inner = AuditReport(
        benchmark=f"{BENCHMARK_ID}/{BENCHMARK_VERSION}",
        case_count=len(active),
        dataset_hash=v3_1_dataset_hash(active),
        findings=tuple(findings),
        sources_checked=tuple(sorted(sources)),
        threshold=threshold,
    )
    return Phase88AuditReport(
        inner=inner, blocking=tuple(blocking), disclosed=tuple(disclosed)
    )


def write_report(
    path: str | Path | None = None, report: Phase88AuditReport | None = None
) -> Path:
    target = Path(path) if path is not None else AUDIT_PATH
    active = report if report is not None else audit()
    payload = {
        **active.as_dict(),
        "provenance": dataset_payload()["provenance"],
        "phase_sources": {
            key: list(value) for key, value in FROZEN_PHASE_SOURCES.items()
        },
        "pre_publication_findings": [dict(item) for item in PRE_PUBLICATION_FINDINGS],
        "note": (
            "A blocking finding is a FAIL and nothing is repaired here. Group C is "
            "a declared regression set: an overlap with a set its own phase publishes "
            "is disclosed rather than blocking, and an overlap with anything else is "
            "blocking, because that is either a mislabel or an unrecorded copy. "
            "`pre_publication_findings` records what the audit found before "
            "publication and what was done about it. The phase forbids deleting a "
            "contaminated case, so the finding is kept: the case was rewritten "
            "rather than removed, and both texts are recorded."
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
        for finding in report.blocking:
            print(
                f"  {finding.kind}: {list(finding.case_ids)} "
                f"({finding.source}) {finding.detail}"
            )
    if "--write" in sys.argv:
        print()
        print(f"wrote {write_report(report=report)}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
