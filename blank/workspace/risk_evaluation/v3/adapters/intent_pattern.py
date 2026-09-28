"""Intent pattern adapter: Phase 8.4's matcher, behind the uniform interface.

Pure delegation. The matcher, the frames, the negation guard and the hedge
detection all come from `risk_evaluation.intent_patterns`; this module converts
`FrameMatch` objects into the v3 `IntentEvidence` shape and decides nothing.

The pattern set is v3's own (`..patterns`), which adds PREDICTION and ADVICE to
the GUARANTEE and RISK_REMOVED relations Phase 8.4 declared. The machinery is
unchanged and unimported - the adapter holds no copy of it.
"""

from __future__ import annotations

import re
from typing import Any

from ...intent_patterns.matcher import RelationMatcher
from ...intent_patterns.model import PatternMatch
from ...v3_repair.negation import classify as classify_negation
from ..model import ClaimInput, IntentEvidence, evidence_strings
from ..patterns import ENTITIES, PATTERNS
from . import AdapterError, AdapterResult


name = "intent_pattern"


def _entity_for(match: PatternMatch, value: str) -> str:
    """Which entity type a role binding belongs to.

    The frame binds a *string*; the entity type is what the lexicon says that
    string is. Reporting the type rather than the text is what lets a decision
    rule say "a guarantee about CAPITAL" without string matching of its own.
    """

    if not value:
        return ""
    for entity in match.entities:
        if entity.value.lower() == value.lower():
            return entity.entity_type
    for entity_type in ENTITIES.names():
        if re.fullmatch(ENTITIES.get(entity_type).pattern, value, re.IGNORECASE):
            return entity_type
    return ""


class IntentPatternAdapter:
    """Relations, entities and frames, from Phase 8.4's matcher."""

    name = name

    def __init__(self, *, matcher: RelationMatcher | None = None) -> None:
        self._matcher = (
            matcher if matcher is not None else RelationMatcher(PATTERNS)
        )

    @property
    def matcher(self) -> RelationMatcher:
        return self._matcher

    def matches(self, text: str) -> tuple[PatternMatch, ...]:
        return self._matcher.match(text)

    def evaluate(self, claim: ClaimInput) -> AdapterResult:
        if not isinstance(claim, ClaimInput):
            raise AdapterError("intent_pattern.evaluate expects a ClaimInput")

        intents: list[IntentEvidence] = []
        evidence: list[str] = []
        matches = self.matches(claim.text)
        for match in matches:
            for frame in match.frames:
                object_value = frame.object_value or frame.subject_value
                entity = _entity_for(match, object_value)
                scope = classify_negation(
                    claim.text,
                    frame_span=frame.span,
                    predicate_span=_predicate_span(claim.text, frame),
                    negated=frame.negated,
                )
                intents.append(
                    IntentEvidence(
                        relation=frame.relation,
                        entity=entity or "UNKNOWN",
                        frame=frame.kind,
                        predicate=frame.predicate,
                        pattern_id=match.pattern_id,
                        span=frame.span,
                        negated=frame.negated,
                        hedge=frame.hedge,
                        negation_scope=scope.scope,
                    )
                )
                evidence.append(_evidence_marker(frame.relation, frame.kind, frame, scope))
                if scope.negated:
                    evidence.append(scope.marker_text)

        if not intents:
            evidence.append("rule:intent_pattern.no-relation")

        asserted = [item for item in intents if item.asserted]
        return AdapterResult(
            adapter=self.name,
            claim_id=claim.claim_id,
            intents=tuple(intents),
            evidence=evidence_strings(evidence),
            confidence=(0.8 if asserted else 0.0),
            detail={
                "patterns": [match.pattern_id for match in matches],
                "asserted": [item.marker for item in asserted],
            },
        )


def _predicate_span(text: str, frame) -> tuple[int, int]:
    """Where the predicate sits, inside the frame.

    The Phase 8.4 `FrameMatch` carries the predicate *text* and the frame span but
    not the predicate's own offsets, and the negation-scope refinement needs them:
    a denial predicate is propositional only when it is outside the predicate.
    Locating the text inside the frame's own span is enough, and falling back to
    the frame span keeps the answer conservative - a marker inside the frame is
    then read as the predicate's own negation, which is what it is.
    """

    if not frame.predicate:
        return frame.span
    start = text.find(frame.predicate, frame.span[0], frame.span[1])
    if start < 0:
        return frame.span
    return start, start + len(frame.predicate)


def _evidence_marker(relation: str, kind: str, frame, scope=None) -> str:
    """A stable, named marker for one frame, as the trace example shows."""

    base = f"{kind}_{relation.lower()}_pattern"
    if frame.negated:
        return f"{base}:negated:{scope.scope}" if scope is not None else f"{base}:negated"
    if frame.hedge:
        return f"{base}:hedged:{frame.hedge}"
    return base


def evaluate(claim: ClaimInput) -> AdapterResult:
    return DEFAULT.evaluate(claim)


DEFAULT = IntentPatternAdapter()
