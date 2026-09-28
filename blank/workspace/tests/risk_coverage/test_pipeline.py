"""The pipeline: the six stages, the Phase 8.9 figures, and the artifacts.

The figures asserted here are the Phase 8.9 ones the phase reports. They are asserted
rather than restated because this framework's whole claim is that it changed none of
them — if they ever differ, this test is the alarm, and it is the source that is wrong.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from risk_evaluation.coverage import analyzer, freeze, generator, pipeline, registry
from risk_evaluation.coverage.model import (
    PENDING,
    CoverageCandidate,
    GeneratedCase,
    RegressionCandidate,
)
from risk_evaluation.coverage.pipeline import (
    ARTIFACTS,
    PACKAGE_DIR,
    Run,
)
from risk_evaluation.coverage.taxonomy import FAILURE_TYPES

from ._support import analysis, candidates, generated, metrics


def snapshot_package_artifacts() -> dict[str, tuple[int, int]]:
    """Size and mtime of every artifact-shaped file in the package directory."""

    out: dict[str, tuple[int, int]] = {}
    for pattern in ("*.json", "*.md", "**/*.json"):
        for path in PACKAGE_DIR.glob(pattern):
            if path.is_file():
                out[str(path.relative_to(PACKAGE_DIR))] = (
                    path.stat().st_mtime_ns,
                    path.stat().st_size,
                )
    return out


class DescribeTest(unittest.TestCase):
    def test_describe_states_the_six_stages_in_order(self) -> None:
        self.assertEqual(
            pipeline.describe()["stages"],
            [
                "failure-generator",
                "risk-evaluator",
                "failure-analyzer",
                "coverage-expansion-candidate",
                "human-review-queue",
                "regression-dataset",
            ],
        )

    def test_every_guarantee_is_false(self) -> None:
        guarantees = pipeline.describe()["guarantees"]
        self.assertTrue(guarantees)
        for name, value in guarantees.items():
            with self.subTest(guarantee=name):
                self.assertIs(value, False)

    def test_the_guarantees_cover_the_prohibitions_the_phase_states(self) -> None:
        guarantees = pipeline.describe()["guarantees"]
        for name in (
            "modifies_evaluator",
            "modifies_benchmark_labels",
            "modifies_decision_policy",
            "writes_to_accepted",
            "uses_network",
            "uses_llm",
            "reaches_production",
        ):
            with self.subTest(guarantee=name):
                self.assertIn(name, guarantees)

    def test_describe_lists_the_four_artifacts(self) -> None:
        self.assertEqual(pipeline.describe()["artifacts"], list(ARTIFACTS))
        self.assertEqual(
            list(ARTIFACTS),
            [
                "failure_analysis_r1.json",
                "generated_cases/generated_cases_r1.json",
                "regression_candidates.json",
                "coverage_freeze_r1.json",
            ],
        )

    def test_describe_reports_the_taxonomy_split(self) -> None:
        body = pipeline.describe()
        self.assertEqual(body["failure_types"], list(FAILURE_TYPES))
        self.assertEqual(
            set(body["auto_generatable"]) | set(body["human_required"]),
            set(FAILURE_TYPES),
        )

    def test_describe_embeds_the_stage_descriptions(self) -> None:
        body = pipeline.describe()
        self.assertEqual(body["generator"]["cases"], len(generated()))
        self.assertEqual(body["registry"]["writes_accepted"], False)
        self.assertTrue(body["lexicon"]["known_words"])


class MetricsTest(unittest.TestCase):
    """The frozen evaluator's own Phase 8.9 scores, unchanged by this phase."""

    def test_the_benchmark_identity(self) -> None:
        self.assertEqual(metrics()["benchmark"], "risk/independent")
        self.assertEqual(metrics()["benchmark_version"], "v1")
        self.assertEqual(metrics()["cases"], 300)

    def test_the_primary_precision_is_the_phase_figure(self) -> None:
        self.assertEqual(metrics()["precision"], 0.9062)

    def test_the_primary_recall_is_the_phase_figure(self) -> None:
        self.assertEqual(metrics()["recall"], 0.1758)

    def test_the_primary_f1_is_the_phase_figure(self) -> None:
        self.assertEqual(metrics()["f1"], 0.2945)

    def test_the_primary_accuracy_is_the_phase_figure(self) -> None:
        self.assertEqual(metrics()["accuracy"], 0.4949)

    def test_the_confusion_matrix_is_the_phase_figure(self) -> None:
        self.assertEqual(
            metrics()["confusion"], {"tp": 29, "fp": 3, "fn": 136, "tn": 129}
        )

    def test_the_primary_scope_excludes_the_three_unresolved_cases(self) -> None:
        self.assertEqual(metrics()["scope"], "resolved")
        self.assertEqual(metrics()["scored_cases"], 297)
        self.assertEqual(
            sorted(metrics()["unresolved_cases"]), ["IND-0150", "IND-0156", "IND-0299"]
        )

    def test_the_confusion_matrix_agrees_with_the_scored_case_count(self) -> None:
        confusion = metrics()["confusion"]
        self.assertEqual(confusion["tp"] + confusion["fp"], 29 + 3)
        self.assertEqual(
            sum(confusion.values()), metrics()["scored_cases"]
        )

    def test_the_relation_metrics_are_carried_too(self) -> None:
        relation = metrics()["relation"]
        for key in ("tp", "fp", "fn", "tn", "precision", "recall", "f1"):
            with self.subTest(key=key):
                self.assertIn(key, relation)


