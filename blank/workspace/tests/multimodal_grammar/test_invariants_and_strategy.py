"""Invariant discovery, strategy distillation, and constraint tests."""

from __future__ import annotations

import ast
import inspect
import json
import unittest

from multimodal_creator.grammar import (
    ATTENTION_STRATEGIES,
    COMPOSITION_MOVES,
    CONSTRAINT_FAMILIES,
    FEATURE_FAMILIES,
    HIERARCHY_STAGES,
    Constraint,
    ConstraintError,
    CreatorStrategyPattern,
    Invariant,
    InvariantError,
    InvariantExtractor,
    InvariantSet,
    StrategyError,
    VisualConstraint,
    constraints_from_strategy,
    distill_strategy,
    extract_grammar,
    summarise_invariants,
)
from multimodal_creator.taxonomy import StructuralObservation


def observation(source_id, regions=None, **overrides):
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
        "density": "balanced",
        "palette_relation": "complementary",
        "type_scale_relation": "two_level",
        "subject_class": "composite",
        "placement": "side_panel",
        "confidence": 0.9,
    }
    fields.update(overrides)
    return StructuralObservation(**fields)


def grammars(count=5, prefix="s"):
    return [extract_grammar(observation(f"{prefix}{i}")).grammar for i in range(count)]


class InvariantModelTests(unittest.TestCase):
    def test_valid_invariant(self) -> None:
        item = Invariant("region_presence", "headline_present", 0.9, 9, 10)
        self.assertEqual(item.key, "region_presence:headline_present")

    def test_unknown_family_is_rejected(self) -> None:
        with self.assertRaises(InvariantError):
            Invariant("vibes", "x", 0.5, 1, 2)

    def test_frequency_outside_unit_range_is_rejected(self) -> None:
        with self.assertRaises(InvariantError):
            Invariant("region_presence", "x", 1.5, 1, 2)

    def test_support_above_total_is_rejected(self) -> None:
        with self.assertRaises(InvariantError):
            Invariant("region_presence", "x", 0.5, 5, 2)

    def test_zero_total_is_rejected(self) -> None:
        with self.assertRaises(InvariantError):
            Invariant("region_presence", "x", 0.5, 0, 0)

    def test_render_shows_percentage(self) -> None:
        self.assertIn("%", Invariant("region_presence", "headline_present", 0.9, 9, 10).render())

    def test_feature_families_are_exposed(self) -> None:
        for name in ("region_presence", "relation_presence", "attention_flow"):
            self.assertIn(name, FEATURE_FAMILIES)


