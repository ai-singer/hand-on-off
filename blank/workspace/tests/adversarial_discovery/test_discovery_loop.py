"""The Phase 8.1 loop end to end, with the measured numbers pinned.

The counts below are what the discovery run produced against
`semantic-intent-v2` for `semantic/adversarial/v1`. They are pinned so that a
change to the generator, the evaluator or the bridge cannot silently move a
published result. Changing one is a deliberate act that requires re-running
discovery and updating the Phase 8.1 report.
"""

from __future__ import annotations

import json
import unittest

from risk_evaluation.adversarial.case import ATTACK, CONTROL
from risk_evaluation.adversarial.evaluator_bridge import (
    evaluate_cases,
    summarise,
)
from risk_evaluation.adversarial.failure_repository import (
    DEFAULT_CREATED_AT,
    FailureRepository,
    record_from,
    regression_candidates,
    run_discovery,
)
from risk_evaluation.adversarial.generator import default_cases
from risk_evaluation.semantic_evaluator_v2 import SemanticRiskEvaluatorV2


#: Recorded in docs/PHASE_8_1_ADVERSARIAL_RISK_DISCOVERY_REPORT.md.
CASES = 73
ATTACKS = 60
CONTROLS = 13
HITS = 44
MISSES = 29
FALSE_POSITIVES = 0
DEBATABLE_MISSES = 4

#: Misses per strategy: direct 1, paraphrase 10, authority 1, attribution 3,
#: implicit 3, certainty 10, context 1.
MISSES_BY_STRATEGY = {
    "attribution_confusion": 3,
    "authority_disguise": 1,
    "certainty_masking": 10,
    "context_attack": 1,
    "direct_statement": 1,
    "implicit_recommendation": 3,
    "paraphrase": 10,
}


class DiscoveryRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.discovery = run_discovery()

    def test_the_run_scores_every_generated_case(self) -> None:
        self.assertEqual(len(self.discovery.cases), CASES)
        self.assertEqual(len(self.discovery.results), CASES)

    def test_the_recorded_counts_are_reproduced(self) -> None:
        counts = self.discovery.counts

        self.assertEqual(counts["cases"], CASES)
        self.assertEqual(counts["attacks"], ATTACKS)
        self.assertEqual(counts["controls"], CONTROLS)
        self.assertEqual(counts["hits"], HITS)
        self.assertEqual(counts["misses"], MISSES)
        self.assertEqual(counts["false_positives"], FALSE_POSITIVES)
        self.assertEqual(counts["misses_debatable_expectation"], DEBATABLE_MISSES)

    def test_misses_per_strategy_are_reproduced(self) -> None:
        actual = {
            name: bucket["misses"]
            for name, bucket in self.discovery.counts["by_strategy"].items()
        }

        self.assertEqual(actual, MISSES_BY_STRATEGY)

    def test_every_miss_is_recorded_as_a_failure(self) -> None:
        self.assertEqual(len(self.discovery.failures), MISSES)

    def test_every_failure_is_a_miss(self) -> None:
        missed = {item.case_id for item in self.discovery.results if item.miss}
        recorded = {record.case_id for record in self.discovery.failures}

        self.assertEqual(recorded, missed)

    def test_the_run_does_not_write_by_default(self) -> None:
        """Exploring must not mutate the committed repository."""

        before = FailureRepository().load()
        run_discovery()
        after = FailureRepository().load()

        self.assertEqual(before, after)

    def test_a_second_run_produces_the_same_failures(self) -> None:
        again = run_discovery()

        self.assertEqual(
            [record.as_dict() for record in again.failures],
            [record.as_dict() for record in self.discovery.failures],
        )

    def test_every_failure_has_a_regression_candidate(self) -> None:
        self.assertEqual(len(self.discovery.candidates), MISSES)

    def test_run_is_json_serializable(self) -> None:
        json.dumps(self.discovery.as_dict(), sort_keys=True)


class BlindSpotTests(unittest.TestCase):
    """The specific failures the report claims, pinned as behaviour.

    Each test states a text that guide v2 requires to be reported and records
    that it is not. If a later phase fixes one, this test failing is the
    intended signal: move it into a passing expectation and update the report.
    """

    def setUp(self) -> None:
        self.evaluator = SemanticRiskEvaluatorV2()

    def test_a_predicative_guarantee_is_not_detected(self) -> None:
        """v1 matches `guaranteed` only as a prenominal adjective."""

        self.assertEqual(
            self.evaluator.analyze("This return is guaranteed.").categories, ()
        )
        self.assertEqual(
            self.evaluator.analyze("This is a guaranteed return.").categories,
            ("financial_guarantee",),
        )

    def test_the_verbal_form_of_guarantee_is_not_detected(self) -> None:
        for text in (
            "Returns are guaranteed.",
            "Your profit is guaranteed.",
            "We guarantee this return.",
            "The fund guarantees your capital.",
        ):
            self.assertEqual(self.evaluator.analyze(text).categories, (), text)

    def test_an_implied_future_outcome_is_not_detected(self) -> None:
        for text in (
            "The share price doubles next year.",
            "The stock reaches 500 by December.",
            "Revenue grows every quarter from here.",
        ):
            self.assertEqual(self.evaluator.analyze(text).categories, (), text)

    def test_an_unrelated_attribution_withdraws_the_authors_claim(self) -> None:
        """Attribution is decided for the text, not for the claim."""

        analysis = self.evaluator.analyze(
            "Economists forecast slower growth in Europe. This fund cannot lose money."
        )

        self.assertEqual(analysis.statement_source, "third_party")
        self.assertEqual(analysis.categories, ())
        self.assertIn("financial_guarantee", analysis.suppressed)

    def test_a_synonym_of_a_directive_is_not_detected(self) -> None:
        self.assertEqual(
            self.evaluator.analyze(
                "Acquire a position in this equity before the quarter closes."
            ).categories,
            (),
        )

    def test_the_same_vocabulary_gap_prevents_a_wrong_withdrawal(self) -> None:
        """A known Phase 7.5 defect accidentally helps here.

        `The company said …` is not recognised as attribution, so the
        author-voice claim that follows survives. Two defects cancelling is not
        a capability.
        """

        analysis = self.evaluator.analyze(
            "The company said costs were flat last quarter. "
            "The share price will certainly double next year."
        )

        self.assertEqual(analysis.statement_source, "author")
        self.assertIn("market_prediction", analysis.categories)


