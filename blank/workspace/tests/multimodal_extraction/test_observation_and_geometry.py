"""Observation schema and geometry normalisation tests (Phase M2)."""

from __future__ import annotations

import unittest

from multimodal_creator import STRUCTURAL_EVIDENCE
from multimodal_creator.extraction import (
    CrossModalCandidate,
    MockExtractionError,
    MockVisionExtractor,
    ObservationProducer,
    RegionSpec,
    SampleProvenance,
    SubjectSpec,
    TextStyleSpec,
    VisualSample,
    annotation_to_observation,
    candidates_from_observation,
    candidates_from_sample,
    contrast_role_for,
    derive_evidence_kinds,
    geometric_relation,
)
from multimodal_creator.extraction.cross_modal_candidates import GEOMETRIC_RELATIONS
from multimodal_creator.extraction.visual_sample import (
    COLOR_FAMILIES,
    NEGATIVE_SPACE,
    SUBJECT_SALIENCE,
)


def region(region_id, role, x, y, w, h, layer=0):
    return RegionSpec(region_id, role, {"x": x, "y": y, "w": w, "h": h}, layer)


def sample(sample_id="S1", creator="creator-1", **overrides):
    fields = {
        "sample_id": sample_id,
        "regions": (
            region("bg", "background", 0.0, 0.0, 1.0, 1.0, 0),
            region("title", "title", 0.06, 0.10, 0.40, 0.20, 1),
            region("img", "subject", 0.55, 0.10, 0.40, 0.60, 1),
        ),
        "color_family": "warm_red",
        "subject": SubjectSpec("human_figure", "subject_dominant"),
        "provenance": SampleProvenance(creator),
        "layout_template_class": "image_left_text_right",
        "alignment": "left",
        "palette_relation": "high_contrast_accent",
        "text_style": TextStyleSpec("two_level", 2),
        "placement": "side_panel",
    }
    fields.update(overrides)
    return VisualSample(**fields)


class RegionGeometryTests(unittest.TestCase):
    """Geometry must be normalised and validated, not trusted."""

    def test_valid_region_is_accepted(self) -> None:
        spec = region("r", "title", 0.1, 0.2, 0.3, 0.4)
        self.assertEqual(spec.role, "title")

    def test_negative_coordinate_is_rejected(self) -> None:
        with self.assertRaises(MockExtractionError):
            region("r", "title", -0.1, 0.0, 0.5, 0.5)

    def test_coordinate_above_one_is_rejected(self) -> None:
        with self.assertRaises(MockExtractionError):
            region("r", "title", 0.0, 0.0, 1.2, 0.5)

    def test_box_extending_past_frame_is_rejected(self) -> None:
        with self.assertRaises(MockExtractionError):
            region("r", "title", 0.8, 0.0, 0.5, 0.5)

    def test_zero_extent_is_rejected(self) -> None:
        with self.assertRaises(MockExtractionError):
            region("r", "title", 0.1, 0.1, 0.0, 0.5)

    def test_unknown_role_is_rejected(self) -> None:
        with self.assertRaises(MockExtractionError):
            region("r", "canvas", 0.1, 0.1, 0.5, 0.5)

    def test_non_integer_layer_order_is_rejected(self) -> None:
        with self.assertRaises(MockExtractionError):
            RegionSpec("r", "title", {"x": 0.1, "y": 0.1, "w": 0.5, "h": 0.5}, 1.5)

    def test_missing_box_component_is_rejected(self) -> None:
        with self.assertRaises(MockExtractionError):
            RegionSpec("r", "title", {"x": 0.1, "y": 0.1, "w": 0.5}, 0)

    def test_layering_is_preserved_through_extraction(self) -> None:
        observation = MockVisionExtractor().extract(sample())
        layers = {r["region_id"]: r["layer_order"] for r in observation.regions}
        self.assertEqual(layers["bg"], 0)
        self.assertEqual(layers["title"], 1)
        self.assertEqual(layers["img"], 1)

    def test_layer_ordering_is_reported_as_dominance_evidence(self) -> None:
        observation = MockVisionExtractor().extract(sample())
        self.assertIn("dominance_order", observation.evidence_kinds)

    def test_single_layer_sample_does_not_claim_dominance_order(self) -> None:
        flat = sample(
            regions=(
                region("a", "title", 0.0, 0.0, 1.0, 0.3),
                region("b", "body", 0.0, 0.4, 1.0, 0.3),
            )
        )
        observation = MockVisionExtractor().extract(flat)
        self.assertNotIn("dominance_order", observation.evidence_kinds)


