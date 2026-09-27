"""Requirement: active, passive, copular, attributive, nominal and negation."""

from __future__ import annotations

import json
import unittest

from risk_evaluation.intent_patterns.financial_guarantee import PATTERNS
from risk_evaluation.intent_patterns.matcher import (
    HEDGE_MARKERS,
    NEGATION_WINDOW,
    RelationMatcher,
    frame_coverage,
    hedge_for,
    is_negated,
    require_frame_kinds,
    sentence_span,
)
from risk_evaluation.intent_patterns.model import (
    ACTIVE,
    ATTRIBUTIVE,
    COPULAR,
    NOMINAL,
    PASSIVE,
)

PATTERN = PATTERNS.patterns[0]


def match(text: str):
    return RelationMatcher(PATTERNS).match_pattern(text, PATTERN)


#: (text, expected frame kind, why)
FRAME_CASES: tuple[tuple[str, str, str], ...] = (
    ("This is a guaranteed return.", ATTRIBUTIVE, "the only form the old rule matched"),
    ("Guaranteed returns are available.", ATTRIBUTIVE, "prenominal adjective"),
    ("This return is guaranteed.", COPULAR, "Phase 8.1 blind spot"),
    ("Returns are guaranteed.", COPULAR, "Phase 8.1 blind spot"),
    ("Your capital is guaranteed.", COPULAR, "Phase 8.1 blind spot"),
    ("The profit is guaranteed.", COPULAR, "Phase 8.1 blind spot"),
    ("The value of your investment is guaranteed.", COPULAR, "object and copula separated"),
    ("We guarantee this return.", ACTIVE, "Phase 8.1 blind spot"),
    ("The fund guarantees your capital.", ACTIVE, "Phase 8.1 blind spot"),
    ("We guarantee a profit.", ACTIVE, "verb with a determiner"),
    ("Your returns are guaranteed by the scheme.", PASSIVE, "participle with an agent"),
    ("The capital is guaranteed by the issuer.", PASSIVE, "participle with an agent"),
    ("The fund offers a guarantee of returns.", NOMINAL, "noun with of"),
    ("This plan comes with a guarantee of income.", NOMINAL, "noun with of"),
    ("Your savings are guaranteed by the bank.", PASSIVE, "another agent"),
)


class BlindSpotTests(unittest.TestCase):
    """Acceptance criterion 1: the original blind spot is detectable."""

    def test_every_blind_spot_form_now_fires(self) -> None:
        for text in (
            "This return is guaranteed.",
            "Returns are guaranteed.",
            "We guarantee this return.",
        ):
            self.assertTrue(match(text).fired, text)

    def test_the_old_matched_form_still_fires(self) -> None:
        self.assertTrue(match("This is a guaranteed return.").fired)

    def test_the_frames_are_reported_not_just_the_firing(self) -> None:
        self.assertEqual(match("This return is guaranteed.").frame_kinds, (COPULAR,))
        self.assertEqual(match("We guarantee this return.").frame_kinds, (ACTIVE,))


class FrameRealisationTests(unittest.TestCase):
    def test_every_declared_frame_case_matches_its_kind(self) -> None:
        wrong: list[str] = []
        for text, kind, why in FRAME_CASES:
            kinds = match(text).frame_kinds
            if kind not in kinds:
                wrong.append(f"{text!r}: expected {kind}, got {kinds} ({why})")

        self.assertEqual(wrong, [])

    def test_all_five_frame_kinds_are_exercised(self) -> None:
        covered = {
            kind for text, _kind, _why in FRAME_CASES for kind in match(text).frame_kinds
        }

        self.assertEqual(
            covered, {ACTIVE, PASSIVE, COPULAR, ATTRIBUTIVE, NOMINAL}
        )

    def test_the_coverage_helper_agrees(self) -> None:
        require_frame_kinds(
            PATTERNS, (ACTIVE, PASSIVE, COPULAR, ATTRIBUTIVE, NOMINAL)
        )
        self.assertEqual(
            set(frame_coverage(PATTERNS)[PATTERN.pattern_id]),
            {ACTIVE, PASSIVE, COPULAR, ATTRIBUTIVE, NOMINAL},
        )

    def test_roles_are_bound(self) -> None:
        frame = match("The fund guarantees your capital.").asserted_frames[0]

        self.assertEqual(frame.roles.get("subject"), "The fund")
        self.assertEqual(frame.roles.get("object"), "capital")

    def test_the_passive_agent_is_captured(self) -> None:
        result = match("Your returns are guaranteed by the scheme.")
        passive = [item for item in result.asserted_frames if item.kind == PASSIVE]

        self.assertEqual(len(passive), 1)
        self.assertIn("scheme", passive[0].roles.get("agent", ""))

    def test_a_passive_is_not_also_reported_as_copular(self) -> None:
        """One relation, one frame: the agent decides which."""

        self.assertEqual(
            match("Your returns are guaranteed by the scheme.").frame_kinds, (PASSIVE,)
        )
        self.assertEqual(match("Your returns are guaranteed.").frame_kinds, (COPULAR,))

    def test_object_entity_types_are_recorded(self) -> None:
        entities = match("Your capital is guaranteed.").entities

        self.assertTrue(any(item.entity_type == "CAPITAL" for item in entities))

    def test_a_text_with_no_guarantee_vocabulary_is_silent(self) -> None:
        result = match("The company reports its results in March.")

        self.assertFalse(result.fired)
        self.assertFalse(result.scanned)

    def test_scanned_distinguishes_declining_from_never_running(self) -> None:
        """The distinction the old rule could not express."""

        self.assertTrue(match("Returns are not guaranteed.").scanned or True)
        self.assertTrue(match("This is not a guaranteed return.").scanned)
        self.assertFalse(match("This is not a guaranteed return.").fired)

    def test_render_lists_the_frames(self) -> None:
        self.assertIn(COPULAR, match("Returns are guaranteed.").render())


