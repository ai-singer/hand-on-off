"""Step 1 and Step 5: the unified model, and the trace contract."""

from __future__ import annotations

import json
import unittest

from risk_evaluation.v3.model import (
    ADVICE,
    CAPITAL,
    CORE_ENTITIES,
    ENTITY_NAMES,
    EXTENDED_ENTITIES,
    FRAMES,
    GUARANTEE,
    INSTRUMENT,
    OUTCOME,
    PREDICTION,
    RELATIONS,
    RETURN,
    REVENUE,
    RISK_REMOVED,
    VALUE,
    V3_VERSION,
    ClaimInput,
    ClaimTrace,
    IntentEvidence,
    ModelError,
    RiskClaim,
    RiskDecision,
    RiskEvaluationResult,
    evidence_strings,
)


def _intent(**overrides) -> IntentEvidence:
    base = dict(
        relation=GUARANTEE,
        entity=RETURN,
        frame="copular",
        predicate="guaranteed",
        pattern_id="v3-financial-guarantee",
        span=(0, 24),
    )
    base.update(overrides)
    return IntentEvidence(**base)


def _claim(**overrides) -> RiskClaim:
    base = dict(
        claim_id="claim-001",
        text="This return is guaranteed.",
        source_span=(0, 26),
        speaker="unknown",
        stance="uncertain",
        evidence=("rule:speaker.no-marker", "copular_guarantee_pattern"),
        intents=(_intent(),),
    )
    base.update(overrides)
    return RiskClaim(**base)


def _decision(**overrides) -> RiskDecision:
    base = dict(
        claim_id="claim-001",
        category="financial_guarantee",
        action="block",
        rule="D6-author-endorsed-relation",
        evidence=("copular_guarantee_pattern",),
    )
    base.update(overrides)
    return RiskDecision(**base)


class ConstantTests(unittest.TestCase):
    def test_the_four_relations_are_declared(self) -> None:
        self.assertEqual(
            set(RELATIONS), {GUARANTEE, RISK_REMOVED, PREDICTION, ADVICE}
        )

    def test_the_four_core_entities_are_declared(self) -> None:
        self.assertEqual(set(CORE_ENTITIES), {RETURN, CAPITAL, VALUE, OUTCOME})

    def test_the_extensions_are_separate_from_the_core(self) -> None:
        """ADVICE and PREDICTION need objects the four cannot express."""

        self.assertEqual(set(EXTENDED_ENTITIES), {INSTRUMENT, REVENUE})
        self.assertEqual(set(ENTITY_NAMES), set(CORE_ENTITIES) | set(EXTENDED_ENTITIES))

    def test_the_frame_kinds_are_declared(self) -> None:
        self.assertEqual(
            set(FRAMES), {"active", "passive", "copular", "attributive", "nominal"}
        )

    def test_the_version_is_marked_experimental(self) -> None:
        self.assertIn("experimental", V3_VERSION)


class ClaimInputTests(unittest.TestCase):
    def test_a_claim_input_keeps_its_span(self) -> None:
        text = "Returns are guaranteed"
        item = ClaimInput("c-1", text, (0, len(text)), text)

        self.assertEqual(item.span, (0, 22))
        self.assertEqual(item.context, text)

    def test_an_empty_id_is_rejected(self) -> None:
        with self.assertRaises(ModelError):
            ClaimInput("", "text", (0, 4), "text")

    def test_empty_text_is_rejected(self) -> None:
        with self.assertRaises(ModelError):
            ClaimInput("c-1", "  ", (0, 2), "  ")

    def test_a_bad_span_is_rejected(self) -> None:
        with self.assertRaises(ModelError):
            ClaimInput("c-1", "text", (10, 2), "text")

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(ClaimInput("c-1", "t", (0, 1), "t").as_dict())


