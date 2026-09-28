"""Taxonomy and model: the seven skill types and the immutable value objects."""

from __future__ import annotations

import unittest

from creator_skill import (
    DEPENDENCY_KINDS,
    PROVENANCE_SOURCES,
    REQUIRED_SKILL_TYPES,
    SKILL_STATUSES,
    SKILL_TYPES,
    SKILL_TYPE_NAMES,
    SKILL_TYPE_ORDER,
    CreatorRequest,
    CreatorSkill,
    SkillBundle,
    SkillCompatibility,
    SkillDependency,
    SkillError,
    SkillProvenance,
    SkillSelection,
    composition_order,
    is_known_skill_type,
    prior_types,
    skill_type,
    taxonomy_document,
)
from creator_skill.catalog import DEFAULT_SKILL_CATALOG
from creator_skill.registry import skill_from_document


def _skill(**overrides):
    base = {
        "skill_id": "test-skill",
        "skill_type": "domain",
        "version": "1.0.0",
        "description": "a test skill",
        "capabilities": ("domain.a", "domain.b"),
        "inputs": ("in",),
        "outputs": ("out",),
        "dependencies": (),
        "compatibility": SkillCompatibility(),
        "provenance": SkillProvenance(
            source_kind="manual",
            source_ref="test",
            skill_version="1.0.0",
            generated_at="1970-01-01T00:00:00Z",
        ),
    }
    base.update(overrides)
    return CreatorSkill(**base)


class TaxonomyTests(unittest.TestCase):
    def test_seven_skill_types_are_declared(self) -> None:
        self.assertEqual(len(SKILL_TYPE_ORDER), 7)

    def test_expected_type_names(self) -> None:
        self.assertEqual(
            list(SKILL_TYPE_ORDER),
            [
                "identity",
                "domain",
                "source",
                "distillation",
                "generation",
                "review",
                "publishing",
            ],
        )

    def test_every_type_has_a_qualified_name(self) -> None:
        for name in SKILL_TYPE_ORDER:
            self.assertEqual(SKILL_TYPE_NAMES[name], f"{name}_skill")

    def test_every_type_is_defined(self) -> None:
        for name in SKILL_TYPE_ORDER:
            self.assertIn(name, SKILL_TYPES)

    def test_lookup_returns_the_entry(self) -> None:
        self.assertEqual(skill_type("identity").skill_type, "identity")

    def test_unknown_type_is_rejected(self) -> None:
        with self.assertRaises(SkillError):
            skill_type("unknown")

    def test_is_known_skill_type(self) -> None:
        self.assertTrue(is_known_skill_type("review"))
        self.assertFalse(is_known_skill_type("review2"))

    def test_every_type_declares_a_responsibility_and_question(self) -> None:
        for name in SKILL_TYPE_ORDER:
            entry = SKILL_TYPES[name]
            self.assertTrue(entry.responsibility)
            self.assertTrue(entry.question)
            self.assertTrue(entry.description)

    def test_composition_order_matches_taxonomy_order(self) -> None:
        self.assertEqual(composition_order(), SKILL_TYPE_ORDER)

    def test_require_prior_edges_reference_earlier_types(self) -> None:
        position = {name: index for index, name in enumerate(SKILL_TYPE_ORDER)}
        for name in SKILL_TYPE_ORDER:
            for prior in prior_types(name):
                with self.subTest(skill_type=name, prior=prior):
                    self.assertLess(position[prior], position[name])

    def test_identity_is_the_root_type(self) -> None:
        self.assertEqual(prior_types("identity"), ())

    def test_every_type_is_required_for_a_creator_bundle(self) -> None:
        self.assertEqual(set(REQUIRED_SKILL_TYPES), set(SKILL_TYPE_ORDER))

    def test_taxonomy_document_is_serialisable(self) -> None:
        import json

        json.dumps(taxonomy_document())

    def test_taxonomy_document_lists_all_types(self) -> None:
        document = taxonomy_document()
        self.assertEqual(len(document["skill_types"]), 7)


class SkillDependencyTests(unittest.TestCase):
    def test_require_edge(self) -> None:
        self.assertEqual(SkillDependency("x", "require").kind, "require")

    def test_every_declared_kind_is_accepted(self) -> None:
        for kind in DEPENDENCY_KINDS:
            with self.subTest(kind=kind):
                self.assertEqual(SkillDependency("x", kind).kind, kind)

    def test_unknown_kind_is_rejected(self) -> None:
        with self.assertRaises(SkillError):
            SkillDependency("x", "maybe")

    def test_empty_target_is_rejected(self) -> None:
        with self.assertRaises(SkillError):
            SkillDependency("   ")

    def test_as_dict_includes_reason_when_present(self) -> None:
        record = SkillDependency("x", "require", "because").as_dict()
        self.assertEqual(record["reason"], "because")


