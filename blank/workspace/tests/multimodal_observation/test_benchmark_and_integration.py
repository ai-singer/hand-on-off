"""Benchmark dataset integrity, label independence, and integration tests."""

from __future__ import annotations

import inspect
import json
import tempfile
import unittest
from pathlib import Path

from multimodal_creator.observation import (
    FrameObserver,
    ObservationSetBuilder,
    StdlibPixelBackend,
    VisualSource,
)
from multimodal_creator.observation.benchmark_dataset import (
    CASE_GROUPS,
    build_dataset,
)
from multimodal_creator.observation.corpus import (
    CALIBRATION_REPEAT_PLAN,
    build_calibration_corpus,
    build_corpus,
    render_corpus,
)
from multimodal_creator.taxonomy import LAYOUT_TEMPLATE_CLASSES


class BenchmarkDatasetTests(unittest.TestCase):
    """The dataset must meet the brief's size and group requirements."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = build_dataset()

    def test_at_least_fifty_cases(self) -> None:
        self.assertGreaterEqual(self.dataset.case_count, 50)

    def test_five_required_groups_exist(self) -> None:
        self.assertEqual(len(CASE_GROUPS), 5)
        counts = self.dataset.group_counts()
        for group in CASE_GROUPS:
            self.assertGreater(counts[group], 0, f"{group} has no cases")

    def test_same_template_detection_group_has_ten_plus(self) -> None:
        self.assertGreaterEqual(self.dataset.group_counts()["same_template_detection"], 10)

    def test_different_template_separation_group_has_ten_plus(self) -> None:
        self.assertGreaterEqual(
            self.dataset.group_counts()["different_template_separation"], 10
        )

    def test_creator_pattern_group_has_ten_plus(self) -> None:
        self.assertGreaterEqual(
            self.dataset.group_counts()["creator_pattern_extraction"], 10
        )

    def test_negative_group_has_ten_plus(self) -> None:
        self.assertGreaterEqual(self.dataset.group_counts()["negative_cases"], 10)

    def test_sequence_group_has_eight_plus(self) -> None:
        self.assertGreaterEqual(self.dataset.group_counts()["sequence_consistency"], 8)

    def test_labels_cover_every_sample(self) -> None:
        for sample in self.dataset.samples:
            self.assertIn(sample.sample_id, self.dataset.labels)

    def test_labels_carry_creator_and_template(self) -> None:
        for sample_id, label in self.dataset.labels.items():
            self.assertIn("creator_id", label, sample_id)
            self.assertIn("template_id", label, sample_id)

    def test_expected_layout_classes_are_contract_valid(self) -> None:
        for label in self.dataset.labels.values():
            self.assertIn(
                label["expected_layout_class"],
                LAYOUT_TEMPLATE_CLASSES,
                label["sample_id"],
            )

    def test_dataset_has_real_creator_diversity(self) -> None:
        creators = {label["creator_id"] for label in self.dataset.labels.values()}
        self.assertGreaterEqual(len(creators), 6)

    def test_dataset_has_template_reuse_across_creators(self) -> None:
        by_template: dict[str, set[str]] = {}
        for label in self.dataset.labels.values():
            by_template.setdefault(label["template_id"], set()).add(label["creator_id"])
        shared = [t for t, creators in by_template.items() if len(creators) > 1]
        self.assertTrue(shared, "no template is used by more than one creator")

    def test_describe_renders(self) -> None:
        self.assertIn("M3 benchmark", self.dataset.describe())


class LabelIndependenceTests(unittest.TestCase):
    """Labels must be independent of the algorithm that is scored by them."""

    def test_labels_come_from_the_generator_not_the_clustering(self) -> None:
        dataset = build_dataset()
        for sample in dataset.samples:
            label = dataset.labels[sample.sample_id]
            self.assertEqual(label["template_id"], sample.template_id)
            self.assertEqual(label["creator_id"], sample.creator_id)

    def test_dataset_module_does_not_import_clustering(self) -> None:
        """Check the parsed imports, not the prose.

        A substring search over source text would trip on this module's own
        docstring, which explains the separation it is being tested for. The
        claim is about what the module *imports*, so it is checked on the syntax
        tree.
        """

        import ast

        from multimodal_creator.observation import benchmark_dataset

        source = inspect.getsource(benchmark_dataset)
        tree = ast.parse(source)
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.append(node.module)
                imported.extend(alias.name for alias in node.names)

        for name in imported:
            self.assertNotIn("clustering", name, f"dataset imports {name}")
            self.assertNotIn("similarity", name, f"dataset imports {name}")

    def test_discovery_never_reads_a_family_label(self) -> None:
        """Discovery may read creator provenance but never family identity.

        ``creator_id`` is legitimate: it is a fact about where an image came
        from, and it drives provenance handling. ``template_id`` and any family
        membership would be the answer itself, so their absence is the property
        that matters.
        """

        import ast

        from multimodal_creator.clustering import template_discovery

        source = inspect.getsource(template_discovery.discover_templates)
        # Strip the docstring before searching, so prose cannot satisfy or
        # violate the check.
        tree = ast.parse(source)
        body = tree.body[0].body if isinstance(tree.body[0], ast.FunctionDef) else []
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            body = body[1:]
        code = "\n".join(ast.unparse(node) for node in body)

        for token in ("template_id", "layout_family", "expected_", "same_family"):
            self.assertNotIn(token, code, f"discover_templates reads {token}")
        # creator provenance is allowed and expected.
        self.assertIn("creator_id", code)

    def test_cases_do_not_name_cluster_ids(self) -> None:
        dataset = build_dataset()
        for case in dataset.cases:
            serialised = json.dumps(case.as_dict())
            self.assertNotIn("family-", serialised, case.case_id)
            self.assertNotIn("cluster_id", serialised, case.case_id)

    def test_evaluation_reads_labels_only_after_discovery(self) -> None:
        """In the runner, discovery must run before any family label is read."""

        from multimodal_creator.observation import benchmark_runner

        source = inspect.getsource(benchmark_runner.run_benchmark)
        discovery_at = source.index("discover_templates(")
        for token in ("layout_family", "expected_layout_class"):
            first = source.find(token)
            self.assertGreater(
                first,
                discovery_at,
                f"{token} is read before discovery runs",
            )


class CorpusTests(unittest.TestCase):
    def test_corpus_builds(self) -> None:
        samples, templates = build_corpus(only_hero=True)
        self.assertTrue(samples)
        self.assertEqual(len(templates), 10)

    def test_calibration_corpus_populates_repeats(self) -> None:
        samples, _templates = build_calibration_corpus()
        counts: dict[tuple[str, str], int] = {}
        for sample in samples:
            key = (sample.creator_id, sample.template_id)
            counts[key] = counts.get(key, 0) + 1
        self.assertTrue(
            any(count >= 3 for count in counts.values()),
            "no creator repeats a template three times, so the "
            "same_creator_same_template quadrant cannot be populated",
        )

    def test_repeat_plan_covers_multiple_creators(self) -> None:
        self.assertGreaterEqual(len(CALIBRATION_REPEAT_PLAN), 6)

    def test_rendering_produces_readable_files(self) -> None:
        from multimodal_creator.observation.pixel.png_codec import read_png

        samples, templates = build_corpus(only_hero=True)
        with tempfile.TemporaryDirectory() as directory:
            written = render_corpus(
                directory, samples=samples[:3], templates=templates, width=160, height=240
            )
            self.assertEqual(len(written), 3)
            for _sample_id, path in written:
                image = read_png(path)
                self.assertEqual((image.width, image.height), (160, 240))

    def test_rendering_is_deterministic(self) -> None:
        from multimodal_creator.observation.corpus import render_sample

        samples, templates = build_corpus(only_hero=True)
        template = templates[samples[0].template_id]
        first = render_sample(samples[0], template, width=120, height=180)
        second = render_sample(samples[0], template, width=120, height=180)
        self.assertEqual(first.pixels, second.pixels)


class ObservationSetTests(unittest.TestCase):
    """Reconstruction from real observations must be faithful and lossy in the
    right direction only."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        dataset = build_dataset()
        cls.dataset = dataset
        subset = dataset.samples[:5]
        written = render_corpus(
            cls._tmp.name,
            samples=list(subset),
            templates=dict(dataset.templates),
            width=240,
            height=360,
        )
        observer = FrameObserver(StdlibPixelBackend())
        results = [
            observer.observe(VisualSource(sample_id, "image", path))
            for sample_id, path in written
        ]
        provenance = {
            sample_id: {
                "creator_id": dataset.labels[sample_id]["creator_id"],
                "batch_id": dataset.labels[sample_id]["batch_id"],
            }
            for sample_id, _path in written
        }
        cls.observation_set = ObservationSetBuilder().build(results, labels=provenance)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_set_is_built(self) -> None:
        self.assertEqual(len(self.observation_set), 5)

    def test_set_reports_completeness(self) -> None:
        self.assertGreaterEqual(self.observation_set.evidence_completeness(), 0.75)

    def test_set_summarises(self) -> None:
        self.assertIn("observation set", self.observation_set.summarise())

    def test_reconstruction_produces_visual_samples(self) -> None:
        samples = ObservationSetBuilder().to_visual_samples(self.observation_set)
        self.assertEqual(len(samples), 5)

    def test_reconstructed_samples_are_contract_valid(self) -> None:
        from multimodal_creator.taxonomy import REGION_ROLES

        for sample in ObservationSetBuilder().to_visual_samples(self.observation_set):
            self.assertTrue(sample.regions)
            for region in sample.regions:
                self.assertIn(region.role, REGION_ROLES)

    def test_reconstruction_preserves_provenance(self) -> None:
        samples = ObservationSetBuilder().to_visual_samples(self.observation_set)
        for sample in samples:
            expected = self.dataset.labels[sample.sample_id]["creator_id"]
            self.assertEqual(sample.provenance.creator_id, expected)

    def test_reconstruction_does_not_invent_undeclared_style(self) -> None:
        """A field the observer could not determine stays neutral."""

        from multimodal_creator.taxonomy import PALETTE_RELATIONS

        for sample in ObservationSetBuilder().to_visual_samples(self.observation_set):
            self.assertIn(sample.palette_relation, PALETTE_RELATIONS)

    def test_duplicate_source_ids_are_rejected(self) -> None:
        first = self.observation_set.results[0]
        with self.assertRaises(Exception):
            ObservationSetBuilder().build([first, first])

    def test_mixed_backends_are_rejected(self) -> None:
        from multimodal_creator.observation import (
            EvidenceRecord,
            ManualAnnotationBackend,
            MockDescriptorBackend,
            ObservationResult,
        )

        base = self.observation_set.results[0]
        other = ObservationResult(
            observation=base.observation,
            source=base.source,
            backend_id="different_backend",
            evidence_source=base.evidence_source,
            evidence=base.evidence,
            confidence=base.confidence,
        )
        with self.assertRaises(Exception):
            ObservationSetBuilder().build([base, other])

    def test_empty_set_is_rejected(self) -> None:
        with self.assertRaises(Exception):
            ObservationSetBuilder().build([])


