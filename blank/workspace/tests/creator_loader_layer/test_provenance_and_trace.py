"""Provenance parsing, shape normalisation, asset references, and tracing."""

from __future__ import annotations

import json
import unittest

from creator_projection import AssetRegistry
from creator_loader import (
    ASSET_ID_KEYS,
    CONTRACT_PROVENANCE_MODULES,
    MAPPING_TRACE_KEYS,
    NOT_RECORDED,
    PROJECTION_FIELDS_KEY,
    REQUIRED_TRACE_KEYS,
    AssetReference,
    AssetReferenceResolver,
    InstanceProvenanceError,
    InstanceProvenanceMissingError,
    ProvenanceKind,
    availability_from_field_records,
    classify_provenance,
    collect_asset_ids,
    contract_block,
    load_creator_instance,
    normalize_provenance,
    parse_provenance,
    projection_fields,
    provenance_kind,
    trace_instance,
    untraced_fields,
    untraced_projection_fields,
)

from . import fixtures


def mapped_document(**kwargs: object) -> dict:
    from creator_loader import read_artifact

    return read_artifact(fixtures.write_mapped("prov_source", **kwargs))  # type: ignore[arg-type]


class ClassifyProvenanceTests(unittest.TestCase):
    """The shape classifier distinguishes three shapes and refuses to guess."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.mapped = mapped_document()["provenance"]
        cls.projected = json.loads(
            (fixtures.write_projected("prov_classify") / "creator_instance.json")
            .read_text(encoding="utf-8")
        )["provenance"]

    def test_a_mapped_payload_is_mapped(self) -> None:
        self.assertEqual(
            classify_provenance(self.mapped), ProvenanceKind.MAPPED.value
        )

    def test_a_projected_block_is_projected(self) -> None:
        self.assertEqual(
            classify_provenance(self.projected), ProvenanceKind.PROJECTED.value
        )

    def test_an_empty_block_is_absent(self) -> None:
        self.assertEqual(classify_provenance({}), ProvenanceKind.ABSENT.value)

    def test_a_non_mapping_is_absent(self) -> None:
        self.assertEqual(classify_provenance("text"), ProvenanceKind.ABSENT.value)

    def test_an_emptied_payload_is_absent_not_projected(self) -> None:
        block = json.loads(json.dumps(self.mapped))
        block["field_provenance"] = {}
        self.assertEqual(classify_provenance(block), ProvenanceKind.ABSENT.value)

    def test_a_payload_is_mapped_even_when_its_maps_are_empty(self) -> None:
        """The keys being present is what claims a mapping, not their contents."""

        block = dict(self.mapped)
        block["field_provenance"] = {"fields": {}, "modules": {}}
        self.assertEqual(classify_provenance(block), ProvenanceKind.MAPPED.value)

    def test_hand_written_records_are_absent(self) -> None:
        block = {module: {"note": "hand written"} for module in CONTRACT_PROVENANCE_MODULES}
        self.assertEqual(classify_provenance(block), ProvenanceKind.ABSENT.value)

    def test_a_partial_projection_is_absent(self) -> None:
        block = json.loads(json.dumps(self.projected))
        del block["risk_policy"]
        self.assertEqual(classify_provenance(block), ProvenanceKind.ABSENT.value)

    def test_provenance_kind_agrees_with_the_classifier(self) -> None:
        for block in (self.mapped, self.projected, {}):
            self.assertEqual(provenance_kind(block), classify_provenance(block))

    def test_a_normalised_projection_still_reads_as_projected(self) -> None:
        block = {
            PROJECTION_FIELDS_KEY: {"identity": {}},
            **{module: {"projection_method": "m"} for module in CONTRACT_PROVENANCE_MODULES},
        }
        self.assertEqual(classify_provenance(block), ProvenanceKind.PROJECTED.value)


class NormalizeProvenanceTests(unittest.TestCase):
    """Normalising regroups what an artifact says; it does not add to it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = fixtures.write_mapped("prov_normalize")
        cls.aggregate = mapped_document()

    def test_a_directory_block_is_recognised(self) -> None:
        block = json.loads((self.directory / "provenance.json").read_text(encoding="utf-8"))
        normalized = normalize_provenance(block)
        for module in CONTRACT_PROVENANCE_MODULES:
            self.assertIn(module, normalized)

    def test_a_directory_block_normalises_to_a_mapping_payload(self) -> None:
        block = json.loads((self.directory / "provenance.json").read_text(encoding="utf-8"))
        normalized = normalize_provenance(block)
        self.assertEqual(classify_provenance(normalized), ProvenanceKind.MAPPED.value)

    def test_the_payload_gains_the_fields_map(self) -> None:
        block = json.loads((self.directory / "provenance.json").read_text(encoding="utf-8"))
        payload = normalize_provenance(block)["field_provenance"]
        self.assertIn("fields", payload)

    def test_the_payload_gains_an_availability_map(self) -> None:
        block = json.loads((self.directory / "provenance.json").read_text(encoding="utf-8"))
        payload = normalize_provenance(block)["field_provenance"]
        self.assertIn("modules", payload)

    def test_the_gained_availability_is_marked_as_derived(self) -> None:
        block = json.loads((self.directory / "provenance.json").read_text(encoding="utf-8"))
        payload = normalize_provenance(block)["field_provenance"]
        self.assertTrue(
            payload["modules"]["source"]["derived_from_field_records"]
        )

    def test_an_aggregate_block_passes_through_unchanged(self) -> None:
        block = self.aggregate["provenance"]
        normalized = normalize_provenance(block)
        self.assertEqual(
            sorted(normalized), sorted(block)
        )

    def test_an_unrecognised_block_passes_through_unchanged(self) -> None:
        block = {"hand": "written"}
        self.assertEqual(normalize_provenance(block), block)

    def test_normalising_a_non_mapping_is_reported(self) -> None:
        with self.assertRaises(InstanceProvenanceMissingError):
            normalize_provenance("text")  # type: ignore[arg-type]

    def test_contract_block_removes_only_the_private_key(self) -> None:
        block = {PROJECTION_FIELDS_KEY: {"a": 1}, "generated_by": "x"}
        self.assertEqual(contract_block(block), {"generated_by": "x"})

    def test_projection_fields_reads_the_private_key(self) -> None:
        block = {PROJECTION_FIELDS_KEY: {"identity": {"name": {}}}}
        self.assertEqual(projection_fields(block), {"identity": {"name": {}}})

    def test_projection_fields_is_empty_without_the_key(self) -> None:
        self.assertEqual(projection_fields({"generated_by": "x"}), {})

    def test_projection_fields_is_empty_for_a_non_mapping(self) -> None:
        self.assertEqual(projection_fields("text"), {})  # type: ignore[arg-type]

    def test_a_projected_directory_normalises_and_keeps_its_field_records(self) -> None:
        directory = fixtures.write_projection_directory("prov_projected_dir")
        block = json.loads((directory / "provenance.json").read_text(encoding="utf-8"))
        normalized = normalize_provenance(block)
        self.assertEqual(
            classify_provenance(normalized), ProvenanceKind.PROJECTED.value
        )
        self.assertIn(PROJECTION_FIELDS_KEY, normalized)


