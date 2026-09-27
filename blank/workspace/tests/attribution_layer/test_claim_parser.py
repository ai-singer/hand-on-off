from __future__ import annotations

import json
import unittest

from risk_evaluation.attribution.claim_parser import (
    CONTRASTIVE_MARKERS,
    CONTRASTIVE_MARKERS_CJK,
    ClaimParser,
    ClaimParserError,
    boundary_rules,
    claim_ids,
)


class ParserContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = ClaimParser()

    def test_an_empty_string_yields_no_segments(self) -> None:
        self.assertEqual(self.parser.parse(""), ())

    def test_whitespace_yields_no_segments(self) -> None:
        self.assertEqual(self.parser.parse("   \n  "), ())

    def test_non_string_input_is_rejected(self) -> None:
        with self.assertRaises(ClaimParserError):
            self.parser.parse(None)  # type: ignore[arg-type]

    def test_a_single_sentence_is_one_segment(self) -> None:
        segments = self.parser.parse("The quarter closed in March.")

        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].text, "The quarter closed in March.")

    def test_segments_are_indexed_in_reading_order(self) -> None:
        segments = self.parser.parse("One thing. Two things. Three things.")

        self.assertEqual([s.index for s in segments], [0, 1, 2])

    def test_spans_point_back_into_the_source(self) -> None:
        text = "Analysts expect growth. We disagree."
        segments = self.parser.parse(text)

        for segment in segments:
            start, end = segment.span
            self.assertTrue(text[start:end].strip().startswith(segment.text[:6]))

    def test_split_returns_just_the_texts(self) -> None:
        self.assertEqual(
            self.parser.split("One thing. Two things."),
            ("One thing.", "Two things."),
        )

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps([s.as_dict() for s in self.parser.parse("One. Two.")])

    def test_a_very_short_fragment_is_dropped(self) -> None:
        segments = self.parser.parse("A. B. Real sentence here.")

        self.assertEqual([s.text for s in segments], ["Real sentence here."])

    def test_the_minimum_length_is_configurable(self) -> None:
        parser = ClaimParser(min_length=40)

        self.assertEqual(parser.split("Short one. Also short."), ())


class SentenceBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = ClaimParser()

    def test_a_full_stop_splits(self) -> None:
        self.assertEqual(len(self.parser.parse("One thing. Two things.")), 2)

    def test_a_question_mark_splits(self) -> None:
        self.assertEqual(len(self.parser.parse("Is it cheap? Yes it is.")), 2)

    def test_an_exclamation_mark_splits(self) -> None:
        self.assertEqual(len(self.parser.parse("Buy now! Do not wait.")), 2)

    def test_full_width_terminators_split(self) -> None:
        self.assertEqual(len(self.parser.parse("\u4e00\u4ef6\u4e8b\u3002\u4e24\u4ef6\u4e8b\u3002")), 2)

    def test_an_abbreviation_does_not_split(self) -> None:
        """`Dr.` is a prefix, not a claim."""

        segments = self.parser.parse("Dr. Smith said the fund is safe. We disagree.")

        self.assertEqual([s.text for s in segments], [
            "Dr. Smith said the fund is safe.",
            "We disagree.",
        ])

    def test_a_trailing_abbreviation_at_the_end_does_split(self) -> None:
        segments = self.parser.parse("The answer is no. Next question.")

        self.assertEqual(len(segments), 2)

    def test_a_trailing_comma_is_trimmed(self) -> None:
        segments = self.parser.parse("Analysts expect growth, however we disagree.")

        self.assertEqual(segments[0].text, "Analysts expect growth")

    def test_the_boundary_rule_is_recorded(self) -> None:
        segments = self.parser.parse("One thing. Two things.")

        self.assertEqual(
            boundary_rules(segments), ("sentence-terminator",)
        )


class ContrastiveSplitTests(unittest.TestCase):
    """A contrastive connective is a split point and stance evidence."""

    def setUp(self) -> None:
        self.parser = ClaimParser()

    def test_a_sentence_initial_contrast_is_recorded_as_a_lead(self) -> None:
        segments = self.parser.parse("Analysts expect growth. However, we disagree.")

        self.assertEqual(segments[1].lead, "however")
        self.assertTrue(segments[1].opens_with_contrast)
        self.assertFalse(segments[0].opens_with_contrast)

    def test_an_internal_contrast_splits_one_sentence_into_two(self) -> None:
        segments = self.parser.parse("Analysts expect growth, however we disagree.")

        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[1].lead, "however")

    def test_an_internal_contrast_uses_its_own_boundary_rule(self) -> None:
        segments = self.parser.parse("Analysts expect growth, however we disagree.")

        self.assertIn("contrastive-connective", boundary_rules(segments))

    def test_every_declared_marker_is_detectable(self) -> None:
        missing: list[str] = []
        for marker in CONTRASTIVE_MARKERS:
            text = f"Analysts expect growth. {marker.capitalize()}, we disagree."
            segments = self.parser.parse(text)
            if len(segments) != 2 or segments[1].lead != marker:
                missing.append(marker)

        self.assertEqual(missing, [])

    def test_cjk_contrastive_markers_are_detectable(self) -> None:
        missing: list[str] = []
        for marker in CONTRASTIVE_MARKERS_CJK:
            segments = self.parser.parse(f"{marker}\uff0c\u6211\u4eec\u4e0d\u540c\u610f\u3002")
            if not segments or segments[0].lead != marker:
                missing.append(marker)

        self.assertEqual(missing, [])

    def test_a_sentence_without_a_contrast_has_no_lead(self) -> None:
        self.assertEqual(self.parser.parse("We disagree.")[0].lead, "")


class ClaimIdTests(unittest.TestCase):
    def test_ids_are_zero_padded_and_ordered(self) -> None:
        self.assertEqual(
            claim_ids(3), ("claim-001", "claim-002", "claim-003")
        )

    def test_ids_sort_as_text(self) -> None:
        ids = claim_ids(12)

        self.assertEqual(list(ids), sorted(ids))

    def test_the_prefix_is_configurable(self) -> None:
        self.assertEqual(claim_ids(1, prefix="c")[0], "c-001")

    def test_no_claims_means_no_ids(self) -> None:
        self.assertEqual(claim_ids(0), ())


if __name__ == "__main__":
    unittest.main()