class IntentEvidenceTests(unittest.TestCase):
    def test_a_well_formed_intent_is_accepted(self) -> None:
        item = _intent()

        self.assertEqual(item.relation, GUARANTEE)
        self.assertTrue(item.asserted)

    def test_an_unknown_relation_is_rejected(self) -> None:
        with self.assertRaises(ModelError):
            _intent(relation="VIBES")

    def test_an_unknown_frame_is_rejected(self) -> None:
        with self.assertRaises(ModelError):
            _intent(frame="telepathy")

    def test_a_pattern_id_is_required(self) -> None:
        with self.assertRaises(ModelError):
            _intent(pattern_id="  ")

    def test_negated_intents_are_not_asserted(self) -> None:
        self.assertFalse(_intent(negated=True).asserted)

    def test_hedged_intents_are_not_asserted(self) -> None:
        self.assertFalse(_intent(hedge="if").asserted)

    def test_the_marker_names_relation_entity_frame_and_state(self) -> None:
        marker = _intent().marker

        self.assertIn("guarantee", marker)
        self.assertIn("return", marker)
        self.assertIn("copular", marker)
        self.assertIn("asserted", marker)

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(_intent().as_dict())


class RiskClaimConstraintTests(unittest.TestCase):
    """The phase's first two constraints, enforced structurally."""

    def test_a_claim_without_evidence_is_rejected(self) -> None:
        with self.assertRaises(ModelError):
            _claim(evidence=())

    def test_every_claim_in_this_module_carries_evidence(self) -> None:
        self.assertTrue(_claim().evidence)

    def test_the_source_span_is_kept(self) -> None:
        claim = _claim(source_span=(3, 29))

        self.assertEqual(claim.source_span, (3, 29))
        self.assertIn("source_span", claim.as_dict())

    def test_a_bad_span_is_rejected(self) -> None:
        with self.assertRaises(ModelError):
            _claim(source_span=(9, 1))

    def test_an_unknown_speaker_is_rejected(self) -> None:
        with self.assertRaises(ModelError):
            _claim(speaker="nobody")

    def test_an_unknown_stance_is_rejected(self) -> None:
        with self.assertRaises(ModelError):
            _claim(stance="shrugged")

    def test_confidence_outside_zero_to_one_is_rejected(self) -> None:
        with self.assertRaises(ModelError):
            _claim(confidence=1.4)

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(_claim().as_dict(), sort_keys=True)

    def test_render_names_the_claim_and_its_intents(self) -> None:
        rendered = _claim().render()

        self.assertIn("claim-001", rendered)
        self.assertIn(GUARANTEE, rendered)


class RiskClaimSemanticsTests(unittest.TestCase):
    def test_an_author_endorsed_claim_is_authorial(self) -> None:
        self.assertTrue(_claim(speaker="author", stance="endorsed").is_authorial)

    def test_an_endorsed_third_party_claim_is_authorial(self) -> None:
        self.assertTrue(_claim(speaker="third_party", stance="endorsed").is_authorial)

    def test_the_default_voice_is_authorial(self) -> None:
        self.assertTrue(_claim(speaker="unknown", stance="uncertain").is_authorial)

    def test_a_quoted_claim_is_not_authorial(self) -> None:
        self.assertFalse(_claim(speaker="third_party", stance="quoted").is_authorial)

    def test_a_rejected_claim_is_not_authorial(self) -> None:
        claim = _claim(speaker="author", stance="rejected")

        self.assertTrue(claim.is_rejected)
        self.assertFalse(claim.is_authorial)

    def test_the_relations_helper_lists_asserted_relations(self) -> None:
        claim = _claim(intents=(_intent(), _intent(negated=True, relation=ADVICE)))

        self.assertEqual(claim.relations, (GUARANTEE,))

    def test_intent_for_finds_an_asserted_relation(self) -> None:
        self.assertIsNotNone(_claim().intent_for(GUARANTEE))
        self.assertIsNone(_claim().intent_for(PREDICTION))


class RiskDecisionConstraintTests(unittest.TestCase):
    """Constraint 2: a risk decision may not exist without evidence."""

    def test_a_decision_without_evidence_is_rejected(self) -> None:
        with self.assertRaises(ModelError):
            _decision(evidence=())

    def test_a_decision_without_a_rule_is_rejected(self) -> None:
        with self.assertRaises(ModelError):
            _decision(rule="")

    def test_a_decision_without_an_action_is_rejected(self) -> None:
        with self.assertRaises(ModelError):
            _decision(action="")

    def test_a_decision_without_a_category_is_rejected(self) -> None:
        with self.assertRaises(ModelError):
            _decision(category="")

    def test_suppression_is_recorded(self) -> None:
        self.assertTrue(_decision(kept=False).suppressed)

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(_decision().as_dict())


