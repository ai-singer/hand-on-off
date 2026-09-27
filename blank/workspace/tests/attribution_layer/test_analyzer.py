"""Requirement 5: the analyzer pipeline, and the bridge a future evaluator uses."""

from __future__ import annotations

import json
import unittest

from risk_evaluation.attribution.analyzer import (
    DEFAULT_ANALYZER,
    AttributionAnalyzer,
    SpeakerDetector,
    analyze,
    authorial_text,
    claim_views,
    to_statement_source,
)
from risk_evaluation.attribution.claim_parser import ClaimParser
from risk_evaluation.attribution.model import AttributionError
from risk_evaluation.attribution.stance_detector import ENDORSED, QUOTED, REJECTED


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.analyzer = AttributionAnalyzer()

    def test_the_result_has_claims_and_a_summary(self) -> None:
        payload = self.analyzer.analyze("Analysts expect growth.").as_dict()

        self.assertEqual(set(payload), {"claims", "summary"})

    def test_every_claim_carries_evidence(self) -> None:
        """Acceptance criterion 4, over a realistic paragraph."""

        result = self.analyzer.analyze(
            "Analysts expect growth. However, we disagree. Costs were flat."
        )

        self.assertTrue(result.claims)
        for claim in result.claims:
            self.assertTrue(claim.evidence, claim.claim_id)

    def test_claims_are_numbered_in_reading_order(self) -> None:
        result = self.analyzer.analyze("One thing. Two things. Three things.")

        self.assertEqual(
            [claim.claim_id for claim in result.claims],
            ["claim-001", "claim-002", "claim-003"],
        )

    def test_claim_index_matches_position(self) -> None:
        result = self.analyzer.analyze("One thing. Two things.")

        self.assertEqual([claim.index for claim in result.claims], [0, 1])

    def test_empty_input_yields_no_claims(self) -> None:
        result = self.analyzer.analyze("   ")

        self.assertEqual(result.claims, ())
        self.assertEqual(result.summary["claim_count"], 0)

    def test_non_string_input_is_rejected(self) -> None:
        with self.assertRaises(AttributionError):
            self.analyzer.analyze(42)  # type: ignore[arg-type]

    def test_analysis_is_deterministic(self) -> None:
        text = "Analysts expect growth. However, we disagree."

        self.assertEqual(
            self.analyzer.analyze(text).as_dict(),
            self.analyzer.analyze(text).as_dict(),
        )

    def test_the_module_level_analyzer_matches_the_default_instance(self) -> None:
        text = "Analysts expect growth."

        self.assertEqual(
            analyze(text).as_dict(), DEFAULT_ANALYZER.analyze(text).as_dict()
        )

    def test_analyze_claims_returns_just_the_claims(self) -> None:
        claims = self.analyzer.analyze_claims("One thing. Two things.")

        self.assertEqual(len(claims), 2)
        self.assertTrue(all(isinstance(claim.claim_id, str) for claim in claims))

    def test_the_summary_counts_every_claim(self) -> None:
        result = self.analyzer.analyze(
            "Analysts expect growth. However, we disagree. Costs were flat."
        )

        self.assertEqual(result.summary["claim_count"], len(result.claims))

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(
            self.analyzer.analyze("Analysts expect growth.").as_dict(), sort_keys=True
        )

    def test_render_shows_every_claim(self) -> None:
        rendered = self.analyzer.analyze("One thing. Two things.").render()

        self.assertIn("claim-001", rendered)
        self.assertIn("claim-002", rendered)

    def test_components_can_be_injected(self) -> None:
        analyzer = AttributionAnalyzer(
            parser=ClaimParser(min_length=100), speaker_detector=SpeakerDetector()
        )

        self.assertEqual(analyzer.analyze("Short. Also short.").claims, ())


class SpeakerStanceCoherenceTests(unittest.TestCase):
    """Combinations the layer must never produce, because they are contradictory."""

    def setUp(self) -> None:
        self.analyzer = AttributionAnalyzer()

    def test_an_author_voiced_claim_is_never_merely_uncertain(self) -> None:
        """Putting a claim in your own voice is taking it up."""

        for text in (
            "We believe the fund is safe.",
            "Our analysis shows revenue is durable.",
            "I think the stock is cheap.",
        ):
            claim = self.analyzer.analyze(text).claims[0]

            self.assertEqual(claim.speaker, "author", text)
            self.assertEqual(claim.stance, ENDORSED, text)

    def test_a_reporting_verb_in_the_authors_voice_is_not_a_quotation(self) -> None:
        claim = self.analyzer.analyze("We expect the sector to recover.").claims[0]

        self.assertEqual(claim.stance, ENDORSED)
        self.assertIn("stance.author-voice-repair", claim.rules())

    def test_a_rejection_with_no_speaker_marker_belongs_to_the_author(self) -> None:
        """`unknown` plus `rejected` would hide the article's own counter-argument."""

        claim = self.analyzer.analyze("But evidence shows otherwise.").claims[0]

        self.assertEqual(claim.speaker, "author")
        self.assertTrue(claim.is_authorial)
        self.assertIn("speaker.rejection-implies-author", claim.rules())

    def test_a_third_party_rejection_stays_third_party(self) -> None:
        """The rule is narrow: a marked speaker keeps the rejection."""

        claim = self.analyzer.analyze("Analysts dispute the rebound.").claims[0]

        self.assertEqual(claim.speaker, "third_party")
        self.assertFalse(claim.is_authorial)

    def test_an_unmarked_claim_is_authorial_by_default(self) -> None:
        claim = self.analyzer.analyze("Costs were flat over the period.").claims[0]

        self.assertTrue(claim.is_default_voice)
        self.assertTrue(claim.is_authorial)


