"""Evaluation reproducibility, the confusion matrices, failure classes and the gate."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from risk_evaluation.v3_independent.adversarial import (
    ADVERSARIAL_PATH,
    ANNOTATION_DISAGREEMENT,
    ATTRIBUTION_ERROR,
    ERROR_KINDS,
    KIND_MEANING,
    LEXICAL_GAP,
    PROPOSALS,
    PROPOSALS_PATH,
    SEMANTIC_GAP,
    TAXONOMY_AMBIGUITY,
    Analysis,
    AnalysisError,
    analyse,
    classify,
    describe as describe_adversarial,
    proposal_payload,
)
from risk_evaluation.v3_independent.coverage import (
    COVERAGE_PATH,
    DIMENSIONS,
    build as build_coverage,
    describe as describe_coverage,
)
from risk_evaluation.v3_independent.dataset import load_records
from risk_evaluation.v3_independent.evaluation import (
    NONE,
    PRECEDENCE,
    CategoryMetrics,
    CaseResult,
    Metrics,
    evaluate,
    predict,
    primary_category,
    score,
)
from risk_evaluation.v3_independent.isolation import (
    ALLOWED_INTERNAL_PREFIXES,
    FORBIDDEN_PREFIXES,
    IsolationError,
    changed_paths,
    describe as describe_isolation,
    scan,
)
from risk_evaluation.v3_independent.regression import (
    REGRESSION_PATH,
    REQUIRED_SETS,
    RegressionError,
    build as build_regression,
)
from risk_evaluation.v3_1.regression import CAPABILITY_SET


def result(
    case_id: str = "IND-0001",
    *,
    expected=(),
    predicted=(),
    expected_relations=(),
    found_relations=(),
    speakers=("author",),
    stances=("endorsed",),
    resolved: bool = True,
    **frame,
) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        text="text",
        group=frame.get("group", "safe"),
        language=frame.get("language", "en"),
        form=frame.get("form", "nominal"),
        source_type=frame.get("source_type", "news_report"),
        topic=frame.get("topic", "funds"),
        boundary_kind=frame.get("boundary_kind", ""),
        intended_intent=frame.get("intended_intent", ""),
        expected=tuple(expected),
        predicted=tuple(predicted),
        expected_relations=tuple(expected_relations),
        found_relations=tuple(found_relations),
        speakers=tuple(speakers),
        stances=tuple(stances),
        evidence=("rule:test",),
        decisions=(),
        suppressed=(),
        resolved=resolved,
    )


class PrimaryCategoryTests(unittest.TestCase):
    def test_precedence_is_the_taxonomys(self) -> None:
        self.assertEqual(PRECEDENCE[0], "investment_advice")
        self.assertEqual(PRECEDENCE[-1], "emotional_manipulation")

    def test_the_highest_precedence_wins(self) -> None:
        self.assertEqual(
            primary_category(("emotional_manipulation", "investment_advice")),
            "investment_advice",
        )

    def test_an_empty_set_is_none(self) -> None:
        self.assertEqual(primary_category(()), NONE)

    def test_a_single_category_is_itself(self) -> None:
        self.assertEqual(primary_category(("market_prediction",)), "market_prediction")


class OutcomeTests(unittest.TestCase):
    def test_a_correct_positive(self) -> None:
        item = result(expected=("market_prediction",), predicted=("market_prediction",))
        self.assertEqual(item.outcome, "tp")
        self.assertTrue(item.correct)

    def test_a_missed_positive(self) -> None:
        item = result(expected=("market_prediction",))
        self.assertEqual(item.outcome, "fn")
        self.assertFalse(item.correct)
        self.assertEqual(item.missing, ("market_prediction",))

    def test_a_false_positive(self) -> None:
        item = result(predicted=("market_prediction",))
        self.assertEqual(item.outcome, "fp")
        self.assertEqual(item.extra, ("market_prediction",))

    def test_a_correct_negative(self) -> None:
        item = result()
        self.assertEqual(item.outcome, "tn")
        self.assertTrue(item.correct)

    def test_an_extra_category_is_incorrect_even_when_the_rest_matches(self) -> None:
        item = result(
            expected=("market_prediction",),
            predicted=("market_prediction", "unverified_information"),
        )
        self.assertFalse(item.correct)
        self.assertEqual(item.extra, ("unverified_information",))
        self.assertEqual(item.outcome, "tp")


class MetricArithmeticTests(unittest.TestCase):
    def test_a_perfect_run(self) -> None:
        items = (
            result("IND-1", expected=("market_prediction",), predicted=("market_prediction",)),
            result("IND-2"),
        )
        metrics = score(items)
        self.assertEqual(metrics.precision, 1.0)
        self.assertEqual(metrics.recall, 1.0)
        self.assertEqual(metrics.f1, 1.0)
        self.assertEqual(metrics.accuracy, 1.0)

    def test_a_run_that_never_fires(self) -> None:
        items = (result("IND-1", expected=("market_prediction",)), result("IND-2"))
        metrics = score(items)
        self.assertEqual(metrics.recall, 0.0)
        self.assertEqual(metrics.f1, 0.0)
        self.assertEqual(metrics.counts["fn"], 1)

    def test_a_run_that_always_fires(self) -> None:
        items = (result("IND-1", predicted=("market_prediction",)), result("IND-2", predicted=("market_prediction",)))
        metrics = score(items)
        self.assertEqual(metrics.precision, 0.0)
        self.assertEqual(metrics.counts["fp"], 2)

    def test_f1_is_the_harmonic_mean(self) -> None:
        row = CategoryMetrics("x", tp=3, fp=1, fn=1, tn=5)
        self.assertEqual(row.precision, 0.75)
        self.assertEqual(row.recall, 0.75)
        self.assertEqual(row.f1, 0.75)

    def test_the_confusion_matrix_is_two_by_two(self) -> None:
        row = CategoryMetrics("x", tp=3, fp=1, fn=1, tn=5)
        self.assertEqual(row.confusion, ((5, 1), (1, 3)))

    def test_the_support_is_tp_plus_fn(self) -> None:
        self.assertEqual(CategoryMetrics("x", tp=3, fp=1, fn=2, tn=5).support, 5)

    def test_the_rates_are_reported(self) -> None:
        items = (
            result("IND-1", expected=("market_prediction",)),
            result("IND-2", predicted=("market_prediction",)),
        )
        metrics = score(items)
        self.assertEqual(metrics.false_negative_rate, 1.0)
        self.assertEqual(metrics.false_positive_rate, 1.0)


class ConfusionMatrixTests(unittest.TestCase):
    def test_the_primary_matrix_is_square_over_precedence_plus_none(self) -> None:
        items = (result("IND-1", expected=("market_prediction",), predicted=()),)
        labels, grid = score(items).primary_matrix()
        self.assertEqual(labels, (*PRECEDENCE, NONE))
        self.assertEqual(len(grid), len(labels))
        for row in grid:
            self.assertEqual(len(row), len(labels))

    def test_the_matrix_counts_every_case(self) -> None:
        items = (
            result("IND-1", expected=("market_prediction",), predicted=("market_prediction",)),
            result("IND-2", expected=("investment_advice",)),
            result("IND-3"),
        )
        labels, grid = score(items).primary_matrix()
        self.assertEqual(sum(sum(row) for row in grid), 3)

    def test_each_category_gets_its_own_two_by_two(self) -> None:
        items = (result("IND-1", expected=("market_prediction",), predicted=("market_prediction",)),)
        rows = score(items).per_category()
        self.assertEqual(len(rows), 5)
        for row in rows:
            self.assertEqual(len(row.confusion), 2)
            self.assertEqual(len(row.confusion[0]), 2)

    def test_the_matrix_places_a_miss_in_the_right_cell(self) -> None:
        items = (result("IND-1", expected=("market_prediction",), predicted=()),)
        labels, grid = score(items).primary_matrix()
        row = labels.index("market_prediction")
        column = labels.index(NONE)
        self.assertEqual(grid[row][column], 1)


class RelationMetricsTests(unittest.TestCase):
    def test_a_found_relation_is_a_true_positive(self) -> None:
        items = (result("IND-1", expected_relations=("PREDICTION",), found_relations=("PREDICTION",)),)
        row = score(items).relation_metrics()
        self.assertEqual(row.tp, 1)

    def test_a_missing_relation_is_a_false_negative(self) -> None:
        items = (result("IND-1", expected_relations=("PREDICTION",)),)
        self.assertEqual(score(items).relation_metrics().fn, 1)

    def test_an_extra_relation_is_a_false_positive(self) -> None:
        items = (result("IND-1", found_relations=("PREDICTION",)),)
        self.assertEqual(score(items).relation_metrics().fp, 1)


class EvaluationReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = evaluate()

    def test_the_report_covers_every_case(self) -> None:
        self.assertEqual(len(self.payload["cases"]), 300)

    def test_unresolved_cases_are_excluded_from_the_primary_metrics(self) -> None:
        unresolved = self.payload["unresolved"]
        self.assertGreater(unresolved["cases"], 0)
        self.assertEqual(
            self.payload["primary"]["cases"] + unresolved["cases"], 300
        )
        for case_id in unresolved["case_ids"]:
            self.assertNotIn(case_id, self.payload["primary"]["error_cases"])

    def test_the_unresolved_block_explains_the_exclusion(self) -> None:
        self.assertIn("declined to settle", self.payload["unresolved"]["note"])

    def test_the_report_has_every_metric_the_phase_names(self) -> None:
        primary = self.payload["primary"]
        for key in (
            "precision",
            "recall",
            "f1",
            "false_positives",
            "false_negatives",
            "per_category",
            "confusion_primary",
        ):
            self.assertIn(key, primary, key)

    def test_per_category_metrics_cover_all_five(self) -> None:
        rows = self.payload["primary"]["per_category"]
        self.assertEqual(len(rows), 5)
        for row in rows:
            for key in ("precision", "recall", "f1", "tp", "fp", "fn", "tn"):
                self.assertIn(key, row)

    def test_the_confusion_matrix_is_serializable_and_square(self) -> None:
        block = self.payload["primary"]["confusion_primary"]
        self.assertEqual(len(block["labels"]), 6)
        for row in block["matrix"]:
            self.assertEqual(len(row), 6)

    def test_the_totals_reconcile_with_the_case_results(self) -> None:
        primary = self.payload["primary"]
        self.assertEqual(
            primary["correct"] + len(primary["error_cases"]), primary["cases"]
        )

    def test_the_evaluation_is_reproducible(self) -> None:
        again = evaluate()
        self.assertEqual(again["primary"], self.payload["primary"])

    def test_predictions_are_stable_across_runs(self) -> None:
        first = [(item.case_id, item.predicted) for item in predict()]
        second = [(item.case_id, item.predicted) for item in predict()]
        self.assertEqual(first, second)

    def test_the_case_results_carry_the_trace(self) -> None:
        for item in self.payload["cases"][:20]:
            self.assertIn("evidence", item)
            self.assertIn("outcome", item)

    def test_every_case_result_carries_its_frame_dimensions(self) -> None:
        for item in self.payload["cases"]:
            for key in ("language", "form", "source_type", "topic", "group"):
                self.assertIn(key, item)

    def test_the_module_does_not_claim_real_world_accuracy(self) -> None:
        text = json.dumps(self.payload).lower()
        self.assertNotIn("real-world accuracy is", text.replace("unknown", ""))

    def test_a_fixture_report_serialises(self) -> None:
        json.dumps(score((result("IND-1"),)).as_dict(), sort_keys=True)


class AdversarialClassificationTests(unittest.TestCase):
    def test_every_failure_class_is_declared(self) -> None:
        self.assertEqual(len(ERROR_KINDS), 5)
        self.assertEqual(set(KIND_MEANING), set(ERROR_KINDS))
        for kind in (
            LEXICAL_GAP,
            SEMANTIC_GAP,
            ATTRIBUTION_ERROR,
            TAXONOMY_AMBIGUITY,
            ANNOTATION_DISAGREEMENT,
        ):
            self.assertIn(kind, ERROR_KINDS)

    def test_a_passing_case_is_not_diagnosed(self) -> None:
        item = result(expected=("market_prediction",), predicted=("market_prediction",))
        self.assertIsNone(classify(item, adjudication={}, disagreements={}))

    def test_a_missing_relation_is_a_lexical_gap(self) -> None:
        item = result(expected=("market_prediction",), predicted=())
        found = classify(item, adjudication={}, disagreements={})
        self.assertEqual(found.kind, LEXICAL_GAP)

    def test_a_found_relation_with_a_wrong_outcome_is_a_semantic_gap(self) -> None:
        item = result(
            expected=("market_prediction",),
            predicted=(),
            expected_relations=("PREDICTION",),
            found_relations=("PREDICTION",),
        )
        found = classify(item, adjudication={}, disagreements={})
        self.assertEqual(found.kind, SEMANTIC_GAP)

    def test_a_disputed_label_outranks_everything(self) -> None:
        item = result(expected=("market_prediction",), predicted=())
        found = classify(
            item,
            adjudication={},
            disagreements={"IND-0001": ({"field": "decision"},)},
        )
        self.assertEqual(found.kind, ANNOTATION_DISAGREEMENT)

    def test_a_third_reading_is_a_taxonomy_ambiguity(self) -> None:
        item = result(expected=("market_prediction",), predicted=())
        found = classify(
            item,
            adjudication={"IND-0001": ({"resolution": "third_reading"},)},
            disagreements={},
        )
        self.assertEqual(found.kind, TAXONOMY_AMBIGUITY)

    def test_an_unresolved_ruling_is_a_taxonomy_ambiguity(self) -> None:
        item = result(expected=("market_prediction",), predicted=())
        found = classify(
            item,
            adjudication={"IND-0001": ({"resolution": "unresolved"},)},
            disagreements={},
        )
        self.assertEqual(found.kind, TAXONOMY_AMBIGUITY)

    def test_an_extra_category_on_a_non_author_claim_is_attribution(self) -> None:
        item = result(
            predicted=("market_prediction",),
            speakers=("third_party",),
        )
        found = classify(item, adjudication={}, disagreements={})
        self.assertEqual(found.kind, ATTRIBUTION_ERROR)

    def test_an_extra_category_on_an_author_claim_is_semantic(self) -> None:
        item = result(predicted=("market_prediction",), speakers=("author",))
        found = classify(item, adjudication={}, disagreements={})
        self.assertEqual(found.kind, SEMANTIC_GAP)

    def test_every_diagnosis_carries_a_detail(self) -> None:
        for item in analyse().diagnoses:
            self.assertTrue(item.detail)
            self.assertIn(item.kind, ERROR_KINDS)

    def test_no_diagnosis_is_unclassified(self) -> None:
        for item in analyse().diagnoses:
            self.assertIn(item.kind, ERROR_KINDS)


class AdversarialReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.analysis = analyse()

    def test_the_analysis_covers_every_case(self) -> None:
        self.assertEqual(len(self.analysis.results), 300)

    def test_every_failure_is_classified(self) -> None:
        failures = [item for item in self.analysis.results if not item.correct]
        self.assertEqual(len(self.analysis.diagnoses), len(failures))

    def test_the_counts_sum_to_the_failures(self) -> None:
        self.assertEqual(sum(self.analysis.counts().values()), len(self.analysis.diagnoses))

    def test_the_failure_rate_is_reported(self) -> None:
        self.assertGreater(self.analysis.failure_rate, 0.0)
        self.assertLess(self.analysis.failure_rate, 1.0)

    def test_the_language_breakdown_sums_to_the_total(self) -> None:
        total = sum(sum(row.values()) for row in self.analysis.by_language().values())
        self.assertEqual(total, len(self.analysis.diagnoses))

    def test_the_analysis_serialises(self) -> None:
        json.dumps(self.analysis.as_dict(), sort_keys=True)

    def test_the_artifact_is_written(self) -> None:
        self.assertTrue(ADVERSARIAL_PATH.is_file())
        payload = json.loads(ADVERSARIAL_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["failures"], len(self.analysis.diagnoses))

    def test_every_error_kind_appears_in_the_counts_even_at_zero(self) -> None:
        counts = self.analysis.counts()
        for kind in ERROR_KINDS:
            self.assertIn(kind, counts)

    def test_the_module_declares_its_precedence(self) -> None:
        described = describe_adversarial()
        self.assertIn("precedence", described)
        self.assertFalse(described["implements_any_proposal"])


class ProposalTests(unittest.TestCase):
    def test_there_is_a_proposal_for_every_class_that_occurred(self) -> None:
        analysis = analyse()
        kinds = {item.kind for item in analysis.diagnoses}
        covered = {item["kind"] for item in PROPOSALS}
        self.assertTrue(kinds <= covered, sorted(kinds - covered))

    def test_every_proposal_names_what_it_must_not_break(self) -> None:
        for item in PROPOSALS:
            self.assertTrue(item["must_not_break"], item["id"])
            self.assertTrue(item["proposal"], item["id"])
            self.assertTrue(item["evidence"], item["id"])

    def test_every_proposal_says_it_is_blocked_by_the_freeze(self) -> None:
        for item in PROPOSALS:
            self.assertIn("blocked_by", item, item["id"])

    def test_the_payload_reports_observed_cases_per_proposal(self) -> None:
        payload = proposal_payload(analyse())
        self.assertEqual(len(payload["proposals"]), len(PROPOSALS))
        for item in payload["proposals"]:
            self.assertIn("observed_cases", item)

    def test_the_payload_records_that_nothing_was_modified(self) -> None:
        payload = proposal_payload(analyse())
        self.assertFalse(payload["evaluator_modified"])
        self.assertIn("forbids changing", payload["note"])

    def test_the_proposals_artifact_is_written(self) -> None:
        self.assertTrue(PROPOSALS_PATH.is_file())
        payload = json.loads(PROPOSALS_PATH.read_text(encoding="utf-8"))
        self.assertFalse(payload["evaluator_modified"])


class CoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.matrix = build_coverage()

    def test_every_declared_dimension_is_reported(self) -> None:
        self.assertEqual(
            set(self.matrix.dimensions), {name for name, _ in DIMENSIONS}
        )

    def test_each_dimension_covers_every_case(self) -> None:
        for dimension in self.matrix.dimensions:
            total = sum(item.cases for item in self.matrix.for_dimension(dimension))
            self.assertEqual(total, 300, dimension)

    def test_both_languages_are_present(self) -> None:
        values = {item.value for item in self.matrix.for_dimension("language")}
        self.assertEqual(values, {"en", "zh"})

    def test_every_source_type_the_frame_declares_appears(self) -> None:
        values = {item.value for item in self.matrix.for_dimension("source_type")}
        self.assertEqual(len(values), 8)
        self.assertNotIn("(none)", values)

    def test_every_form_appears(self) -> None:
        values = {item.value for item in self.matrix.for_dimension("form")}
        self.assertEqual(len(values), 8)

    def test_a_cell_reports_accuracy_and_counts(self) -> None:
        cell = self.matrix.for_dimension("language")[0]
        self.assertEqual(cell.cases, cell.correct + (cell.cases - cell.correct))
        self.assertIn("accuracy", cell.as_dict())
        self.assertIn("recall", cell.as_dict())

    def test_the_matrix_serialises(self) -> None:
        json.dumps(self.matrix.as_dict(), sort_keys=True)

    def test_the_artifact_is_written(self) -> None:
        self.assertTrue(COVERAGE_PATH.is_file())

    def test_the_module_says_where_the_dimensions_come_from(self) -> None:
        described = describe_coverage()
        self.assertIn("frame block", described["source"])


class RegressionGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.gate = build_regression()

    def test_the_required_sets_are_all_present(self) -> None:
        names = {item.set_name for item in self.gate.sets}
        for name in REQUIRED_SETS:
            self.assertIn(name, names, name)

    def test_no_case_is_broken(self) -> None:
        self.assertEqual(self.gate.broken, ())
        self.assertEqual(self.gate.status, "PASS")

    def test_every_set_meets_its_floor(self) -> None:
        self.assertEqual(self.gate.floor_violations, ())

    def test_the_freeze_is_verified_by_the_gate(self) -> None:
        self.assertTrue(self.gate.freeze_verified)
        self.assertIn("frozen", self.gate.freeze_note)

    def test_the_phase_8_6_benchmark_is_reported(self) -> None:
        summary = self.gate.phase_8_6_v1
        self.assertEqual(summary["cases"], 100)
        self.assertGreater(summary["correct"], 90)

    def test_the_capability_set_is_included(self) -> None:
        self.assertIn(CAPABILITY_SET, REQUIRED_SETS)
        item = next(s for s in self.gate.sets if s.set_name == CAPABILITY_SET)
        self.assertEqual(item.cases, 80)
        self.assertEqual(item.broken, ())

    def test_the_gate_records_that_nothing_was_modified(self) -> None:
        self.assertFalse(self.gate.as_dict()["evaluator_modified"])

    def test_the_gate_serialises(self) -> None:
        json.dumps(self.gate.as_dict(), sort_keys=True)

    def test_the_artifact_is_written(self) -> None:
        self.assertTrue(REGRESSION_PATH.is_file())
        payload = json.loads(REGRESSION_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["broken_count"], 0)


class IsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = scan()

    def test_no_forbidden_import_is_present(self) -> None:
        self.assertEqual(self.report.violations, ())

    def test_every_package_file_is_scanned(self) -> None:
        self.assertGreaterEqual(self.report.files_scanned, 13)

    def test_the_evaluator_is_still_frozen(self) -> None:
        self.assertTrue(self.report.frozen_paths_ok)

    def test_the_status_is_pass(self) -> None:
        self.assertEqual(self.report.status, "PASS")

    def test_the_forbidden_prefixes_are_the_phases(self) -> None:
        for name in (
            "runtime",
            "production",
            "workflows",
            "plugins",
            "artifact",
            "multimodal_creator",
        ):
            self.assertIn(name, FORBIDDEN_PREFIXES)

    def test_changed_paths_detects_a_forbidden_path(self) -> None:
        found = changed_paths(
            [
                " M blank/workspace/risk_evaluation/v3/model.py",
                "?? blank/workspace/runtime/something.py",
                "?? blank/workspace/multimodal_creator/x/",
            ]
        )
        self.assertIn("blank/workspace/runtime/something.py", found)
        self.assertIn("blank/workspace/multimodal_creator/x/", found)

    def test_changed_paths_ignores_allowed_paths(self) -> None:
        found = changed_paths(
            [" M blank/workspace/risk_evaluation/v3_independent/freeze.py"]
        )
        self.assertEqual(found, ())

    def test_the_allowed_internal_prefixes_are_declared(self) -> None:
        self.assertIn("risk_evaluation", ALLOWED_INTERNAL_PREFIXES)

    def test_the_report_serialises(self) -> None:
        json.dumps(self.report.as_dict(), sort_keys=True)

    def test_the_module_describes_its_method(self) -> None:
        described = describe_isolation()
        self.assertIn("ast", described["method"])


if __name__ == "__main__":
    unittest.main()
