"""The decision policy: explicit rules, each producing its own evidence.

The phase names three cases and they are the spine of this module.

**Case 1 - author, endorsed, GUARANTEE** becomes the article's guarantee:
`financial_guarantee`, `block`.

**Case 2 - third party, quoted, GUARANTEE** must not become the article's risk.
It becomes `unverified_information` with `require_evidence`: the claim is still
worth reporting, but as an unchecked source rather than as the article's promise.

**Case 3 - author, rejected** must not inherit the rejected claim's risk. The
rejection is the article arguing against something, and arguing against a
guarantee is the opposite of making one.

The rules are an ordered table rather than a chain of conditions, so each one can
be read, tested and cited by id in a trace. Every rule returns its own evidence
strings, which is what makes Phase 8.5's trace requirement satisfiable: a
decision can always name the rule and the finding it acted on.

Order matters and is deliberate:

    negation and hedging first   a negated or reported guarantee is not asserted
    rejection next               an argument against a claim is not the claim
    author-voice relations       the article's own risk
    attribution-agnostic         sourcing, which survives every voice
    fallback                     whatever the semantic layer added
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..taxonomy import category as taxonomy_category
from ..taxonomy_v2 import ATTRIBUTION_AGNOSTIC_CATEGORIES
from .model import (
    ADVICE,
    GUARANTEE,
    PREDICTION,
    RELATIONS,
    RISK_REMOVED,
    ClaimInput,
    ModelError,
    RiskClaim,
    RiskDecision,
    evidence_strings,
)
from .patterns import RELATION_CATEGORY


#: Rule ids, cited in every trace.
R_NEGATED = "D1-negated-intent"
R_HEDGED = "D2-hedged-intent"
R_REJECTED = "D3-author-rejected"
R_THIRD_PARTY = "D4-third-party-unverified"
R_AUTHOR_RELATION = "D5-author-voice-relation"
R_AUTHOR_ENDORSED = "D6-author-endorsed-relation"
R_AGNOSTIC = "D7-attribution-agnostic"
R_FALLBACK = "D8-semantic-fallback"
R_NO_EVIDENCE = "D9-no-evidence"

#: Actions the policy can emit. `block` and `require_evidence` come from the
#: taxonomy; `review` is the phase's word for a block-severity category whose
#: claim is real but whose wording is drawn from a relation the intent layer
#: derived rather than the semantic layer.
BLOCK = "block"
REVIEW = "review"
REQUIRE_EVIDENCE = "require_evidence"
DOWNRANK = "downrank"

ACTIONS = (BLOCK, REVIEW, REQUIRE_EVIDENCE, DOWNRANK)


@dataclass(frozen=True, slots=True)
class DecisionRule:
    """One policy rule: when it applies and what it emits."""

    rule_id: str
    description: str
    base_action: str

    def as_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "description": self.description,
            "base_action": self.base_action,
        }


RULES: tuple[DecisionRule, ...] = (
    DecisionRule(
        R_NEGATED,
        "the intent frame is negated, so the relation is not asserted",
        DOWNRANK,
    ),
    DecisionRule(
        R_HEDGED,
        "the intent frame is reported or conditional, so it is not the article's",
        DOWNRANK,
    ),
    DecisionRule(
        R_REJECTED,
        "the article argues against this claim, so it does not inherit its risk",
        DOWNRANK,
    ),
    DecisionRule(
        R_THIRD_PARTY,
        "a quoted third party's relation becomes an unverified source",
        REQUIRE_EVIDENCE,
    ),
    DecisionRule(
        R_AUTHOR_ENDORSED,
        "the author endorses the claim, so the relation is the article's risk",
        BLOCK,
    ),
    DecisionRule(
        R_AUTHOR_RELATION,
        "an author-voiced claim carrying the relation",
        REVIEW,
    ),
    DecisionRule(
        R_AGNOSTIC,
        "sourcing risk survives whatever the voice",
        REQUIRE_EVIDENCE,
    ),
    DecisionRule(
        R_FALLBACK,
        "the semantic layer's category, kept where the intent layer was silent",
        REQUIRE_EVIDENCE,
    ),
)


def rule(rule_id: str) -> DecisionRule:
    for item in RULES:
        if item.rule_id == rule_id:
            return item
    raise ModelError(f"unknown decision rule {rule_id!r}")


def action_for(rule_id: str, category: str) -> str:
    """The action a rule emits, corrected by the taxonomy's own severity.

    The taxonomy already states which categories block and which require
    evidence. The policy uses that rather than inventing a second opinion, so a
    rule cannot quietly downgrade a `block` category.
    """

    entry = taxonomy_category(category)
    declared = entry.action
    if declared in (BLOCK, REQUIRE_EVIDENCE, DOWNRANK):
        return declared
    return rule(rule_id).base_action


def categories_for_relation(relation: str) -> tuple[str, ...]:
    category = RELATION_CATEGORY.get(relation)
    return (category,) if category else ()


#: Hedge markers that mean *reported*, not *conditional*.
#:
#: The Phase 8.4 matcher reports one `hedge` string for anything that makes a
#: claim less than asserted, and `The company said the fund cannot lose money.`
#: is hedged by `said`. But `said` is the attribution marker, and the
#: attribution layer has already recorded what it means: this is a quoted third
#: party's claim. Treating it as a generic hedge suppressed the finding
#: entirely and produced no category where the phase requires
#: `unverified_information`. Reported speech is therefore routed to Case 2, and
#: only conditional or modal hedging suppresses.
REPORTING_HEDGES: frozenset[str] = frozenset(
    {
        "said",
        "says",
        "say",
        "according to",
        "reportedly",
        "reported",
        "reports",
        "claims",
        "claimed",
        "states",
        "stated",
        "advertises",
        "advertised",
        "promises",
        "promised",
        "\u636e\u79f0",
        "\u4f20\u95fb",
    }
)


def is_reporting_hedge(hedge: str) -> bool:
    return hedge.strip().lower() in REPORTING_HEDGES


#: Modals that are *constitutive* of a relation rather than hedging it.
#:
#: Phase 8.4 lists `should` as a hedge, which is right for a guarantee:
#: `Returns should be guaranteed.` is weaker than `Returns are guaranteed.` For
#: advice it is the opposite - `You should buy this stock.` is the advice. The
#: marker means different things for different relations, so the decision layer
#: interprets it rather than the matcher.
DIRECTIVE_MODALS: frozenset[str] = frozenset({"should", "ought to", "must"})


def hedges(relation: str, hedge: str) -> bool:
    """Does this marker actually weaken this relation?"""

    marker = hedge.strip().lower()
    if not marker:
        return False
    if relation == ADVICE and marker in DIRECTIVE_MODALS:
        return False
    return True


def decide(
    claim: RiskClaim,
    *,
    fallback_searched: bool = False,
) -> tuple[tuple[RiskDecision, ...], tuple[RiskDecision, ...]]:
    """Decide the claim. Returns (kept, suppressed), both evidenced."""

    if not isinstance(claim, RiskClaim):
        raise ModelError("decide expects a RiskClaim")

    kept: list[RiskDecision] = []
    suppressed: list[RiskDecision] = []
    emitted: set[tuple[str, bool]] = set()

    def emit(
        decision_rule: str,
        category: str,
        marker: str,
        *,
        keep: bool,
        reason: str = "",
    ) -> None:
        # One decision per (category, kept) per claim. Two frames of the same
        # relation in one sentence - `The share price will certainly double next
        # year.` matches both the modal and the horizon frame - are one finding,
        # and reporting them twice would inflate every count built on decisions.
        if (category, keep) in emitted:
            return
        emitted.add((category, keep))
        target = kept if keep else suppressed
        target.append(
            RiskDecision(
                claim_id=claim.claim_id,
                category=category,
                action=action_for(decision_rule, category) if keep else DOWNRANK,
                rule=decision_rule,
                evidence=evidence_strings(claim.evidence, (marker,)),
                kept=keep,
                reason=reason,
            )
        )

    # -- what the intent layer found ---------------------------------------
    for intent in claim.intents:
        categories = categories_for_relation(intent.relation)
        if not categories:
            continue
        marker = f"intent:{intent.marker}"
        category = categories[0]

        if intent.negated:
            emit(
                R_NEGATED,
                category,
                marker,
                keep=False,
                reason=f"the {intent.relation} frame is negated",
            )
            continue

        # `stance == quoted` is the condition, not `speaker == third_party and
        # stance == quoted`. The phase states Case 2 with both, and the extra
        # clause is necessary but not sufficient: `The regulator said capital is
        # guaranteed.` is `unknown/quoted`, because the Phase 8.2 marker table
        # has `regulators` and not `the regulator`. The situation is identical -
        # the article is reporting somebody else's words - and keying on the
        # stance rather than on whether the speaker was identified is what makes
        # Case 2 robust to the attribution layer's vocabulary.
        #
        # `unverified_information` is emitted only when the sourcing layer also
        # flags the source. Guide v2 section 7 is explicit that a named,
        # checkable source is *negative* for that category, so `Management
        # expects the share price to double.` must not produce it. Taking the
        # phase's Case 2 literally - any quoted third party becomes unverified -
        # broke two of Phase 8.1's controls, which is how this narrowing was
        # found. The guide is the normative document and it wins.
        attributed = claim.stance == "quoted"
        sourcing_flagged = "unverified_information" in claim.fallback_categories
        real_hedge = hedges(intent.relation, intent.hedge)
        reporting_hedge = intent.hedge and is_reporting_hedge(intent.hedge)

        if attributed and (not real_hedge or reporting_hedge):
            if sourcing_flagged:
                emit(
                    R_THIRD_PARTY,
                    "unverified_information",
                    f"attribution:{claim.speaker}/{claim.stance}",
                    keep=True,
                    reason=(
                        "the relation belongs to a quoted third party whose "
                        "source cannot be checked, so it is reported as an "
                        "unchecked source rather than as the article's claim"
                    ),
                )
            emit(
                R_THIRD_PARTY,
                category,
                marker,
                keep=False,
                reason=(
                    "a quoted third party's relation is not the article's"
                    if sourcing_flagged
                    else "a quoted third party's relation is not the article's, "
                    "and the source is identifiable so it is not "
                    "unverified_information either"
                ),
            )
            continue

        if real_hedge:
            emit(
                R_HEDGED,
                category,
                marker,
                keep=False,
                reason=f"the {intent.relation} frame is hedged by {intent.hedge!r}",
            )
            continue

        # Case 3: a rejection never inherits the rejected claim's risk.
        if claim.is_rejected:
            emit(
                R_REJECTED,
                category,
                marker,
                keep=False,
                reason="the article rejects this claim",
            )
            continue

        # Any other non-authorial voice: reported without the quotation frame
        # the taxonomy recognises, so the relation is still not the article's.
        # The same guide section 7 condition applies - a named, checkable
        # source is negative for unverified_information.
        if not claim.is_authorial:
            if sourcing_flagged:
                emit(
                    R_THIRD_PARTY,
                    "unverified_information",
                    f"attribution:{claim.speaker}/{claim.stance}",
                    keep=True,
                    reason="a non-authorial claim's uncheckable source is the risk",
                )
            emit(
                R_THIRD_PARTY,
                category,
                marker,
                keep=False,
                reason="the claim is not the article's",
            )
            continue

        # Case 1 and the general author-voice case.
        rule_id = (
            R_AUTHOR_ENDORSED
            if claim.speaker == "author" and claim.stance == "endorsed"
            else R_AUTHOR_RELATION
        )
        emit(rule_id, category, marker, keep=True)

    # -- sourcing risk, which survives every voice -------------------------
    # Only the layer that detects sourcing may raise it. An earlier version
    # emitted `unverified_information` for every third-party claim, which is
    # wrong for a named, checkable source: guide v2 section 7 says a named
    # source is negative for this category.
    for category in ATTRIBUTION_AGNOSTIC_CATEGORIES:
        if category not in claim.fallback_categories:
            continue
        emit(
            R_AGNOSTIC,
            category,
            f"fallback:agnostic:{category}",
            keep=True,
            reason="sourcing risk is reported whatever the voice",
        )

    # -- what the semantic fallback added ----------------------------------
    # A category the intent layer found and the policy declined is not offered
    # to the fallback again. `A guaranteed return is not available.` reaches the
    # intent layer as a negated GUARANTEE, which the policy suppresses; letting
    # the semantic layer re-add `financial_guarantee` afterwards undid the
    # suppression and put the false positive straight back. The intent layer saw
    # the relation and made a decision about it, and a weaker signal does not
    # get to overrule that.
    declined = {item.category for item in suppressed}
    for category in claim.fallback_categories:
        if any(item.category == category and item.kept for item in kept):
            continue
        if category in declined:
            emit(
                R_FALLBACK,
                category,
                f"fallback:declined-by-intent:{category}",
                keep=False,
                reason="the intent layer found this relation and the policy declined it",
            )
            continue
        if claim.is_rejected:
            emit(
                R_REJECTED,
                category,
                f"fallback:{category}",
                keep=False,
                reason="the article rejects this claim",
            )
            continue
        if not claim.is_authorial:
            emit(
                R_FALLBACK,
                category,
                f"fallback:suppressed:{category}",
                keep=False,
                reason="the claim is not the article's",
            )
            continue
        emit(
            R_FALLBACK,
            category,
            f"fallback:{category}",
            keep=True,
            reason=(
                "the intent layer produced no relation here"
                if fallback_searched
                else "kept from the semantic layer"
            ),
        )

    return tuple(kept), tuple(suppressed)


def decide_input(claim: ClaimInput, **kwargs) -> tuple[tuple[RiskDecision, ...], ...]:
    del claim, kwargs
    raise ModelError(
        "decide() takes a RiskClaim: a decision needs a speaker, a stance and "
        "evidence, and a ClaimInput has none of them"
    )


def policy_table() -> tuple[dict[str, object], ...]:
    return tuple(item.as_dict() for item in RULES)


def relations_covered() -> tuple[str, ...]:
    """Relations the policy has a category mapping for."""

    return tuple(name for name in RELATIONS if name in RELATION_CATEGORY)


def uncovered_relations() -> tuple[str, ...]:
    return tuple(name for name in RELATIONS if name not in RELATION_CATEGORY)


def rule_ids() -> Sequence[str]:
    return tuple(item.rule_id for item in RULES)
