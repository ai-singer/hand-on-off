"""Grammar model, extraction, relation, and SimilarityVector tests."""

from __future__ import annotations

import copy
import unittest

from multimodal_creator.grammar import (
    ATTENTION_STAGES,
    COLUMN_BANDS,
    DENSITY_LEVELS,
    DOMINANCE_RANKS,
    POSITION_BANDS,
    REGION_TYPES,
    RELATION_TYPES,
    AttentionFlow,
    DimensionReading,
    GrammarError,
    GrammarExtractor,
    GrammarRegion,
    GrammarRelation,
    RelationExtractor,
    SimilarityError,
    SimilarityVector,
    VisualGrammar,
    extract_grammar,
)
from multimodal_creator.grammar.model import column_band_of, position_band_of
from multimodal_creator.grammar.similarity_v2 import (
    BALANCED_PROFILE,
    CREATOR_STYLE_PROFILE,
    PROFILES,
    SIMILARITY_DIMENSIONS,
    TEMPLATE_PROFILE,
    profile_scores,
    vector_matrix,
    vector_similarity,
)
from multimodal_creator.taxonomy import StructuralObservation


def observation(source_id="s1", regions=None, **overrides):
    body = (
        {"region_id": "bg", "role": "background", "box": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}, "layer_order": 0},
        {"region_id": "t", "role": "title", "box": {"x": 0.05, "y": 0.08, "w": 0.45, "h": 0.14}, "layer_order": 1},
        {"region_id": "b", "role": "body", "box": {"x": 0.05, "y": 0.30, "w": 0.45, "h": 0.28}, "layer_order": 1},
        {"region_id": "s", "role": "subject", "box": {"x": 0.55, "y": 0.08, "w": 0.40, "h": 0.62}, "layer_order": 1},
    )
    fields = {
        "observation_id": f"{source_id}:observed",
        "medium": "image",
        "source_id": source_id,
        "roles": ("visual_style_source", "layout_source", "subject_source"),
        "evidence_kinds": ("region_layout", "region_geometry", "dominance_order", "reading_order"),
        "regions": regions or body,
        "layout_template_class": "image_left_text_right",
        "alignment": "left",
        "density": "balanced",
        "palette_relation": "complementary",
        "type_scale_relation": "two_level",
        "subject_class": "composite",
        "placement": "side_panel",
        "confidence": 0.9,
    }
    fields.update(overrides)
    return StructuralObservation(**fields)


def region(region_id, region_type, **overrides):
    fields = {
        "region_id": region_id,
        "region_type": region_type,
        "position_band": "center",
        "column_band": "mid",
        "width_share": 0.5,
        "height_share": 0.3,
        "area_share": 0.15,
        "density": "moderate",
        "dominance": "secondary",
        "layer_order": 1,
        "position_center": (0.5, 0.5),
    }
    fields.update(overrides)
    return GrammarRegion(**fields)


