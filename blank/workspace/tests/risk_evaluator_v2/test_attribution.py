from __future__ import annotations

import unittest

from risk_evaluation.semantic_evaluator_v2 import (
    SemanticRiskEvaluatorV2,
    analyze_attribution,
)

#: (text, expected statement_source, why) -- all expectations verified against
#: the annotation guide v2 (section 4), not read back off the implementation.
ATTRIBUTION_CASES: tuple[tuple[str, str, str], ...] = (
    (
        "The stock will rise tomorrow.",
        "author",
        "no attribution marker: the author's own claim",
    ),
    (
        "Revenue will grow next year.",
        "author",
        "author-voice projection",
    ),
    (
        "The margin holds at 30 percent.",
        "author",
        "a statement of the author's own reading",
    ),
    (
        "Management expects the stock to reach 500.",
        "third_party",
        "reported expectation of an identifiable body",
    ),
    (
        "The board expects revenue to grow next year.",
        "third_party",
        "reported expectation of a named body",
    ),
    (
        "Economists forecast a slowdown.",
        "third_party",
        "identifiable professional group as the source",
    ),
    (
        "Regulators believe the rules will change.",
        "third_party",
        "identifiable authority as the source",
    ),
    (
        "The broker note estimates a 20 percent upside.",
        "third_party",
        "an identifiable published note",
    ),
    (
        "Sources say revenue will double next quarter.",
        "unknown",
        "an unnamed source cannot be checked",
    ),
    (
        "Insiders already know the outcome.",
        "unknown",
        "anonymous insiders",
    ),
    (
        "Rumour has it the company will be acquired.",
        "unknown",
        "a rumour is unattributable",
    ),
    (
        "People close to the company say revenue will double.",
        "unknown",
        "anonymous people close to the matter",
    ),
    (
        "An anonymous official confirmed the review.",
        "unknown",
        "explicitly anonymous source",
    ),
    (
        "Analysts say the price target will be reached.",
        "unknown",
        "an unnamed plural group is unattributable, not a named party",
    ),
    (
        "I heard the dividend will be cut.",
        "unknown",
        "first-person hearsay names no source",
    ),
    (
        'The CEO said "the stock will rise".',
        "quoted",
        "explicit quotation marks",
    ),
    (
        '"Revenue will double," the report states.',
        "quoted",
        "quoted material",
    ),
    (
        "The analyst wrote that margins will improve.",
        "quoted",
        "a writing frame presents someone else's words",
    ),
    (
        "The company refuted the claim that revenue fell.",
        "quoted",
        "rejection framing: discussing a claim is not making it",
    ),
)


class AttributionDetectionTests(unittest.TestCase):
    """`statement_source` is the dimension v1 had no notion of."""

    def test_every_declared_case_is_classified_as_expected(self) -> None:
        wrong: list[str] = []
        for text, expected, why in ATTRIBUTION_CASES:
            actual = analyze_attribution(text).statement_source
            if actual != expected:
                wrong.append(f"{text!r}: expected {expected}, got {actual} ({why})")

        self.assertEqual(wrong, [])

    def test_all_four_sources_are_exercised(self) -> None:
        covered = {
            analyze_attribution(text).statement_source
            for text, _, _ in ATTRIBUTION_CASES
        }

        self.assertEqual(covered, {"author", "third_party", "quoted", "unknown"})

    def test_an_attributed_claim_is_never_reported_as_author_voice(self) -> None:
        for text, expected, _ in ATTRIBUTION_CASES:
            if expected != "author":
                self.assertNotEqual(
                    analyze_attribution(text).statement_source, "author", text
                )

    def test_analysis_reports_the_markers_it_used(self) -> None:
        analysis = analyze_attribution("Sources say revenue will double.")

        self.assertTrue(analysis.markers)
        self.assertTrue(all(isinstance(marker, str) for marker in analysis.markers))

    def test_author_text_has_no_attribution_marker_to_report(self) -> None:
        self.assertEqual(analyze_attribution("The stock will rise.").markers, ())

    def test_markers_are_stable_across_calls(self) -> None:
        text = "Sources say revenue will double."

        self.assertEqual(analyze_attribution(text), analyze_attribution(text))

    def test_render_states_the_source(self) -> None:
        rendered = analyze_attribution("Sources say revenue will double.").render()

        self.assertIn("statement_source=unknown", rendered)

    def test_non_string_input_is_rejected(self) -> None:
        with self.assertRaises(Exception):
            analyze_attribution(None)


