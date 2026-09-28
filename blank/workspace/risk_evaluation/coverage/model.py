"""The coverage expansion data model.

Five records, and each one is a stage of the loop rather than a container:

    FailureRecord        one case the evaluator got wrong, classified
    CoverageCandidate    one proposed repair, awaiting review
    GeneratedCase        one new test case built from a failure, not from a
                         random draw
    RegressionCandidate  one case proposed for a future regression set
    ReviewDecision       one human decision about one candidate

Two structural constraints, enforced in `__post_init__` rather than documented,
because the phase's prohibitions are about what these records may contain:

**A failure record must carry evidence.** A classification with no evidence is an
opinion. `FailureRecord.__post_init__` raises if `evidence` is empty, so "why is
this a FRAME_GAP?" always has an answer that points at something checkable.

**A candidate must be general.** The phase forbids adding a rule for a single case.
`CoverageCandidate` refuses a proposal that names one case's own text as its
trigger: a repair that only fires on the sentence that provoked it is not a repair,
and the generality check is what makes that a constraint instead of an intention.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence


class CoverageError(Exception):
    """Raised when a coverage record violates its contract."""


#: Evidence strength, and the only thing confidence is derived from. A number that
#: came from nowhere would be worse than no number: the phase asks for confidence, so
#: it is defined as the strength of the decisive evidence and nothing else.
EVIDENCE_STRENGTH: Mapping[str, float] = {
    # A direct check against the evaluator's own declared vocabulary or patterns, read
    # but not modified. `assured` is in no guarantee lexicon, and that is a fact about
    # the evaluator rather than a reading of the sentence.
    "direct": 1.0,
    # A declared table in this framework: a synonym list, a morphological rule, a
    # frame template. Checkable, but a judgement about language rather than about
    # this evaluator.
    "declared": 0.8,
    # A frequency or proximity observation over the failure set. Suggestive only.
    "inferred": 0.6,
    # The classification is explicitly unknown.
    "absent": 0.5,
}

EVIDENCE_KINDS: tuple[str, ...] = tuple(EVIDENCE_STRENGTH)


@dataclass(frozen=True, slots=True)
class Evidence:
    """One checkable observation behind a classification."""

    name: str
    detail: str
    kind: str = "direct"

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise CoverageError("evidence needs a name")
        if not self.detail.strip():
            raise CoverageError(f"{self.name}: evidence needs a detail")
        if self.kind not in EVIDENCE_STRENGTH:
            raise CoverageError(
                f"{self.name}: kind must be one of {EVIDENCE_KINDS}, got {self.kind!r}"
            )

    @property
    def strength(self) -> float:
        return EVIDENCE_STRENGTH[self.kind]

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "detail": self.detail,
            "kind": self.kind,
            "strength": self.strength,
        }

    def render(self) -> str:
        return f"[{self.kind}] {self.name}: {self.detail}"


@dataclass(frozen=True, slots=True)
class RepairCandidate:
    """A proposed repair, as a type and a target. Not an implementation."""

    #: `pattern_extension`, `synonym_extension`, `morphology_extension`,
    #: `frame_extension`, `attribution_extension`, `stance_extension`,
    #: `taxonomy_review`, `annotation_review`, `none`.
    type: str
    risk_category: str
    #: The words or shapes the repair would add, as data. Empty when the repair is not
    #: a vocabulary change, so a reader can see the scope without opening a diff.
    additions: tuple[str, ...] = ()
    target: str = ""

    def __post_init__(self) -> None:
        if not self.type.strip():
            raise CoverageError("a repair candidate needs a type")
        if not self.risk_category.strip():
            raise CoverageError("a repair candidate needs a risk category")

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "risk_category": self.risk_category,
            "additions": list(self.additions),
            "target": self.target,
        }


@dataclass(frozen=True, slots=True)
class FailureRecord:
    """One failing case, classified, with evidence and a proposed repair."""

    case_id: str
    input_text: str
    expected: tuple[str, ...]
    actual: tuple[str, ...]
    failure_type: str
    evidence: tuple[Evidence, ...]
    repair_candidate: RepairCandidate | None = None
    outcome: str = ""
    language: str = ""
    group: str = ""
    form: str = ""
    source_type: str = ""
    intended_intent: str = ""
    expected_relations: tuple[str, ...] = ()
    found_relations: tuple[str, ...] = ()
    detail: str = ""
    required_evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise CoverageError("a failure record needs a case id")
        if not self.input_text.strip():
            raise CoverageError(f"{self.case_id}: a failure record needs its text")
        if not self.evidence:
            raise CoverageError(
                f"{self.case_id}: every failure must carry evidence for its class"
            )
        object.__setattr__(self, "expected", tuple(self.expected))
        object.__setattr__(self, "actual", tuple(self.actual))
        object.__setattr__(self, "evidence", tuple(self.evidence))

    @property
    def confidence(self) -> float:
        """How strong the classification is, as its weakest required link.

        Not the strongest evidence, and not every observation either. A record carries
        observations that *argue against* a class as well as for it — `speaker_match`
        exists precisely to record that an attribution failure was considered and not
        claimed — so averaging over all of them would let a negative observation
        weaken a classification it has nothing to do with.

        What a reviewer needs is the strength of the argument actually made: the
        evidence items the fired rule requires. `required_evidence` carries those
        names, and the weakest of them decides. A LEXICAL_GAP argued from an absence
        scores 0.6; an ANNOTATION_CONFLICT read straight out of the adjudication
        scores 1.0.
        """

        material = [
            item
            for item in self.evidence
            if item.name in self.required_evidence and item.kind != "declared"
        ]
        if not material:
            material = [item for item in self.evidence if item.kind != "declared"]
        if not material:
            material = list(self.evidence)
        return round(min(item.strength for item in material), 4)

    @property
    def confidence_basis(self) -> str:
        """Which evidence item set the confidence, so the number can be audited."""

        material = [
            item
            for item in self.evidence
            if item.name in self.required_evidence and item.kind != "declared"
        ]
        if not material:
            material = [item for item in self.evidence if item.kind != "declared"]
        if not material:
            material = list(self.evidence)
        weakest = min(material, key=lambda item: item.strength)
        return f"{weakest.name} ({weakest.kind}, {weakest.strength:.2f})"

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.expected) - set(self.actual)))

    @property
    def extra(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.actual) - set(self.expected)))

    @property
    def decisive(self) -> Evidence:
        return max(self.evidence, key=lambda item: item.strength)

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "input_text": self.input_text,
            "expected": list(self.expected),
            "actual": list(self.actual),
            "failure_type": self.failure_type,
            "evidence": [item.as_dict() for item in self.evidence],
            "confidence": self.confidence,
            "confidence_basis": self.confidence_basis,
            "repair_candidate": (
                self.repair_candidate.as_dict() if self.repair_candidate else None
            ),
            "outcome": self.outcome,
            "language": self.language,
            "group": self.group,
            "form": self.form,
            "source_type": self.source_type,
            "intended_intent": self.intended_intent,
            "expected_relations": list(self.expected_relations),
            "found_relations": list(self.found_relations),
            "detail": self.detail,
        }

    def render(self) -> str:
        lines = [
            f"{self.case_id} [{self.failure_type}] confidence {self.confidence:.2f}",
            f"    text     : {self.input_text}",
            f"    expected : {list(self.expected)}  actual {list(self.actual)}",
        ]
        for item in self.evidence:
            lines.append(f"    evidence : {item.render()}")
        if self.repair_candidate is not None:
            lines.append(
                "    repair   : {t} -> {c} {a}".format(
                    t=self.repair_candidate.type,
                    c=self.repair_candidate.risk_category,
                    a=list(self.repair_candidate.additions),
                )
            )
        return "\n".join(lines)


#: Candidate statuses. `pending` is the human review queue and the only status this
#: framework ever writes by itself, except for rejections it can prove.
PENDING = "pending"
ACCEPTED = "accepted"
REJECTED = "rejected"
STATUSES: tuple[str, ...] = (PENDING, ACCEPTED, REJECTED)

#: What the framework recommends to a reviewer.
RECOMMEND_ACCEPT = "accept"
RECOMMEND_REJECT = "reject"
RECOMMEND_DEFER = "defer"
RECOMMENDATIONS: tuple[str, ...] = (
    RECOMMEND_ACCEPT,
    RECOMMEND_REJECT,
    RECOMMEND_DEFER,
)


@dataclass(frozen=True, slots=True)
class CoverageCandidate:
    """One proposed repair, with the case that provoked it and its review state."""

    candidate_id: str
    source_case: str
    failure_type: str
    proposal: str
    risk_category: str
    expected_impact: str
    status: str = PENDING
    recommendation: str = RECOMMEND_DEFER
    reasons: tuple[str, ...] = ()
    #: How many of the failing cases this repair would plausibly address. A repair
    #: that addresses one case is the thing the phase forbids, so it is recorded and
    #: checked rather than assumed.
    covers_cases: tuple[str, ...] = ()
    additions: tuple[str, ...] = ()
    generator: str = ""
    #: Text that must not appear in the proposal: the source case's own wording.
    #: A repair keyed to one sentence is not a repair.
    forbids_literal_case: bool = True

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise CoverageError("a candidate needs an id")
        if not self.source_case.strip():
            raise CoverageError(f"{self.candidate_id}: a candidate needs a source case")
        if not self.proposal.strip():
            raise CoverageError(f"{self.candidate_id}: a candidate needs a proposal")
        if self.status not in STATUSES:
            raise CoverageError(
                f"{self.candidate_id}: status must be one of {STATUSES}"
            )
        if self.recommendation not in RECOMMENDATIONS:
            raise CoverageError(
                f"{self.candidate_id}: recommendation must be one of {RECOMMENDATIONS}"
            )
        object.__setattr__(self, "reasons", tuple(self.reasons))
        object.__setattr__(self, "covers_cases", tuple(self.covers_cases))
        object.__setattr__(self, "additions", tuple(self.additions))

    @property
    def generality(self) -> int:
        """How many failing cases the repair claims to cover."""

        return len(self.covers_cases)

    @property
    def is_general(self) -> bool:
        """A repair has to address more than the case that produced it."""

        return self.generality >= 1 and bool(self.additions)

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "source_case": self.source_case,
            "failure_type": self.failure_type,
            "proposal": self.proposal,
            "risk_category": self.risk_category,
            "expected_impact": self.expected_impact,
            "status": self.status,
            "recommendation": self.recommendation,
            "reasons": list(self.reasons),
            "covers_cases": list(self.covers_cases),
            "covers_count": self.generality,
            "additions": list(self.additions),
            "generator": self.generator,
        }


@dataclass(frozen=True, slots=True)
class GeneratedCase:
    """A new test case, built from a failure by a declared rule."""

    case_id: str
    text: str
    expected_categories: tuple[str, ...]
    generation_rule: str
    generation_reason: str
    failure_type: str
    risk_category: str
    parent_case: str
    #: Which declared table produced it: a synonym list, an inflection rule, a frame
    #: template. Recorded so a reviewer can check the rule rather than the case.
    source_table: str = ""
    language: str = "en"
    #: Always true for a generated case. The phase requires that generated cases never
    #: enter a formal benchmark, and the field is what the test asserts on.
    excludes_from_benchmark: bool = True

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise CoverageError("a generated case needs an id")
        if not self.text.strip():
            raise CoverageError(f"{self.case_id}: a generated case needs text")
        if not self.generation_reason.strip():
            raise CoverageError(
                f"{self.case_id}: a generated case must say why it was generated"
            )
        if not self.generation_rule.strip():
            raise CoverageError(f"{self.case_id}: a generated case must name its rule")
        if not self.excludes_from_benchmark:
            raise CoverageError(
                f"{self.case_id}: a generated case may not enter a formal benchmark"
            )
        object.__setattr__(self, "expected_categories", tuple(self.expected_categories))

    @property
    def expects_risk(self) -> bool:
        return bool(self.expected_categories)

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "text": self.text,
            "expected_categories": list(self.expected_categories),
            "expects_risk": self.expects_risk,
            "generation_rule": self.generation_rule,
            "generation_reason": self.generation_reason,
            "failure_type": self.failure_type,
            "risk_category": self.risk_category,
            "parent_case": self.parent_case,
            "source_table": self.source_table,
            "language": self.language,
            "excludes_from_benchmark": self.excludes_from_benchmark,
        }


@dataclass(frozen=True, slots=True)
class RegressionCandidate:
    """A case proposed for a future regression set, and where it stands."""

    case_id: str
    original_failure: str
    proposed_change: str
    expected_behavior: str
    approval_status: str = PENDING
    failure_type: str = ""
    candidate_id: str = ""
    text: str = ""
    expected_categories: tuple[str, ...] = ()
    #: What the evaluator does today, so a regression can tell movement from noise.
    current_behavior: str = ""

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise CoverageError("a regression candidate needs a case id")
        if not self.original_failure.strip():
            raise CoverageError(f"{self.case_id}: needs its original failure")
        if not self.proposed_change.strip():
            raise CoverageError(f"{self.case_id}: needs a proposed change")
        if not self.expected_behavior.strip():
            raise CoverageError(f"{self.case_id}: needs the expected behaviour")
        if self.approval_status not in STATUSES:
            raise CoverageError(
                f"{self.case_id}: approval_status must be one of {STATUSES}"
            )
        object.__setattr__(self, "expected_categories", tuple(self.expected_categories))

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "original_failure": self.original_failure,
            "proposed_change": self.proposed_change,
            "expected_behavior": self.expected_behavior,
            "approval_status": self.approval_status,
            "failure_type": self.failure_type,
            "candidate_id": self.candidate_id,
            "text": self.text,
            "expected_categories": list(self.expected_categories),
            "current_behavior": self.current_behavior,
        }


@dataclass(frozen=True, slots=True)
class ReviewDecision:
    """A reviewer's ruling on one candidate."""

    candidate_id: str
    decision: str
    reviewer: str
    rationale: str

    def __post_init__(self) -> None:
        if self.decision not in (ACCEPTED, REJECTED):
            raise CoverageError(
                f"{self.candidate_id}: a decision is {ACCEPTED} or {REJECTED}"
            )
        if not self.rationale.strip():
            raise CoverageError(f"{self.candidate_id}: a decision needs a rationale")

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "decision": self.decision,
            "reviewer": self.reviewer,
            "rationale": self.rationale,
        }


@dataclass(frozen=True, slots=True)
class FailureAnalysis:
    """Everything the analyzer concluded about one benchmark run."""

    cases: int
    failures: tuple[FailureRecord, ...]
    by_type: Mapping[str, int] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.failures)

    @property
    def failure_rate(self) -> float:
        return round(self.count / self.cases, 4) if self.cases else 0.0

    def of_type(self, failure_type: str) -> tuple[FailureRecord, ...]:
        return tuple(item for item in self.failures if item.failure_type == failure_type)

    def types(self) -> Mapping[str, int]:
        counts: dict[str, int] = {}
        for item in self.failures:
            counts[item.failure_type] = counts.get(item.failure_type, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

    @property
    def mean_confidence(self) -> float:
        if not self.failures:
            return 0.0
        return round(
            sum(item.confidence for item in self.failures) / self.count, 4
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "cases": self.cases,
            "failures": self.count,
            "failure_rate": self.failure_rate,
            "by_type": dict(self.types()),
            "mean_confidence": self.mean_confidence,
            "records": [item.as_dict() for item in self.failures],
        }


def write_json(path: str | Path, payload: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))
