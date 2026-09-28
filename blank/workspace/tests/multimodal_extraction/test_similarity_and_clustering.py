"""Similarity contract and template discovery tests (Phase M2)."""

from __future__ import annotations

import unittest

from multimodal_creator.clustering import (
    DEFAULT_SIMILARITY_THRESHOLD,
    RECURRENCE_MIN,
    TemplateClusterError,
    discover_templates,
)
from multimodal_creator.extraction import (
    RegionSpec,
    SampleProvenance,
    SubjectSpec,
    TextStyleSpec,
    VisualSample,
)
from multimodal_creator.similarity import (
    DIMENSIONS,
    PROVENANCE_MODES,
    SCORE_PRECISION,
    SimilarityContractError,
    dimension_weights,
    geometry_dimension,
    pairwise_similarity,
    similarity_matrix,
    structure_dimension,
)


def region(region_id, role, x, y, w, h, layer=0):
    return RegionSpec(region_id, role, {"x": x, "y": y, "w": w, "h": h}, layer)


LEFT_TEXT_RIGHT_IMAGE = (
    region("bg", "background", 0.0, 0.0, 1.0, 1.0, 0),
    region("title", "title", 0.06, 0.10, 0.40, 0.20, 1),
    region("img", "subject", 0.55, 0.10, 0.40, 0.60, 1),
)

IMAGE_TOP_TEXT_BOTTOM = (
    region("bg", "background", 0.0, 0.0, 1.0, 1.0, 0),
    region("img", "subject", 0.10, 0.05, 0.80, 0.50, 1),
    region("title", "title", 0.10, 0.62, 0.80, 0.18, 1),
)

THREE_CARD = (
    region("bg", "background", 0.0, 0.0, 1.0, 1.0, 0),
    region("title", "title", 0.05, 0.04, 0.90, 0.12, 1),
    region("c1", "body", 0.05, 0.22, 0.28, 0.55, 1),
    region("c2", "body", 0.36, 0.22, 0.28, 0.55, 1),
    region("c3", "body", 0.67, 0.22, 0.28, 0.55, 1),
)


def sample(
    sample_id,
    regions=LEFT_TEXT_RIGHT_IMAGE,
    *,
    creator="creator-1",
    layout="image_left_text_right",
    color="warm_red",
    palette="high_contrast_accent",
    subject="human_figure",
    salience="subject_dominant",
    alignment="left",
    density="balanced",
    placement="side_panel",
    text_style=None,
):
    return VisualSample(
        sample_id=sample_id,
        regions=tuple(regions),
        color_family=color,
        subject=SubjectSpec(subject, salience),
        provenance=SampleProvenance(creator),
        layout_template_class=layout,
        alignment=alignment,
        composition_density=density,
        palette_relation=palette,
        placement=placement,
        text_style=text_style if text_style is not None else TextStyleSpec("two_level", 2),
    )


def jitter(regions, *, scale, shift):
    def box(b):
        x = min(max(b["x"] * scale + shift, 0.0), 1.0 - b["w"] * scale)
        y = min(max(b["y"] * scale + shift, 0.0), 1.0 - b["h"] * scale)
        return {
            "x": round(x, 4),
            "y": round(y, 4),
            "w": round(b["w"] * scale, 4),
            "h": round(b["h"] * scale, 4),
        }

    return tuple(
        RegionSpec(r.region_id, r.role, box(r.box), r.layer_order) for r in regions
    )