class AnalysisTest(unittest.TestCase):
    def test_the_analysis_scores_all_three_hundred_cases(self) -> None:
        self.assertEqual(analysis().cases, 300)

    def test_the_analysis_finds_the_phase_failure_count(self) -> None:
        self.assertEqual(analysis().count, 151)

    def test_the_failure_rate_matches_the_count(self) -> None:
        self.assertEqual(analysis().failure_rate, round(151 / 300, 4))

    def test_every_failure_disagrees_with_its_label(self) -> None:
        for record in analysis().failures:
            with self.subTest(case=record.case_id):
                self.assertNotEqual(set(record.expected), set(record.actual))

    def test_every_failure_has_a_missing_or_an_extra_category(self) -> None:
        for record in analysis().failures:
            with self.subTest(case=record.case_id):
                self.assertTrue(
                    record.missing or record.extra,
                    "a failure with no difference in either direction is not a failure",
                )

    def test_every_failure_record_carries_evidence(self) -> None:
        for record in analysis().failures:
            with self.subTest(case=record.case_id):
                self.assertTrue(record.evidence)

    def test_every_failure_type_is_one_the_taxonomy_declares(self) -> None:
        for record in analysis().failures:
            with self.subTest(case=record.case_id):
                self.assertIn(record.failure_type, FAILURE_TYPES)

    def test_every_failure_carries_the_evidence_its_rule_requires(self) -> None:
        for record in analysis().failures:
            names = {item.name for item in record.evidence}
            with self.subTest(case=record.case_id):
                self.assertTrue(set(record.required_evidence) <= names)

    def test_the_distribution_uses_every_type_the_failures_carry(self) -> None:
        self.assertEqual(
            set(analysis().types()),
            {record.failure_type for record in analysis().failures},
        )

    def test_the_largest_type_is_a_vocabulary_gap(self) -> None:
        ordered = sorted(analysis().types().items(), key=lambda item: (-item[1], item[0]))
        self.assertEqual(ordered[0][0], "LEXICAL_GAP")
        self.assertGreater(ordered[0][1], ordered[1][1])

    def test_the_census_counts_the_evidence_signals(self) -> None:
        census = analyzer.census(analysis()).as_dict()
        self.assertEqual(census["failures"], 151)
        self.assertEqual(census["cases"], 300)
        self.assertGreater(census["no_hook_at_all"], 0)

    def test_the_summary_split_adds_up_to_the_failure_count(self) -> None:
        body = analyzer.summary(analysis())
        self.assertEqual(body["failures"], 151)
        self.assertEqual(
            body["auto_generatable"] + body["human_required"], body["failures"]
        )

    def test_the_payload_carries_the_three_freeze_digests(self) -> None:
        body = analyzer.payload(analysis())
        self.assertEqual(body["source_hash"], freeze.source_digest())
        self.assertEqual(body["benchmark_hash"], freeze.benchmark_digest())
        self.assertEqual(body["evaluator_hash"], freeze.evaluator_digest())

    def test_the_payload_states_that_nothing_was_modified(self) -> None:
        body = analyzer.payload(analysis())
        self.assertIn("no evaluator file", body["note"])
        self.assertEqual(body["phase"], "R1")