class SkillProvenanceTests(unittest.TestCase):
    def _provenance(self, **overrides):
        base = {
            "source_kind": "manual",
            "source_ref": "authored",
            "skill_version": "1.0.0",
            "generated_at": "1970-01-01T00:00:00Z",
        }
        base.update(overrides)
        return SkillProvenance(**base)

    def test_valid_provenance(self) -> None:
        self.assertEqual(self._provenance().source_kind, "manual")

    def test_every_declared_source_kind_is_accepted(self) -> None:
        for kind in PROVENANCE_SOURCES:
            with self.subTest(kind=kind):
                self.assertEqual(self._provenance(source_kind=kind).source_kind, kind)

    def test_unknown_source_kind_is_rejected(self) -> None:
        with self.assertRaises(SkillError):
            self._provenance(source_kind="guess")

    def test_empty_source_ref_is_rejected(self) -> None:
        with self.assertRaises(SkillError):
            self._provenance(source_ref="  ")

    def test_empty_version_is_rejected(self) -> None:
        with self.assertRaises(SkillError):
            self._provenance(skill_version="")

    def test_empty_timestamp_is_rejected(self) -> None:
        with self.assertRaises(SkillError):
            self._provenance(generated_at="")

    def test_confidence_out_of_range_is_rejected(self) -> None:
        with self.assertRaises(SkillError):
            self._provenance(confidence=1.5)

    def test_boolean_confidence_is_rejected(self) -> None:
        with self.assertRaises(SkillError):
            self._provenance(confidence=True)

    def test_as_dict_shape(self) -> None:
        record = self._provenance().as_dict()
        for key in ("source_kind", "source_ref", "skill_version", "generated_at", "confidence"):
            self.assertIn(key, record)


class SkillCompatibilityTests(unittest.TestCase):
    def test_empty_declaration_is_a_wildcard(self) -> None:
        compatibility = SkillCompatibility()
        self.assertTrue(compatibility.matches_domain("anything"))
        self.assertTrue(compatibility.matches_platform("anything"))
        self.assertTrue(compatibility.matches_style("anything"))

    def test_declared_domain_must_contain_the_value(self) -> None:
        compatibility = SkillCompatibility(domains=("finance",))
        self.assertTrue(compatibility.matches_domain("finance"))
        self.assertFalse(compatibility.matches_domain("sports"))

    def test_declared_platform_must_contain_the_value(self) -> None:
        compatibility = SkillCompatibility(platforms=("xiaohongshu",))
        self.assertTrue(compatibility.matches_platform("xiaohongshu"))
        self.assertFalse(compatibility.matches_platform("bilibili"))

    def test_declared_style_must_contain_the_value(self) -> None:
        compatibility = SkillCompatibility(styles=("education",))
        self.assertTrue(compatibility.matches_style("education"))
        self.assertFalse(compatibility.matches_style("comedy"))

    def test_values_are_deduplicated(self) -> None:
        compatibility = SkillCompatibility(domains=("finance", "finance"))
        self.assertEqual(compatibility.domains, ("finance",))

    def test_as_dict_lists_every_dimension(self) -> None:
        record = SkillCompatibility().as_dict()
        self.assertEqual(
            sorted(record),
            ["domains", "platforms", "requires_contract_version", "styles"],
        )


class CreatorSkillTests(unittest.TestCase):
    def test_minimal_skill_is_accepted(self) -> None:
        self.assertEqual(_skill().skill_id, "test-skill")

    def test_capabilities_are_deduplicated(self) -> None:
        skill = _skill(capabilities=("a", "a", "b"))
        self.assertEqual(skill.capabilities, ("a", "b"))

    def test_empty_capabilities_are_rejected(self) -> None:
        with self.assertRaises(SkillError):
            _skill(capabilities=())

    def test_unknown_status_is_rejected(self) -> None:
        with self.assertRaises(SkillError):
            _skill(status="half")

    def test_unavailable_status_requires_a_reason(self) -> None:
        with self.assertRaises(SkillError):
            _skill(status="declared")

    def test_unavailable_status_with_a_reason_is_accepted(self) -> None:
        skill = _skill(status="declared", reason="not built yet")
        self.assertFalse(skill.available)

    def test_every_declared_status_is_accepted(self) -> None:
        for status in SKILL_STATUSES:
            with self.subTest(status=status):
                reason = "" if status == "available" else "why not"
                self.assertEqual(_skill(status=status, reason=reason).status, status)

    def test_requires_and_enhances_and_conflicts_are_separated(self) -> None:
        skill = _skill(
            dependencies=(
                SkillDependency("a", "require"),
                SkillDependency("b", "enhance"),
                SkillDependency("c", "conflict"),
            )
        )
        self.assertEqual(skill.requires(), ("a",))
        self.assertEqual(skill.enhances(), ("b",))
        self.assertEqual(skill.conflicts_with(), ("c",))

    def test_self_dependency_is_rejected_by_validation(self) -> None:
        from creator_skill import validate_semantics

        with self.assertRaises(SkillError):
            validate_semantics(_skill(dependencies=(SkillDependency("test-skill"),)))

    def test_empty_skill_id_is_rejected(self) -> None:
        with self.assertRaises(SkillError):
            _skill(skill_id=" ")

    def test_empty_description_is_rejected(self) -> None:
        with self.assertRaises(SkillError):
            _skill(description="")

    def test_as_dict_is_serialisable(self) -> None:
        import json

        json.dumps(_skill().as_dict())

    def test_as_dict_carries_every_contract_field(self) -> None:
        record = _skill().as_dict()
        for key in (
            "skill_id",
            "skill_type",
            "version",
            "description",
            "capabilities",
            "inputs",
            "outputs",
            "dependencies",
            "compatibility",
            "provenance",
            "status",
        ):
            self.assertIn(key, record)


