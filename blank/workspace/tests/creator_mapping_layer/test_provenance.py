"""Provenance: every field must trace to a skill, an asset, a version and a rule."""

from __future__ import annotations

import unittest
from copy import deepcopy
from pathlib import Path

from creator_mapping import (
    MAPPED_MODULES,
    NO_ASSET,
    REQUIRED_MAPPING_KEYS,
    BundleAssetResolver,
    FieldMapping,
    MappingProvenanceBuilder,
    MappingProvenanceError,
    assert_fields_mapped,
    assert_no_unknown_rules,
    map_bundle_to_instance,
    rule_ids,
    validate_mapping_provenance,
)
from creator_mapping.mapper import MappedInstance
from creator_skill import (
    CreatorRequest,
    DEFAULT_SKILL_CATALOG,
    SkillComposer,
    SkillRegistry,
)

WORKSPACE = Path(__file__).resolve().parents[2]


def _mapped():
    registry = SkillRegistry.from_documents(DEFAULT_SKILL_CATALOG, validate=False)
    from creator_projection import AssetRegistry

    resolver = BundleAssetResolver(AssetRegistry.load(WORKSPACE), registry)
    bundle = SkillComposer(registry).compose(
        CreatorRequest(
            domain="finance",
            platform="xiaohongshu",
            creator_id="finance_xhs",
            declared_capabilities=("visual-style-distillation",),
        )
    ).bundle
    return bundle, map_bundle_to_instance(bundle, resolver=resolver)


def _rebuild_provenance(mapped, payload_fields):
    instance = deepcopy(mapped.instance)
    instance["provenance"]["field_provenance"]["fields"] = payload_fields
    return MappedInstance(
        instance=instance,
        bundle_id=mapped.bundle_id,
        creator_id=mapped.creator_id,
        modules=mapped.modules,
        mapping_provenance=payload_fields,
        assets=mapped.assets,
        notes=mapped.notes,
        timestamp=mapped.timestamp,
    )


class FieldMappingObjectTests(unittest.TestCase):
    def _mapping(self, **overrides):
        base = {
            "field": "identity.name",
            "skill_id": "finance-persona",
            "asset_id": "text_distillation_rules",
            "version": "1.0.0",
            "rule_id": "RULE_IDENTITY_002",
            "mode": "structural",
        }
        base.update(overrides)
        return FieldMapping(**base)

    def test_valid_mapping(self) -> None:
        self.assertEqual(self._mapping().field, "identity.name")

    def test_each_required_attribute_is_enforced(self) -> None:
        for name in ("field", "skill_id", "asset_id", "version", "rule_id", "mode"):
            with self.subTest(name=name):
                with self.assertRaises(MappingProvenanceError):
                    self._mapping(**{name: ""})

    def test_as_dict_carries_the_four_required_links(self) -> None:
        record = self._mapping().as_dict()
        for key in ("skill_id", "asset_id", "version", "rule_id"):
            self.assertIn(key, record)


class BuilderTests(unittest.TestCase):
    def test_builder_records_a_field(self) -> None:
        builder = MappingProvenanceBuilder()
        builder.add(
            "identity",
            "name",
            skill_id="finance-persona",
            asset_id="text_distillation_rules",
            version="1.0.0",
            rule_id="RULE_IDENTITY_002",
            mode="structural",
        )
        self.assertTrue(builder.has("identity", "name"))

    def test_duplicate_field_is_rejected(self) -> None:
        builder = MappingProvenanceBuilder()
        builder.add("identity", "name", skill_id="s", asset_id="a", version="1",
                    rule_id="RULE_IDENTITY_002", mode="structural")
        with self.assertRaises(MappingProvenanceError):
            builder.add("identity", "name", skill_id="s", asset_id="a", version="1",
                        rule_id="RULE_IDENTITY_002", mode="structural")

    def test_empty_module_is_rejected(self) -> None:
        builder = MappingProvenanceBuilder()
        with self.assertRaises(MappingProvenanceError):
            builder.add("", "name", skill_id="s", asset_id="a", version="1",
                        rule_id="RULE_IDENTITY_002", mode="structural")

    def test_get_on_an_unmapped_field_is_rejected(self) -> None:
        with self.assertRaises(MappingProvenanceError):
            MappingProvenanceBuilder().get("identity", "ghost")

    def test_keys_are_sorted(self) -> None:
        builder = MappingProvenanceBuilder()
        for field in ("zeta", "alpha"):
            builder.add("m", field, skill_id="s", asset_id="a", version="1",
                        rule_id="RULE_IDENTITY_002", mode="structural")
        self.assertEqual(builder.keys(), ("m.alpha", "m.zeta"))

    def test_by_module_groups_fields(self) -> None:
        builder = MappingProvenanceBuilder()
        builder.add("identity", "name", skill_id="s", asset_id="a", version="1",
                    rule_id="RULE_IDENTITY_002", mode="structural")
        self.assertIn("identity", builder.by_module())

    def test_modules_lists_distinct_modules(self) -> None:
        builder = MappingProvenanceBuilder()
        builder.add("identity", "name", skill_id="s", asset_id="a", version="1",
                    rule_id="RULE_IDENTITY_002", mode="structural")
        self.assertEqual(builder.modules(), ("identity",))

    def test_as_dict_is_deterministic(self) -> None:
        builder = MappingProvenanceBuilder()
        builder.add("identity", "name", skill_id="s", asset_id="a", version="1",
                    rule_id="RULE_IDENTITY_002", mode="structural")
        self.assertEqual(builder.as_dict(), builder.as_dict())


