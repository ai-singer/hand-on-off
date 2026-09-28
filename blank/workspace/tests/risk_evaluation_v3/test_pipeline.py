"""Step 2 and Step 5: the pipeline, the stage order, and the trace contract."""

from __future__ import annotations

import json
import unittest

from risk_evaluation.v3.model import V3_VERSION
from risk_evaluation.v3.pipeline import (
    DEFAULT,
    PipelineConfig,
    RiskEvaluationPipeline,
    evaluate,
)


GUARANTEE = "This return is guaranteed."
MIXED = "Economists forecast slower growth in Europe. This fund cannot lose money."


class PipelineContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pipeline = RiskEvaluationPipeline()

    def test_the_pipeline_names_itself_and_its_version(self) -> None:
        self.assertEqual(self.pipeline.name, "risk-evaluation-v3")
        self.assertEqual(self.pipeline.version, V3_VERSION)

    def test_the_module_helper_matches_the_default_instance(self) -> None:
        self.assertEqual(
            evaluate(GUARANTEE).categories, DEFAULT.evaluate(GUARANTEE).categories
        )

    def test_every_stage_is_recorded(self) -> None:
        result = self.pipeline.evaluate(GUARANTEE)
        stages = [item["stage"] for item in result.evidence["stages"]]

        self.assertIn("claim_extraction", stages)
        self.assertIn("attribution", stages)
        self.assertIn("intent_pattern", stages)
        self.assertIn("semantic_fallback", stages)

    def test_the_stage_order_is_the_documented_one(self) -> None:
        result = self.pipeline.evaluate(MIXED)
        stages = [item["stage"] for item in result.evidence["stages"]]

        self.assertLess(stages.index("attribution"), stages.index("intent_pattern"))
        self.assertLess(
            stages.index("intent_pattern"), stages.index("semantic_fallback")
        )

    def test_the_baseline_is_computed_alongside(self) -> None:
        result = self.pipeline.evaluate(GUARANTEE)

        self.assertEqual(result.baseline, ())

    def test_empty_input_yields_no_claims(self) -> None:
        result = self.pipeline.evaluate("   ")

        self.assertEqual(result.claims, ())
        self.assertEqual(result.categories, ())

    def test_non_string_input_is_rejected(self) -> None:
        from risk_evaluation.v3.model import ModelError

        with self.assertRaises(ModelError):
            self.pipeline.evaluate(7)  # type: ignore[arg-type]

    def test_evaluation_is_deterministic(self) -> None:
        """The recorded trace is a function of the input, timings excluded."""

        self.assertEqual(
            self.pipeline.evaluate(MIXED).as_dict(),
            self.pipeline.evaluate(MIXED).as_dict(),
        )

    def test_timings_can_be_requested_separately(self) -> None:
        pipeline = RiskEvaluationPipeline(config=PipelineConfig(record_timings=True))
        result = pipeline.evaluate(MIXED)

        self.assertTrue(
            any(item["milliseconds"] for item in result.evidence["stages"])
        )

    def test_timings_are_off_by_default(self) -> None:
        result = self.pipeline.evaluate(MIXED)

        self.assertTrue(
            all(item["milliseconds"] == 0 for item in result.evidence["stages"])
        )

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(self.pipeline.evaluate(MIXED).as_dict(), sort_keys=True)


class ClaimExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pipeline = RiskEvaluationPipeline()

    def test_a_two_sentence_text_yields_two_claims(self) -> None:
        self.assertEqual(len(self.pipeline.extract(MIXED)), 2)

    def test_every_claim_carries_a_span_into_the_source(self) -> None:
        for claim in self.pipeline.extract(MIXED):
            self.assertGreater(claim.span[1], claim.span[0])

    def test_the_span_matches_the_claim_text(self) -> None:
        for claim in self.pipeline.extract(MIXED):
            self.assertEqual(claim.context.strip(), claim.text)

    def test_extraction_is_delegated_to_the_attribution_adapter(self) -> None:
        """No second claim parser exists in v3."""

        claims = self.pipeline.extract(MIXED)

        self.assertEqual([c.claim_id for c in claims], ["claim-001", "claim-002"])

    def test_empty_text_extracts_nothing(self) -> None:
        self.assertEqual(self.pipeline.extract(""), ())