class ReadOnlyRunTest(unittest.TestCase):
    """A run with every write switched off must not touch anything."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name) / "run"
        cls.before = snapshot_package_artifacts()
        cls.pipeline_run = pipeline.run(
            output_dir=cls.root,
            write_artifacts=False,
            write_reports=False,
            freeze_run=False,
        )
        cls.after = snapshot_package_artifacts()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_the_run_scores_three_hundred_cases(self) -> None:
        self.assertEqual(self.pipeline_run.counts["cases"], 300)

    def test_the_run_finds_one_hundred_and_fifty_one_failures(self) -> None:
        self.assertEqual(self.pipeline_run.counts["failures"], 151)

    def test_the_run_builds_the_candidates_and_regression_proposals(self) -> None:
        self.assertEqual(self.pipeline_run.counts["candidates"], len(candidates()))
        self.assertEqual(self.pipeline_run.counts["generated"], len(generator.generate()))
        self.assertEqual(self.pipeline_run.counts["regression"], len(candidates()))
        self.assertEqual(self.pipeline_run.counts["rejected"], 0)

    def test_the_run_is_a_run(self) -> None:
        self.assertIsInstance(self.pipeline_run, Run)
        self.assertTrue(
            all(isinstance(item, GeneratedCase) for item in self.pipeline_run.cases)
        )
        self.assertTrue(
            all(isinstance(item, RegressionCandidate) for item in self.pipeline_run.regression)
        )

    def test_the_run_records_no_artifact_path(self) -> None:
        self.assertEqual(dict(self.pipeline_run.artifacts), {})

    def test_the_run_writes_nothing_into_the_output_directory(self) -> None:
        self.assertFalse(self.root.exists() and any(self.root.rglob("*")))

    def test_the_run_leaves_the_package_artifacts_untouched(self) -> None:
        self.assertEqual(self.after, self.before)

    def test_the_run_records_the_registry_policy(self) -> None:
        self.assertEqual(self.pipeline_run.registry.accepted, ())
        self.assertEqual(self.pipeline_run.registry.counts["accepted"], 0)

    def test_the_run_describes_itself(self) -> None:
        body = self.pipeline_run.describe()
        self.assertEqual(body["counts"], self.pipeline_run.counts)
        self.assertEqual(body["by_type"], dict(self.pipeline_run.analysis.types()))

    def test_the_run_leaves_the_frozen_digests_alone(self) -> None:
        report = freeze.guard()
        self.assertTrue(report.ok, report.mismatches)


class RegressionCandidateTest(unittest.TestCase):
    def test_every_proposal_is_pending(self) -> None:
        for item in pipeline.regression_candidates(candidates(), generated()):
            with self.subTest(case=item.case_id):
                self.assertEqual(item.approval_status, PENDING)

    def test_identifiers_are_sequential_and_prefixed(self) -> None:
        items = pipeline.regression_candidates(candidates(), generated())
        self.assertEqual(
            [item.case_id for item in items],
            [f"REG-R1-{index:04d}" for index in range(1, len(items) + 1)],
        )

    def test_every_proposal_names_a_real_candidate(self) -> None:
        known = {item.candidate_id for item in candidates()}
        for item in pipeline.regression_candidates(candidates(), generated()):
            with self.subTest(case=item.case_id):
                self.assertIn(item.candidate_id, known)

    def test_every_proposal_states_the_measurement_it_needs(self) -> None:
        for item in pipeline.regression_candidates(candidates(), generated()):
            with self.subTest(case=item.case_id):
                self.assertIn("keep every currently-passing case passing", item.expected_behavior)

    def test_every_proposal_records_that_it_is_not_applied(self) -> None:
        for item in pipeline.regression_candidates(candidates(), generated()):
            with self.subTest(case=item.case_id):
                self.assertIn("not applied", item.current_behavior)

    def test_an_exemplar_comes_from_the_same_axis_as_its_proposal(self) -> None:
        from risk_evaluation.coverage import synonyms

        by_text = {case.text: case for case in generated()}
        checked = 0
        for item in pipeline.regression_candidates(candidates(), generated()):
            if not item.text:
                continue
            axis = next(
                (name for name in (a.name for a in synonyms.AXES) if name in item.proposed_change),
                None,
            )
            with self.subTest(case=item.case_id):
                self.assertIsNotNone(axis, item.proposed_change)
                self.assertIn(f"axis:{axis}", by_text[item.text].generation_rule)
            checked += 1
        self.assertGreater(checked, 0)

    def test_a_structural_proposal_has_no_exemplar_sentence(self) -> None:
        structural = candidate_proposal_without_axis()
        items = pipeline.regression_candidates([structural], generated())
        self.assertEqual(items[0].text, "")
        self.assertIn("structural change", items[0].current_behavior)

    def test_expected_categories_follow_the_proposed_category(self) -> None:
        for item in pipeline.regression_candidates(candidates(), generated()):
            with self.subTest(case=item.case_id):
                if item.expected_categories:
                    self.assertEqual(len(item.expected_categories), 1)
                    self.assertIn(item.expected_categories[0], item.expected_behavior)


def candidate_proposal_without_axis() -> CoverageCandidate:
    return CoverageCandidate(
        candidate_id="CAND-R1-0001",
        source_case="IND-0001",
        failure_type="FRAME_GAP",
        proposal="review the FRAME_GAP affecting market_prediction: the repair is structural",
        risk_category="market_prediction",
        expected_impact="structural",
        covers_cases=("IND-0001",),
    )


class WritingRunTest(unittest.TestCase):
    """One complete writing run, in a temporary directory, reloaded and checked."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name) / "run"
        cls.pipeline_run = pipeline.run(output_dir=cls.root, write_reports=True, freeze_run=True)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_the_writing_run_still_scores_the_same_cases(self) -> None:
        self.assertEqual(self.pipeline_run.counts["cases"], 300)
        self.assertEqual(self.pipeline_run.counts["failures"], 151)

    def test_every_artifact_is_recorded(self) -> None:
        names = set(self.pipeline_run.artifacts)
        for expected in (
            "failure_analysis_r1.json",
            "generated_cases/generated_cases_r1.json",
            "regression_candidates.json",
            "coverage_freeze_r1.json",
        ):
            with self.subTest(artifact=expected):
                self.assertIn(expected, names)

    def test_every_recorded_artifact_exists(self) -> None:
        for name, path in self.pipeline_run.artifacts.items():
            with self.subTest(artifact=name):
                self.assertTrue(path.exists(), name)

    def test_validate_artifacts_accepts_the_run(self) -> None:
        report = pipeline.validate_artifacts(self.root)
        self.assertTrue(report["ok"], report)
        self.assertEqual(len(report["artifacts"]), len(ARTIFACTS))

    def test_validate_artifacts_reports_the_failure_count(self) -> None:
        report = pipeline.validate_artifacts(self.root)
        entry = next(
            item for item in report["artifacts"] if item["artifact"].startswith("failure_analysis")
        )
        self.assertEqual(entry["failures"], 151)
        self.assertNotIn("failures_without_evidence", entry)

    def test_validate_artifacts_reports_the_generated_case_count(self) -> None:
        report = pipeline.validate_artifacts(self.root)
        entry = next(
            item for item in report["artifacts"] if item["artifact"].startswith("generated")
        )
        self.assertEqual(entry["cases"], len(generator.generate()))
        self.assertNotIn("cases_not_excluded_from_benchmark", entry)

    def test_validate_artifacts_reports_only_pending_regression_candidates(self) -> None:
        report = pipeline.validate_artifacts(self.root)
        entry = next(
            item for item in report["artifacts"] if item["artifact"].startswith("regression")
        )
        self.assertEqual(entry["candidates"], self.pipeline_run.counts["regression"])
        self.assertNotIn("candidates_not_pending", entry)

    def test_validate_artifacts_records_the_freeze_fields(self) -> None:
        report = pipeline.validate_artifacts(self.root)
        entry = next(
            item for item in report["artifacts"] if item["artifact"].startswith("coverage_freeze")
        )
        for key in ("source_hash", "benchmark_hash", "evaluator_hash", "timestamp"):
            with self.subTest(key=key):
                self.assertIs(entry[key], True)

    def test_validate_artifacts_fails_loudly_on_a_missing_run(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            report = pipeline.validate_artifacts(raw)
        self.assertFalse(report["ok"])
        for entry in report["artifacts"]:
            with self.subTest(artifact=entry["artifact"]):
                self.assertIs(entry["exists"], False)
                self.assertIs(entry["ok"], False)

    def test_the_failure_artifact_carries_evidence_for_every_failure(self) -> None:
        body = json.loads(
            (self.root / "failure_analysis_r1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(body["failures"]), 151)
        for record in body["failures"]:
            with self.subTest(case=record["case_id"]):
                self.assertTrue(record["evidence"])

    def test_the_failure_artifact_carries_the_phase_figures(self) -> None:
        body = json.loads(
            (self.root / "failure_analysis_r1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(body["metrics"]["precision"], 0.9062)
        self.assertEqual(body["metrics"]["recall"], 0.1758)
        self.assertEqual(body["metrics"]["confusion"]["fn"], 136)

    def test_the_generated_artifact_marks_every_case_as_excluded(self) -> None:
        body = json.loads(
            (self.root / "generated_cases" / "generated_cases_r1.json").read_text(
                encoding="utf-8"
            )
        )
        for case in body["cases"]:
            with self.subTest(case=case["case_id"]):
                self.assertIs(case["excludes_from_benchmark"], True)

    def test_the_regression_artifact_is_a_proposal_list(self) -> None:
        body = json.loads(
            (self.root / "regression_candidates.json").read_text(encoding="utf-8")
        )
        self.assertEqual(body["count"], len(body["candidates"]))
        for item in body["candidates"]:
            with self.subTest(case=item["case_id"]):
                self.assertEqual(item["approval_status"], PENDING)
        self.assertIn("approval is a human decision", body["approval_policy"])

    def test_the_freeze_artifact_records_the_three_digests(self) -> None:
        body = json.loads(
            (self.root / "coverage_freeze_r1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(body["source_hash"], freeze.source_digest())
        self.assertEqual(body["benchmark_hash"], freeze.benchmark_digest())
        self.assertEqual(body["evaluator_hash"], freeze.evaluator_digest())
        self.assertEqual(body["phase"], "R1")

    def test_the_run_never_writes_into_accepted(self) -> None:
        accepted = self.root / "coverage_candidates" / "accepted"
        self.assertEqual(sorted(path.name for path in accepted.iterdir()), ["README.md"])

    def test_the_run_writes_one_pending_file_per_candidate(self) -> None:
        pending = self.root / "coverage_candidates" / "pending"
        files = sorted(path.name for path in pending.glob("*.json"))
        self.assertEqual(
            files, sorted(f"{item.candidate_id}.json" for item in self.pipeline_run.candidates)
        )

    def test_a_second_identical_run_is_reproducible(self) -> None:
        """The same inputs rewrite the same artifacts and reach the same counts.

        Two fields are the run's own and are excluded: the freeze's `timestamp` and the
        generated set's `generated_at`. Everything else must be byte-identical.
        """

        volatile = {"timestamp", "generated_at"}

        def bodies(source: Run) -> dict[str, object]:
            return {
                name: {
                    key: value
                    for key, value in json.loads(
                        path.read_text(encoding="utf-8")
                    ).items()
                    if key not in volatile
                }
                for name, path in source.artifacts.items()
                if path.is_file() and path.suffix == ".json"
            }

        first = bodies(self.pipeline_run)
        second = pipeline.run(output_dir=self.root, write_reports=True, freeze_run=True)
        self.assertEqual(first, bodies(second))
        self.assertEqual(self.pipeline_run.counts, second.counts)


class ArtifactPathTest(unittest.TestCase):
    def test_the_package_artifacts_live_under_the_package(self) -> None:
        for name, path in (
            ("analysis", pipeline.ANALYSIS_ARTIFACT),
            ("generated", pipeline.GENERATED_ARTIFACT),
            ("regression", pipeline.REGRESSION_ARTIFACT),
            ("freeze", pipeline.FREEZE_ARTIFACT),
        ):
            with self.subTest(artifact=name):
                self.assertEqual(path.parent if name != "generated" else path.parent.parent, PACKAGE_DIR)

    def test_no_package_artifact_points_at_a_frozen_area(self) -> None:
        for path in (
            pipeline.ANALYSIS_ARTIFACT,
            pipeline.GENERATED_ARTIFACT,
            pipeline.REGRESSION_ARTIFACT,
            pipeline.FREEZE_ARTIFACT,
        ):
            text = str(path).replace("\\", "/")
            with self.subTest(path=text):
                self.assertNotIn("/benchmarks/", text)
                self.assertNotIn("/v3/", text)
                self.assertNotIn("production", text)

    def test_the_default_registry_and_generator_dirs_are_the_packages_own(self) -> None:
        from risk_evaluation.coverage.registry import REGISTRY_DIR
        from risk_evaluation.coverage.generator import GENERATED_DIR

        self.assertEqual(REGISTRY_DIR.parent, PACKAGE_DIR)
        self.assertEqual(GENERATED_DIR.parent, PACKAGE_DIR)