class RegionModelTests(unittest.TestCase):
    """The region type must reject anything outside the closed vocabulary."""

    def test_valid_region_builds(self) -> None:
        self.assertEqual(region("r", "headline").region_type, "headline")

    def test_unknown_region_type_is_rejected(self) -> None:
        with self.assertRaises(GrammarError):
            region("r", "banner")

    def test_unknown_position_band_is_rejected(self) -> None:
        with self.assertRaises(GrammarError):
            region("r", "headline", position_band="upper")

    def test_unknown_column_band_is_rejected(self) -> None:
        with self.assertRaises(GrammarError):
            region("r", "headline", column_band="center")

    def test_unknown_density_is_rejected(self) -> None:
        with self.assertRaises(GrammarError):
            region("r", "headline", density="heavy")

    def test_unknown_dominance_is_rejected(self) -> None:
        with self.assertRaises(GrammarError):
            region("r", "headline", dominance="quaternary")

    def test_share_above_one_is_rejected(self) -> None:
        with self.assertRaises(GrammarError):
            region("r", "headline", area_share=1.5)

    def test_unnormalized_centre_is_rejected(self) -> None:
        with self.assertRaises(GrammarError):
            region("r", "headline", position_center=(1.4, 0.5))

    def test_vocabularies_are_exposed(self) -> None:
        self.assertIn("headline", REGION_TYPES)
        self.assertIn("cta", REGION_TYPES)
        self.assertEqual(list(POSITION_BANDS), ["top", "center", "bottom"])
        self.assertEqual(list(COLUMN_BANDS), ["left", "mid", "right"])
        self.assertEqual(list(DENSITY_LEVELS), ["sparse", "moderate", "dense"])
        self.assertIn("primary", DOMINANCE_RANKS)

    def test_band_mapping_is_separated_by_axis(self) -> None:
        """Position and column vocabularies must not be interchangeable."""

        self.assertEqual(position_band_of(0.1), "top")
        self.assertEqual(position_band_of(0.5), "center")
        self.assertEqual(position_band_of(0.9), "bottom")
        self.assertEqual(column_band_of(0.1), "left")
        self.assertEqual(column_band_of(0.5), "mid")
        self.assertEqual(column_band_of(0.9), "right")
        self.assertNotIn("center", COLUMN_BANDS)
        self.assertNotIn("mid", POSITION_BANDS)


class RelationModelTests(unittest.TestCase):
    def test_valid_relation_builds(self) -> None:
        item = GrammarRelation("r", "subject_center_focus", "a", "a", 0.9, "reason")
        self.assertEqual(item.strength, 0.9)

    def test_unknown_relation_type_is_rejected(self) -> None:
        with self.assertRaises(GrammarError):
            GrammarRelation("r", "vibes", "a", "b", 0.5, "reason")

    def test_strength_outside_unit_range_is_rejected(self) -> None:
        with self.assertRaises(GrammarError):
            GrammarRelation("r", "subject_center_focus", "a", "b", 1.5, "reason")

    def test_relation_needs_both_endpoints(self) -> None:
        with self.assertRaises(GrammarError):
            GrammarRelation("r", "subject_center_focus", "", "b", 0.5, "reason")

    def test_relation_vocabulary_covers_the_brief_examples(self) -> None:
        for name in (
            "headline_above_subject",
            "subject_center_focus",
            "cta_bottom_anchor",
            "high_contrast_boundary",
        ):
            self.assertIn(name, RELATION_TYPES)


class AttentionFlowTests(unittest.TestCase):
    def test_valid_flow(self) -> None:
        flow = AttentionFlow(("entrance_point", "primary_focus"), {"entrance_point": "a", "primary_focus": "b"})
        self.assertEqual(flow.region_for("primary_focus"), "b")

    def test_unknown_stage_is_rejected(self) -> None:
        with self.assertRaises(GrammarError):
            AttentionFlow(("entrance_point", "finale"), {"entrance_point": "a"})

    def test_out_of_order_stages_are_rejected(self) -> None:
        with self.assertRaises(GrammarError):
            AttentionFlow(("action_area", "entrance_point"), {})

    def test_stage_vocabulary_matches_the_brief(self) -> None:
        self.assertEqual(
            list(ATTENTION_STAGES),
            ["entrance_point", "primary_focus", "secondary_information", "action_area"],
        )