class AttributionPrecedenceTests(unittest.TestCase):
    """`quoted` beats `unknown` beats `third_party` beats `author`."""

    def test_quotation_outranks_a_named_source(self) -> None:
        analysis = analyze_attribution('Economists say "the slowdown will deepen".')

        self.assertEqual(analysis.statement_source, "quoted")

    def test_unknown_outranks_a_named_source(self) -> None:
        analysis = analyze_attribution("Sources say management expects a rebound.")

        self.assertEqual(analysis.statement_source, "unknown")

    def test_lowercase_and_uppercase_are_treated_alike(self) -> None:
        self.assertEqual(
            analyze_attribution("SOURCES SAY REVENUE WILL DOUBLE.").statement_source,
            analyze_attribution("Sources say revenue will double.").statement_source,
        )


class AttributionChangesTheVerdictTests(unittest.TestCase):
    """The reason the dimension exists: the same sentence, different owner."""

    def setUp(self) -> None:
        self.evaluator = SemanticRiskEvaluatorV2()

    def test_author_voice_prediction_is_flagged(self) -> None:
        analysis = self.evaluator.analyze(
            "The share price will definitely double next year."
        )

        self.assertIn("market_prediction", analysis.categories)

    def test_the_same_prediction_attributed_is_not_market_prediction(self) -> None:
        analysis = self.evaluator.analyze(
            "Analysts are certain the price target will be reached."
        )

        self.assertNotIn("market_prediction", analysis.categories)

    def test_an_attributed_claim_is_recorded_as_suppressed(self) -> None:
        """The category must be *matched* first, or nothing is suppressed."""

        analysis = self.evaluator.analyze(
            "Analysts are certain the price target will be reached."
        )

        self.assertIn("market_prediction", analysis.suppressed)

    def test_a_quoted_prediction_is_not_market_prediction(self) -> None:
        analysis = self.evaluator.analyze(
            '"The share price will definitely double next year," he said.'
        )

        self.assertNotIn("market_prediction", analysis.categories)

    def test_attribution_does_not_suppress_unverified_information(self) -> None:
        """Reporting an unverifiable source is a risk whatever the voice."""

        analysis = self.evaluator.analyze("Sources say revenue will double.")

        self.assertIn("unverified_information", analysis.categories)

    def test_a_quoted_author_voice_prediction_is_suppressed(self) -> None:
        analysis = self.evaluator.analyze(
            '"The share price will definitely double next year," he said.'
        )

        self.assertIn("market_prediction", analysis.suppressed)

    def test_every_non_author_voice_loses_the_prediction_category(self) -> None:
        cases = {
            "third_party": "Management expects the share price will definitely double.",
            "quoted": '"The share price will definitely double," he said.',
            "unknown": "Sources say the share price will definitely double.",
        }
        for source, text in cases.items():
            analysis = self.evaluator.analyze(text)

            self.assertNotIn("market_prediction", analysis.categories, source)
            self.assertIn("market_prediction", analysis.suppressed, source)


