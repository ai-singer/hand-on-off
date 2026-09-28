"""Step 4: the decision policy, including the three cases the phase names."""

from __future__ import annotations

import json
import unittest

from risk_evaluation.v3.decision import (
    ACTIONS,
    BLOCK,
    RULES,
    R_AGNOSTIC,
    R_AUTHOR_ENDORSED,
    R_FALLBACK,
    R_HEDGED,
    R_NEGATED,
    R_REJECTED,
    R_THIRD_PARTY,
    REQUIRE_EVIDENCE,
    action_for,
    categories_for_relation,
    decide,
    hedges,
    is_reporting_hedge,
    policy_table,
    relations_covered,
    rule,
    rule_ids,
    uncovered_relations,
)
from risk_evaluation.v3.model import (
    ADVICE,
    GUARANTEE,
    ModelError,
    PREDICTION,
    RISK_REMOVED,
    RiskClaim,
    IntentEvidence,
)
from risk_evaluation.v3.patterns import RELATION_CATEGORY


def _intent(relation: str = GUARANTEE, **overrides) -> IntentEvidence:
    base = dict(
        relation=relation,
        entity="RETURN",
        frame="copular",
        predicate="guaranteed",
        pattern_id="v3-financial-guarantee",
        span=(0, 8),
    )
    base.update(overrides)
    return IntentEvidence(**base)


def _claim(
    *,
    speaker: str = "author",
    stance: str = "endorsed",
    intents=(),
    fallback=(),
) -> RiskClaim:
    intents = tuple(intents)
    fallback = tuple(fallback)
    return RiskClaim(
        claim_id="claim-001",
        text="This return is guaranteed.",
        source_span=(0, 26),
        speaker=speaker,
        stance=stance,
        evidence=("copular_guarantee_pattern",),
        intents=intents,
        fallback_categories=fallback,
        fallback_evidence=("rule:semantic.searched",),
    )


class RuleTableTests(unittest.TestCase):
    def test_every_rule_id_is_unique(self) -> None:
        ids = rule_ids()

        self.assertEqual(len(ids), len(set(ids)))

    def test_every_rule_can_be_looked_up(self) -> None:
        for rule_id in rule_ids():
            self.assertEqual(rule(rule_id).rule_id, rule_id)

    def test_an_unknown_rule_raises(self) -> None:
        with self.assertRaises(ModelError):
            rule("D999-nonsense")

    def test_the_policy_table_is_json_serializable(self) -> None:
        json.dumps(list(policy_table()), sort_keys=True)

    def test_every_relation_has_a_category_mapping(self) -> None:
        self.assertEqual(uncovered_relations(), ())
        self.assertEqual(set(relations_covered()), {GUARANTEE, RISK_REMOVED, PREDICTION, ADVICE})

    def test_the_relation_mapping_targets_real_categories(self) -> None:
        from risk_evaluation.taxonomy import RISK_TAXONOMY

        known = {entry.name for entry in RISK_TAXONOMY}
        for relation, category in RELATION_CATEGORY.items():
            self.assertIn(category, known, relation)

    def test_actions_come_from_the_taxonomy(self) -> None:
        """A rule may not downgrade a block category."""

        self.assertEqual(action_for(R_AUTHOR_ENDORSED, "financial_guarantee"), BLOCK)
        self.assertEqual(
            action_for(R_FALLBACK, "unverified_information"), REQUIRE_EVIDENCE
        )

    def test_the_declared_actions_are_the_four_in_use(self) -> None:
        self.assertEqual(set(ACTIONS), {"block", "review", "require_evidence", "downrank"})

    def test_categories_for_relation_returns_the_mapping(self) -> None:
        self.assertEqual(categories_for_relation(GUARANTEE), ("financial_guarantee",))
        self.assertEqual(categories_for_relation("NOT_A_RELATION"), ())

    def test_reporting_hedges_are_recognised(self) -> None:
        self.assertTrue(is_reporting_hedge("said"))
        self.assertTrue(is_reporting_hedge("according to"))
        self.assertFalse(is_reporting_hedge("if"))

    def test_a_directive_modal_does_not_hedge_advice(self) -> None:
        """`You should buy this stock.` is the advice, not a hedge of it."""

        self.assertFalse(hedges(ADVICE, "should"))
        self.assertTrue(hedges(GUARANTEE, "should"))
        self.assertTrue(hedges(ADVICE, "if"))