class AvailabilityRecoveryTests(unittest.TestCase):
    """When the availability map is absent, the state is recovered, not invented."""

    def _flat_fields(self) -> dict:
        return {
            "identity.name": {"asset_id": "text_distillation_rules", "mode": "asset"},
            "identity.tone": {"asset_id": "text_distillation_rules", "mode": "asset"},
            "source.collection_rules": {"asset_id": "(none)", "mode": "not_available"},
            "generation.enabled": {"asset_id": "generation_capability",
                                   "mode": "capability"},
        }

    def test_every_module_with_fields_gets_a_record(self) -> None:
        records = availability_from_field_records(self._flat_fields())
        self.assertEqual(sorted(records), ["generation", "identity", "source"])

    def test_the_first_asset_in_id_order_is_recorded(self) -> None:
        records = availability_from_field_records(self._flat_fields())
        self.assertEqual(records["identity"]["asset_id"], "text_distillation_rules")

    def test_a_module_reading_an_asset_is_available(self) -> None:
        records = availability_from_field_records(self._flat_fields())
        self.assertTrue(records["identity"]["has_available_source"])

    def test_a_module_reading_no_asset_is_not_available(self) -> None:
        fields = {"source.collection_rules": {"asset_id": "(none)",
                                              "mode": "not_available"}}
        records = availability_from_field_records(fields)
        self.assertFalse(records["source"]["has_available_source"])

    def test_the_modes_are_recorded(self) -> None:
        records = availability_from_field_records(self._flat_fields())
        self.assertEqual(records["identity"]["modes"], ["asset"])

    def test_records_are_marked_as_derived(self) -> None:
        records = availability_from_field_records(self._flat_fields())
        self.assertTrue(all(r["derived_from_field_records"] for r in records.values()))

    def test_a_module_block_declaring_unavailable_wins(self) -> None:
        fields = {"generation.enabled": {"asset_id": "generation_capability",
                                         "mode": "capability"}}
        blocks = {"generation": {"asset_status": "unavailable"}}
        records = availability_from_field_records(fields, blocks)
        self.assertFalse(records["generation"]["has_available_source"])
        self.assertEqual(records["generation"]["asset_status"], "unavailable")

    def test_a_module_block_declaring_available_wins(self) -> None:
        fields = {"source.collection_rules": {"asset_id": "(none)",
                                              "mode": "not_available"}}
        blocks = {"source": {"asset_status": "available"}}
        records = availability_from_field_records(fields, blocks)
        self.assertTrue(records["generation" if False else "source"]["has_available_source"])

    def test_no_asset_cited_yields_no_asset_id(self) -> None:
        fields = {"source.collection_rules": {"asset_id": "(none)",
                                              "mode": "not_available"}}
        records = availability_from_field_records(fields)
        self.assertEqual(records["source"]["asset_id"], "(none)")

    def test_an_empty_field_map_yields_no_records(self) -> None:
        self.assertEqual(availability_from_field_records({}), {})

    def test_a_non_mapping_field_record_is_skipped(self) -> None:
        self.assertEqual(
            availability_from_field_records({"identity.name": "text"}), {}
        )

    def test_a_field_of_an_unknown_module_is_skipped(self) -> None:
        self.assertEqual(
            availability_from_field_records({"nope.field": {"asset_id": "a"}}), {}
        )


