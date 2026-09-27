from __future__ import annotations

import unittest

from risk_evaluation.semantic_evaluator import (
    NEGATION_WINDOW,
    SIGNAL_PATTERNS,
    SemanticRiskEvaluator,
    detect_signals,
)


class SignalDetectionTests(unittest.TestCase):
    def test_every_declared_signal_class_has_patterns(self) -> None:
        for signal, patterns in SIGNAL_PATTERNS.items():
            self.assertTrue(patterns, signal)

    def test_directive_is_detected(self) -> None:
        signals = detect_signals("You should buy this stock today.")

        values = {match.value for match in signals["directive"]}
        self.assertIn("should", values)
        self.assertIn("buy", values)

    def test_financial_object_is_detected(self) -> None:
        signals = detect_signals("Move your savings into this fund.")

        values = {match.value for match in signals["financial_object"]}
        self.assertIn("savings", values)
        self.assertIn("fund", values)

    def test_future_marker_is_detected(self) -> None:
        signals = detect_signals("The price will rise and is expected to double.")

        values = {match.value for match in signals["future_marker"]}
        self.assertIn("will", values)
        self.assertTrue(any("expected" in value for value in values))

    def test_certainty_marker_is_detected(self) -> None:
        signals = detect_signals("It will definitely and certainly double.")

        values = {match.value for match in signals["certainty_marker"]}
        self.assertIn("definitely", values)
        self.assertIn("certainly", values)

    def test_risk_negation_is_detected(self) -> None:
        signals = detect_signals("This is a risk free and guaranteed return.")

        values = {match.value for match in signals["risk_negation"]}
        self.assertIn("risk free", values)
        self.assertIn("guaranteed return", values)

    def test_vague_source_is_detected(self) -> None:
        signals = detect_signals("Insiders already know how this ends.")

        values = {match.value.lower() for match in signals["vague_source"]}
        self.assertTrue(any("insiders" in value for value in values), values)
        # The span covers the attribution phrase, not just the source noun.
        self.assertTrue(any("know" in value for value in values), values)

    def test_emotional_pressure_is_detected(self) -> None:
        signals = detect_signals("Everyone is buying before it is too late.")

        values = {match.value for match in signals["emotional_pressure"]}
        self.assertTrue(values)

    def test_signals_carry_spans_and_render(self) -> None:
        signals = detect_signals("You should buy this stock today.")

        matches = signals["directive"]
        self.assertTrue(matches)
        for match in matches:
            self.assertLess(match.start, match.end)
            self.assertIn(match.value.lower(), "you should buy this stock today.")
            self.assertTrue(match.render())
            self.assertFalse(match.negated)


class NegationGuardTests(unittest.TestCase):
    def test_a_negated_signal_is_marked_negated(self) -> None:
        signals = detect_signals("This is not a guaranteed return.")

        certainty = signals["certainty_marker"]
        self.assertTrue(certainty)
        self.assertTrue(all(match.negated for match in certainty))

    def test_negation_window_is_bounded(self) -> None:
        distant = "not " + ("filler " * 20) + "guaranteed return"

        signals = detect_signals(distant)

        self.assertTrue(
            all(not match.negated for match in signals["certainty_marker"]),
            f"negation must not reach beyond {NEGATION_WINDOW} characters",
        )

    def test_patterns_that_are_themselves_negative_still_fire(self) -> None:
        """The cue inside "no risk" is the claim, not a modifier of it."""

        for text in ("This is a no risk plan.", "It cannot fail.", "It never falls."):
            with self.subTest(text=text):
                signals = detect_signals(text)
                active = [m for m in signals["risk_negation"] if not m.negated]
                self.assertTrue(active, text)

    def test_negation_reaches_risk_negation_patterns(self) -> None:
        signals = detect_signals("This is not a guaranteed return.")

        active = [m for m in signals["risk_negation"] if not m.negated]
        self.assertEqual(active, [])


class ChineseSignalTests(unittest.TestCase):
    """Regression: ``\\b`` fails between CJK characters, so CJK terms are unanchored."""

    def test_chinese_pressure_is_detected_inside_a_longer_phrase(self) -> None:
        signals = detect_signals("恐慌情绪蔓延，赶紧上车。")

        values = {match.value for match in signals["emotional_pressure"]}
        self.assertIn("恐慌", values)
        self.assertIn("赶紧", values)

    def test_chinese_certainty_and_outcome_are_detected(self) -> None:
        signals = detect_signals("必然上涨，目标价翻倍。")

        self.assertTrue(
            {match.value for match in signals["certainty_marker"]} & {"必然"}
        )
        self.assertTrue(
            {match.value for match in signals["future_marker"]} & {"上涨", "翻倍"}
        )

    def test_chinese_directive_and_object_are_detected(self) -> None:
        signals = detect_signals("立即买入这只股票。")

        self.assertTrue(any("买入" in match.value for match in signals["directive"]))
        self.assertTrue(any("股票" in match.value for match in signals["financial_object"]))

    def test_chinese_vague_source_is_detected(self) -> None:
        signals = detect_signals("据说不具名消息人士透露，公司将重组。")

        self.assertTrue(signals["vague_source"])


class CompositionalDetectionTests(unittest.TestCase):
    """Intent requires a conjunction of signals, not one phrase."""

    def setUp(self) -> None:
        self.evaluator = SemanticRiskEvaluator()

    def test_one_signal_alone_is_not_enough(self) -> None:
        for text in (
            "The stock is listed on the exchange.",
            "The company announced its quarterly earnings.",
            "Revenue grew at a moderate rate.",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.evaluator.evaluate_text(text), (), text)

    def test_swapping_the_object_keeps_the_intent(self) -> None:
        first = self.evaluator.evaluate_text("You should buy this stock today.")
        second = self.evaluator.evaluate_text("Move your money into this company.")

        self.assertEqual(
            {item.category for item in first}, {item.category for item in second}
        )

    def test_negated_directive_is_not_advice(self) -> None:
        self.assertEqual(
            self.evaluator.evaluate_text(
                "The company does not recommend buying its own shares."
            ),
            (),
        )


if __name__ == "__main__":
    unittest.main()
