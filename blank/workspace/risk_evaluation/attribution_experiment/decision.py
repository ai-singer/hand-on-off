"""Decision logic: which claim-level detections become the article's risk.

The phase's three rules, stated once and implemented as named predicates:

    R1  only `speaker=author` AND `stance=endorsed` raises the risk weight
    R2  `speaker=third_party` AND `stance=quoted` must not become author risk
    R3  `speaker=author` AND `stance=rejected` must not be risk

Two readings of R1 are possible and they are not equivalent, so both are
implemented and the difference is measured rather than assumed.

**Reading A - suppression only.** R2 and R3 say what must *not* be risk. R1 says
what is *elevated*. A claim covered by neither is left with the baseline's
verdict. This is the literal reading, and it is the one used by default.

**Reading B - authorial filter.** Anything not the article's own voice is
suppressed. This generalises R2 from `third_party+quoted` to every non-authorial
combination, and it recovers cases such as `A broker told clients the fund cannot
lose money.` where the speaker is `unknown` rather than `third_party`.

Neither reading is obviously right, and the experiment reports both because the
choice is a policy decision, not a fact.

One exception applies to both: `unverified_information` is declared
attribution-agnostic by `taxonomy_v2` - reporting an uncheckable source is a risk
whatever the voice. Dropping it would be an experiment artefact rather than an
improvement, so it is kept regardless of who is speaking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..attribution.analyzer import to_statement_source
from ..attribution.model import Claim
from ..model import RiskEvaluationResult
from ..taxonomy_v2 import ATTRIBUTION_AGNOSTIC_CATEGORIES


#: Rule identifiers, recorded in evidence so a decision can be traced.
R1_AUTHOR_ENDORSED = "R1-author-endorsed"
R2_THIRD_PARTY_QUOTED = "R2-third-party-quoted"
R3_AUTHOR_REJECTED = "R3-author-rejected"
R4_ATTRIBUTION_AGNOSTIC = "R4-attribution-agnostic"
R5_NOT_AUTHORIAL = "R5-not-authorial"
R6_BASELINE_VERDICT = "R6-baseline-verdict"

STRICT = "strict-rules"
AUTHORIAL = "authorial-filter"
POLICIES = (STRICT, AUTHORIAL)


def raises_risk_weight(claim: Claim) -> bool:
    """R1: the claim is the article's own assertion."""

    return claim.speaker == "author" and claim.stance == "endorsed"


def is_third_party_quotation(claim: Claim) -> bool:
    """R2: a reported third-party claim, not the article's."""

    return claim.speaker == "third_party" and claim.stance == "quoted"


def is_author_rejection(claim: Claim) -> bool:
    """R3: the article arguing against something."""

    return claim.speaker == "author" and claim.stance == "rejected"


def is_attribution_agnostic(category: str) -> bool:
    """Categories `taxonomy_v2` reports whatever the voice."""

    return category in ATTRIBUTION_AGNOSTIC_CATEGORIES


@dataclass(frozen=True, slots=True)
class ClaimDecision:
    """One claim's detections, and what the policy did with them."""

    claim: Claim
    statement_source: str
    detected: tuple[str, ...]
    kept: tuple[str, ...]
    dropped: tuple[str, ...]
    rules: tuple[str, ...]
    weight_raised: bool
    reason: str = ""

    @property
    def claim_id(self) -> str:
        return self.claim.claim_id

    @property
    def suppressed(self) -> bool:
        return not self.kept and bool(self.detected)

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "text": self.claim.text,
            "speaker": self.claim.speaker,
            "stance": self.claim.stance,
            "statement_source": self.statement_source,
            "is_authorial": self.claim.is_authorial,
            "detected": list(self.detected),
            "kept": list(self.kept),
            "dropped": list(self.dropped),
            "rules": list(self.rules),
            "weight_raised": self.weight_raised,
            "reason": self.reason,
            "evidence": list(self.claim.evidence),
        }

    def render(self) -> str:
        state = "kept" if self.kept else ("dropped" if self.detected else "silent")
        return (
            f"{self.claim_id} [{state}] {self.claim.speaker}/{self.claim.stance} "
            f"detected={list(self.detected)} rules={list(self.rules)}"
        )