class PipelineIntegrationTests(unittest.TestCase):
    """Observation must flow into the M2 pipeline unchanged."""

    @classmethod
    def setUpClass(cls) -> None:
        from multimodal_creator.clustering import discover_templates

        cls._tmp = tempfile.TemporaryDirectory()
        dataset = build_dataset()
        subset = dataset.samples[:6]
        written = render_corpus(
            cls._tmp.name,
            samples=list(subset),
            templates=dict(dataset.templates),
            width=240,
            height=360,
        )
        observer = FrameObserver(StdlibPixelBackend())
        results = [
            observer.observe(VisualSource(sample_id, "image", path))
            for sample_id, path in written
        ]
        provenance = {
            sample_id: {
                "creator_id": dataset.labels[sample_id]["creator_id"],
                "batch_id": dataset.labels[sample_id]["batch_id"],
            }
            for sample_id, _path in written
        }
        cls.observation_set = ObservationSetBuilder().build(results, labels=provenance)
        cls.samples = ObservationSetBuilder().to_visual_samples(cls.observation_set)
        cls.discovery = discover_templates(cls.samples)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_discovery_runs_on_reconstructed_samples(self) -> None:
        self.assertIsNotNone(self.discovery)

    def test_discovery_output_is_serialisable(self) -> None:
        payload = json.dumps(self.discovery.as_dict())
        self.assertIn("clusters", payload)

    def test_patterns_distil_from_real_observations(self) -> None:
        from multimodal_creator.pattern import distill_patterns

        patterns = distill_patterns(self.discovery, self.samples)
        for pattern in patterns:
            self.assertTrue(pattern.layout_strategy)

    def test_temporal_rhythm_allowed_only_for_video(self) -> None:
        for result in self.observation_set.results:
            if result.observation.medium == "image":
                self.assertNotIn("temporal_rhythm", result.observation.evidence_kinds)


if __name__ == "__main__":
    unittest.main()
