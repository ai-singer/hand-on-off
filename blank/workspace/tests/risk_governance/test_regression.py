from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from risk_evaluation.benchmark_registry import BenchmarkRegistry
from risk_evaluation.evaluator import KeywordRiskEvaluator
from risk_evaluation.regression import (
    BASELINE_NAME,
    EVALUATORS,
    IMPROVED,
    PRIMARY_METRIC,
    REGRESSED,
    UNCHANGED,
    RegressionError,
    baseline_path,
    load_baseline,
    run_all,
    run_regression,
    snapshot,
)
from risk_evaluation.semantic_evaluator import SemanticRiskEvaluator


class BaselineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = BenchmarkRegistry()

    def test_every_benchmark_version_has_a_recorded_baseline(self) -> None:
        for record in self.registry.list_benchmarks():
            self.assertTrue(baseline_path(record, self.registry).is_file(), record.version)

    def test_baseline_records_both_evaluators(self) -> None:
        baseline = load_baseline(self.registry.get("semantic", "v1"), self.registry)

        self.assertEqual(set(baseline["evaluators"]), set(EVALUATORS))

    def test_baseline_is_bound_to_the_dataset_hash(self) -> None:
        record = self.registry.get("semantic", "v1")
        baseline = load_baseline(record, self.registry)

        for entry in baseline["evaluators"].values():
            self.assertEqual(entry["dataset_hash"], record.dataset_hash)

    def test_baseline_matches_the_phase_7_3_figures(self) -> None:
        baseline = load_baseline(self.registry.get("semantic", "v1"), self.registry)

        self.assertEqual(baseline["evaluators"]["keyword"]["metrics"]["macro_f1"], 0.2841)
        self.assertEqual(baseline["evaluators"]["semantic"]["metrics"]["macro_f1"], 0.8344)

    def test_v2_baseline_matches_the_decontaminated_figures(self) -> None:
        baseline = load_baseline(self.registry.get("semantic", "v2"), self.registry)

        self.assertEqual(baseline["evaluators"]["keyword"]["metrics"]["macro_f1"], 0.2061)
        self.assertEqual(baseline["evaluators"]["semantic"]["metrics"]["macro_f1"], 0.7424)

    def test_missing_baseline_is_reported(self) -> None:
        record = self.registry.get("semantic", "v2")
        empty = _EmptyRegistry()

        with self.assertRaises(RegressionError):
            load_baseline(record, empty)


class _EmptyRegistry(BenchmarkRegistry):
    def baseline_missing(self) -> bool:
        return True

    def directory(self, record):  # type: ignore[override]
        return Path(__file__).resolve().parent / "does-not-exist"


class RegressionComparisonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = BenchmarkRegistry()
        self.record = self.registry.get("semantic", "v2")
        self.baseline = load_baseline(self.record, self.registry)

    def test_unchanged_evaluator_reports_no_delta(self) -> None:
        report = run_regression(
            self.record, SemanticRiskEvaluator(), registry=self.registry
        )

        self.assertEqual(report.delta, 0.0)
        self.assertEqual(report.status, UNCHANGED)
        self.assertFalse(report.regressed)
        self.assertEqual(report.changed_cases, ())

    def test_every_version_and_evaluator_runs(self) -> None:
        """Four registered versions times two frozen evaluators."""

        reports = run_all(self.registry)

        self.assertEqual(len(reports), 8)
        self.assertTrue(all(not report.regressed for report in reports))

    def test_the_new_phase_7_5_versions_are_covered(self) -> None:
        """A benchmark version without a baseline cannot be governed."""

        for version in ("v3", "v4"):
            record = self.registry.get("semantic", version)
            baseline = load_baseline(record, self.registry)

            self.assertEqual(set(baseline["evaluators"]), set(EVALUATORS))
            for entry in baseline["evaluators"].values():
                self.assertEqual(entry["dataset_hash"], record.dataset_hash)

    def test_a_raise_in_the_previous_score_reads_as_a_regression(self) -> None:
        inflated = copy.deepcopy(self.baseline)
        inflated["evaluators"]["semantic"]["metrics"][PRIMARY_METRIC] = 0.99

        report = run_regression(
            self.record,
            SemanticRiskEvaluator(),
            registry=self.registry,
            baseline=inflated,
        )

        self.assertLess(report.delta, 0)
        self.assertEqual(report.status, REGRESSED)
        self.assertTrue(report.regressed)

    def test_a_drop_in_the_previous_score_reads_as_improvement(self) -> None:
        deflated = copy.deepcopy(self.baseline)
        deflated["evaluators"]["semantic"]["metrics"][PRIMARY_METRIC] = 0.10

        report = run_regression(
            self.record,
            SemanticRiskEvaluator(),
            registry=self.registry,
            baseline=deflated,
        )

        self.assertGreater(report.delta, 0)
        self.assertEqual(report.status, IMPROVED)

    def test_changed_cases_are_attributed(self) -> None:
        flipped = copy.deepcopy(self.baseline)
        case_id = next(iter(flipped["evaluators"]["semantic"]["case_results"]))
        flipped["evaluators"]["semantic"]["case_results"][case_id] = not flipped[
            "evaluators"
        ]["semantic"]["case_results"][case_id]

        report = run_regression(
            self.record,
            SemanticRiskEvaluator(),
            registry=self.registry,
            baseline=flipped,
        )

        self.assertEqual(len(report.changed_cases), 1)
        self.assertEqual(report.changed_cases[0].case_id, case_id)

    def test_dataset_hash_mismatch_is_rejected(self) -> None:
        stale = copy.deepcopy(self.baseline)
        stale["evaluators"]["semantic"]["dataset_hash"] = "0" * 64

        with self.assertRaises(RegressionError):
            run_regression(
                self.record,
                SemanticRiskEvaluator(),
                registry=self.registry,
                baseline=stale,
            )

    def test_unknown_evaluator_key_is_rejected(self) -> None:
        with self.assertRaises(RegressionError):
            run_regression(
                self.record,
                SemanticRiskEvaluator(),
                registry=self.registry,
                baseline={"evaluators": {}},
            )

    def test_report_serializes(self) -> None:
        report = run_regression(
            self.record, KeywordRiskEvaluator(), registry=self.registry, side="keyword"
        )
        payload = json.loads(json.dumps(report.as_dict()))

        self.assertEqual(payload["benchmark_id"], "semantic")
        self.assertEqual(payload["metric"], PRIMARY_METRIC)
        self.assertIn("delta", payload)

    def test_report_renders_the_comparison(self) -> None:
        rendered = run_regression(
            self.record, SemanticRiskEvaluator(), registry=self.registry
        ).render()

        for token in ("previous", "current", "delta", "status"):
            self.assertIn(token, rendered)

    def test_snapshot_shape(self) -> None:
        payload = snapshot(self.record, self.registry, SemanticRiskEvaluator())

        self.assertEqual(set(payload), {
            "benchmark_id",
            "version",
            "evaluator",
            "dataset_hash",
            "metrics",
            "case_results",
        })
        self.assertEqual(len(payload["case_results"]), self.record.case_count)

    def test_primary_metric_is_present_in_metrics(self) -> None:
        payload = snapshot(self.record, self.registry, SemanticRiskEvaluator())

        self.assertIn(PRIMARY_METRIC, payload["metrics"])

    def test_baseline_file_name_is_stable(self) -> None:
        self.assertEqual(BASELINE_NAME, "baseline.json")
        self.assertEqual(
            baseline_path(self.record, self.registry).name, BASELINE_NAME
        )


if __name__ == "__main__":
    unittest.main()
