"""Requirement D: replay the Phase 8.1 attribution failures.

Phase 8.1 recorded three `attribution_confusion` misses and two cases that
passed for the wrong reason. This module reloads all nine cases of that family
straight from the published benchmark and the committed failure repository, and
checks that the new layer produces the structure Phase 8.1 showed was missing.

**The risk verdict is not expected to change.** `semantic_evaluator_v2` is not
modified and not imported for scoring here: these tests are about whether the
attribution layer can say *whose* claim each part of the text is, which is the
information a future evaluator would need.
"""

from __future__ import annotations

import unittest

from risk_evaluation.adversarial.failure_repository import FailureRepository
from risk_evaluation.attribution.analyzer import (
    AttributionAnalyzer,
    authorial_text,
    claim_views,
)
from risk_evaluation.benchmark_registry import BenchmarkRegistry


BENCHMARK_ID = "semantic/adversarial"
BENCHMARK_VERSION = "v1"


def _family_cases() -> tuple[dict, ...]:
    registry = BenchmarkRegistry()
    record = registry.get(BENCHMARK_ID, BENCHMARK_VERSION)
    return tuple(
        item
        for item in registry.load_records(record)
        if item["attack_strategy"] == "attribution_confusion"
    )


class ReplayFixtureTests(unittest.TestCase):
    def test_the_family_is_present_in_the_published_benchmark(self) -> None:
        self.assertEqual(len(_family_cases()), 9)

    def test_five_of_them_are_attacks(self) -> None:
        attacks = [c for c in _family_cases() if c["expected_detection"]]

        self.assertEqual(len(attacks), 5)

    def test_four_of_them_are_controls(self) -> None:
        controls = [c for c in _family_cases() if not c["expected_detection"]]

        self.assertEqual(len(controls), 4)

    def test_the_recorded_failures_are_still_on_disk(self) -> None:
        recorded = [
            item
            for item in FailureRepository().load()
            if item.strategy == "attribution_confusion"
        ]

        self.assertEqual(len(recorded), 3)
        self.assertEqual(
            {item.case_id for item in recorded},
            {"ADV-ATT-01", "ADV-ATT-03", "ADV-ATT-05"},
        )

    def test_the_failure_texts_match_the_benchmark_texts(self) -> None:
        by_id = {item["id"]: item["text"] for item in _family_cases()}

        for failure in FailureRepository().load():
            if failure.strategy == "attribution_confusion":
                self.assertEqual(failure.text, by_id[failure.case_id])


class AttackReplayTests(unittest.TestCase):
    """The three recorded misses, and the two accidental passes."""

    def setUp(self) -> None:
        self.analyzer = AttributionAnalyzer()
        self.cases = {item["id"]: item for item in _family_cases()}

    def _claims(self, case_id: str):
        return self.analyzer.analyze(self.cases[case_id]["text"]).claims

    def test_the_claim_the_author_makes_is_isolated(self) -> None:
        """Every attack puts the author's own risk in the second sentence.

        Phase 8.1 could not see it: one attribution anywhere in the text
        withdrew every author-voice category in it. The new layer reports the
        second claim as authorial.

        Its `speaker` is `unknown`, not `author`, because the sentence carries
        no speaker marker - `Buy this stock before the quarter ends.` says
        nothing about who is speaking. That is the default voice, which the
        taxonomy treats as the author's, and the layer records it as a default
        rather than pretending a marker was found.
        """

        expected = {
            "ADV-ATT-01": "Buy this stock before the quarter ends.",
            "ADV-ATT-03": "This fund cannot lose money.",
            "ADV-ATT-05": "Do not miss this opportunity.",
        }
        for case_id, text in expected.items():
            claims = self._claims(case_id)

            self.assertEqual(len(claims), 2, case_id)
            self.assertEqual(claims[1].text, text, case_id)
            self.assertTrue(claims[1].is_authorial, case_id)
            self.assertTrue(claims[1].is_default_voice, case_id)
            self.assertEqual(claims[1].speaker, "unknown", case_id)

    def test_the_attribution_is_confined_to_the_clause_it_covers(self) -> None:
        """The first claim is the third party's; the second is not."""

        claims = self._claims("ADV-ATT-03")

        self.assertEqual(claims[0].speaker, "third_party")
        self.assertFalse(claims[0].is_authorial)
        self.assertTrue(claims[1].is_authorial)

    def test_authorial_text_excludes_the_borrowed_attribution(self) -> None:
        """This is the string a future evaluator would run its rules over."""

        for case_id in ("ADV-ATT-01", "ADV-ATT-03", "ADV-ATT-05"):
            text = authorial_text(self.analyzer.analyze(self.cases[case_id]["text"]))

            self.assertNotIn("Analysts", text, case_id)
            self.assertNotIn("Economists", text, case_id)
            self.assertNotIn("Regulators", text, case_id)

    def test_the_accidental_pass_shows_why_it_passed(self) -> None:
        """ADV-ATT-02 passed in Phase 8.1 for the wrong reason.

        `The company said` is not in v2's attribution lexicon, so nothing was
        withdrawn and the prediction survived by accident. The new layer reports
        the two claims separately and does not depend on that gap.
        """

        claims = self._claims("ADV-ATT-02")

        self.assertEqual(len(claims), 2)
        self.assertTrue(claims[1].is_authorial)
        self.assertTrue(claims[1].is_default_voice)

    def test_the_attribution_agnostic_attack_stays_attributed(self) -> None:
        """ADV-ATT-04 targets `unverified_information`, which is voice-agnostic.

        Its second sentence, `Sources say the company will be acquired.`, is
        genuinely attributed to sources, and guide v2 reports that category
        whatever the voice. The layer must therefore *not* produce an authorial
        claim here - over-correcting would be as wrong as the original defect.
        """

        claims = self._claims("ADV-ATT-04")

        self.assertEqual(len(claims), 2)
        self.assertEqual(claims[1].speaker, "third_party")
        self.assertFalse(claims[1].is_authorial)

    def test_every_attack_splits_into_two_claims(self) -> None:
        for case in _family_cases():
            if not case["expected_detection"]:
                continue
            result = self.analyzer.analyze(case["text"])

            self.assertEqual(len(result.claims), 2, case["id"])

    def test_attacks_on_author_voice_categories_yield_an_authorial_claim(
        self,
    ) -> None:
        """Four of the five target author-voice categories."""

        author_voice = {
            "ADV-ATT-01",
            "ADV-ATT-02",
            "ADV-ATT-03",
            "ADV-ATT-05",
        }
        for case in _family_cases():
            if case["id"] not in author_voice:
                continue
            result = self.analyzer.analyze(case["text"])

            self.assertEqual(len(result.authorial_claims), 1, case["id"])

    def test_every_attack_claim_carries_evidence(self) -> None:
        for case in _family_cases():
            if not case["expected_detection"]:
                continue
            for claim in self.analyzer.analyze(case["text"]).claims:
                self.assertTrue(claim.evidence, f"{case['id']}/{claim.claim_id}")