class HelperTests(unittest.TestCase):
    def test_assert_fields_mapped_accepts_a_complete_record(self) -> None:
        builder = MappingProvenanceBuilder()
        builder.add("identity", "name", skill_id="s", asset_id="a", version="1",
                    rule_id="RULE_IDENTITY_002", mode="structural")
        assert_fields_mapped(builder.as_dict(), "identity", ("name",))

    def test_assert_fields_mapped_rejects_a_missing_record(self) -> None:
        with self.assertRaises(MappingProvenanceError):
            assert_fields_mapped({}, "identity", ("name",))

    def test_assert_fields_mapped_rejects_a_missing_key(self) -> None:
        payload = {
            "identity.name": {
                "field": "identity.name",
                "skill_id": "s",
                "asset_id": "a",
                "version": "1",
                "mode": "structural",
            }
        }
        with self.assertRaises(MappingProvenanceError):
            assert_fields_mapped(payload, "identity", ("name",))

    def test_assert_no_unknown_rules_accepts_known_rules(self) -> None:
        builder = MappingProvenanceBuilder()
        builder.add("identity", "name", skill_id="s", asset_id="a", version="1",
                    rule_id=rule_ids()[0], mode="structural")
        assert_no_unknown_rules(builder.as_dict(), rule_ids())

    def test_assert_no_unknown_rules_rejects_an_unknown_rule(self) -> None:
        builder = MappingProvenanceBuilder()
        builder.add("identity", "name", skill_id="s", asset_id="a", version="1",
                    rule_id="RULE_GHOST_999", mode="structural")
        with self.assertRaises(MappingProvenanceError):
            assert_no_unknown_rules(builder.as_dict(), rule_ids())

    def test_required_mapping_keys_are_the_four_links_plus_context(self) -> None:
        self.assertEqual(
            set(REQUIRED_MAPPING_KEYS),
            {"field", "skill_id", "asset_id", "version", "rule_id", "mode"},
        )


class RealProvenanceTests(unittest.TestCase):
    """The brief's four links, on every field of a real mapping."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle, cls.mapped = _mapped()

    def test_every_field_has_a_record(self) -> None:
        for module in MAPPED_MODULES:
            document = self.mapped.instance[module]
            for path in document:
                if path == "mapped_availability":
                    continue
                with self.subTest(field=f"{module}.{path}"):
                    self.assertIn(f"{module}.{path}", self.mapped.field_provenance)

    def test_every_record_names_a_skill(self) -> None:
        for key, record in self.mapped.field_provenance.items():
            self.assertTrue(str(record["skill_id"]).strip(), key)

    def test_every_record_names_an_asset(self) -> None:
        for key, record in self.mapped.field_provenance.items():
            self.assertTrue(str(record["asset_id"]).strip(), key)

    def test_every_record_names_a_version(self) -> None:
        for key, record in self.mapped.field_provenance.items():
            self.assertTrue(str(record["version"]).strip(), key)

    def test_every_record_names_a_rule(self) -> None:
        for key, record in self.mapped.field_provenance.items():
            self.assertTrue(str(record["rule_id"]).startswith("RULE_"), key)

    def test_every_rule_cited_exists(self) -> None:
        known = set(rule_ids())
        for key, record in self.mapped.field_provenance.items():
            self.assertIn(record["rule_id"], known, key)

    def test_every_record_carries_the_required_keys(self) -> None:
        for key, record in self.mapped.field_provenance.items():
            for name in REQUIRED_MAPPING_KEYS:
                self.assertIn(name, record, key)

    def test_visual_field_cites_the_visual_skill_and_the_m5_asset(self) -> None:
        """The brief's worked example: visual_rules.profile_id."""

        record = self.mapped.field_provenance["visual_rules.profile_id"]
        self.assertEqual(record["skill_id"], "visual-style-distillation")
        self.assertEqual(record["asset_id"], "visual_profile_m5")
        self.assertEqual(record["rule_id"], "RULE_VISUAL_001")

    def test_risk_field_cites_the_review_skill(self) -> None:
        record = self.mapped.field_provenance["risk_policy.risk_categories"]
        self.assertEqual(record["skill_id"], "finance-risk-review")
        self.assertEqual(record["asset_id"], "risk_policy_reference")

    def test_generation_field_cites_the_generation_skill(self) -> None:
        record = self.mapped.field_provenance["generation.enabled"]
        self.assertEqual(record["skill_id"], "xiaohongshu-article-generation")

    def test_publishing_field_cites_the_publishing_skill(self) -> None:
        record = self.mapped.field_provenance["publishing.enabled"]
        self.assertEqual(record["skill_id"], "xiaohongshu-publishing")

    def test_identity_field_cites_the_persona_skill(self) -> None:
        record = self.mapped.field_provenance["identity.creator_id"]
        self.assertEqual(record["skill_id"], "finance-persona")

    def test_provenance_is_deterministic(self) -> None:
        again = _mapped()[1]
        self.assertEqual(self.mapped.field_provenance, again.field_provenance)

    def test_provenance_is_serialisable(self) -> None:
        import json

        json.dumps(self.mapped.field_provenance)

    def test_every_module_has_an_availability_record(self) -> None:
        for module in MAPPED_MODULES:
            with self.subTest(module=module):
                self.assertIn(module, self.mapped.module_availability)


