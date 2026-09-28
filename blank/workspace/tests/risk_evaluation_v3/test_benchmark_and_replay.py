"""Step 6 and Step 7: the composition benchmark, and the historical replay."""

from __future__ import annotations

import json
import unittest

from risk_evaluation.v3.benchmark import (
    AMBIGUOUS,
    AUTHOR_ENDORSED,
    AUTHOR_REJECTION,
    BENCHMARK_CASES,
    GROUP_BASIS,
    GROUP_NAMES,
    NEUTRAL_EDUCATION,
    REPORT_PATH,
    REQUIRED_GROUP_SIZES,
    THIRD_PARTY_QUOTED,
    BenchmarkCase,
    ClaimLabel,
    case_index,
    evaluate_benchmark,
    group_cases,
    group_sizes,
    label_source,
    metrics_payload,
    write_report,
)
from risk_evaluation.v3.replay import (
    PHASE_81,
    PHASE_83,
    PHASE_84,
    PHASES,
    REQUIRED_PER_PHASE,
    REPLAY_PATH,
    replay,
    replay_cases,
    write_report as write_replay,
)


class BenchmarkShapeTests(unittest.TestCase):
    def test_the_composition_matches_the_phase(self) -> None:
        self.assertEqual(
            group_sizes(),
            {
                AUTHOR_ENDORSED: 15,
                THIRD_PARTY_QUOTED: 15,
                AUTHOR_REJECTION: 10,
                NEUTRAL_EDUCATION: 10,
                AMBIGUOUS: 10,
            },
        )

    def test_the_total_is_sixty(self) -> None:
        self.assertEqual(len(BENCHMARK_CASES), 60)

    def test_every_group_meets_its_required_size(self) -> None:
        sizes = group_sizes()
        for group, required in REQUIRED_GROUP_SIZES.items():
            self.assertGreaterEqual(sizes[group], required, group)

    def test_case_ids_are_unique(self) -> None:
        ids = [case.case_id for case in BENCHMARK_CASES]

        self.assertEqual(len(ids), len(set(ids)))

    def test_case_index_maps_every_id(self) -> None:
        self.assertEqual(len(case_index()), len(BENCHMARK_CASES))

    def test_every_group_has_a_basis(self) -> None:
        for group in GROUP_NAMES:
            self.assertTrue(GROUP_BASIS[group].strip(), group)

    def test_an_unknown_group_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            BenchmarkCase("X-1", "nonsense", "text", (), (ClaimLabel("author", "endorsed"),))

    def test_empty_text_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            BenchmarkCase("X-1", AUTHOR_ENDORSED, " ", (), (ClaimLabel("author", "endorsed"),))

    def test_a_case_needs_a_claim_label(self) -> None:
        with self.assertRaises(ValueError):
            BenchmarkCase("X-1", AUTHOR_ENDORSED, "text", (), ())

    def test_an_unknown_category_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            BenchmarkCase(
                "X-1", AUTHOR_ENDORSED, "text", ("not_a_category",), (ClaimLabel("author", "endorsed"),)
            )

    def test_a_bad_speaker_label_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            BenchmarkCase("X-1", AUTHOR_ENDORSED, "text", (), (ClaimLabel("nobody", "endorsed"),))

    def test_a_bad_stance_label_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            BenchmarkCase("X-1", AUTHOR_ENDORSED, "text", (), (ClaimLabel("author", "shrugged"),))


class LabelProvenanceTests(unittest.TestCase):
    """The phase forbids generating labels from evaluator output."""

    def test_every_case_names_a_guide_section(self) -> None:
        for case in BENCHMARK_CASES:
            self.assertIn("guide v2", label_source(case), case.case_id)

    def test_no_case_records_a_pipeline_result_as_its_basis(self) -> None:
        for case in BENCHMARK_CASES:
            basis = label_source(case).lower()
            for token in ("pipeline", "evaluator output", "v3 says", "baseline says"):
                self.assertNotIn(token, basis, case.case_id)

    def test_group_expectations_follow_the_group(self) -> None:
        for case in BENCHMARK_CASES:
            self.assertEqual(case.expects_risk, bool(case.expected_categories))

    def test_the_neutral_group_never_expects_risk(self) -> None:
        for case in group_cases(NEUTRAL_EDUCATION):
            self.assertFalse(case.expects_risk, case.case_id)

    def test_the_rejection_group_expects_no_author_voice_category(self) -> None:
        author_voice = {
            "investment_advice",
            "market_prediction",
            "financial_guarantee",
            "emotional_manipulation",
        }
        for case in group_cases(AUTHOR_REJECTION):
            self.assertEqual(
                set(case.expected_categories) & author_voice, set(), case.case_id
            )

    def test_every_case_labels_its_claims(self) -> None:
        for case in BENCHMARK_CASES:
            self.assertTrue(case.claims, case.case_id)
            self.assertEqual(len(case.expected_speakers), len(case.claims))


class MetricsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.metrics = evaluate_benchmark()

    def test_every_case_is_scored(self) -> None:
        self.assertEqual(len(self.metrics.outcomes), 60)

    def test_attribution_covers_every_aligned_claim(self) -> None:
        self.assertEqual(self.metrics.attribution.cases, 60)
        self.assertEqual(
            self.metrics.attribution.aligned_claims,
            sum(len(c.claims) for c in BENCHMARK_CASES),
        )

    def test_attribution_accuracy_is_pinned(self) -> None:
        # Phase 8.5 measured speaker 0.9683 / stance 0.9524. Phase 8.7's source
        # typing raised speaker to 0.9841 and left stance where it was: no case in
        # this benchmark labels a stance the repair disagrees with. The one
        # speaker still wrong is `TQ-05`, recorded as open.
        self.assertEqual(self.metrics.attribution.split_accuracy, 1.0)
        self.assertEqual(self.metrics.attribution.speaker_accuracy, 0.9841)
        self.assertEqual(self.metrics.attribution.stance_accuracy, 0.9524)

    def test_intent_recall_is_pinned(self) -> None:
        self.assertEqual(self.metrics.intent.expected_total, 40)
        self.assertEqual(self.metrics.intent.relation_recall, 1.0)

    def test_decision_metrics_are_pinned(self) -> None:
        # Phase 8.5: precision 0.9500, recall 0.7917, accuracy 0.9000,
        # fp 1, fn 5. Phase 8.7 moved recall and accuracy up and precision up as
        # well, and the false positive count is where 8.5 left it.
        self.assertEqual(self.metrics.decision.precision, 0.9565)
        self.assertEqual(self.metrics.decision.recall, 0.9167)
        self.assertEqual(self.metrics.decision.accuracy, 0.95)
        self.assertEqual(self.metrics.decision.counts["fp"], 1)
        self.assertEqual(self.metrics.decision.counts["fn"], 2)

    def test_no_case_was_broken(self) -> None:
        self.assertEqual(self.metrics.broken_cases, ())

    def test_the_repair_fixed_three_more_cases_without_breaking_one(self) -> None:
        """Phase 8.5 fixed 12; Phase 8.7 fixed 15 and broke none.

        `TQ-03` was the one case the first attempt at the fallback guard and
        source typing regressed, and it is asserted here by name so a later
        version of either cannot quietly lose it again.
        """

        self.assertEqual(len(self.metrics.fixed_cases), 15)
        self.assertIn("TQ-03", [item.case_id for item in self.metrics.outcomes])
        self.assertNotIn("TQ-03", [item.case_id for item in self.metrics.decision.errors()])

    def test_the_controls_did_not_regress(self) -> None:
        baseline = self.metrics.baseline.per_group()
        decision = self.metrics.decision.per_group()

        for group in baseline:
            self.assertGreaterEqual(
                decision[group]["correct"], baseline[group]["correct"], group
            )

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(self.metrics.as_dict(), sort_keys=True)

    def test_the_payload_is_json_serializable(self) -> None:
        json.dumps(metrics_payload(self.metrics), sort_keys=True)

    def test_render_states_all_four_metric_families(self) -> None:
        rendered = self.metrics.render()

        for token in ("attribution", "intent", "decision", "trace"):
            self.assertIn(token, rendered)


class TraceMetricsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.metrics = evaluate_benchmark()

    def test_the_trace_is_complete(self) -> None:
        self.assertEqual(self.metrics.trace.completeness, 1.0)
        self.assertGreater(self.metrics.trace.claims, 60)

    def test_no_decision_lacks_evidence(self) -> None:
        self.assertEqual(self.metrics.trace.decisions_without_evidence, 0)

    def test_no_trace_lacks_a_span(self) -> None:
        self.assertEqual(self.metrics.trace.traces_missing_spans, 0)

    def test_every_case_is_trace_complete(self) -> None:
        self.assertEqual(self.metrics.trace.complete_cases, 60)