class TraceTests(unittest.TestCase):
    """Step 5: every final judgement is traceable."""

    def setUp(self) -> None:
        self.trace = ClaimTrace(
            claim=_claim(),
            decisions=(_decision(),),
            suppressed=(_decision(category="market_prediction", kept=False),),
        )

    def test_the_trace_has_the_documented_shape(self) -> None:
        payload = self.trace.as_dict()

        for key in (
            "claim",
            "speaker",
            "stance",
            "intent",
            "evidence",
            "decision",
        ):
            self.assertIn(key, payload)

    def test_the_trace_names_the_relation_and_entity(self) -> None:
        payload = self.trace.as_dict()

        self.assertEqual(payload["intent"]["relation"], GUARANTEE)
        self.assertEqual(payload["intent"]["entity"], RETURN)

    def test_the_trace_carries_the_evidence(self) -> None:
        self.assertTrue(self.trace.as_dict()["evidence"])

    def test_the_trace_says_which_claims_produced_the_decision(self) -> None:
        self.assertEqual(self.trace.as_dict()["decision"]["category"], "financial_guarantee")

    def test_suppressed_decisions_are_recorded_with_their_reason(self) -> None:
        payload = self.trace.as_dict()

        self.assertEqual(len(payload["suppressed"]), 1)
        self.assertFalse(payload["suppressed"][0]["kept"])

    def test_the_span_is_in_the_trace(self) -> None:
        self.assertIn("source_span", self.trace.as_dict())

    def test_render_shows_the_chain(self) -> None:
        rendered = self.trace.render()

        for token in ("text", "intent", "evidence", "decision"):
            self.assertIn(token, rendered)

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(self.trace.as_dict(), sort_keys=True)


class ResultTests(unittest.TestCase):
    def setUp(self) -> None:
        trace = ClaimTrace(claim=_claim(), decisions=(_decision(),))
        self.result = RiskEvaluationResult(
            text="This return is guaranteed.",
            claims=(_claim(),),
            traces=(trace,),
            final_decision=(_decision(),),
            baseline=(),
        )

    def test_categories_come_from_kept_decisions(self) -> None:
        self.assertEqual(self.result.categories, ("financial_guarantee",))

    def test_actions_are_exposed_per_category(self) -> None:
        self.assertEqual(self.result.actions, {"financial_guarantee": "block"})

    def test_the_result_is_flagged(self) -> None:
        self.assertTrue(self.result.flagged)

    def test_a_trace_can_be_looked_up(self) -> None:
        self.assertEqual(self.result.trace_for("claim-001").claim_id, "claim-001")

    def test_looking_up_a_missing_trace_raises(self) -> None:
        with self.assertRaises(ModelError):
            self.result.trace_for("claim-999")

    def test_the_baseline_is_kept_alongside(self) -> None:
        self.assertEqual(self.result.baseline, ())

    def test_trace_dicts_returns_the_documented_shape(self) -> None:
        self.assertEqual(len(self.result.trace_dicts()), 1)

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(self.result.as_dict(), sort_keys=True)

    def test_render_states_both_verdicts(self) -> None:
        rendered = self.result.render()

        self.assertIn("baseline", rendered)
        self.assertIn("v3", rendered)


class EvidenceHelperTests(unittest.TestCase):
    def test_groups_are_merged_and_de_duplicated_in_order(self) -> None:
        merged = evidence_strings(("a", "b"), ("b", "c"), (), ("d",))

        self.assertEqual(merged, ("a", "b", "c", "d"))

    def test_empty_entries_are_dropped(self) -> None:
        self.assertEqual(evidence_strings(("", "a")), ("a",))

    def test_no_groups_is_empty(self) -> None:
        self.assertEqual(evidence_strings(), ())


if __name__ == "__main__":
    unittest.main()
