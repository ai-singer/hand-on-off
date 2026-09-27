"""The decision policy: R1 raises, R2 and R3 suppress, agnostic survives."""

from __future__ import annotations

import json
import unittest

from risk_evaluation.attribution.model import Claim
from risk_evaluation.model import RiskEvaluationResult
from risk_evaluation.attribution_experiment.decision import (
    AUTHORIAL,
    POLICIES,
    R1_AUTHOR_ENDORSED,
    R2_THIRD_PARTY_QUOTED,
    R3_AUTHOR_REJECTED,
    R4_ATTRIBUTION_AGNOSTIC,
    R5_NOT_AUTHORIAL,
    R6_BASELINE_VERDICT,
    STRICT,
    ClaimDecision,
    decide_claim,
    is_attribution_agnostic,
    is_author_rejection,
    is_third_party_quotation,
    merge_results,
    raises_risk_weight,
    summarise,
)
from risk_evaluation.semantic_evaluator_v2 import SemanticRiskEvaluatorV2


def _claim(
    *,
    speaker: str = "author",
    stance: str = "endorsed",
    claim_id: str = "claim-001",
    text: str = "This fund cannot lose money.",
) -> Claim:
    return Claim(
        claim_id=claim_id,
        text=text,
        speaker=speaker,
        stance=stance,
        confidence=0.8,
        evidence=("test-marker",),
    )


class RulePredicateTests(unittest.TestCase):
    def test_r1_is_author_and_endorsed(self) -> None:
        self.assertTrue(raises_risk_weight(_claim(speaker="author", stance="endorsed")))
        self.assertFalse(raises_risk_weight(_claim(speaker="author", stance="rejected")))
        self.assertFalse(
            raises_risk_weight(_claim(speaker="third_party", stance="endorsed"))
        )
        self.assertFalse(
            raises_risk_weight(_claim(speaker="unknown", stance="uncertain"))
        )

    def test_r2_is_third_party_and_quoted(self) -> None:
        self.assertTrue(
            is_third_party_quotation(_claim(speaker="third_party", stance="quoted"))
        )
        self.assertFalse(
            is_third_party_quotation(_claim(speaker="third_party", stance="endorsed"))
        )
        self.assertFalse(
            is_third_party_quotation(_claim(speaker="unknown", stance="quoted"))
        )

    def test_r3_is_author_and_rejected(self) -> None:
        self.assertTrue(is_author_rejection(_claim(speaker="author", stance="rejected")))
        self.assertFalse(
            is_author_rejection(_claim(speaker="third_party", stance="rejected"))
        )

    def test_unverified_information_is_the_agnostic_category(self) -> None:
        self.assertTrue(is_attribution_agnostic("unverified_information"))
        self.assertFalse(is_attribution_agnostic("financial_guarantee"))
        self.assertFalse(is_attribution_agnostic("investment_advice"))