class VisualSampleValidationTests(unittest.TestCase):
    def test_geometry_units_are_normalized(self) -> None:
        from multimodal_creator import build_multimodal_artifact, structure_from_metadata

        batch = ObservationProducer().produce([sample()])
        artifact = build_multimodal_artifact(
            {
                "artifact_version": "1.0.0",
                "plugin": {"name": "p", "version": "1", "domain": "d", "creator_target": "t"},
                "topic_candidate": [],
                "content_template": [],
                "knowledge_unit": [],
                "style_pattern": [],
                "domain_extension": {},
                "risk_constraints": [],
                "evaluation_result": {
                    "common": {"score": 0.0, "checks": {}, "passed": True},
                    "domain": {},
                },
            },
            structures=[
                structure_from_metadata(
                    "S1",
                    "image",
                    {"modalities": ["visual"], "multimodal_roles": ["visual_style_source"]},
                )
            ],
            observations=batch.observations,
            visual_capability="observed",
        )
        self.assertEqual(
            artifact["multimodal_envelope"]["geometry_units"], "normalized_xywh"
        )

    def test_unknown_color_family_is_rejected(self) -> None:
        with self.assertRaises(MockExtractionError):
            sample(color_family="iridescent")

    def test_unknown_subject_class_is_rejected(self) -> None:
        with self.assertRaises(MockExtractionError):
            SubjectSpec("dragon", "balanced")

    def test_unknown_salience_is_rejected(self) -> None:
        with self.assertRaises(MockExtractionError):
            SubjectSpec("human_figure", "overwhelming")

    def test_unknown_density_is_rejected(self) -> None:
        with self.assertRaises(MockExtractionError):
            sample(composition_density="packed")

    def test_unknown_negative_space_is_rejected(self) -> None:
        with self.assertRaises(MockExtractionError):
            sample(negative_space="vast")

    def test_unknown_layout_class_is_rejected(self) -> None:
        with self.assertRaises(MockExtractionError):
            sample(layout_template_class="diagonal_cascade")

    def test_zero_hierarchy_levels_is_rejected(self) -> None:
        with self.assertRaises(MockExtractionError):
            TextStyleSpec("two_level", 0)

    def test_confidence_outside_unit_range_is_rejected(self) -> None:
        with self.assertRaises(MockExtractionError):
            sample(confidence=1.5)

    def test_duplicate_region_ids_are_rejected(self) -> None:
        with self.assertRaises(MockExtractionError):
            sample(
                regions=(
                    region("dup", "title", 0.0, 0.0, 0.5, 0.2),
                    region("dup", "body", 0.0, 0.3, 0.5, 0.2),
                )
            )

    def test_reading_order_referencing_unknown_region_is_rejected(self) -> None:
        with self.assertRaises(MockExtractionError):
            sample(reading_order=("ghost",))

    def test_text_region_ids_are_validated(self) -> None:
        with self.assertRaises(MockExtractionError):
            sample(text_region_ids=("ghost",))

    def test_declared_cross_modal_relation_for_unknown_region_is_rejected(self) -> None:
        with self.assertRaises(MockExtractionError):
            sample(cross_modal_relations={"ghost": "contrasts"})

    def test_vocabularies_are_exposed_and_closed(self) -> None:
        self.assertIn("warm_red", COLOR_FAMILIES)
        self.assertIn("generous", NEGATIVE_SPACE)
        self.assertIn("text_dominant", SUBJECT_SALIENCE)
        self.assertNotIn("iridescent", COLOR_FAMILIES)

    def test_derived_reading_order_is_deterministic(self) -> None:
        s = sample()
        self.assertEqual(s.resolved_reading_order(), s.resolved_reading_order())
        self.assertEqual(s.resolved_reading_order()[0], "bg")