class InvariantExtractionTests(unittest.TestCase):
    """Invariants must be mined, and frequencies must be honest."""

    def test_extraction_produces_an_invariant_set(self) -> None:
        result = InvariantExtractor().extract(grammars(), cluster_id="c1")
        self.assertIsInstance(result, InvariantSet)

    def test_identical_grammars_yield_frequency_one(self) -> None:
        result = InvariantExtractor().extract(grammars(4), cluster_id="c1")
        self.assertEqual(result.frequency_of("region_presence:background_present"), 1.0)

    def test_bare_feature_name_also_resolves(self) -> None:
        result = InvariantExtractor().extract(grammars(4), cluster_id="c1")
        self.assertEqual(result.frequency_of("background_present"), 1.0)

    def test_unknown_feature_resolves_to_zero(self) -> None:
        result = InvariantExtractor().extract(grammars(3), cluster_id="c1")
        self.assertEqual(result.frequency_of("region_presence:unicorn_present"), 0.0)

    def test_threshold_filters_invariants(self) -> None:
        loose = InvariantExtractor(threshold=0.1).extract(grammars(3), cluster_id="c1")
        tight = InvariantExtractor(threshold=1.0).extract(grammars(3), cluster_id="c1")
        self.assertGreaterEqual(len(loose.invariants), len(tight.invariants))

    def test_all_features_survive_the_threshold(self) -> None:
        """Everything is reported; the cut is a separate decision."""

        result = InvariantExtractor(threshold=1.0).extract(grammars(3), cluster_id="c1")
        self.assertGreaterEqual(len(result.all_features), len(result.invariants))

    def test_empty_input_is_rejected(self) -> None:
        with self.assertRaises(InvariantError):
            InvariantExtractor().extract([], cluster_id="c1")

    def test_invalid_threshold_is_rejected(self) -> None:
        with self.assertRaises(InvariantError):
            InvariantExtractor(threshold=0.0)

    def test_row_threshold_override_is_validated(self) -> None:
        with self.assertRaises(InvariantError):
            InvariantExtractor().extract(grammars(2), cluster_id="c1", threshold=2.0)

    def test_frequencies_are_exact_fractions(self) -> None:
        mixed = grammars(3) + [
            extract_grammar(
                observation(
                    "x",
                    regions=(
                        {"region_id": "bg", "role": "background", "box": {"x": 0, "y": 0, "w": 1, "h": 1}, "layer_order": 0},
                    ),
                )
            ).grammar
        ]
        result = InvariantExtractor(threshold=0.1).extract(mixed, cluster_id="c1")
        self.assertAlmostEqual(result.frequency_of("region_presence:subject_present"), 0.75, places=6)

    def test_extraction_is_deterministic(self) -> None:
        first = InvariantExtractor().extract(grammars(3), cluster_id="c1")
        second = InvariantExtractor().extract(grammars(3), cluster_id="c1")
        self.assertEqual(first.invariants, second.invariants)

    def test_ordering_is_deterministic(self) -> None:
        result = InvariantExtractor(threshold=0.1).extract(grammars(3), cluster_id="c1")
        keys = [item.key for item in result.all_features]
        self.assertEqual(keys, sorted(keys, key=lambda k: (-result.frequency_of(k), k)))

    def test_dominant_relation_appears_as_a_feature(self) -> None:
        result = InvariantExtractor(threshold=0.1).extract(grammars(3), cluster_id="c1")
        self.assertTrue(
            any(item.feature_family == "relation_presence" for item in result.invariants)
        )

    def test_attention_flow_appears_as_a_feature(self) -> None:
        result = InvariantExtractor(threshold=0.1).extract(grammars(3), cluster_id="c1")
        self.assertTrue(
            any(item.feature_family == "attention_flow" for item in result.invariants)
        )

    def test_by_family_filters(self) -> None:
        result = InvariantExtractor(threshold=0.1).extract(grammars(3), cluster_id="c1")
        for item in result.by_family("region_presence"):
            self.assertEqual(item.feature_family, "region_presence")

    def test_strongest_returns_sorted(self) -> None:
        result = InvariantExtractor(threshold=0.1).extract(grammars(3), cluster_id="c1")
        strongest = result.strongest(3)
        frequencies = [item.frequency for item in strongest]
        self.assertEqual(frequencies, sorted(frequencies, reverse=True))

    def test_serialises(self) -> None:
        payload = InvariantExtractor().extract(grammars(2), cluster_id="c1").as_dict()
        self.assertIn("invariants", payload)
        self.assertIn("all_features", payload)

    def test_render_works(self) -> None:
        self.assertIn("invariants", InvariantExtractor().extract(grammars(2), cluster_id="c1").render())

    def test_extractor_does_not_consult_a_declared_list(self) -> None:
        """The brief forbids hand-specified patterns."""

        source = inspect.getsource(InvariantExtractor.extract)
        for token in ("REGION_TYPES", "RELATION_TYPES", "ATTENTION_STAGES"):
            self.assertNotIn(token, source)

    def test_summarise_renders_multiple_sets(self) -> None:
        sets = [InvariantExtractor().extract(grammars(2), cluster_id=f"c{i}") for i in range(2)]
        self.assertIn("invariants", summarise_invariants(sets))

    def test_summarise_handles_empty(self) -> None:
        self.assertIn("no invariant", summarise_invariants([]))