class FallbackTests(unittest.TestCase):
    """The semantic evaluator is a fallback, not a replacement."""

    def setUp(self) -> None:
        self.pipeline = RiskEvaluationPipeline()

    def test_the_fallback_is_searched_when_the_intent_layer_is_silent(self) -> None:
        result = self.pipeline.evaluate("Do not miss this opportunity.")
        claim = result.claims[0]

        self.assertEqual(claim.intents, ())
        self.assertIn("emotional_manipulation", claim.fallback_categories)

    def test_the_fallback_is_skipped_when_a_relation_was_asserted(self) -> None:
        result = self.pipeline.evaluate(GUARANTEE)
        claim = result.claims[0]

        self.assertTrue(claim.asserted_intents)
        self.assertTrue(
            any("rule:semantic.skipped" in item for item in claim.fallback_evidence)
        )

    def test_the_fallback_reason_is_recorded(self) -> None:
        result = self.pipeline.evaluate("Do not miss this opportunity.")

        self.assertTrue(
            any(
                "intent-found-nothing" in item
                for item in result.claims[0].fallback_evidence
            )
        )

    def test_a_relation_the_intent_layer_found_is_not_sent_to_the_fallback(
        self,
    ) -> None:
        pipeline = RiskEvaluationPipeline()
        result = pipeline.evaluate(GUARANTEE)

        self.assertIn("financial_guarantee", result.categories)
        self.assertEqual(result.claims[0].fallback_categories, ())


class TraceCompletenessTests(unittest.TestCase):
    """The phase's trace requirement: 100% of claims carry evidence."""

    TEXTS = (
        GUARANTEE,
        MIXED,
        "Analysts say this fund cannot lose money.",
        "We disagree with the view that this fund cannot lose money.",
        "Do not miss this opportunity.",
        "The company reports its results in March.",
        "The share price will certainly double next year.",
        "Returns are not guaranteed.",
    )

    def test_every_claim_carries_evidence(self) -> None:
        pipeline = RiskEvaluationPipeline()
        for text in self.TEXTS:
            result = pipeline.evaluate(text)
            for claim in result.claims:
                self.assertTrue(claim.evidence, f"{text!r} / {claim.claim_id}")

    def test_every_decision_carries_evidence(self) -> None:
        pipeline = RiskEvaluationPipeline()
        for text in self.TEXTS:
            for decision in pipeline.evaluate(text).final_decision:
                self.assertTrue(decision.evidence, text)

    def test_the_trace_reports_full_coverage(self) -> None:
        pipeline = RiskEvaluationPipeline()
        for text in self.TEXTS:
            self.assertTrue(pipeline.evaluate(text).evidence["trace_complete"], text)

    def test_every_trace_can_name_the_relation_when_there_is_one(self) -> None:
        result = RiskEvaluationPipeline().evaluate(GUARANTEE)
        payload = result.trace_dicts()[0]

        self.assertEqual(payload["intent"]["relation"], "GUARANTEE")

    def test_a_trace_without_a_relation_says_so(self) -> None:
        result = RiskEvaluationPipeline().evaluate("The company reports its results in March.")

        self.assertIsNone(result.trace_dicts()[0]["intent"])

    def test_suppressed_decisions_are_in_the_trace(self) -> None:
        result = RiskEvaluationPipeline().evaluate("Returns are not guaranteed.")
        payload = result.trace_dicts()[0]

        self.assertTrue(payload["suppressed"] or payload["decisions"] == [])


class DecisionIntegrationTests(unittest.TestCase):
    """The three decision cases, end to end."""

    def setUp(self) -> None:
        self.pipeline = RiskEvaluationPipeline()

    def test_case_one(self) -> None:
        result = self.pipeline.evaluate(GUARANTEE)

        self.assertEqual(result.categories, ("financial_guarantee",))
        self.assertEqual(result.actions, {"financial_guarantee": "block"})

    def test_case_two_with_an_uncheckable_source(self) -> None:
        result = self.pipeline.evaluate("Analysts say this fund cannot lose money.")

        self.assertEqual(result.categories, ("unverified_information",))
        self.assertEqual(result.actions, {"unverified_information": "require_evidence"})

    def test_case_three(self) -> None:
        result = self.pipeline.evaluate(
            "We disagree with the view that this fund cannot lose money."
        )

        self.assertEqual(result.categories, ())

    def test_the_article_risk_survives_a_borrowed_attribution(self) -> None:
        result = self.pipeline.evaluate(MIXED)

        self.assertEqual(result.categories, ("financial_guarantee",))

    def test_no_author_risk_is_lost(self) -> None:
        for text in (
            "We believe this fund cannot lose money.",
            "Shift your savings into this fund.",
            "Do not miss this opportunity.",
        ):
            self.assertTrue(self.pipeline.evaluate(text).flagged, text)

    def test_neutral_text_stays_neutral(self) -> None:
        for text in (
            "The company reports its results in March.",
            "Diversification spreads risk across assets.",
            "A price-to-earnings ratio compares price with earnings per share.",
        ):
            self.assertEqual(self.pipeline.evaluate(text).categories, (), text)