class ObservationSchemaTests(unittest.TestCase):
    """Extracted observations must satisfy the M1 observation shape."""

    def test_observation_is_produced(self) -> None:
        observation = MockVisionExtractor().extract(sample())
        self.assertEqual(observation.source_id, "S1")
        self.assertEqual(observation.medium, "image")

    def test_observation_carries_regions(self) -> None:
        observation = MockVisionExtractor().extract(sample())
        self.assertEqual(len(observation.regions), 3)
        for item in observation.regions:
            self.assertIn("region_id", item)
            self.assertIn("role", item)
            self.assertIn("box", item)
            self.assertIn("layer_order", item)

    def test_every_evidence_kind_is_structural(self) -> None:
        observation = MockVisionExtractor().extract(sample())
        for kind in observation.evidence_kinds:
            self.assertIn(kind, STRUCTURAL_EVIDENCE, kind)

    def test_observation_records_layout_class(self) -> None:
        observation = MockVisionExtractor().extract(sample())
        self.assertEqual(observation.layout_template_class, "image_left_text_right")

    def test_observation_records_subject_role(self) -> None:
        observation = MockVisionExtractor().extract(sample())
        self.assertEqual(observation.subject_class, "human_figure")

    def test_extraction_is_deterministic(self) -> None:
        extractor = MockVisionExtractor()
        first = extractor.extract(sample())
        second = extractor.extract(sample())
        self.assertEqual(first, second)

    def test_extraction_is_pure_over_input(self) -> None:
        extractor = MockVisionExtractor()
        s = sample()
        before = s
        extractor.extract(s)
        self.assertEqual(s, before)

    def test_video_frame_observation_may_claim_temporal_rhythm(self) -> None:
        observation = MockVisionExtractor().extract(
            sample(media_kind="video_frame", media_role="opener")
        )
        self.assertEqual(observation.medium, "video")
        self.assertIn("temporal_rhythm", observation.evidence_kinds)

    def test_batch_rejects_duplicate_sample_ids(self) -> None:
        with self.assertRaises(MockExtractionError):
            MockVisionExtractor().extract_all([sample("dup"), sample("dup")])

    def test_evidence_derivation_never_returns_ocr(self) -> None:
        kinds = derive_evidence_kinds(sample())
        self.assertNotIn("ocr_text", kinds)

    def test_contrast_role_maps_warning_composition(self) -> None:
        self.assertEqual(contrast_role_for("warm_red", "high_contrast_accent"), "warning")
        self.assertEqual(contrast_role_for("cool_blue", "monochrome"), "ground")
        self.assertEqual(contrast_role_for("neutral_grey", "muted"), "ground")


class AnnotationPathTests(unittest.TestCase):
    """The hand-annotation input path must work without extraction."""

    def test_annotation_produces_observation(self) -> None:
        observation = annotation_to_observation(
            {
                "regions": [
                    {"region_id": "t", "role": "title", "box": {"x": 0, "y": 0, "w": 1, "h": 0.2}, "layer_order": 0}
                ],
                "evidence_kinds": ["region_layout"],
                "layout_template_class": "single_column",
                "subject_class": "human_figure",
            },
            source_id="A1",
        )
        self.assertEqual(observation.source_id, "A1")
        self.assertEqual(observation.layout_template_class, "single_column")
        self.assertEqual(observation.observation_id, "A1:annotated")

    def test_annotation_requires_regions(self) -> None:
        with self.assertRaises(MockExtractionError):
            annotation_to_observation({"evidence_kinds": ["region_layout"]}, source_id="A1")

    def test_annotation_requires_evidence(self) -> None:
        with self.assertRaises(MockExtractionError):
            annotation_to_observation(
                {"regions": [{"region_id": "t", "role": "title", "box": {"x": 0, "y": 0, "w": 1, "h": 0.2}, "layer_order": 0}]},
                source_id="A1",
            )

    def test_annotation_grounded_only_in_ocr_is_rejected(self) -> None:
        with self.assertRaises(MockExtractionError):
            annotation_to_observation(
                {
                    "regions": [
                        {"region_id": "t", "role": "title", "box": {"x": 0, "y": 0, "w": 1, "h": 0.2}, "layer_order": 0}
                    ],
                    "evidence_kinds": ["ocr_text"],
                },
                source_id="A1",
            )

    def test_annotation_empty_source_id_is_rejected(self) -> None:
        with self.assertRaises(MockExtractionError):
            annotation_to_observation(
                {
                    "regions": [
                        {"region_id": "t", "role": "title", "box": {"x": 0, "y": 0, "w": 1, "h": 0.2}, "layer_order": 0}
                    ],
                    "evidence_kinds": ["region_layout"],
                },
                source_id="  ",
            )

    def test_producer_annotate_only_requires_declared_layout(self) -> None:
        with self.assertRaises(MockExtractionError):
            ObservationProducer().produce(
                [sample(layout_template_class=None)], annotate_only=True
            )

    def test_producer_rejects_unknown_mode(self) -> None:
        with self.assertRaises(MockExtractionError):
            ObservationProducer(mode="telepathy")