class CaseOneTests(unittest.TestCase):
    """author + endorsed + GUARANTEE -> financial_guarantee, block."""

    def test_the_guarantee_becomes_the_articles_risk(self) -> None:
        kept, suppressed = decide(
            _claim(speaker="author", stance="endorsed", intents=(_intent(GUARANTEE),))
        )

        self.assertEqual([d.category for d in kept], ["financial_guarantee"])
        self.assertEqual(kept[0].action, BLOCK)
        self.assertEqual(kept[0].rule, R_AUTHOR_ENDORSED)
        self.assertEqual(suppressed, ())

    def test_the_decision_carries_evidence(self) -> None:
        kept, _ = decide(
            _claim(speaker="author", stance="endorsed", intents=(_intent(GUARANTEE),))
        )

        self.assertTrue(kept[0].evidence)

    def test_risk_removed_also_becomes_the_category(self) -> None:
        kept, _ = decide(
            _claim(speaker="author", stance="endorsed", intents=(_intent(RISK_REMOVED),))
        )

        self.assertEqual([d.category for d in kept], ["financial_guarantee"])

    def test_a_default_voice_claim_keeps_the_relation(self) -> None:
        kept, _ = decide(
            _claim(speaker="unknown", stance="uncertain", intents=(_intent(),))
        )

        self.assertEqual([d.category for d in kept], ["financial_guarantee"])


class CaseTwoTests(unittest.TestCase):
    """third party + quoted + GUARANTEE -> unverified_information."""

    def test_an_uncheckable_quoted_guarantee_becomes_unverified(self) -> None:
        kept, suppressed = decide(
            _claim(
                speaker="third_party",
                stance="quoted",
                intents=(_intent(GUARANTEE),),
                fallback=("unverified_information",),
            )
        )

        self.assertEqual([d.category for d in kept], ["unverified_information"])
        self.assertEqual(kept[0].action, REQUIRE_EVIDENCE)
        self.assertEqual(kept[0].rule, R_THIRD_PARTY)

    def test_the_guarantee_is_not_the_articles(self) -> None:
        _, suppressed = decide(
            _claim(
                speaker="third_party",
                stance="quoted",
                intents=(_intent(GUARANTEE),),
                fallback=("unverified_information",),
            )
        )

        self.assertEqual([d.category for d in suppressed], ["financial_guarantee"])

    def test_a_named_checkable_source_produces_nothing(self) -> None:
        """Guide v2 section 7: a named, checkable source is negative.

        The phase's Case 2 says a quoted third party's guarantee becomes
        unverified information. Taking that literally broke two Phase 8.1
        controls, because `Management expects the share price to double.` names
        a checkable party. The guide is normative, so the rule is narrowed.
        """

        kept, suppressed = decide(
            _claim(
                speaker="third_party",
                stance="quoted",
                intents=(_intent(GUARANTEE),),
                fallback=(),
            )
        )

        self.assertEqual(kept, ())
        self.assertEqual([d.category for d in suppressed], ["financial_guarantee"])
        self.assertIn("identifiable", suppressed[0].reason)

    def test_an_unidentified_quoted_speaker_is_handled_too(self) -> None:
        """`The regulator said …` is unknown/quoted, and the situation is the same."""

        kept, _ = decide(
            _claim(
                speaker="unknown",
                stance="quoted",
                intents=(_intent(GUARANTEE),),
                fallback=("unverified_information",),
            )
        )

        self.assertEqual([d.category for d in kept], ["unverified_information"])

    def test_a_reported_guarantee_is_not_suppressed_as_a_hedge(self) -> None:
        """`said` hedges the frame and is also the attribution marker."""

        kept, _ = decide(
            _claim(
                speaker="third_party",
                stance="quoted",
                intents=(_intent(GUARANTEE, hedge="said"),),
                fallback=("unverified_information",),
            )
        )

        self.assertEqual([d.category for d in kept], ["unverified_information"])


class CaseThreeTests(unittest.TestCase):
    """author + rejected -> no inherited risk."""

    def test_a_rejected_guarantee_is_not_the_articles_risk(self) -> None:
        kept, suppressed = decide(
            _claim(speaker="author", stance="rejected", intents=(_intent(GUARANTEE),))
        )

        self.assertEqual(kept, ())
        self.assertEqual([d.category for d in suppressed], ["financial_guarantee"])
        self.assertEqual(suppressed[0].rule, R_REJECTED)

    def test_a_rejected_third_party_claim_is_also_suppressed(self) -> None:
        kept, _ = decide(
            _claim(
                speaker="third_party",
                stance="rejected",
                intents=(_intent(RISK_REMOVED),),
                fallback=("financial_guarantee",),
            )
        )

        self.assertEqual(kept, ())

    def test_a_rejected_claim_does_not_inherit_the_fallback_either(self) -> None:
        kept, suppressed = decide(
            _claim(speaker="author", stance="rejected", fallback=("market_prediction",))
        )

        self.assertEqual(kept, ())
        self.assertEqual([d.category for d in suppressed], ["market_prediction"])