class StrategyPatternTests(unittest.TestCase):
    """Strategy must be abstract, label-free, and material-free."""

    def _distil(self, count=4):
        gs = grammars(count)
        invariant_set = InvariantExtractor(threshold=0.5).extract(gs, cluster_id="c1")
        return distill_strategy(
            gs, invariant_set, creator_ids=[f"creator-{i}" for i in range(count)]
        )

    def test_distillation_produces_a_pattern(self) -> None:
        self.assertIsInstance(self._distil(), CreatorStrategyPattern)

    def test_attention_strategy_is_from_the_vocabulary(self) -> None:
        self.assertIn(self._distil().attention_strategy, ATTENTION_STRATEGIES)

    def test_hierarchy_stages_are_from_the_vocabulary(self) -> None:
        for stage in self._distil().information_hierarchy:
            self.assertIn(stage, HIERARCHY_STAGES)

    def test_hierarchy_is_in_delivery_order(self) -> None:
        pattern = self._distil()
        self.assertEqual(
            list(pattern.information_hierarchy),
            [s for s in HIERARCHY_STAGES if s in pattern.information_hierarchy],
        )

    def test_composition_moves_are_from_the_vocabulary(self) -> None:
        for move in self._distil().composition_strategy:
            self.assertIn(move, COMPOSITION_MOVES)

    def test_support_matches_member_count(self) -> None:
        self.assertEqual(self._distil(4).support, 4)

    def test_creator_ids_are_recorded(self) -> None:
        self.assertEqual(len(self._distil(3).creator_ids), 3)

    def test_evidence_records_label_independence(self) -> None:
        evidence = self._distil().evidence
        self.assertEqual(evidence["derived_from"], "grammar+invariants")
        self.assertFalse(evidence["layout_label_used"])

    def test_pattern_carries_no_material(self) -> None:
        """The brief forbids colour values, image references, and pixel data."""

        payload = json.dumps(self._distil().as_dict()).lower()
        for forbidden in (".png", ".jpg", "base64", "pixel", "rgb(", "bitmap", "#"):
            self.assertNotIn(forbidden, payload)

    def test_pattern_has_no_asset_reference_field(self) -> None:
        fields = set(CreatorStrategyPattern.__dataclass_fields__)
        for forbidden in ("asset_reference", "image_path", "pixels", "colour", "colors"):
            self.assertNotIn(forbidden, fields)

    def test_unknown_attention_strategy_is_rejected(self) -> None:
        with self.assertRaises(StrategyError):
            CreatorStrategyPattern(
                pattern_id="p",
                cluster_id="c",
                attention_strategy="vibes",
                information_hierarchy=("hook",),
                composition_strategy=(),
                invariants=(),
                support=1,
                creator_ids=(),
                confidence=0.5,
            )

    def test_out_of_order_hierarchy_is_rejected(self) -> None:
        with self.assertRaises(StrategyError):
            CreatorStrategyPattern(
                pattern_id="p",
                cluster_id="c",
                attention_strategy="headline_first",
                information_hierarchy=("action", "hook"),
                composition_strategy=(),
                invariants=(),
                support=1,
                creator_ids=(),
                confidence=0.5,
            )

    def test_unknown_composition_move_is_rejected(self) -> None:
        with self.assertRaises(StrategyError):
            CreatorStrategyPattern(
                pattern_id="p",
                cluster_id="c",
                attention_strategy="headline_first",
                information_hierarchy=(),
                composition_strategy=("diagonal_cascade",),
                invariants=(),
                support=1,
                creator_ids=(),
                confidence=0.5,
            )

    def test_confidence_outside_unit_range_is_rejected(self) -> None:
        with self.assertRaises(StrategyError):
            CreatorStrategyPattern(
                pattern_id="p",
                cluster_id="c",
                attention_strategy="headline_first",
                information_hierarchy=(),
                composition_strategy=(),
                invariants=(),
                support=1,
                creator_ids=(),
                confidence=1.5,
            )

    def test_empty_grammars_are_rejected(self) -> None:
        invariant_set = InvariantExtractor().extract(grammars(2), cluster_id="c1")
        with self.assertRaises(StrategyError):
            distill_strategy([], invariant_set)

    def test_mismatched_invariant_set_is_rejected(self) -> None:
        gs = grammars(4)
        invariant_set = InvariantExtractor().extract(gs[:2], cluster_id="c1")
        with self.assertRaises(StrategyError):
            distill_strategy(gs, invariant_set)

    def test_invalid_support_is_rejected(self) -> None:
        gs = grammars(2)
        invariant_set = InvariantExtractor().extract(gs, cluster_id="c1")
        with self.assertRaises(StrategyError):
            distill_strategy(gs, invariant_set, support=0.0)

    def test_distillation_is_deterministic(self) -> None:
        first = self._distil()
        second = self._distil()
        self.assertEqual(first.attention_strategy, second.attention_strategy)
        self.assertEqual(first.information_hierarchy, second.information_hierarchy)
        self.assertEqual(first.composition_strategy, second.composition_strategy)

    def test_strategy_does_not_read_a_layout_label(self) -> None:
        """M3's flaw: pattern extraction depended on the cluster label."""

        source = inspect.getsource(distill_strategy)
        tree = ast.parse(source)
        body = tree.body[0].body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            body = body[1:]
        code = "\n".join(ast.unparse(node) for node in body)
        for token in ("layout_template_class", "layout_class", "template_class"):
            self.assertNotIn(token, code)

    def test_strategy_module_never_reads_layout_class(self) -> None:
        from multimodal_creator.grammar import strategy as strategy_module

        source = inspect.getsource(strategy_module)
        self.assertNotIn("layout_template_class", source)

    def test_attention_strategy_folds_subtitle_into_headline(self) -> None:
        """A subtitle lead and a headline lead are the same strategic move."""

        obs = observation(
            "sub",
            regions=(
                {"region_id": "bg", "role": "background", "box": {"x": 0, "y": 0, "w": 1, "h": 1}, "layer_order": 0},
                {"region_id": "s", "role": "subtitle", "box": {"x": 0.1, "y": 0.05, "w": 0.8, "h": 0.1}, "layer_order": 1},
                {"region_id": "b", "role": "body", "box": {"x": 0.1, "y": 0.3, "w": 0.8, "h": 0.3}, "layer_order": 1},
            ),
        )
        gs = [extract_grammar(obs).grammar for _ in range(3)]
        invariant_set = InvariantExtractor(threshold=0.5).extract(gs, cluster_id="c")
        pattern = distill_strategy(gs, invariant_set)
        self.assertEqual(pattern.attention_strategy, "headline_first")

    def test_hook_requires_text_near_the_top(self) -> None:
        """Text at the bottom is not an entry hook."""

        obs = observation(
            "bottom",
            regions=(
                {"region_id": "bg", "role": "background", "box": {"x": 0, "y": 0, "w": 1, "h": 1}, "layer_order": 0},
                {"region_id": "s", "role": "subject", "box": {"x": 0.1, "y": 0.05, "w": 0.8, "h": 0.5}, "layer_order": 1},
                {"region_id": "t", "role": "title", "box": {"x": 0.1, "y": 0.7, "w": 0.8, "h": 0.15}, "layer_order": 1},
            ),
        )
        gs = [extract_grammar(obs).grammar for _ in range(3)]
        invariant_set = InvariantExtractor(threshold=0.5).extract(gs, cluster_id="c")
        pattern = distill_strategy(gs, invariant_set)
        self.assertNotIn("hook", pattern.information_hierarchy)

    def test_render_works(self) -> None:
        self.assertIn("attention", self._distil().render())