class SimilarityContractShapeTests(unittest.TestCase):
    """The contract's own invariants."""

    def test_weights_sum_to_one(self) -> None:
        self.assertAlmostEqual(sum(dimension_weights().values()), 1.0, places=9)

    def test_four_dimensions_are_declared(self) -> None:
        self.assertEqual(
            set(DIMENSIONS), {"geometry", "structure", "style", "asset"}
        )

    def test_provenance_modes_are_declared(self) -> None:
        self.assertIn("cross_provenance", PROVENANCE_MODES)
        self.assertIn("provenance_only", PROVENANCE_MODES)

    def test_unknown_provenance_mode_is_rejected(self) -> None:
        with self.assertRaises(SimilarityContractError):
            pairwise_similarity(sample("A"), sample("B"), provenance_mode="vibes")

    def test_score_is_decomposable_into_contributions(self) -> None:
        result = pairwise_similarity(sample("A"), sample("B", color="cool_blue"))
        total = sum(item.weighted_score for item in result.contributions)
        self.assertAlmostEqual(total, result.score, places=6)

    def test_result_exposes_every_dimension(self) -> None:
        result = pairwise_similarity(sample("A"), sample("B"))
        for name in DIMENSIONS:
            self.assertIsNotNone(result.dimension(name))

    def test_explanation_renders_without_error(self) -> None:
        text = pairwise_similarity(sample("A"), sample("B")).explain()
        self.assertIn("similarity=", text)

    def test_result_serialises(self) -> None:
        payload = pairwise_similarity(sample("A"), sample("B")).as_dict()
        self.assertIn("contributions", payload)
        self.assertIn("difference_codes", payload)

    def test_scores_are_rounded_to_contract_precision(self) -> None:
        result = pairwise_similarity(sample("A"), sample("B", color="cool_teal"))
        self.assertEqual(result.score, round(result.score, SCORE_PRECISION))


class SimilarityDeterminismTests(unittest.TestCase):
    """Same inputs must always give the same number."""

    def test_repeated_comparison_is_identical(self) -> None:
        left, right = sample("A"), sample("B", color="cool_blue")
        self.assertEqual(
            pairwise_similarity(left, right).score,
            pairwise_similarity(left, right).score,
        )

    def test_comparison_is_symmetric(self) -> None:
        left, right = sample("A"), sample("B", color="cool_blue")
        self.assertEqual(
            pairwise_similarity(left, right).score,
            pairwise_similarity(right, left).score,
        )

    def test_matrix_is_order_independent(self) -> None:
        a, b, c = sample("A"), sample("B", color="cool_blue"), sample("C", color="cool_teal")
        forward = similarity_matrix([a, b, c])
        backward = similarity_matrix([c, b, a])
        self.assertEqual(
            {key: value.score for key, value in forward.items()},
            {key: value.score for key, value in backward.items()},
        )

    def test_matrix_computes_each_pair_once(self) -> None:
        a, b, c = sample("A"), sample("B"), sample("C")
        matrix = similarity_matrix([a, b, c])
        self.assertEqual(len(matrix), 3)
        self.assertIn(("A", "B"), matrix)
        self.assertNotIn(("B", "A"), matrix)

    def test_matrix_rejects_duplicate_ids(self) -> None:
        with self.assertRaises(SimilarityContractError):
            similarity_matrix([sample("dup"), sample("dup")])

    def test_region_declaration_order_does_not_matter(self) -> None:
        a = sample("A", LEFT_TEXT_RIGHT_IMAGE)
        reversed_regions = tuple(reversed(LEFT_TEXT_RIGHT_IMAGE))
        b = sample("B", reversed_regions)
        self.assertEqual(pairwise_similarity(a, b).score, 1.0)


class SimilarTemplateTests(unittest.TestCase):
    """Similar templates must score high."""

    def test_identical_structure_scores_one(self) -> None:
        self.assertEqual(pairwise_similarity(sample("A"), sample("B")).score, 1.0)

    def test_jittered_same_layout_stays_above_threshold(self) -> None:
        result = pairwise_similarity(
            sample("A"), sample("B", jitter(LEFT_TEXT_RIGHT_IMAGE, scale=0.97, shift=0.01))
        )
        self.assertGreaterEqual(result.score, DEFAULT_SIMILARITY_THRESHOLD)

    def test_three_card_variant_stays_above_threshold(self) -> None:
        result = pairwise_similarity(
            sample("A", THREE_CARD, layout="three_card", density="dense"),
            sample(
                "B",
                jitter(THREE_CARD, scale=0.98, shift=0.005),
                layout="three_card",
                density="dense",
            ),
        )
        self.assertGreaterEqual(result.score, DEFAULT_SIMILARITY_THRESHOLD)

    def test_color_change_alone_does_not_break_the_family(self) -> None:
        result = pairwise_similarity(sample("A"), sample("B", color="cool_blue"))
        self.assertGreater(result.score, 0.80)
        self.assertIn("color_family_mismatch", result.codes())

    def test_subject_change_alone_does_not_break_the_family(self) -> None:
        result = pairwise_similarity(
            sample("A"), sample("B", subject="product_object", color="cool_blue")
        )
        self.assertGreater(result.score, 0.75)
        self.assertIn("subject_class_mismatch", result.codes())


