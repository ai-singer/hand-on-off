"""Mapping a bundle to an instance: complete, partial, and unavailable skills."""

from __future__ import annotations

import unittest
from pathlib import Path

from creator_mapping import (
    BundleAssetResolver,
    BundleInstanceMapper,
    MappedInstance,
    MappingAssetError,
    MappingRuleError,
    bundle_instance_diff,
    map_bundle_to_instance,
    write_mapped_instance,
)
from creator_skill import (
    CreatorRequest,
    DEFAULT_SKILL_CATALOG,
    SkillComposer,
    SkillRegistry,
)

WORKSPACE = Path(__file__).resolve().parents[2]


def _registry() -> SkillRegistry:
    return SkillRegistry.from_documents(DEFAULT_SKILL_CATALOG, validate=False)


def _resolver(registry: SkillRegistry | None = None) -> BundleAssetResolver:
    from creator_projection import AssetRegistry

    # Explicit None check, not `registry or ...`: SkillRegistry defines __len__, so
    # an *empty* registry is falsy and an `or` fallback would silently substitute a
    # populated one - which is exactly the case a test needs to exercise.
    active = _registry() if registry is None else registry
    return BundleAssetResolver(AssetRegistry.load(WORKSPACE), active)


def _finance_bundle(*, with_visual: bool = True, creator_id: str = "finance_xhs"):
    registry = _registry()
    request = CreatorRequest(
        domain="finance",
        platform="xiaohongshu",
        style="education",
        creator_id=creator_id,
        declared_capabilities=("visual-style-distillation",) if with_visual else (),
    )
    return SkillComposer(registry).compose(request).bundle