class ConstraintTests(unittest.TestCase):
    """The constraint prototype must be a design surface, never a generator."""

    def _constraints(self):
        gs = grammars(4)
        invariant_set = InvariantExtractor(threshold=0.5).extract(gs, cluster_id="c1")
        pattern = distill_strategy(gs, invariant_set, creator_ids=["a", "b"])
        return constraints_from_strategy(pattern)

    def test_constraints_are_derived(self) -> None:
        self.assertIsInstance(self._constraints(), VisualConstraint)

    def test_constraint_is_not_generative(self) -> None:
        self.assertFalse(self._constraints().generative)

    def test_generative_constraint_is_rejected(self) -> None:
        with self.assertRaises(ConstraintError):
            VisualConstraint(
                constraint_id="c",
                pattern_id="p",
                layout_constraints=(),
                attention_constraints=(),
                style_constraints=(),
                generative=True,
            )

    def test_every_constraint_names_its_source(self) -> None:
        for constraint in self._constraints().all_constraints():
            self.assertTrue(constraint.source_feature.strip())

    def test_families_match_the_brief(self) -> None:
        self.assertEqual(
            set(CONSTRAINT_FAMILIES),
            {"layout_constraints", "attention_constraints", "style_constraints"},
        )

    def test_constraint_families_are_populated(self) -> None:
        constraints = self._constraints()
        self.assertTrue(constraints.layout_constraints or constraints.attention_constraints)

    def test_strength_values_are_valid(self) -> None:
        for constraint in self._constraints().all_constraints():
            self.assertIn(constraint.strength, ("required", "preferred"))

    def test_required_subset_is_consistent(self) -> None:
        constraints = self._constraints()
        for constraint in constraints.required():
            self.assertEqual(constraint.strength, "required")

    def test_unknown_family_is_rejected(self) -> None:
        with self.assertRaises(ConstraintError):
            Constraint("vibes", "x", "required", 0.9, "f")

    def test_unknown_strength_is_rejected(self) -> None:
        with self.assertRaises(ConstraintError):
            Constraint("layout_constraints", "x", "mandatory", 0.9, "f")

    def test_constraint_without_source_is_rejected(self) -> None:
        with self.assertRaises(ConstraintError):
            Constraint("layout_constraints", "x", "required", 0.9, "")

    def test_empty_constraint_value_is_rejected(self) -> None:
        with self.assertRaises(ConstraintError):
            Constraint("layout_constraints", "  ", "required", 0.9, "f")

    def test_frequency_outside_unit_range_is_rejected(self) -> None:
        with self.assertRaises(ConstraintError):
            Constraint("layout_constraints", "x", "required", 1.5, "f")

    def test_by_family_lookup(self) -> None:
        constraints = self._constraints()
        for family in CONSTRAINT_FAMILIES:
            self.assertEqual(constraints.by_family(family), getattr(constraints, family))

    def test_unknown_family_lookup_is_rejected(self) -> None:
        with self.assertRaises(ConstraintError):
            self._constraints().by_family("vibes")

    def test_invalid_required_frequency_is_rejected(self) -> None:
        gs = grammars(3)
        invariant_set = InvariantExtractor(threshold=0.5).extract(gs, cluster_id="c1")
        pattern = distill_strategy(gs, invariant_set)
        with self.assertRaises(ConstraintError):
            constraints_from_strategy(pattern, required_frequency=0.0)

    def test_carries_no_pixel_data(self) -> None:
        """Check for actual material, not for the word describing its absence."""

        payload = self._constraints().as_dict()
        # The explanatory note legitimately says "carries no pixels", so the
        # check runs on the constraint list, not on the whole serialisation.
        constraints = (
            payload["layout_constraints"]
            + payload["attention_constraints"]
            + payload["style_constraints"]
        )
        serialised = json.dumps(constraints).lower()
        for forbidden in (".png", ".jpg", "base64", "bitmap", "data:image"):
            self.assertNotIn(forbidden, serialised)
        fields = set(Constraint.__dataclass_fields__)
        for forbidden in ("pixels", "image_data", "colour_rgb", "asset_path"):
            self.assertNotIn(forbidden, fields)

    def test_as_dict_marks_it_non_generative(self) -> None:
        self.assertFalse(self._constraints().as_dict()["generative"])

    def test_render_works(self) -> None:
        self.assertIn("visual constraints", self._constraints().render())

    def test_attention_strategy_becomes_a_constraint(self) -> None:
        constraints = self._constraints()
        values = {c.value for c in constraints.attention_constraints}
        self.assertTrue(
            values & set(ATTENTION_STRATEGIES) or any(v.startswith("hierarchy:") for v in values)
        )


if __name__ == "__main__":
    unittest.main()
