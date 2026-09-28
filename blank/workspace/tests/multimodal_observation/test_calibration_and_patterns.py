"""Calibration, reproducibility, pattern extraction, and negative-case tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from multimodal_creator.clustering import discover_templates
from multimodal_creator.extraction.visual_sample import (
    RegionSpec,
    SampleProvenance,
    SubjectSpec,
    VisualSample,
)
from multimodal_creator.observation.calibration import (
    M2_SYNTHETIC_THRESHOLD,
    QUADRANTS,
    CalibrationError,
    CalibrationReport,
    QuadrantStats,
    ThresholdCandidate,
    calibrate,
    calibrate_from_samples,
    quadrant_of,
    write_calibration,
)
from multimodal_creator.observation.evaluation import (
    clustering_metrics,
    detection_metrics,
    pattern_metrics,
)
from multimodal_creator.pattern import (
    CreatorVisualPattern,
    PatternDistillationError,
    distill_cluster,
    distill_patterns,
    render_patterns,
)
from multimodal_creator.similarity import pairwise_similarity


def region(region_id, role, x, y, w, h, layer=0):
    return RegionSpec(region_id, role, {"x": x, "y": y, "w": w, "h": h}, layer)


def sample(sample_id, creator, *, template, regions=None, color="warm_red", **kw):
    return VisualSample(
        sample_id=sample_id,
        regions=regions
        or (
            region("bg", "background", 0.0, 0.0, 1.0, 1.0, 0),
            region("t", "title", 0.05, 0.10, 0.40, 0.15, 1),
            region("s", "subject", 0.55, 0.10, 0.40, 0.60, 1),
        ),
        color_family=color,
        subject=SubjectSpec("composite", "balanced"),
        provenance=SampleProvenance(creator),
        layout_template_class=kw.get("layout", "image_left_text_right"),
        alignment=kw.get("alignment", "left"),
        palette_relation=kw.get("palette", "complementary"),
        placement=kw.get("placement", "side_panel"),
    )


class QuadrantTests(unittest.TestCase):
    def test_all_four_quadrants_are_declared(self) -> None:
        self.assertEqual(len(QUADRANTS), 4)
        self.assertIn("same_creator_same_template", QUADRANTS)
        self.assertIn("different_creator_different_template", QUADRANTS)

    def test_quadrant_classification(self) -> None:
        a = {"creator_id": "c1", "template_id": "T1"}
        cases = [
            ({"creator_id": "c1", "template_id": "T1"}, "same_creator_same_template"),
            ({"creator_id": "c1", "template_id": "T2"}, "same_creator_different_template"),
            ({"creator_id": "c2", "template_id": "T1"}, "different_creator_same_template"),
            ({"creator_id": "c2", "template_id": "T2"}, "different_creator_different_template"),
        ]
        for other, expected in cases:
            self.assertEqual(quadrant_of(a, other), expected)


class QuadrantStatsTests(unittest.TestCase):
    def test_statistics_are_computed(self) -> None:
        stats = QuadrantStats.from_scores("q", [0.1, 0.2, 0.3, 0.4, 0.5])
        self.assertEqual(stats.count, 5)
        self.assertAlmostEqual(stats.mean, 0.3, places=5)
        self.assertAlmostEqual(stats.median, 0.3, places=5)
        self.assertAlmostEqual(stats.minimum, 0.1, places=5)
        self.assertAlmostEqual(stats.maximum, 0.5, places=5)

    def test_empty_scores_are_safe(self) -> None:
        stats = QuadrantStats.from_scores("q", [])
        self.assertEqual(stats.count, 0)
        self.assertEqual(stats.mean, 0.0)

    def test_serialises_with_required_keys(self) -> None:
        payload = QuadrantStats.from_scores("q", [0.2, 0.8]).as_dict()
        for key in ("quadrant", "count", "mean", "median", "min", "max"):
            self.assertIn(key, payload)


class ThresholdCandidateTests(unittest.TestCase):
    def test_metrics_are_computed(self) -> None:
        candidate = ThresholdCandidate(0.5, true_positive=8, false_positive=2, true_negative=18, false_negative=2)
        self.assertAlmostEqual(candidate.precision, 0.8, places=5)
        self.assertAlmostEqual(candidate.recall, 0.8, places=5)
        self.assertAlmostEqual(candidate.f1, 0.8, places=5)

    def test_youden_j_for_perfect_separation_is_one(self) -> None:
        candidate = ThresholdCandidate(0.5, true_positive=10, false_positive=0, true_negative=10, false_negative=0)
        self.assertAlmostEqual(candidate.youden_j, 1.0, places=5)

    def test_zero_denominators_are_safe(self) -> None:
        candidate = ThresholdCandidate(0.5, 0, 0, 0, 0)
        self.assertEqual(candidate.precision, 0.0)
        self.assertEqual(candidate.recall, 0.0)
        self.assertEqual(candidate.f1, 0.0)


class CalibrationTests(unittest.TestCase):
    """Calibration must re-measure rather than reuse a synthetic threshold."""

    def _populated(self):
        samples = [
            sample("a1", "c1", template="T1"),
            sample("a2", "c1", template="T2", layout="image_top_text_bottom", color="cool_blue"),
            sample("b1", "c2", template="T1"),
            sample("b2", "c2", template="T2", layout="image_top_text_bottom", color="cool_blue"),
        ]
        labels = {
            "a1": {"creator_id": "c1", "template_id": "T1"},
            "a2": {"creator_id": "c1", "template_id": "T2"},
            "b1": {"creator_id": "c2", "template_id": "T1"},
            "b2": {"creator_id": "c2", "template_id": "T2"},
        }
        return samples, labels

    def test_calibration_reports_all_four_quadrants(self) -> None:
        samples, labels = self._populated()
        report = calibrate_from_samples(
            samples, labels=labels, dataset_id="t", backend_id="b"
        )
        for name in QUADRANTS:
            self.assertIn(name, report.quadrants)

    def test_calibration_reports_required_statistics(self) -> None:
        samples, labels = self._populated()
        report = calibrate_from_samples(
            samples, labels=labels, dataset_id="t", backend_id="b"
        )
        payload = report.as_dict()
        for name in QUADRANTS:
            entry = payload["quadrants"][name]
            for key in ("mean", "median", "min", "max"):
                self.assertIn(key, entry)

    def test_threshold_is_not_the_m2_synthetic_value(self) -> None:
        """The brief forbids reusing 0.90 without re-measuring."""

        samples, labels = self._populated()
        report = calibrate_from_samples(
            samples, labels=labels, dataset_id="t", backend_id="b"
        )
        self.assertNotEqual(report.recommended_threshold, M2_SYNTHETIC_THRESHOLD)
        self.assertIn(
            M2_SYNTHETIC_THRESHOLD, [report.m2_threshold_for_reference]
        )

    def test_report_records_the_selection_method(self) -> None:
        samples, labels = self._populated()
        report = calibrate_from_samples(
            samples, labels=labels, dataset_id="t", backend_id="b"
        )
        self.assertEqual(report.selection_method, "youden_j")

    def test_missing_positive_class_is_rejected(self) -> None:
        one_template = [
            sample("a1", "c1", template="T1"),
            sample("a2", "c1", template="T2", layout="image_top_text_bottom"),
        ]
        labels = {
            "a1": {"creator_id": "c1", "template_id": "T1"},
            "a2": {"creator_id": "c1", "template_id": "T2"},
        }
        with self.assertRaises(CalibrationError):
            calibrate_from_samples(
                one_template, labels=labels, dataset_id="t", backend_id="b"
            )

    def test_missing_label_is_reported(self) -> None:
        samples, labels = self._populated()
        del labels["a2"]
        with self.assertRaises(CalibrationError):
            calibrate_from_samples(
                samples, labels=labels, dataset_id="t", backend_id="b"
            )

    def test_report_renders(self) -> None:
        samples, labels = self._populated()
        report = calibrate_from_samples(
            samples, labels=labels, dataset_id="t", backend_id="b"
        )
        text = report.render()
        self.assertIn("recommended threshold", text)

    def test_report_writes_json(self) -> None:
        samples, labels = self._populated()
        report = calibrate_from_samples(
            samples, labels=labels, dataset_id="t", backend_id="b"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = write_calibration(report, Path(directory) / "similarity_distribution.json")
            self.assertTrue(path.is_file())
            import json

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("quadrants", payload)
            self.assertIn("recommended_threshold", payload)

    def test_calibration_is_deterministic(self) -> None:
        samples, labels = self._populated()
        first = calibrate_from_samples(samples, labels=labels, dataset_id="t", backend_id="b")
        second = calibrate_from_samples(samples, labels=labels, dataset_id="t", backend_id="b")
        self.assertEqual(first.recommended_threshold, second.recommended_threshold)


class ClusteringReproducibilityTests(unittest.TestCase):
    """Clustering must be reproducible and label-independent."""

    def _population(self):
        same = [
            sample("s1", "c1", template="T1"),
            sample("s2", "c2", template="T1"),
            sample("s3", "c3", template="T1"),
        ]
        other = [
            sample("o1", "c4", template="T2", layout="image_top_text_bottom", color="cool_blue"),
            sample("o2", "c5", template="T2", layout="image_top_text_bottom", color="cool_blue"),
            sample("o3", "c6", template="T2", layout="image_top_text_bottom", color="cool_blue"),
        ]
        return same, other

    def test_clustering_is_reproducible(self) -> None:
        same, other = self._population()
        first = discover_templates(same + other)
        second = discover_templates(same + other)
        self.assertEqual(
            [c.cluster_id for c in first.clusters], [c.cluster_id for c in second.clusters]
        )

    def test_clustering_is_order_independent(self) -> None:
        same, other = self._population()
        forward = discover_templates(same + other)
        backward = discover_templates(list(reversed(other + same)))
        self.assertEqual(
            [c.cluster_id for c in forward.clusters],
            [c.cluster_id for c in backward.clusters],
        )

    def test_similar_samples_group_and_different_separate(self) -> None:
        same, other = self._population()
        discovery = discover_templates(same + other)
        self.assertEqual(len(discovery.clusters), 2)
        self.assertEqual(len(discovery.templates()), 2)

    def test_discovery_reads_no_family_labels(self) -> None:
        import inspect

        from multimodal_creator.clustering import template_discovery

        source = inspect.getsource(template_discovery.discover_templates)
        for token in ("template_id", "layout_family", "expected_"):
            self.assertNotIn(token, source)

    def test_threshold_is_honoured(self) -> None:
        same, other = self._population()
        high = discover_templates(same + other, threshold=0.999)
        low = discover_templates(same + other, threshold=0.0)
        self.assertLessEqual(len(high.clusters), len(low.clusters))


class PatternExtractionTests(unittest.TestCase):
    """Patterns must abstract strategy, never copy material."""

    def _cluster_and_samples(self):
        members = [
            sample("m1", "c1", template="T1"),
            sample("m2", "c2", template="T1"),
            sample("m3", "c3", template="T1"),
        ]
        discovery = discover_templates(members)
        return discovery.clusters[0], {s.sample_id: s for s in members}

    def test_pattern_is_distilled(self) -> None:
        cluster, samples = self._cluster_and_samples()
        pattern = distill_cluster(cluster, samples)
        self.assertIsInstance(pattern, CreatorVisualPattern)

    def test_pattern_exposes_layout_strategy(self) -> None:
        cluster, samples = self._cluster_and_samples()
        pattern = distill_cluster(cluster, samples)
        self.assertTrue(pattern.layout_strategy)

    def test_pattern_exposes_hierarchy(self) -> None:
        cluster, samples = self._cluster_and_samples()
        pattern = distill_cluster(cluster, samples)
        self.assertIn("attention_entry", pattern.hierarchy)

    def test_pattern_exposes_style_traits(self) -> None:
        cluster, samples = self._cluster_and_samples()
        pattern = distill_cluster(cluster, samples)
        self.assertTrue(pattern.style_pattern)

    def test_pattern_carries_support_and_creators(self) -> None:
        cluster, samples = self._cluster_and_samples()
        pattern = distill_cluster(cluster, samples)
        self.assertEqual(pattern.support, 3)
        self.assertEqual(len(pattern.creator_ids), 3)

    def test_pattern_records_evidence(self) -> None:
        cluster, samples = self._cluster_and_samples()
        pattern = distill_cluster(cluster, samples)
        self.assertIn("threshold", pattern.evidence)
        self.assertIn("recurring", pattern.evidence)

    def test_pattern_contains_no_pixel_or_asset_data(self) -> None:
        """The whole point: strategy, not material."""

        cluster, samples = self._cluster_and_samples()
        payload = distill_cluster(cluster, samples).as_dict()
        serialised = str(payload).lower()
        for forbidden in (".png", ".jpg", "base64", "pixels", "asset_reference", "bitmap"):
            self.assertNotIn(forbidden, serialised)
        self.assertNotIn("path", payload)

    def test_pattern_needs_no_source_image(self) -> None:
        """A pattern is constructible from structure alone."""

        cluster, samples = self._cluster_and_samples()
        pattern = distill_cluster(cluster, samples)
        self.assertEqual(pattern.support, len(cluster.member_ids))

    def test_empty_cluster_is_rejected(self) -> None:
        cluster, _samples = self._cluster_and_samples()
        with self.assertRaises(PatternDistillationError):
            distill_cluster(cluster, {})

    def test_distill_patterns_returns_all_clusters(self) -> None:
        members = [
            sample("m1", "c1", template="T1"),
            sample("m2", "c2", template="T1"),
            sample("m3", "c3", template="T1"),
            sample("n1", "c4", template="T2", layout="image_top_text_bottom", color="cool_blue"),
            sample("n2", "c5", template="T2", layout="image_top_text_bottom", color="cool_blue"),
            sample("n3", "c6", template="T2", layout="image_top_text_bottom", color="cool_blue"),
        ]
        discovery = discover_templates(members)
        patterns = distill_patterns(discovery, members)
        self.assertEqual(len(patterns), len(discovery.clusters))

    def test_only_recurring_filter(self) -> None:
        members = [
            sample("m1", "c1", template="T1"),
            sample("m2", "c2", template="T1"),
            sample("n1", "c4", template="T2", layout="image_top_text_bottom", color="cool_blue"),
        ]
        discovery = discover_templates(members)
        all_patterns = distill_patterns(discovery, members)
        recurring = distill_patterns(discovery, members, only_recurring=True)
        self.assertLessEqual(len(recurring), len(all_patterns))

    def test_patterns_render(self) -> None:
        cluster, samples = self._cluster_and_samples()
        text = render_patterns([distill_cluster(cluster, samples)])
        self.assertIn("creator visual patterns", text)

    def test_pattern_serialises(self) -> None:
        cluster, samples = self._cluster_and_samples()
        payload = distill_cluster(cluster, samples).as_dict()
        for key in ("layout_strategy", "hierarchy", "style_pattern", "region_recipe"):
            self.assertIn(key, payload)


class NegativeCaseTests(unittest.TestCase):
    """Negative behaviour must be explicit, not incidental."""

    def test_structurally_different_samples_do_not_merge(self) -> None:
        left = sample("a", "c1", template="T1")
        right = sample(
            "b",
            "c2",
            template="T2",
            layout="image_top_text_bottom",
            color="cool_blue",
            regions=(
                region("bg", "background", 0.0, 0.0, 1.0, 1.0, 0),
                region("s", "subject", 0.1, 0.05, 0.8, 0.5, 1),
                region("t", "title", 0.1, 0.62, 0.8, 0.18, 1),
            ),
        )
        discovery = discover_templates([left, right])
        self.assertEqual(discovery.clusters, ())

    def test_identical_instances_score_maximally(self) -> None:
        """Two instances that declare the same typography score exactly 1.0.

        Note the qualifier. M2's similarity contract scores an *undeclared*
        comparable field as neutral (0.5) rather than as agreement, on the
        reasoning that "not declared" is weaker evidence than "agrees". When
        ``text_style`` is absent on both sides, an otherwise identical pair
        therefore tops out at 0.955 rather than 1.0.

        That is M2 behaviour and M3 is forbidden from changing it, so the test
        pins the real ceiling instead of asserting a maximum the contract does
        not promise. The consequence for M3 is significant and is recorded in
        the phase report: observations that cannot evidence typography have a
        *lower attainable similarity ceiling*, which is one reason M2's 0.90
        threshold transfers poorly to real observations.
        """

        from multimodal_creator.extraction.visual_sample import TextStyleSpec

        declared = sample("a", "c1", template="T1")
        declared = VisualSample(
            sample_id=declared.sample_id,
            regions=declared.regions,
            color_family=declared.color_family,
            subject=declared.subject,
            provenance=declared.provenance,
            layout_template_class=declared.layout_template_class,
            alignment=declared.alignment,
            palette_relation=declared.palette_relation,
            placement=declared.placement,
            text_style=TextStyleSpec("two_level", 2),
        )
        import copy

        self.assertEqual(pairwise_similarity(declared, copy.deepcopy(declared)).score, 1.0)

    def test_undeclared_typography_lowers_the_attainable_ceiling(self) -> None:
        """Documented M2 constraint, pinned so a change is noticed."""

        import copy

        undeclared = sample("a", "c1", template="T1")
        self.assertIsNone(undeclared.text_style)
        score = pairwise_similarity(undeclared, copy.deepcopy(undeclared)).score
        self.assertAlmostEqual(score, 0.955, places=3)
        self.assertLess(score, 1.0)

    def test_two_samples_of_one_template_score_very_high(self) -> None:
        left = sample("a", "c1", template="T1")
        right = sample("b", "c2", template="T1")
        self.assertGreater(pairwise_similarity(left, right).score, 0.95)

    def test_constant_similarity_is_impossible(self) -> None:
        """A degenerate always-1.0 similarity would pass every positive case."""

        left = sample("a", "c1", template="T1")
        right = sample(
            "b",
            "c2",
            template="T2",
            layout="image_top_text_bottom",
            color="cool_blue",
            regions=(
                region("bg", "background", 0.0, 0.0, 1.0, 1.0, 0),
                region("s", "subject", 0.1, 0.05, 0.8, 0.5, 1),
                region("t", "title", 0.1, 0.62, 0.8, 0.18, 1),
            ),
        )
        self.assertLess(pairwise_similarity(left, right).score, 0.95)

    def test_undetected_prediction_counts_as_a_miss(self) -> None:
        metrics = detection_metrics({"a": None}, {"a": "T1"})
        self.assertEqual(metrics.correct, 0)
        self.assertEqual(metrics.micro_recall, 0.0)

    def test_unclustered_samples_count_against_recall(self) -> None:
        metrics = clustering_metrics(
            {"a": "c1", "b": None},
            {"a": "T1", "b": "T1"},
        )
        self.assertEqual(metrics.false_negative, 1)
        self.assertEqual(metrics.recall, 0.0)

    def test_predicted_class_outside_the_label_set_is_a_false_positive(self) -> None:
        metrics = detection_metrics({"a": "novel"}, {"a": "T1"})
        self.assertEqual(metrics.correct, 0)
        self.assertGreater(metrics.per_family["novel"]["false_positive"], 0)


class EvaluationMetricTests(unittest.TestCase):
    """The required metrics must be computed correctly."""

    def test_perfect_detection(self) -> None:
        metrics = detection_metrics({"a": "T1", "b": "T2"}, {"a": "T1", "b": "T2"})
        self.assertEqual(metrics.micro_f1, 1.0)
        self.assertEqual(metrics.macro_f1, 1.0)

    def test_detection_precision_and_recall(self) -> None:
        metrics = detection_metrics(
            {"a": "T1", "b": "T2", "c": "T1"}, {"a": "T1", "b": "T2", "c": "T2"}
        )
        self.assertEqual(metrics.correct, 2)
        self.assertLess(metrics.micro_f1, 1.0)

    def test_clustering_precision_recall(self) -> None:
        metrics = clustering_metrics(
            {"a": "x", "b": "x", "c": "y"},
            {"a": "T1", "b": "T1", "c": "T2"},
        )
        self.assertEqual(metrics.precision, 1.0)
        self.assertEqual(metrics.recall, 1.0)

    def test_clustering_penalises_merging_different_families(self) -> None:
        metrics = clustering_metrics(
            {"a": "x", "b": "x"}, {"a": "T1", "b": "T2"}
        )
        self.assertEqual(metrics.false_positive, 1)
        self.assertEqual(metrics.precision, 0.0)

    def test_pattern_purity_and_coverage(self) -> None:
        class FakePattern:
            pattern_id = "p1"
            member_ids = ("a", "b")
            layout_strategy = ("headline_top",)
            hierarchy = ("attention_entry",)

        metrics = pattern_metrics([FakePattern()], {"a": "T1", "b": "T1", "c": "T2"})
        self.assertEqual(metrics.purity, 1.0)
        self.assertAlmostEqual(metrics.coverage, 2 / 3, places=5)

    def test_pattern_metrics_note_that_it_is_not_human_agreement(self) -> None:
        payload = pattern_metrics([], {"a": "T1"}).as_dict()
        self.assertIn("measurement_note", payload)
        self.assertIn("not human agreement", payload["measurement_note"])

    def test_f1_is_harmonic_mean(self) -> None:
        candidate = ThresholdCandidate(0.5, 6, 2, 10, 4)
        expected = 2 * candidate.precision * candidate.recall / (
            candidate.precision + candidate.recall
        )
        self.assertAlmostEqual(candidate.f1, round(expected, 6), places=6)


if __name__ == "__main__":
    unittest.main()