class KnownAttributionGapsTests(unittest.TestCase):
    """Gaps recorded so they cannot be silently forgotten.

    Every assertion here pins *current* behaviour that the annotation guide does
    not want. Nine of the ten attribution errors on semantic/v3 share one cause:
    the source lexicon in the v1 signal layer is thin. The detection logic
    (precedence, orthogonality, suppression) is not what is failing. If a later
    phase widens the lexicon, these tests failing is the intended signal: move
    the case into ATTRIBUTION_CASES and delete it from here.
    """

    def test_hearsay_verbs_without_a_named_source_are_read_as_author_voice(
        self,
    ) -> None:
        for text in (
            "I was told the factory is closing.",
            "A person familiar with the matter said the deal is off.",
        ):
            self.assertEqual(
                analyze_attribution(text).statement_source, "author", text
            )

    def test_anonymous_source_phrases_are_read_as_author_voice(self) -> None:
        for text in (
            "A source close to the deal mentioned a delay.",
            "Everybody says the founder is leaving.",
            "Leaked internal documents suggest a restatement.",
            "Traders say the stock is cheap.",
        ):
            self.assertEqual(
                analyze_attribution(text).statement_source, "author", text
            )

    def test_chinese_hearsay_is_read_as_author_voice(self) -> None:
        """网上传 / 据说 have no marker in the source lexicon."""

        self.assertEqual(
            analyze_attribution("\u7f51\u4e0a\u4f20\u8be5\u516c\u53f8\u5373\u5c06\u9000\u5e02\u3002").statement_source,
            "author",
        )

    def test_corporate_reporting_verbs_are_read_as_author_voice(self) -> None:
        for text in (
            "The company said margins improved last quarter.",
            "The report estimates revenue will double.",
            "The company disclosed a change in accounting policy.",
            "The exchange published the revised listing rules.",
        ):
            self.assertEqual(
                analyze_attribution(text).statement_source, "author", text
            )

    def test_unnamed_plus_a_profession_reads_as_third_party(self) -> None:
        """`unnamed` is not in the vague-source vocabulary, but `banker` is a party."""

        self.assertEqual(
            analyze_attribution("An unnamed banker says the deal is off.").statement_source,
            "third_party",
        )

    def test_rejection_framing_downgrades_a_named_source_to_quoted(self) -> None:
        """The one v3 attribution error that is precedence, not vocabulary."""

        analysis = analyze_attribution(
            "The broker note says the stock is a buy, which the article does not endorse."
        )

        self.assertEqual(analysis.statement_source, "quoted")


class KnownLayerDisagreementTests(unittest.TestCase):
    """The v2 layers disagree about implied certainty.

    `taxonomy_v2` defines a direct prediction as an author-voice certainty, and
    `analyze_certainty` reports `certain` whenever no modal or conditional marker
    is present -- so plain "will X" is labelled a certainty. But the
    `market_prediction` intent pattern still requires an *explicit* certainty
    marker, inherited from v1. The same sentence is therefore classified as an
    `explicit_prediction` by the taxonomy layer and as no risk at all by the
    category layer.

    This is a real specification gap in Phase 7.5, not merely a recall miss: the
    declared definition and the implemented one are not the same. It is recorded
    rather than repaired, because changing the pattern after measuring the
    benchmark would be tuning against known cases.
    """

    def setUp(self) -> None:
        self.evaluator = SemanticRiskEvaluatorV2()

    def test_taxonomy_calls_it_a_direct_prediction(self) -> None:
        analysis = self.evaluator.analyze("The share price will double next year.")

        self.assertEqual(analysis.statement_source, "author")
        self.assertEqual(analysis.certainty_level, "certain")
        self.assertEqual(analysis.market_claim_case, "explicit_prediction")

    def test_the_category_layer_still_does_not_flag_it(self) -> None:
        analysis = self.evaluator.analyze("The share price will double next year.")

        self.assertEqual(analysis.categories, ())

    def test_an_explicit_certainty_adverb_is_what_makes_it_fire(self) -> None:
        without = self.evaluator.analyze("The share price will double next year.")
        with_adverb = self.evaluator.analyze(
            "The share price will definitely double next year."
        )

        self.assertEqual(without.categories, ())
        self.assertEqual(with_adverb.categories, ("market_prediction",))

    def test_the_definition_is_at_least_as_wide_as_the_detector(self) -> None:
        """Every flagged prediction must be a declared direct prediction.

        The reverse does not hold, which is the gap: the detector is narrower
        than the definition it claims to implement.
        """

        from risk_evaluation.taxonomy_v2 import is_direct_prediction

        flagged = 0
        for text in (
            "The share price will definitely double next year.",
            "Revenue will surely grow every quarter.",
            "The stock will certainly reach 500.",
            "The share price will double next year.",
            "The stock may rise.",
            "If rates fall, the stock will rise.",
        ):
            analysis = self.evaluator.analyze(text)
            if "market_prediction" in analysis.categories:
                flagged += 1
                self.assertTrue(
                    is_direct_prediction(
                        statement_source=analysis.statement_source,
                        certainty_level=analysis.certainty_level,
                    ),
                    text,
                )

        self.assertGreater(flagged, 0)


if __name__ == "__main__":
    unittest.main()