class SuppressionTests(unittest.TestCase):
    def test_a_negated_frame_is_suppressed(self) -> None:
        kept, suppressed = decide(
            _claim(intents=(_intent(GUARANTEE, negated=True),))
        )

        self.assertEqual(kept, ())
        self.assertEqual(suppressed[0].rule, R_NEGATED)

    def test_a_hedged_frame_is_suppressed(self) -> None:
        kept, suppressed = decide(_claim(intents=(_intent(GUARANTEE, hedge="if"),)))

        self.assertEqual(kept, ())
        self.assertEqual(suppressed[0].rule, R_HEDGED)

    def test_the_fallback_may_not_re_add_a_declined_category(self) -> None:
        """Suppressing a relation and then re-adding it undoes the suppression.

        The guard is behavioural: the category stays suppressed. The rule
        recorded is the one that suppressed it first - the negation - because a
        category has one suppressed decision and the earliest rule is the most
        informative one.
        """

        kept, suppressed = decide(
            _claim(
                intents=(_intent(GUARANTEE, negated=True),),
                fallback=("financial_guarantee",),
            )
        )

        self.assertEqual(kept, ())
        self.assertEqual([d.category for d in suppressed], ["financial_guarantee"])
        self.assertEqual(suppressed[0].rule, R_NEGATED)
        self.assertEqual(len(suppressed), 1)

    def test_the_fallback_re_adds_a_category_the_intent_layer_never_saw(self) -> None:
        """The guard applies only to categories the intent layer found."""

        kept, _ = decide(
            _claim(
                speaker="author",
                stance="endorsed",
                intents=(_intent(GUARANTEE),),
                fallback=("emotional_manipulation",),
            )
        )

        self.assertEqual(
            sorted(d.category for d in kept),
            ["emotional_manipulation", "financial_guarantee"],
        )

    def test_a_fallback_category_survives_for_an_authorial_claim(self) -> None:
        """A category no relation defines still reaches the fallback.

        `emotional_manipulation` has no v3 relation, so the semantic layer is its
        only detector and the guard in `RELATION_REQUIRED` does not apply to it.
        """

        kept, _ = decide(_claim(speaker="author", stance="endorsed", fallback=("emotional_manipulation",)))

        self.assertEqual([d.category for d in kept], ["emotional_manipulation"])

    def test_a_fallback_category_needing_a_relation_is_declined_without_one(self) -> None:
        """Phase 8.6's four false positives, as the rule that answers them.

        `investment_advice` is defined as a directive aimed at the reader, and
        `The expense ratio is the annual cost of holding a fund.` contains no
        directive. The fallback kept it anyway; now the relation decides.
        """

        kept, suppressed = decide(
            _claim(speaker="author", stance="endorsed", fallback=("investment_advice",))
        )

        self.assertEqual(kept, ())
        self.assertEqual([d.category for d in suppressed], ["investment_advice"])
        self.assertEqual(suppressed[0].rule, R_FALLBACK)
        self.assertIn("no-relation-behind-it", " ".join(suppressed[0].evidence))

    def test_a_category_the_guard_does_not_cover_still_reaches_the_fallback(self) -> None:
        """The guard is a table, and it covers what was measured, not everything.

        `market_prediction` is deliberately absent: adding it changed no number
        on any scored set, so shipping it would have been untested code. This
        test is what makes that decision visible rather than invisible.
        """

        kept, _ = decide(
            _claim(speaker="author", stance="endorsed", fallback=("market_prediction",))
        )

        self.assertEqual([d.category for d in kept], ["market_prediction"])

    def test_a_fallback_category_is_kept_when_the_relation_is_there(self) -> None:
        """The guard asks whether the relation fired, not what was decided."""

        kept, _ = decide(
            _claim(
                speaker="author",
                stance="endorsed",
                intents=(_intent(ADVICE),),
                fallback=("investment_advice",),
            )
        )

        self.assertEqual([d.category for d in kept], ["investment_advice"])

    def test_a_fallback_category_is_suppressed_for_a_quoted_claim(self) -> None:
        kept, suppressed = decide(
            _claim(
                speaker="third_party",
                stance="quoted",
                fallback=("market_prediction",),
            )
        )

        self.assertEqual(kept, ())
        self.assertEqual([d.category for d in suppressed], ["market_prediction"])

    def test_sourcing_risk_survives_a_quoted_voice(self) -> None:
        kept, _ = decide(
            _claim(
                speaker="third_party",
                stance="quoted",
                fallback=("unverified_information",),
            )
        )

        self.assertEqual([d.category for d in kept], ["unverified_information"])
        self.assertEqual(kept[0].rule, R_AGNOSTIC)

    def test_sourcing_risk_is_not_invented_by_the_policy(self) -> None:
        """Only the layer that detects sourcing may raise it."""

        kept, _ = decide(
            _claim(speaker="third_party", stance="quoted", fallback=())
        )

        self.assertEqual(kept, ())

    def test_one_decision_per_category_per_claim(self) -> None:
        """Two frames of one relation in one sentence are one finding."""

        kept, _ = decide(
            _claim(intents=(_intent(GUARANTEE), _intent(GUARANTEE, frame="active")))
        )

        self.assertEqual(len(kept), 1)

    def test_decide_requires_a_risk_claim(self) -> None:
        with self.assertRaises(ModelError):
            decide("not a claim")  # type: ignore[arg-type]


def decisions_rule_ids(decisions) -> tuple[str, ...]:
    return tuple(item.rule for item in decisions)


if __name__ == "__main__":
    unittest.main()
