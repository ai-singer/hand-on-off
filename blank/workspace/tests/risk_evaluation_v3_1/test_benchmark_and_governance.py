"""Benchmark governance, evaluation and the frozen gate.

The two tests that matter most are the negative ones: that the audit reports
contamination when there is contamination, and that the gate reports a break when
one is injected. A governance suite that can only agree with itself would pass while
proving nothing.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from risk_evaluation.v3_repair.regression import BROKEN, FIXED, STILL_WRONG, UNCHANGED
from risk_evaluation.v3_validation.freeze import VERIFIED_KEYS, load_freeze
from risk_evaluation.v3_1 import audit as audit_module
from risk_evaluation.v3_1 import evaluation, regression
from risk_evaluation.v3_1.audit import (
    AUDIT_PATH,
    BLOCKING_KINDS,
    DISCLOSED_OVERLAP,
    FROZEN_PHASE_SOURCES,
    PRE_PUBLICATION_FINDINGS,
    UNVERIFIABLE_PROVENANCE,
    audit,
    failure_repository_texts,
    phase_8_8_sources,
    write_report as write_audit,
)
from risk_evaluation.v3_1.benchmark.cases import (
    ADVICE_BOUNDARY,
    BENCHMARK_ID,
    BENCHMARK_VERSION,
    CASES,
    CATEGORIES,
    DATASET_PATH,
    FROZEN_CASE_IDS,
    FROZEN_QUOTAS,
    GROUP_NAMES,
    MINIMUM_CASES,
    MODAL_PREDICTION,
    PROVENANCE,
    REGRESSION,
    SUBGROUP_SIZES,
    CapabilityCase,
    ClaimLabel,
    BenchmarkError,
    blind_records,
    case_index,
    category_counts,
    dataset_payload,
    group_cases,
    group_sizes,
    relation_counts,
    subgroup_cases,
    subgroup_sizes,
    verdict_counts,
    write_dataset,
)
from risk_evaluation.v3_1.evaluation import (
    ERROR_KINDS,
    ERRORS_PATH,
    METRICS_PATH,
    NO_ERROR,
    PREDICTION_PATH,
    analyse,
    diagnose,
    predict,
    score,
    write_error_analysis,
    write_metrics,
    write_predictions,
)
from risk_evaluation.v3_1.freeze import (
    BASELINE_PATH,
    CAPABILITY_MODULES,
    FREEZE_PATH,
    FREEZE_SCHEMA_VERSION,
    baseline_hash,
    build_capability_freeze,
    capability_hashes,
    capability_table_hash,
    describe as describe_freeze,
    load_baseline,
    load_capability_freeze,
    verify_baseline,
    verify_capability_freeze,
    write_capability_freeze,
)
from risk_evaluation.v3_1.regression import (
    CAPABILITY_SET,
    PHASE_8_7_FLOORS,
    REPORT_PATH,
    build_gate,
    dataset_hash,
    write_report as write_gate,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


class BenchmarkShapeTests(unittest.TestCase):
    def test_the_benchmark_meets_the_minimum_size(self) -> None:
        self.assertGreaterEqual(len(CASES), MINIMUM_CASES)
        self.assertEqual(len(CASES), 80)

    def test_the_groups_are_the_three_the_phase_names(self) -> None:
        self.assertEqual(
            group_sizes(),
            {MODAL_PREDICTION: 30, ADVICE_BOUNDARY: 30, REGRESSION: 20},
        )

    def test_every_subgroup_meets_its_declared_size(self) -> None:
        sizes = subgroup_sizes()
        for name, target in SUBGROUP_SIZES.items():
            self.assertEqual(sizes[name], target, name)

    def test_the_frozen_quotas_are_met_one_per_phase(self) -> None:
        frozen = group_cases(REGRESSION)
        by_phase: dict[str, int] = {}
        for case in frozen:
            by_phase[case.frozen_phase] = by_phase.get(case.frozen_phase, 0) + 1
        self.assertEqual(by_phase, dict(FROZEN_QUOTAS))

    def test_every_frozen_case_declares_its_phase(self) -> None:
        for case in group_cases(REGRESSION):
            self.assertTrue(case.frozen_phase, case.case_id)
            self.assertIn(case.frozen_phase, FROZEN_QUOTAS, case.case_id)

    def test_authored_cases_declare_a_verdict_and_frozen_ones_do_not(self) -> None:
        for case in CASES:
            if case.group == REGRESSION:
                self.assertEqual(case.expected_verdict, "", case.case_id)
            else:
                self.assertTrue(case.expected_verdict, case.case_id)

    def test_case_ids_are_unique(self) -> None:
        ids = [case.case_id for case in CASES]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(case_index()), len(CASES))

    def test_every_authored_case_cites_a_guide_section(self) -> None:
        """Group C's basis is its frozen source, not the guide, and that is the point."""

        for case in CASES:
            if case.group == REGRESSION:
                self.assertIn(case.frozen_phase, case.basis, case.case_id)
            else:
                self.assertIn("guide", case.basis.lower(), case.case_id)

    def test_every_case_labels_its_claims(self) -> None:
        for case in CASES:
            self.assertTrue(case.claims, case.case_id)
            self.assertEqual(len(case.expected_speakers), len(case.claims))

    def test_authored_and_frozen_cases_are_separable(self) -> None:
        authored = [case for case in CASES if case.group != REGRESSION]
        self.assertEqual(len(authored), 60)
        self.assertEqual(sum(len(c.expected_verdict) > 0 for c in authored), 60)

    def test_the_category_and_relation_counts_are_reported(self) -> None:
        counts = category_counts()
        self.assertIn("market_prediction", counts)
        self.assertIn("investment_advice", counts)
        self.assertTrue(all(name in CATEGORIES for name in counts))
        relations = relation_counts()
        self.assertIn("PREDICTION", relations)
        self.assertIn("ADVICE", relations)

    def test_the_verdict_counts_cover_both_capabilities(self) -> None:
        counts = verdict_counts()
        self.assertGreater(counts["prediction"], 0)
        self.assertGreater(counts["advice"], 0)
        self.assertGreater(counts["weak_prediction"], 0)

    def test_an_unknown_group_is_rejected(self) -> None:
        with self.assertRaises(BenchmarkError):
            group_cases("sentiment")

    def test_an_unknown_subgroup_is_rejected(self) -> None:
        with self.assertRaises(BenchmarkError):
            subgroup_cases("vibes")

    def test_a_bad_label_is_rejected(self) -> None:
        with self.assertRaises(BenchmarkError):
            ClaimLabel("nobody", "endorsed")
        with self.assertRaises(BenchmarkError):
            ClaimLabel("author", "shrugged")
        with self.assertRaises(BenchmarkError):
            ClaimLabel("author", "endorsed", "VIBES")

    def test_a_case_without_a_basis_is_rejected(self) -> None:
        with self.assertRaises(BenchmarkError):
            CapabilityCase(
                case_id="X-1",
                group=MODAL_PREDICTION,
                subgroup="strong_prediction",
                text="text",
                expected_categories=(),
                claims=(ClaimLabel("author", "endorsed"),),
                basis=" ",
            )