class GeometricRelationTests(unittest.TestCase):
    """Cross-modal geometry must be derived, not read off text."""

    def test_relation_vocabulary_is_exposed(self) -> None:
        for name in ("left_of", "right_of", "above", "below", "contained_by"):
            self.assertIn(name, GEOMETRIC_RELATIONS)

    def test_left_of_is_detected(self) -> None:
        self.assertEqual(
            geometric_relation(
                {"x": 0.05, "y": 0.1, "w": 0.4, "h": 0.2},
                {"x": 0.55, "y": 0.1, "w": 0.4, "h": 0.6},
            ),
            "left_of",
        )

    def test_short_text_beside_tall_image_is_left_of_not_diagonal(self) -> None:
        """Centre offsets must not turn adjacency into a diagonal relation."""

        self.assertEqual(
            geometric_relation(
                {"x": 0.06, "y": 0.10, "w": 0.40, "h": 0.20},
                {"x": 0.55, "y": 0.10, "w": 0.40, "h": 0.60},
            ),
            "left_of",
        )

    def test_above_is_detected(self) -> None:
        self.assertEqual(
            geometric_relation(
                {"x": 0.1, "y": 0.05, "w": 0.8, "h": 0.18},
                {"x": 0.1, "y": 0.30, "w": 0.8, "h": 0.55},
            ),
            "above",
        )

    def test_contained_by_is_detected(self) -> None:
        self.assertEqual(
            geometric_relation(
                {"x": 0.15, "y": 0.40, "w": 0.7, "h": 0.2},
                {"x": 0.05, "y": 0.05, "w": 0.9, "h": 0.9},
            ),
            "contained_by",
        )

    def test_relation_is_deterministic(self) -> None:
        args = (
            {"x": 0.05, "y": 0.1, "w": 0.4, "h": 0.2},
            {"x": 0.55, "y": 0.1, "w": 0.4, "h": 0.6},
        )
        self.assertEqual(geometric_relation(*args), geometric_relation(*args))


class CrossModalCandidateTests(unittest.TestCase):
    """Cross-modal records must carry both anchors."""

    def test_candidate_carries_both_anchors(self) -> None:
        candidates = candidates_from_sample(sample())
        self.assertTrue(candidates)
        for candidate in candidates:
            self.assertTrue(candidate.text_region_id)
            self.assertTrue(candidate.visual_region_id)

    def test_anchor_is_the_subject_not_the_background(self) -> None:
        candidate = candidates_from_sample(sample())[0]
        self.assertEqual(candidate.visual_role, "subject")
        self.assertEqual(candidate.visual_region_id, "img")

    def test_sample_without_text_region_yields_no_candidate(self) -> None:
        no_text = sample(
            regions=(
                region("bg", "background", 0.0, 0.0, 1.0, 1.0, 0),
                region("img", "subject", 0.1, 0.1, 0.5, 0.5, 1),
            )
        )
        self.assertEqual(candidates_from_sample(no_text), ())

    def test_sample_without_visual_region_yields_no_candidate(self) -> None:
        """Text regions and a background alone carry nothing to relate to.

        ``background`` is a visual region, so a genuinely text-only sample has no
        subject, chart, or table for a text region to align with.
        """

        no_visual = sample(
            regions=(
                region("title", "title", 0.1, 0.1, 0.5, 0.2, 0),
                region("body", "body", 0.1, 0.4, 0.5, 0.4, 0),
            )
        )
        # No region counts as visual here, so there is no anchor.
        self.assertEqual(no_visual.visual_regions(), ())
        self.assertEqual(candidates_from_sample(no_visual), ())

    def test_declared_relation_is_marked_as_declared(self) -> None:
        declared = sample(cross_modal_relations={"title": "contrasts"})
        candidate = candidates_from_sample(declared)[0]
        self.assertTrue(candidate.declared)
        self.assertEqual(candidate.relation, "contrasts")

    def test_undeclared_relation_is_marked_as_derived(self) -> None:
        candidate = candidates_from_sample(sample())[0]
        self.assertFalse(candidate.declared)
        self.assertIn(candidate.relation, {"labels", "illustrates", "reinforces"})

    def test_unknown_declared_relation_is_rejected(self) -> None:
        with self.assertRaises(MockExtractionError):
            candidates_from_sample(sample(cross_modal_relations={"title": "vibes"}))

    def test_candidate_from_observation_uses_stored_geometry(self) -> None:
        observation = MockVisionExtractor().extract(sample())
        candidates = candidates_from_observation(observation)
        self.assertTrue(candidates)
        self.assertEqual(candidates[0].visual_role, "subject")

    def test_candidate_from_empty_observation_is_empty(self) -> None:
        from multimodal_creator import StructuralObservation

        empty = StructuralObservation(
            observation_id="e",
            medium="image",
            source_id="E",
            roles=["visual_style_source"],
            evidence_kinds=["region_geometry"],
        )
        self.assertEqual(candidates_from_observation(empty), ())

    def test_evidence_rendering_keeps_geometry(self) -> None:
        candidate = candidates_from_sample(sample())[0]
        evidence = candidate.as_evidence()
        self.assertIn("geometric_relation", evidence)
        self.assertIn("declared", evidence)


