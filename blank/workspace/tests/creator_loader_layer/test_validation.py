"""The seven pre-load validation layers, and the post-load immutability proof."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from creator_mapping import REQUIRED_PATHS
from creator_loader import (
    REQUIRED_MODULES,
    VALID_CAPABILITY_STATES,
    CapabilityState,
    InstanceProvenanceError,
    LoaderError,
    ProvenanceKind,
    assert_immutable,
    capability_state,
    load_creator_instance,
    schema_document,
    validate_capabilities,
    validate_contract,
    validate_fields,
    validate_instance,
    validate_loaded,
    validate_modules,
    validate_provenance_block,
    validate_schema,
    validate_traceability,
)

from . import fixtures


def mapped_document(**kwargs: object) -> dict:
    """Return the aggregate document of a freshly mapped instance."""

    from creator_loader import read_artifact

    return read_artifact(fixtures.write_mapped("validation_source", **kwargs))  # type: ignore[arg-type]


class ValidateModulesTests(unittest.TestCase):
    """Layer 1: every module is present, and a missing one is never created."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.document = mapped_document()

    def test_a_complete_document_passes(self) -> None:
        validate_modules(self.document)

    def test_seven_modules_are_required(self) -> None:
        self.assertEqual(REQUIRED_MODULES, (
            "identity", "source", "text_rules", "visual_rules", "risk_policy",
            "generation", "publishing",
        ))

    def test_each_missing_module_is_reported(self) -> None:
        for module in REQUIRED_MODULES:
            document = dict(self.document)
            del document[module]
            with self.assertRaises(LoaderError, msg=module) as context:
                validate_modules(document)
            self.assertEqual(context.exception.code, "INSTANCE_MODULE_MISSING")

    def test_missing_provenance_is_reported(self) -> None:
        document = dict(self.document)
        del document["provenance"]
        with self.assertRaises(LoaderError) as context:
            validate_modules(document)
        self.assertEqual(context.exception.code, "INSTANCE_MODULE_MISSING")

    def test_a_non_object_module_is_reported(self) -> None:
        for module in REQUIRED_MODULES:
            document = dict(self.document)
            document[module] = "text"
            with self.assertRaises(LoaderError, msg=module) as context:
                validate_modules(document)
            self.assertEqual(context.exception.code, "INSTANCE_MODULE_MISSING")

    def test_a_validation_never_adds_a_module(self) -> None:
        document = dict(self.document)
        del document["publishing"]
        try:
            validate_modules(document)
        except LoaderError:
            pass
        self.assertNotIn("publishing", document)


