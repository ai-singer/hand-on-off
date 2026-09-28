"""The unified failure taxonomy: nine types, one precedence order, no ambiguity.

Phase 8.9 classified 151 failures into five classes and its largest bucket was
`lexical_gap` at 106 — a fifth of the whole benchmark in one undifferentiated pile.
That is not actionable: "the vocabulary missed it" does not say whether the evaluator
knows the concept and not the wording, knows the wording and not the form, or knows
both and not the shape. R1 splits it.

    LEXICAL_GAP          the concept is expressed by a word the evaluator has no
                         hook for, and none of the declared tables reach it either
    SYNONYM_GAP          the concept is expressed by a declared synonym of a word the
                         evaluator does have
    MORPHOLOGY_GAP       the concept is expressed by an inflected form of a word the
                         evaluator has, and the surface form is not matched
    FRAME_GAP            every hook the evaluator needs is present in the text and no
                         frame matched, so the shape is unsupported
    ATTRIBUTION_GAP      the speaker was resolved differently from the label
    STANCE_GAP           the stance was resolved differently from the label
    TAXONOMY_CONFLICT    the guide does not settle the case
    ANNOTATION_CONFLICT  the two annotators disagreed, so the label itself is in doubt
    UNKNOWN              none of the above, reported rather than hidden

### Precedence is declared, not implied

The order below is the order the analyzer tests, and it is where the judgement lives.
Two decisions are worth stating outright.

**A doubtful label outranks everything.** A case the adjudication never settled is
reported as UNKNOWN, and one where the adjudicator needed a third reading is a
TAXONOMY_CONFLICT, even if the vocabulary also missed it. The first question about a
failure is whether the label is solid, and a classification that answered the second
question first would build repairs on sand.

**The cheapest explanation wins among the evaluator's own gaps.** If the text
contains an inflected form of a word the evaluator already has, that is a
MORPHOLOGY_GAP and not a FRAME_GAP, because the form is the smaller thing to
explain and the smaller thing to fix. SYNONYM_GAP beats LEXICAL_GAP for the same
reason.

`RULES` is the table, `classify` applies it, and the analyzer supplies the evidence.
Nothing here reads the evaluator; this module is the standard, and the analyzer is
what measures against it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .model import Evidence, FailureRecord, RepairCandidate

LEXICAL_GAP = "LEXICAL_GAP"
SYNONYM_GAP = "SYNONYM_GAP"
MORPHOLOGY_GAP = "MORPHOLOGY_GAP"
FRAME_GAP = "FRAME_GAP"
ATTRIBUTION_GAP = "ATTRIBUTION_GAP"
STANCE_GAP = "STANCE_GAP"
TAXONOMY_CONFLICT = "TAXONOMY_CONFLICT"
ANNOTATION_CONFLICT = "ANNOTATION_CONFLICT"
UNKNOWN = "UNKNOWN"

#: The nine types, as the canonical listing. This is *not* the order the analyzer tests
#: them in: two types have more than one rule, and the unresolved-label rule runs before
#: every other. The applied order lives in `RULES`, and `PRECEDENCE` is derived from
#: `RULES` so a declared number cannot disagree with the order `classify` walks.
FAILURE_TYPES: tuple[str, ...] = (
    ANNOTATION_CONFLICT,
    TAXONOMY_CONFLICT,
    ATTRIBUTION_GAP,
    STANCE_GAP,
    MORPHOLOGY_GAP,
    SYNONYM_GAP,
    FRAME_GAP,
    LEXICAL_GAP,
    UNKNOWN,
)

MEANING: Mapping[str, str] = {
    ANNOTATION_CONFLICT: "the two annotators disagreed on this case's label",
    TAXONOMY_CONFLICT: "the guide does not settle the case",
    ATTRIBUTION_GAP: "the speaker was resolved differently from the label",
    STANCE_GAP: "the stance was resolved differently from the label",
    MORPHOLOGY_GAP: "an inflected form of a known word was not matched",
    SYNONYM_GAP: "a declared synonym of a known word was not matched",
    FRAME_GAP: "the hooks are present and no frame matched",
    LEXICAL_GAP: "the concept has no hook at all, in any declared table",
    UNKNOWN: "not explained by any declared rule",
}

#: Which repair a type implies. Recorded here rather than in the analyzer so the
#: classification and the repair it suggests cannot drift apart.
REPAIR_TYPE: Mapping[str, str] = {
    ANNOTATION_CONFLICT: "annotation_review",
    TAXONOMY_CONFLICT: "taxonomy_review",
    ATTRIBUTION_GAP: "attribution_extension",
    STANCE_GAP: "stance_extension",
    MORPHOLOGY_GAP: "morphology_extension",
    SYNONYM_GAP: "synonym_extension",
    FRAME_GAP: "frame_extension",
    LEXICAL_GAP: "lexical_extension",
    UNKNOWN: "none",
}

REPAIR_TYPES: tuple[str, ...] = tuple(sorted(set(REPAIR_TYPE.values())))

#: Types the framework can turn into a generated test case by itself, because the
#: rule that produces one is declared: an inflection table, a synonym table, a frame
#: template. The two conflicts and UNKNOWN are not here and cannot be, because the
#: first thing to settle is the label or the guide, not the evaluator.
AUTO_GENERATABLE: tuple[str, ...] = (
    MORPHOLOGY_GAP,
    SYNONYM_GAP,
    FRAME_GAP,
    LEXICAL_GAP,
)

#: Types that require a human decision before any repair is attempted.
HUMAN_REQUIRED: tuple[str, ...] = (
    ANNOTATION_CONFLICT,
    TAXONOMY_CONFLICT,
    UNKNOWN,
    ATTRIBUTION_GAP,
    STANCE_GAP,
)


@dataclass(frozen=True, slots=True)
class Rule:
    """One classification rule: what it tests and what it produces."""

    failure_type: str
    requires: tuple[str, ...]
    summary: str

    def as_dict(self) -> dict[str, object]:
        return {
            "failure_type": self.failure_type,
            "requires": list(self.requires),
            "summary": self.summary,
            "precedence": PRECEDENCE[self.failure_type],
            "repair_type": REPAIR_TYPE[self.failure_type],
            "auto_generatable": self.failure_type in AUTO_GENERATABLE,
        }


#: The rules, in precedence order. `requires` names the evidence items the analyzer
#: must supply for the rule to fire, so a classification can never be made without
#: the observation that justifies it.
#:
#: Two orderings here are load-bearing, and both were corrected after measuring the
#: Phase 8.9 set.
#:
#: `annotation_unresolved` comes first because a case whose label the adjudication
#: never settled cannot support a repair proposal at all — classifying it as a
#: vocabulary gap would be proposing a fix for an unknown target.
#:
#: TAXONOMY_CONFLICT precedes ANNOTATION_CONFLICT because a third reading *is* a
#: disagreement; with the opposite order every third reading would be absorbed by the
#: broader annotation rule and this type could never fire. TAXONOMY_CONFLICT is the
#: narrower, more informative reading, so it is tested first.
RULES: tuple[Rule, ...] = (
    Rule(
        UNKNOWN,
        ("annotation_unresolved",),
        "the adjudication left this case unresolved, so no repair has a defined target",
    ),
    Rule(
        TAXONOMY_CONFLICT,
        ("adjudicator_third_reading",),
        "the adjudicator ruled a reading neither annotator proposed, or declined",
    ),
    Rule(
        ANNOTATION_CONFLICT,
        ("annotators_disagreed",),
        "the annotators differed on the decision set for this case",
    ),
    Rule(
        ATTRIBUTION_GAP,
        ("speaker_mismatch",),
        "the label's speaker and the resolved speaker differ decisively",
    ),
    Rule(
        STANCE_GAP,
        ("stance_mismatch", "speaker_match"),
        "the speakers agree and the stances differ",
    ),
    Rule(
        MORPHOLOGY_GAP,
        ("known_lemma_unmatched_form",),
        "a token is an inflected form of a word in an evaluator lexicon",
    ),
    Rule(
        SYNONYM_GAP,
        ("declared_synonym_present",),
        "a token is a declared synonym of a word in an evaluator lexicon",
    ),
    Rule(
        FRAME_GAP,
        ("hooks_present", "no_frame_matched", "relation_cue_present"),
        "an entity hook and a relation cue are both present and nothing fired, so the "
        "frame declined on structure rather than on wording",
    ),
    Rule(
        FRAME_GAP,
        ("capability_declined",),
        "a capability layer examined the structure and declined it, so no word list "
        "would have changed the outcome",
    ),
    Rule(
        LEXICAL_GAP,
        ("no_hook_at_all",),
        "no evaluator lexicon entry, declared synonym or inflected form is present",
    ),
    Rule(
        LEXICAL_GAP,
        ("no_relation_cue",),
        "an entity hook is present but the relation has no cue word in the text, in "
        "any form the evaluator declares or could inflect",
    ),
)


class TaxonomyError(Exception):
    """Raised when a classification cannot be made."""


#: The precedence actually applied: a dense rank, in order of first appearance in the
#: rule table. A type with more than one rule takes the rank of its first, which is the
#: position at which it can first be returned.
#:
#: This used to be derived from `FAILURE_TYPES`, whose order is a canonical listing
#: rather than an application order; the two diverged the moment the unresolved-label
#: rule was placed ahead of everything and the third-reading rule ahead of the broader
#: annotation rule. `Rule.as_dict()["precedence"]` then reported a number contradicting
#: `classify`, and anything sorting rules by that field got the wrong order. The rank is
#: kept dense — 0 through 8 with no gaps — so a consumer may still read it as an order.
PRECEDENCE: Mapping[str, int] = {
    failure_type: rank
    for rank, failure_type in enumerate(
        dict.fromkeys(rule.failure_type for rule in RULES)
    )
}


#: The rule of last resort. Distinct from `RULES[0]`, which is also UNKNOWN but for a
#: specific reason — an unsettled label. Conflating the two made the fallback
#: unreachable: `rule_for(UNKNOWN)` scanned `RULES`, matched the label rule first, and
#: every unexplained case was then rejected for lacking `annotation_unresolved`.
UNEXPLAINED = Rule(UNKNOWN, ("no_rule_matched",), MEANING[UNKNOWN])


def rule_for(failure_type: str) -> Rule:
    if failure_type == UNKNOWN:
        return UNEXPLAINED
    for item in RULES:
        if item.failure_type == failure_type:
            return item
    raise TaxonomyError(f"unknown failure type {failure_type!r}")


def classify(evidence: Sequence[Evidence]) -> tuple[str, Rule]:
    """Apply the precedence order to a body of evidence.

    The first rule whose required evidence is all present wins. `UNKNOWN` is what
    remains, and it is a result rather than an error: a failure the taxonomy cannot
    explain is reported as unexplained so that the taxonomy's coverage is visible.
    """

    names = {item.name for item in evidence}
    for item in RULES:
        if all(name in names for name in item.requires):
            return item.failure_type, item
    return UNKNOWN, UNEXPLAINED


def repair_for(
    failure_type: str,
    *,
    risk_category: str,
    additions: Sequence[str] = (),
    target: str = "",
) -> RepairCandidate | None:
    """The repair a type implies, or None when the type implies none."""

    repair_type = REPAIR_TYPE.get(failure_type)
    if repair_type in (None, "none"):
        return None
    return RepairCandidate(
        type=repair_type,
        risk_category=risk_category,
        additions=tuple(additions),
        target=target,
    )


def build_record(
    *,
    case_id: str,
    input_text: str,
    expected: Sequence[str],
    actual: Sequence[str],
    evidence: Sequence[Evidence],
    risk_category: str = "",
    additions: Sequence[str] = (),
    target: str = "",
    **extra: object,
) -> FailureRecord:
    """Classify one case and build its record."""

    if not evidence:
        raise TaxonomyError(f"{case_id}: a failure record needs evidence")
    failure_type, rule = classify(evidence)
    category = risk_category or (expected[0] if expected else "")
    present = {item.name for item in evidence}
    missing = tuple(name for name in rule.requires if name not in present)
    if missing:
        raise TaxonomyError(
            f"{case_id}: rule for {failure_type} requires {list(missing)}, "
            "which the evidence does not supply"
        )
    return FailureRecord(
        case_id=case_id,
        input_text=input_text,
        expected=tuple(expected),
        actual=tuple(actual),
        failure_type=failure_type,
        evidence=tuple(evidence),
        repair_candidate=repair_for(
            failure_type, risk_category=category, additions=additions, target=target
        ),
        required_evidence=tuple(rule.requires),
        **extra,  # type: ignore[arg-type]
    )


def describe() -> dict[str, object]:
    """The taxonomy, for the report and the tests."""

    return {
        "types": list(FAILURE_TYPES),
        "meaning": dict(MEANING),
        "precedence": dict(PRECEDENCE),
        "repair_type": dict(REPAIR_TYPE),
        "auto_generatable": list(AUTO_GENERATABLE),
        "human_required": list(HUMAN_REQUIRED),
        "rules": [item.as_dict() for item in RULES],
    }


def counts_by_type(failures: Sequence[FailureRecord]) -> Mapping[str, int]:
    counts = {name: 0 for name in FAILURE_TYPES}
    for item in failures:
        counts[item.failure_type] = counts.get(item.failure_type, 0) + 1
    return counts