class AntiOcrRegressionTests(unittest.TestCase):
    """The extraction prototype must stay structural."""

    def test_no_source_file_reads_text_from_images(self) -> None:
        """The prototype must not open, decode, or OCR any image."""

        import pathlib

        package = pathlib.Path(__file__).resolve().parents[2] / "multimodal_creator"
        offenders: list[str] = []
        forbidden = (
            "PIL",
            "cv2",
            "pytesseract",
            "easyocr",
            "imageio",
            "numpy",
            "torch",
            "requests",
            "urllib",
        )
        for path in sorted(package.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                if f"import {token}" in text or f"from {token}" in text:
                    offenders.append(f"{path.name}:{token}")
        self.assertEqual(offenders, [], f"perception or network imports found: {offenders}")

    def test_no_network_or_file_image_access_in_extraction(self) -> None:
        import pathlib

        package = pathlib.Path(__file__).resolve().parents[2] / "multimodal_creator" / "extraction"
        offenders: list[str] = []
        for path in sorted(package.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for token in ("open(", "urlopen", "requests.", "socket."):
                if token in text:
                    offenders.append(f"{path.name}:{token}")
        self.assertEqual(offenders, [], f"file or network access found: {offenders}")

    def test_extracted_observation_never_claims_ocr(self) -> None:
        for color in ("warm_red", "cool_blue", "dark_monochrome"):
            observation = MockVisionExtractor().extract(sample(color_family=color))
            self.assertNotIn("ocr_text", observation.evidence_kinds)

    def test_producer_validation_rejects_ocr_only_observation(self) -> None:
        from multimodal_creator import StructuralObservation
        from multimodal_creator.extraction.observation_producer import ObservationBatch

        bad = StructuralObservation(
            observation_id="bad",
            medium="image",
            source_id="B",
            roles=["visual_style_source"],
            evidence_kinds=["ocr_text"],
            regions=({"region_id": "r", "role": "title", "box": {"x": 0, "y": 0, "w": 1, "h": 0.2}, "layer_order": 0},),
        )
        batch = ObservationBatch(samples=(sample("B"),), observations=(bad,))
        with self.assertRaises(MockExtractionError):
            ObservationProducer()._validate_batch(batch)

    def test_producer_validation_rejects_image_temporal_claim(self) -> None:
        from multimodal_creator import MultimodalContractError, StructuralObservation

        # The M1 observation type rejects an image claiming temporal evidence at
        # construction, before the producer ever sees it.
        with self.assertRaises(MultimodalContractError):
            StructuralObservation(
                observation_id="bad",
                medium="image",
                source_id="B",
                roles=["visual_style_source"],
                evidence_kinds=["region_geometry", "temporal_rhythm"],
                regions=({"region_id": "r", "role": "title", "box": {"x": 0, "y": 0, "w": 1, "h": 0.2}, "layer_order": 0},),
            )


if __name__ == "__main__":
    unittest.main()