class CreatorRequestTests(unittest.TestCase):
    def test_minimal_request(self) -> None:
        self.assertEqual(CreatorRequest(domain="finance", platform="xiaohongshu").style, "education")

    def test_request_is_unavailable_tolerant_by_default(self) -> None:
        self.assertTrue(CreatorRequest(domain="finance", platform="web").allow_unavailable)

    def test_empty_domain_is_rejected(self) -> None:
        with self.assertRaises(SkillError):
            CreatorRequest(domain="", platform="web")

    def test_empty_platform_is_rejected(self) -> None:
        with self.assertRaises(SkillError):
            CreatorRequest(domain="finance", platform=" ")

    def test_declared_capabilities_are_deduplicated(self) -> None:
        request = CreatorRequest(
            domain="finance", platform="web", declared_capabilities=("a", "a")
        )
        self.assertEqual(request.declared_capabilities, ("a",))

    def test_as_dict_is_serialisable(self) -> None:
        import json

        json.dumps(CreatorRequest(domain="finance", platform="web").as_dict())


class SkillBundleTests(unittest.TestCase):
    def _selection(self, skill_type: str, skill_id: str) -> SkillSelection:
        return SkillSelection(
            skill_type=skill_type, skill_id=skill_id, version="1.0.0", reason="because"
        )

    def _bundle(self, selections, extras=()):
        return SkillBundle(
            bundle_id="bundle-test",
            request=CreatorRequest(domain="finance", platform="web"),
            selections=tuple(selections),
            extras=tuple(extras),
            provenance=SkillProvenance(
                source_kind="projection",
                source_ref="bundle-test",
                skill_version="1.0.0",
                generated_at="1970-01-01T00:00:00Z",
            ),
        )

    def test_bundle_accepts_one_skill_per_type(self) -> None:
        bundle = self._bundle([self._selection("identity", "a"), self._selection("domain", "b")])
        self.assertEqual(len(bundle.selections), 2)

    def test_duplicate_type_is_rejected(self) -> None:
        with self.assertRaises(SkillError):
            self._bundle([self._selection("identity", "a"), self._selection("identity", "b")])

    def test_extras_may_repeat_a_type(self) -> None:
        bundle = self._bundle(
            [self._selection("distillation", "a")],
            extras=[self._selection("distillation", "b")],
        )
        self.assertEqual(len(bundle.extras), 1)

    def test_a_skill_cannot_be_both_selection_and_extra(self) -> None:
        with self.assertRaises(SkillError):
            self._bundle(
                [self._selection("distillation", "a")],
                extras=[self._selection("distillation", "a")],
            )

    def test_skill_ids_include_extras(self) -> None:
        bundle = self._bundle(
            [self._selection("distillation", "a")],
            extras=[self._selection("distillation", "b")],
        )
        self.assertEqual(bundle.skill_ids(), ("a", "b"))

    def test_by_type_returns_the_selection(self) -> None:
        bundle = self._bundle([self._selection("identity", "a")])
        self.assertIsNotNone(bundle.by_type("identity"))
        self.assertIsNone(bundle.by_type("domain"))

    def test_empty_bundle_id_is_rejected(self) -> None:
        with self.assertRaises(SkillError):
            SkillBundle(
                bundle_id="",
                request=CreatorRequest(domain="finance", platform="web"),
                selections=(),
                provenance=SkillProvenance(
                    source_kind="manual",
                    source_ref="x",
                    skill_version="1.0.0",
                    generated_at="1970-01-01T00:00:00Z",
                ),
            )

    def test_as_dict_is_serialisable(self) -> None:
        import json

        json.dumps(self._bundle([self._selection("identity", "a")]).as_dict())


class CatalogShapeTests(unittest.TestCase):
    def test_catalog_declares_skills(self) -> None:
        self.assertGreaterEqual(len(DEFAULT_SKILL_CATALOG), 7)

    def test_every_catalog_entry_builds(self) -> None:
        for entry in DEFAULT_SKILL_CATALOG:
            with self.subTest(skill=entry["skill_id"]):
                self.assertIsInstance(skill_from_document(entry), CreatorSkill)

    def test_catalog_covers_identity_domain_review(self) -> None:
        types = {entry["skill_type"] for entry in DEFAULT_SKILL_CATALOG}
        for required in ("identity", "domain", "review"):
            self.assertIn(required, types)

    def test_catalog_skill_ids_are_unique(self) -> None:
        ids = [entry["skill_id"] for entry in DEFAULT_SKILL_CATALOG]
        self.assertEqual(len(ids), len(set(ids)))

    def test_catalog_versions_are_semver(self) -> None:
        for entry in DEFAULT_SKILL_CATALOG:
            with self.subTest(skill=entry["skill_id"]):
                self.assertRegex(entry["version"], r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
