from __future__ import annotations

import json
import unittest

from risk_evaluation.attribution.evidence import (
    KINDS,
    RULE_PREFIX,
    SPEAKER,
    STANCE,
    EvidenceLog,
    EvidenceMark,
    empty_log,
    marks_for,
)
from risk_evaluation.attribution.model import (
    AUTHORISING_STANCES,
    DISTANCING_STANCES,
    SPEAKERS,
    STANCES,
    AttributionError,
    AttributionResult,
    Claim,
    summarise,
)


def _claim(**overrides) -> Claim:
    base = dict(
        claim_id="claim-001",
        text="Analysts expect growth.",
        speaker="third_party",
        stance="quoted",
        confidence=0.75,
        evidence=("analysts", "expect"),
    )
    base.update(overrides)
    return Claim(**base)


class EvidenceMarkTests(unittest.TestCase):
    def test_a_mark_records_marker_kind_and_rule(self) -> None:
        mark = EvidenceMark("analysts", SPEAKER, "speaker.third-party")

        self.assertEqual(mark.marker, "analysts")
        self.assertEqual(mark.kind, SPEAKER)
        self.assertEqual(mark.rule, "speaker.third-party")

    def test_an_empty_marker_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            EvidenceMark("   ", SPEAKER, "rule")

    def test_an_unknown_kind_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            EvidenceMark("x", "vibes", "rule")

    def test_every_declared_kind_is_accepted(self) -> None:
        for kind in KINDS:
            self.assertEqual(EvidenceMark("x", kind, "rule").kind, kind)

    def test_a_rule_is_required(self) -> None:
        with self.assertRaises(ValueError):
            EvidenceMark("x", SPEAKER, "  ")

    def test_absence_marks_are_recognised(self) -> None:
        mark = EvidenceMark(f"{RULE_PREFIX}no-marker", SPEAKER, "speaker.no-marker")

        self.assertTrue(mark.is_absence)
        self.assertFalse(EvidenceMark("analysts", SPEAKER, "r").is_absence)

    def test_render_is_the_marker(self) -> None:
        self.assertEqual(EvidenceMark("analysts", SPEAKER, "r").render(), "analysts")

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(EvidenceMark("analysts", SPEAKER, "r", (0, 8)).as_dict())


class EvidenceLogTests(unittest.TestCase):
    def test_a_new_log_is_empty_and_falsy(self) -> None:
        self.assertEqual(len(empty_log()), 0)
        self.assertFalse(empty_log())

    def test_add_returns_a_new_log(self) -> None:
        log = empty_log()
        grown = log.add("analysts", kind=SPEAKER, rule="speaker.third-party")

        self.assertEqual(len(log), 0)
        self.assertEqual(len(grown), 1)

    def test_markers_are_de_duplicated_in_order(self) -> None:
        log = (
            empty_log()
            .add("analysts", kind=SPEAKER, rule="a")
            .add("expect", kind=STANCE, rule="b")
            .add("analysts", kind=SPEAKER, rule="a")
        )

        self.assertEqual(log.markers(), ("analysts", "expect"))

    def test_rules_are_reported(self) -> None:
        log = (
            empty_log()
            .add("analysts", kind=SPEAKER, rule="speaker.third-party")
            .add("say", kind=STANCE, rule="stance.quotation")
        )

        self.assertEqual(
            log.rules(), ("speaker.third-party", "stance.quotation")
        )

    def test_for_kind_filters(self) -> None:
        log = (
            empty_log()
            .add("analysts", kind=SPEAKER, rule="r")
            .add("say", kind=STANCE, rule="r")
        )

        self.assertEqual(len(log.for_kind(SPEAKER)), 1)
        self.assertEqual(log.for_kind(SPEAKER)[0].marker, "analysts")

    def test_absence_records_a_rule_tag(self) -> None:
        log = empty_log().absence(kind=SPEAKER, rule="speaker.no-marker")

        self.assertTrue(log.marks[0].is_absence)
        self.assertEqual(log.markers(), (f"{RULE_PREFIX}speaker.no-marker",))

    def test_extend_concatenates(self) -> None:
        first = empty_log().add("a", kind=SPEAKER, rule="r")
        second = empty_log().add("b", kind=STANCE, rule="r")

        self.assertEqual(len(first.extend(second.marks)), 2)

    def test_marks_for_builds_from_plain_strings(self) -> None:
        log = marks_for(["analysts", "expect"], kind=SPEAKER, rule="r")

        self.assertEqual(log.markers(), ("analysts", "expect"))


class ClaimValidationTests(unittest.TestCase):
    """Acceptance criterion 4: no determination without evidence."""

    def test_a_well_formed_claim_is_accepted(self) -> None:
        claim = _claim()

        self.assertEqual(claim.claim_id, "claim-001")
        self.assertEqual(claim.id, "claim-001")

    def test_a_claim_without_evidence_is_rejected(self) -> None:
        with self.assertRaises(AttributionError):
            _claim(evidence=())

    def test_an_empty_id_is_rejected(self) -> None:
        with self.assertRaises(AttributionError):
            _claim(claim_id="")

    def test_empty_text_is_rejected(self) -> None:
        with self.assertRaises(AttributionError):
            _claim(text="   ")

    def test_every_declared_speaker_is_accepted(self) -> None:
        for speaker in SPEAKERS:
            self.assertEqual(_claim(speaker=speaker).speaker, speaker)

    def test_an_unknown_speaker_is_rejected(self) -> None:
        with self.assertRaises(AttributionError):
            _claim(speaker="quoted")

    def test_every_declared_stance_is_accepted(self) -> None:
        for stance in STANCES:
            self.assertEqual(_claim(stance=stance).stance, stance)

    def test_an_unknown_stance_is_rejected(self) -> None:
        with self.assertRaises(AttributionError):
            _claim(stance="agreed")

    def test_confidence_outside_zero_to_one_is_rejected(self) -> None:
        for bad in (-0.1, 1.1):
            with self.assertRaises(AttributionError):
                _claim(confidence=bad)

    def test_evidence_is_a_tuple_of_strings(self) -> None:
        claim = _claim(evidence=["analysts", "expect"])

        self.assertIsInstance(claim.evidence, tuple)
        self.assertTrue(all(isinstance(item, str) for item in claim.evidence))


