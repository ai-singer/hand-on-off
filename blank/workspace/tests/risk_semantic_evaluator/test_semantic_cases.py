from __future__ import annotations

import unittest

from risk_evaluation.semantic_evaluator import SemanticRiskEvaluator


class RequiredSemanticCaseTests(unittest.TestCase):
    """The exact examples Phase 7.2 requires the evaluator to handle."""

    def setUp(self) -> None:
        self.evaluator = SemanticRiskEvaluator()

    def _categories(self, text: str) -> set[str]:
        return {item.category for item in self.evaluator.evaluate_text(text)}

    # Investment advice: action inducement + financial object
    def test_investment_advice_requires_action_and_object(self) -> None:
        for text in (
            "You should buy this stock today.",
            "Move your money into this company.",
        ):
            with self.subTest(text=text):
                self.assertIn("investment_advice", self._categories(text), text)

    # Market prediction: future outcome + certainty
    def test_market_prediction_requires_future_and_certainty(self) -> None:
        for text in (
            "The price will definitely rise.",
            "The share price is bound to double by next year.",
            "Revenue is sure to grow every quarter from here.",
        ):
            with self.subTest(text=text):
                self.assertIn("market_prediction", self._categories(text), text)

    def test_attributed_expectation_is_a_documented_miss(self) -> None:
        """A price target framed as someone's expectation is not flagged.

        The taxonomy defines market_prediction as an outcome stated *as a
        certainty*; "management expects" is attributed and hedged, so the
        certainty requirement is not met. Arguably correct per the taxonomy,
        but it is a real recall gap for named price targets, and it is reported
        as a benchmark failure rather than patched with a case-specific rule.
        """

        text = "Management expects the stock to reach 500."

        self.assertEqual(self._categories(text), set())

    # Financial guarantee: unconditional outcome
    def test_financial_guarantee_is_detected(self) -> None:
        for text in (
            "This opportunity cannot fail.",
            "This is a zero risk way to grow capital.",
            "You cannot lose money with this fund.",
        ):
            with self.subTest(text=text):
                self.assertIn("financial_guarantee", self._categories(text), text)

    # Unverified information: source the reader cannot check
    def test_unverified_information_is_detected(self) -> None:
        for text in (
            "People say insiders know this will happen.",
            "I heard the company is about to be acquired.",
            "Sources claim revenue will double next quarter.",
        ):
            with self.subTest(text=text):
                self.assertIn("unverified_information", self._categories(text), text)

    def test_emotional_pressure_is_detected(self) -> None:
        self.assertIn(
            "emotional_manipulation",
            self._categories("Everyone is buying before it is too late."),
        )

    def test_a_sentence_can_carry_more_than_one_risk(self) -> None:
        categories = self._categories(
            "There is no way this valuation drops again, so buy now."
        )

        self.assertIn("financial_guarantee", categories)

    def test_disclaimed_risk_is_not_flagged(self) -> None:
        for text in (
            "This is not a guaranteed return, and the material explains why.",
            "Past performance does not guarantee future results.",
            "Analysts do not expect the share price to rise this year.",
            "The report describes the cost structure; no recommendation is made.",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.evaluator.evaluate_text(text), (), text)

    def test_legitimate_explanation_is_not_flagged(self) -> None:
        for text in (
            "The income statement shows how revenue converts into margin.",
            "Quarterly cash flow grew while the ratio stayed stable.",
            "A common misunderstanding is that revenue equals profit.",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.evaluator.evaluate_text(text), (), text)

    def test_explanations_name_the_signals_that_fired(self) -> None:
        results = self.evaluator.evaluate_text("You should buy this stock today.")

        self.assertTrue(results)
        detail = results[0].detail
        self.assertIn("Signals:", detail)
        self.assertIn("directive", detail)
        self.assertIn("financial_object", detail)


if __name__ == "__main__":
    unittest.main()