def decide_claim(
    claim: Claim,
    detected: Sequence[str],
    *,
    policy: str = STRICT,
) -> ClaimDecision:
    """Apply the decision policy to one claim's detections."""

    if policy not in POLICIES:
        raise ValueError(f"policy must be one of {POLICIES}, got {policy!r}")

    categories = tuple(sorted({str(name) for name in detected}))
    kept: list[str] = []
    dropped: list[str] = []
    rules: list[str] = []
    raised = raises_risk_weight(claim)

    suppressed_by: str = ""
    if is_author_rejection(claim):
        suppressed_by = R3_AUTHOR_REJECTED
    elif is_third_party_quotation(claim):
        suppressed_by = R2_THIRD_PARTY_QUOTED
    elif policy == AUTHORIAL and not claim.is_authorial:
        suppressed_by = R5_NOT_AUTHORIAL

    for category in categories:
        if is_attribution_agnostic(category):
            kept.append(category)
            if suppressed_by:
                rules.append(R4_ATTRIBUTION_AGNOSTIC)
            continue
        if suppressed_by:
            dropped.append(category)
            rules.append(suppressed_by)
            continue
        kept.append(category)
        if raised:
            rules.append(R1_AUTHOR_ENDORSED)
        else:
            rules.append(R6_BASELINE_VERDICT)

    return ClaimDecision(
        claim=claim,
        statement_source=to_statement_source(claim),
        detected=categories,
        kept=tuple(kept),
        dropped=tuple(dropped),
        rules=tuple(dict.fromkeys(rules)),
        weight_raised=raised,
        reason=suppressed_by,
    )


def merge_results(
    decisions: Sequence[ClaimDecision],
    per_claim: Mapping[str, Sequence[RiskEvaluationResult]],
) -> tuple[RiskEvaluationResult, ...]:
    """Combine kept claim detections into one decision.

    Where two claims keep the same category, the higher-confidence detection
    wins and both claim ids are recorded as its sources, so a merged result can
    still be traced back to the claims that produced it.
    """

    best: dict[str, RiskEvaluationResult] = {}
    sources: dict[str, list[str]] = {}
    for decision in decisions:
        for result in per_claim.get(decision.claim_id, ()):
            if result.category not in decision.kept:
                continue
            sources.setdefault(result.category, []).append(decision.claim_id)
            current = best.get(result.category)
            if current is None or result.confidence > current.confidence:
                best[result.category] = result

    merged: list[RiskEvaluationResult] = []
    for category in sorted(best):
        result = best[category]
        merged.append(
            RiskEvaluationResult(
                category=result.category,
                intent=result.intent,
                confidence=result.confidence,
                evidence_required=result.evidence_required,
                severity=result.severity,
                action=result.action,
                evaluator=result.evaluator,
                detail=result.detail,
                source_ids=tuple(sources[category]),
                candidates=result.candidates,
            )
        )
    return tuple(merged)


@dataclass(frozen=True, slots=True)
class DecisionSummary:
    """Counts over one decision."""

    claims: int
    kept_claims: int
    suppressed_claims: int
    weight_raised: int
    dropped_categories: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "claims": self.claims,
            "kept_claims": self.kept_claims,
            "suppressed_claims": self.suppressed_claims,
            "weight_raised": self.weight_raised,
            "dropped_categories": list(self.dropped_categories),
        }


def summarise(decisions: Sequence[ClaimDecision]) -> DecisionSummary:
    dropped: list[str] = []
    for decision in decisions:
        dropped.extend(decision.dropped)
    return DecisionSummary(
        claims=len(decisions),
        kept_claims=sum(1 for item in decisions if item.kept),
        suppressed_claims=sum(1 for item in decisions if item.suppressed),
        weight_raised=sum(1 for item in decisions if item.weight_raised),
        dropped_categories=tuple(sorted(set(dropped))),
    )
