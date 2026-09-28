"""Provenance, human evaluation, benchmark, and integration-boundary tests."""

from __future__ import annotations

import ast
import inspect
import json
import pathlib
import tempfile
import unittest
from pathlib import Path

from multimodal_creator.dataset import (
    COLLECTION_METHODS,
    COLLECTION_PROTOCOL,
    MINIMUM_HUMAN_RATERS,
    ORIGINS,
    PERMISSION_STATUSES,
    DatasetManifest,
    HumanEvaluationError,
    ProvenanceError,
    ProvenanceRecord,
    Rating,
    Rater,
    build_rating_packet,
    compute_agreement,
    read_manifest,
    synthetic_manifest,
    write_agreement_report,
    write_manifest,
)
from multimodal_creator.grammar import (
    REGION_TYPES,
    RELATION_TYPES,
    extract_grammar,
    region_accuracy,
    relation_metrics,
    stability_metrics,
    strategy_metrics,
)
from multimodal_creator.grammar.benchmark_dataset import (
    CASE_GROUPS,
    NEGATIVE_EXPECTATIONS,
    TEMPLATE_GRAMMAR_LABELS,
    build_dataset,
)


class ProvenanceRecordTests(unittest.TestCase):
    """Provenance must be unambiguous and impossible to overstate."""

    def test_valid_synthetic_record(self) -> None:
        record = ProvenanceRecord(
            "s1", "c1", "synthetic_rendered", "synthetic_generation",
            "not_applicable_synthetic", "2026-01-01T00:00:00Z",
        )
        self.assertFalse(record.is_real)

    def test_valid_real_record(self) -> None:
        record = ProvenanceRecord(
            "s1", "c1", "real_creator_post", "creator_authorised_export",
            "explicit_written_permission", "2026-01-01T00:00:00Z",
        )
        self.assertTrue(record.is_real)
        self.assertTrue(record.is_permitted)

    def test_origin_is_required(self) -> None:
        with self.assertRaises(ProvenanceError):
            ProvenanceRecord("s", "c", "", "synthetic_generation", "not_applicable_synthetic", "t")

    def test_unknown_origin_is_rejected(self) -> None:
        with self.assertRaises(ProvenanceError):
            ProvenanceRecord("s", "c", "scraped", "synthetic_generation", "not_applicable_synthetic", "t")

    def test_unknown_collection_method_is_rejected(self) -> None:
        with self.assertRaises(ProvenanceError):
            ProvenanceRecord("s", "c", "synthetic_rendered", "vibes", "not_applicable_synthetic", "t")

    def test_unknown_permission_status_is_rejected(self) -> None:
        with self.assertRaises(ProvenanceError):
            ProvenanceRecord("s", "c", "synthetic_rendered", "synthetic_generation", "probably_fine", "t")

    def test_empty_source_id_is_rejected(self) -> None:
        with self.assertRaises(ProvenanceError):
            ProvenanceRecord("  ", "c", "synthetic_rendered", "synthetic_generation", "not_applicable_synthetic", "t")

    def test_missing_timestamp_is_rejected(self) -> None:
        with self.assertRaises(ProvenanceError):
            ProvenanceRecord("s", "c", "synthetic_rendered", "synthetic_generation", "not_applicable_synthetic", " ")

    def test_synthetic_cannot_claim_a_real_collection_method(self) -> None:
        with self.assertRaises(ProvenanceError):
            ProvenanceRecord("s", "c", "synthetic_rendered", "creator_authorised_export", "not_applicable_synthetic", "t")

    def test_real_post_cannot_claim_synthetic_generation(self) -> None:
        with self.assertRaises(ProvenanceError):
            ProvenanceRecord("s", "c", "real_creator_post", "synthetic_generation", "explicit_written_permission", "t")

    def test_permission_pending_blocks_use(self) -> None:
        record = ProvenanceRecord(
            "s", "c", "real_creator_post", "public_post_manual_capture",
            "permission_pending", "t",
        )
        self.assertFalse(record.is_permitted)
        with self.assertRaises(ProvenanceError):
            record.assert_usable()

    def test_vocabularies_are_exposed(self) -> None:
        self.assertIn("real_creator_post", ORIGINS)
        self.assertIn("synthetic_rendered", ORIGINS)
        self.assertIn("synthetic_generation", COLLECTION_METHODS)
        self.assertIn("explicit_written_permission", PERMISSION_STATUSES)