class DifferentTemplateTests(unittest.TestCase):
    """Different templates must score low enough to stay apart."""

    def test_left_text_vs_top_text_is_below_threshold(self) -> None:
        result = pairwise_similarity(
            sample("A"), sample("B", IMAGE_TOP_TEXT_BOTTOM, layout="image_top_text_bottom", alignment=None)
        )
        self.assertLess(result.score, DEFAULT_SIMILARITY_THRESHOLD)
        self.assertIn("layout_template_class_mismatch", result.codes())

    def test_three_card_vs_single_column_is_below_threshold(self) -> None:
        result = pairwise_similarity(
            sample("A", THREE_CARD, layout="three_card", density="dense"),
            sample("B", layout="single_column", density="sparse"),
        )
        self.assertLess(result.score, DEFAULT_SIMILARITY_THRESHOLD)

    def test_same_declared_class_mirrored_geometry_is_flagged(self) -> None:
        """A declared-class agreement must not hide a geometric disagreement."""

        mirrored = (
            region("bg", "background", 0.0, 0.0, 1.0, 1.0, 0),
            region("title", "title", 0.50, 0.70, 0.42, 0.18, 1),
            region("img", "subject", 0.05, 0.05, 0.42, 0.60, 1),
        )
        result = pairwise_similarity(
            sample("A"), sample("B", mirrored, alignment="right")
        )
        self.assertIn("region_geometry_differs", result.codes())
        self.assertLess(result.score, 1.0)

    def test_graph_difference_is_reported(self) -> None:
        result = pairwise_similarity(
            sample("A"), sample("B", IMAGE_TOP_TEXT_BOTTOM, layout="image_top_text_bottom", alignment=None)
        )
        self.assertIn("layout_graph_differs", result.codes())

    def test_structure_dimension_separates_layouts(self) -> None:
        left_score, _ = structure_dimension(
            sample("A"), sample("B", IMAGE_TOP_TEXT_BOTTOM, layout="image_top_text_bottom", alignment=None)
        )
        same_score, _ = structure_dimension(sample("A"), sample("C"))
        self.assertLess(left_score, same_score)

    def test_geometry_dimension_separates_layouts(self) -> None:
        different, _ = geometry_dimension(
            sample("A"), sample("B", IMAGE_TOP_TEXT_BOTTOM, layout="image_top_text_bottom", alignment=None)
        )
        same, _ = geometry_dimension(sample("A"), sample("C"))
        self.assertLess(different, same)

    def test_missing_region_role_is_charged(self) -> None:
        sparse = (
            region("bg", "background", 0.0, 0.0, 1.0, 1.0, 0),
            region("title", "title", 0.06, 0.1, 0.4, 0.2, 1),
        )
        result = pairwise_similarity(sample("A"), sample("B", sparse))
        self.assertLess(result.score, 1.0)
        # B lacks the ``subject`` role that A declares, so it is absent on the
        # right-hand sample.
        self.assertIn("region_role_absent_on_right", result.codes())