class CompleteBundleTests(unittest.TestCase):
    """A complete finance bundle maps end to end."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = _finance_bundle()
        cls.mapped = map_bundle_to_instance(cls.bundle, resolver=_resolver())

    def test_mapping_returns_a_mapped_instance(self) -> None:
        self.assertIsInstance(self.mapped, MappedInstance)

    def test_creator_id_comes_from_the_request(self) -> None:
        self.assertEqual(self.mapped.creator_id, "finance_xhs")

    def test_all_seven_modules_are_mapped(self) -> None:
        self.assertEqual(
            [m.module for m in self.mapped.modules],
            ["identity", "source", "text_rules", "visual_rules", "risk_policy",
             "generation", "publishing"],
        )

    def test_instance_declares_the_contract_version(self) -> None:
        self.assertEqual(self.mapped.instance["contract_version"], "1.0.0")

    def test_instance_has_all_eight_modules(self) -> None:
        for module in ("identity", "source", "text_rules", "visual_rules",
                       "risk_policy", "generation", "publishing", "provenance"):
            self.assertIn(module, self.mapped.instance)

    def test_bundle_id_is_recorded(self) -> None:
        self.assertEqual(self.mapped.bundle_id, self.bundle.bundle_id)

    def test_diff_reports_consistency(self) -> None:
        self.assertTrue(bundle_instance_diff(self.bundle, self.mapped)["consistent"])

    def test_mapping_is_deterministic(self) -> None:
        again = map_bundle_to_instance(self.bundle, resolver=_resolver())
        self.assertEqual(self.mapped.instance, again.instance)

    def test_mapping_report_is_serialisable(self) -> None:
        import json

        json.dumps(self.mapped.as_report())

    def test_creator_id_is_derived_from_the_bundle_when_unset(self) -> None:
        bundle = _finance_bundle(creator_id="")
        mapped = map_bundle_to_instance(bundle, resolver=_resolver())
        self.assertTrue(mapped.creator_id.startswith("creator-"))

    def test_explicit_creator_id_is_honoured(self) -> None:
        bundle = _finance_bundle(creator_id="my_creator")
        mapped = map_bundle_to_instance(bundle, resolver=_resolver())
        self.assertEqual(mapped.creator_id, "my_creator")


class PartialBundleTests(unittest.TestCase):
    """A bundle with declared gaps still maps, and reports the gaps."""

    @classmethod
    def setUpClass(cls) -> None:
        registry = _registry()
        cls.bundle = SkillComposer(registry).compose(
            CreatorRequest(domain="sports", platform="xiaohongshu", creator_id="sports_xhs")
        ).bundle
        cls.mapped = map_bundle_to_instance(cls.bundle, resolver=_resolver(registry))

    def test_partial_bundle_maps(self) -> None:
        self.assertTrue(self.mapped.modules)

    def test_identity_is_declared_absent_when_no_identity_skill_exists(self) -> None:
        identity = self.mapped.instance["identity"]
        self.assertTrue(
            str(identity["audience"]).startswith("not_available:")
        )

    def test_partial_bundle_diff_is_consistent(self) -> None:
        self.assertTrue(bundle_instance_diff(self.bundle, self.mapped)["consistent"])

    def test_mapping_notes_record_the_gap(self) -> None:
        self.assertTrue(any("no available asset" in note for note in self.mapped.notes))

    def test_generation_availability_has_no_available_source_on_a_partial_bundle(self) -> None:
        """Sports selects no generation skill, so no available asset backs it."""

        availability = self.mapped.module_availability["generation"]
        self.assertIs(availability["has_available_source"], False)
        self.assertFalse(availability["asset_status"] == "available")

    def test_partial_bundle_marks_the_visual_module_absent(self) -> None:
        """Sports carries no visual skill, so every visual field is declared absent."""

        visual = self.mapped.instance["visual_rules"]
        self.assertTrue(str(visual["profile_id"]).startswith("not_available:"))

    def test_partial_bundle_records_the_absent_visual_fields_in_provenance(self) -> None:
        record = self.mapped.field_provenance["visual_rules.profile_id"]
        self.assertEqual(record["mode"], "not_available")
        self.assertEqual(record["asset_id"], "(none)")

    def test_partial_bundle_notes_the_missing_module_source(self) -> None:
        """At least one module must record that it mapped with no available asset."""

        self.assertTrue(self.mapped.notes)

    def test_partial_bundle_declares_absent_fields_where_the_contract_allows(self) -> None:
        """Sports has no identity or visual skill, so absences are declared somewhere."""

        identity = self.mapped.instance["identity"]
        self.assertTrue(str(identity["audience"]).startswith("not_available:"))
        visual = self.mapped.instance["visual_rules"]
        self.assertTrue(str(visual["profile_id"]).startswith("not_available:"))


class UnavailableSkillTests(unittest.TestCase):
    """An unavailable skill maps to a disabled capability, never an enabled one."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = _finance_bundle()
        cls.mapped = map_bundle_to_instance(cls.bundle, resolver=_resolver())

    def test_generation_is_disabled(self) -> None:
        self.assertIs(self.mapped.instance["generation"]["enabled"], False)

    def test_publishing_is_disabled(self) -> None:
        self.assertIs(self.mapped.instance["publishing"]["enabled"], False)

    def test_generation_reason_is_machine_readable(self) -> None:
        self.assertEqual(
            self.mapped.instance["generation"]["reason"],
            "generation_capability_not_available",
        )

    def test_publishing_reason_is_machine_readable(self) -> None:
        self.assertEqual(
            self.mapped.instance["publishing"]["reason"],
            "publishing_capability_not_available",
        )

    def test_declared_skills_are_visible_in_availability(self) -> None:
        availability = self.mapped.module_availability
        self.assertIs(availability["generation"]["has_available_source"], False)
        self.assertIs(availability["publishing"]["has_available_source"], False)

    def test_availability_records_the_asset_reason(self) -> None:
        availability = self.mapped.module_availability
        self.assertEqual(
            availability["generation"]["asset_reason"],
            "generation_capability_not_available",
        )

    def test_available_modules_report_an_available_source(self) -> None:
        availability = self.mapped.module_availability
        for module in ("identity", "text_rules", "visual_rules", "risk_policy"):
            with self.subTest(module=module):
                self.assertIs(availability[module]["has_available_source"], True)

    def test_declared_skill_asset_is_unavailable_in_the_registry(self) -> None:
        asset = self.mapped.assets.get("generation_capability")
        self.assertFalse(asset.available)

    def test_source_module_declares_no_available_source(self) -> None:
        """The source skill binds an asset of a kind the registry records as
        unavailable, so the module reports no available source."""

        availability = self.mapped.module_availability["source"]
        self.assertIs(availability["has_available_source"], False)

    def test_source_fields_are_still_mapped_from_the_domain_asset(self) -> None:
        """Keywords come from the domain taxonomy, which is available, so the module
        is not empty even though its own source skill has no asset."""

        self.assertTrue(self.mapped.instance["source"]["keywords"])
        record = self.mapped.field_provenance["source.keywords"]
        self.assertEqual(record["asset_id"], "text_distillation_rules")


class ResolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = _registry()
        cls.bundle = _finance_bundle()
        cls.assets = _resolver(cls.registry).resolve(cls.bundle)

    def test_resolve_returns_bundle_assets(self) -> None:
        self.assertTrue(len(self.assets) > 0)

    def test_every_skill_is_recorded(self) -> None:
        self.assertEqual(len(self.assets.skills), len(self.bundle.all_selections()))

    def test_resolved_assets_carry_an_asset_type(self) -> None:
        for asset_id in self.assets.ids():
            self.assertTrue(self.assets.get(asset_id).asset_type, asset_id)

    def test_available_assets_have_documents(self) -> None:
        for asset in self.assets.available():
            self.assertIsNotNone(asset.document, asset.asset_id)

    def test_unavailable_assets_have_no_document(self) -> None:
        for asset in self.assets.unavailable():
            self.assertIsNone(asset.document, asset.asset_id)

    def test_unknown_asset_id_is_rejected(self) -> None:
        with self.assertRaises(MappingAssetError):
            self.assets.get("not_a_real_asset")

    def test_for_skill_returns_the_asset(self) -> None:
        asset = self.assets.for_skill("text-distillation")
        self.assertEqual(asset.skill_id, "text-distillation")

    def test_for_unknown_skill_is_rejected(self) -> None:
        with self.assertRaises(MappingAssetError):
            self.assets.for_skill("ghost-skill")

    def test_first_available_for_skill_type(self) -> None:
        asset = self.assets.first_available_for("review")
        self.assertIsNotNone(asset)
        self.assertTrue(asset.available)

    def test_first_available_returns_none_when_all_unavailable(self) -> None:
        self.assertIsNone(self.assets.first_available_for("generation"))

    def test_resolver_requires_an_asset_registry(self) -> None:
        with self.assertRaises(MappingAssetError):
            BundleAssetResolver("not a registry", self.registry)  # type: ignore[arg-type]

    def test_resolver_requires_a_skill_registry(self) -> None:
        from creator_projection import AssetRegistry

        with self.assertRaises(MappingAssetError):
            BundleAssetResolver(AssetRegistry.load(WORKSPACE), "nope")  # type: ignore[arg-type]

    def test_assets_as_dict_is_serialisable(self) -> None:
        import json

        json.dumps(self.assets.as_dict())