class ParseProvenanceTests(unittest.TestCase):
    """Parsing turns a block into typed, frozen records."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = fixtures.write_mapped("prov_parse")
        cls.document = mapped_document()

    def test_a_mapped_block_parses(self) -> None:
        provenance = parse_provenance(self.document["provenance"])
        self.assertEqual(provenance.kind, ProvenanceKind.MAPPED.value)

    def test_a_mapped_block_yields_one_trace_per_field(self) -> None:
        provenance = parse_provenance(self.document["provenance"])
        self.assertEqual(len(provenance.field_traces), 46)

    def test_the_rule_count_is_read(self) -> None:
        provenance = parse_provenance(self.document["provenance"])
        self.assertEqual(provenance.mapping_rule_count, 46)

    def test_the_bundle_id_is_read(self) -> None:
        provenance = parse_provenance(self.document["provenance"])
        self.assertTrue(provenance.bundle_id.startswith("bundle-"))

    def test_the_generator_is_read(self) -> None:
        provenance = parse_provenance(self.document["provenance"])
        self.assertEqual(provenance.generated_by[:23], "creator_mapping.mapper ")

    def test_the_factory_version_is_read(self) -> None:
        provenance = parse_provenance(self.document["provenance"])
        self.assertEqual(provenance.factory_version, "c0.4-a")

    def test_the_mapping_version_is_read(self) -> None:
        provenance = parse_provenance(self.document["provenance"])
        self.assertEqual(provenance.mapping_version, "c0.4-a")

    def test_every_module_has_a_record(self) -> None:
        provenance = parse_provenance(self.document["provenance"])
        for module in CONTRACT_PROVENANCE_MODULES:
            self.assertIn(module, provenance.module_records)

    def test_traces_carry_every_required_key(self) -> None:
        provenance = parse_provenance(self.document["provenance"])
        for trace in provenance.field_traces.values():
            for key in REQUIRED_TRACE_KEYS:
                self.assertTrue(getattr(trace, key) != "", f"{trace.field}.{key}")

    def test_the_required_trace_keys_are_the_six_the_brief_names(self) -> None:
        self.assertEqual(
            REQUIRED_TRACE_KEYS,
            ("field", "skill_id", "asset_id", "version", "rule_id", "mode"),
        )

    def test_mapping_trace_keys_are_the_three_that_prove_a_mapping(self) -> None:
        self.assertEqual(MAPPING_TRACE_KEYS, ("skill_id", "rule_id", "mode"))

    def test_asset_ids_are_resolved_when_a_registry_is_given(self) -> None:
        resolver = AssetReferenceResolver.for_workspace(fixtures.WORKSPACE)
        provenance = parse_provenance(
            self.document["provenance"], resolver=resolver
        )
        self.assertTrue(provenance.asset_references["visual_profile_m5"].registered)

    def test_asset_ids_are_recorded_unresolved_without_a_registry(self) -> None:
        provenance = parse_provenance(self.document["provenance"])
        reference = provenance.asset_references["visual_profile_m5"]
        self.assertFalse(reference.registered)
        self.assertEqual(reference.asset_status, "not_resolved")

    def test_the_unresolved_reason_names_the_missing_registry(self) -> None:
        provenance = parse_provenance(self.document["provenance"])
        self.assertEqual(
            provenance.asset_references["visual_profile_m5"].reason,
            "no_asset_registry_supplied",
        )

    def test_a_block_without_provenance_entries_is_reported(self) -> None:
        with self.assertRaises(InstanceProvenanceMissingError):
            parse_provenance({"generated_by": "x", "field_provenance": {"fields": {},
                                                                       "modules": {}}})

    def test_a_block_in_no_known_shape_is_reported(self) -> None:
        block = {module: {"note": "x"} for module in CONTRACT_PROVENANCE_MODULES}
        with self.assertRaises(InstanceProvenanceMissingError):
            parse_provenance(block)

    def test_a_trace_missing_a_required_key_is_reported(self) -> None:
        document = json.loads(json.dumps(self.document))
        del document["provenance"]["field_provenance"]["fields"]["identity.tone"][
            "mode"
        ]
        with self.assertRaises(InstanceProvenanceError):
            parse_provenance(document["provenance"])

    def test_a_trace_with_an_empty_value_is_reported(self) -> None:
        document = json.loads(json.dumps(self.document))
        document["provenance"]["field_provenance"]["fields"]["identity.tone"][
            "mode"
        ] = "  "
        with self.assertRaises(InstanceProvenanceError):
            parse_provenance(document["provenance"])

    def test_a_non_object_trace_is_reported(self) -> None:
        document = json.loads(json.dumps(self.document))
        document["provenance"]["field_provenance"]["fields"]["identity.tone"] = "x"
        with self.assertRaises(InstanceProvenanceError):
            parse_provenance(document["provenance"])

    def test_a_corrupt_trace_is_never_repaired(self) -> None:
        document = json.loads(json.dumps(self.document))
        del document["provenance"]["field_provenance"]["fields"]["identity.tone"][
            "rule_id"
        ]
        try:
            parse_provenance(document["provenance"])
        except InstanceProvenanceError:
            pass
        self.assertNotIn(
            "rule_id",
            document["provenance"]["field_provenance"]["fields"]["identity.tone"],
        )

    def test_the_skill_type_is_carried_through(self) -> None:
        provenance = parse_provenance(self.document["provenance"])
        self.assertEqual(
            provenance.field_traces["generation.enabled"].skill_type, "generation"
        )

    def test_a_trace_without_a_skill_type_parses(self) -> None:
        document = json.loads(json.dumps(self.document))
        del document["provenance"]["field_provenance"]["fields"]["identity.tone"][
            "skill_type"
        ]
        provenance = parse_provenance(document["provenance"])
        self.assertEqual(provenance.field_traces["identity.tone"].skill_type, "")

    def test_a_projected_block_parses_with_no_traces(self) -> None:
        projected = json.loads(
            (fixtures.write_projected("prov_parse_projected")
             / "creator_instance.json").read_text(encoding="utf-8")
        )
        provenance = parse_provenance(projected["provenance"])
        self.assertEqual(provenance.kind, ProvenanceKind.PROJECTED.value)
        self.assertEqual(provenance.field_traces, {})

    def test_a_projected_block_records_the_factory_version(self) -> None:
        projected = json.loads(
            (fixtures.write_projected("prov_parse_projected2")
             / "creator_instance.json").read_text(encoding="utf-8")
        )
        provenance = parse_provenance(projected["provenance"])
        self.assertEqual(provenance.factory_version, "c0.2.0")

    def test_a_projected_block_does_not_claim_a_bundle(self) -> None:
        projected = json.loads(
            (fixtures.write_projected("prov_parse_projected3")
             / "creator_instance.json").read_text(encoding="utf-8")
        )
        provenance = parse_provenance(projected["provenance"])
        self.assertEqual(provenance.bundle_id, NOT_RECORDED)

    def test_parsing_is_deterministic(self) -> None:
        first = parse_provenance(self.document["provenance"]).as_dict()
        second = parse_provenance(self.document["provenance"]).as_dict()
        self.assertEqual(first, second)

    def test_parsing_is_json_safe(self) -> None:
        json.dumps(parse_provenance(self.document["provenance"]).as_dict())

    def test_the_skills_are_every_skill_the_fields_came_from(self) -> None:
        provenance = parse_provenance(self.document["provenance"])
        self.assertEqual(len(provenance.skills()), 8)

    def test_the_assets_are_every_asset_the_fields_cited(self) -> None:
        provenance = parse_provenance(self.document["provenance"])
        self.assertEqual(len(provenance.assets()), 6)


class UnrecordedValuesTests(unittest.TestCase):
    """What an artifact does not record is reported, never invented."""

    def test_the_not_recorded_marker_is_explicit(self) -> None:
        self.assertEqual(NOT_RECORDED, "(not recorded)")

    def test_a_projected_instance_reports_no_factory_identity(self) -> None:
        loaded = load_creator_instance(fixtures.write_projected("prov_unrecorded"))
        self.assertEqual(loaded.provenance.bundle_id, NOT_RECORDED)

    def test_a_projected_instance_reports_no_rule_count(self) -> None:
        loaded = load_creator_instance(fixtures.write_projected("prov_unrecorded2"))
        self.assertEqual(loaded.provenance.mapping_rule_count, 0)

    def test_a_directory_instance_reports_no_generated_by(self) -> None:
        loaded = load_creator_instance(
            fixtures.write_mapped("prov_unrecorded3"), layout="modules"
        )
        self.assertEqual(loaded.provenance.generated_by, "")

    def test_the_trace_says_the_request_is_unrecorded(self) -> None:
        loaded = load_creator_instance(fixtures.write_mapped("prov_unrecorded4"))
        trace = trace_instance(loaded, fields=["identity.tone"])
        self.assertFalse(trace["chains"][0]["request"]["recorded"])

    def test_the_trace_explains_why_the_request_is_unrecorded(self) -> None:
        loaded = load_creator_instance(fixtures.write_mapped("prov_unrecorded5"))
        trace = trace_instance(loaded, fields=["identity.tone"])
        self.assertIn("CreatorRequest", trace["chains"][0]["request"]["detail"])

    def test_the_trace_never_invents_a_request_id(self) -> None:
        loaded = load_creator_instance(fixtures.write_mapped("prov_unrecorded6"))
        chain = trace_instance(loaded, fields=["identity.tone"])["chains"][0]
        self.assertNotIn("request_id", chain["request"])


class TraceInstanceTests(unittest.TestCase):
    """Tracing walks request → skill bundle → asset → instance field."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.loaded = load_creator_instance(fixtures.write_mapped("prov_trace"))

    def test_the_four_steps_are_declared(self) -> None:
        trace = trace_instance(self.loaded)
        self.assertEqual(
            trace["steps"], ["request", "skill_bundle", "asset", "instance_field"]
        )

    def test_one_chain_per_field(self) -> None:
        self.assertEqual(trace_instance(self.loaded)["field_count"], 46)

    def test_every_chain_names_its_field(self) -> None:
        for chain in trace_instance(self.loaded)["chains"]:
            self.assertTrue(chain["field"])

    def test_every_chain_names_its_module(self) -> None:
        for chain in trace_instance(self.loaded)["chains"]:
            self.assertEqual(chain["module"], chain["field"].partition(".")[0])

    def test_every_chain_is_complete(self) -> None:
        self.assertTrue(trace_instance(self.loaded)["complete"])

    def test_the_kind_is_reported(self) -> None:
        self.assertEqual(
            trace_instance(self.loaded)["kind"], ProvenanceKind.MAPPED.value
        )

    def test_the_instance_id_is_reported(self) -> None:
        self.assertEqual(trace_instance(self.loaded)["instance_id"], "finance_xhs")

    def test_the_source_path_is_reported(self) -> None:
        trace = trace_instance(self.loaded)
        self.assertIn("finance_xhs", trace["source_path"])

    def test_the_skill_bundle_step_is_recorded(self) -> None:
        self.assertTrue(trace_instance(self.loaded)["recorded_steps"]["skill_bundle"])

    def test_the_asset_step_is_recorded(self) -> None:
        self.assertTrue(trace_instance(self.loaded)["recorded_steps"]["asset"])

    def test_the_instance_field_step_is_recorded(self) -> None:
        self.assertTrue(
            trace_instance(self.loaded)["recorded_steps"]["instance_field"]
        )

    def test_the_request_step_is_not_recorded(self) -> None:
        self.assertFalse(trace_instance(self.loaded)["recorded_steps"]["request"])

    def test_a_single_field_can_be_traced(self) -> None:
        trace = trace_instance(self.loaded, fields=["visual_rules.profile_id"])
        self.assertEqual(trace["field_count"], 1)

    def test_a_chain_names_the_skill(self) -> None:
        chain = trace_instance(
            self.loaded, fields=["visual_rules.profile_id"]
        )["chains"][0]
        self.assertEqual(chain["skill"]["skill_id"], "visual-style-distillation")

    def test_a_chain_names_the_skill_version(self) -> None:
        chain = trace_instance(
            self.loaded, fields=["visual_rules.profile_id"]
        )["chains"][0]
        self.assertEqual(chain["skill"]["version"], "1.0.0")

    def test_a_chain_names_the_bundle(self) -> None:
        chain = trace_instance(
            self.loaded, fields=["visual_rules.profile_id"]
        )["chains"][0]
        self.assertTrue(chain["skill_bundle"]["bundle_id"].startswith("bundle-"))

    def test_a_chain_names_the_asset(self) -> None:
        chain = trace_instance(
            self.loaded, fields=["visual_rules.profile_id"]
        )["chains"][0]
        self.assertEqual(chain["asset"]["asset_id"], "visual_profile_m5")

    def test_a_chain_reports_the_asset_as_resolved(self) -> None:
        chain = trace_instance(
            self.loaded, fields=["visual_rules.profile_id"]
        )["chains"][0]
        self.assertTrue(chain["asset"]["resolved"])

    def test_a_chain_names_the_rule_that_mapped_the_field(self) -> None:
        chain = trace_instance(
            self.loaded, fields=["visual_rules.profile_id"]
        )["chains"][0]
        self.assertEqual(chain["mapping"]["rule_id"], "RULE_VISUAL_001")

    def test_a_chain_names_the_mapping_mode(self) -> None:
        chain = trace_instance(
            self.loaded, fields=["visual_rules.profile_id"]
        )["chains"][0]
        self.assertEqual(chain["mapping"]["mode"], "asset")

    def test_a_chain_names_the_mapping_version(self) -> None:
        chain = trace_instance(
            self.loaded, fields=["visual_rules.profile_id"]
        )["chains"][0]
        self.assertEqual(chain["mapping"]["mapping_version"], "c0.4-a")

    def test_a_generation_chain_names_a_declared_capability(self) -> None:
        chain = trace_instance(
            self.loaded, fields=["generation.enabled"]
        )["chains"][0]
        self.assertEqual(chain["mapping"]["mode"], "capability")

    def test_a_generation_chain_names_its_asset_as_unavailable(self) -> None:
        chain = trace_instance(
            self.loaded, fields=["generation.enabled"]
        )["chains"][0]
        self.assertEqual(chain["asset"]["status"], "unavailable")

    def test_a_field_with_no_asset_reports_one_as_unrecorded(self) -> None:
        chain = trace_instance(
            self.loaded, fields=["source.collection_rules"]
        )["chains"][0]
        self.assertFalse(chain["asset"]["recorded"])

    def test_an_unknown_field_is_reported(self) -> None:
        with self.assertRaises(InstanceProvenanceError):
            trace_instance(self.loaded, fields=["identity.nope"])

    def test_tracing_a_non_instance_is_reported(self) -> None:
        with self.assertRaises(InstanceProvenanceError):
            trace_instance({"not": "an instance"})

    def test_the_trace_is_json_safe(self) -> None:
        json.dumps(trace_instance(self.loaded))

    def test_tracing_is_deterministic(self) -> None:
        self.assertEqual(trace_instance(self.loaded), trace_instance(self.loaded))

    def test_a_projected_instance_traces_to_nothing_and_says_so(self) -> None:
        projected = load_creator_instance(
            fixtures.write_projected("prov_trace_projected")
        )
        trace = trace_instance(projected)
        self.assertEqual(trace["field_count"], 0)

    def test_a_projected_trace_reports_completeness_as_unknown(self) -> None:
        """"Nothing to trace" must not read as "everything is traced"."""

        projected = load_creator_instance(
            fixtures.write_projected("prov_trace_projected2")
        )
        self.assertIsNone(trace_instance(projected)["complete"])

    def test_a_projected_trace_explains_the_shape(self) -> None:
        projected = load_creator_instance(
            fixtures.write_projected("prov_trace_projected3")
        )
        self.assertIn("projected", trace_instance(projected)["detail"])

    def test_a_projected_trace_is_not_marked_as_traced(self) -> None:
        projected = load_creator_instance(
            fixtures.write_projected("prov_trace_projected4")
        )
        self.assertFalse(trace_instance(projected)["traced"])

    def test_a_mapped_trace_is_marked_as_traced(self) -> None:
        self.assertTrue(trace_instance(self.loaded)["traced"])