class MissingSourceRejectionTests(unittest.TestCase):
    """A field that cannot be traced must fail validation."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle, cls.mapped = _mapped()

    def test_baseline_passes(self) -> None:
        validate_mapping_provenance(self.mapped)

    def test_removing_a_field_record_is_rejected(self) -> None:
        payload = dict(self.mapped.field_provenance)
        del payload["identity.name"]
        tampered = _rebuild_provenance(self.mapped, payload)
        with self.assertRaises(MappingProvenanceError):
            validate_mapping_provenance(tampered)

    def test_every_required_key_is_enforced(self) -> None:
        for key in REQUIRED_MAPPING_KEYS:
            with self.subTest(key=key):
                payload = deepcopy(dict(self.mapped.field_provenance))
                del payload["identity.name"][key]
                tampered = _rebuild_provenance(self.mapped, payload)
                with self.assertRaises(MappingProvenanceError):
                    validate_mapping_provenance(tampered)

    def test_blanking_a_skill_id_is_rejected(self) -> None:
        payload = deepcopy(dict(self.mapped.field_provenance))
        payload["identity.name"]["skill_id"] = ""
        tampered = _rebuild_provenance(self.mapped, payload)
        with self.assertRaises(MappingProvenanceError):
            validate_mapping_provenance(tampered)

    def test_blanking_an_asset_id_is_rejected(self) -> None:
        payload = deepcopy(dict(self.mapped.field_provenance))
        payload["identity.name"]["asset_id"] = ""
        tampered = _rebuild_provenance(self.mapped, payload)
        with self.assertRaises(MappingProvenanceError):
            validate_mapping_provenance(tampered)

    def test_blanking_a_rule_id_is_rejected(self) -> None:
        payload = deepcopy(dict(self.mapped.field_provenance))
        payload["identity.name"]["rule_id"] = ""
        tampered = _rebuild_provenance(self.mapped, payload)
        with self.assertRaises(MappingProvenanceError):
            validate_mapping_provenance(tampered)

    def test_an_unknown_rule_is_rejected(self) -> None:
        payload = deepcopy(dict(self.mapped.field_provenance))
        payload["identity.name"]["rule_id"] = "RULE_GHOST_999"
        tampered = _rebuild_provenance(self.mapped, payload)
        with self.assertRaises(MappingProvenanceError):
            validate_mapping_provenance(tampered)

    def test_an_empty_provenance_payload_is_rejected(self) -> None:
        tampered = _rebuild_provenance(self.mapped, {})
        with self.assertRaises(MappingProvenanceError):
            validate_mapping_provenance(tampered)

    def test_a_missing_provenance_payload_is_rejected(self) -> None:
        instance = deepcopy(self.mapped.instance)
        del instance["provenance"]["field_provenance"]
        tampered = MappedInstance(
            instance=instance,
            bundle_id=self.mapped.bundle_id,
            creator_id=self.mapped.creator_id,
            modules=self.mapped.modules,
            mapping_provenance={},
            assets=self.mapped.assets,
            notes=self.mapped.notes,
            timestamp=self.mapped.timestamp,
        )
        with self.assertRaises(MappingProvenanceError):
            validate_mapping_provenance(tampered)


if __name__ == "__main__":
    unittest.main()