class VisualGrammarTests(unittest.TestCase):
    def _grammar(self):
        return extract_grammar(observation()).grammar

    def test_grammar_builds(self) -> None:
        grammar = self._grammar()
        self.assertTrue(grammar.regions)

    def test_duplicate_region_ids_are_rejected(self) -> None:
        with self.assertRaises(GrammarError):
            VisualGrammar(
                grammar_id="g",
                source_id="s",
                regions=(region("dup", "headline"), region("dup", "subject")),
                relationships=(),
                attention_flow=AttentionFlow((), {}),
                evidence_source="test",
                confidence=0.5,
            )

    def test_dangling_relation_is_rejected(self) -> None:
        with self.assertRaises(GrammarError):
            VisualGrammar(
                grammar_id="g",
                source_id="s",
                regions=(region("a", "headline"),),
                relationships=(
                    GrammarRelation("r", "subject_center_focus", "a", "ghost", 0.5, "x"),
                ),
                attention_flow=AttentionFlow((), {}),
                evidence_source="test",
                confidence=0.5,
            )

    def test_empty_grammar_is_rejected(self) -> None:
        with self.assertRaises(GrammarError):
            VisualGrammar(
                grammar_id="g",
                source_id="s",
                regions=(),
                relationships=(),
                attention_flow=AttentionFlow((), {}),
                evidence_source="test",
                confidence=0.5,
            )

    def test_confidence_outside_unit_range_is_rejected(self) -> None:
        with self.assertRaises(GrammarError):
            VisualGrammar(
                grammar_id="g",
                source_id="s",
                regions=(region("a", "headline"),),
                relationships=(),
                attention_flow=AttentionFlow((), {}),
                evidence_source="test",
                confidence=1.5,
            )

    def test_attention_assignment_referencing_unknown_region_is_rejected(self) -> None:
        with self.assertRaises(GrammarError):
            VisualGrammar(
                grammar_id="g",
                source_id="s",
                regions=(region("a", "headline"),),
                relationships=(),
                attention_flow=AttentionFlow(("entrance_point",), {"entrance_point": "ghost"}),
                evidence_source="test",
                confidence=0.5,
            )

    def test_structural_signature_is_order_independent(self) -> None:
        grammar = self._grammar()
        reversed_grammar = VisualGrammar(
            grammar_id=grammar.grammar_id,
            source_id=grammar.source_id,
            regions=tuple(reversed(grammar.regions)),
            relationships=grammar.relationships,
            attention_flow=grammar.attention_flow,
            evidence_source=grammar.evidence_source,
            confidence=grammar.confidence,
        )
        self.assertEqual(
            grammar.structural_signature(), reversed_grammar.structural_signature()
        )

    def test_region_lookup(self) -> None:
        grammar = self._grammar()
        first = grammar.regions[0]
        self.assertEqual(grammar.region(first.region_id).region_id, first.region_id)

    def test_unknown_region_lookup_raises(self) -> None:
        with self.assertRaises(GrammarError):
            self._grammar().region("ghost")

    def test_as_dict_serialises(self) -> None:
        payload = self._grammar().as_dict()
        for key in ("regions", "relationships", "attention_flow", "structural_signature"):
            self.assertIn(key, payload)

    def test_render_works(self) -> None:
        self.assertIn("grammar", self._grammar().render())