class BenchmarkArtifactTests(unittest.TestCase):
    def test_the_report_file_exists(self) -> None:
        self.assertTrue(REPORT_PATH.is_file())

    def test_the_file_matches_a_fresh_run(self) -> None:
        payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        fresh = evaluate_benchmark()

        self.assertEqual(payload["case_count"], 60)
        self.assertEqual(
            payload["metrics"]["decision"]["precision"], fresh.decision.precision
        )

    def test_the_file_says_where_labels_come_from(self) -> None:
        payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

        self.assertIn("never from a pipeline run", payload["note"])

    def test_writing_is_reproducible(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "report.json"
            write_report(target)
            first = target.read_text(encoding="utf-8")
            write_report(target)

            self.assertEqual(first, target.read_text(encoding="utf-8"))


class ReplayFixtureTests(unittest.TestCase):
    def test_every_phase_meets_its_minimum(self) -> None:
        groups = replay_cases()

        for phase in PHASES:
            self.assertGreaterEqual(len(groups[phase]), REQUIRED_PER_PHASE, phase)

    def test_the_three_phases_are_present(self) -> None:
        self.assertEqual(set(replay_cases()), {PHASE_81, PHASE_83, PHASE_84})

    def test_case_ids_are_unique_within_a_group(self) -> None:
        for phase, cases in replay_cases().items():
            ids = [case.case_id for case in cases]
            self.assertEqual(len(ids), len(set(ids)), phase)

    def test_every_case_names_its_origin(self) -> None:
        for cases in replay_cases().values():
            for case in cases:
                self.assertTrue(case.origin.strip(), case.case_id)

    def test_every_case_carries_an_expected_label(self) -> None:
        """An expected label may be empty: Phase 8.1's controls expect nothing."""

        for cases in replay_cases().values():
            for case in cases:
                self.assertIsInstance(case.expected, tuple, case.case_id)

    def test_the_replay_includes_cases_that_expect_nothing(self) -> None:
        """The controls are the half that catches over-correction."""

        controls = [
            case
            for cases in replay_cases().values()
            for case in cases
            if not case.expected
        ]

        self.assertTrue(controls)


class ReplayResultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = replay()

    def test_every_case_is_replayed(self) -> None:
        self.assertEqual(
            self.report.cases,
            sum(len(v) for v in replay_cases().values()),
        )

    def test_every_phase_meets_the_minimum_in_the_report(self) -> None:
        for phase, summary in self.report.group_summary().items():
            self.assertTrue(summary["meets_minimum"], phase)

    def test_no_historical_failure_regressed(self) -> None:
        self.assertEqual(self.report.broken, ())

    def test_the_guarantee_blind_spot_is_closed(self) -> None:
        summary = self.report.group_summary()[PHASE_84]

        self.assertGreater(summary["after_correct"], summary["before_correct"])
        self.assertEqual(summary["broken"], [])

    def test_the_attribution_failures_improved(self) -> None:
        summary = self.report.group_summary()[PHASE_83]

        self.assertGreaterEqual(summary["after_correct"], summary["before_correct"])

    def test_every_replay_case_carries_evidence(self) -> None:
        self.assertEqual(self.report.evidence_complete, self.report.cases)

    def test_before_and_after_are_both_kept(self) -> None:
        for item in self.report.outcomes:
            self.assertIsInstance(item.before, tuple)
            self.assertIsInstance(item.after, tuple)
            self.assertTrue(item.trace)

    def test_the_trace_names_the_relation(self) -> None:
        item = next(
            i for i in self.report.outcomes if i.case_id.startswith("84-")
        )

        self.assertTrue(any(entry["intent"] for entry in item.trace))

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(self.report.as_dict(), sort_keys=True)

    def test_render_states_each_phase(self) -> None:
        rendered = self.report.render()

        for phase in PHASES:
            self.assertIn(phase, rendered)

    def test_open_defects_are_reported_not_hidden(self) -> None:
        """Phase 8.1's paraphrase misses are still open and are listed as such."""

        summary = self.report.group_summary()[PHASE_81]

        self.assertTrue(summary["still_wrong"])
        self.assertTrue(summary["fixed"])


class ReplayArtifactTests(unittest.TestCase):
    def test_the_replay_file_exists(self) -> None:
        self.assertTrue(REPLAY_PATH.is_file())

    def test_the_file_records_the_minimums(self) -> None:
        payload = json.loads(REPLAY_PATH.read_text(encoding="utf-8"))

        for phase in PHASES:
            self.assertTrue(payload["by_phase"][phase]["meets_minimum"], phase)

    def test_writing_is_reproducible(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "replay.json"
            write_replay(target)
            first = target.read_text(encoding="utf-8")
            write_replay(target)

            self.assertEqual(first, target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
