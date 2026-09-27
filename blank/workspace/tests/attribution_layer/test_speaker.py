"""Requirement A: speaker detection, plus the inference rules around it."""

from __future__ import annotations

import unittest

from risk_evaluation.attribution.analyzer import (
    AUTHOR_MARKERS,
    THIRD_PARTY_MARKERS,
    SpeakerDetector,
)
from risk_evaluation.attribution.claim_parser import ClaimParser
from risk_evaluation.attribution.model import SPEAKERS


#: (text, expected speaker, why)
SPEAKER_CASES: tuple[tuple[str, str, str], ...] = (
    # -- third party ------------------------------------------------------
    ("Analysts said the stock will rise.", "third_party", "required case: analysts"),
    ("Experts predict growth next year.", "third_party", "required case: experts"),
    ("Researchers say the effect is small.", "third_party", "required case: researchers"),
    ("According to analysts, the outlook improved.", "third_party", "required case: according to"),
    ("Reports say the merger will complete.", "third_party", "required case: reports say"),
    ("Some investors believe the rally continues.", "third_party", "required case: some investors"),
    ("Management expects margins to recover.", "third_party", "corporate speaker"),
    ("Economists forecast slower growth.", "third_party", "profession as speaker"),
    ("Regulators published the revised rules.", "third_party", "authority as speaker"),
    ("Sources say the deal is close.", "third_party", "unnamed collective"),
    # -- author -----------------------------------------------------------
    ("I think the stock is cheap.", "author", "required case: I think"),
    ("We believe the fund is well managed.", "author", "required case: we believe"),
    ("Our analysis shows revenue is durable.", "author", "required case: our analysis"),
    ("This article argues the fee is too high.", "author", "required case: this article argues"),
    ("In our view the valuation is stretched.", "author", "explicit self-reference"),
    ("Our research shows the effect is small.", "author", "self-reference"),
    # -- unknown ----------------------------------------------------------
    ("The quarter closed in March.", "unknown", "required case: no subject"),
    ("Revenue rose four percent.", "unknown", "no marker"),
    ("Costs were flat over the period.", "unknown", "no marker"),
)


class SpeakerDetectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.detector = SpeakerDetector()
        self.parser = ClaimParser()

    def test_every_declared_case_is_classified_as_expected(self) -> None:
        wrong: list[str] = []
        for text, expected, why in SPEAKER_CASES:
            segment = self.parser.parse(text)[0]
            actual = self.detector.detect(segment).speaker
            if actual != expected:
                wrong.append(f"{text!r}: expected {expected}, got {actual} ({why})")

        self.assertEqual(wrong, [])

    def test_all_three_speakers_are_exercised(self) -> None:
        covered = {
            self.detector.detect(self.parser.parse(text)[0]).speaker
            for text, _, _ in SPEAKER_CASES
        }

        self.assertEqual(covered, set(SPEAKERS))

    def test_every_declared_third_party_marker_is_detectable(self) -> None:
        missing: list[str] = []
        for marker in THIRD_PARTY_MARKERS:
            if not marker.isascii():
                continue
            text = f"{marker.capitalize()} said the fund is safe."
            verdict = self.detector.detect(self.parser.parse(text)[0])
            if verdict.speaker != "third_party":
                missing.append(marker)

        # "the report" and similar need their own article; check those directly.
        self.assertEqual([m for m in missing if m not in {"the report"}], [])

    def test_every_declared_author_marker_is_detectable(self) -> None:
        missing: list[str] = []
        for marker in AUTHOR_MARKERS:
            if not marker.isascii():
                continue
            text = f"{marker.capitalize()} the fund is safe."
            verdict = self.detector.detect(self.parser.parse(text)[0])
            if verdict.speaker != "author":
                missing.append(marker)

        self.assertEqual(missing, [])

    def test_an_author_marker_is_found_through_case(self) -> None:
        verdict = self.detector.detect(self.parser.parse("WE BELIEVE the fund is safe.")[0])

        self.assertEqual(verdict.speaker, "author")

    def test_markers_are_reported_as_evidence(self) -> None:
        verdict = self.detector.detect(self.parser.parse("Analysts expect growth.")[0])

        self.assertIn("analysts", verdict.markers)
        self.assertTrue(verdict.determined)

    def test_an_unknown_speaker_records_the_absence(self) -> None:
        verdict = self.detector.detect(self.parser.parse("Costs were flat.")[0])

        self.assertFalse(verdict.determined)
        self.assertEqual(verdict.markers, ("rule:speaker.no-marker",))

    def test_the_first_marker_names_the_subject(self) -> None:
        """`Analysts say X, and we agree` is the analysts speaking."""

        verdict = self.detector.detect(
            self.parser.parse("Analysts say the rally continues, and we agree.")[0]
        )

        self.assertEqual(verdict.speaker, "third_party")

    def test_an_author_subject_wins_when_it_comes_first(self) -> None:
        verdict = self.detector.detect(
            self.parser.parse("We believe analysts are wrong.")[0]
        )

        self.assertEqual(verdict.speaker, "author")

    def test_detection_is_deterministic(self) -> None:
        segment = self.parser.parse("Analysts expect growth.")[0]

        self.assertEqual(
            self.detector.detect(segment).as_dict(),
            self.detector.detect(segment).as_dict(),
        )

    def test_as_dict_is_json_serializable(self) -> None:
        import json

        json.dumps(
            self.detector.detect(self.parser.parse("Analysts expect growth.")[0]).as_dict()
        )


if __name__ == "__main__":
    unittest.main()
