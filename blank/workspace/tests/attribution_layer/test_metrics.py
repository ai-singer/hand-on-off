"""Requirement 8's metric, and the coverage boundary that keeps it honest."""

from __future__ import annotations

import json
import unittest

from risk_evaluation.attribution.evaluation import (
    ANNOTATION_CASES,
    ANNOTATION_SET_VERSION,
    COVERAGE_PROBES,
    REPORT_PATH,
    AnnotationRow,
    AttributionMetrics,
    CaseOutcome,
    evaluate_attribution,
    probe_coverage,
    run_case,
    write_report,
)
from risk_evaluation.attribution.model import SPEAKERS, STANCES


class AnnotationSetTests(unittest.TestCase):
    def test_the_set_has_thirty_cases(self) -> None:
        self.assertEqual(len(ANNOTATION_CASES), 30)

    def test_case_ids_are_unique(self) -> None:
        ids = [row.case_id for row in ANNOTATION_CASES]

        self.assertEqual(len(ids), len(set(ids)))

    def test_every_row_states_its_note(self) -> None:
        for row in ANNOTATION_CASES:
            self.assertTrue(row.note.strip(), row.case_id)

    def test_every_row_has_matching_speakers_and_stances(self) -> None:
        for row in ANNOTATION_CASES:
            self.assertEqual(len(row.speakers), len(row.stances), row.case_id)

    def test_every_expected_label_is_declared(self) -> None:
        for row in ANNOTATION_CASES:
            for name in row.speakers:
                self.assertIn(name, SPEAKERS, row.case_id)
            for name in row.stances:
                self.assertIn(name, STANCES, row.case_id)

    def test_all_three_speakers_appear(self) -> None:
        covered = {name for row in ANNOTATION_CASES for name in row.speakers}

        self.assertEqual(covered, set(SPEAKERS))

    def test_all_four_stances_appear(self) -> None:
        covered = {name for row in ANNOTATION_CASES for name in row.stances}

        self.assertEqual(covered, set(STANCES))

    def test_the_set_contains_multi_claim_cases(self) -> None:
        multi = [row for row in ANNOTATION_CASES if row.claim_count > 1]

        self.assertGreaterEqual(len(multi), 4)

    def test_mismatched_speaker_and_stance_counts_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            AnnotationRow("X-1", "text", ("author",), ("endorsed", "quoted"))

    def test_an_unknown_speaker_in_an_annotation_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            AnnotationRow("X-1", "text", ("nobody",), ("quoted",))

    def test_a_row_with_no_claims_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            AnnotationRow("X-1", "text", (), ())


class MainMetricTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.metrics = evaluate_attribution()

    def test_the_metric_covers_every_case(self) -> None:
        self.assertEqual(self.metrics.cases, 30)

    def test_the_split_is_exact(self) -> None:
        self.assertEqual(self.metrics.split_correct, 30)
        self.assertEqual(self.metrics.split_accuracy, 1.0)

    def test_speaker_accuracy_is_exact(self) -> None:
        self.assertEqual(self.metrics.speaker_accuracy, 1.0)

    def test_stance_accuracy_is_exact(self) -> None:
        self.assertEqual(self.metrics.stance_accuracy, 1.0)

    def test_every_aligned_claim_is_counted(self) -> None:
        self.assertEqual(
            self.metrics.aligned_claims, self.metrics.expected_claims
        )
        self.assertGreater(self.metrics.aligned_claims, 30)

    def test_no_split_or_label_errors_remain(self) -> None:
        self.assertEqual(self.metrics.split_errors(), ())
        self.assertEqual(self.metrics.label_errors(), ())

    def test_per_speaker_breakdown_covers_every_speaker(self) -> None:
        self.assertEqual(set(self.metrics.per_speaker()), set(SPEAKERS))

    def test_per_stance_breakdown_covers_every_stance(self) -> None:
        self.assertEqual(set(self.metrics.per_stance()), set(STANCES))

    def test_metrics_are_json_serializable(self) -> None:
        json.dumps(self.metrics.as_dict(), sort_keys=True)

    def test_render_states_all_three_metrics(self) -> None:
        rendered = self.metrics.render()

        self.assertIn("claim split accuracy", rendered)
        self.assertIn("speaker accuracy", rendered)
        self.assertIn("stance accuracy", rendered)

    def test_the_metric_does_not_report_risk_scores(self) -> None:
        """This layer does not classify risk, so it must not report risk F1."""

        payload = self.metrics.as_dict()

        for key in ("macro_f1", "precision", "recall", "false_positive_rate"):
            self.assertNotIn(key, payload)