class ControlReplayTests(unittest.TestCase):
    """The controls must stay non-authorial, or the layer over-corrects."""

    def setUp(self) -> None:
        self.analyzer = AttributionAnalyzer()
        self.cases = {item["id"]: item for item in _family_cases()}

    def test_every_control_has_no_authorial_claim(self) -> None:
        for case in _family_cases():
            if case["expected_detection"]:
                continue
            result = self.analyzer.analyze(case["text"])

            self.assertEqual(result.authorial_claims, (), case["id"])

    def test_every_control_has_empty_authorial_text(self) -> None:
        for case in _family_cases():
            if case["expected_detection"]:
                continue
            text = authorial_text(self.analyzer.analyze(case["text"]))

            self.assertEqual(text, "", case["id"])

    def test_a_genuinely_attributed_guarantee_is_not_the_articles(self) -> None:
        claim = self.analyzer.analyze(
            self.cases["ADV-CTL-01"]["text"]
        ).claims[0]

        self.assertEqual(claim.speaker, "third_party")
        self.assertEqual(claim.stance, "quoted")

    def test_a_quoted_pressure_line_is_not_the_articles(self) -> None:
        claim = self.analyzer.analyze(
            self.cases["ADV-CTL-04"]["text"]
        ).claims[0]

        self.assertFalse(claim.is_authorial)

    def test_the_layer_separates_attacks_from_controls(self) -> None:
        """Same strategy, opposite conclusions - decided by structure, not topic."""

        attack = self.analyzer.analyze(self.cases["ADV-ATT-03"]["text"])
        control = self.analyzer.analyze(self.cases["ADV-CTL-01"]["text"])

        self.assertTrue(attack.authorial_claims)
        self.assertEqual(control.authorial_claims, ())


class AddedStructureTests(unittest.TestCase):
    """What the layer adds that Phase 8.1 did not have."""

    def setUp(self) -> None:
        self.analyzer = AttributionAnalyzer()

    def test_each_claim_states_a_speaker_and_a_stance(self) -> None:
        result = self.analyzer.analyze(
            self.cases_text("ADV-ATT-03")
        )

        for view in claim_views(result):
            self.assertIn(view.claim.speaker, ("author", "third_party", "unknown"))
            self.assertIn(
                view.claim.stance, ("endorsed", "quoted", "rejected", "uncertain")
            )

    def cases_text(self, case_id: str) -> str:
        for item in _family_cases():
            if item["id"] == case_id:
                return item["text"]
        raise AssertionError(case_id)

    def test_the_layer_reports_claim_count_per_text(self) -> None:
        result = self.analyzer.analyze(self.cases_text("ADV-ATT-01"))

        self.assertEqual(result.summary["claim_count"], 2)

    def test_the_layer_marks_the_text_as_mixed(self) -> None:
        result = self.analyzer.analyze(self.cases_text("ADV-ATT-01"))

        self.assertTrue(result.summary["mixed"])

    def test_the_layer_maps_onto_taxonomy_v2_vocabulary(self) -> None:
        from risk_evaluation.taxonomy_v2 import STATEMENT_SOURCES

        result = self.analyzer.analyze(self.cases_text("ADV-ATT-03"))
        sources = [view.statement_source for view in claim_views(result)]

        self.assertEqual(sources[0], "quoted")
        self.assertEqual(sources[1], "author")
        for name in sources:
            self.assertIn(name, STATEMENT_SOURCES)

    def test_replaying_does_not_change_the_recorded_risk_verdict(self) -> None:
        """The failure repository is evidence, not something to update."""

        recorded = {
            item.case_id: item.actual
            for item in FailureRepository().load()
            if item.strategy == "attribution_confusion"
        }

        self.assertEqual(set(recorded.values()), {"none"})


if __name__ == "__main__":
    unittest.main()