class ValidateSchemaTests(unittest.TestCase):
    """Layer 2: the document matches the C0.1 contract schema."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.document = mapped_document()

    def test_a_valid_document_passes(self) -> None:
        validate_schema(self.document)

    def test_a_non_mapping_is_reported(self) -> None:
        with self.assertRaises(LoaderError) as context:
            validate_schema(["not", "an", "object"])  # type: ignore[arg-type]
        self.assertEqual(context.exception.code, "INSTANCE_SCHEMA_INVALID")

    def test_an_unexpected_top_level_key_is_reported(self) -> None:
        document = dict(self.document)
        document["extra"] = 1
        with self.assertRaises(LoaderError) as context:
            validate_schema(document)
        self.assertEqual(context.exception.code, "INSTANCE_SCHEMA_INVALID")

    def test_a_wrongly_typed_field_is_reported(self) -> None:
        document = json.loads(json.dumps(self.document))
        document["generation"]["enabled"] = "yes"
        with self.assertRaises(LoaderError) as context:
            validate_schema(document)
        self.assertEqual(context.exception.code, "INSTANCE_SCHEMA_INVALID")

    def test_schema_document_strips_the_loader_private_key(self) -> None:
        """The key the loader uses to carry C0.2 projection records is withheld."""

        from creator_loader import PROJECTION_FIELDS_KEY

        document = {
            "provenance": {
                PROJECTION_FIELDS_KEY: {"identity": {"name": {}}},
                "generated_by": "x",
                "identity": {"source": "a"},
            }
        }
        stripped = schema_document(document)
        self.assertNotIn(PROJECTION_FIELDS_KEY, stripped["provenance"])

    def test_schema_document_keeps_the_contract_keys(self) -> None:
        document = {
            "provenance": {
                "field_provenance": {"fields": {}, "modules": {}},
                "generated_by": "x",
                "identity": {"a": 1},
            }
        }
        stripped = schema_document(document)
        self.assertEqual(sorted(stripped["provenance"]),
                         ["field_provenance", "generated_by", "identity"])

    def test_schema_document_does_not_mutate_the_input(self) -> None:
        from creator_loader import PROJECTION_FIELDS_KEY

        document = {"provenance": {PROJECTION_FIELDS_KEY: {"a": 1}}}
        schema_document(document)
        self.assertIn(PROJECTION_FIELDS_KEY, document["provenance"])

    def test_schema_document_leaves_a_document_without_provenance_alone(self) -> None:
        document = {"identity": {"a": 1}}
        self.assertEqual(schema_document(document), document)


class ValidateContractTests(unittest.TestCase):
    """Layer 3: C0.1's own validation runs, and its checks are reported."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.document = mapped_document()

    def test_a_valid_document_passes(self) -> None:
        checks = validate_contract(self.document)
        self.assertEqual(checks["schema"], "PASS")

    def test_the_contract_checks_every_axis(self) -> None:
        checks = validate_contract(self.document)
        for name in ("schema", "dependencies", "capability_declaration", "isolation"):
            self.assertIn(name, checks)

    def test_capability_declaration_is_checked(self) -> None:
        self.assertEqual(
            validate_contract(self.document)["capability_declaration"], "PASS"
        )

    def test_isolation_is_checked(self) -> None:
        self.assertEqual(validate_contract(self.document)["isolation"], "PASS")

    def test_a_broken_dependency_is_reported(self) -> None:
        document = json.loads(json.dumps(self.document))
        document["identity"]["creator_id"] = ""
        with self.assertRaises(LoaderError) as context:
            validate_contract(document)
        self.assertEqual(context.exception.code, "INSTANCE_CONTRACT_INVALID")

    def test_validation_does_not_mutate_the_document(self) -> None:
        before = json.dumps(self.document, sort_keys=True)
        validate_contract(self.document)
        self.assertEqual(json.dumps(self.document, sort_keys=True), before)