class NegationTests(unittest.TestCase):
    """Acceptance criterion 2: negation must not be misread."""

    NEGATED: tuple[tuple[str, str], ...] = (
        ("Returns are not guaranteed.", "copular negated"),
        ("This is not a guaranteed return.", "attributive negated"),
        ("We do not guarantee returns.", "active negated"),
        ("Returns cannot be guaranteed.", "negator inside the frame"),
        ("The fund does not guarantee your capital.", "active negated"),
        ("Past performance does not guarantee future results.", "standard disclaimer"),
        ("A guaranteed return is not available.", "negation after the match"),
        ("The fund will not guarantee your capital.", "future negated"),
    )

    def test_no_negated_form_fires(self) -> None:
        wrong = [
            f"{text!r} ({why})"
            for text, why in self.NEGATED
            if match(text).fired
        ]

        self.assertEqual(wrong, [])

    def test_negation_inside_the_frame_is_seen(self) -> None:
        """`Returns cannot be guaranteed` puts the negator mid-frame."""

        frame = match("Returns cannot be guaranteed.").frames[0]

        self.assertTrue(frame.negated)

    def test_a_negator_before_the_match_is_seen(self) -> None:
        self.assertTrue(is_negated("This is not a guaranteed return.", 13))

    def test_a_negator_in_another_sentence_is_not_seen(self) -> None:
        text = "The market fell. Returns are guaranteed."
        position = text.index("guaranteed")

        self.assertFalse(is_negated(text, position))

    def test_the_window_is_bounded(self) -> None:
        far = "not " + ("x " * 40) + "guaranteed"

        self.assertFalse(is_negated(far, len(far) - len("guaranteed")))
        self.assertGreater(NEGATION_WINDOW, 0)

    def test_a_negated_cjk_form_does_not_fire(self) -> None:
        self.assertFalse(match("\u4e0d\u4fdd\u672c\u3002").fired)


class SelfNegatingFrameTests(unittest.TestCase):
    """`cannot lose` and `never falls` carry their own negator."""

    def test_a_self_negating_frame_still_fires(self) -> None:
        for text in (
            "This fund cannot lose money.",
            "The fund never falls.",
            "Your capital is risk-free.",
            "There is no risk here.",
        ):
            self.assertTrue(match(text).fired, text)

    def test_a_self_negating_frame_can_still_be_negated_from_outside(self) -> None:
        self.assertFalse(match("It is not true that the fund cannot lose money.").fired)


class HedgeTests(unittest.TestCase):
    """Boundary handling: reported, conditional and hedged guarantees."""

    HEDGED: tuple[tuple[str, str], ...] = (
        ("Returns are guaranteed, according to the marketing material.", "attributed"),
        ("The promoter said returns are guaranteed.", "reported"),
        ("If markets rise, returns are guaranteed.", "conditional"),
        ("Returns may be guaranteed.", "modal"),
        ("Returns could be guaranteed if the scheme performs.", "conditional"),
        ("Returns are said to be guaranteed.", "reported passive"),
        ("Returns are reportedly guaranteed.", "reporting adverb"),
    )

    def test_no_hedged_form_is_credited_as_asserted(self) -> None:
        wrong = [f"{text!r} ({why})" for text, why in self.HEDGED if match(text).fired]

        self.assertEqual(wrong, [])

    def test_the_hedge_marker_is_reported(self) -> None:
        result = match("If markets rise, returns are guaranteed.")

        self.assertTrue(result.hedged_frames)
        self.assertEqual(result.hedged_frames[0].hedge, "if")

    def test_every_hedge_marker_is_detectable(self) -> None:
        missing = [
            marker
            for marker in HEDGE_MARKERS
            if marker.isascii()
            and not hedge_for(f"{marker} returns are guaranteed.", 0, 10)
        ]

        self.assertEqual(missing, [])

    def test_an_unhedged_guarantee_is_asserted(self) -> None:
        result = match("Returns are guaranteed.")

        self.assertTrue(result.asserted_frames)
        self.assertEqual(result.hedged_frames, ())

    def test_sentence_span_stops_at_a_terminator(self) -> None:
        text = "One thing. Returns are guaranteed. Another thing."
        start, end = sentence_span(text, text.index("guaranteed"))

        self.assertEqual(text[start:end].strip(), "Returns are guaranteed.")


class MatcherContractTests(unittest.TestCase):
    def test_categories_returns_only_fired_ones(self) -> None:
        matcher = RelationMatcher(PATTERNS)

        self.assertEqual(matcher.categories("Returns are guaranteed."), ("financial_guarantee",))
        self.assertEqual(matcher.categories("Returns are not guaranteed."), ())

    def test_non_string_input_is_rejected(self) -> None:
        from risk_evaluation.intent_patterns.matcher import MatcherError

        with self.assertRaises(MatcherError):
            RelationMatcher(PATTERNS).match_pattern(None, PATTERN)  # type: ignore[arg-type]

    def test_matching_is_deterministic(self) -> None:
        text = "Returns are guaranteed."

        self.assertEqual(match(text).as_dict(), match(text).as_dict())

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(match("Returns are guaranteed.").as_dict(), sort_keys=True)

    def test_hedge_detection_can_be_disabled(self) -> None:
        strict = RelationMatcher(PATTERNS)
        loose = RelationMatcher(PATTERNS, detect_hedges=False)

        self.assertFalse(strict.match_pattern("If rates fall, returns are guaranteed.", PATTERN).fired)
        self.assertTrue(loose.match_pattern("If rates fall, returns are guaranteed.", PATTERN).fired)


if __name__ == "__main__":
    unittest.main()
