"""Error classification: every failure, with a named cause.

The phase forbids listing numbers without analysing the cases. This module
classifies each failing case into one of five categories and, where the
mechanism is identifiable from the text and the prediction, names it:

    attribution_error          the speaker or stance is wrong
    intent_detection_error     the relation was not found, or found wrongly
    decision_policy_error      the relation was found and decided wrongly
    annotation_ambiguity       the label itself is open to dispute
    unknown_language_pattern   a phrasing no layer was built against

Classification is a judgement, so the classifier is a table of explicit checks
rather than a score, and `diagnose()` returns the reasons it used. A case the
classifier cannot place is reported as `unclassified` rather than forced into a
bucket, and the report discusses it by hand.

The mechanisms worth naming, because they recur:

    inflected_verb           `expands` where only `expand` is listed
    novel_source_noun        a reporting frame whose source noun is not known
    novel_rejection_cue      a first-person rejection phrase not in the cue list
    fallback_propagation     a baseline false positive carried through by the
                             semantic fallback
    lexical_gap              the expected relation has no marker in the text's
                             vocabulary
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..v3.patterns import ENTITIES, PATTERNS
from ..intent_patterns.matcher import RelationMatcher
from .cases import ValidationCase
from .evaluation import CaseOutcome

ANALYSIS_PATH = Path(__file__).resolve().parent / "error_analysis.json"

ATTRIBUTION_ERROR = "attribution_error"
INTENT_DETECTION_ERROR = "intent_detection_error"
DECISION_POLICY_ERROR = "decision_policy_error"
ANNOTATION_AMBIGUITY = "annotation_ambiguity"
UNKNOWN_LANGUAGE_PATTERN = "unknown_language_pattern"
UNCLASSIFIED = "unclassified"

CATEGORIES = (
    ATTRIBUTION_ERROR,
    INTENT_DETECTION_ERROR,
    DECISION_POLICY_ERROR,
    ANNOTATION_AMBIGUITY,
    UNKNOWN_LANGUAGE_PATTERN,
    UNCLASSIFIED,
)

INFLECTED_VERB = "inflected_verb"
NOVEL_SOURCE_NOUN = "novel_source_noun"
NOVEL_REJECTION_CUE = "novel_rejection_cue"
FALLBACK_PROPAGATION = "fallback_propagation"
LEXICAL_GAP = "lexical_gap"

MECHANISMS = (
    INFLECTED_VERB,
    NOVEL_SOURCE_NOUN,
    NOVEL_REJECTION_CUE,
    FALLBACK_PROPAGATION,
    LEXICAL_GAP,
)

AMBIGUOUS_NEGATED_RELATION = "ambiguous_negated_relation"
AMBIGUOUS_RELATION_NAME = "ambiguous_relation_name"

#: Vocabulary that identifies each relation by form rather than by meaning.
#:
#: Only the two relations whose form is a closed list are checked. PREDICTION
#: and ADVICE are realised too variously - `Turnover expands sharply next
#: quarter.` is a prediction with no auxiliary at all - so a checklist for them
#: would flag correct labels as ambiguous, which is worse than not checking.
_RELATION_MARKERS: Mapping[str, tuple[str, ...]] = {
    "GUARANTEE": ("guarantee", "guaranteed", "guarantees"),
    "RISK_REMOVED": ("risk-free", "no risk", "zero risk", "cannot lose", "never fall"),
}

_NEGATION = re.compile(
    r"\b(?:not|no|never|cannot|can't|without|n't)\b", re.IGNORECASE
)

#: Movement verbs the prediction frame lists, in their base form only.
_MOVEMENT_VERBS = (
    "rise",
    "fall",
    "double",
    "triple",
    "reach",
    "grow",
    "climb",
    "drop",
    "decline",
    "crash",
    "recover",
    "rally",
    "surge",
    "slip",
    "tumble",
    "soar",
    "multiply",
    "increase",
    "decrease",
    "expand",
    "contract",
)

#: First-person rejection openers the attribution layer looks for.
_REJECTION_CUES = (
    "we disagree",
    "we do not agree",
    "we don't agree",
    "this is incorrect",
    "this is wrong",
    "we doubt",
    "we are not convinced",
    "refute",
    "debunk",
    "dispute",
)

#: Source nouns the attribution layer knows.
_KNOWN_SOURCES = (
    "analysts",
    "experts",
    "economists",
    "management",
    "the board",
    "regulators",
    "officials",
    "brokers",
    "bankers",
    "commentators",
    "the company",
    "the newsletter",
    "the broker note",
    "sources",
    "insiders",
    "a source",
    "people close to",
    "the report",
)

#: Reporting verbs that make a claim somebody else's.
_REPORTING = re.compile(
    r"\b(?:said|says|say|stated|states|according to|reports say|reportedly|"
    r"claims|claimed|told|noted|wrote|writes|suggests|suggested|confirmed|"
    r"published|expects|predicted|forecasts|argue|argues|recommends)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Mechanism:
    name: str
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class Diagnosis:
    case_id: str
    category: str
    text: str
    group: str
    expected: tuple[str, ...]
    predicted: tuple[str, ...]
    baseline: tuple[str, ...]
    outcome: str
    mechanisms: tuple[Mechanism, ...]
    explanation: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "text": self.text,
            "group": self.group,
            "expected": list(self.expected),
            "predicted": list(self.predicted),
            "baseline": list(self.baseline),
            "outcome": self.outcome,
            "mechanisms": [m.as_dict() for m in self.mechanisms],
            "explanation": self.explanation,
        }

    def render(self) -> str:
        lines = [
            f"{self.case_id} [{self.category}] {self.outcome}",
            f"    text      : {self.text}",
            f"    expected  : {list(self.expected)}  predicted: {list(self.predicted)}"
            f"  baseline: {list(self.baseline)}",
        ]
        for item in self.mechanisms:
            lines.append(f"    mechanism : {item.name} - {item.detail}")
        lines.append(f"    why       : {self.explanation}")
        return "\n".join(lines)


def _inflected_verb(text: str) -> Mechanism | None:
    """A movement verb present only in an inflected form.

    `Turnover expands sharply next quarter.` is a prediction by the guide and
    the frames list only base forms, so `expand\\b` does not match `expands`.
    """

    lowered = text.lower()
    for verb in _MOVEMENT_VERBS:
        for suffix in ("s", "es", "ed", "ing"):
            candidate = f"{verb}{suffix}"
            if re.search(rf"\b{re.escape(candidate)}\b", lowered) and not re.search(
                rf"\b{re.escape(verb)}\b", lowered
            ):
                return Mechanism(
                    INFLECTED_VERB,
                    f"`{candidate}` appears but the frames list only `{verb}`",
                )
    return None


def _novel_source(text: str) -> Mechanism | None:
    lowered = text.lower()
    if not _REPORTING.search(text):
        return None
    if any(source in lowered for source in _KNOWN_SOURCES):
        return None
    return Mechanism(
        NOVEL_SOURCE_NOUN,
        "a reporting frame is present and its source noun is not in the attribution lexicon",
    )


def _novel_rejection(text: str) -> Mechanism | None:
    lowered = text.lower()
    if not lowered.startswith(("we ", "the ", "that ", "claims ", "contrary ")):
        return None
    if any(cue in lowered for cue in _REJECTION_CUES):
        return None
    if re.search(
        r"\b(?:reject|unconvinced|not supported|no basis|is false|overstated|"
        r"not accept|would not describe|no evidence)\b",
        lowered,
    ):
        return Mechanism(
            NOVEL_REJECTION_CUE,
            "a rejection is phrased with words the attribution cue list does not contain",
        )
    return None


def _fallback_propagation(outcome: CaseOutcome) -> Mechanism | None:
    """The baseline flagged the text and the verdict came from the fallback."""

    if outcome.prediction.baseline != outcome.prediction.categories:
        return None
    if not outcome.prediction.baseline:
        return None
    return Mechanism(
        FALLBACK_PROPAGATION,
        "the semantic fallback reproduced the baseline's verdict on this text",
    )


def _lexical_gap(outcome: CaseOutcome) -> Mechanism | None:
    missing = set(outcome.expected_relations) - set(outcome.found_relations)
    if not missing:
        return None
    return Mechanism(
        LEXICAL_GAP,
        f"no frame matched for {sorted(missing)} in this wording",
    )


def annotation_ambiguity(outcome: CaseOutcome) -> Mechanism | None:
    """Is the label itself open to dispute?

    Two narrow, checkable forms, because "the annotation is arguable" is easy to
    claim and hard to evidence:

    * the expected relation appears only in a negated form, so calling it the
      present relation is a reading rather than a transcription;
    * the expected relation is named by meaning and the text contains none of
      its vocabulary, so the label asserts a relation the words do not carry.
    """

    lowered = outcome.case.text.lower()
    for relation in outcome.expected_relations:
        markers = _RELATION_MARKERS.get(relation, ())
        if not markers:
            continue
        present = [m for m in markers if m in lowered]
        if not present:
            return Mechanism(
                AMBIGUOUS_RELATION_NAME,
                f"the case expects {relation} but the text contains none of "
                f"{list(markers)}, so the label asserts a relation by meaning",
            )
        # RISK_REMOVED's markers are themselves negative - `cannot lose`, `no
        # risk`, `never fall` - so a negator is the relation rather than a
        # modifier of it. Flagging those would call the clearest labels in the
        # benchmark ambiguous, which is the same trap the Phase 8.4 matcher
        # needed a `self_negating` flag to avoid.
        if relation != "RISK_REMOVED" and _NEGATION.search(lowered):
            return Mechanism(
                AMBIGUOUS_NEGATED_RELATION,
                f"{relation} appears only alongside a negation, so whether it is "
                f"the present relation is a reading",
            )
    return None


def diagnose(outcome: CaseOutcome) -> Diagnosis:
    """Classify one failing case."""

    case = outcome.case
    mechanisms: list[Mechanism] = []

    if not outcome.split_ok:
        mechanisms.append(
            Mechanism("claim_split", "the claim count differs from the annotation")
        )
        return _build(
            outcome,
            ATTRIBUTION_ERROR,
            mechanisms,
            "the text was split into a different number of claims",
        )

    speaker_stance_ok = all(outcome.speaker_ok) and all(outcome.stance_ok)
    attribution_mechanism = _novel_source(case.text) or _novel_rejection(case.text)

    relation_missing = bool(set(case.expected_relations) - set(outcome.found_relations))
    relation_extra = bool(set(outcome.found_relations) - set(case.expected_relations))
    inflected = _inflected_verb(case.text)
    gap = _lexical_gap(outcome)

    if not speaker_stance_ok:
        if attribution_mechanism:
            mechanisms.append(attribution_mechanism)
        mechanisms.append(
            Mechanism(
                "speaker_stance",
                f"annotated {list(case.expected_speakers)}/{list(case.expected_stances)}, "
                f"predicted {[c['speaker'] for c in outcome.prediction.claims]}/"
                f"{[c['stance'] for c in outcome.prediction.claims]}",
            )
        )
        if relation_missing:
            mechanisms.append(gap) if gap else None
        # A wrong speaker or stance that produced a wrong decision is an
        # attribution error first: the decision layer acted on what it was told.
        if not outcome.correct:
            return _build(
                outcome,
                ATTRIBUTION_ERROR,
                mechanisms,
                "the speaker or stance was wrong, and the decision followed it",
            )

    if relation_missing:
        if inflected:
            mechanisms.append(inflected)
        if gap:
            mechanisms.append(gap)
        return _build(
            outcome,
            INTENT_DETECTION_ERROR,
            mechanisms,
            "a relation the guide says is present was not found",
        )

    if relation_extra and not outcome.correct:
        mechanisms.append(
            Mechanism(
                "extra_relation",
                f"found {sorted(set(outcome.found_relations) - set(case.expected_relations))} "
                f"which the guide does not place here",
            )
        )
        return _build(
            outcome,
            INTENT_DETECTION_ERROR,
            mechanisms,
            "a relation was found where the guide does not place one",
        )

    propagation = _fallback_propagation(outcome)
    if propagation:
        mechanisms.append(propagation)
        return _build(
            outcome,
            DECISION_POLICY_ERROR,
            mechanisms,
            "the relation layer was silent and the fallback carried the verdict",
        )

    if outcome.prediction.categories == case.categories:
        return _build(
            outcome,
            UNCLASSIFIED,
            mechanisms,
            "the categories match the annotation but the case was scored wrong",
        )

    return _build(
        outcome,
        DECISION_POLICY_ERROR,
        mechanisms,
        "the relation was found and the policy decided against the guide",
    )


def _build(
    outcome: CaseOutcome,
    category: str,
    mechanisms: Sequence[Mechanism],
    explanation: str,
) -> Diagnosis:
    return Diagnosis(
        case_id=outcome.case_id,
        category=category,
        text=outcome.case.text,
        group=outcome.case.group,
        expected=outcome.case.categories,
        predicted=outcome.prediction.categories,
        baseline=outcome.prediction.baseline,
        outcome=outcome.outcome,
        mechanisms=tuple(mechanisms),
        explanation=explanation,
    )


@dataclass(frozen=True, slots=True)
class ErrorAnalysis:
    diagnoses: tuple[Diagnosis, ...]
    case_count: int

    @property
    def error_count(self) -> int:
        return len(self.diagnoses)

    def counts(self) -> Mapping[str, int]:
        buckets = {name: 0 for name in CATEGORIES}
        for item in self.diagnoses:
            buckets[item.category] += 1
        return buckets

    def mechanism_counts(self) -> Mapping[str, int]:
        buckets = {name: 0 for name in MECHANISMS}
        for item in self.diagnoses:
            for mechanism in item.mechanisms:
                if mechanism.name in buckets:
                    buckets[mechanism.name] += 1
        return buckets

    def of_category(self, category: str) -> tuple[Diagnosis, ...]:
        return tuple(d for d in self.diagnoses if d.category == category)

    @property
    def language_gap_cases(self) -> tuple[Diagnosis, ...]:
        """Failures whose mechanism is a language-coverage gap.

        The primary category says **which stage** failed; this says which
        failures were caused by the layer not knowing the wording. The two are
        different questions and a case can be an attribution error *because* the
        source noun was unknown, so this is a cross-cutting view rather than a
        sixth bucket.
        """

        gap_mechanisms = {
            INFLECTED_VERB,
            NOVEL_SOURCE_NOUN,
            NOVEL_REJECTION_CUE,
            LEXICAL_GAP,
        }
        return tuple(
            d
            for d in self.diagnoses
            if {m.name for m in d.mechanisms} & gap_mechanisms
        )

    @property
    def disputed_label_cases(self) -> tuple[Diagnosis, ...]:
        """Failures whose annotation is itself arguable."""

        arguable = {AMBIGUOUS_NEGATED_RELATION, AMBIGUOUS_RELATION_NAME}
        return tuple(
            d for d in self.diagnoses if {m.name for m in d.mechanisms} & arguable
        )

    @property
    def decision_errors(self) -> tuple[Diagnosis, ...]:
        """Failures where the verdict was wrong, as opposed to merely the labels."""

        return tuple(d for d in self.diagnoses if d.predicted != d.expected)

    @property
    def error_rate(self) -> float:
        """Share of cases with any classified failure, verdict or not."""

        return round(self.error_count / self.case_count, 4) if self.case_count else 0.0

    @property
    def decision_error_rate(self) -> float:
        return (
            round(len(self.decision_errors) / self.case_count, 4)
            if self.case_count
            else 0.0
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "cases": self.case_count,
            "classified_failures": self.error_count,
            "any_failure_rate": self.error_rate,
            "decision_errors": len(self.decision_errors),
            "decision_error_rate": self.decision_error_rate,
            "counts": dict(self.counts()),
            "mechanisms": dict(self.mechanism_counts()),
            "language_gap_cases": [d.case_id for d in self.language_gap_cases],
            "disputed_label_cases": [d.case_id for d in self.disputed_label_cases],
            "diagnoses": [item.as_dict() for item in self.diagnoses],
        }

    def render(self) -> str:
        lines = [
            f"cases               : {self.case_count}",
            f"classified failures : {self.error_count} ({self.error_rate:.1%})",
            f"  of which the verdict was wrong : {len(self.decision_errors)} "
            f"({self.decision_error_rate:.1%})",
            f"  of which only the labels were  : "
            f"{self.error_count - len(self.decision_errors)}",
            "",
            "by category:",
        ]
        for name, count in self.counts().items():
            if count:
                lines.append(f"  {name:26} {count}")
        lines.append("")
        lines.append("by mechanism:")
        for name, count in self.mechanism_counts().items():
            if count:
                lines.append(f"  {name:26} {count}")
        lines.append("")
        lines.append(
            f"cross-cutting - unknown language pattern : "
            f"{len(self.language_gap_cases)} "
            f"{[d.case_id for d in self.language_gap_cases]}"
        )
        lines.append(
            f"cross-cutting - annotation ambiguity     : "
            f"{len(self.disputed_label_cases)} "
            f"{[d.case_id for d in self.disputed_label_cases]}"
        )
        return "\n".join(lines)


def analyse(outcomes: Sequence[CaseOutcome], *, case_count: int | None = None) -> ErrorAnalysis:
    """Classify every failing case.

    Two kinds of failure are counted. A **decision error** is a case whose
    categories differ from the annotation, and it is classified by cause. An
    **attribution error** that did not change the verdict is also a failure - the
    speaker or stance is wrong - and is recorded as one rather than dropped for
    being harmless this time. A case can appear once, under its primary cause.
    """

    diagnoses: list[Diagnosis] = []
    seen: set[str] = set()

    for item in outcomes:
        if item.correct:
            continue
        seen.add(item.case_id)
        diagnosis = diagnose(item)
        ambiguity = annotation_ambiguity(item)
        if ambiguity and diagnosis.category in (
            INTENT_DETECTION_ERROR,
            DECISION_POLICY_ERROR,
        ):
            diagnosis = _build(
                item,
                ANNOTATION_AMBIGUITY,
                (*diagnosis.mechanisms, ambiguity),
                f"{diagnosis.explanation}, and the label is arguable",
            )
        elif ambiguity:
            diagnosis = _build(
                item,
                diagnosis.category,
                (*diagnosis.mechanisms, ambiguity),
                diagnosis.explanation,
            )
        diagnoses.append(diagnosis)

    for item in outcomes:
        if item.case_id in seen:
            continue
        if item.split_ok and all(item.speaker_ok) and all(item.stance_ok):
            continue
        mechanisms: list[Mechanism] = []
        for detector in (_novel_source, _novel_rejection):
            found = detector(item.case.text)
            if found:
                mechanisms.append(found)
        mechanisms.append(
            Mechanism(
                "speaker_stance",
                f"annotated {list(item.case.expected_speakers)}/"
                f"{list(item.case.expected_stances)}, predicted "
                f"{[c['speaker'] for c in item.prediction.claims]}/"
                f"{[c['stance'] for c in item.prediction.claims]}",
            )
        )
        diagnoses.append(
            _build(
                item,
                ATTRIBUTION_ERROR,
                mechanisms,
                "the speaker or stance was wrong; the verdict happened to be right",
            )
        )

    return ErrorAnalysis(
        diagnoses=tuple(sorted(diagnoses, key=lambda d: d.case_id)),
        case_count=case_count if case_count is not None else len(outcomes),
    )


def write_report(
    path: str | Path | None = None,
    analysis: ErrorAnalysis | None = None,
) -> Path:
    from .cases import blind_records
    from .evaluation import predict, score

    target = Path(path) if path is not None else ANALYSIS_PATH
    if analysis is None:
        outcomes = score(predict(blind_records())).outcomes
        analysis = analyse(outcomes)
    payload = {
        **analysis.as_dict(),
        "note": (
            "Each failing case is classified and explained. A case the "
            "classifier cannot place is reported as unclassified rather than "
            "forced into a bucket."
        ),
    }
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    import sys

    from .cases import blind_records
    from .evaluation import predict, score

    analysis = analyse(score(predict(blind_records())).outcomes)
    print(analysis.render())
    print()
    for item in analysis.diagnoses:
        print(item.render())
        print()
    if "--write" in sys.argv:
        print(f"wrote {write_report(analysis=analysis)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
