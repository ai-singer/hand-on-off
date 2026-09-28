"""Skill provenance: every skill must name a real source."""

from __future__ import annotations

import unittest
from copy import deepcopy

from creator_skill import (
    CONFIDENCE_BY_SOURCE,
    DEFAULT_SKILL_CATALOG,
    PROVENANCE_SOURCES,
    REQUIRED_SKILL_PROVENANCE_KEYS,
    SkillProvenance,
    SkillProvenanceError,
    SkillRegistry,
    assert_provenance_keys_complete,
    assert_provenance_present,
    assert_source_registered,
    build_skill_provenance,
    bundle_provenance,
    validate_provenance,
    validate_skill,
)
from creator_skill.catalog import catalog_asset_references
from creator_skill.provenance import DEFAULT_TIMESTAMP
from creator_skill.registry import skill_from_document


class BuildProvenanceTests(unittest.TestCase):
    def test_manual_source_defaults_to_lower_confidence(self) -> None:
        record = build_skill_provenance(
            source_kind="manual", source_ref="authored", skill_version="1.0.0"
        )
        self.assertEqual(record.confidence, CONFIDENCE_BY_SOURCE["manual"])

    def test_template_source_defaults_to_full_confidence(self) -> None:
        record = build_skill_provenance(
            source_kind="template", source_ref="path", skill_version="1.0.0"
        )
        self.assertEqual(record.confidence, 1.0)

    def test_explicit_confidence_is_honoured(self) -> None:
        record = build_skill_provenance(
            source_kind="manual",
            source_ref="x",
            skill_version="1.0.0",
            confidence=0.25,
        )
        self.assertEqual(record.confidence, 0.25)

    def test_unknown_source_kind_is_rejected(self) -> None:
        with self.assertRaises(SkillProvenanceError):
            build_skill_provenance(
                source_kind="guess", source_ref="x", skill_version="1.0.0"
            )

    def test_timestamp_defaults_deterministically(self) -> None:
        record = build_skill_provenance(
            source_kind="manual", source_ref="x", skill_version="1.0.0"
        )
        self.assertEqual(record.generated_at, DEFAULT_TIMESTAMP)

    def test_every_source_kind_builds(self) -> None:
        for kind in PROVENANCE_SOURCES:
            with self.subTest(kind=kind):
                record = build_skill_provenance(
                    source_kind=kind, source_ref="x", skill_version="1.0.0"
                )
                self.assertEqual(record.source_kind, kind)


class RegisteredAssetTests(unittest.TestCase):
    def test_derived_source_must_resolve(self) -> None:
        record = build_skill_provenance(
            source_kind="distillation_artifact",
            source_ref="visual_profile_m5",
            skill_version="1.0.0",
        )
        assert_source_registered(record, ["visual_profile_m5"])

    def test_unknown_derived_source_is_rejected(self) -> None:
        record = build_skill_provenance(
            source_kind="distillation_artifact",
            source_ref="ghost_asset",
            skill_version="1.0.0",
        )
        with self.assertRaises(SkillProvenanceError):
            assert_source_registered(record, ["visual_profile_m5"])

    def test_projection_source_must_resolve(self) -> None:
        record = build_skill_provenance(
            source_kind="projection", source_ref="ghost", skill_version="1.0.0"
        )
        with self.assertRaises(SkillProvenanceError):
            assert_source_registered(record, ["something_else"])

    def test_manual_source_need_not_resolve(self) -> None:
        record = build_skill_provenance(
            source_kind="manual", source_ref="hand-written", skill_version="1.0.0"
        )
        assert_source_registered(record, [])

    def test_template_source_need_not_resolve(self) -> None:
        record = build_skill_provenance(
            source_kind="template", source_ref="some/path.json", skill_version="1.0.0"
        )
        assert_source_registered(record, [])


class ProvenanceKeyTests(unittest.TestCase):
    def _record(self) -> dict:
        return build_skill_provenance(
            source_kind="manual", source_ref="x", skill_version="1.0.0"
        ).as_dict()

    def test_complete_record_passes(self) -> None:
        assert_provenance_keys_complete(self._record())

    def test_every_required_key_is_enforced(self) -> None:
        for key in REQUIRED_SKILL_PROVENANCE_KEYS:
            with self.subTest(key=key):
                record = deepcopy(self._record())
                del record[key]
                with self.assertRaises(SkillProvenanceError):
                    assert_provenance_keys_complete(record)

    def test_empty_source_ref_is_rejected(self) -> None:
        record = self._record()
        record["source_ref"] = ""
        with self.assertRaises(SkillProvenanceError):
            assert_provenance_keys_complete(record)

    def test_as_dict_carries_every_required_key(self) -> None:
        record = self._record()
        for key in REQUIRED_SKILL_PROVENANCE_KEYS:
            self.assertIn(key, record)


class SkillProvenanceValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.assets = list(catalog_asset_references())

    def test_every_catalog_skill_has_valid_provenance(self) -> None:
        for entry in DEFAULT_SKILL_CATALOG:
            with self.subTest(skill=entry["skill_id"]):
                validate_provenance(
                    skill_from_document(entry), registered_assets=self.assets
                )

    def test_every_catalog_source_ref_is_a_registered_asset(self) -> None:
        registered = set(self.assets)
        for entry in DEFAULT_SKILL_CATALOG:
            source = entry["provenance"]
            if source["source_kind"] in ("distillation_artifact", "projection"):
                with self.subTest(skill=entry["skill_id"]):
                    self.assertIn(source["source_ref"], registered)

    def test_skill_claiming_an_unregistered_artifact_is_rejected(self) -> None:
        entry = deepcopy(DEFAULT_SKILL_CATALOG[0])
        entry["provenance"]["source_kind"] = "distillation_artifact"
        entry["provenance"]["source_ref"] = "no_such_artifact"
        with self.assertRaises(SkillProvenanceError):
            validate_provenance(skill_from_document(entry), registered_assets=self.assets)

    def test_skill_without_provenance_block_cannot_be_built(self) -> None:
        entry = deepcopy(DEFAULT_SKILL_CATALOG[0])
        del entry["provenance"]
        with self.assertRaises(Exception):
            skill_from_document(entry)

    def test_empty_source_ref_cannot_be_built(self) -> None:
        entry = deepcopy(DEFAULT_SKILL_CATALOG[0])
        entry["provenance"]["source_ref"] = "  "
        with self.assertRaises(Exception):
            skill_from_document(entry)

    def test_provenance_present_helper_accepts_a_valid_skill(self) -> None:
        assert_provenance_present(skill_from_document(DEFAULT_SKILL_CATALOG[0]))

    def test_declared_skills_carry_a_zero_confidence_note(self) -> None:
        """An unimplemented capability must not claim confidence it has not earned."""

        by_id = {entry["skill_id"]: entry for entry in DEFAULT_SKILL_CATALOG}
        for skill_id in (
            "xiaohongshu-article-generation",
            "xiaohongshu-publishing",
        ):
            with self.subTest(skill=skill_id):
                self.assertEqual(by_id[skill_id]["provenance"]["confidence"], 0.0)

    def test_substituted_skills_carry_reduced_confidence(self) -> None:
        by_id = {entry["skill_id"]: entry for entry in DEFAULT_SKILL_CATALOG}
        persona = by_id["finance-persona"]["provenance"]
        self.assertLess(persona["confidence"], 1.0)
        self.assertIn("no distilled persona asset", persona["note"])

    def test_every_unavailable_skill_declares_a_reason(self) -> None:
        for entry in DEFAULT_SKILL_CATALOG:
            if entry["status"] != "available":
                with self.subTest(skill=entry["skill_id"]):
                    self.assertTrue(entry.get("reason"))


class BundleProvenanceTests(unittest.TestCase):
    def test_bundle_provenance_names_the_skills(self) -> None:
        record = bundle_provenance(bundle_id="b-1", sources=["a", "b"])
        self.assertIn("a", record.note)
        self.assertIn("b", record.note)

    def test_bundle_provenance_uses_projection_kind(self) -> None:
        self.assertEqual(
            bundle_provenance(bundle_id="b-1", sources=["a"]).source_kind, "projection"
        )

    def test_bundle_provenance_requires_a_source(self) -> None:
        with self.assertRaises(SkillProvenanceError):
            bundle_provenance(bundle_id="b-1", sources=[])

    def test_bundle_provenance_is_deterministic(self) -> None:
        first = bundle_provenance(bundle_id="b-1", sources=["a", "b"])
        second = bundle_provenance(bundle_id="b-1", sources=["b", "a"])
        self.assertEqual(first.as_dict(), second.as_dict())


class FullSkillValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.assets = list(catalog_asset_references())

    def test_every_catalog_skill_validates_completely(self) -> None:
        for entry in DEFAULT_SKILL_CATALOG:
            with self.subTest(skill=entry["skill_id"]):
                report = validate_skill(
                    skill_from_document(entry), registered_assets=self.assets
                )
                self.assertTrue(report.passed)
                self.assertEqual(report.status, "PASS")

    def test_report_records_all_four_checks(self) -> None:
        report = validate_skill(
            skill_from_document(DEFAULT_SKILL_CATALOG[0]), registered_assets=self.assets
        )
        self.assertEqual(
            sorted(report.checks),
            ["isolation", "provenance", "schema", "semantics"],
        )

    def test_report_is_serialisable(self) -> None:
        import json

        report = validate_skill(
            skill_from_document(DEFAULT_SKILL_CATALOG[0]), registered_assets=self.assets
        )
        json.dumps(report.as_dict())

    def test_every_registered_skill_in_the_default_registry_validates(self) -> None:
        registry = SkillRegistry.from_documents(
            DEFAULT_SKILL_CATALOG, registered_assets=self.assets
        )
        for skill in registry:
            with self.subTest(skill=skill.skill_id):
                self.assertTrue(
                    validate_skill(skill, registered_assets=self.assets).passed
                )


if __name__ == "__main__":
    unittest.main()