class ValidateFieldsTests(unittest.TestCase):
    """Layer 4: every field C0.4-A's rules declare is present."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.document = mapped_document()

    def test_a_complete_document_passes(self) -> None:
        validate_fields(self.document)

    def test_required_paths_covers_every_module(self) -> None:
        self.assertEqual(sorted(REQUIRED_PATHS), sorted(REQUIRED_MODULES))

    def test_every_declared_field_is_checked(self) -> None:
        total = sum(len(paths) for paths in REQUIRED_PATHS.values())
        self.assertEqual(total, 46)

    def test_each_missing_field_is_reported(self) -> None:
        for module, paths in REQUIRED_PATHS.items():
            for path in paths:
                document = json.loads(json.dumps(self.document))
                del document[module][path]
                with self.assertRaises(LoaderError, msg=f"{module}.{path}") as context:
                    validate_fields(document)
                self.assertEqual(context.exception.code, "INSTANCE_FIELD_MISSING")

    def test_a_missing_module_is_reported_as_missing_fields(self) -> None:
        document = dict(self.document)
        del document["risk_policy"]
        with self.assertRaises(LoaderError) as context:
            validate_fields(document)
        self.assertEqual(context.exception.code, "INSTANCE_FIELD_MISSING")

    def test_the_missing_field_is_named_in_the_detail(self) -> None:
        document = json.loads(json.dumps(self.document))
        del document["visual_rules"]["profile_id"]
        with self.assertRaises(LoaderError) as context:
            validate_fields(document)
        self.assertIn("profile_id", context.exception.detail)

    def test_validation_never_fills_a_missing_field(self) -> None:
        document = json.loads(json.dumps(self.document))
        del document["visual_rules"]["profile_id"]
        try:
            validate_fields(document)
        except LoaderError:
            pass
        self.assertNotIn("profile_id", document["visual_rules"])


class ValidateProvenanceBlockTests(unittest.TestCase):
    """Layer 5: provenance is present, complete, and of a shape that is recognised."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.document = mapped_document()

    def test_a_mapped_document_is_classified_as_mapped(self) -> None:
        self.assertEqual(
            validate_provenance_block(self.document), ProvenanceKind.MAPPED.value
        )

    def test_a_document_without_provenance_is_reported(self) -> None:
        document = {k: v for k, v in self.document.items() if k != "provenance"}
        with self.assertRaises(LoaderError) as context:
            validate_provenance_block(document)
        self.assertEqual(context.exception.code, "INSTANCE_PROVENANCE_INVALID")

    def test_a_non_mapping_provenance_is_reported(self) -> None:
        document = dict(self.document)
        document["provenance"] = "text"
        with self.assertRaises(LoaderError) as context:
            validate_provenance_block(document)
        self.assertEqual(context.exception.code, "INSTANCE_PROVENANCE_INVALID")

    def test_each_missing_module_entry_is_reported(self) -> None:
        for module in REQUIRED_MODULES:
            document = json.loads(json.dumps(self.document))
            del document["provenance"][module]
            with self.assertRaises(LoaderError, msg=module) as context:
                validate_provenance_block(document)
            self.assertEqual(context.exception.code, "INSTANCE_PROVENANCE_INVALID")

    def test_an_emptied_payload_is_not_reclassified_as_projected(self) -> None:
        """The defect that hid a damaged artifact behind the wrong shape name."""

        document = json.loads(json.dumps(self.document))
        document["provenance"]["field_provenance"] = {}
        with self.assertRaises(LoaderError) as context:
            validate_provenance_block(document)
        self.assertEqual(context.exception.code, "INSTANCE_PROVENANCE_INVALID")

    def test_a_payload_without_its_fields_map_is_reported(self) -> None:
        document = json.loads(json.dumps(self.document))
        del document["provenance"]["field_provenance"]["fields"]
        with self.assertRaises(LoaderError) as context:
            validate_provenance_block(document)
        self.assertEqual(context.exception.code, "INSTANCE_PROVENANCE_INVALID")

    def test_a_payload_without_its_modules_map_is_reported(self) -> None:
        document = json.loads(json.dumps(self.document))
        del document["provenance"]["field_provenance"]["modules"]
        with self.assertRaises(LoaderError) as context:
            validate_provenance_block(document)
        self.assertEqual(context.exception.code, "INSTANCE_PROVENANCE_INVALID")

    def test_an_empty_module_record_is_reported(self) -> None:
        document = json.loads(json.dumps(self.document))
        document["provenance"]["field_provenance"]["modules"]["identity"] = {}
        with self.assertRaises(LoaderError) as context:
            validate_provenance_block(document)
        self.assertEqual(context.exception.code, "INSTANCE_PROVENANCE_INVALID")

    def test_a_record_that_states_no_availability_is_reported(self) -> None:
        document = json.loads(json.dumps(self.document))
        record = document["provenance"]["field_provenance"]["modules"]["identity"]
        record.pop("has_available_source", None)
        record.pop("asset_status", None)
        with self.assertRaises(LoaderError) as context:
            validate_provenance_block(document)
        self.assertEqual(context.exception.code, "INSTANCE_PROVENANCE_INVALID")

    def test_availability_stated_as_an_asset_status_is_accepted(self) -> None:
        document = json.loads(json.dumps(self.document))
        record = document["provenance"]["field_provenance"]["modules"]["identity"]
        record.pop("has_available_source", None)
        record["asset_status"] = "available"
        validate_provenance_block(document)

    def test_an_unrecognisable_provenance_is_reported(self) -> None:
        document = dict(self.document)
        document["provenance"] = {
            module: {"note": "hand written"} for module in REQUIRED_MODULES
        }
        with self.assertRaises(LoaderError) as context:
            validate_provenance_block(document)
        self.assertEqual(context.exception.code, "INSTANCE_PROVENANCE_INVALID")

    def test_an_empty_entry_for_one_module_is_reported(self) -> None:
        document = json.loads(json.dumps(self.document))
        document["provenance"]["identity"] = {}
        with self.assertRaises(LoaderError) as context:
            validate_provenance_block(document)
        self.assertEqual(context.exception.code, "INSTANCE_PROVENANCE_INVALID")


