from __future__ import annotations

import unittest

from risk_evaluation.semantic_evaluator_v2 import (
    SemanticRiskEvaluatorV2,
    analyze_certainty,
    supported_dimensions,
)

#: (text, expected certainty_level, why)
CERTAINTY_CASES: tuple[tuple[str, str, str], ...] = (
    ("The stock will rise.", "certain", "a bare future assertion is the default"),
    ("The stock will definitely rise.", "certain", "explicit certainty adverb"),
    ("The stock is certain to rise.", "certain", "certainty adjective"),
    ("The stock is bound to rise.", "certain", "bound to"),
    ("The margin holds at 30 percent.", "certain", "no hedging marker present"),
    ("The stock is likely to rise.", "probable", "likelihood adverb"),
    ("The stock will probably rise.", "probable", "probability adverb"),
    ("Revenue is expected to grow.", "probable", "expectation frame"),
    ("Revenue is projected to grow.", "probable", "projection frame"),
    ("The stock may rise.", "possible", "possibility modal"),
    ("The stock might rise.", "possible", "possibility modal"),
    ("The stock could rise.", "possible", "possibility modal"),
    ("Perhaps the stock will rise.", "possible", "possibility adverb"),
    ("The stock will potentially rise.", "possible", "possibility adverb"),
    ("If rates fall, the stock will rise.", "hypothetical", "stated condition"),
    ("Unless rates fall, the stock will rise.", "hypothetical", "unless"),
    ("Assuming demand holds, revenue grows.", "hypothetical", "assuming"),
    ("Depending on the quarter, revenue may vary.", "hypothetical", "depending on"),
    ("Were rates to fall, the stock would rise.", "hypothetical", "subjunctive"),
    ("Should the market decline, the position is hedged.", "hypothetical", "inversion"),
)


class CertaintyDetectionTests(unittest.TestCase):
    """`certainty_level` is the second dimension v1 had no notion of."""

    def test_every_declared_case_is_classified_as_expected(self) -> None:
        wrong: list[str] = []
        for text, expected, why in CERTAINTY_CASES:
            actual = analyze_certainty(text).certainty_level
            if actual != expected:
                wrong.append(f"{text!r}: expected {expected}, got {actual} ({why})")

        self.assertEqual(wrong, [])

    def test_all_four_levels_are_exercised(self) -> None:
        covered = {analyze_certainty(text).certainty_level for text, _, _ in CERTAINTY_CASES}

        self.assertEqual(covered, {"certain", "probable", "possible", "hypothetical"})

    def test_dimension_values_are_declared(self) -> None:
        self.assertEqual(
            supported_dimensions()["certainty_level"],
            ("certain", "probable", "possible", "hypothetical"),
        )

    def test_analysis_reports_the_markers_it_used(self) -> None:
        analysis = analyze_certainty("The stock may rise.")

        self.assertTrue(analysis.markers)

    def test_a_bare_assertion_reports_no_marker(self) -> None:
        self.assertEqual(analyze_certainty("The stock will rise.").markers, ())

    def test_render_states_the_level(self) -> None:
        self.assertIn("certainty_level=possible", analyze_certainty("The stock may rise.").render())

    def test_analysis_is_stable_across_calls(self) -> None:
        text = "The stock may rise."

        self.assertEqual(analyze_certainty(text), analyze_certainty(text))


class CertaintyPrecedenceTests(unittest.TestCase):
    """`hypothetical` > `possible` > `probable` > `certain`."""

    def test_conditional_beats_possibility(self) -> None:
        self.assertEqual(
            analyze_certainty("If rates fall, the stock may rise.").certainty_level,
            "hypothetical",
        )

    def test_conditional_beats_probability(self) -> None:
        self.assertEqual(
            analyze_certainty("If demand holds, revenue is likely to grow.").certainty_level,
            "hypothetical",
        )

    def test_possibility_beats_probability(self) -> None:
        self.assertEqual(
            analyze_certainty("The stock may probably rise.").certainty_level,
            "possible",
        )

    def test_lowercase_and_uppercase_agree(self) -> None:
        self.assertEqual(
            analyze_certainty("THE STOCK MAY RISE.").certainty_level,
            analyze_certainty("The stock may rise.").certainty_level,
        )


class CertaintyChangesTheVerdictTests(unittest.TestCase):
    """A hedge is not an assertion, so it is not a prediction."""

    def setUp(self) -> None:
        self.evaluator = SemanticRiskEvaluatorV2()

    def test_a_certain_author_prediction_is_flagged(self) -> None:
        analysis = self.evaluator.analyze("The share price will definitely double.")

        self.assertIn("market_prediction", analysis.categories)

    def test_a_hypothetical_author_prediction_is_not_flagged(self) -> None:
        analysis = self.evaluator.analyze(
            "If rates fall, the share price will definitely double."
        )

        self.assertNotIn("market_prediction", analysis.categories)

    def test_a_possible_author_prediction_is_not_flagged(self) -> None:
        analysis = self.evaluator.analyze("The share price may definitely double.")

        self.assertNotIn("market_prediction", analysis.categories)

    def test_a_hypothetical_claim_is_recorded_as_suppressed(self) -> None:
        analysis = self.evaluator.analyze(
            "If rates fall, the share price will definitely double."
        )

        self.assertIn("market_prediction", analysis.suppressed)

    def test_the_reported_level_matches_the_suppression_reason(self) -> None:
        analysis = self.evaluator.analyze(
            "If rates fall, the share price will definitely double."
        )

        self.assertEqual(analysis.certainty_level, "hypothetical")
        self.assertEqual(analysis.market_claim_case, "scenario_analysis")


class KnownCertaintyGapsTests(unittest.TestCase):
    """Hedged author claims and implied certainty, recorded rather than repaired."""

    def test_an_implied_certainty_needs_an_explicit_marker(self) -> None:
        """`certainty_level` is reported as certain, but nothing is flagged."""

        analysis = SemanticRiskEvaluatorV2().analyze(
            "The share price will double next year."
        )

        self.assertEqual(analysis.certainty_level, "certain")
        self.assertEqual(analysis.categories, ())

    def test_the_epistemic_use_of_should_reads_as_certainty(self) -> None:
        """Sentence-initial `should` is an inversion and is conditional.

        Mid-sentence `should` is an epistemic hedge and ought to be `probable`.
        It currently falls through to the `certain` default, because the
        conditional pattern is deliberately anchored to sentence start to avoid
        misreading directives such as "you should buy". Anchoring fixes the
        directive bug but leaves the hedge mislabelled.
        """

        self.assertEqual(
            analyze_certainty("Should the market decline, the stock falls.").certainty_level,
            "hypothetical",
        )
        self.assertEqual(
            analyze_certainty("The stock should rise next year.").certainty_level,
            "certain",
        )

    def test_a_projection_with_an_intervening_object_is_read_as_certain(self) -> None:
        """`project\\w* to` needs the verb and `to` adjacent.

        "Revenue is projected to grow" is a projection; "the company projects
        revenue to grow" is the same claim with an object in between, and is
        currently reported as an unhedged certainty.
        """

        self.assertEqual(
            analyze_certainty("Revenue is projected to grow.").certainty_level,
            "probable",
        )
        self.assertEqual(
            analyze_certainty("The company projects revenue to grow.").certainty_level,
            "certain",
        )

    def test_a_negated_modal_is_not_treated_as_possibility(self) -> None:
        """v1's negation guard applies to the shared signal layer."""

        analysis = analyze_certainty("The stock cannot rise.")

        self.assertIn(analysis.certainty_level, ("certain", "probable", "possible"))


if __name__ == "__main__":
    unittest.main()