class ClaimSemanticsTests(unittest.TestCase):
    def test_an_author_claim_is_authorial(self) -> None:
        claim = _claim(speaker="author", stance="endorsed")

        self.assertTrue(claim.is_authorial)
        self.assertFalse(claim.is_attributed)

    def test_an_endorsed_third_party_claim_is_authorial(self) -> None:
        """Taking up somebody else's claim makes it the article's."""

        claim = _claim(speaker="third_party", stance="endorsed")

        self.assertTrue(claim.is_authorial)

    def test_a_quoted_claim_is_not_authorial(self) -> None:
        claim = _claim(speaker="third_party", stance="quoted")

        self.assertFalse(claim.is_authorial)
        self.assertTrue(claim.is_attributed)

    def test_a_rejected_claim_is_not_authorial(self) -> None:
        claim = _claim(speaker="third_party", stance="rejected")

        self.assertFalse(claim.is_authorial)
        self.assertTrue(claim.is_rejected)

    def test_an_unmarked_claim_is_the_default_voice(self) -> None:
        """No attribution at all means the article's own voice applies."""

        claim = _claim(speaker="unknown", stance="uncertain")

        self.assertTrue(claim.is_default_voice)
        self.assertTrue(claim.is_authorial)

    def test_the_default_voice_is_distinguishable_from_an_author_marker(self) -> None:
        marked = _claim(speaker="author", stance="endorsed")
        default = _claim(speaker="unknown", stance="uncertain")

        self.assertFalse(marked.is_default_voice)
        self.assertTrue(default.is_default_voice)

    def test_authorising_and_distancing_stances_are_disjoint(self) -> None:
        self.assertEqual(
            set(AUTHORISING_STANCES) & set(DISTANCING_STANCES), set()
        )

    def test_as_dict_has_the_documented_fields(self) -> None:
        payload = _claim().as_dict()

        for key in ("id", "text", "speaker", "stance", "confidence", "evidence"):
            self.assertIn(key, payload)

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(_claim().as_dict(), sort_keys=True)

    def test_rules_collects_the_distinct_rules(self) -> None:
        claim = _claim(
            detail=(
                EvidenceMark("analysts", SPEAKER, "speaker.third-party"),
                EvidenceMark("expect", STANCE, "stance.quotation"),
            )
        )

        self.assertEqual(
            claim.rules(), ("speaker.third-party", "stance.quotation")
        )


class ResultTests(unittest.TestCase):
    def _result(self) -> AttributionResult:
        claims = (
            _claim(claim_id="claim-001", speaker="third_party", stance="quoted"),
            _claim(claim_id="claim-002", speaker="author", stance="endorsed"),
            _claim(claim_id="claim-003", speaker="third_party", stance="rejected"),
        )
        return AttributionResult(text="x", claims=claims, summary=summarise(claims))

    def test_authorial_claims_are_selected(self) -> None:
        result = self._result()

        self.assertEqual(
            [claim.claim_id for claim in result.authorial_claims], ["claim-002"]
        )

    def test_attributed_claims_are_selected(self) -> None:
        result = self._result()

        self.assertEqual(
            [claim.claim_id for claim in result.attributed_claims],
            ["claim-001", "claim-003"],
        )

    def test_rejected_claims_are_selected(self) -> None:
        result = self._result()

        self.assertEqual(
            [claim.claim_id for claim in result.rejected_claims], ["claim-003"]
        )

    def test_a_claim_can_be_looked_up_by_id(self) -> None:
        self.assertEqual(self._result().claim("claim-002").speaker, "author")

    def test_looking_up_a_missing_claim_raises(self) -> None:
        with self.assertRaises(AttributionError):
            self._result().claim("claim-999")

    def test_summary_counts_speakers_and_stances(self) -> None:
        summary = self._result().summary

        self.assertEqual(summary["claim_count"], 3)
        self.assertEqual(summary["speakers"], {"author": 1, "third_party": 2, "unknown": 0})
        self.assertEqual(summary["stances"]["quoted"], 1)

    def test_summary_lists_the_claim_ids_per_conclusion(self) -> None:
        summary = self._result().summary

        self.assertEqual(summary["authorial_claims"], ["claim-002"])
        self.assertEqual(summary["rejected_claims"], ["claim-003"])

    def test_summary_flags_a_mixed_text(self) -> None:
        self.assertTrue(self._result().summary["mixed"])

    def test_as_dict_has_claims_and_summary(self) -> None:
        payload = self._result().as_dict()

        self.assertEqual(set(payload), {"claims", "summary"})

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(self._result().as_dict(), sort_keys=True)

    def test_render_lists_every_claim(self) -> None:
        rendered = self._result().render()

        for claim_id in ("claim-001", "claim-002", "claim-003"):
            self.assertIn(claim_id, rendered)


if __name__ == "__main__":
    unittest.main()