class CapabilityStateTests(unittest.TestCase):
    """The derivation table, branch by branch."""

    def test_an_available_source_is_available(self) -> None:
        self.assertEqual(
            capability_state({"has_available_source": True, "asset_status": "available"}),
            CapabilityState.AVAILABLE.value,
        )

    def test_a_declared_unavailable_asset_is_declared(self) -> None:
        self.assertEqual(
            capability_state(
                {"has_available_source": False, "asset_status": "unavailable",
                 "asset_id": "generation_capability"}
            ),
            CapabilityState.DECLARED.value,
        )

    def test_no_named_asset_is_absent(self) -> None:
        self.assertEqual(
            capability_state(
                {"has_available_source": False, "asset_status": "absent",
                 "asset_id": "(none)"}
            ),
            CapabilityState.ABSENT.value,
        )

    def test_a_named_asset_that_is_not_unavailable_is_unavailable(self) -> None:
        self.assertEqual(
            capability_state(
                {"has_available_source": False, "asset_status": "unknown",
                 "asset_id": "something"}
            ),
            CapabilityState.UNAVAILABLE.value,
        )

    def test_a_non_mapping_record_is_absent(self) -> None:
        self.assertEqual(
            capability_state(None), CapabilityState.ABSENT.value  # type: ignore[arg-type]
        )

    def test_a_projected_record_uses_its_asset_status(self) -> None:
        self.assertEqual(
            capability_state({"asset_status": "available", "source": "a"}),
            CapabilityState.AVAILABLE.value,
        )

    def test_a_projected_record_declaring_unavailable_is_declared(self) -> None:
        self.assertEqual(
            capability_state({"asset_status": "unavailable", "source": "a"}),
            CapabilityState.DECLARED.value,
        )

    def test_an_available_source_wins_over_an_absent_asset_id(self) -> None:
        self.assertEqual(
            capability_state({"has_available_source": True, "asset_id": "(none)"}),
            CapabilityState.AVAILABLE.value,
        )

    def test_every_produced_state_is_a_declared_state(self) -> None:
        samples = [
            {"has_available_source": True, "asset_status": "available"},
            {"has_available_source": False, "asset_status": "unavailable",
             "asset_id": "a"},
            {"has_available_source": False, "asset_status": "absent",
             "asset_id": "(none)"},
            {"has_available_source": False, "asset_status": "other", "asset_id": "a"},
            {},
        ]
        for record in samples:
            self.assertIn(capability_state(record), VALID_CAPABILITY_STATES + ("absent",))

    def test_the_declared_states_are_the_three_the_brief_names(self) -> None:
        self.assertEqual(
            VALID_CAPABILITY_STATES, ("available", "declared", "unavailable")
        )

    def test_the_derivation_never_returns_an_enabled_flag(self) -> None:
        """The function labels a state; it has no way to enable anything."""

        record = {"has_available_source": True, "asset_status": "available"}
        self.assertEqual(capability_state(record, enabled=False),
                         CapabilityState.AVAILABLE.value)