class ProvenanceTests(unittest.TestCase):
    """Same-creator agreement is not independent evidence."""

    def test_cross_provenance_suppresses_same_creator_pairs(self) -> None:
        result = pairwise_similarity(
            sample("A", creator="solo"),
            sample("B", creator="solo"),
            provenance_mode="cross_provenance",
        )
        self.assertFalse(result.comparable)
        self.assertIn("provenance_not_comparable", result.codes())

    def test_cross_provenance_allows_different_creators(self) -> None:
        result = pairwise_similarity(
            sample("A", creator="one"),
            sample("B", creator="two"),
            provenance_mode="cross_provenance",
        )
        self.assertTrue(result.comparable)

    def test_provenance_only_suppresses_different_creators(self) -> None:
        result = pairwise_similarity(
            sample("A", creator="one"),
            sample("B", creator="two"),
            provenance_mode="provenance_only",
        )
        self.assertFalse(result.comparable)

    def test_agnostic_mode_compares_everything(self) -> None:
        result = pairwise_similarity(
            sample("A", creator="one"), sample("B", creator="two")
        )
        self.assertTrue(result.comparable)

    def test_suppressed_result_scores_zero_and_says_why(self) -> None:
        result = pairwise_similarity(
            sample("A", creator="solo"),
            sample("B", creator="solo"),
            provenance_mode="cross_provenance",
        )
        self.assertEqual(result.score, 0.0)
        self.assertIsNotNone(result.suppressed_reason)


