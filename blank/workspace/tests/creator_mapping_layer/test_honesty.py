"""Capability honesty: an absent capability is declared, never enabled."""

from __future__ import annotations

import unittest
from copy import deepcopy
from pathlib import Path

from creator_mapping import (
    CAPABILITY_MODULES,
    BundleAssetResolver,
    BundleInstanceMapper,
    MappingHonestyError,
    bundle_instance_diff,
    map_bundle_to_instance,
    validate_mapping,
    validate_mapping_result,
)
from creator_skill import (
    CreatorRequest,
    DEFAULT_SKILL_CATALOG,
    SkillComposer,
    SkillRegistry,
)

WORKSPACE = Path(__file__).resolve().parents[2]


def _setup(*, with_visual: bool = True):
    registry = SkillRegistry.from_documents(DEFAULT_SKILL_CATALOG, validate=False)
    from creator_projection import AssetRegistry

    resolver = BundleAssetResolver(AssetRegistry.load(WORKSPACE), registry)
    bundle = SkillComposer(registry).compose(
        CreatorRequest(
            domain="finance",
            platform="xiaohongshu",
            creator_id="finance_xhs",
            declared_capabilities=("visual-style-distillation",) if with_visual else (),
        )
    ).bundle
    return registry, resolver, bundle


def _mapped(**kwargs):
    _registry, resolver, bundle = _setup(**kwargs)
    return resolver, bundle, map_bundle_to_instance(bundle, resolver=resolver)


def _mapped_instance(**kwargs):
    """Return just the mapped instance, for tests that need nothing else."""

    return _mapped(**kwargs)[2]


def _rebuild(mapped, instance):
    from creator_mapping.mapper import MappedInstance

    return MappedInstance(
        instance=instance,
        bundle_id=mapped.bundle_id,
        creator_id=mapped.creator_id,
        modules=mapped.modules,
        mapping_provenance=mapped.mapping_provenance,
        assets=mapped.assets,
        notes=mapped.notes,
        timestamp=mapped.timestamp,
    )


class BaselineHonestyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.resolver, cls.bundle, cls.mapped = _mapped()

    def test_generation_is_disabled(self) -> None:
        self.assertIs(self.mapped.instance["generation"]["enabled"], False)

    def test_publishing_is_disabled(self) -> None:
        self.assertIs(self.mapped.instance["publishing"]["enabled"], False)

    def test_both_carry_a_reason(self) -> None:
        for module in CAPABILITY_MODULES:
            with self.subTest(module=module):
                self.assertTrue(self.mapped.instance[module]["reason"])

    def test_availability_records_no_source_for_both(self) -> None:
        for module in CAPABILITY_MODULES:
            with self.subTest(module=module):
                self.assertIs(
                    self.mapped.module_availability[module]["has_available_source"],
                    False,
                )

    def test_availability_records_enabled_by_mapping(self) -> None:
        for module in CAPABILITY_MODULES:
            with self.subTest(module=module):
                self.assertIs(
                    self.mapped.module_availability[module]["enabled_by_mapping"],
                    False,
                )

    def test_valid_mapping_passes_the_honesty_check(self) -> None:
        validate_mapping(self.mapped)

    def test_diff_reports_no_capability_change(self) -> None:
        diff = bundle_instance_diff(self.bundle, self.mapped)
        self.assertEqual(diff["capability_changes"], [])