class CoverageProbeTests(unittest.TestCase):
    """The boundary stress set, reported separately from the headline metric."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.metrics = probe_coverage()

    def test_the_probe_is_not_part_of_the_main_set(self) -> None:
        main_ids = {row.case_id for row in ANNOTATION_CASES}
        probe_ids = {row.case_id for row in COVERAGE_PROBES}

        self.assertEqual(main_ids & probe_ids, set())

    def test_the_probe_covers_the_predicted_boundary(self) -> None:
        self.assertEqual(len(COVERAGE_PROBES), 12)

    def test_the_probe_records_actual_shortfalls(self) -> None:
        """A stress set that everything passes would not be a stress set.

        These are the known limits of a rule table: unnamed plural speakers,
        passive attribution, nominalised attribution, and disagreement phrased
        outside the cue list.
        """

        self.assertLess(self.metrics.split_accuracy, 1.0)
        self.assertLess(self.metrics.speaker_accuracy, 1.0)

    def test_the_unnamed_speaker_cases_are_the_speaker_failures(self) -> None:
        failed = {item.case_id for item in self.metrics.label_errors()}

        self.assertEqual(failed, {"PR-001", "PR-002", "PR-003"})

    def test_the_split_failure_is_the_semicolon_case(self) -> None:
        failed = {item.case_id for item in self.metrics.split_errors()}

        self.assertEqual(failed, {"PR-006"})

    def test_absolute_attribution_cases_pass(self) -> None:
        """Attribution phrased the way the table expects does work."""

        for case_id in ("PR-004", "PR-005", "PR-007", "PR-011", "PR-012"):
            outcome = next(
                item for item in self.metrics.outcomes if item.case_id == case_id
            )
            self.assertTrue(outcome.split_ok, case_id)
            self.assertTrue(all(outcome.speaker_ok), case_id)

    def test_chinese_cases_are_handled(self) -> None:
        for case_id in ("PR-009", "PR-010"):
            outcome = next(
                item for item in self.metrics.outcomes if item.case_id == case_id
            )
            self.assertTrue(all(outcome.speaker_ok), case_id)


class OutcomeTests(unittest.TestCase):
    def test_an_outcome_records_expected_and_predicted(self) -> None:
        row = ANNOTATION_CASES[0]
        outcome = run_case(row)

        self.assertEqual(outcome.expected_speakers, row.speakers)
        self.assertEqual(outcome.predicted_speakers, row.speakers)

    def test_a_misaligned_case_reports_no_per_claim_comparison(self) -> None:
        """Comparing positions across different claim counts measures nothing."""

        outcome = CaseOutcome(
            case_id="X-1",
            text="t",
            expected_speakers=("author", "author"),
            expected_stances=("endorsed", "endorsed"),
            predicted_speakers=("author",),
            predicted_stances=("endorsed",),
            split_ok=False,
        )

        self.assertEqual(outcome.speaker_ok, ())
        self.assertEqual(outcome.stance_ok, ())

    def test_a_misaligned_case_is_excluded_from_the_accuracy_denominator(
        self,
    ) -> None:
        mismatched = CaseOutcome(
            case_id="X-1",
            text="t",
            expected_speakers=("author", "author"),
            expected_stances=("endorsed", "endorsed"),
            predicted_speakers=("third_party",),
            predicted_stances=("quoted",),
            split_ok=False,
        )
        metrics = AttributionMetrics(outcomes=(mismatched,))

        self.assertEqual(metrics.cases, 1)
        self.assertEqual(metrics.aligned_claims, 0)
        self.assertEqual(metrics.speaker_accuracy, 0.0)
        self.assertEqual(metrics.split_accuracy, 0.0)

    def test_empty_metrics_do_not_divide_by_zero(self) -> None:
        metrics = AttributionMetrics(outcomes=())

        self.assertEqual(metrics.split_accuracy, 0.0)
        self.assertEqual(metrics.speaker_accuracy, 0.0)
        self.assertEqual(metrics.stance_accuracy, 0.0)


class ReportArtifactTests(unittest.TestCase):
    def test_the_report_is_written(self) -> None:
        self.assertTrue(REPORT_PATH.is_file())

    def test_the_report_records_both_sets_separately(self) -> None:
        payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

        self.assertIn("coverage_probe", payload)
        self.assertEqual(payload["cases"], 30)
        self.assertEqual(payload["annotation_set_version"], ANNOTATION_SET_VERSION)

    def test_the_report_says_the_probe_is_not_held_out(self) -> None:
        payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

        self.assertIn("not a held-out estimate", payload["note"])

    def test_the_report_carries_per_case_detail(self) -> None:
        payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

        self.assertEqual(len(payload["cases_detail"]), 30)
        self.assertEqual(len(payload["coverage_detail"]), len(COVERAGE_PROBES))

    def test_the_report_matches_a_fresh_evaluation(self) -> None:
        payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        fresh = evaluate_attribution().as_dict()

        for key in ("split_accuracy", "speaker_accuracy", "stance_accuracy"):
            self.assertEqual(payload[key], fresh[key], key)

    def test_writing_is_reproducible(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "report.json"
            write_report(target)
            first = target.read_text(encoding="utf-8")
            write_report(target)

            self.assertEqual(first, target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