class ValidateCapabilitiesTests(unittest.TestCase):
    """Layer 6: a capability may not claim more than its record supports."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.document = mapped_document()

    def test_a_honest_document_passes(self) -> None:
        validate_capabilities(self.document)

    def test_a_document_without_provenance_is_reported(self) -> None:
        document = {k: v for k, v in self.document.items() if k != "provenance"}
        with self.assertRaises(LoaderError) as context:
            validate_capabilities(document)
        self.assertEqual(context.exception.code, "INSTANCE_CAPABILITY_INVALID")

    def test_generation_enabled_without_a_source_is_rejected(self) -> None:
        document = json.loads(json.dumps(self.document))
        document["generation"]["enabled"] = True
        document["generation"]["reason"] = ""
        with self.assertRaises(LoaderError) as context:
            validate_capabilities(document)
        self.assertEqual(context.exception.code, "INSTANCE_CAPABILITY_INVALID")

    def test_publishing_enabled_without_a_source_is_rejected(self) -> None:
        document = json.loads(json.dumps(self.document))
        document["publishing"]["enabled"] = True
        document["publishing"]["reason"] = ""
        with self.assertRaises(LoaderError) as context:
            validate_capabilities(document)
        self.assertEqual(context.exception.code, "INSTANCE_CAPABILITY_INVALID")

    def test_a_disabled_capability_without_a_reason_is_rejected(self) -> None:
        document = json.loads(json.dumps(self.document))
        document["generation"]["reason"] = ""
        with self.assertRaises(LoaderError) as context:
            validate_capabilities(document)
        self.assertEqual(context.exception.code, "INSTANCE_CAPABILITY_INVALID")

    def test_an_available_source_that_is_not_enabled_is_rejected(self) -> None:
        document = json.loads(json.dumps(self.document))
        record = document["provenance"]["field_provenance"]["modules"]["generation"]
        record["has_available_source"] = True
        record["asset_status"] = "available"
        document["generation"]["reason"] = ""
        with self.assertRaises(LoaderError) as context:
            validate_capabilities(document)
        self.assertEqual(context.exception.code, "INSTANCE_CAPABILITY_INVALID")

    def test_a_non_boolean_enabled_flag_is_rejected(self) -> None:
        document = json.loads(json.dumps(self.document))
        document["generation"]["enabled"] = "false"
        with self.assertRaises(LoaderError) as context:
            validate_capabilities(document)
        self.assertEqual(context.exception.code, "INSTANCE_CAPABILITY_INVALID")

    def test_a_missing_capability_module_is_rejected(self) -> None:
        document = json.loads(json.dumps(self.document))
        del document["publishing"]
        with self.assertRaises(LoaderError) as context:
            validate_capabilities(document)
        self.assertEqual(context.exception.code, "INSTANCE_CAPABILITY_INVALID")

    def test_a_missing_provenance_record_is_rejected(self) -> None:
        document = json.loads(json.dumps(self.document))
        del document["provenance"]["field_provenance"]["modules"]["generation"]
        with self.assertRaises(LoaderError) as context:
            validate_capabilities(document)
        self.assertEqual(context.exception.code, "INSTANCE_CAPABILITY_INVALID")

    def test_validation_never_enables_a_capability(self) -> None:
        document = json.loads(json.dumps(self.document))
        validate_capabilities(document)
        self.assertFalse(document["generation"]["enabled"])
        self.assertFalse(document["publishing"]["enabled"])

    def test_validation_never_disables_a_capability_the_artifact_enables(self) -> None:
        """It reports the contradiction; it does not resolve it by rewriting."""

        document = json.loads(json.dumps(self.document))
        document["generation"]["enabled"] = True
        document["generation"]["reason"] = ""
        try:
            validate_capabilities(document)
        except LoaderError:
            pass
        self.assertTrue(document["generation"]["enabled"])


class ValidateTraceabilityTests(unittest.TestCase):
    """Layer 7: every field is accounted for by the shape in use."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.document = mapped_document()

    def test_a_mapped_document_passes(self) -> None:
        validate_traceability(self.document, kind=ProvenanceKind.MAPPED.value)

    def test_a_missing_trace_is_reported(self) -> None:
        document = json.loads(json.dumps(self.document))
        del document["provenance"]["field_provenance"]["fields"]["identity.tone"]
        with self.assertRaises(LoaderError) as context:
            validate_traceability(document, kind=ProvenanceKind.MAPPED.value)
        self.assertEqual(context.exception.code, "INSTANCE_PROVENANCE_INVALID")

    def test_every_field_is_required_to_be_traced(self) -> None:
        document = json.loads(json.dumps(self.document))
        fields = document["provenance"]["field_provenance"]["fields"]
        for key in list(fields):
            gone = json.loads(json.dumps(document))
            del gone["provenance"]["field_provenance"]["fields"][key]
            with self.assertRaises(LoaderError, msg=key):
                validate_traceability(gone, kind=ProvenanceKind.MAPPED.value)

    def test_a_missing_fields_map_is_reported(self) -> None:
        document = json.loads(json.dumps(self.document))
        del document["provenance"]["field_provenance"]["fields"]
        with self.assertRaises(LoaderError) as context:
            validate_traceability(document, kind=ProvenanceKind.MAPPED.value)
        self.assertEqual(context.exception.code, "INSTANCE_PROVENANCE_INVALID")

    def test_a_projected_document_passes_on_its_module_records(self) -> None:
        projected = fixtures.write_projected("validation_projected")
        document = fixtures.as_document(
            json.loads((projected / "creator_instance.json").read_text(encoding="utf-8"))
        )
        validate_traceability(document, kind=ProvenanceKind.PROJECTED.value)

    def test_a_projected_module_without_evidence_is_reported(self) -> None:
        projected = fixtures.write_projected("validation_projected2")
        document = json.loads(
            (projected / "creator_instance.json").read_text(encoding="utf-8")
        )
        document["provenance"]["identity"] = {"note": "nothing useful"}
        with self.assertRaises(LoaderError) as context:
            validate_traceability(document, kind=ProvenanceKind.PROJECTED.value)
        self.assertEqual(context.exception.code, "INSTANCE_PROVENANCE_INVALID")