class FalseEnableRejectionTests(unittest.TestCase):
    """The load-bearing negative: enabling an absent capability must be rejected."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.resolver, cls.bundle, cls.mapped = _mapped()

    def _tamper(self, module: str, **changes):
        instance = deepcopy(self.mapped.instance)
        instance[module].update(changes)
        return _rebuild(self.mapped, instance)

    def test_enabling_generation_is_rejected(self) -> None:
        tampered = self._tamper("generation", enabled=True, reason="")
        with self.assertRaises(MappingHonestyError):
            validate_mapping(tampered)

    def test_enabling_publishing_is_rejected(self) -> None:
        tampered = self._tamper("publishing", enabled=True, reason="")
        with self.assertRaises(MappingHonestyError):
            validate_mapping(tampered)

    def test_enabling_generation_also_fails_full_validation(self) -> None:
        tampered = self._tamper("generation", enabled=True, reason="")
        with self.assertRaises(Exception):
            validate_mapping_result(tampered)

    def test_enabling_while_keeping_a_reason_is_still_rejected_by_the_contract(self) -> None:
        tampered = self._tamper("generation", enabled=True)
        with self.assertRaises(Exception):
            validate_mapping_result(tampered)

    def test_disabling_without_a_reason_is_rejected(self) -> None:
        tampered = self._tamper("publishing", reason="")
        with self.assertRaises(Exception):
            validate_mapping_result(tampered)

    def test_a_missing_module_is_rejected(self) -> None:
        instance = deepcopy(self.mapped.instance)
        del instance["generation"]
        tampered = _rebuild(self.mapped, instance)
        with self.assertRaises(Exception):
            validate_mapping(tampered)

    def test_an_unjustified_enable_is_caught_by_the_diff(self) -> None:
        """The diff is the audit trail for a capability that changed in transit."""

        tampered = self._tamper("generation", enabled=True, reason="")
        diff = bundle_instance_diff(self.bundle, tampered)
        self.assertFalse(diff["consistent"])
        self.assertTrue(diff["capability_changes"])


class AbsenceDeclarationTests(unittest.TestCase):
    """A declared absence must be marked, and must state why."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.resolver, cls.bundle, cls.mapped = _mapped()

    def test_scalar_absences_are_marked(self) -> None:
        self.assertTrue(
            self.mapped.instance["identity"]["audience"].startswith("not_available:")
        )

    def test_sealed_object_absences_carry_a_marker_inside(self) -> None:
        rules = self.mapped.instance["source"]["collection_rules"]
        self.assertTrue(str(rules["dedupe_by"]).startswith("not_available:"))

    def test_sealed_array_absences_carry_a_marker_inside(self) -> None:
        entry = self.mapped.instance["source"]["reference_creators"][0]
        self.assertTrue(
            str(entry["verification_method"]).startswith("not_available:")
        )

    def test_a_marked_scalar_without_a_reason_is_rejected(self) -> None:
        instance = deepcopy(self.mapped.instance)
        instance["identity"]["audience"] = "not_available:"
        tampered = _rebuild(self.mapped, instance)
        with self.assertRaises(MappingHonestyError):
            validate_mapping(tampered)

    def test_an_unmarked_scalar_for_an_absent_field_is_rejected(self) -> None:
        instance = deepcopy(self.mapped.instance)
        instance["identity"]["audience"] = "everyone"
        tampered = _rebuild(self.mapped, instance)
        with self.assertRaises(MappingHonestyError):
            validate_mapping(tampered)

    def test_an_unmarked_sealed_shape_is_rejected(self) -> None:
        instance = deepcopy(self.mapped.instance)
        instance["source"]["collection_rules"] = {
            "min_notes": 100,
            "material_tiers": ["S"],
            "rate_limit_seconds": 3,
            "dedupe_by": "note_id",
        }
        tampered = _rebuild(self.mapped, instance)
        with self.assertRaises(MappingHonestyError):
            validate_mapping(tampered)

    def test_partial_bundle_absence_is_marked(self) -> None:
        registry = SkillRegistry.from_documents(DEFAULT_SKILL_CATALOG, validate=False)
        from creator_projection import AssetRegistry

        resolver = BundleAssetResolver(AssetRegistry.load(WORKSPACE), registry)
        bundle = SkillComposer(registry).compose(
            CreatorRequest(domain="sports", platform="xiaohongshu", creator_id="sports_xhs")
        ).bundle
        mapped = map_bundle_to_instance(bundle, resolver=resolver)
        self.assertTrue(
            str(mapped.instance["visual_rules"]["profile_id"]).startswith(
                "not_available:"
            )
        )
        self.assertTrue(validate_mapping_result(mapped).passed)


class NoAutoFillTests(unittest.TestCase):
    """Nothing may be auto-filled where no capability exists."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.resolver, cls.bundle, cls.mapped = _mapped()

    def test_generation_reason_is_not_a_placeholder(self) -> None:
        self.assertNotIn("todo", self.mapped.instance["generation"]["reason"].lower())
        self.assertNotIn("tbd", self.mapped.instance["generation"]["reason"].lower())

    def test_publishing_reason_is_not_a_placeholder(self) -> None:
        self.assertNotIn("todo", self.mapped.instance["publishing"]["reason"].lower())

    def test_generation_input_is_a_contract_value_not_invented(self) -> None:
        from creator_mapping import GENERATION_INPUTS

        self.assertEqual(self.mapped.instance["generation"]["input"], list(GENERATION_INPUTS))

    def test_no_capability_is_enabled(self) -> None:
        for module in CAPABILITY_MODULES:
            with self.subTest(module=module):
                self.assertIsNot(self.mapped.instance[module]["enabled"], True)

    def test_risk_policy_is_enabled_and_justified(self) -> None:
        """A capability with a real asset IS enabled, and says so."""

        self.assertIs(self.mapped.instance["risk_policy"]["enabled"], True)
        self.assertIs(
            self.mapped.module_availability["risk_policy"]["has_available_source"],
            True,
        )


if __name__ == "__main__":
    unittest.main()
