"""Skill registry: register, resolve, dependency validation, listing."""

from __future__ import annotations

import unittest
from copy import deepcopy

from creator_skill import (
    DEFAULT_SKILL_CATALOG,
    SkillDependency,
    SkillDependencyError,
    SkillRegistry,
    SkillRegistryError,
    SkillSelection,
    CreatorRequest,
    SkillBundle,
    SkillProvenance,
    VERSION_SEPARATOR,
    skill_from_document,
)
from creator_skill.catalog import catalog_asset_references
from creator_skill.model import CreatorSkill, SkillCompatibility
from creator_skill.registry import DependencyReport


def _manual_skill(skill_id: str, skill_type: str = "domain", depends=()):
    return CreatorSkill(
        skill_id=skill_id,
        skill_type=skill_type,
        version="1.0.0",
        description="synthetic skill for registry tests",
        capabilities=("cap.one", "cap.two"),
        inputs=("in",),
        outputs=("out",),
        dependencies=tuple(SkillDependency(target) for target in depends),
        compatibility=SkillCompatibility(),
        provenance=SkillProvenance(
            source_kind="manual",
            source_ref="test-fixture",
            skill_version="1.0.0",
            generated_at="1970-01-01T00:00:00Z",
        ),
    )


class RegistryConstructionTests(unittest.TestCase):
    def test_default_registry_builds_from_the_catalog(self) -> None:
        registry = SkillRegistry.default()
        self.assertEqual(len(registry), len(DEFAULT_SKILL_CATALOG))

    def test_from_documents_builds_a_registry(self) -> None:
        registry = SkillRegistry.from_documents(DEFAULT_SKILL_CATALOG)
        self.assertGreater(len(registry), 0)

    def test_empty_registry_is_empty(self) -> None:
        self.assertEqual(len(SkillRegistry()), 0)

    def test_registry_records_registered_assets(self) -> None:
        registry = SkillRegistry(registered_assets=["a", "b"])
        self.assertEqual(registry.registered_assets, ("a", "b"))

    def test_construction_without_validation_is_possible(self) -> None:
        registry = SkillRegistry.from_documents(DEFAULT_SKILL_CATALOG, validate=False)
        self.assertEqual(len(registry), len(DEFAULT_SKILL_CATALOG))


class RegisterTests(unittest.TestCase):
    def test_register_adds_a_skill(self) -> None:
        registry = SkillRegistry(validate=False) if False else SkillRegistry()
        registry.register(_manual_skill("alpha"), validate=False)
        self.assertIn("alpha", registry.ids())

    def test_register_returns_the_skill(self) -> None:
        skill = _manual_skill("alpha")
        self.assertIs(SkillRegistry().register(skill, validate=False), skill)

    def test_duplicate_registration_is_rejected(self) -> None:
        registry = SkillRegistry()
        registry.register(_manual_skill("alpha"), validate=False)
        with self.assertRaises(SkillRegistryError):
            registry.register(_manual_skill("alpha"), validate=False)

    def test_duplicate_rejection_mentions_the_existing_version(self) -> None:
        registry = SkillRegistry()
        registry.register(_manual_skill("alpha"), validate=False)
        with self.assertRaises(SkillRegistryError) as ctx:
            registry.register(_manual_skill("alpha"), validate=False)
        self.assertIn("1.0.0", str(ctx.exception))

    def test_register_rejects_a_non_skill(self) -> None:
        with self.assertRaises(SkillRegistryError):
            SkillRegistry().register("not a skill")  # type: ignore[arg-type]

    def test_register_validates_by_default(self) -> None:
        """A skill with an unknown type fails validation and is not registered."""

        broken = CreatorSkill(
            skill_id="broken-skill",
            skill_type="identity",
            version="1.0.0",
            description="d",
            capabilities=("a", "b", "c"),
            inputs=("i",),
            outputs=("o",),
            dependencies=(),
            compatibility=SkillCompatibility(),
            provenance=SkillProvenance(
                source_kind="manual",
                source_ref="x",
                skill_version="9.9.9",
                generated_at="1970-01-01T00:00:00Z",
            ),
        )
        registry = SkillRegistry()
        with self.assertRaises(Exception):
            registry.register(broken)
        self.assertNotIn("broken-skill", registry.ids())

    def test_registry_is_iterable(self) -> None:
        registry = SkillRegistry.from_documents(DEFAULT_SKILL_CATALOG, validate=False)
        self.assertTrue(all(isinstance(s, CreatorSkill) for s in registry))

    def test_ids_are_sorted(self) -> None:
        registry = SkillRegistry.from_documents(DEFAULT_SKILL_CATALOG, validate=False)
        self.assertEqual(list(registry.ids()), sorted(registry.ids()))

    def test_contains_operator(self) -> None:
        registry = SkillRegistry.from_documents(DEFAULT_SKILL_CATALOG, validate=False)
        self.assertIn("finance-persona", registry)
        self.assertNotIn("nope", registry)


class ResolveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = SkillRegistry.from_documents(DEFAULT_SKILL_CATALOG, validate=False)

    def test_resolve_by_id(self) -> None:
        self.assertEqual(self.registry.resolve("finance-persona").skill_id, "finance-persona")

    def test_resolve_by_id_and_version(self) -> None:
        skill = self.registry.resolve(f"finance-persona{VERSION_SEPARATOR}1.0.0")
        self.assertEqual(skill.version, "1.0.0")

    def test_resolve_with_explicit_version_argument(self) -> None:
        self.assertEqual(
            self.registry.resolve("finance-persona", version="1.0.0").version, "1.0.0"
        )

    def test_resolve_with_wrong_version_is_rejected(self) -> None:
        with self.assertRaises(SkillRegistryError):
            self.registry.resolve("finance-persona", version="9.9.9")

    def test_resolve_unknown_id_lists_known_ids(self) -> None:
        with self.assertRaises(SkillRegistryError) as ctx:
            self.registry.resolve("ghost")
        self.assertIn("finance-persona", str(ctx.exception))

    def test_empty_reference_is_rejected(self) -> None:
        with self.assertRaises(SkillRegistryError):
            self.registry.resolve("   ")

    def test_malformed_versioned_reference_is_rejected(self) -> None:
        with self.assertRaises(SkillRegistryError):
            self.registry.resolve("finance-persona@")

    def test_has_returns_true_for_a_known_skill(self) -> None:
        self.assertTrue(self.registry.has("finance-persona"))

    def test_has_returns_false_for_an_unknown_skill(self) -> None:
        self.assertFalse(self.registry.has("ghost"))

    def test_has_accepts_a_versioned_reference(self) -> None:
        self.assertTrue(self.registry.has("finance-persona@1.0.0"))
        self.assertFalse(self.registry.has("finance-persona@9.9.9"))

    def test_skills_are_immutable_once_registered(self) -> None:
        skill = self.registry.resolve("finance-persona")
        with self.assertRaises(Exception):
            skill.version = "2.0.0"  # type: ignore[misc]


class UnregisterTests(unittest.TestCase):
    def test_unregister_removes_an_unrequired_skill(self) -> None:
        registry = SkillRegistry()
        registry.register(_manual_skill("lonely"), validate=False)
        registry.unregister("lonely")
        self.assertNotIn("lonely", registry.ids())

    def test_unregister_returns_the_skill(self) -> None:
        registry = SkillRegistry()
        registry.register(_manual_skill("lonely"), validate=False)
        self.assertEqual(registry.unregister("lonely").skill_id, "lonely")

    def test_unregister_refuses_when_required(self) -> None:
        registry = SkillRegistry()
        registry.register(_manual_skill("base"), validate=False)
        registry.register(_manual_skill("dependent", depends=["base"]), validate=False)
        with self.assertRaises(SkillRegistryError) as ctx:
            registry.unregister("base")
        self.assertIn("dependent", str(ctx.exception))

    def test_unregister_unknown_skill_is_rejected(self) -> None:
        with self.assertRaises(SkillRegistryError):
            SkillRegistry().unregister("ghost")


class DependencyValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = SkillRegistry.from_documents(DEFAULT_SKILL_CATALOG, validate=False)

    def test_catalog_dependencies_all_resolve(self) -> None:
        self.registry.assert_no_missing_dependencies()

    def test_validate_dependency_returns_a_report(self) -> None:
        report = self.registry.validate_dependency("text-distillation")
        self.assertIsInstance(report, DependencyReport)

    def test_resolvable_skill_passes(self) -> None:
        self.assertTrue(self.registry.validate_dependency("text-distillation").passed)

    def test_visual_style_dependency_resolves(self) -> None:
        report = self.registry.validate_dependency("visual-style-distillation")
        self.assertTrue(report.passed)
        self.assertIn("text-distillation", report.satisfied)

    def test_missing_dependency_is_recorded(self) -> None:
        registry = SkillRegistry()
        registry.register(_manual_skill("needy", depends=["absent"]), validate=False)
        report = registry.validate_dependency("needy")
        self.assertFalse(report.passed)
        self.assertEqual(report.missing, ("absent",))

    def test_assert_dependencies_resolvable_raises_on_missing(self) -> None:
        registry = SkillRegistry()
        registry.register(_manual_skill("needy", depends=["absent"]), validate=False)
        with self.assertRaises(SkillDependencyError) as ctx:
            registry.assert_dependencies_resolvable("needy")
        self.assertIn("absent", str(ctx.exception))

    def test_missing_dependency_is_not_a_registry_failure_at_registration(self) -> None:
        """A skill may be registered before its dependency exists."""

        registry = SkillRegistry()
        registry.register(_manual_skill("needy", depends=["absent"]), validate=False)
        self.assertIn("needy", registry.ids())

    def test_assert_no_missing_dependencies_reports_all_offenders(self) -> None:
        registry = SkillRegistry()
        registry.register(_manual_skill("a", depends=["x"]), validate=False)
        registry.register(_manual_skill("b", depends=["y"]), validate=False)
        with self.assertRaises(SkillDependencyError) as ctx:
            registry.assert_no_missing_dependencies()
        message = str(ctx.exception)
        self.assertIn("a", message)
        self.assertIn("b", message)

    def test_conflict_edge_is_reported_when_present(self) -> None:
        registry = SkillRegistry()
        registry.register(_manual_skill("other"), validate=False)
        registry.register(
            _manual_skill("fighter", depends=[]), validate=False
        )
        conflict = CreatorSkill(
            skill_id="conflicter",
            skill_type="review",
            version="1.0.0",
            description="d",
            capabilities=("a", "b"),
            inputs=("i",),
            outputs=("o",),
            dependencies=(SkillDependency("other", "conflict"),),
            compatibility=SkillCompatibility(),
            provenance=SkillProvenance(
                source_kind="manual",
                source_ref="x",
                skill_version="1.0.0",
                generated_at="1970-01-01T00:00:00Z",
            ),
        )
        registry.register(conflict, validate=False)
        report = registry.validate_dependency("conflicter")
        self.assertEqual(report.conflicts, ("other",))
        self.assertFalse(report.passed)

    def test_enhance_edges_are_not_required_to_resolve(self) -> None:
        registry = SkillRegistry()
        registry.register(
            CreatorSkill(
                skill_id="enhancer",
                skill_type="domain",
                version="1.0.0",
                description="d",
                capabilities=("a", "b"),
                inputs=("i",),
                outputs=("o",),
                dependencies=(SkillDependency("absent", "enhance"),),
                compatibility=SkillCompatibility(),
                provenance=SkillProvenance(
                    source_kind="manual",
                    source_ref="x",
                    skill_version="1.0.0",
                    generated_at="1970-01-01T00:00:00Z",
                ),
            ),
            validate=False,
        )
        report = registry.validate_dependency("enhancer")
        self.assertEqual(report.missing, ())
        self.assertTrue(report.passed)

    def test_report_as_dict_shape(self) -> None:
        record = self.registry.validate_dependency("text-distillation").as_dict()
        for key in ("skill_id", "satisfied", "missing", "conflicts", "passed"):
            self.assertIn(key, record)


class GraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = SkillRegistry.from_documents(DEFAULT_SKILL_CATALOG, validate=False)

    def test_topological_order_includes_every_skill(self) -> None:
        self.assertEqual(set(self.registry.topological_order()), set(self.registry.ids()))

    def test_dependencies_precede_dependents(self) -> None:
        order = list(self.registry.topological_order())
        for skill in self.registry:
            for dependency in skill.requires():
                with self.subTest(skill=skill.skill_id, dependency=dependency):
                    self.assertLess(order.index(dependency), order.index(skill.skill_id))

    def test_catalog_graph_is_acyclic(self) -> None:
        self.assertEqual(self.registry.detect_cycles(), ())

    def test_a_cycle_is_detected(self) -> None:
        registry = SkillRegistry()
        registry.register(_manual_skill("a", depends=["b"]), validate=False)
        registry.register(_manual_skill("b", depends=["a"]), validate=False)
        with self.assertRaises(SkillDependencyError):
            registry.topological_order()

    def test_cycle_detection_reports_the_ids(self) -> None:
        registry = SkillRegistry()
        registry.register(_manual_skill("a", depends=["b"]), validate=False)
        registry.register(_manual_skill("b", depends=["a"]), validate=False)
        self.assertEqual(registry.detect_cycles(), ("a", "b"))


class ListingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = SkillRegistry.from_documents(DEFAULT_SKILL_CATALOG, validate=False)

    def test_list_available_excludes_declared_skills(self) -> None:
        available = self.registry.list_available()
        self.assertTrue(all(skill.available for skill in available))

    def test_list_all_includes_declared_skills(self) -> None:
        self.assertGreater(len(self.registry.list_all()), len(self.registry.list_available()))

    def test_list_all_is_ordered_by_taxonomy(self) -> None:
        from creator_skill import SKILL_TYPE_ORDER

        order = {name: index for index, name in enumerate(SKILL_TYPE_ORDER)}
        types = [skill.skill_type for skill in self.registry.list_all()]
        self.assertEqual(types, sorted(types, key=lambda t: order[t]))

    def test_list_available_by_type(self) -> None:
        reviews = self.registry.list_available(skill_type="review")
        self.assertTrue(reviews)
        self.assertTrue(all(s.skill_type == "review" for s in reviews))

    def test_list_available_with_unknown_type_is_rejected(self) -> None:
        with self.assertRaises(SkillRegistryError):
            self.registry.list_available(skill_type="nope")

    def test_require_reusable_filters(self) -> None:
        result = self.registry.list_available(require_reusable=True)
        self.assertTrue(all(skill.reusable for skill in result))

    def test_by_type_returns_matching_skills(self) -> None:
        domains = self.registry.by_type("domain")
        self.assertTrue(domains)
        self.assertTrue(all(skill.skill_type == "domain" for skill in domains))

    def test_by_type_with_unknown_type_is_rejected(self) -> None:
        with self.assertRaises(SkillRegistryError):
            self.registry.by_type("nope")

    def test_by_type_returns_empty_for_an_unused_type(self) -> None:
        self.assertEqual(self.registry.by_type("publishing")[:0], ())
        self.assertTrue(all(s.skill_type == "publishing" for s in self.registry.by_type("publishing")))

    def test_available_assets_accessor(self) -> None:
        registry = SkillRegistry(registered_assets=catalog_asset_references())
        self.assertEqual(len(registry.available_assets()), len(catalog_asset_references()))

    def test_registry_as_dict_is_serialisable(self) -> None:
        import json

        json.dumps(self.registry.as_dict())


if __name__ == "__main__":
    unittest.main()