class MapperInputTests(unittest.TestCase):
    def test_map_requires_a_bundle(self) -> None:
        with self.assertRaises(MappingAssetError):
            BundleInstanceMapper(_resolver()).map("not a bundle")  # type: ignore[arg-type]

    def test_mapper_requires_a_resolver(self) -> None:
        with self.assertRaises(MappingAssetError):
            BundleInstanceMapper("nope")  # type: ignore[arg-type]

    def test_unsupported_domain_is_rejected(self) -> None:
        registry = _registry()
        bundle = _finance_bundle()
        object.__setattr__(bundle.request, "domain", "astrology")
        with self.assertRaises(MappingRuleError):
            BundleInstanceMapper(_resolver(registry)).map(bundle)

    def test_bundle_from_another_registry_is_rejected(self) -> None:
        """A bundle composed against one registry must not map against another."""

        foreign = SkillRegistry()
        bundle = _finance_bundle()
        with self.assertRaises(Exception):
            map_bundle_to_instance(bundle, resolver=_resolver(foreign))

    def test_mapping_against_the_composing_registry_succeeds(self) -> None:
        """The positive control for the check above."""

        registry = _registry()
        bundle = _finance_bundle()
        self.assertTrue(
            map_bundle_to_instance(bundle, resolver=_resolver(registry)).modules
        )
    def test_map_without_resolver_or_workspace_is_rejected(self) -> None:
        with self.assertRaises(MappingAssetError):
            map_bundle_to_instance(_finance_bundle())


class DiffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = _finance_bundle()
        cls.mapped = map_bundle_to_instance(cls.bundle, resolver=_resolver())

    def test_diff_reports_all_four_sections(self) -> None:
        diff = bundle_instance_diff(self.bundle, self.mapped)
        for key in ("unmapped_skills", "lost_assets", "capability_changes",
                    "incomplete_provenance", "counts"):
            self.assertIn(key, diff)

    def test_diff_counts_skills_and_assets(self) -> None:
        diff = bundle_instance_diff(self.bundle, self.mapped)
        self.assertEqual(diff["counts"]["skills"], len(self.bundle.all_selections()))
        self.assertGreater(diff["counts"]["assets"], 0)

    def test_diff_is_serialisable(self) -> None:
        import json

        json.dumps(bundle_instance_diff(self.bundle, self.mapped))

    def test_diff_requires_a_bundle(self) -> None:
        with self.assertRaises(MappingAssetError):
            bundle_instance_diff("nope", self.mapped)  # type: ignore[arg-type]

    def test_diff_requires_a_mapped_instance(self) -> None:
        with self.assertRaises(MappingAssetError):
            bundle_instance_diff(self.bundle, {})  # type: ignore[arg-type]


class WriteTests(unittest.TestCase):
    def test_write_creates_nine_files(self) -> None:
        import tempfile

        mapped = map_bundle_to_instance(_finance_bundle(), resolver=_resolver())
        with tempfile.TemporaryDirectory() as tmp:
            written = write_mapped_instance(mapped, tmp)
            self.assertEqual(len(written), 9)

    def test_write_creates_the_declared_layout(self) -> None:
        import tempfile

        mapped = map_bundle_to_instance(_finance_bundle(), resolver=_resolver())
        with tempfile.TemporaryDirectory() as tmp:
            write_mapped_instance(mapped, tmp)
            target = Path(tmp) / mapped.creator_id
            for name in ("identity.json", "source.json", "text_rules.json",
                         "visual_rules.json", "risk_policy.json", "generation.json",
                         "publishing.json", "provenance.json", "instance.json"):
                self.assertTrue((target / name).is_file(), name)

    def test_written_instance_is_readable_and_valid(self) -> None:
        import json
        import tempfile

        from creator_contract import validate as validate_contract

        mapped = map_bundle_to_instance(_finance_bundle(), resolver=_resolver())
        with tempfile.TemporaryDirectory() as tmp:
            write_mapped_instance(mapped, tmp)
            target = Path(tmp) / mapped.creator_id
            payload = json.loads((target / "instance.json").read_text(encoding="utf-8"))
            self.assertTrue(validate_contract(payload).passed)


if __name__ == "__main__":
    unittest.main()