class DecisionTests(unittest.TestCase):
    def test_r1_keeps_and_marks_the_weight_raised(self) -> None:
        decision = decide_claim(
            _claim(speaker="author", stance="endorsed"), ["financial_guarantee"]
        )

        self.assertEqual(decision.kept, ("financial_guarantee",))
        self.assertEqual(decision.dropped, ())
        self.assertTrue(decision.weight_raised)
        self.assertIn(R1_AUTHOR_ENDORSED, decision.rules)

    def test_r2_drops_an_author_voice_category(self) -> None:
        decision = decide_claim(
            _claim(speaker="third_party", stance="quoted"), ["financial_guarantee"]
        )

        self.assertEqual(decision.kept, ())
        self.assertEqual(decision.dropped, ("financial_guarantee",))
        self.assertFalse(decision.weight_raised)
        self.assertIn(R2_THIRD_PARTY_QUOTED, decision.rules)
        self.assertTrue(decision.suppressed)

    def test_r3_drops_the_risk(self) -> None:
        decision = decide_claim(
            _claim(speaker="author", stance="rejected"), ["financial_guarantee"]
        )

        self.assertEqual(decision.kept, ())
        self.assertIn(R3_AUTHOR_REJECTED, decision.rules)

    def test_the_agnostic_category_survives_r2(self) -> None:
        """`taxonomy_v2` reports an uncheckable source whatever the voice."""

        decision = decide_claim(
            _claim(speaker="third_party", stance="quoted"), ["unverified_information"]
        )

        self.assertEqual(decision.kept, ("unverified_information",))
        self.assertEqual(decision.dropped, ())
        self.assertIn(R4_ATTRIBUTION_AGNOSTIC, decision.rules)

    def test_the_agnostic_category_survives_r3(self) -> None:
        decision = decide_claim(
            _claim(speaker="author", stance="rejected"), ["unverified_information"]
        )

        self.assertEqual(decision.kept, ("unverified_information",))

    def test_a_mixed_detection_is_split(self) -> None:
        decision = decide_claim(
            _claim(speaker="third_party", stance="quoted"),
            ["financial_guarantee", "unverified_information"],
        )

        self.assertEqual(decision.kept, ("unverified_information",))
        self.assertEqual(decision.dropped, ("financial_guarantee",))

    def test_a_default_voice_claim_keeps_the_baseline_verdict(self) -> None:
        """R1, R2 and R3 say nothing about an unmarked claim."""

        decision = decide_claim(
            _claim(speaker="unknown", stance="uncertain"), ["financial_guarantee"]
        )

        self.assertEqual(decision.kept, ("financial_guarantee",))
        self.assertIn(R6_BASELINE_VERDICT, decision.rules)
        self.assertFalse(decision.weight_raised)

    def test_the_authorial_policy_suppresses_other_non_authorial_shapes(self) -> None:
        claim = _claim(speaker="unknown", stance="quoted")
        strict = decide_claim(claim, ["financial_guarantee"], policy=STRICT)
        authorial = decide_claim(claim, ["financial_guarantee"], policy=AUTHORIAL)

        self.assertEqual(strict.kept, ("financial_guarantee",))
        self.assertEqual(authorial.kept, ())
        self.assertIn(R5_NOT_AUTHORIAL, authorial.rules)

    def test_both_policies_agree_on_r2_and_r3(self) -> None:
        for speaker, stance in (("third_party", "quoted"), ("author", "rejected")):
            claim = _claim(speaker=speaker, stance=stance)
            for policy in POLICIES:
                decision = decide_claim(claim, ["financial_guarantee"], policy=policy)
                self.assertEqual(decision.kept, (), f"{speaker}/{stance}/{policy}")

    def test_no_detections_means_no_rules(self) -> None:
        decision = decide_claim(_claim(), [])

        self.assertEqual(decision.detected, ())
        self.assertEqual(decision.kept, ())
        self.assertEqual(decision.rules, ())

    def test_an_unknown_policy_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            decide_claim(_claim(), ["financial_guarantee"], policy="make-it-pass")

    def test_duplicate_categories_are_collapsed(self) -> None:
        decision = decide_claim(
            _claim(), ["financial_guarantee", "financial_guarantee"]
        )

        self.assertEqual(decision.detected, ("financial_guarantee",))

    def test_the_statement_source_bridge_is_recorded(self) -> None:
        decision = decide_claim(_claim(speaker="third_party", stance="quoted"), [])

        self.assertEqual(decision.statement_source, "quoted")

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(decide_claim(_claim(), ["financial_guarantee"]).as_dict())

    def test_render_states_what_happened(self) -> None:
        rendered = decide_claim(
            _claim(speaker="third_party", stance="quoted"), ["financial_guarantee"]
        ).render()

        self.assertIn("dropped", rendered)


class SummaryTests(unittest.TestCase):
    def test_the_summary_counts_claims_and_suppressions(self) -> None:
        decisions = [
            decide_claim(_claim(claim_id="claim-001"), ["financial_guarantee"]),
            decide_claim(
                _claim(claim_id="claim-002", speaker="third_party", stance="quoted"),
                ["market_prediction"],
            ),
        ]
        summary = summarise(decisions)

        self.assertEqual(summary.claims, 2)
        self.assertEqual(summary.kept_claims, 1)
        self.assertEqual(summary.suppressed_claims, 1)
        self.assertEqual(summary.weight_raised, 1)
        self.assertEqual(summary.dropped_categories, ("market_prediction",))

    def test_an_empty_decision_set_summarises_to_zero(self) -> None:
        summary = summarise([])

        self.assertEqual(summary.claims, 0)
        self.assertEqual(summary.dropped_categories, ())