class GrammarExtractionTests(unittest.TestCase):
    def test_extraction_produces_a_grammar(self) -> None:
        result = GrammarExtractor().extract(observation())
        self.assertTrue(result.grammar.regions)

    def test_role_mapping_is_recorded(self) -> None:
        result = GrammarExtractor().extract(observation())
        self.assertTrue(result.decisions)
        self.assertTrue(all("->" in value for value in result.decisions.values()))

    def test_title_maps_to_headline(self) -> None:
        result = GrammarExtractor().extract(observation())
        self.assertIn("headline", {r.region_type for r in result.grammar.regions})

    def test_body_maps_to_supporting_information(self) -> None:
        result = GrammarExtractor().extract(observation())
        self.assertIn(
            "supporting_information", {r.region_type for r in result.grammar.regions}
        )

    def test_chart_maps_to_data_display(self) -> None:
        obs = observation(
            regions=(
                {"region_id": "bg", "role": "background", "box": {"x": 0, "y": 0, "w": 1, "h": 1}, "layer_order": 0},
                {"region_id": "c", "role": "chart", "box": {"x": 0.1, "y": 0.2, "w": 0.8, "h": 0.5}, "layer_order": 1},
            )
        )
        result = GrammarExtractor().extract(obs)
        self.assertIn("data_display", {r.region_type for r in result.grammar.regions})

    def test_logo_maps_to_branding(self) -> None:
        obs = observation(
            regions=(
                {"region_id": "bg", "role": "background", "box": {"x": 0, "y": 0, "w": 1, "h": 1}, "layer_order": 0},
                {"region_id": "l", "role": "logo", "box": {"x": 0.85, "y": 0.85, "w": 0.1, "h": 0.08}, "layer_order": 1},
            )
        )
        result = GrammarExtractor().extract(obs)
        self.assertIn("branding", {r.region_type for r in result.grammar.regions})

    def test_footer_maps_to_cta(self) -> None:
        obs = observation(
            regions=(
                {"region_id": "bg", "role": "background", "box": {"x": 0, "y": 0, "w": 1, "h": 1}, "layer_order": 0},
                {"region_id": "f", "role": "footer", "box": {"x": 0.1, "y": 0.85, "w": 0.8, "h": 0.08}, "layer_order": 1},
            )
        )
        result = GrammarExtractor().extract(obs)
        self.assertIn("cta", {r.region_type for r in result.grammar.regions})

    def test_unknown_role_is_dropped_with_a_warning(self) -> None:
        obs = observation(
            regions=(
                {"region_id": "bg", "role": "background", "box": {"x": 0, "y": 0, "w": 1, "h": 1}, "layer_order": 0},
                {"region_id": "x", "role": "hologram", "box": {"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.2}, "layer_order": 1},
            )
        )
        result = GrammarExtractor().extract(obs)
        self.assertTrue(result.warnings)

    def test_empty_observation_is_rejected(self) -> None:
        from multimodal_creator.taxonomy import StructuralObservation

        empty = StructuralObservation(
            observation_id="e",
            medium="image",
            source_id="e",
            roles=("visual_style_source",),
            evidence_kinds=("region_geometry",),
            regions=(),
        )
        with self.assertRaises(GrammarError):
            GrammarExtractor().extract(empty)

    def test_extraction_is_deterministic(self) -> None:
        first = GrammarExtractor().extract(observation()).grammar
        second = GrammarExtractor().extract(observation()).grammar
        self.assertEqual(first, second)

    def test_subject_is_primary_dominance(self) -> None:
        result = GrammarExtractor().extract(observation())
        subject = [r for r in result.grammar.regions if r.region_type == "subject"]
        self.assertTrue(subject)
        self.assertEqual(subject[0].dominance, "primary")

    def test_background_is_always_background_dominance(self) -> None:
        """A full-frame ground must never win a raw area ranking."""

        result = GrammarExtractor().extract(observation())
        background = [r for r in result.grammar.regions if r.region_type == "background"]
        self.assertTrue(background)
        self.assertEqual(background[0].dominance, "background")

    def test_dominant_region_is_content_not_ground(self) -> None:
        grammar = extract_grammar(observation()).grammar
        self.assertNotEqual(grammar.dominant_region().region_type, "background")

    def test_no_text_is_read(self) -> None:
        """The extractor must not consult any text field."""

        import inspect

        from multimodal_creator.grammar import extractor as extractor_module

        source = inspect.getsource(extractor_module).lower()
        for token in ("ocr", "tesseract", "text_content", "recognize"):
            self.assertNotIn(token, source)


class RelationExtractionTests(unittest.TestCase):
    def _relations(self, regions):
        return RelationExtractor().extract(regions)

    def test_headline_above_subject_is_detected(self) -> None:
        regions = (
            region("t", "headline", position_band="top", position_center=(0.3, 0.15), width_share=0.5, height_share=0.12, area_share=0.06),
            region("s", "subject", position_band="center", position_center=(0.7, 0.5), width_share=0.4, height_share=0.5, area_share=0.2),
        )
        names = {r.relation_type for r in self._relations(regions)}
        self.assertIn("headline_above_subject", names)

    def test_headline_overlay_is_detected(self) -> None:
        regions = (
            region("s", "subject", area_share=0.8, width_share=0.9, height_share=0.9, position_center=(0.5, 0.5), layer_order=0),
            region("t", "headline", area_share=0.1, width_share=0.7, height_share=0.15, position_center=(0.5, 0.5), layer_order=1),
        )
        names = {r.relation_type for r in self._relations(regions)}
        self.assertIn("headline_overlay_subject", names)

    def test_subject_center_focus_is_detected(self) -> None:
        regions = (region("s", "subject", position_center=(0.5, 0.5), width_share=0.4, area_share=0.2),)
        names = {r.relation_type for r in self._relations(regions)}
        self.assertIn("subject_center_focus", names)

    def test_subject_offset_focus_is_detected(self) -> None:
        regions = (region("s", "subject", position_center=(0.8, 0.5), width_share=0.3, area_share=0.15),)
        names = {r.relation_type for r in self._relations(regions)}
        self.assertIn("subject_offset_focus", names)

    def test_subject_full_bleed_is_detected(self) -> None:
        regions = (region("s", "subject", area_share=0.8, width_share=0.95, height_share=0.95, position_center=(0.5, 0.5)),)
        names = {r.relation_type for r in self._relations(regions)}
        self.assertIn("subject_full_bleed", names)

    def test_cta_bottom_anchor_is_detected(self) -> None:
        regions = (region("c", "cta", position_center=(0.5, 0.88), position_band="bottom"),)
        names = {r.relation_type for r in self._relations(regions)}
        self.assertIn("cta_bottom_anchor", names)

    def test_cta_top_anchor_is_detected(self) -> None:
        regions = (region("c", "cta", position_center=(0.5, 0.1), position_band="top"),)
        names = {r.relation_type for r in self._relations(regions)}
        self.assertIn("cta_top_anchor", names)

    def test_branding_corner_is_detected(self) -> None:
        regions = (region("l", "branding", position_center=(0.92, 0.92)),)
        names = {r.relation_type for r in self._relations(regions)}
        self.assertIn("branding_corner", names)

    def test_background_encloses_all_is_detected(self) -> None:
        regions = (
            region("bg", "background", width_share=1.0, height_share=1.0, area_share=1.0, position_center=(0.5, 0.5), dominance="background"),
            region("t", "headline", position_center=(0.5, 0.2), width_share=0.6, height_share=0.15, area_share=0.09),
        )
        names = {r.relation_type for r in self._relations(regions)}
        self.assertIn("background_encloses_all", names)

    def test_support_below_headline_is_detected(self) -> None:
        regions = (
            region("t", "headline", position_center=(0.5, 0.15), height_share=0.15, area_share=0.08),
            region("b", "supporting_information", position_center=(0.5, 0.5), height_share=0.3, area_share=0.14),
        )
        names = {r.relation_type for r in self._relations(regions)}
        self.assertIn("support_below_headline", names)

    def test_support_beside_subject_is_detected(self) -> None:
        regions = (
            region("b", "supporting_information", position_center=(0.2, 0.5), width_share=0.3),
            region("s", "subject", position_center=(0.8, 0.5), width_share=0.3),
        )
        names = {r.relation_type for r in self._relations(regions)}
        self.assertIn("support_beside_subject", names)

    def test_data_below_headline_is_detected(self) -> None:
        regions = (
            region("t", "headline", position_center=(0.5, 0.12), height_share=0.12, area_share=0.07),
            region("d", "data_display", position_center=(0.5, 0.5), height_share=0.4, area_share=0.3),
        )
        names = {r.relation_type for r in self._relations(regions)}
        self.assertIn("data_below_headline", names)

    def test_contrast_relation_is_always_emitted_for_two_large_regions(self) -> None:
        regions = (
            region("a", "subject", area_share=0.3, density="moderate", position_center=(0.2, 0.5)),
            region("b", "supporting_information", area_share=0.25, density="sparse", position_center=(0.8, 0.5)),
        )
        names = {r.relation_type for r in self._relations(regions)}
        self.assertTrue({"high_contrast_boundary", "low_contrast_blend"} & names)

    def test_extraction_is_deterministic(self) -> None:
        regions = (
            region("t", "headline", position_band="top", position_center=(0.3, 0.15)),
            region("s", "subject", position_center=(0.7, 0.5)),
        )
        first = self._relations(regions)
        second = self._relations(regions)
        self.assertEqual(first, second)

    def test_relation_order_is_deterministic(self) -> None:
        regions = tuple(region(f"r{i}", "headline", position_center=(0.1 * i, 0.1 * i)) for i in range(1, 4))
        first = [r.relation_id for r in self._relations(regions)]
        second = [r.relation_id for r in self._relations(regions)]
        self.assertEqual(first, sorted(first))
        self.assertEqual(first, second)

    def test_empty_regions_are_rejected(self) -> None:
        with self.assertRaises(GrammarError):
            self._relations(())

    def test_invalid_contrast_threshold_is_rejected(self) -> None:
        with self.assertRaises(GrammarError):
            RelationExtractor(contrast_threshold=0.0)

    def test_relations_only_use_vocabulary_names(self) -> None:
        grammar = extract_grammar(observation()).grammar
        for relation in grammar.relationships:
            self.assertIn(relation.relation_type, RELATION_TYPES)


class SimilarityVectorTests(unittest.TestCase):
    """The vector must carry four dimensions and refuse to collapse them."""

    def _pair(self, **right_overrides):
        left = observation("L")
        right = observation("R", **right_overrides)
        left_grammar = extract_grammar(left).grammar
        right_grammar = extract_grammar(right).grammar
        return vector_similarity(
            left_grammar, right_grammar, left_observation=left, right_observation=right
        )

    def test_vector_has_four_dimensions(self) -> None:
        vector = self._pair()
        self.assertEqual(set(vector.values()), set(vector.values()))
        self.assertEqual(len(vector.values()), 4)

    def test_dimension_names_are_canonical(self) -> None:
        vector = self._pair()
        self.assertEqual(set(vector.values()), set(SIMILARITY_DIMENSIONS))

    def test_vector_exposes_no_combined_score(self) -> None:
        """The brief forbids synthesising one score; the type must not offer one."""

        payload = self._pair().as_dict()
        self.assertNotIn("score", payload)
        self.assertNotIn("total", payload)
        self.assertNotIn("combined", payload)

    def test_similarity_vector_dataclass_has_no_score_field(self) -> None:
        fields = set(SimilarityVector.__dataclass_fields__)
        for forbidden in ("score", "total", "combined", "aggregate"):
            self.assertNotIn(forbidden, fields)

    def test_identical_grammars_score_one_on_evidenced_dimensions(self) -> None:
        """Structural, style, and composition reach 1.0 for identical inputs.

        ``asset`` does not, and deliberately so: neither observation declares a
        chart class, and an *absent* fact scores neutral (0.5) rather than as
        agreement. Two images that both lack charts provide no evidence about
        chart similarity, so claiming perfect asset agreement would overstate
        what was measured. The behaviour is pinned rather than patched.
        """

        vector = self._pair()
        for name in ("structural", "style", "composition"):
            self.assertEqual(vector[name], 1.0, name)
        self.assertLess(vector["asset"], 1.0)
        self.assertGreater(vector["asset"], 0.5)

    def test_identical_grammars_with_chart_evidence_score_one_on_asset(self) -> None:
        regions = (
            {"region_id": "bg", "role": "background", "box": {"x": 0, "y": 0, "w": 1, "h": 1}, "layer_order": 0},
            {"region_id": "c", "role": "chart", "box": {"x": 0.1, "y": 0.15, "w": 0.8, "h": 0.5}, "layer_order": 1},
        )
        left = observation("L", regions=regions, chart_class="bar")
        right = observation("R", regions=regions, chart_class="bar")
        vector = vector_similarity(
            extract_grammar(left).grammar,
            extract_grammar(right).grammar,
            left_observation=left,
            right_observation=right,
        )
        self.assertEqual(vector["asset"], 1.0)

    def test_all_values_within_unit_range(self) -> None:
        vector = self._pair(palette_relation="monochrome", density="dense")
        for name in SIMILARITY_DIMENSIONS:
            self.assertGreaterEqual(vector[name], 0.0)
            self.assertLessEqual(vector[name], 1.0)

    def test_different_structure_lowers_structural_dimension(self) -> None:
        same = self._pair()
        different = self._pair(
            regions=(
                {"region_id": "bg", "role": "background", "box": {"x": 0, "y": 0, "w": 1, "h": 1}, "layer_order": 0},
                {"region_id": "c", "role": "chart", "box": {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.5}, "layer_order": 1},
            )
        )
        self.assertLess(different["structural"], same["structural"])

    def test_style_change_lowers_only_style(self) -> None:
        same = self._pair()
        changed = self._pair(palette_relation="monochrome")
        self.assertLess(changed["style"], same["style"])
        self.assertEqual(changed["structural"], same["structural"])

    def test_vector_is_symmetric(self) -> None:
        left = observation("L")
        right = observation("R", palette_relation="monochrome")
        lg = extract_grammar(left).grammar
        rg = extract_grammar(right).grammar
        forward = vector_similarity(lg, rg, left_observation=left, right_observation=right)
        backward = vector_similarity(rg, lg, left_observation=right, right_observation=left)
        self.assertEqual(forward.values(), backward.values())

    def test_grammar_observation_mismatch_is_rejected(self) -> None:
        left = observation("L")
        other = observation("OTHER")
        with self.assertRaises(SimilarityError):
            vector_similarity(
                extract_grammar(left).grammar,
                extract_grammar(left).grammar,
                left_observation=left,
                right_observation=other,
            )

    def test_matrix_rejects_duplicate_ids(self) -> None:
        obs = observation("dup")
        with self.assertRaises(SimilarityError):
            vector_matrix([extract_grammar(obs).grammar, extract_grammar(obs).grammar], {"dup": obs})

    def test_matrix_is_order_independent(self) -> None:
        observations = {sid: observation(sid) for sid in ("A", "B", "C")}
        grammars = [extract_grammar(o).grammar for o in observations.values()]
        forward = vector_matrix(grammars, observations)
        backward = vector_matrix(list(reversed(grammars)), observations)
        self.assertEqual(
            {k: v.values() for k, v in forward.items()},
            {k: v.values() for k, v in backward.items()},
        )

    def test_render_includes_every_dimension(self) -> None:
        text = self._pair().render()
        for name in SIMILARITY_DIMENSIONS:
            self.assertIn(name, text)


class SimilarityProfileTests(unittest.TestCase):
    """Profiles are the explicit, task-specific way to read the vector."""

    def test_all_profiles_have_weights_summing_to_one(self) -> None:
        for profile in PROFILES.values():
            self.assertAlmostEqual(sum(profile.weights.values()), 1.0, places=9)

    def test_template_profile_ignores_style_and_asset(self) -> None:
        self.assertEqual(TEMPLATE_PROFILE.weights["style"], 0.0)
        self.assertEqual(TEMPLATE_PROFILE.weights["asset"], 0.0)

    def test_creator_profile_weights_style_most(self) -> None:
        weights = CREATOR_STYLE_PROFILE.weights
        self.assertGreater(weights["style"], weights["structural"])

    def test_profiles_state_their_question(self) -> None:
        for profile in PROFILES.values():
            self.assertTrue(profile.question.strip())

    def test_unknown_dimension_in_profile_is_rejected(self) -> None:
        from multimodal_creator.grammar.similarity_v2 import SimilarityProfile

        with self.assertRaises(SimilarityError):
            SimilarityProfile("bad", {"vibes": 1.0}, "question?")

    def test_weights_not_summing_to_one_are_rejected(self) -> None:
        from multimodal_creator.grammar.similarity_v2 import SimilarityProfile

        with self.assertRaises(SimilarityError):
            SimilarityProfile("bad", {"structural": 0.5}, "question?")

    def test_profile_without_a_question_is_rejected(self) -> None:
        from multimodal_creator.grammar.similarity_v2 import SimilarityProfile

        with self.assertRaises(SimilarityError):
            SimilarityProfile("bad", {"structural": 1.0}, "  ")

    def test_template_profile_separates_layouts(self) -> None:
        left = observation("L")
        same = observation("S")
        different = observation(
            "D",
            regions=(
                {"region_id": "bg", "role": "background", "box": {"x": 0, "y": 0, "w": 1, "h": 1}, "layer_order": 0},
                {"region_id": "s", "role": "subject", "box": {"x": 0.1, "y": 0.05, "w": 0.8, "h": 0.5}, "layer_order": 1},
                {"region_id": "t", "role": "title", "box": {"x": 0.1, "y": 0.65, "w": 0.8, "h": 0.15}, "layer_order": 1},
            ),
        )
        lg = extract_grammar(left).grammar
        vector_same = vector_similarity(
            lg, extract_grammar(same).grammar, left_observation=left, right_observation=same
        )
        vector_diff = vector_similarity(
            lg,
            extract_grammar(different).grammar,
            left_observation=left,
            right_observation=different,
        )
        self.assertGreater(
            TEMPLATE_PROFILE.project(vector_same), TEMPLATE_PROFILE.project(vector_diff)
        )

    def test_profile_scores_works_over_a_matrix(self) -> None:
        observations = {sid: observation(sid) for sid in ("A", "B")}
        grammars = [extract_grammar(o).grammar for o in observations.values()]
        scores = profile_scores(vector_matrix(grammars, observations), TEMPLATE_PROFILE)
        self.assertEqual(len(scores), 1)

    def test_unavailable_dimension_does_not_drag_the_projection(self) -> None:
        """A missing measurement must dilute, not read as zero."""

        readings = {
            "structural": DimensionReading("structural", 1.0),
            "style": DimensionReading("style", 0.0, available=False, unavailable_reason="not measured"),
            "composition": DimensionReading("composition", 1.0),
            "asset": DimensionReading("asset", 0.0, available=False, unavailable_reason="not measured"),
        }
        vector = SimilarityVector("A", "B", readings)
        self.assertEqual(TEMPLATE_PROFILE.project(vector), 1.0)
        self.assertEqual(BALANCED_PROFILE.project(vector), 1.0)

    def test_unavailable_dimension_requires_a_reason(self) -> None:
        with self.assertRaises(SimilarityError):
            DimensionReading("style", 0.0, available=False)

    def test_unknown_dimension_reading_is_rejected(self) -> None:
        with self.assertRaises(SimilarityError):
            DimensionReading("vibes", 0.5)

    def test_vector_missing_a_dimension_is_rejected(self) -> None:
        with self.assertRaises(SimilarityError):
            SimilarityVector("A", "B", {"structural": DimensionReading("structural", 1.0)})

    def test_profile_cannot_project_with_no_available_dimension(self) -> None:
        readings = {
            name: DimensionReading(name, 0.0, available=False, unavailable_reason="x")
            for name in SIMILARITY_DIMENSIONS
        }
        with self.assertRaises(SimilarityError):
            TEMPLATE_PROFILE.project(SimilarityVector("A", "B", readings))


if __name__ == "__main__":
    unittest.main()