class MergedDecisionTests(unittest.TestCase):
    def test_one_decision_per_category_across_claims(self) -> None:
        result = RiskEvaluationPipeline().evaluate(
            "This fund cannot lose money. Your capital is guaranteed."
        )

        self.assertEqual([d.category for d in result.final_decision], ["financial_guarantee"])

    def test_the_merged_decision_records_every_contributing_claim(self) -> None:
        result = RiskEvaluationPipeline().evaluate(
            "This fund cannot lose money. Your capital is guaranteed."
        )

        self.assertIn(",", result.final_decision[0].claim_id)


class ConfigTests(unittest.TestCase):
    def test_layers_can_be_disabled(self) -> None:
        pipeline = RiskEvaluationPipeline(
            config=PipelineConfig(use_intent_patterns=False)
        )
        result = pipeline.evaluate(GUARANTEE)

        self.assertEqual(result.categories, ())

    def test_disabling_the_fallback_is_recorded(self) -> None:
        pipeline = RiskEvaluationPipeline(
            config=PipelineConfig(use_semantic_fallback=False)
        )
        result = pipeline.evaluate("Do not miss this opportunity.")

        self.assertEqual(result.categories, ())

    def test_the_config_is_recorded_in_the_result(self) -> None:
        result = RiskEvaluationPipeline().evaluate(GUARANTEE)

        self.assertIn("config", result.evidence)

    def test_the_default_config_enables_every_layer(self) -> None:
        config = PipelineConfig()

        self.assertTrue(config.use_attribution)
        self.assertTrue(config.use_intent_patterns)
        self.assertTrue(config.use_semantic_fallback)

    def test_disabling_attribution_leaves_the_claim_unattributed(self) -> None:
        pipeline = RiskEvaluationPipeline(config=PipelineConfig(use_attribution=False))
        result = pipeline.evaluate("Analysts say this fund cannot lose money.")

        self.assertEqual(result.claims[0].speaker, "unknown")

    def test_disabling_attribution_turns_off_the_refinement_with_it(self) -> None:
        """The Phase 8.7 refinement is part of the attribution stage.

        It types a source and finds rejection cues, both of which are attribution
        answers. Keeping it running while the layer it refines was switched off
        would make `use_attribution` mean less than it says.
        """

        text = "Analysts say this fund cannot lose money."
        off = RiskEvaluationPipeline(config=PipelineConfig(use_attribution=False))
        on = RiskEvaluationPipeline()

        self.assertEqual(off.evaluate(text).claims[0].speaker, "unknown")
        self.assertEqual(off.evaluate(text).claims[0].sourcing_categories, ())
        self.assertEqual(on.evaluate(text).claims[0].speaker, "third_party")
        self.assertEqual(
            on.evaluate(text).claims[0].sourcing_categories,
            ("unverified_information",),
        )


class BaselineComparisonTests(unittest.TestCase):
    def test_the_baseline_is_the_evaluator_on_the_whole_text(self) -> None:
        from risk_evaluation.semantic_evaluator_v2 import SemanticRiskEvaluatorV2

        text = "This is a guaranteed return."
        expected = tuple(
            sorted({i.category for i in SemanticRiskEvaluatorV2().evaluate_text(text)})
        )

        self.assertEqual(RiskEvaluationPipeline().evaluate(text).baseline, expected)

    def test_the_baseline_misses_what_the_intent_layer_catches(self) -> None:
        result = RiskEvaluationPipeline().evaluate(GUARANTEE)

        self.assertEqual(result.baseline, ())
        self.assertEqual(result.categories, ("financial_guarantee",))


if __name__ == "__main__":
    unittest.main()