class UntracedFieldsTests(unittest.TestCase):
    """The gap finders report; they do not fill."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.loaded = load_creator_instance(fixtures.write_mapped("prov_untraced"))

    def test_a_complete_mapped_instance_has_no_gap(self) -> None:
        self.assertEqual(untraced_fields(self.loaded), ())

    def test_a_projected_instance_is_not_reported_as_wholly_untraced(self) -> None:
        """Reporting 46 missing traces for the wrong shape would be noise."""

        projected = load_creator_instance(
            fixtures.write_projected("prov_untraced_projected")
        )
        self.assertEqual(untraced_fields(projected), ())

    def test_a_projected_instance_has_no_unrecorded_module(self) -> None:
        projected = load_creator_instance(
            fixtures.write_projected("prov_untraced_projected2")
        )
        self.assertEqual(untraced_projection_fields(projected), ())

    def test_a_mapped_instance_has_no_projection_gap(self) -> None:
        self.assertEqual(untraced_projection_fields(self.loaded), ())

    def test_untraced_fields_is_empty_for_a_non_instance(self) -> None:
        self.assertEqual(untraced_fields(object()), ())

    def test_untraced_projection_fields_is_empty_for_a_non_instance(self) -> None:
        self.assertEqual(untraced_projection_fields(object()), ())


class AssetReferenceResolverTests(unittest.TestCase):
    """Resolving reads a reference; it never reads the asset's content."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = AssetRegistry.load(fixtures.WORKSPACE)
        cls.resolver = AssetReferenceResolver(cls.registry)

    def test_the_resolver_is_built_for_the_workspace(self) -> None:
        self.assertIsInstance(
            AssetReferenceResolver.for_workspace(fixtures.WORKSPACE),
            AssetReferenceResolver,
        )

    def test_a_non_registry_is_rejected(self) -> None:
        from creator_loader import InstanceAssetReferenceError

        with self.assertRaises(InstanceAssetReferenceError):
            AssetReferenceResolver({"not": "a registry"})  # type: ignore[arg-type]

    def test_a_known_asset_resolves(self) -> None:
        reference = self.resolver.resolve("visual_profile_m5")
        self.assertTrue(reference.registered)

    def test_a_known_asset_reports_its_type(self) -> None:
        self.assertEqual(
            self.resolver.resolve("visual_profile_m5").asset_type, "visual_rules"
        )

    def test_a_known_asset_reports_its_location(self) -> None:
        self.assertTrue(
            self.resolver.resolve("visual_profile_m5").location.endswith(".yaml")
        )

    def test_an_unknown_asset_resolves_as_unregistered(self) -> None:
        self.assertFalse(self.resolver.resolve("no_such_asset").registered)

    def test_an_unknown_asset_states_why(self) -> None:
        self.assertEqual(
            self.resolver.resolve("no_such_asset").reason,
            "asset_not_registered_in_this_workspace",
        )

    def test_an_empty_asset_id_is_rejected(self) -> None:
        from creator_loader import InstanceAssetReferenceError

        with self.assertRaises(InstanceAssetReferenceError):
            self.resolver.resolve("")

    def test_a_non_string_asset_id_is_rejected(self) -> None:
        from creator_loader import InstanceAssetReferenceError

        with self.assertRaises(InstanceAssetReferenceError):
            self.resolver.resolve(None)  # type: ignore[arg-type]

    def test_the_skill_id_is_attributed(self) -> None:
        reference = self.resolver.resolve("visual_profile_m5", skill_id="s")
        self.assertEqual(reference.skill_id, "s")

    def test_resolution_is_cached(self) -> None:
        first = self.resolver.resolve("visual_profile_m5")
        second = self.resolver.resolve("visual_profile_m5")
        self.assertIs(first, second)

    def test_a_later_skill_attribution_fills_a_cached_blank(self) -> None:
        first = self.resolver.resolve("visual_profile_m5")
        self.assertEqual(first.skill_id, "")
        second = self.resolver.resolve("visual_profile_m5", skill_id="s")
        self.assertEqual(second.skill_id, "s")

    def test_a_later_version_attribution_fills_a_cached_blank(self) -> None:
        """A blank attribution must not shadow a later, better-informed call."""

        resolver = AssetReferenceResolver(self.registry)
        first = resolver.resolve("visual_profile_m5")
        self.assertEqual(first.version, "")
        second = resolver.resolve("visual_profile_m5", version="1.0.0")
        self.assertEqual(second.version, "1.0.0")

    def test_an_omitted_attribution_keeps_the_cached_one(self) -> None:
        resolver = AssetReferenceResolver(self.registry)
        resolver.resolve("visual_profile_m5", skill_id="s", version="2.0.0")
        again = resolver.resolve("visual_profile_m5")
        self.assertEqual((again.skill_id, again.version), ("s", "2.0.0"))

    def test_an_explicit_attribution_overrides_the_cached_one(self) -> None:
        resolver = AssetReferenceResolver(self.registry)
        resolver.resolve("visual_profile_m5", skill_id="a", version="1.0.0")
        again = resolver.resolve("visual_profile_m5", skill_id="b", version="3.0.0")
        self.assertEqual((again.skill_id, again.version), ("b", "3.0.0"))

    def test_the_version_is_attributed(self) -> None:
        reference = self.resolver.resolve("visual_profile_m5", version="1.0.0")
        self.assertEqual(reference.version, "1.0.0")

    def test_unregistered_lists_the_unknown_ids(self) -> None:
        resolver = AssetReferenceResolver(self.registry)
        resolver.resolve("no_such_asset")
        self.assertEqual(resolver.unregistered(), ("no_such_asset",))

    def test_declared_unavailable_lists_the_declared_ones(self) -> None:
        resolver = AssetReferenceResolver(self.registry)
        resolver.resolve("generation_capability")
        self.assertEqual(resolver.declared_unavailable(), ("generation_capability",))

    def test_knows_reports_a_registered_asset(self) -> None:
        self.assertTrue(self.resolver.knows("visual_profile_m5"))

    def test_knows_reports_an_unknown_asset(self) -> None:
        self.assertFalse(self.resolver.knows("no_such_asset"))

    def test_the_registry_is_exposed(self) -> None:
        self.assertIs(self.resolver.registry, self.registry)

    def test_as_dict_is_json_safe(self) -> None:
        resolver = AssetReferenceResolver(self.registry)
        resolver.resolve("visual_profile_m5")
        json.dumps(resolver.as_dict())

    def test_a_reference_holds_no_asset_content(self) -> None:
        reference = self.resolver.resolve("visual_profile_m5")
        for forbidden in ("content", "body", "document", "payload", "text"):
            self.assertFalse(hasattr(reference, forbidden), forbidden)

    def test_asset_id_keys_are_the_two_the_artifact_uses(self) -> None:
        self.assertEqual(ASSET_ID_KEYS, ("asset_id", "asset"))

    def test_resolve_many_keys_by_id(self) -> None:
        resolver = AssetReferenceResolver(self.registry)
        resolved = resolver.resolve_many(["visual_profile_m5", "generation_capability"])
        self.assertEqual(
            sorted(resolved), ["generation_capability", "visual_profile_m5"]
        )

    def test_resolve_many_skips_placeholders(self) -> None:
        resolver = AssetReferenceResolver(self.registry)
        self.assertEqual(resolver.resolve_many(["(none)", "", "  "]), {})

    def test_resolve_many_skips_non_strings(self) -> None:
        resolver = AssetReferenceResolver(self.registry)
        self.assertEqual(resolver.resolve_many([None, 1]), {})  # type: ignore[list-item]


