"""Requirement B and C: stance detection, and rejection across claim boundaries."""

from __future__ import annotations

import json
import unittest

from risk_evaluation.attribution.analyzer import AttributionAnalyzer
from risk_evaluation.attribution.claim_parser import ClaimParser
from risk_evaluation.attribution.model import STANCES
from risk_evaluation.attribution.stance_detector import (
    ENDORSEMENT_MARKERS,
    QUOTATION_MARKERS,
    REJECTION_MARKERS,
    ENDORSED,
    QUOTED,
    REJECTED,
    STANCE_PRECEDENCE,
    UNCERTAIN,
    StanceDetector,
)


#: (text, expected stance, why)
STANCE_CASES: tuple[tuple[str, str, str], ...] = (
    ("Analysts said the stock will rise.", QUOTED, "required case: X said"),
    ("According to analysts, the outlook improved.", QUOTED, "required case: according to"),
    ("Analysts say the dividend will be cut.", QUOTED, "reporting frame"),
    ("Experts say the rally continues, and we agree.", ENDORSED, "required case: we agree"),
    ("Analysts expect growth, and this is correct.", ENDORSED, "required case: this is correct"),
    ("Analysts expect higher margins, and indeed this is correct.", ENDORSED, "'indeed'"),
    ("However, we disagree.", REJECTED, "required case: however plus disagreement"),
    ("But evidence shows otherwise.", REJECTED, "required case: evidence shows"),
    ("This is misleading.", REJECTED, "'is misleading'"),
    ("The quarter closed in March.", UNCERTAIN, "required case: cannot tell"),
    ("Costs were flat over the period.", UNCERTAIN, "no stance marker"),
)


class StanceDetectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.detector = StanceDetector()
        self.parser = ClaimParser()

    def _detect(self, text: str):
        return self.detector.detect(self.parser.parse(text)[0])

    def test_every_declared_case_is_classified_as_expected(self) -> None:
        wrong: list[str] = []
        for text, expected, why in STANCE_CASES:
            actual = self._detect(text).stance
            if actual != expected:
                wrong.append(f"{text!r}: expected {expected}, got {actual} ({why})")

        self.assertEqual(wrong, [])

    def test_all_four_stances_are_exercised(self) -> None:
        covered = {self._detect(text).stance for text, _, _ in STANCE_CASES}

        self.assertEqual(covered, set(STANCES))

    def test_every_ascii_rejection_marker_is_detectable(self) -> None:
        """Each marker is probed in a segment that actually contains it.

        The probe sentence is split by the parser - `However` is a boundary - so
        the check runs over every segment rather than assuming the first one.
        """

        missing = [
            marker
            for marker in REJECTION_MARKERS
            if marker.isascii()
            and not any(
                self.detector.detect(segment).stance == REJECTED
                for segment in self.parser.parse(
                    f"Analysts expect growth. However, {marker}."
                )
            )
        ]

        self.assertEqual(missing, [])

    def test_every_ascii_endorsement_marker_is_detectable(self) -> None:
        missing = [
            marker
            for marker in ENDORSEMENT_MARKERS
            if marker.isascii()
            and self._detect(f"Analysts expect growth, and {marker}.").stance
            != ENDORSED
        ]

        self.assertEqual(missing, [])

    def test_every_ascii_quotation_marker_is_detectable(self) -> None:
        missing = [
            marker
            for marker in QUOTATION_MARKERS
            if marker.isascii()
            and self._detect(
                f"Analysts {marker.strip()} the fund is safe."
            ).stance
            != QUOTED
        ]

        self.assertEqual(missing, [])

    def test_precedence_rejection_beats_endorsement(self) -> None:
        verdict = self._detect(
            "Analysts said the fund is safe, and we agree that the claim is misleading."
        )

        self.assertEqual(verdict.stance, REJECTED)

    def test_precedence_endorsement_beats_quotation(self) -> None:
        verdict = self._detect("Analysts said growth continues, and we agree.")

        self.assertEqual(verdict.stance, ENDORSED)

    def test_the_precedence_order_is_declared(self) -> None:
        self.assertEqual(
            STANCE_PRECEDENCE, (REJECTED, ENDORSED, QUOTED, UNCERTAIN)
        )

    def test_an_uncertain_stance_records_the_absence(self) -> None:
        verdict = self._detect("Costs were flat over the period.")

        self.assertEqual(verdict.markers, ("rule:stance.no-marker",))

    def test_markers_are_reported_as_evidence(self) -> None:
        verdict = self._detect("Analysts said the fund is safe.")

        self.assertIn("said", verdict.markers)

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(self._detect("Analysts said the fund is safe.").as_dict())


class BackwardRejectionTests(unittest.TestCase):
    """Requirement C: a rejection applies to the claim before it."""

    def setUp(self) -> None:
        self.analyzer = AttributionAnalyzer()

    def test_a_contrastive_lead_rejects_the_previous_claim(self) -> None:
        result = self.analyzer.analyze(
            "Analysts believe the stock will rise. However, we disagree."
        )

        self.assertEqual(len(result.claims), 2)
        self.assertEqual(result.claims[0].stance, REJECTED)
        self.assertEqual(result.claims[0].speaker, "third_party")

    def test_the_rejecting_segment_is_the_authors(self) -> None:
        result = self.analyzer.analyze(
            "Analysts believe the stock will rise. However, we disagree."
        )

        self.assertEqual(result.claims[1].speaker, "author")

    def test_an_internal_contrast_also_rejects_backwards(self) -> None:
        result = self.analyzer.analyze(
            "Analysts expect growth, however we disagree."
        )

        self.assertEqual(result.claims[0].stance, REJECTED)

    def test_a_rejection_without_a_contrast_marker_still_applies(self) -> None:
        result = self.analyzer.analyze("Analysts expect growth. We disagree.")

        self.assertEqual(result.claims[0].stance, REJECTED)

    def test_backward_rejection_replaces_the_absence_evidence(self) -> None:
        """A rejected claim must not still report that no stance was found."""

        result = self.analyzer.analyze(
            "Analysts expect growth. However, we disagree."
        )
        claim = result.claims[0]

        self.assertNotIn("rule:stance.no-marker", claim.evidence)
        self.assertIn("stance.rejection-backward", claim.rules())

    def test_a_rejection_does_not_reach_further_back_than_one_claim(self) -> None:
        result = self.analyzer.analyze(
            "Costs were flat. Analysts expect growth. However, we disagree."
        )

        self.assertEqual(result.claims[0].stance, UNCERTAIN)
        self.assertEqual(result.claims[1].stance, REJECTED)

    def test_a_non_contrastive_sentence_leaves_the_previous_claim_alone(self) -> None:
        result = self.analyzer.analyze(
            "Analysts expect growth. The quarter closed in March."
        )

        self.assertEqual(result.claims[0].stance, QUOTED)


if __name__ == "__main__":
    unittest.main()
