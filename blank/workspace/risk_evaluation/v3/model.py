"""The unified risk evaluation data model.

Phase 8.5's job is to make the experimental layers compose. This module defines
the object they compose into, and it exists because the three layers were built
to three different contracts:

    Phase 8.2 attribution      Claim(speaker, stance, evidence)
    Phase 8.4 intent patterns  PatternMatch(frames, entities, evidence)
    semantic_evaluator_v2      RiskEvaluationResult(category, action, ...)

A `RiskClaim` is one claim carrying all three, plus the span it came from.

Two constraints are enforced structurally rather than documented:

**Every claim has evidence.** `RiskClaim.__post_init__` raises if `evidence` is
empty. A claim whose speaker and stance cannot be evidenced is not a claim this
pipeline is allowed to report.

**No decision without evidence.** `RiskDecision.__post_init__` raises if its
evidence is empty, so "why was this flagged?" always has an answer that points
at something in the text or at a named rule.

**The span survives.** `source_span` is kept on the claim, so a final category
can always be traced back to the characters that produced it. Returning only
categories is what made the Phase 8.1 defect hard to see: the verdict was there
and the reason was not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..attribution.model import SPEAKERS, STANCES


V3_VERSION = "3.0.0-experimental"

#: Relations the v3 intent layer understands.
GUARANTEE = "GUARANTEE"
RISK_REMOVED = "RISK_REMOVED"
PREDICTION = "PREDICTION"
ADVICE = "ADVICE"
RELATIONS = (GUARANTEE, RISK_REMOVED, PREDICTION, ADVICE)

#: Entity types the intent layer can report.
RETURN = "RETURN"
CAPITAL = "CAPITAL"
VALUE = "VALUE"
OUTCOME = "OUTCOME"
INSTRUMENT = "INSTRUMENT"
REVENUE = "REVENUE"

#: The four the phase names, plus two the advice and prediction relations need.
#: `You should buy this stock` has no object among the four: a stock is not a
#: return, a capital amount, a value or an outcome.
CORE_ENTITIES = (RETURN, CAPITAL, VALUE, OUTCOME)
EXTENDED_ENTITIES = (INSTRUMENT, REVENUE)
ENTITY_NAMES = (*CORE_ENTITIES, *EXTENDED_ENTITIES)

#: Frame kinds, from the Phase 8.4 model.
FRAMES = ("active", "passive", "copular", "attributive", "nominal")


class ModelError(Exception):
    """Raised when a claim or decision violates the model contract."""


@dataclass(frozen=True, slots=True)
class ClaimInput:
    """What an adapter is handed: one claim, and the text it came from.

    `source_text` is carried because attribution is not a per-sentence
    question - a rejection in the next sentence decides the stance of this one -
    while the intent and semantic adapters only need the claim itself.
    """

    claim_id: str
    text: str
    span: tuple[int, int]
    source_text: str
    index: int = 0

    def __post_init__(self) -> None:
        if not self.claim_id.strip():
            raise ModelError("a claim input needs an id")
        if not self.text.strip():
            raise ModelError(f"{self.claim_id}: text must not be empty")
        start, end = self.span
        if start < 0 or end < start:
            raise ModelError(f"{self.claim_id}: bad span {self.span!r}")

    @property
    def context(self) -> str:
        """The span as it appears in the source, for verification."""

        return self.source_text[self.span[0] : self.span[1]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "text": self.text,
            "span": list(self.span),
            "index": self.index,
        }


@dataclass(frozen=True, slots=True)
class IntentEvidence:
    """One relation the intent layer found in a claim."""

    relation: str
    entity: str
    frame: str
    predicate: str
    pattern_id: str
    span: tuple[int, int]
    negated: bool = False
    hedge: str = ""

    def __post_init__(self) -> None:
        if self.relation not in RELATIONS:
            raise ModelError(f"unknown relation {self.relation!r}")
        if self.frame not in FRAMES:
            raise ModelError(f"unknown frame {self.frame!r}")
        if not self.pattern_id.strip():
            raise ModelError("intent evidence must name the pattern that fired")

    @property
    def asserted(self) -> bool:
        return not self.negated and not self.hedge

    @property
    def marker(self) -> str:
        """The evidence string this relation contributes to the claim."""

        state = "negated" if self.negated else ("hedged" if self.hedge else "asserted")
        return f"{self.relation.lower()}:{self.entity.lower()}:{self.frame}:{state}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "relation": self.relation,
            "entity": self.entity,
            "frame": self.frame,
            "predicate": self.predicate,
            "pattern_id": self.pattern_id,
            "span": list(self.span),
            "negated": self.negated,
            "hedge": self.hedge,
            "asserted": self.asserted,
        }

    def render(self) -> str:
        state = "" if self.asserted else f" ({'negated' if self.negated else 'hedged'})"
        return f"{self.relation}({self.entity}) [{self.frame}] {self.predicate}{state}"


@dataclass(frozen=True, slots=True)
class RiskClaim:
    """One claim with who said it, what relation it carries, and the evidence."""

    claim_id: str
    text: str
    source_span: tuple[int, int]
    speaker: str
    stance: str
    evidence: tuple[str, ...]
    intents: tuple[IntentEvidence, ...] = ()
    confidence: float = 0.5
    attribution_evidence: tuple[str, ...] = ()
    fallback_categories: tuple[str, ...] = ()
    fallback_evidence: tuple[str, ...] = ()
    intent_available: bool = True

    def __post_init__(self) -> None:
        if not self.claim_id.strip():
            raise ModelError("a claim needs an id")
        if not self.text.strip():
            raise ModelError(f"{self.claim_id}: text must not be empty")
        if self.speaker not in SPEAKERS:
            raise ModelError(
                f"{self.claim_id}: speaker must be one of {SPEAKERS}, got {self.speaker!r}"
            )
        if self.stance not in STANCES:
            raise ModelError(
                f"{self.claim_id}: stance must be one of {STANCES}, got {self.stance!r}"
            )
        # Constraint 1 and 2 from the phase: no claim, and therefore no decision
        # taken from it, may exist without evidence.
        if not self.evidence:
            raise ModelError(
                f"{self.claim_id}: every claim must carry evidence for its "
                f"speaker, stance and intent"
            )
        start, end = self.source_span
        if start < 0 or end < start:
            raise ModelError(f"{self.claim_id}: bad source span {self.source_span!r}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ModelError(
                f"{self.claim_id}: confidence must be within 0..1, got {self.confidence}"
            )
        object.__setattr__(self, "evidence", tuple(str(item) for item in self.evidence))
        object.__setattr__(self, "intents", tuple(self.intents))

    @property
    def is_authorial(self) -> bool:
        """Is the article advancing this claim?

        `endorsed` counts even when the speaker is a third party: taking up
        somebody else's claim is making it. An unmarked claim is the default
        voice and counts too, because the taxonomy treats unmarked text as the
        author's.

        A **rejected** claim does not count, whatever the speaker. The rejecting
        segment is the author's act, but the claim it rejects is the thing being
        argued against, and the property is about the claim rather than about
        who uttered the sentence.
        """

        if self.stance == "rejected":
            return False
        if self.speaker == "author" or self.stance == "endorsed":
            return True
        return self.speaker == "unknown" and self.stance == "uncertain"

    @property
    def is_rejected(self) -> bool:
        return self.stance == "rejected"

    @property
    def asserted_intents(self) -> tuple[IntentEvidence, ...]:
        return tuple(item for item in self.intents if item.asserted)

    @property
    def relations(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.relation for item in self.asserted_intents))

    def intent_for(self, relation: str) -> IntentEvidence | None:
        for item in self.asserted_intents:
            if item.relation == relation:
                return item
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "text": self.text,
            "source_span": list(self.source_span),
            "speaker": self.speaker,
            "stance": self.stance,
            "confidence": self.confidence,
            "is_authorial": self.is_authorial,
            "evidence": list(self.evidence),
            "attribution_evidence": list(self.attribution_evidence),
            "intent_evidence": [item.as_dict() for item in self.intents],
            "fallback_categories": list(self.fallback_categories),
            "fallback_evidence": list(self.fallback_evidence),
            "intent_available": self.intent_available,
        }

    def render(self) -> str:
        return (
            f"{self.claim_id} {self.speaker}/{self.stance} "
            f"span={list(self.source_span)} intents={[i.relation for i in self.intents]}"
        )


@dataclass(frozen=True, slots=True)
class RiskDecision:
    """One category decided for one claim, with the rule and the evidence."""

    claim_id: str
    category: str
    action: str
    rule: str
    evidence: tuple[str, ...]
    kept: bool = True
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.category.strip():
            raise ModelError("a decision needs a category")
        if not self.action.strip():
            raise ModelError(f"{self.claim_id}: a decision needs an action")
        if not self.rule.strip():
            raise ModelError(f"{self.claim_id}: a decision must name its rule")
        # Constraint 2: a risk decision without evidence is not allowed.
        if not self.evidence:
            raise ModelError(
                f"{self.claim_id}/{self.category}: a decision must carry evidence"
            )
        object.__setattr__(self, "evidence", tuple(str(item) for item in self.evidence))

    @property
    def suppressed(self) -> bool:
        return not self.kept

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "category": self.category,
            "action": self.action,
            "rule": self.rule,
            "evidence": list(self.evidence),
            "kept": self.kept,
            "reason": self.reason,
        }

    def render(self) -> str:
        state = "" if self.kept else " (suppressed)"
        return f"{self.category} -> {self.action} [{self.rule}]{state}"


@dataclass(frozen=True, slots=True)
class ClaimTrace:
    """Everything that happened to one claim, in pipeline order."""

    claim: RiskClaim
    decisions: tuple[RiskDecision, ...] = ()
    suppressed: tuple[RiskDecision, ...] = ()

    @property
    def claim_id(self) -> str:
        return self.claim.claim_id

    @property
    def categories(self) -> tuple[str, ...]:
        return tuple(sorted({item.category for item in self.decisions if item.kept}))

    def as_dict(self) -> dict[str, Any]:
        """The documented trace shape, plus the fields that make it auditable."""

        primary = self.claim.asserted_intents[0] if self.claim.asserted_intents else None
        kept = [item for item in self.decisions if item.kept]
        return {
            "claim": self.claim.text,
            "claim_id": self.claim_id,
            "source_span": list(self.claim.source_span),
            "speaker": self.claim.speaker,
            "stance": self.claim.stance,
            "intent": (
                {"relation": primary.relation, "entity": primary.entity}
                if primary is not None
                else None
            ),
            "intents": [item.as_dict() for item in self.claim.intents],
            "evidence": list(self.claim.evidence),
            "decision": (
                {"category": kept[0].category, "action": kept[0].action}
                if kept
                else None
            ),
            "decisions": [item.as_dict() for item in self.decisions],
            "suppressed": [item.as_dict() for item in self.suppressed],
            "fallback_categories": list(self.claim.fallback_categories),
        }

    def render(self) -> str:
        lines = [
            f"claim {self.claim_id} [{self.claim.speaker}/{self.claim.stance}] "
            f"span={list(self.claim.source_span)}",
            f"    text      : {self.claim.text}",
        ]
        for intent in self.claim.intents:
            lines.append(f"    intent    : {intent.render()}")
        lines.append(f"    evidence  : {list(self.claim.evidence)}")
        for item in self.decisions:
            lines.append(f"    decision  : {item.render()}")
        for item in self.suppressed:
            lines.append(f"    suppressed: {item.render()} ({item.reason})")
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class RiskEvaluationResult:
    """The pipeline's output for one text."""

    text: str
    claims: tuple[RiskClaim, ...]
    traces: tuple[ClaimTrace, ...]
    final_decision: tuple[RiskDecision, ...]
    baseline: tuple[str, ...] = ()
    version: str = V3_VERSION
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", dict(self.evidence))

    @property
    def categories(self) -> tuple[str, ...]:
        return tuple(sorted({item.category for item in self.final_decision}))

    @property
    def actions(self) -> Mapping[str, str]:
        return {item.category: item.action for item in self.final_decision}

    @property
    def flagged(self) -> bool:
        return bool(self.final_decision)

    @property
    def baseline_flagged(self) -> bool:
        return bool(self.baseline)

    def trace_for(self, claim_id: str) -> ClaimTrace:
        for item in self.traces:
            if item.claim_id == claim_id:
                return item
        raise ModelError(f"no trace for claim {claim_id!r}")

    def trace_dicts(self) -> tuple[dict[str, Any], ...]:
        return tuple(item.as_dict() for item in self.traces)

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "text": self.text,
            "categories": list(self.categories),
            "actions": dict(sorted(self.actions.items())),
            "baseline": list(self.baseline),
            "claims": [item.as_dict() for item in self.claims],
            "trace": [item.as_dict() for item in self.traces],
            "evidence": dict(sorted(self.evidence.items(), key=lambda kv: kv[0])),
        }

    def render(self) -> str:
        lines = [
            f"v3 {self.version}",
            f"text       : {self.text}",
            f"baseline   : {list(self.baseline)}",
            f"v3         : {list(self.categories)}",
        ]
        for trace in self.traces:
            lines.append(trace.render())
        return "\n".join(lines)


def evidence_strings(*groups: Sequence[str]) -> tuple[str, ...]:
    """Merge evidence groups, de-duplicated, in first-seen order."""

    seen: dict[str, None] = {}
    for group in groups:
        for item in group:
            if item:
                seen.setdefault(str(item), None)
    return tuple(seen)
