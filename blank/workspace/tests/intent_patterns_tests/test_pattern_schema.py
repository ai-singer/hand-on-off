"""Requirement: pattern schema - entities, relations, frames, patterns."""

from __future__ import annotations

import json
import unittest

from risk_evaluation.intent_patterns.financial_guarantee import (
    ENTITIES,
    FINANCIAL_GUARANTEE,
    GUARANTEE,
    GUARANTORS,
    PATTERNS,
    RISK_REMOVED,
)
from risk_evaluation.intent_patterns.model import (
    ACTIVE,
    ATTRIBUTIVE,
    COPULAR,
    FRAME_KINDS,
    NOMINAL,
    PASSIVE,
    EntityLexicon,
    EntityType,
    Frame,
    IntentPattern,
    PatternError,
    PatternSet,
    Relation,
    frame_kinds_covered,
)


class EntityTypeTests(unittest.TestCase):
    def test_an_entity_type_needs_a_name_and_alternatives(self) -> None:
        with self.assertRaises(PatternError):
            EntityType("", (r"x",))
        with self.assertRaises(PatternError):
            EntityType("X", ())

    def test_the_pattern_is_a_non_capturing_alternation(self) -> None:
        entity = EntityType("X", (r"a", r"b"))

        self.assertEqual(entity.pattern, "(?:a|b)")

    def test_a_bad_alternative_fails_loudly(self) -> None:
        with self.assertRaises(Exception):
            EntityType("X", (r"(unclosed",))

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(EntityType("X", (r"a",), "why").as_dict())


class LexiconTests(unittest.TestCase):
    def test_every_declared_entity_type_is_present(self) -> None:
        self.assertEqual(
            set(ENTITIES.names()), {"RETURN", "CAPITAL", "VALUE", "OUTCOME"}
        )

    def test_group_combines_several_types(self) -> None:
        group = ENTITIES.group("RETURN", "CAPITAL")

        self.assertIn("returns?", group)
        self.assertIn("capital", group)

    def test_an_unknown_type_raises(self) -> None:
        with self.assertRaises(PatternError):
            ENTITIES.get("NOT_A_TYPE")

    def test_membership_works(self) -> None:
        self.assertIn("RETURN", ENTITIES)
        self.assertNotIn("NOPE", ENTITIES)

    def test_an_empty_lexicon_is_rejected(self) -> None:
        with self.assertRaises(PatternError):
            EntityLexicon({})

    def test_the_guarantor_entity_is_separate_from_the_object_entities(self) -> None:
        """Who promises is not what is promised."""

        self.assertNotIn("GUARANTOR", ENTITIES)
        self.assertIn("GUARANTOR", GUARANTORS.name)


class FrameTests(unittest.TestCase):
    def test_every_declared_frame_kind_is_constructible(self) -> None:
        for kind in FRAME_KINDS:
            self.assertEqual(Frame(kind, r"x", ("predicate",)).kind, kind)

    def test_an_unknown_frame_kind_is_rejected(self) -> None:
        with self.assertRaises(PatternError):
            Frame("vibes", r"x", ("predicate",))

    def test_a_frame_needs_a_role(self) -> None:
        with self.assertRaises(PatternError):
            Frame(ACTIVE, r"x", ())

    def test_a_bad_template_fails_loudly(self) -> None:
        with self.assertRaises(Exception):
            Frame(ACTIVE, r"(unclosed", ("predicate",))

    def test_self_negating_defaults_to_false(self) -> None:
        self.assertFalse(Frame(ACTIVE, r"x", ("predicate",)).self_negating)

    def test_as_dict_records_self_negation(self) -> None:
        payload = Frame(ACTIVE, r"x", ("predicate",), "why", True).as_dict()

        self.assertTrue(payload["self_negating"])