class ValidateInstanceTests(unittest.TestCase):
    """The combined entry point runs every layer and reports the shape it found."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.document = mapped_document()

    def test_a_valid_document_returns_a_check_map(self) -> None:
        checks = validate_instance(self.document)
        self.assertIsInstance(checks, dict)

    def test_every_layer_is_reported(self) -> None:
        checks = validate_instance(self.document)
        for name in ("modules", "schema", "contract", "fields", "provenance",
                     "capabilities", "traceability"):
            self.assertIn(name, checks)

    def test_every_layer_passes(self) -> None:
        checks = validate_instance(self.document)
        for name, status in checks.items():
            if name == "provenance_kind":
                continue
            self.assertEqual(status, "PASS", name)

    def test_the_provenance_kind_is_reported(self) -> None:
        self.assertEqual(
            validate_instance(self.document)["provenance_kind"],
            ProvenanceKind.MAPPED.value,
        )

    def test_the_contract_checks_are_folded_in(self) -> None:
        checks = validate_instance(self.document)
        self.assertIn("dependencies", checks)

    def test_validate_instance_does_not_mutate_the_document(self) -> None:
        before = json.dumps(self.document, sort_keys=True)
        validate_instance(self.document)
        self.assertEqual(json.dumps(self.document, sort_keys=True), before)


class ValidateLoadedTests(unittest.TestCase):
    """Post-load: the proof of immutability, and that traces survived the load."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = fixtures.write_mapped("validation_loaded")
        cls.loaded = load_creator_instance(cls.directory)

    def test_a_loaded_instance_passes(self) -> None:
        checks = validate_loaded(self.loaded)
        self.assertEqual(checks["immutable"], "PASS")

    def test_immutability_is_reported(self) -> None:
        self.assertEqual(validate_loaded(self.loaded)["immutable"], "PASS")

    def test_loaded_traceability_is_reported(self) -> None:
        self.assertEqual(
            validate_loaded(self.loaded)["loaded_traceability"], "PASS"
        )

    def test_the_pre_load_checks_are_carried_through(self) -> None:
        checks = validate_loaded(self.loaded)
        self.assertEqual(checks["schema"], "PASS")

    def test_assert_immutable_accepts_a_loaded_instance(self) -> None:
        assert_immutable(self.loaded)

    def test_a_projected_instance_also_passes(self) -> None:
        projected = load_creator_instance(
            fixtures.write_projected("validation_loaded_projected")
        )
        self.assertEqual(validate_loaded(projected)["immutable"], "PASS")

    def test_validate_loaded_does_not_mutate_the_instance(self) -> None:
        before = self.loaded.as_dict()
        validate_loaded(self.loaded)
        self.assertEqual(self.loaded.as_dict(), before)


