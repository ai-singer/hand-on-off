from __future__ import annotations

import unittest

from risk_evaluation.benchmark_v2 import V3_CASES
from risk_evaluation.semantic_evaluator import SemanticRiskEvaluator
from risk_evaluation.semantic_evaluator_v2 import (
    READER_PRESSURE_PATTERNS,
    SemanticRiskEvaluatorV2,
    detect_reader_pressure,
)
from risk_evaluation.taxonomy import RISK_TAXONOMY
from risk_evaluation.taxonomy_v2 import (
    AUTHOR_VOICE_CATEGORIES,
    is_direct_prediction,
)


class DramaticVocabularyTests(unittest.TestCase):
    """Guide v2 section 6.1: dramatic market vocabulary is not manipulation."""

    def setUp(self) -> None:
        self.v1 = SemanticRiskEvaluator()
        self.v2 = SemanticRiskEvaluatorV2()

    def test_dramatic_vocabulary_alone_is_not_manipulation(self) -> None:
        analysis = self.v2.analyze("Panic is spreading.")

        self.assertEqual(analysis.categories, ())

    def test_v1_did_flag_that_sentence(self) -> None:
        """The false positive v2 exists to remove."""

        flagged = {r.category for r in self.v1.evaluate_text("Panic is spreading.")}

        self.assertIn("emotional_manipulation", flagged)

    def test_a_certain_prediction_is_not_also_manipulation(self) -> None:
        analysis = self.v2.analyze("The market will certainly crash.")

        self.assertEqual(analysis.categories, ("market_prediction",))

    def test_v1_double_counted_that_sentence(self) -> None:
        flagged = {
            r.category for r in self.v1.evaluate_text("The market will certainly crash.")
        }

        self.assertEqual(
            flagged, {"market_prediction", "emotional_manipulation"}
        )

    def test_reader_pressure_is_required_for_manipulation(self) -> None:
        analysis = self.v2.analyze("Do not miss this opportunity.")

        self.assertEqual(analysis.categories, ("emotional_manipulation",))
        self.assertTrue(detect_reader_pressure("Do not miss this opportunity."))

    def test_reader_directed_pressure_v1_missed_is_now_caught(self) -> None:
        """A genuine new true positive, not merely a removed false one."""

        text = "You would be crazy not to buy."
        before = {r.category for r in self.v1.evaluate_text(text)}
        after = self.v2.analyze(text).categories

        self.assertEqual(before, set())
        self.assertEqual(after, ("emotional_manipulation",))

    def test_pressure_and_prediction_can_coexist(self) -> None:
        analysis = self.v2.analyze(
            "The stock will definitely rise, do not miss out."
        )

        self.assertEqual(
            set(analysis.categories), {"market_prediction", "emotional_manipulation"}
        )


class AttributionSeparationTests(unittest.TestCase):
    """Guide v2 section 3: an attributed claim is not the article's claim."""

    def setUp(self) -> None:
        self.v1 = SemanticRiskEvaluator()
        self.v2 = SemanticRiskEvaluatorV2()

    def test_only_the_attribution_agnostic_category_survives(self) -> None:
        analysis = self.v2.analyze("Sources say the market will certainly crash.")

        self.assertEqual(analysis.categories, ("unverified_information",))

    def test_v1_reported_all_three_categories(self) -> None:
        flagged = {
            r.category
            for r in self.v1.evaluate_text("Sources say the market will certainly crash.")
        }

        self.assertEqual(
            flagged,
            {
                "market_prediction",
                "emotional_manipulation",
                "unverified_information",
            },
        )

    def test_the_suppressed_author_voice_category_is_reported(self) -> None:
        analysis = self.v2.analyze("Sources say the market will certainly crash.")

        self.assertIn("market_prediction", analysis.suppressed)

    def test_a_named_source_is_handled_the_same_way(self) -> None:
        analysis = self.v2.analyze("Analysts say the market will certainly crash.")

        self.assertEqual(analysis.categories, ("unverified_information",))

    def test_unverified_information_is_never_suppressed_by_attribution(self) -> None:
        for text in (
            "Sources say revenue will double.",
            "Analysts say the market will certainly crash.",
            "Rumour has it the company will be acquired.",
        ):
            self.assertIn(
                "unverified_information", self.v2.analyze(text).categories, text
            )