class MergeTests(unittest.TestCase):
    """The merge reads the evaluator's real per-claim output, not declared labels.

    These use explicit synthetic detections: taking them from a real text means
    the policy suppresses one of the claims and the merge never sees it, which
    is correct behaviour but not what these tests are about.
    """

    @staticmethod
    def _result(category: str, confidence: float) -> RiskEvaluationResult:
        from risk_evaluation.taxonomy import category as taxonomy_category

        entry = taxonomy_category(category)
        return RiskEvaluationResult(
            category=category,
            intent=entry.intent,
            confidence=confidence,
            evidence_required=entry.evidence_required,
            severity=entry.severity,
            action=entry.action,
            evaluator="synthetic",
            detail="synthetic",
        )

    def test_the_merge_keeps_only_what_the_policy_kept(self) -> None:
        decisions = [
            decide_claim(_claim(claim_id="claim-001"), ["financial_guarantee"]),
            decide_claim(_claim(claim_id="claim-002"), ["market_prediction"]),
        ]
        per_claim = {
            "claim-001": (self._result("financial_guarantee", 0.7),),
            "claim-002": (self._result("market_prediction", 0.7),),
        }
        merged = merge_results(
            [decisions[1]], per_claim
        )

        self.assertEqual([item.category for item in merged], ["market_prediction"])

    def test_the_merge_uses_the_real_result_not_the_declared_category(self) -> None:
        """A declared category with no matching result contributes nothing."""

        decisions = [decide_claim(_claim(claim_id="claim-001"), ["financial_guarantee"])]
        per_claim = {"claim-001": (self._result("market_prediction", 0.7),)}

        self.assertEqual(merge_results(decisions, per_claim), ())

    def test_two_claims_keeping_the_same_category_are_both_recorded(self) -> None:
        decisions = [
            decide_claim(_claim(claim_id="claim-001"), ["financial_guarantee"]),
            decide_claim(_claim(claim_id="claim-002"), ["financial_guarantee"]),
        ]
        per_claim = {
            "claim-001": (self._result("financial_guarantee", 0.7),),
            "claim-002": (self._result("financial_guarantee", 0.7),),
        }
        merged = merge_results(decisions, per_claim)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].source_ids, ("claim-001", "claim-002"))

    def test_the_higher_confidence_detection_wins(self) -> None:
        decisions = [
            decide_claim(_claim(claim_id="claim-001"), ["financial_guarantee"]),
            decide_claim(_claim(claim_id="claim-002"), ["financial_guarantee"]),
        ]
        per_claim = {
            "claim-001": (self._result("financial_guarantee", 0.4),),
            "claim-002": (self._result("financial_guarantee", 0.9),),
        }
        merged = merge_results(decisions, per_claim)

        self.assertEqual(merged[0].confidence, 0.9)
        self.assertEqual(merged[0].source_ids, ("claim-001", "claim-002"))

    def test_a_real_split_merge_keeps_the_authorial_claim_only(self) -> None:
        """End to end on the Phase 8.1 shape, with real evaluator output."""

        evaluator = SemanticRiskEvaluatorV2()
        text = "Economists forecast growth. This fund cannot lose money."
        claims = semantic_claim_split(text)
        per_claim = {
            claim.claim_id: tuple(evaluator.evaluate_text(claim.text))
            for claim in claims
        }
        decisions = [
            decide_claim(claim, [item.category for item in per_claim[claim.claim_id]])
            for claim in claims
        ]
        merged = merge_results(decisions, per_claim)

        self.assertEqual([item.category for item in merged], ["financial_guarantee"])
        self.assertEqual(merged[0].source_ids, ("claim-002",))

    def test_nothing_kept_means_an_empty_decision(self) -> None:
        decisions = [decide_claim(_claim(), [])]

        self.assertEqual(merge_results(decisions, {}), ())


def semantic_claim_split(text: str):
    from risk_evaluation.attribution import analyze

    return analyze(text).claims


if __name__ == "__main__":
    unittest.main()