class LoadRejectsInvalidArtifactsTests(unittest.TestCase):
    """The loader wires every layer together, and never repairs what it rejects."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = fixtures.write_mapped("validation_reject")

    def _copy(self, name: str, mutate: object) -> Path:
        root = fixtures.scratch_dir(f"validation_reject_{name}") / "finance_xhs"
        root.mkdir()
        for path in self.source.iterdir():
            if path.is_file():
                root.joinpath(path.name).write_bytes(path.read_bytes())
        aggregate = root / "instance.json"
        document = json.loads(aggregate.read_text(encoding="utf-8"))
        document = mutate(document)  # type: ignore[operator]
        aggregate.write_text(json.dumps(document, indent=2), encoding="utf-8")
        return root

    def test_a_valid_artifact_loads(self) -> None:
        load_creator_instance(self.source)

    def test_a_missing_field_is_never_repaired_on_disk(self) -> None:
        def mutate(document: dict) -> dict:
            del document["text_rules"]["tone"]
            return document

        root = self._copy("field", mutate)
        before = (root / "instance.json").read_bytes()
        try:
            load_creator_instance(root)
        except LoaderError:
            pass
        self.assertEqual((root / "instance.json").read_bytes(), before)

    def test_a_rejected_load_writes_nothing_new(self) -> None:
        def mutate(document: dict) -> dict:
            del document["source"]
            return document

        root = self._copy("module", mutate)
        names = sorted(path.name for path in root.iterdir())
        try:
            load_creator_instance(root)
        except LoaderError:
            pass
        self.assertEqual(sorted(path.name for path in root.iterdir()), names)

    def test_the_error_detail_names_the_problem(self) -> None:
        def mutate(document: dict) -> dict:
            del document["risk_policy"]
            return document

        root = self._copy("detail", mutate)
        try:
            load_creator_instance(root)
        except LoaderError as exc:
            text = str(exc)
            self.assertTrue("risk_policy" in text or "schema" in text, text)
        else:  # pragma: no cover
            self.fail("expected a loader failure")

    def test_a_projected_instance_never_reports_an_enabled_capability(self) -> None:
        for name in ("reject_projected_1", "reject_projected_2"):
            loaded = load_creator_instance(fixtures.write_projected(name))
            self.assertEqual(loaded.enabled_capabilities(), ())

    def test_every_loader_error_code_is_a_string(self) -> None:
        try:
            load_creator_instance("")
        except LoaderError as exc:
            self.assertIsInstance(exc.code, str)

    def test_instance_provenance_error_is_still_a_loader_error(self) -> None:
        self.assertTrue(issubclass(InstanceProvenanceError, LoaderError))

    def test_a_projected_instance_with_no_records_is_rejected(self) -> None:
        projected = fixtures.write_projected("reject_projected_3")
        document = json.loads(
            (projected / "creator_instance.json").read_text(encoding="utf-8")
        )
        document["provenance"] = {module: {} for module in REQUIRED_MODULES}
        (projected / "creator_instance.json").write_text(
            json.dumps(document), encoding="utf-8"
        )
        with self.assertRaises(LoaderError) as context:
            load_creator_instance(projected)
        self.assertIn(
            context.exception.code,
            ("INSTANCE_PROVENANCE_INVALID", "INSTANCE_CONTRACT_INVALID"),
        )


if __name__ == "__main__":
    unittest.main()