class BridgeTests(unittest.TestCase):
    """Requirement 8: how a future risk evaluator would consume this."""

    def setUp(self) -> None:
        self.analyzer = AttributionAnalyzer()

    def test_an_authorial_claim_maps_to_author(self) -> None:
        claim = self.analyzer.analyze("We believe the fund is safe.").claims[0]

        self.assertEqual(to_statement_source(claim), "author")

    def test_a_quoted_claim_maps_to_quoted(self) -> None:
        claim = self.analyzer.analyze("Analysts say the fund is safe.").claims[0]

        self.assertEqual(to_statement_source(claim), "quoted")

    def test_a_rejected_claim_maps_to_quoted(self) -> None:
        result = self.analyzer.analyze(
            "Analysts expect growth. However, we disagree."
        )

        self.assertEqual(to_statement_source(result.claims[0]), "quoted")

    def test_every_mapping_is_a_declared_statement_source(self) -> None:
        from risk_evaluation.taxonomy_v2 import STATEMENT_SOURCES

        result = self.analyzer.analyze(
            "Analysts expect growth. However, we disagree. Costs were flat."
        )
        for view in claim_views(result):
            self.assertIn(view.statement_source, STATEMENT_SOURCES)

    def test_claim_views_carry_what_an_evaluator_needs(self) -> None:
        result = self.analyzer.analyze("Analysts expect growth.")
        view = claim_views(result)[0]

        for key in (
            "claim_id",
            "text",
            "speaker",
            "stance",
            "statement_source",
            "is_authorial",
            "confidence",
            "evidence",
        ):
            self.assertIn(key, view.as_dict())

    def test_authorial_text_isolates_the_articles_own_claims(self) -> None:
        """The structural fix Phase 8.1 pointed at."""

        result = self.analyzer.analyze(
            "Economists forecast slower growth in Europe. This fund cannot lose money."
        )

        self.assertEqual(authorial_text(result), "This fund cannot lose money.")
        self.assertNotIn("Economists", authorial_text(result))

    def test_authorial_text_is_empty_when_everything_is_attributed(self) -> None:
        result = self.analyzer.analyze("Analysts say this fund cannot lose money.")

        self.assertEqual(authorial_text(result), "")

    def test_the_bridge_does_not_modify_the_claim(self) -> None:
        result = self.analyzer.analyze("Analysts expect growth.")
        before = result.claims[0].as_dict()
        claim_views(result)

        self.assertEqual(result.claims[0].as_dict(), before)


class RejectionClassificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.analyzer = AttributionAnalyzer()

    def test_a_rejected_claim_is_not_the_articles_claim(self) -> None:
        result = self.analyzer.analyze(
            "Analysts believe the stock will rise. However, we disagree."
        )

        self.assertFalse(result.claims[0].is_authorial)
        self.assertTrue(result.claims[0].is_rejected)

    def test_the_rejection_is_reported_in_the_summary(self) -> None:
        """Both segments are `rejected`, and they differ in `speaker`.

        `Analysts believe X. However, we disagree.` contains a rejected claim
        (`X`) and the author's act of rejecting it. Both carry the stance
        `rejected`; the first is the analysts' and the second is the author's.
        """

        result = self.analyzer.analyze(
            "Analysts believe the stock will rise. However, we disagree."
        )

        self.assertTrue(result.summary["has_rejection"])
        self.assertEqual(
            result.summary["rejected_claims"], ["claim-001", "claim-002"]
        )
        self.assertEqual(result.claims[0].speaker, "third_party")
        self.assertEqual(result.claims[1].speaker, "author")

    def test_a_text_with_no_attribution_has_no_attributed_claims(self) -> None:
        result = self.analyzer.analyze("Costs were flat. Revenue rose.")

        self.assertFalse(result.summary["has_attribution"])

    def test_a_mixed_text_is_flagged(self) -> None:
        result = self.analyzer.analyze(
            "Analysts say revenue will double. We disagree with that view."
        )

        self.assertTrue(result.summary["mixed"])


if __name__ == "__main__":
    unittest.main()
