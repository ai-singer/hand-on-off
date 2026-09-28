"""Phase 8.9 adversarial analysis: classify every failure, then propose.

The phase is explicit that seeing the result must not lead to changing the evaluator.
So this module has two outputs and neither of them is a patch.

**A classification.** Every failing case is assigned one of the five kinds the phase
names, from the trace rather than from the symptom, in a fixed order of precedence
so the assignment is reproducible:

    annotation_disagreement  the annotators disagreed on this case's decision or
                             intent, so the "failure" may be about the label
    taxonomy_ambiguity       the adjudicator needed a third reading, or declined to
                             settle the field
    attribution_error        the speaker or stance the evaluator resolved differs
                             from the label's
    lexical_gap              the labelled relation produced no finding at all, so
                             nothing was found to suppress - the vocabulary missed it
    semantic_gap             a relation was found and the outcome is still wrong, so
                             the fault is in what the layer did with it

Precedence matters and is declared rather than implied. A case where the annotators
disagreed *and* the vocabulary missed the wording is classified as a disagreement,
because the first question about a failure is whether the label is solid.

**A proposal per class.** Each class gets a written proposal: what the evidence is,
what a repair would have to do, and what it must not break. The proposals are not
implemented in this phase, and `freeze.guard()` raises if anyone tries.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .evaluation import CaseResult

ADVERSARIAL_PATH = Path(__file__).resolve().parent / "adversarial_analysis_v3_2.json"
PROPOSALS_PATH = Path(__file__).resolve().parent / "proposals_v3_2.json"

ANNOTATION_DISAGREEMENT = "annotation_disagreement"
TAXONOMY_AMBIGUITY = "taxonomy_ambiguity"
ATTRIBUTION_ERROR = "attribution_error"
LEXICAL_GAP = "lexical_gap"
SEMANTIC_GAP = "semantic_gap"

#: The phase's five classes, in the order they are tested.
ERROR_KINDS: tuple[str, ...] = (
    ANNOTATION_DISAGREEMENT,
    TAXONOMY_AMBIGUITY,
    ATTRIBUTION_ERROR,
    LEXICAL_GAP,
    SEMANTIC_GAP,
)

KIND_MEANING: Mapping[str, str] = {
    ANNOTATION_DISAGREEMENT: "the two annotators differed on this case's label",
    TAXONOMY_AMBIGUITY: "the guide did not settle it and the adjudicator ruled a third reading or declined",
    ATTRIBUTION_ERROR: "the speaker or stance the evaluator resolved differs from the label",
    LEXICAL_GAP: "the labelled relation produced no finding at all",
    SEMANTIC_GAP: "a relation was found and the outcome is still wrong",
}


class AnalysisError(Exception):
    """Raised when the analysis cannot run."""


@dataclass(frozen=True, slots=True)
class Diagnosis:
    """One failing case, classified, with the evidence behind the class."""

    case_id: str
    kind: str
    detail: str
    group: str
    language: str
    form: str
    source_type: str
    text: str
    expected: tuple[str, ...]
    predicted: tuple[str, ...]
    expected_relations: tuple[str, ...]
    found_relations: tuple[str, ...]
    intended_intent: str
    evidence: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "kind": self.kind,
            "detail": self.detail,
            "group": self.group,
            "language": self.language,
            "form": self.form,
            "source_type": self.source_type,
            "text": self.text,
            "expected": list(self.expected),
            "predicted": list(self.predicted),
            "expected_relations": list(self.expected_relations),
            "found_relations": list(self.found_relations),
            "intended_intent": self.intended_intent,
            "evidence": list(self.evidence),
        }


def _disputed_fields(case_id: str, manifest: Mapping[str, Any]) -> tuple[str, ...]:
    """Whether the annotators differed on this case, from the published record."""

    for entry in manifest.get("_disagreements", ()):
        if entry.get("case_id") == case_id:
            return ("decision",)
    return ()


def classify(
    case: CaseResult,
    *,
    adjudication: Mapping[str, Any],
    disagreements: Mapping[str, Sequence[Mapping[str, Any]]],
) -> Diagnosis | None:
    """One failure, one class. Returns None when the case is not a failure."""

    if case.correct:
        return None

    disputed = {item.get("field") for item in disagreements.get(case.case_id, ())}
    rulings = adjudication.get(case.case_id, ())

    kind = SEMANTIC_GAP
    detail = "a relation was found and the outcome is still wrong"

    if {"decision", "intent", "severity"} & disputed:
        kind = ANNOTATION_DISAGREEMENT
        detail = (
            "the annotators differed on "
            + ", ".join(sorted({"decision", "intent", "severity"} & disputed))
            + ", so the label itself was in dispute before the evaluator saw it"
        )
    elif any(item.get("resolution") == "third_reading" for item in rulings):
        kind = TAXONOMY_AMBIGUITY
        detail = "the adjudicator ruled a third reading, so the guide did not settle the case"
    elif any(item.get("resolution") == "unresolved" for item in rulings):
        kind = TAXONOMY_AMBIGUITY
        detail = "the adjudicator declined to settle a field"
    elif case.extra and case.speakers and case.speakers != ("author",):
        # An extra category on a claim the evaluator read as somebody else's is an
        # attribution question before it is a vocabulary question.
        kind = ATTRIBUTION_ERROR
        detail = (
            "an extra category was raised on a claim the evaluator resolved as "
            + "/".join(case.speakers)
        )
    elif case.missing and not case.found_relations:
        kind = LEXICAL_GAP
        detail = (
            "the label expects "
            + "/".join(sorted(case.missing))
            + " and no relation was found at all, so there was nothing for the "
            "decision layer to suppress"
        )
    elif case.missing and case.found_relations:
        kind = SEMANTIC_GAP
        detail = (
            "a relation was found ("
            + "/".join(case.found_relations)
            + ") and the label still expects "
            + "/".join(sorted(case.missing))
            + ": the layer found something and did the wrong thing with it"
        )
    elif case.extra:
        kind = SEMANTIC_GAP
        detail = "an extra category was raised with no speaker mismatch to explain it"

    return Diagnosis(
        case_id=case.case_id,
        kind=kind,
        detail=detail,
        group=case.group,
        language=case.language,
        form=case.form,
        source_type=case.source_type,
        text=case.text,
        expected=case.expected,
        predicted=case.predicted,
        expected_relations=case.expected_relations,
        found_relations=case.found_relations,
        intended_intent=case.intended_intent,
        evidence=case.evidence,
    )


def _index_adjudication() -> Mapping[str, Sequence[Mapping[str, Any]]]:
    """The rulings per case, read from the published adjudication artifact."""

    path = (
        Path(__file__).resolve().parent
        / "run"
        / "annotation"
        / "adjudication"
        / "adjudicated.json"
    )
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    index: dict[str, list[Mapping[str, Any]]] = {}
    for item in payload.get("cases", ()):
        index[str(item["case_id"])] = list(item.get("rulings", ()))
    return index


def _index_disagreements() -> Mapping[str, Sequence[Mapping[str, Any]]]:
    path = Path(__file__).resolve().parents[1] / "benchmarks" / "risk" / "independent" / "v1" / "disagreements.json"
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    index: dict[str, list[Mapping[str, Any]]] = {}
    for item in payload.get("disagreements", ()):
        index.setdefault(str(item["case_id"]), []).append(item)
    return index


@dataclass(frozen=True, slots=True)
class Analysis:
    results: tuple[CaseResult, ...]
    diagnoses: tuple[Diagnosis, ...]

    def counts(self) -> Mapping[str, int]:
        buckets = {kind: 0 for kind in ERROR_KINDS}
        for item in self.diagnoses:
            buckets[item.kind] = buckets.get(item.kind, 0) + 1
        return buckets

    def of_kind(self, kind: str) -> tuple[Diagnosis, ...]:
        return tuple(item for item in self.diagnoses if item.kind == kind)

    def by_language(self) -> Mapping[str, Mapping[str, int]]:
        buckets: dict[str, dict[str, int]] = {}
        for item in self.diagnoses:
            entry = buckets.setdefault(item.language, {kind: 0 for kind in ERROR_KINDS})
            entry[item.kind] += 1
        return {key: dict(value) for key, value in sorted(buckets.items())}

    @property
    def failure_rate(self) -> float:
        total = len(self.results)
        return round(len(self.diagnoses) / total, 4) if total else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "cases": len(self.results),
            "failures": len(self.diagnoses),
            "failure_rate": self.failure_rate,
            "counts": dict(self.counts()),
            "meanings": dict(KIND_MEANING),
            "by_language": {k: dict(v) for k, v in self.by_language().items()},
            "diagnoses": [item.as_dict() for item in self.diagnoses],
        }

    def render(self) -> str:
        lines = [f"cases    : {len(self.results)}", f"failures : {len(self.diagnoses)}"]
        for kind, count in self.counts().items():
            lines.append(f"  {kind:24} {count:4}  {KIND_MEANING[kind]}")
        lines.append("")
        for language, bucket in self.by_language().items():
            lines.append(
                f"  language {language:4} "
                + "  ".join(f"{k}={v}" for k, v in bucket.items() if v)
            )
        return "\n".join(lines)


def analyse(
    results: Sequence[CaseResult] | None = None,
    *,
    adjudication: Mapping[str, Any] | None = None,
    disagreements: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
) -> Analysis:
    from .evaluation import predict

    active = tuple(results) if results is not None else predict()
    adj = adjudication if adjudication is not None else _index_adjudication()
    dis = disagreements if disagreements is not None else _index_disagreements()
    diagnoses = tuple(
        item
        for item in (classify(case, adjudication=adj, disagreements=dis) for case in active)
        if item is not None
    )
    return Analysis(results=active, diagnoses=diagnoses)


#: One proposal per failure class. Written, not implemented: the phase forbids
#: modifying the evaluator after seeing the result, so the honest output is a plan.
PROPOSALS: tuple[Mapping[str, Any], ...] = (
    {
        "id": "P1-language-coverage",
        "kind": LEXICAL_GAP,
        "title": "The relation vocabulary is effectively English-only",
        "evidence": (
            "Recall on the independently authored set is far below the author's own "
            "benchmark, and the loss is concentrated in one language. The Chinese "
            "cases in the frame express the same five categories with the same "
            "relations, and the intent layer finds almost none of them."
        ),
        "proposal": (
            "Add Chinese relation vocabulary to the v3.1 capability layers: movement "
            "and comparison outcomes, modal carriers, directive verbs, method "
            "guidance markers, and the disclosure and symmetric-pair forms. The "
            "morphology layer does not apply to Chinese, so the frames need a "
            "separate lexical path rather than an inflection rule."
        ),
        "must_not_break": (
            "the 30 English cases the frame marks safe, the Phase 8.6 and 8.8 "
            "benchmarks, and the Phase 8.5 relation recall of 1.0"
        ),
        "blocked_by": "the Phase 8.9 freeze: no evaluator change is permitted this phase",
    },
    {
        "id": "P2-modality-coverage",
        "kind": LEXICAL_GAP,
        "title": "Wording outside the frame's own vocabulary is invisible",
        "evidence": (
            "The failures classified as a lexical gap are cases where the labelled "
            "relation produced no finding at all. The capability layers decide on "
            "declared signals and outcome lexicons, and a sentence that expresses "
            "the relation with words outside those lists is not seen."
        ),
        "proposal": (
            "Widen the outcome and directive vocabularies from a corpus of the "
            "independent text rather than from imagination, and add a coverage test "
            "that fails when a relation's lexicon misses a labelled case in a held "
            "out set."
        ),
        "must_not_break": (
            "precision: the layers currently over-flag almost nothing, and widening "
            "the lexicon is how a precision-first layer loses that"
        ),
        "blocked_by": "the Phase 8.9 freeze",
    },
    {
        "id": "P3-annotation-ambiguity",
        "kind": ANNOTATION_DISAGREEMENT,
        "title": "The guide leaves real cases undecided",
        "evidence": (
            "The agreement section reports a kappa per field; the lowest ones name "
            "the fields the guide under-specifies. The cases classified here failed "
            "while the label itself was in dispute, so they measure the guide as much "
            "as the evaluator."
        ),
        "proposal": (
            "Rule on the disputed fields the adjudicator had to settle with a third "
            "reading, in a guide v3. Until then, report these cases separately from "
            "the evaluator's own failures rather than counting them as one."
        ),
        "must_not_break": "the frozen guide version every earlier label cites",
        "blocked_by": "a guide revision is out of scope for a validation phase",
    },
    {
        "id": "P4-attribution-boundary",
        "kind": ATTRIBUTION_ERROR,
        "title": "Speaker resolution differs from the label on quoted material",
        "evidence": (
            "The attribution classification counts cases where the evaluator resolved "
            "a speaker or stance the label does not share, and the extra category "
            "follows from that resolution rather than from the wording."
        ),
        "proposal": (
            "Extend the source lexicon from the independent text, and re-examine the "
            "rule that maps a checkable source to a negative verdict against the "
            "cases where the label disagreed."
        ),
        "must_not_break": "the Phase 8.3 control case and the Phase 8.6 attribution metrics",
        "blocked_by": "the Phase 8.9 freeze",
    },
    {
        "id": "P5-semantic-boundary",
        "kind": SEMANTIC_GAP,
        "title": "A relation is found and the decision goes the wrong way",
        "evidence": (
            "These cases produced at least one relation and still missed or added a "
            "category, so the vocabulary was sufficient and the boundary rule was not."
        ),
        "proposal": (
            "Re-derive the certainty and directionality boundaries from the "
            "independent cases, and check whether the hedge policy that preserves a "
            "matcher hedge is suppressing statements the guide calls asserted."
        ),
        "must_not_break": "the Phase 8.8 modal and advice benchmarks",
        "blocked_by": "the Phase 8.9 freeze",
    },
    {
        "id": "P6-guide-v3",
        "kind": TAXONOMY_AMBIGUITY,
        "title": "The guide does not settle every case the text contains",
        "evidence": (
            "These are the cases where the adjudicator ruled a third reading that "
            "neither annotator proposed, or declined to settle the field at all. The "
            "two annotators disagreed, the disagreement survived adjudication, and "
            "the reason is that the guide has no rule for the case."
        ),
        "proposal": (
            "Write the missing rules into a guide v3, one per ambiguity the "
            "adjudication record names, and re-label the affected cases under it "
            "while keeping the v2 labels beside them. A guide revision is the only "
            "honest repair for this class: the evaluator is not wrong about a case "
            "the standard does not decide."
        ),
        "must_not_break": (
            "the frozen guide version every earlier label cites, and the labels "
            "themselves - a guide revision re-labels, it does not overwrite"
        ),
        "blocked_by": "a guide revision is out of scope for a validation phase",
    },
)


def proposal_payload(analysis: Analysis) -> dict[str, Any]:
    counts = analysis.counts()
    payload = []
    for item in PROPOSALS:
        entry = dict(item)
        entry["observed_cases"] = counts.get(str(item["kind"]), 0)
        payload.append(entry)
    return {
        "proposals": payload,
        "evaluator_modified": False,
        "note": (
            "The phase forbids changing the evaluator in response to these results. "
            "Each proposal names what a repair would have to do and what it must not "
            "break; none is implemented. `freeze.guard()` raises if one is."
        ),
    }


def write_reports(
    *, analysis: Analysis | None = None, directory: str | Path | None = None
) -> tuple[Path, Path]:
    active = analysis if analysis is not None else analyse()
    root = Path(directory) if directory is not None else Path(__file__).resolve().parent
    adversarial = root / ADVERSARIAL_PATH.name
    proposals = root / PROPOSALS_PATH.name
    adversarial.write_text(
        json.dumps(active.as_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    proposals.write_text(
        json.dumps(proposal_payload(active), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    return adversarial, proposals


def describe() -> dict[str, Any]:
    return {
        "kinds": list(ERROR_KINDS),
        "meanings": dict(KIND_MEANING),
        "precedence": "declared, and tested in this order",
        "proposals": [item["id"] for item in PROPOSALS],
        "implements_any_proposal": False,
    }


def main() -> int:
    import sys

    analysis = analyse()
    print(analysis.render())
    if "--write" in sys.argv:
        written = write_reports(analysis=analysis)
        print()
        for path in written:
            print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
