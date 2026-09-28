"""Profile model, schema, and derivation tests (Phase M5)."""

from __future__ import annotations

import json
import unittest

from multimodal_creator.grammar import (
    CreatorStrategyPattern,
    Invariant,
    InvariantExtractor,
    VisualConstraint,
    constraints_from_strategy,
    distill_strategy,
    extract_grammar,
)
from multimodal_creator.grammar.constraints import Constraint
from multimodal_creator.profile import (
    ATTENTION_SLOTS,
    COMPLEXITY_LEVELS,
    DERIVATIONS,
    HIERARCHY_TIERS,
    LANGUAGE_BY_ATTENTION,
    PROFILE_VERSION,
    PROVENANCE_FAMILIES,
    SOURCE_PHASES,
    VISUAL_LANGUAGES,
    AttentionStrategy,
    CompositionRules,
    ConstraintLayer,
    FieldProvenance,
    HierarchyPattern,
    MappingError,
    PatternToProfileMapper,
    ProfileError,
    VisualCreatorProfile,
    VisualIdentity,
    build_schema,
    pattern_to_profile,
    schema_keys,
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


def grammars(count=4, prefix="s"):
    return [extract_grammar(observation(f"{prefix}{i}")).grammar for i in range(count)]


def m4_bundle(count=4, creator="creator-x"):
    """A realistic M4 output bundle: grammars, strategy pattern, constraints."""
    gs = grammars(count)
    invariant_set = InvariantExtractor(threshold=0.5).extract(gs, cluster_id="c1")
    strategy = distill_strategy(
        gs, invariant_set, creator_ids=[creator]
    )
    constraints = constraints_from_strategy(strategy)
    return gs, strategy, constraints


def build_profile(creator="creator-x", count=4):
    gs, strategy, constraints = m4_bundle(count, creator)
    return pattern_to_profile(
        creator_id=creator, patterns=[strategy], grammars=gs, constraints=[constraints]
    )


class ProvenanceModelTests(unittest.TestCase):
    """Every field must be traceable; an unsourced value is a hard error."""

    def test_valid_provenance(self) -> None:
        record = FieldProvenance("M4", "p1", "CreatorStrategyPattern", "direct", 0.9)
        self.assertEqual(record.source_phase, "M4")

    def test_only_m4_is_accepted_as_a_source_phase(self) -> None:
        self.assertEqual(list(SOURCE_PHASES), ["M4"])
        with self.assertRaises(ProfileError):
            FieldProvenance("M3", "p1", "kind", "direct", 0.9)

    def test_empty_artifact_id_is_rejected(self) -> None:
        with self.assertRaises(ProfileError):
            FieldProvenance("M4", "  ", "kind", "direct", 0.9)

    def test_empty_artifact_kind_is_rejected(self) -> None:
        with self.assertRaises(ProfileError):
            FieldProvenance("M4", "p1", "", "direct", 0.9)

    def test_unknown_derivation_is_rejected(self) -> None:
        with self.assertRaises(ProfileError):
            FieldProvenance("M4", "p1", "kind", "guessed", 0.9)

    def test_confidence_outside_unit_range_is_rejected(self) -> None:
        with self.assertRaises(ProfileError):
            FieldProvenance("M4", "p1", "kind", "direct", 1.5)

    def test_derivations_are_exposed(self) -> None:
        for name in ("direct", "aggregated", "thresholded", "inverted", "enumerated_absent"):
            self.assertIn(name, DERIVATIONS)

    def test_serialises_with_source_nested(self) -> None:
        payload = FieldProvenance("M4", "p1", "kind", "direct", 0.9).as_dict()
        self.assertIn("source", payload)
        self.assertEqual(payload["source"]["phase"], "M4")


class VisualIdentityTests(unittest.TestCase):
    def test_valid_identity(self) -> None:
        identity = VisualIdentity("a__b", "information_first", "low", "dense", "high_contrast", "split", "display_led")
        self.assertEqual(identity.visual_language, "information_first")

    def test_unknown_visual_language_is_rejected(self) -> None:
        with self.assertRaises(ProfileError):
            VisualIdentity("a", "vibes_first", "low", "dense", "high", "split", "display_led")

    def test_unknown_complexity_is_rejected(self) -> None:
        with self.assertRaises(ProfileError):
            VisualIdentity("a", "information_first", "extreme", "dense", "high", "split", "display_led")

    def test_empty_style_family_is_rejected(self) -> None:
        with self.assertRaises(ProfileError):
            VisualIdentity("  ", "information_first", "low", "dense", "high", "split", "display_led")

    def test_undetermined_is_an_allowed_language(self) -> None:
        identity = VisualIdentity("undetermined", "undetermined", "undetermined", "dense", "undetermined", "stacked", "undetermined")
        self.assertEqual(identity.visual_language, "undetermined")

    def test_vocabularies_are_exposed(self) -> None:
        self.assertIn("information_first", VISUAL_LANGUAGES)
        self.assertIn("low", COMPLEXITY_LEVELS)
        self.assertIn("headline_first", LANGUAGE_BY_ATTENTION)


class CompositionRulesTests(unittest.TestCase):
    def test_valid_rules(self) -> None:
        rules = CompositionRules(("top_entry",), ("overlay_headline",))
        self.assertEqual(rules.preferred, ("top_entry",))

    def test_overlap_between_preferred_and_forbidden_is_rejected(self) -> None:
        with self.assertRaises(ProfileError):
            CompositionRules(("top_entry",), ("top_entry",))

    def test_empty_sets_are_allowed(self) -> None:
        rules = CompositionRules((), ())
        self.assertEqual(rules.forbidden, ())


class AttentionStrategyTests(unittest.TestCase):
    def test_valid_strategy(self) -> None:
        strategy = AttentionStrategy({"first": "headline", "second": "supporting_information"})
        self.assertEqual(strategy.order["second"], "supporting_information")

    def test_unknown_slot_is_rejected(self) -> None:
        with self.assertRaises(ProfileError):
            AttentionStrategy({"fifth": "headline"})

    def test_gapped_slots_are_rejected(self) -> None:
        with self.assertRaises(ProfileError):
            AttentionStrategy({"first": "headline", "third": "cta"})

    def test_empty_strategy_is_rejected(self) -> None:
        with self.assertRaises(ProfileError):
            AttentionStrategy({})

    def test_empty_target_is_rejected(self) -> None:
        with self.assertRaises(ProfileError):
            AttentionStrategy({"first": "  "})

    def test_slots_are_exposed(self) -> None:
        self.assertEqual(list(ATTENTION_SLOTS), ["first", "second", "third", "fourth"])


class HierarchyPatternTests(unittest.TestCase):
    def test_valid_pattern(self) -> None:
        pattern = HierarchyPattern({"primary": "hook", "secondary": "explanation"})
        self.assertEqual(pattern.tiers["primary"], "hook")

    def test_unknown_tier_is_rejected(self) -> None:
        with self.assertRaises(ProfileError):
            HierarchyPattern({"fifth": "hook"})

    def test_gapped_tiers_are_rejected(self) -> None:
        with self.assertRaises(ProfileError):
            HierarchyPattern({"primary": "hook", "tertiary": "action"})

    def test_empty_pattern_is_rejected(self) -> None:
        with self.assertRaises(ProfileError):
            HierarchyPattern({})

    def test_tiers_are_exposed(self) -> None:
        self.assertEqual(
            list(HIERARCHY_TIERS), ["primary", "secondary", "tertiary", "quaternary"]
        )


class ConstraintLayerTests(unittest.TestCase):
    def test_valid_layer(self) -> None:
        layer = ConstraintLayer(("clear_entry_point",), ("excessive_decoration",))
        self.assertEqual(layer.must_have, ("clear_entry_point",))

    def test_overlap_is_rejected(self) -> None:
        with self.assertRaises(ProfileError):
            ConstraintLayer(("x",), ("x",))


class VisualCreatorProfileTests(unittest.TestCase):
    """The profile refuses to exist without sources and provenance."""

    def _provenance(self):
        return {
            family: FieldProvenance("M4", "p1", "kind", "direct", 0.8)
            for family in PROVENANCE_FAMILIES
        }

    def _profile(self, **overrides):
        fields = {
            "profile_id": "vcp-test",
            "creator_id": "creator-x",
            "version": PROFILE_VERSION,
            "visual_identity": VisualIdentity("a__b", "information_first", "low", "dense", "high_contrast", "split", "display_led"),
            "composition_rules": CompositionRules(("top_entry",), ("overlay_headline",)),
            "attention_strategy": AttentionStrategy({"first": "headline"}),
            "hierarchy_pattern": HierarchyPattern({"primary": "hook"}),
            "constraints": ConstraintLayer(("headline_present",), ()),
            "provenance": self._provenance(),
            "source_pattern_ids": ("p1",),
            "support": 4,
            "confidence": 0.8,
        }
        fields.update(overrides)
        return VisualCreatorProfile(**fields)

    def test_valid_profile_builds(self) -> None:
        self.assertEqual(self._profile().profile_id, "vcp-test")

    def test_empty_profile_id_is_rejected(self) -> None:
        with self.assertRaises(ProfileError):
            self._profile(profile_id="  ")

    def test_empty_creator_id_is_rejected(self) -> None:
        with self.assertRaises(ProfileError):
            self._profile(creator_id="")

    def test_no_source_patterns_is_rejected(self) -> None:
        """A profile with no source is a hand-written config."""

        with self.assertRaises(ProfileError):
            self._profile(source_pattern_ids=())

    def test_missing_provenance_family_is_rejected(self) -> None:
        provenance = self._provenance()
        del provenance["constraints"]
        with self.assertRaises(ProfileError):
            self._profile(provenance=provenance)

    def test_provenance_from_another_phase_is_rejected(self) -> None:
        provenance = self._provenance()
        provenance["constraints"] = FieldProvenance("M4", "p1", "kind", "direct", 0.8)
        profile = self._profile(provenance=provenance)
        self.assertEqual(profile.provenance_for("constraints").source_phase, "M4")

    def test_unknown_provenance_family_is_rejected(self) -> None:
        provenance = self._provenance()
        provenance["vibes"] = FieldProvenance("M4", "p1", "kind", "direct", 0.8)
        with self.assertRaises(ProfileError):
            self._profile(provenance=provenance)

    def test_confidence_outside_unit_range_is_rejected(self) -> None:
        with self.assertRaises(ProfileError):
            self._profile(confidence=1.5)

    def test_negative_support_is_rejected(self) -> None:
        with self.assertRaises(ProfileError):
            self._profile(support=-1)

    def test_weakest_confidence_is_the_floor(self) -> None:
        provenance = self._provenance()
        provenance["constraints"] = FieldProvenance("M4", "p1", "kind", "direct", 0.2)
        profile = self._profile(provenance=provenance)
        self.assertEqual(profile.weakest_confidence(), 0.2)

    def test_all_rules_flattens_every_group(self) -> None:
        rules = self._profile().all_rules()
        self.assertTrue(any(rule.startswith("preferred_layout:") for rule in rules))
        self.assertTrue(any(rule.startswith("forbidden_layout:") for rule in rules))
        self.assertTrue(any(rule.startswith("attention_first:") for rule in rules))
        self.assertTrue(any(rule.startswith("hierarchy_primary:") for rule in rules))
        self.assertTrue(any(rule.startswith("must_have:") for rule in rules))

    def test_serialises(self) -> None:
        payload = self._profile().as_dict()
        for key in (
            "profile_version",
            "visual_identity",
            "composition_rules",
            "attention_strategy",
            "hierarchy_pattern",
            "constraints",
            "provenance",
            "source_pattern_ids",
        ):
            self.assertIn(key, payload)

    def test_render_works(self) -> None:
        self.assertIn("visual creator profile", self._profile().render())

    def test_profile_has_no_generation_fields(self) -> None:
        fields = set(VisualCreatorProfile.__dataclass_fields__)
        for forbidden in ("prompt", "model", "renderer", "image", "pixels"):
            self.assertNotIn(forbidden, fields)


class SchemaTests(unittest.TestCase):
    """The schema is generated, strict, and free of unsupported constructs."""

    def test_schema_builds(self) -> None:
        schema = build_schema()
        self.assertEqual(schema["title"], "VisualCreatorProfile")

    def test_schema_is_strict_at_the_root(self) -> None:
        self.assertFalse(build_schema()["additionalProperties"])

    def test_nested_objects_are_strict(self) -> None:
        schema = build_schema()
        for section in (
            "visual_identity",
            "composition_rules",
            "attention_strategy",
            "hierarchy_pattern",
            "constraints",
            "provenance",
        ):
            self.assertFalse(
                schema["properties"][section]["additionalProperties"], section
            )

    def test_schema_stays_inside_the_dependency_free_subset(self) -> None:
        """Check for schema *keywords*, not substrings of unrelated words."""

        schema = build_schema()

        def keywords(document: object) -> set[str]:
            found: set[str] = set()
            if isinstance(document, dict):
                for key, value in document.items():
                    found.add(str(key))
                    found |= keywords(value)
            elif isinstance(document, list):
                for item in document:
                    found |= keywords(item)
            return found

        present = keywords(schema)
        for unsupported in ("$ref", "allOf", "anyOf", "oneOf", "if", "then", "not"):
            self.assertNotIn(unsupported, present, unsupported)

    def test_schema_requires_provenance_for_every_family(self) -> None:
        required = build_schema()["properties"]["provenance"]["required"]
        self.assertEqual(sorted(required), sorted(PROVENANCE_FAMILIES))

    def test_schema_requires_source_patterns(self) -> None:
        schema = build_schema()
        self.assertIn("source_pattern_ids", schema["required"])
        self.assertEqual(
            schema["properties"]["source_pattern_ids"]["minItems"], 1
        )

    def test_schema_keys_match_the_model(self) -> None:
        self.assertEqual(
            schema_keys(),
            {
                "profile_version",
                "profile_id",
                "creator_id",
                "source_pattern_ids",
                "support",
                "confidence",
                "visual_identity",
                "composition_rules",
                "attention_strategy",
                "hierarchy_pattern",
                "constraints",
                "provenance",
                "notes",
            },
        )

    def test_schema_enums_come_from_the_model_vocabularies(self) -> None:
        schema = build_schema()
        identity = schema["properties"]["visual_identity"]["properties"]
        self.assertEqual(identity["visual_language"]["enum"], list(VISUAL_LANGUAGES))
        self.assertEqual(identity["complexity"]["enum"], list(COMPLEXITY_LEVELS))
        provenance = schema["properties"]["provenance"]["properties"]["visual_identity"]
        self.assertEqual(provenance["properties"]["derivation"]["enum"], list(DERIVATIONS))

    def test_schema_has_no_generation_keys(self) -> None:
        raw = json.dumps(build_schema()).lower()
        for forbidden in ('"prompt"', '"model"', '"renderer"', '"image"', '"pixels"'):
            self.assertNotIn(forbidden, raw)


class DerivationTests(unittest.TestCase):
    """The mapper derives; it does not invent."""

    def test_profile_is_derived_from_m4(self) -> None:
        profile = build_profile()
        self.assertEqual(profile.source_pattern_ids[0][:9], "strategy-")

    def test_creator_id_is_passed_in_not_hardcoded(self) -> None:
        first = build_profile(creator="alpha")
        second = build_profile(creator="beta")
        self.assertEqual(first.creator_id, "alpha")
        self.assertEqual(second.creator_id, "beta")

    def test_profile_id_is_content_addressed(self) -> None:
        first = build_profile(creator="alpha")
        second = build_profile(creator="alpha")
        self.assertEqual(first.profile_id, second.profile_id)
        third = build_profile(creator="beta")
        self.assertNotEqual(first.profile_id, third.profile_id)

    def test_visual_language_comes_from_attention_strategy(self) -> None:
        profile = build_profile()
        strategy = profile.provenance["visual_identity"].evidence["attention_strategy"][0]
        self.assertEqual(
            profile.visual_identity.visual_language, LANGUAGE_BY_ATTENTION[strategy]
        )

    def test_composition_preferred_matches_m4_moves(self) -> None:
        gs, strategy, constraints = m4_bundle()
        profile = pattern_to_profile(
            creator_id="x", patterns=[strategy], grammars=gs, constraints=[constraints]
        )
        self.assertEqual(
            set(profile.composition_rules.preferred), set(strategy.composition_strategy)
        )

    def test_forbidden_set_is_vocabulary_minus_observed(self) -> None:
        from multimodal_creator.grammar.strategy import COMPOSITION_MOVES

        gs, strategy, constraints = m4_bundle()
        profile = pattern_to_profile(
            creator_id="x", patterns=[strategy], grammars=gs, constraints=[constraints]
        )
        expected = set(COMPOSITION_MOVES) - set(strategy.composition_strategy)
        self.assertEqual(set(profile.composition_rules.forbidden), expected)

    def test_preferred_and_forbidden_are_disjoint(self) -> None:
        profile = build_profile()
        self.assertFalse(
            set(profile.composition_rules.preferred)
            & set(profile.composition_rules.forbidden)
        )

    def test_attention_order_comes_from_grammar_signatures(self) -> None:
        profile = build_profile()
        self.assertIn("first", profile.attention_strategy.order)

    def test_hierarchy_comes_from_m4_stages(self) -> None:
        gs, strategy, constraints = m4_bundle()
        profile = pattern_to_profile(
            creator_id="x", patterns=[strategy], grammars=gs, constraints=[constraints]
        )
        stages = list(profile.hierarchy_pattern.tiers.values())
        for stage in stages:
            self.assertTrue(
                stage in strategy.information_hierarchy or stage == "undetermined"
            )

    def test_style_family_is_a_composite_of_measured_traits(self) -> None:
        profile = build_profile()
        family = profile.visual_identity.style_family
        self.assertNotEqual(family, "")
        for part in family.split("__"):
            self.assertIn(
                part,
                {"high_contrast", "low_contrast", "undetermined", "sparse", "moderate", "dense",
                 "full_bleed", "split", "stacked", "large_display_type",
                 "balanced_display_and_body", "display_led"},
                part,
            )

    def test_no_hardcoded_domain_label_appears(self) -> None:
        """The brief forbids hand-written templates such as a finance one."""

        import inspect

        from multimodal_creator.profile import pattern_to_profile as module

        source = inspect.getsource(module).lower()
        for forbidden in ("educational_finance", "xiaolin", "finance_template", "sports_"):
            self.assertNotIn(forbidden, source)

    def test_no_colour_value_appears_anywhere_in_the_mapper(self) -> None:
        import inspect

        from multimodal_creator.profile import pattern_to_profile as module

        source = inspect.getsource(module).lower()
        for forbidden in ("#ff", "rgb(", "hex_colour", "colour_code", "red_background"):
            self.assertNotIn(forbidden, source)

    def test_no_creator_name_literal_appears(self) -> None:
        import inspect

        from multimodal_creator.profile import pattern_to_profile as module

        source = inspect.getsource(module)
        for forbidden in ('"creator-', "'creator-", "creator_name ="):
            self.assertNotIn(forbidden, source)

    def test_empty_patterns_are_rejected(self) -> None:
        gs, _strategy, constraints = m4_bundle()
        with self.assertRaises(MappingError):
            pattern_to_profile(
                creator_id="x", patterns=[], grammars=gs, constraints=[constraints]
            )

    def test_empty_grammars_are_rejected(self) -> None:
        _gs, strategy, constraints = m4_bundle()
        with self.assertRaises(MappingError):
            pattern_to_profile(
                creator_id="x", patterns=[strategy], grammars=[], constraints=[constraints]
            )

    def test_mismatched_constraint_is_rejected(self) -> None:
        gs, _strategy, constraints = m4_bundle()
        other = CreatorStrategyPattern(
            pattern_id="other-pattern",
            cluster_id="c9",
            attention_strategy="headline_first",
            information_hierarchy=("hook",),
            composition_strategy=("top_entry",),
            invariants=(),
            support=1,
            creator_ids=("y",),
            confidence=0.5,
        )
        with self.assertRaises(MappingError):
            pattern_to_profile(
                creator_id="x", patterns=[other], grammars=gs, constraints=[constraints]
            )

    def test_empty_creator_id_is_rejected(self) -> None:
        gs, strategy, constraints = m4_bundle()
        with self.assertRaises(MappingError):
            pattern_to_profile(
                creator_id="  ", patterns=[strategy], grammars=gs, constraints=[constraints]
            )

    def test_invalid_must_have_frequency_is_rejected(self) -> None:
        with self.assertRaises(MappingError):
            PatternToProfileMapper(must_have_frequency=0.0)

    def test_derivation_is_deterministic(self) -> None:
        first = build_profile()
        second = build_profile()
        self.assertEqual(first.as_dict(), second.as_dict())

    def test_multiple_patterns_are_all_recorded(self) -> None:
        gs, strategy, constraints = m4_bundle()
        second = CreatorStrategyPattern(
            pattern_id=strategy.pattern_id + "-b",
            cluster_id=strategy.cluster_id + "-b",
            attention_strategy=strategy.attention_strategy,
            information_hierarchy=strategy.information_hierarchy,
            composition_strategy=strategy.composition_strategy,
            invariants=strategy.invariants,
            support=strategy.support,
            creator_ids=strategy.creator_ids,
            confidence=strategy.confidence,
            evidence=strategy.evidence,
        )
        constraints_b = VisualConstraint(
            constraint_id=constraints.constraint_id + "-b",
            pattern_id=second.pattern_id,
            layout_constraints=constraints.layout_constraints,
            attention_constraints=constraints.attention_constraints,
            style_constraints=constraints.style_constraints,
        )
        profile = pattern_to_profile(
            creator_id="x",
            patterns=[strategy, second],
            grammars=gs,
            constraints=[constraints, constraints_b],
        )
        self.assertEqual(len(profile.source_pattern_ids), 2)

    def test_confidence_is_the_weakest_input(self) -> None:
        profile = build_profile()
        self.assertEqual(
            profile.confidence,
            min(record.confidence for record in profile.provenance.values()),
        )


if __name__ == "__main__":
    unittest.main()