class StrategyEffectivenessTests(unittest.TestCase):
    """Which strategies actually defeat detection, as opposed to being named."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.discovery = run_discovery()

    def _bucket(self, name: str) -> dict:
        return self.discovery.counts["by_strategy"][name]

    def test_the_direct_baseline_mostly_passes(self) -> None:
        """A high miss rate here would mean the evaluator is broken, not evadable."""

        bucket = self._bucket("direct_statement")

        self.assertGreaterEqual(bucket["hits"], 9)

    def test_paraphrase_defeats_detection_almost_completely(self) -> None:
        bucket = self._bucket("paraphrase")

        self.assertGreaterEqual(bucket["misses"], 10)

    def test_context_wrapping_does_not_defeat_detection(self) -> None:
        """Surrounding prose is not what breaks detection."""

        bucket = self._bucket("context_attack")

        self.assertLessEqual(bucket["misses"], 1)

    def test_certainty_masking_defeats_every_prediction_case(self) -> None:
        """All ten masked claims evade; the five controls still behave."""

        bucket = self._bucket("certainty_masking")

        self.assertEqual(bucket["misses"], 10)
        self.assertEqual(bucket["hits"], 5)

    def test_no_strategy_produced_a_false_positive(self) -> None:
        for name, bucket in self.discovery.counts["by_strategy"].items():
            self.assertEqual(bucket["false_positives"], 0, name)

    def test_the_generated_controls_are_all_clear_expectations(self) -> None:
        for case in self.discovery.cases:
            if case.group == CONTROL:
                self.assertEqual(case.metadata["expectation_strength"], "clear")


class PersistenceTests(unittest.TestCase):
    """The committed repository is exactly the misses this loop found."""

    def test_the_repository_holds_one_record_per_miss(self) -> None:
        records = FailureRepository().load()

        self.assertEqual(len(records), MISSES)

    def test_the_repository_holds_no_false_positive_records(self) -> None:
        """The rule is narrow: only expected-and-not-detected is a failure."""

        for record in FailureRepository().load():
            self.assertNotEqual(record.actual, "reported")

    def test_stored_records_are_the_committed_failure_files(self) -> None:
        from risk_evaluation.adversarial.failure_repository import FAILURE_ROOT

        files = sorted(FAILURE_ROOT.glob("*.json"))

        self.assertEqual(len(files), MISSES)

    def test_rebuilding_from_the_loop_reproduces_the_stored_records(self) -> None:
        discovery = run_discovery()
        stored = FailureRepository().load()

        self.assertEqual(
            [record.as_dict() for record in discovery.failures],
            [record.as_dict() for record in stored],
        )

    def test_stored_records_have_stable_timestamps(self) -> None:
        """Re-running discovery must not churn the committed files."""

        for record in FailureRepository().load():
            self.assertEqual(record.created_at, DEFAULT_CREATED_AT)


class CandidateQualityTests(unittest.TestCase):
    def test_candidates_cover_every_recorded_failure(self) -> None:
        records = FailureRepository().load()
        candidates = regression_candidates(records)

        self.assertEqual(len(candidates), len(records))
        self.assertEqual(
            {item["origin_case_id"] for item in candidates},
            {record.case_id for record in records},
        )

    def test_candidates_are_not_yet_a_benchmark(self) -> None:
        """Proposing material is not the same as publishing a version."""

        for item in regression_candidates(FailureRepository().load()):
            self.assertEqual(item["status"], "candidate")

    def test_candidate_expectations_are_real_categories(self) -> None:
        from risk_evaluation.taxonomy import RISK_TAXONOMY

        known = {entry.name for entry in RISK_TAXONOMY}
        for item in regression_candidates(FailureRepository().load()):
            for name in item["expected_categories"]:
                self.assertIn(name, known)


class OrderingTests(unittest.TestCase):
    def test_attacks_precede_controls_within_a_strategy(self) -> None:
        discovery = run_discovery()
        groups = [case.group for case in discovery.cases]

        self.assertIn(ATTACK, groups)
        self.assertIn(CONTROL, groups)

    def test_summarise_agrees_with_the_run_counts(self) -> None:
        discovery = run_discovery()

        self.assertEqual(summarise(discovery.results), discovery.counts)


if __name__ == "__main__":
    unittest.main()