class CollectAssetIdsTests(unittest.TestCase):
    """Collecting reads both provenance maps, and only the ids they really name."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.document = mapped_document()

    def test_a_mapped_payload_yields_its_assets(self) -> None:
        ids = collect_asset_ids(self.document["provenance"])
        self.assertIn("visual_profile_m5", ids)

    def test_a_placeholder_is_not_an_asset(self) -> None:
        ids = collect_asset_ids(self.document["provenance"])
        self.assertNotIn("(none)", ids)

    def test_the_result_is_sorted(self) -> None:
        ids = collect_asset_ids(self.document["provenance"])
        self.assertEqual(list(ids), sorted(ids))

    def test_the_result_has_no_duplicates(self) -> None:
        ids = collect_asset_ids(self.document["provenance"])
        self.assertEqual(len(set(ids)), len(ids))

    def test_a_contract_block_names_its_assets_not_its_skill(self) -> None:
        """A contract block's ``source`` is a skill; reading it as an asset lies."""

        block = {
            "identity": {
                "source": "finance-persona",
                "assets": ["text_distillation_rules"],
            }
        }
        ids = collect_asset_ids(block, block)
        self.assertIn("text_distillation_rules", ids)
        self.assertNotIn("finance-persona", ids)

    def test_an_asset_named_only_by_the_field_map_is_collected(self) -> None:
        block = {"field_provenance": {"fields": {"a.b": {"asset_id": "x"}},
                                      "modules": {}}}
        self.assertEqual(collect_asset_ids(block), ("x",))

    def test_an_asset_named_only_by_a_module_record_is_collected(self) -> None:
        """A declared capability may contribute no derived field at all."""

        block = {
            "field_provenance": {
                "fields": {"a.b": {"asset_id": "x"}},
                "modules": {"generation": {"asset_id": "generation_capability"}},
            }
        }
        self.assertEqual(
            collect_asset_ids(block), ("generation_capability", "x")
        )

    def test_open_recordings_are_ignored(self) -> None:
        block = {"field_provenance": {"fields": {"a.b": {"asset": "(none)"}},
                                      "modules": {}}}
        self.assertEqual(collect_asset_ids(block), ())

    def test_the_asset_key_is_accepted(self) -> None:
        block = {"field_provenance": {"fields": {"a.b": {"asset": "x"}},
                                      "modules": {}}}
        self.assertEqual(collect_asset_ids(block), ("x",))

    def test_an_empty_block_yields_nothing(self) -> None:
        self.assertEqual(collect_asset_ids({}), ())

    def test_a_non_mapping_record_is_skipped(self) -> None:
        block = {"field_provenance": {"fields": {"a.b": "text"}, "modules": {}}}
        self.assertEqual(collect_asset_ids(block), ())

    def test_an_unrelated_top_level_key_is_not_read_as_a_module(self) -> None:
        block = {"generated_by": "creator_mapping.mapper c0.4-a",
                 "identity": {"asset_id": "x"}}
        self.assertEqual(collect_asset_ids(block), ("x",))


if __name__ == "__main__":
    unittest.main()
