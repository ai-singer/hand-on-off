from __future__ import annotations

import unittest

from risk_evaluation.semantic_evaluator_v2 import (
    SemanticRiskEvaluatorV2,
    analyze_certainty,
)

#: Conditional markers from guide v2 section 5, and the level they must produce.
CONDITIONAL_CASES: tuple[tuple[str, str], ...] = (
    ("If the margin holds, revenue grows.", "if"),
    ("Unless rates fall, revenue stalls.", "unless"),
    ("Assuming demand holds, revenue grows.", "assuming"),
    ("Depending on the quarter, revenue varies.", "depending on"),
    ("Provided that demand holds, revenue grows.", "provided that"),
    ("In the event of a downgrade, the position falls.", "in the event"),
    ("Should the market decline, the position falls.", "inverted should"),
    ("Had the deal closed, revenue would have risen.", "inverted had"),
)


class ConditionalDetectionTests(unittest.TestCase):
    def test_every_marker_yields_a_hypothetical_level(self) -> None:
        wrong: list[str] = []
        for text, marker in CONDITIONAL_CASES:
            actual = analyze_certainty(text).certainty_level
            if actual != "hypothetical":
                wrong.append(f"{marker}: expected hypothetical, got {actual}")

        self.assertEqual(wrong, [])

    def test_conditionality_beats_possibility(self) -> None:
        self.assertEqual(
            analyze_certainty("If rates fall, the stock may rise.").certainty_level,
            "hypothetical",
        )

    def test_conditionality_beats_probability(self) -> None:
        self.assertEqual(
            analyze_certainty("If demand holds, revenue is likely to grow.").certainty_level,
            "hypothetical",
        )


class ConditionalOutcomeTests(unittest.TestCase):
    """Guide v2 section 5: a conditional *outcome* is not a prediction."""

    def setUp(self) -> None:
        self.evaluator = SemanticRiskEvaluatorV2()

    def test_a_conditional_prediction_is_not_flagged(self) -> None:
        analysis = self.evaluator.analyze(
            "If rates fall, the share price will definitely double."
        )

        self.assertNotIn("market_prediction", analysis.categories)

    def test_a_conditional_prediction_is_recorded_as_suppressed(self) -> None:
        analysis = self.evaluator.analyze(
            "If rates fall, the share price will definitely double."
        )

        self.assertIn("market_prediction", analysis.suppressed)

    def test_every_marker_suppresses_the_prediction(self) -> None:
        for text, marker in CONDITIONAL_CASES:
            analysis = self.evaluator.analyze(
                text.replace("revenue grows", "revenue will definitely double")
                .replace("revenue stalls", "revenue will definitely double")
                .replace("revenue varies", "revenue will definitely double")
                .replace("the position falls", "the position will definitely double")
            )

            self.assertNotIn("market_prediction", analysis.categories, marker)

    def test_an_unconditional_prediction_is_still_flagged(self) -> None:
        """The suppression must be caused by the condition, not by the vocabulary."""

        analysis = self.evaluator.analyze("The share price will definitely double.")

        self.assertIn("market_prediction", analysis.categories)


class ConditionalDirectiveTests(unittest.TestCase):
    """Guide v2 section 5: a conditional *directive* is still advice."""

    def test_a_conditional_directive_is_still_advice(self) -> None:
        analysis = SemanticRiskEvaluatorV2().analyze(
            "If you want higher returns, buy this stock."
        )

        self.assertEqual(analysis.certainty_level, "hypothetical")
        self.assertIn("investment_advice", analysis.categories)


class KnownConditionalDefectsTests(unittest.TestCase):
    """Guide/implementation disagreements, recorded rather than repaired.

    These are the guide's own published examples. Each assertion pins what the
    evaluator does today, which is not what guide v2 says it should do. They are
    left in place because changing the evaluator after measuring the benchmark
    would be tuning against known cases; they are listed as defects in the
    Phase 7.5 report and are the first item for a following phase.
    """

    def setUp(self) -> None:
        self.evaluator = SemanticRiskEvaluatorV2()

    def test_a_conditional_outcome_containing_should_still_fires_advice(self) -> None:
        """The guide's marker-table example, contradicted by the implementation."""

        analysis = self.evaluator.analyze(
            "Should the market decline, the position would lose value."
        )

        self.assertEqual(analysis.certainty_level, "hypothetical")
        self.assertEqual(analysis.categories, ("investment_advice",))

    def test_a_conditional_outcome_containing_holds_still_fires_advice(self) -> None:
        """`holds` is a v1 directive verb; "the margin holds" is not a directive."""

        analysis = self.evaluator.analyze("If the margin holds, the company could grow.")

        self.assertEqual(analysis.certainty_level, "hypothetical")
        self.assertEqual(analysis.categories, ("investment_advice",))

    def test_the_guide_row_one_example_is_not_reproduced(self) -> None:
        analysis = self.evaluator.analyze(
            "If the margin holds, the company could grow, but that is uncertain."
        )

        self.assertNotEqual(analysis.categories, ())

    def test_were_to_with_a_multiword_subject_is_not_conditional(self) -> None:
        """`were\\s+\\w+\\s+to` only spans a one-word subject.

        "Were the deal to close" has a two-word subject, so the conditional
        pattern misses and the possibility modal decides the level instead.
        """

        self.assertEqual(
            analyze_certainty("Were the deal to close, revenue might rise.").certainty_level,
            "possible",
        )

    def test_were_to_with_a_oneword_subject_is_conditional(self) -> None:
        """The pattern does work in the shape it was written for."""

        self.assertEqual(
            analyze_certainty("Were rates to fall, the stock would rise.").certainty_level,
            "hypothetical",
        )

    def test_an_implied_certainty_in_the_guide_is_not_flagged(self) -> None:
        """Guide v2 section 5 row 4 promises `market_prediction` here."""

        analysis = self.evaluator.analyze("The stock will rise.")

        self.assertEqual(analysis.certainty_level, "certain")
        self.assertEqual(analysis.market_claim_case, "explicit_prediction")
        self.assertEqual(analysis.categories, ())


if __name__ == "__main__":
    unittest.main()