class ManifestTests(unittest.TestCase):
    def test_synthetic_manifest_builds(self) -> None:
        manifest = synthetic_manifest(["a", "b", "c"])
        self.assertEqual(len(manifest), 3)
        self.assertFalse(manifest.is_real_collection)

    def test_synthetic_manifest_fails_real_check(self) -> None:
        """The guard that stops a synthetic corpus being reported as real."""

        manifest = synthetic_manifest([f"s{i}" for i in range(30)])
        with self.assertRaises(ProvenanceError):
            manifest.assert_real_collection(minimum=20)

    def test_real_manifest_passes_real_check(self) -> None:
        records = tuple(
            ProvenanceRecord(
                f"s{i}", f"creator-{i % 3}", "real_creator_post",
                "creator_authorised_export", "explicit_written_permission",
                "2026-01-01T00:00:00Z",
            )
            for i in range(24)
        )
        manifest = DatasetManifest("real-set", records)
        manifest.assert_real_collection(minimum=20)
        self.assertTrue(manifest.is_real_collection)

    def test_real_check_needs_multiple_creators(self) -> None:
        records = tuple(
            ProvenanceRecord(
                f"s{i}", "only-creator", "real_creator_post",
                "creator_authorised_export", "explicit_written_permission",
                "2026-01-01T00:00:00Z",
            )
            for i in range(24)
        )
        with self.assertRaises(ProvenanceError):
            DatasetManifest("real-set", records).assert_real_collection(minimum=20)

    def test_duplicate_source_ids_are_rejected(self) -> None:
        with self.assertRaises(ProvenanceError):
            synthetic_manifest(["dup", "dup"])

    def test_empty_manifest_is_rejected(self) -> None:
        with self.assertRaises(ProvenanceError):
            DatasetManifest("empty", ())

    def test_empty_dataset_id_is_rejected(self) -> None:
        with self.assertRaises(ProvenanceError):
            DatasetManifest("  ", synthetic_manifest(["a"]).records)

    def test_origins_are_counted(self) -> None:
        manifest = synthetic_manifest(["a", "b"])
        self.assertEqual(manifest.origins(), {"synthetic_rendered": 2})

    def test_creators_are_listed(self) -> None:
        manifest = synthetic_manifest(["a", "b"], creator_ids={"a": "x", "b": "y"})
        self.assertEqual(manifest.creators(), ("x", "y"))

    def test_manifest_round_trips_through_json(self) -> None:
        manifest = synthetic_manifest(["a", "b", "c"], dataset_id="round-trip")
        with tempfile.TemporaryDirectory() as directory:
            path = write_manifest(manifest, Path(directory) / "dataset_manifest.json")
            restored = read_manifest(path)
            self.assertEqual(restored.dataset_id, "round-trip")
            self.assertEqual(len(restored), 3)
            self.assertFalse(restored.is_real_collection)

    def test_read_validates_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(
                json.dumps(
                    {
                        "dataset_id": "bad",
                        "records": [
                            {
                                "source_id": "a",
                                "creator_id": "c",
                                "origin": "scraped",
                                "collection_method": "synthetic_generation",
                                "permission_status": "not_applicable_synthetic",
                                "collected_at": "t",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ProvenanceError):
                read_manifest(path)

    def test_render_mentions_real_collection_status(self) -> None:
        self.assertIn("real_collection", synthetic_manifest(["a"]).render())

    def test_collection_protocol_is_published(self) -> None:
        self.assertGreaterEqual(len(COLLECTION_PROTOCOL), 5)
        for step in COLLECTION_PROTOCOL:
            self.assertIn("step", step)
            self.assertIn("detail", step)


class RaterAndRatingTests(unittest.TestCase):
    def test_valid_rater(self) -> None:
        self.assertTrue(Rater("r1", "human").is_human)

    def test_model_rater_is_not_human(self) -> None:
        self.assertFalse(Rater("m1", "model").is_human)

    def test_unknown_rater_kind_is_rejected(self) -> None:
        with self.assertRaises(HumanEvaluationError):
            Rater("r", "robot")

    def test_empty_rater_id_is_rejected(self) -> None:
        with self.assertRaises(HumanEvaluationError):
            Rater("  ")

    def test_valid_rating(self) -> None:
        self.assertTrue(Rating("r", "i", "yes", "no").verdict("grammar_matches_image"))

    def test_invalid_verdict_is_rejected(self) -> None:
        with self.assertRaises(HumanEvaluationError):
            Rating("r", "i", "maybe", "yes")

    def test_missing_item_id_is_rejected(self) -> None:
        with self.assertRaises(HumanEvaluationError):
            Rating("r", "", "yes", "yes")

    def test_unknown_question_is_rejected(self) -> None:
        with self.assertRaises(HumanEvaluationError):
            Rating("r", "i", "yes", "yes").verdict("vibes")


class AgreementComputationTests(unittest.TestCase):
    """The brief forbids computing agreement without a second person."""

    def _raters(self, kind="human", count=2):
        return [Rater(f"r{i}", kind) for i in range(1, count + 1)]

    def _ratings(self, values):
        return [
            Rating(f"r{index + 1}", "item", verdict, "yes")
            for index, verdict in enumerate(values)
        ]

    def test_two_humans_can_agree(self) -> None:
        report = compute_agreement(self._ratings(["yes", "yes"]), self._raters())
        self.assertEqual(report.overall_agreement, 1.0)
        self.assertTrue(report.is_human_agreement)

    def test_two_humans_can_disagree(self) -> None:
        """The helper's ratings disagree on one question and agree on the other.

        Both questions are always asked, so an item where raters split on
        ``grammar_matches_image`` but agree on ``strategy_is_reasonable`` produces
        an overall agreement of 0.5 — one of two rater pairs agreeing, averaged
        across questions. The disagreement case is still reported.
        """

        report = compute_agreement(self._ratings(["yes", "no"]), self._raters())
        self.assertEqual(report.overall_agreement, 0.5)
        self.assertTrue(report.disagreement_cases)
        self.assertEqual(
            report.per_question["grammar_matches_image"]["agreement"], 0.0
        )
        self.assertEqual(
            report.per_question["strategy_is_reasonable"]["agreement"], 1.0
        )

    def test_one_rater_is_refused(self) -> None:
        with self.assertRaises(HumanEvaluationError):
            compute_agreement(self._ratings(["yes"]), self._raters(count=1))

    def test_model_raters_are_refused_as_human_evidence(self) -> None:
        with self.assertRaises(HumanEvaluationError):
            compute_agreement(self._ratings(["yes", "yes"]), self._raters(kind="model"))

    def test_fixture_raters_are_refused_as_human_evidence(self) -> None:
        with self.assertRaises(HumanEvaluationError):
            compute_agreement(
                self._ratings(["yes", "yes"]), self._raters(kind="synthetic_fixture")
            )

    def test_require_human_false_allows_fixtures(self) -> None:
        report = compute_agreement(
            self._ratings(["yes", "yes"]),
            self._raters(kind="synthetic_fixture"),
            require_human=False,
        )
        self.assertFalse(report.is_human_agreement)
        self.assertEqual(report.overall_agreement, 1.0)

    def test_fixture_report_declares_itself_non_human(self) -> None:
        report = compute_agreement(
            self._ratings(["yes", "yes"]),
            self._raters(kind="synthetic_fixture"),
            require_human=False,
        )
        payload = report.as_dict()
        self.assertFalse(payload["is_human_agreement"])
        self.assertIn("NOT human agreement", payload["claim"])

    def test_undeclared_rater_is_rejected(self) -> None:
        with self.assertRaises(HumanEvaluationError):
            compute_agreement([Rating("ghost", "i", "yes", "yes")], self._raters())

    def test_empty_ratings_are_rejected(self) -> None:
        with self.assertRaises(HumanEvaluationError):
            compute_agreement([], self._raters())

    def test_single_scored_item_is_rejected(self) -> None:
        with self.assertRaises(HumanEvaluationError):
            compute_agreement([Rating("r1", "i", "yes", "yes")], self._raters())

    def test_both_questions_are_reported(self) -> None:
        report = compute_agreement(self._ratings(["yes", "no"]), self._raters())
        self.assertIn("grammar_matches_image", report.per_question)
        self.assertIn("strategy_is_reasonable", report.per_question)

    def test_unanimous_items_are_counted(self) -> None:
        ratings = [
            Rating("r1", "item-a", "yes", "yes"),
            Rating("r2", "item-a", "yes", "yes"),
            Rating("r1", "item-b", "yes", "yes"),
            Rating("r2", "item-b", "no", "yes"),
        ]
        report = compute_agreement(ratings, self._raters())
        self.assertEqual(report.unanimous_items, 1)

    def test_disagreement_cases_carry_verdicts(self) -> None:
        report = compute_agreement(self._ratings(["yes", "no"]), self._raters())
        case = report.disagreement_cases[0]
        self.assertEqual(set(case.verdicts), {"r1", "r2"})

    def test_minimum_human_raters_is_two(self) -> None:
        self.assertEqual(MINIMUM_HUMAN_RATERS, 2)

    def test_report_renders_and_warns_when_not_human(self) -> None:
        report = compute_agreement(
            self._ratings(["yes", "yes"]),
            self._raters(kind="model"),
            require_human=False,
        )
        self.assertIn("is_human_agreement", report.render())

    def test_report_writes_json(self) -> None:
        report = compute_agreement(self._ratings(["yes", "no"]), self._raters())
        with tempfile.TemporaryDirectory() as directory:
            path = write_agreement_report(report, Path(directory) / "agreement_report.json")
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("overall_agreement", payload)
            self.assertIn("disagreement_cases", payload)


class RatingPacketTests(unittest.TestCase):
    def test_packet_builds(self) -> None:
        packet = build_rating_packet(
            [{"item_id": "i1", "image_reference": "a.png", "grammar_summary": "g", "strategy_summary": "s"}]
        )
        self.assertEqual(len(packet["items"]), 1)

    def test_packet_has_blank_verdicts(self) -> None:
        packet = build_rating_packet([{"item_id": "i1"}])
        ratings = packet["items"][0]["ratings"]
        self.assertIsNone(ratings["grammar_matches_image"])
        self.assertIsNone(ratings["strategy_is_reasonable"])

    def test_packet_states_both_questions(self) -> None:
        packet = build_rating_packet([])
        self.assertIn("grammar_matches_image", packet["questions"])
        self.assertIn("strategy_is_reasonable", packet["questions"])

    def test_packet_states_minimum_raters(self) -> None:
        self.assertEqual(build_rating_packet([])["minimum_raters"], 2)

    def test_packet_writes_to_disk(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rating_packet.json"
            build_rating_packet([{"item_id": "i1"}], output_path=path)
            self.assertTrue(path.is_file())


class BenchmarkDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = build_dataset()

    def test_at_least_eighty_cases(self) -> None:
        self.assertGreaterEqual(self.dataset.case_count, 80)

    def test_five_required_groups(self) -> None:
        self.assertEqual(len(CASE_GROUPS), 5)
        counts = self.dataset.group_counts()
        for group in CASE_GROUPS:
            self.assertGreater(counts[group], 0, group)

    def test_grammar_group_has_twenty_plus(self) -> None:
        self.assertGreaterEqual(self.dataset.group_counts()["grammar_extraction"], 20)

    def test_relation_group_has_fifteen_plus(self) -> None:
        self.assertGreaterEqual(self.dataset.group_counts()["relation_extraction"], 15)

    def test_invariant_group_has_fifteen_plus(self) -> None:
        self.assertGreaterEqual(self.dataset.group_counts()["invariant_discovery"], 15)

    def test_strategy_group_has_fifteen_plus(self) -> None:
        self.assertGreaterEqual(self.dataset.group_counts()["creator_strategy"], 15)

    def test_negative_group_has_ten(self) -> None:
        self.assertGreaterEqual(self.dataset.group_counts()["negative_cases"], 10)

    def test_labels_are_produced_before_the_algorithm(self) -> None:
        """Labels come from the template specification, not from a run."""

        for sample_id, label in self.dataset.labels.items():
            self.assertIn("grammar", label, sample_id)
            self.assertIn("strategy", label, sample_id)
            self.assertIn("template_prefix", label, sample_id)

    def test_dataset_module_does_not_import_the_extractor(self) -> None:
        from multimodal_creator.grammar import benchmark_dataset

        tree = ast.parse(inspect.getsource(benchmark_dataset))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        for name in imported:
            self.assertNotIn("extractor", name, f"dataset imports {name}")
            self.assertNotIn("strategy", name, f"dataset imports {name}")
            self.assertNotIn("invariants", name, f"dataset imports {name}")

    def test_dataset_module_uses_no_private_pipeline_helpers(self) -> None:
        """Only module-level functions count; class methods are not helpers."""

        from multimodal_creator.grammar import benchmark_dataset

        tree = ast.parse(inspect.getsource(benchmark_dataset))
        defined = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertEqual(
            defined,
            {"build_dataset", "_by_prefix", "_build_cases"},
            f"unexpected module-level helpers: {sorted(defined)}",
        )
        # And the pipeline entry points must not be imported at all.
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
                imported.extend(alias.name for alias in node.names)
        for name in imported:
            self.assertNotIn("extractor", name)
            self.assertNotIn("strategy", name)
            self.assertNotIn("invariants", name)

    def test_labels_reference_declared_region_types(self) -> None:
        for label in TEMPLATE_GRAMMAR_LABELS.values():
            for region in label["regions"]:
                self.assertIn(region["region_type"], REGION_TYPES)

    def test_labels_reference_declared_relations(self) -> None:
        for label in TEMPLATE_GRAMMAR_LABELS.values():
            for relation in label["relations"]:
                self.assertIn(relation, RELATION_TYPES)

    def test_negative_expectations_are_declared(self) -> None:
        self.assertEqual(len(NEGATIVE_EXPECTATIONS), 10)

    def test_describe_renders(self) -> None:
        self.assertIn("M4 benchmark", self.dataset.describe())


class EvaluationMetricTests(unittest.TestCase):
    def _grammar(self):
        from multimodal_creator.taxonomy import StructuralObservation

        obs = StructuralObservation(
            observation_id="x",
            medium="image",
            source_id="x",
            roles=("visual_style_source",),
            evidence_kinds=("region_layout",),
            regions=(
                {"region_id": "bg", "role": "background", "box": {"x": 0, "y": 0, "w": 1, "h": 1}, "layer_order": 0},
                {"region_id": "t", "role": "title", "box": {"x": 0.05, "y": 0.08, "w": 0.4, "h": 0.14}, "layer_order": 1},
            ),
        )
        return extract_grammar(obs).grammar

    def test_perfect_region_match(self) -> None:
        grammar = self._grammar()
        expected = {
            "regions": [
                {"region_type": "background", "position_band": "center"},
                {"region_type": "headline", "position_band": "top"},
            ]
        }
        score = region_accuracy(grammar, expected)
        self.assertEqual(score.f1, 1.0)
        self.assertEqual(score.type_accuracy, 1.0)

    def test_missing_region_lowers_recall(self) -> None:
        grammar = self._grammar()
        expected = {
            "regions": [
                {"region_type": "background", "position_band": "center"},
                {"region_type": "subject", "position_band": "center"},
            ]
        }
        score = region_accuracy(grammar, expected)
        self.assertLess(score.recall, 1.0)
        self.assertTrue(score.missing)

    def test_extra_region_lowers_precision(self) -> None:
        grammar = self._grammar()
        expected = {"regions": [{"region_type": "background", "position_band": "center"}]}
        score = region_accuracy(grammar, expected)
        self.assertLess(score.precision, 1.0)
        self.assertTrue(score.spurious)

    def test_placement_accuracy_is_separate_from_type_accuracy(self) -> None:
        grammar = self._grammar()
        expected = {"regions": [{"region_type": "headline", "position_band": "bottom"}]}
        score = region_accuracy(grammar, expected)
        self.assertEqual(score.type_accuracy, 1.0)
        self.assertEqual(score.placement_accuracy, 0.0)

    def test_relation_metrics_perfect(self) -> None:
        grammar = self._grammar()
        metrics = relation_metrics(grammar, sorted(grammar.relation_types()))
        self.assertEqual(metrics.precision, 1.0)
        self.assertEqual(metrics.recall, 1.0)

    def test_relation_metrics_missing_relation(self) -> None:
        grammar = self._grammar()
        metrics = relation_metrics(grammar, ["headline_above_subject"])
        self.assertLess(metrics.recall, 1.0)

    def test_relation_metrics_extra_relation(self) -> None:
        grammar = self._grammar()
        metrics = relation_metrics(grammar, [])
        self.assertLess(metrics.precision, 1.0)

    def test_stability_repetition(self) -> None:
        baseline = [("a", "b"), ("c",)]
        metrics = stability_metrics(baseline, [baseline, baseline])
        self.assertEqual(metrics.repetition_rate, 1.0)

    def test_stability_detects_change(self) -> None:
        baseline = [("a", "b"), ("c",)]
        metrics = stability_metrics(baseline, [[("a",), ("b",), ("c",)]])
        self.assertEqual(metrics.repetition_rate, 0.0)

    def test_stability_is_naming_independent(self) -> None:
        """The same partition in a different order still counts as identical."""

        baseline = [("b", "a"), ("c",)]
        metrics = stability_metrics(baseline, [[("a", "b"), ("c",)]])
        self.assertEqual(metrics.repetition_rate, 1.0)

    def test_stability_perturbation(self) -> None:
        baseline = [("a", "b")]
        metrics = stability_metrics(baseline, [baseline], [baseline, [("a",), ("b",)]])
        self.assertEqual(metrics.perturbation_rate, 0.5)

    def test_strategy_metrics_agree(self) -> None:
        from multimodal_creator.grammar import CreatorStrategyPattern

        pattern = CreatorStrategyPattern(
            pattern_id="p",
            cluster_id="c",
            attention_strategy="headline_first",
            information_hierarchy=("hook",),
            composition_strategy=("top_entry",),
            invariants=(),
            support=3,
            creator_ids=("a",),
            confidence=0.8,
        )
        metrics = strategy_metrics(
            [pattern],
            {"p": {"attention_strategy": "headline_first", "information_hierarchy": ["hook"]}},
        )
        self.assertEqual(metrics.attention_accuracy, 1.0)
        self.assertEqual(metrics.hierarchy_accuracy, 1.0)

    def test_strategy_metrics_note_is_explicit(self) -> None:
        metrics = strategy_metrics([], {})
        self.assertIn("human", metrics.measurement_note)


class NoRuntimeIntegrationTests(unittest.TestCase):
    """M4 stays an experimental layer and must not reach the runtime."""

    def test_no_forbidden_imports_anywhere_in_the_package(self) -> None:
        """M4 must not reach the runtime, the engine, or another track.

        ``evaluation`` is deliberately absent from this list: the grammar package
        has its own ``grammar.evaluation`` module, and M2's mock observer imports
        ``evaluation.evaluator``. Flagging those would be a false positive, and a
        test that cries wolf gets disabled.
        """

        root = Path(__file__).resolve().parents[2] / "multimodal_creator"
        forbidden = {
            "distillation_core",
            "workflows",
            "runtime",
            "production",
            "security",
            "artifact",
            "plugins",
            "risk_evaluation",
            "schema_validation",
        }
        offenders: list[str] = []
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] in forbidden:
                            offenders.append(f"{path.name}:{alias.name}")
                elif isinstance(node, ast.ImportFrom) and node.module:
                    if node.module.split(".")[0] in forbidden:
                        offenders.append(f"{path.name}:{node.module}")
        self.assertEqual(offenders, [], f"runtime imports found: {offenders}")

    def test_distillation_engine_is_not_referenced(self) -> None:
        root = Path(__file__).resolve().parents[2] / "multimodal_creator"
        for path in sorted(root.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("DistillationEngine", text, str(path))

    def test_grammar_layer_does_not_import_the_engine(self) -> None:
        from multimodal_creator.grammar import benchmark_runner

        source = inspect.getsource(benchmark_runner)
        self.assertNotIn("DistillationEngine", source)

    def test_no_content_generation_exists(self) -> None:
        """No module may define or import a generation capability.

        Checked structurally rather than by substring. A bare token search flags a
        module that merely *names* a forbidden capability — M5's
        ``FORBIDDEN_KEYS`` contains ``"diffusion"`` precisely to reject it, which
        a substring scan reads as the opposite of what it is.
        """

        root = Path(__file__).resolve().parents[2] / "multimodal_creator"
        forbidden_imports = {
            "torch",
            "diffusers",
            "transformers",
            "openai",
            "stability_sdk",
            "replicate",
        }
        forbidden_callables = (
            "generate",
            "render_image",
            "publish",
            "deploy",
            "upload",
        )
        offenders: list[str] = []
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] in forbidden_imports:
                            offenders.append(f"{path.name}:import {alias.name}")
                elif isinstance(node, ast.ImportFrom) and node.module:
                    if node.module.split(".")[0] in forbidden_imports:
                        offenders.append(f"{path.name}:from {node.module}")
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    lowered = node.name.lower()
                    for token in forbidden_callables:
                        if token in lowered:
                            offenders.append(f"{path.name}:def {node.name}")
        self.assertEqual(offenders, [], f"generation code found: {offenders}")


if __name__ == "__main__":
    unittest.main()