class RelationTests(unittest.TestCase):
    def test_a_relation_needs_frames(self) -> None:
        with self.assertRaises(PatternError):
            Relation("R", (), ())

    def test_the_guarantee_relation_realises_every_required_frame(self) -> None:
        """The phase requires active, passive, copular, attributive, nominal."""

        self.assertEqual(
            set(GUARANTEE.kinds),
            {ACTIVE, PASSIVE, COPULAR, ATTRIBUTIVE, NOMINAL},
        )

    def test_frames_of_filters_by_kind(self) -> None:
        self.assertEqual(len(GUARANTEE.frames_of(ACTIVE)), 1)
        self.assertEqual(len(GUARANTEE.frames_of(NOMINAL)), 2)

    def test_the_risk_removed_relation_is_present_for_parity(self) -> None:
        """Without it, a recall change could come from dropped coverage."""

        self.assertTrue(RISK_REMOVED.frames)
        self.assertTrue(any(f.self_negating for f in RISK_REMOVED.frames))

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(GUARANTEE.as_dict())


class IntentPatternTests(unittest.TestCase):
    def test_the_six_documented_fields_are_present(self) -> None:
        payload = FINANCIAL_GUARANTEE.as_dict()

        self.assertEqual(
            set(payload),
            {
                "id",
                "category",
                "required_entities",
                "relations",
                "confidence",
                "evidence",
            },
        )

    def test_the_pattern_id_property_matches(self) -> None:
        self.assertEqual(FINANCIAL_GUARANTEE.id, FINANCIAL_GUARANTEE.pattern_id)

    def test_confidence_must_be_within_zero_and_one(self) -> None:
        with self.assertRaises(PatternError):
            IntentPattern("p", "c", ("RETURN",), (GUARANTEE,), 1.5, "why")

    def test_evidence_is_required(self) -> None:
        with self.assertRaises(PatternError):
            IntentPattern("p", "c", ("RETURN",), (GUARANTEE,), 0.5, "  ")

    def test_relations_are_required(self) -> None:
        with self.assertRaises(PatternError):
            IntentPattern("p", "c", ("RETURN",), (), 0.5, "why")

    def test_the_pattern_declares_its_relations(self) -> None:
        self.assertEqual(
            FINANCIAL_GUARANTEE.relation_names, ("GUARANTEE", "RISK_REMOVED")
        )

    def test_only_financial_guarantee_is_implemented(self) -> None:
        """The phase says not to extend to other categories."""

        self.assertEqual(FINANCIAL_GUARANTEE.category, "financial_guarantee")
        self.assertEqual(PATTERNS.categories, ("financial_guarantee",))

    def test_frame_kinds_covered_spans_the_relations(self) -> None:
        self.assertEqual(
            set(frame_kinds_covered(FINANCIAL_GUARANTEE)),
            {ACTIVE, PASSIVE, COPULAR, ATTRIBUTIVE, NOMINAL},
        )

    def test_entity_types_are_declared_as_required(self) -> None:
        self.assertEqual(
            set(FINANCIAL_GUARANTEE.required_entities),
            {"RETURN", "CAPITAL", "VALUE", "OUTCOME"},
        )


class PatternSetTests(unittest.TestCase):
    def test_the_set_names_its_version(self) -> None:
        self.assertEqual(PATTERNS.version, "1.0.0")

    def test_an_unknown_entity_type_is_rejected_at_construction(self) -> None:
        bad = IntentPattern("p", "c", ("NOPE",), (GUARANTEE,), 0.5, "why")

        with self.assertRaises(PatternError):
            PatternSet("s", ENTITIES, (bad,))

    def test_for_category_filters(self) -> None:
        self.assertEqual(len(PATTERNS.for_category("financial_guarantee")), 1)
        self.assertEqual(PATTERNS.for_category("nothing"), ())

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(PATTERNS.as_dict(), sort_keys=True)

    def test_as_dict_records_the_lexicon(self) -> None:
        payload = PATTERNS.as_dict()

        self.assertEqual(set(payload["entities"]), set(ENTITIES.names()))


if __name__ == "__main__":
    unittest.main()