class TemplateDiscoveryTests(unittest.TestCase):
    """Clusters must be discovered, not declared."""

    def _two_families(self):
        left_family = [
            sample("A1", creator="c1"),
            sample("A2", creator="c2"),
            sample("A3", creator="c3"),
        ]
        top_family = [
            sample("B1", IMAGE_TOP_TEXT_BOTTOM, creator="c4", layout="image_top_text_bottom", alignment=None),
            sample("B2", IMAGE_TOP_TEXT_BOTTOM, creator="c5", layout="image_top_text_bottom", alignment=None),
            sample("B3", IMAGE_TOP_TEXT_BOTTOM, creator="c6", layout="image_top_text_bottom", alignment=None),
        ]
        return left_family, top_family

    def test_similar_samples_cluster_together(self) -> None:
        left_family, _ = self._two_families()
        discovery = discover_templates(left_family)
        self.assertEqual(len(discovery.clusters), 1)
        self.assertEqual(discovery.clusters[0].member_ids, ("A1", "A2", "A3"))

    def test_different_samples_stay_separate(self) -> None:
        left_family, top_family = self._two_families()
        discovery = discover_templates(left_family + top_family)
        self.assertEqual(len(discovery.clusters), 2)
        self.assertNotEqual(
            discovery.cluster_for("A1").cluster_id,
            discovery.cluster_for("B1").cluster_id,
        )

    def test_three_members_are_marked_recurring(self) -> None:
        left_family, _ = self._two_families()
        discovery = discover_templates(left_family)
        self.assertTrue(discovery.clusters[0].evidence.recurring)

    def test_two_members_are_not_marked_recurring(self) -> None:
        discovery = discover_templates([sample("A1"), sample("A2")])
        self.assertFalse(discovery.clusters[0].evidence.recurring)
        self.assertGreaterEqual(RECURRENCE_MIN, 3)

    def test_cluster_records_threshold_and_evidence(self) -> None:
        left_family, _ = self._two_families()
        discovery = discover_templates(left_family, threshold=0.85)
        evidence = discovery.clusters[0].evidence
        self.assertEqual(evidence.threshold, 0.85)
        self.assertEqual(evidence.creator_count, 3)
        self.assertGreaterEqual(evidence.mean_similarity, 0.85)

    def test_cluster_records_member_ids(self) -> None:
        left_family, _ = self._two_families()
        discovery = discover_templates(left_family)
        self.assertEqual(set(discovery.clusters[0].member_ids), {"A1", "A2", "A3"})

    def test_cluster_records_dominant_layout_class(self) -> None:
        left_family, _ = self._two_families()
        discovery = discover_templates(left_family)
        self.assertEqual(
            discovery.clusters[0].evidence.dominant_layout_class,
            "image_left_text_right",
        )

    def test_cluster_ids_are_stable_across_input_order(self) -> None:
        left_family, top_family = self._two_families()
        forward = discover_templates(left_family + top_family)
        backward = discover_templates(list(reversed(top_family + left_family)))
        self.assertEqual(
            [c.cluster_id for c in forward.clusters],
            [c.cluster_id for c in backward.clusters],
        )

    def test_discovery_does_not_mutate_samples(self) -> None:
        left_family, _ = self._two_families()
        before = list(left_family)
        discover_templates(left_family)
        self.assertEqual(list(left_family), before)

    def test_merge_steps_are_recorded(self) -> None:
        left_family, _ = self._two_families()
        discovery = discover_templates(left_family)
        self.assertTrue(discovery.merge_steps)
        for step in discovery.merge_steps:
            self.assertGreaterEqual(step.average_similarity, discovery.threshold)

    def test_merge_steps_carry_justifying_pairs(self) -> None:
        left_family, _ = self._two_families()
        discovery = discover_templates(left_family)
        for step in discovery.merge_steps:
            self.assertTrue(step.justifying_pairs)
            for _left, _right, score in step.justifying_pairs:
                self.assertGreaterEqual(score, 0.0)

    def test_cross_provenance_blocks_single_creator_clusters(self) -> None:
        same_person = [
            sample("A1", creator="solo"),
            sample("A2", creator="solo"),
            sample("A3", creator="solo"),
        ]
        discovery = discover_templates(same_person, provenance_mode="cross_provenance")
        self.assertEqual(discovery.clusters, ())
        self.assertTrue(discovery.non_comparable_pairs)

    def test_agnostic_mode_allows_single_creator_clusters(self) -> None:
        same_person = [
            sample("A1", creator="solo"),
            sample("A2", creator="solo"),
            sample("A3", creator="solo"),
        ]
        discovery = discover_templates(same_person, provenance_mode="provenance_agnostic")
        self.assertEqual(len(discovery.clusters), 1)

    def test_high_threshold_yields_no_clusters(self) -> None:
        discovery = discover_templates(
            [sample("A", color="warm_red"), sample("B", color="cool_blue")],
            threshold=0.999,
        )
        self.assertEqual(discovery.clusters, ())

    def test_low_threshold_merges_everything(self) -> None:
        discovery = discover_templates(
            [
                sample("A", IMAGE_TOP_TEXT_BOTTOM, layout="image_top_text_bottom", alignment=None),
                sample("B", color="cool_blue"),
            ],
            threshold=0.0,
        )
        self.assertEqual(len(discovery.clusters), 1)

    def test_empty_input_is_rejected(self) -> None:
        with self.assertRaises(TemplateClusterError):
            discover_templates([])

    def test_duplicate_ids_are_rejected(self) -> None:
        with self.assertRaises(TemplateClusterError):
            discover_templates([sample("dup"), sample("dup")])

    def test_invalid_threshold_is_rejected(self) -> None:
        with self.assertRaises(TemplateClusterError):
            discover_templates([sample("A")], threshold=1.5)

    def test_unknown_provenance_mode_is_rejected(self) -> None:
        with self.assertRaises(TemplateClusterError):
            discover_templates([sample("A")], provenance_mode="vibes")

    def test_min_cluster_size_filters_singletons(self) -> None:
        lone = sample("LONE", IMAGE_TOP_TEXT_BOTTOM, layout="image_top_text_bottom", alignment=None)
        left_family = [sample("A1", creator="c1"), sample("A2", creator="c2")]
        discovery = discover_templates(left_family + [lone], min_cluster_size=2)
        self.assertEqual(len(discovery.clusters), 1)
        self.assertEqual(set(discovery.clusters[0].member_ids), {"A1", "A2"})

    def test_summary_renders(self) -> None:
        left_family, _ = self._two_families()
        text = discover_templates(left_family).summarise()
        self.assertIn("threshold", text)

    def test_result_serialises(self) -> None:
        left_family, _ = self._two_families()
        payload = discover_templates(left_family).as_dict()
        self.assertIn("clusters", payload)
        self.assertIn("threshold", payload)

    def test_templates_only_returns_recurring_clusters(self) -> None:
        left_family, _ = self._two_families()
        pair = [sample("P1", creator="x"), sample("P2", creator="y")]
        discovery = discover_templates(left_family + pair)
        for cluster in discovery.templates():
            self.assertTrue(cluster.evidence.recurring)


if __name__ == "__main__":
    unittest.main()