class InvariantTests(unittest.TestCase):
    """Properties that must hold for every case, not just the convenient ones."""

    def setUp(self) -> None:
        self.evaluator = SemanticRiskEvaluatorV2()

    def _analyses(self):
        for case in V3_CASES:
            yield case, self.evaluator.analyze(case.text)

    def test_manipulation_implies_reader_pressure(self) -> None:
        violations = [
            case.case_id
            for case, analysis in self._analyses()
            if "emotional_manipulation" in analysis.categories
            and not detect_reader_pressure(case.text)
        ]

        self.assertEqual(violations, [])

    def test_prediction_implies_an_author_voice_certainty(self) -> None:
        violations = [
            case.case_id
            for case, analysis in self._analyses()
            if "market_prediction" in analysis.categories
            and not is_direct_prediction(
                statement_source=analysis.statement_source,
                certainty_level=analysis.certainty_level,
            )
        ]

        self.assertEqual(violations, [])

    def test_author_voice_categories_never_survive_attribution(self) -> None:
        violations = [
            case.case_id
            for case, analysis in self._analyses()
            if analysis.statement_source != "author"
            and set(analysis.categories) & set(AUTHOR_VOICE_CATEGORIES)
        ]

        self.assertEqual(violations, [])

    def test_v2_invents_no_category(self) -> None:
        known = {entry.name for entry in RISK_TAXONOMY}
        invented = {
            name
            for _, analysis in self._analyses()
            for name in analysis.categories
            if name not in known
        }

        self.assertEqual(invented, set())

    def test_a_category_is_never_both_kept_and_suppressed(self) -> None:
        violations = [
            case.case_id
            for case, analysis in self._analyses()
            if set(analysis.categories) & set(analysis.suppressed)
        ]

        self.assertEqual(violations, [])

    def test_reported_categories_are_deterministically_ordered(self) -> None:
        """Presentation order must be stable; precedence is checked separately.

        Guide v2 section 6.2 documents a precedence order for reports, but the
        implementation sorts alphabetically and `resolve_category_conflicts`'s
        precedence ordering is discarded by the caller. That discrepancy is
        pinned in `test_guide_conformance.py`; here the property asserted is the
        one that actually holds and matters for reproducibility.
        """

        for case, analysis in self._analyses():
            self.assertEqual(
                list(analysis.categories), sorted(analysis.categories), case.case_id
            )
            self.assertEqual(
                len(analysis.categories), len(set(analysis.categories)), case.case_id
            )

    def test_every_result_carries_its_taxonomy_evidence_requirement(self) -> None:
        for case, analysis in self._analyses():
            for result in analysis.results:
                self.assertTrue(result.evidence_required, case.case_id)
                self.assertTrue(result.intent, case.case_id)

    def test_confidence_stays_within_zero_and_one(self) -> None:
        for case, analysis in self._analyses():
            for result in analysis.results:
                self.assertGreaterEqual(result.confidence, 0.0, case.case_id)
                self.assertLessEqual(result.confidence, 1.0, case.case_id)

    def test_reader_pressure_patterns_are_valid_regular_expressions(self) -> None:
        import re

        for pattern in READER_PRESSURE_PATTERNS:
            re.compile(pattern)

    def test_pressure_detection_is_deterministic(self) -> None:
        text = "Everyone is buying and there is no time left."

        self.assertEqual(detect_reader_pressure(text), detect_reader_pressure(text))


if __name__ == "__main__":
    unittest.main()