class ProvenanceTests(unittest.TestCase):
    def test_the_provenance_declares_synthetic_and_not_independent(self) -> None:
        self.assertTrue(PROVENANCE["synthetic"])
        self.assertFalse(PROVENANCE["independent"])

    def test_the_provenance_explains_why_independence_is_absent(self) -> None:
        note = PROVENANCE["independent_note"]
        self.assertIn("same author", note)
        self.assertIn("74.0%", note)
        self.assertIn("67.5%", note)

    def test_the_provenance_records_author_time_and_source(self) -> None:
        for key in ("author", "generated_at", "source", "annotation", "guide", "protocol"):
            self.assertTrue(PROVENANCE[key], key)

    def test_the_provenance_names_the_label_sources_per_group(self) -> None:
        self.assertEqual(
            set(PROVENANCE["label_sources"]), {"A", "B", "C"}
        )

    def test_single_annotator_status_is_declared(self) -> None:
        self.assertEqual(
            PROVENANCE["annotation"], "single-annotator engineering validation only"
        )

    def test_the_dataset_artifact_carries_the_provenance(self) -> None:
        payload = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["provenance"]["independent"], False)
        self.assertEqual(payload["case_count"], len(CASES))

    def test_the_dataset_file_matches_the_cases(self) -> None:
        payload = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["cases"]), len(CASES))
        self.assertEqual(payload["benchmark"], f"{BENCHMARK_ID}/{BENCHMARK_VERSION}")

    def test_writing_the_dataset_is_reproducible(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "d.json"
            write_dataset(target)
            first = target.read_text(encoding="utf-8")
            write_dataset(target)
            self.assertEqual(first, target.read_text(encoding="utf-8"))

    def test_the_payload_is_json_serializable(self) -> None:
        json.dumps(dataset_payload(), sort_keys=True)


class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit()

    def test_the_audit_covers_every_case(self) -> None:
        self.assertEqual(self.report.case_count, len(CASES))

    def test_the_audit_checks_the_historical_sources(self) -> None:
        self.assertGreaterEqual(len(self.report.sources_checked), 15)
        self.assertIn("phase-8.6/independent_v1", self.report.sources_checked)
        self.assertIn("phase-8.1/failure-repository", self.report.sources_checked)

    def test_the_authored_cases_are_not_contaminated(self) -> None:
        """The check the first run failed, on `MP-A2-08`."""

        authored = {
            item.case_id
            for item in self.report.blocking
            for item in [item]
            if case_index()[item.case_ids[0]].group != REGRESSION
        }
        self.assertEqual(authored, set())
        self.assertEqual(self.report.status, "PASS")

    def test_no_blocking_finding_remains(self) -> None:
        self.assertEqual(self.report.blocking, ())
        self.assertEqual(self.report.affected_case_ids, ())

    def test_every_blocking_kind_is_declared(self) -> None:
        self.assertIn(UNVERIFIABLE_PROVENANCE, BLOCKING_KINDS)
        for item in self.report.blocking:
            self.assertIn(item.kind, BLOCKING_KINDS, item.kind)

    def test_the_frozen_cases_are_disclosed_rather_than_blocking(self) -> None:
        self.assertTrue(self.report.disclosed)
        for item in self.report.disclosed:
            self.assertEqual(
                case_index()[item.case_ids[0]].group, REGRESSION, item.case_ids
            )

    def test_a_synthetic_overlap_is_detected_and_blocks(self) -> None:
        """The audit must be able to fail on an authored case.

        The text is `IV-001`'s, which is in the historical sources, presented as a
        new authored case. That is exactly what `MP-A2-08` was.
        """

        from risk_evaluation.v3_1.benchmark.cases import ClaimLabel as Label

        contaminated = CapabilityCase(
            case_id="X-1",
            group=MODAL_PREDICTION,
            subgroup="strong_prediction",
            text="Your money is guaranteed to be returned in full.",
            expected_categories=("financial_guarantee",),
            claims=(Label("author", "endorsed", "GUARANTEE"),),
            basis="guide 7",
            expected_verdict="prediction",
        )
        report = audit((contaminated,))

        self.assertEqual(report.status, "FAIL")
        self.assertTrue(report.blocking)
        self.assertIn("X-1", report.affected_case_ids)

    def test_an_authored_case_matching_the_benchmark_blocks(self) -> None:
        """Two authored cases repeating each other is contamination too."""

        from risk_evaluation.v3_1.benchmark.cases import ClaimLabel as Label

        twin = CapabilityCase(
            case_id="X-2",
            group=MODAL_PREDICTION,
            subgroup="strong_prediction",
            text=case_index()["MP-A1-01"].text,
            expected_categories=("market_prediction",),
            claims=(Label("author", "endorsed", "PREDICTION"),),
            basis="guide 2",
            expected_verdict="prediction",
        )
        report = audit((twin, case_index()["MP-A1-01"]))

        self.assertEqual(report.status, "FAIL")
        self.assertTrue(report.blocking)
        self.assertTrue(
            all(item.kind == "exact_overlap" for item in report.blocking),
            [item.kind for item in report.blocking],
        )

    def test_an_unverifiable_provenance_is_detected_and_blocks(self) -> None:
        from risk_evaluation.v3_1.benchmark.cases import ClaimLabel as Label

        invented = CapabilityCase(
            case_id="C-1",
            group=REGRESSION,
            subgroup="frozen",
            text="A sentence that appears in no frozen set whatsoever.",
            expected_categories=(),
            claims=(Label("unknown", "uncertain"),),
            basis="phase-8.6: label copied from the frozen source, not re-annotated",
            frozen_phase="phase-8.6",
        )
        report = audit((invented,))

        self.assertEqual(report.status, "FAIL")
        self.assertEqual(
            [item.kind for item in report.blocking], [UNVERIFIABLE_PROVENANCE]
        )

    def test_an_unknown_frozen_phase_has_no_declared_sources(self) -> None:
        self.assertEqual(FROZEN_PHASE_SOURCES.get("phase-9.9"), None)
        for phase, sources in FROZEN_PHASE_SOURCES.items():
            self.assertTrue(sources, phase)

    def test_the_pre_publication_finding_is_recorded(self) -> None:
        """The phase forbids deleting a contaminated case, so the finding is kept."""

        self.assertEqual(len(PRE_PUBLICATION_FINDINGS), 1)
        finding = PRE_PUBLICATION_FINDINGS[0]
        self.assertEqual(finding["case_id"], "MP-A2-08")
        self.assertIn("IV-098", finding["why"])
        self.assertIn("rewritten", finding["resolution"])

    def test_the_rewritten_case_is_the_one_now_in_the_benchmark(self) -> None:
        case = case_index()["MP-A2-08"]
        self.assertEqual(case.text, PRE_PUBLICATION_FINDINGS[0]["replacement_text"])
        self.assertNotEqual(case.text, PRE_PUBLICATION_FINDINGS[0]["original_text"])
        self.assertIn("contamination audit", case.note)

    def test_the_failure_repository_is_an_audit_source(self) -> None:
        self.assertTrue(failure_repository_texts())
        self.assertIn(
            "phase-8.1/failure-repository", phase_8_8_sources()
        )

    def test_the_finding_kinds_are_reported_even_when_zero(self) -> None:
        counts = self.report.counts()
        self.assertIn(DISCLOSED_OVERLAP, counts)
        self.assertTrue(all(name in counts for name in BLOCKING_KINDS))

    def test_the_audit_report_artifact_is_written(self) -> None:
        self.assertTrue(AUDIT_PATH.is_file())
        payload = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))

        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["blocking_findings"], 0)
        self.assertIn("pre_publication_findings", payload)
        self.assertIn("forbids deleting a contaminated case", payload["note"])

    def test_writing_the_audit_is_reproducible(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "a.json"
            write_audit(target, report=self.report)
            first = target.read_text(encoding="utf-8")
            write_audit(target, report=self.report)
            self.assertEqual(first, target.read_text(encoding="utf-8"))

    def test_the_audit_is_json_serializable(self) -> None:
        json.dumps(self.report.as_dict(), sort_keys=True)


class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.metrics = score(predict(blind_records()))

    def test_every_case_is_scored(self) -> None:
        self.assertEqual(self.metrics.decision.cases, len(CASES))

    def test_the_capability_verdict_is_scored_on_every_authored_case(self) -> None:
        self.assertEqual(len(self.metrics.verdict.scored), 60)
        self.assertEqual(self.metrics.verdict.accuracy, 1.0)

    def test_relations_are_scored_only_where_they_are_labelled(self) -> None:
        """Group C's 8.1 and 8.3 cases label a category and no relation."""

        self.assertEqual(self.metrics.relation.predicted_total, self.metrics.relation.recalled)
        self.assertEqual(self.metrics.relation.precision, 1.0)

    def test_no_false_positive_or_false_negative_remains(self) -> None:
        counts = self.metrics.decision.counts
        self.assertEqual(counts["fp"], 0)
        self.assertEqual(counts["fn"], 0)
        self.assertEqual(self.metrics.decision.precision, 1.0)
        self.assertEqual(self.metrics.decision.recall, 1.0)

    def test_the_per_category_metrics_are_reported_separately(self) -> None:
        rows = self.metrics.decision.per_category()
        self.assertEqual(len(rows), len(CATEGORIES))
        for row in rows:
            payload = row.as_dict()
            self.assertEqual(
                set(payload), {"category", "tp", "fp", "fn", "precision", "recall", "f1"}
            )
            self.assertEqual(payload["tp"] + payload["fn"], sum(
                1
                for item in self.metrics.outcomes
                if row.category in item.case.expected_categories
            ))

    def test_the_two_capability_categories_are_perfect_on_this_benchmark(self) -> None:
        by_name = {row.category: row for row in self.metrics.decision.per_category()}
        for name in ("market_prediction", "investment_advice"):
            self.assertEqual(by_name[name].precision, 1.0, name)
            self.assertEqual(by_name[name].recall, 1.0, name)

    def test_the_metrics_are_not_a_single_f1(self) -> None:
        payload = self.metrics.as_dict()
        for family in ("verdict", "relation", "decision", "trace"):
            self.assertIn(family, payload)
        self.assertIn("per_category", payload["decision"])
        self.assertIn("per_group", payload["decision"])
        self.assertIn("per_subgroup", payload["decision"])

    def test_the_verdict_is_reported_per_capability(self) -> None:
        per_group = self.metrics.verdict.per_group()
        self.assertIn(MODAL_PREDICTION, per_group)
        self.assertIn(ADVICE_BOUNDARY, per_group)
        self.assertEqual(per_group[MODAL_PREDICTION]["accuracy"], 1.0)
        self.assertEqual(per_group[ADVICE_BOUNDARY]["accuracy"], 1.0)

    def test_the_trace_is_complete_and_carries_signals(self) -> None:
        trace = self.metrics.trace
        self.assertEqual(trace.claim_evidence_rate, 1.0)
        self.assertGreater(trace.claims_with_signals, 0)
        self.assertEqual(trace.claims_with_capability_verdicts, trace.claims)

    def test_every_failure_is_classified(self) -> None:
        analysis = analyse(self.metrics.outcomes)
        self.assertTrue(all(item.kind in ERROR_KINDS for item in analysis.diagnoses))
        self.assertEqual(analysis.unclassified(), ())

    def test_the_one_failure_is_an_annotation_issue(self) -> None:
        """Not a detector defect: the baseline finds what the label does not name."""

        analysis = analyse(self.metrics.outcomes)
        self.assertEqual(len(analysis.diagnoses), 1)
        self.assertEqual(analysis.diagnoses[0].case_id, "83-ATT-01")
        self.assertEqual(analysis.diagnoses[0].kind, "annotation_issue")
        self.assertEqual(analysis.diagnoses[0].mechanism, "label-omits-category")

    def test_a_passing_case_is_not_diagnosed(self) -> None:
        passing = [
            item for item in self.metrics.outcomes if item.correct and item.verdict_correct is not False
        ]
        self.assertTrue(passing)
        for item in passing[:10]:
            self.assertIsNone(diagnose(item))

    def test_the_error_kind_counts_include_every_kind(self) -> None:
        analysis = analyse(self.metrics.outcomes)
        counts = analysis.counts()
        for kind in (*ERROR_KINDS, NO_ERROR):
            self.assertIn(kind, counts)

    def test_the_metrics_artifact_is_written(self) -> None:
        self.assertTrue(METRICS_PATH.is_file())
        payload = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["cases"]), len(CASES))
        self.assertIn("synthetic", payload["note"])
        self.assertIn("error_analysis", payload)

    def test_the_prediction_artifact_carries_no_labels(self) -> None:
        payload = json.loads(PREDICTION_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["mode"], "blind")
        self.assertEqual(len(payload["predictions"]), len(CASES))
        self.assertNotIn("expected_categories", json.dumps(payload["predictions"]))

    def test_the_error_artifact_is_written(self) -> None:
        self.assertTrue(ERRORS_PATH.is_file())
        payload = json.loads(ERRORS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["unclassified"], 0)

    def test_the_blind_records_carry_only_id_and_text(self) -> None:
        for record in blind_records():
            self.assertEqual(set(record), {"id", "text"})

    def test_writing_the_artifacts_is_reproducible(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "m.json"
            write_metrics(target, metrics=self.metrics)
            first = target.read_text(encoding="utf-8")
            write_metrics(target, metrics=self.metrics)
            self.assertEqual(first, target.read_text(encoding="utf-8"))

    def test_scoring_is_reproducible(self) -> None:
        again = score(predict(blind_records()))
        self.assertEqual(again.as_dict(), self.metrics.as_dict())

    def test_a_blind_record_missing_a_field_is_rejected(self) -> None:
        with self.assertRaises(evaluation.EvaluationError):
            predict([{"id": "X-1"}])

    def test_render_states_all_four_families(self) -> None:
        rendered = self.metrics.render()
        for token in ("capability verdicts", "relations", "decisions", "per category", "trace"):
            self.assertIn(token, rendered)


class RegressionGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.gate = build_gate()

    def test_the_gate_covers_six_sets(self) -> None:
        self.assertEqual(len(self.gate.sets), 6)
        self.assertEqual(self.gate.sets[-1].set_name, CAPABILITY_SET)

    def test_no_case_is_broken(self) -> None:
        """The phase's release condition, as an assertion."""

        self.assertEqual(self.gate.broken, ())
        self.assertEqual(self.gate.status, "PASS")

    def test_the_phase_8_7_sets_are_at_or_above_their_floors(self) -> None:
        self.assertEqual(self.gate.floor_violations, {})
        for name, floor in PHASE_8_7_FLOORS.items():
            summary = self.gate.phase_8_7.summary_for(name)
            self.assertGreaterEqual(summary.v3_correct, floor, name)

    def test_the_three_way_comparison_is_reported(self) -> None:
        for item in self.gate.sets:
            payload = item.as_dict()
            for key in ("fixed", "broken", "unchanged", "still_right", "still_wrong"):
                self.assertIn(key, payload)
            self.assertEqual(
                len(item.unchanged), len(item.still_right) + len(item.still_wrong)
            )

    def test_fixed_broken_and_unchanged_partition_every_case(self) -> None:
        for item in self.gate.sets:
            self.assertEqual(
                len(item.fixed) + len(item.broken) + len(item.unchanged), item.cases
            )

    def test_the_replay_sets_did_not_move(self) -> None:
        for name in ("phase_8.1", "phase_8.3", "phase_8.4"):
            item = next(s for s in self.gate.sets if s.set_name == name)
            self.assertEqual(item.fixed, (), name)
            self.assertEqual(item.broken, (), name)
            self.assertEqual(item.still_right and True, True, name)

    def test_phase_8_6_improved_on_phase_8_7(self) -> None:
        item = next(s for s in self.gate.sets if s.set_name == "phase_8.6_independent_v2")
        self.assertEqual(item.v3_correct, 98)
        self.assertIn("IV-072", item.fixed)
        self.assertIn("IV-089", item.fixed)

    def test_the_gate_reports_a_break_when_one_is_injected(self) -> None:
        """A gate that cannot fail is not a gate. Injected into the real suite."""

        from risk_evaluation.v3_repair.regression import (
            CaseRecord,
            RegressionReport,
            summarise,
        )

        injected = CaseRecord(
            set_name="phase_8.5",
            case_id="INJECTED",
            text="Anything at all.",
            expected=("investment_advice",),
            baseline=(),
            v3=(),
            pre_repair=("investment_advice",),
        )
        records = (*self.gate.phase_8_7.records, injected)
        report = RegressionReport(records=records, summaries=summarise(records))
        gate = build_gate(report=report)

        self.assertIn("INJECTED", gate.broken)
        self.assertEqual(gate.status, "FAIL")
        self.assertFalse(gate.passed)

    def test_a_missing_set_is_reported_as_broken_rather_than_skipped(self) -> None:
        from risk_evaluation.v3_repair.regression import RegressionReport, summarise

        empty = RegressionReport(records=(), summaries=summarise(()))
        gate = build_gate(report=empty)

        self.assertFalse(gate.passed)
        self.assertTrue(any("MISSING" in item for item in gate.broken))

    def test_the_gate_reports_a_floor_violation(self) -> None:
        gate = build_gate(floors={"phase_8.5": 99})
        self.assertIn("phase_8.5", gate.floor_violations)
        self.assertEqual(gate.status, "FAIL")

    def test_the_capability_set_was_scored(self) -> None:
        item = next(s for s in self.gate.sets if s.set_name == CAPABILITY_SET)
        self.assertEqual(item.cases, len(CASES))
        self.assertGreater(item.v3_correct, item.pre_repair_correct)
        self.assertEqual(item.broken, ())

    def test_the_report_artifact_is_written(self) -> None:
        self.assertTrue(REPORT_PATH.is_file())
        payload = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["broken_count"], 0)
        self.assertEqual(payload["dataset_hash"], dataset_hash())

    def test_writing_the_gate_is_reproducible(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "g.json"
            write_gate(target, gate=self.gate)
            first = target.read_text(encoding="utf-8")
            write_gate(target, gate=self.gate)
            self.assertEqual(first, target.read_text(encoding="utf-8"))

    def test_the_gate_is_json_serializable(self) -> None:
        json.dumps(self.gate.as_dict(), sort_keys=True)

    def test_the_gate_names_why_broken_is_measured_against_phase_8_7(self) -> None:
        self.assertIn("Phase 8.7", self.gate.as_dict()["note"])


class FreezeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frozen = load_capability_freeze()

    def test_the_baseline_freeze_exists_and_is_a_pre_change_record(self) -> None:
        self.assertTrue(BASELINE_PATH.is_file())
        baseline = load_baseline()
        self.assertEqual(baseline["kind"], "pre-change baseline")
        self.assertIn("8b627c8", baseline["taken_on"])
        self.assertIn("clean working tree", baseline["taken_on"])

    def test_the_baseline_carries_all_five_components(self) -> None:
        baseline = load_baseline()
        for key in VERIFIED_KEYS:
            self.assertIn(key, baseline, key)
        self.assertTrue(baseline["phase_8_7_regression"]["reproducible"])

    def test_no_inherited_component_moved(self) -> None:
        """The capability is additive: the pattern set and the policy are unchanged."""

        result = verify_baseline()
        self.assertTrue(result.matches, result.render())
        self.assertEqual(result.moved, ())

    def test_the_phase_8_6_benchmark_hash_is_untouched(self) -> None:
        phase_86 = load_freeze()
        self.assertEqual(self.frozen["benchmark_hash"], phase_86["benchmark_hash"])
        self.assertEqual(phase_86["benchmark"], "independent_v1/v1")
        self.assertEqual(self.frozen["capability_benchmark"], f"{BENCHMARK_ID}/{BENCHMARK_VERSION}")

    def test_the_two_benchmark_hashes_are_distinct_keys(self) -> None:
        """A collision here would overwrite the evidence that labels are untouched."""

        self.assertNotEqual(
            self.frozen["benchmark_hash"], self.frozen["capability_benchmark_hash"]
        )
        self.assertEqual(
            self.frozen["capability_benchmark_hash"], dataset_hash()
        )

    def test_the_decision_policy_is_unchanged(self) -> None:
        phase_87 = json.loads(
            (
                WORKSPACE_ROOT
                / "risk_evaluation/v3_repair/evaluation_freeze_v3_repair.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            self.frozen["decision_policy_hash"], phase_87["decision_policy_hash"]
        )

    def test_only_what_this_phase_added_is_frozen_beyond_the_five(self) -> None:
        self.assertEqual(
            self.frozen["capability_table_hash"], capability_table_hash()
        )
        self.assertEqual(self.frozen["baseline_hash"], baseline_hash())

    def test_every_capability_module_is_frozen(self) -> None:
        self.assertEqual(set(self.frozen["capability_hashes"]), set(CAPABILITY_MODULES))
        for name, digest in self.frozen["capability_hashes"].items():
            self.assertEqual(len(digest), 64, name)
            int(digest, 16)
        self.assertEqual(self.frozen["capability_hashes"], capability_hashes())

    def test_the_freeze_records_the_gate(self) -> None:
        self.assertEqual(self.frozen["gate"]["status"], "PASS")
        self.assertEqual(self.frozen["gate"]["broken"], [])
        self.assertEqual(self.frozen["gate"]["sets"], 6)

    def test_the_freeze_records_the_benchmark_provenance(self) -> None:
        self.assertFalse(self.frozen["benchmark_provenance"]["independent"])
        self.assertEqual(self.frozen["capability_case_count"], len(CASES))
        self.assertEqual(self.frozen["minimum_cases"], MINIMUM_CASES)

    def test_the_freeze_matches_the_tree(self) -> None:
        result = verify_capability_freeze()
        self.assertTrue(result.matches, result.render())
        self.assertEqual(result.gate_status, "PASS")

    def test_it_is_a_new_version_that_supersedes_two_others(self) -> None:
        self.assertEqual(
            self.frozen["freeze_schema_version"], FREEZE_SCHEMA_VERSION
        )
        self.assertEqual(
            set(self.frozen["supersedes"]), {"phase_8_6", "phase_8_7"}
        )

    def test_a_tampered_capability_hash_is_detected(self) -> None:
        import tempfile

        tampered = dict(self.frozen)
        tampered["capability_hashes"] = dict(
            tampered["capability_hashes"], modal="0" * 64
        )
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "f.json"
            target.write_text(json.dumps(tampered), encoding="utf-8")
            result = verify_capability_freeze(target)

        self.assertFalse(result.matches)
        self.assertIn("capability_hashes.modal", result.mismatches)

    def test_a_moved_gate_status_is_detected(self) -> None:
        import tempfile

        tampered = dict(self.frozen)
        tampered["gate"] = dict(tampered["gate"], status="FAIL")
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "f.json"
            target.write_text(json.dumps(tampered), encoding="utf-8")
            result = verify_capability_freeze(target)

        self.assertFalse(result.matches)
        self.assertIn("gate.status", result.mismatches)

    def test_building_twice_gives_the_same_hashes(self) -> None:
        first = {k: v for k, v in build_capability_freeze().items() if k != "timestamp"}
        second = {k: v for k, v in build_capability_freeze().items() if k != "timestamp"}
        self.assertEqual(first, second)

    def test_a_missing_freeze_is_reported(self) -> None:
        import tempfile

        with self.assertRaises(Exception):
            load_capability_freeze(Path(tempfile.gettempdir()) / "no-such-v3-1.json")

    def test_writing_is_reproducible(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "f.json"
            write_capability_freeze(target)
            first = json.loads(target.read_text(encoding="utf-8"))
            write_capability_freeze(target)
            second = json.loads(target.read_text(encoding="utf-8"))

        self.assertEqual(first["capability_hashes"], second["capability_hashes"])

    def test_the_freeze_describes_its_own_components(self) -> None:
        described = describe_freeze()
        self.assertIn("baseline_hash", described["components"])
        self.assertIn("capability_benchmark_hash", described["components"])

    def test_the_freeze_is_json_serializable(self) -> None:
        json.dumps(self.frozen, sort_keys=True)


class IsolationTests(unittest.TestCase):
    def test_the_test_package_does_not_shadow_a_workspace_package(self) -> None:
        top_level = {
            path.name
            for path in WORKSPACE_ROOT.iterdir()
            if path.is_dir() and (path / "__init__.py").is_file()
        }
        self.assertNotIn("risk_evaluation_v3_1", top_level)

    def test_the_capability_package_is_inside_risk_evaluation(self) -> None:
        import risk_evaluation.v3_1 as package

        path = Path(package.__file__).resolve()
        self.assertTrue(path.is_relative_to(WORKSPACE_ROOT / "risk_evaluation"))
        self.assertEqual(path.parent.name, "v3_1")

    def test_v3_1_does_not_import_production_paths(self) -> None:
        import ast

        package = WORKSPACE_ROOT / "risk_evaluation/v3_1"
        forbidden = (
            "production",
            "runtime",
            "workflows",
            "artifact",
            "multimodal_creator",
        )
        for path in sorted(package.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for name in names:
                    for banned in forbidden:
                        self.assertNotIn(
                            f".{banned}", name, f"{path.name}: {name}"
                        )


if __name__ == "__main__":
    unittest.main()
