"""Projection output: schema conformance, layout, and the example projection."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from creator_contract import validate as validate_contract
from creator_projection import (
    SOURCED_MODULES,
    ProjectionError,
    assert_registry_consistency,
    project_instance,
    validate_projection,
    write_instance,
)

WORKSPACE = Path(__file__).resolve().parents[2]


class OutputSchemaTests(unittest.TestCase):
    """The projection output must satisfy the C0.1 contract schema."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = project_instance(WORKSPACE)

    def test_contract_version_is_declared(self) -> None:
        self.assertEqual(self.result.instance["contract_version"], "1.0.0")

    def test_contract_schema_validation_passes(self) -> None:
        self.assertTrue(validate_contract(self.result.instance).passed)

    def test_projection_validation_passes(self) -> None:
        self.assertTrue(validate_projection(self.result).passed)

    def test_all_eight_modules_are_present(self) -> None:
        for module in list(SOURCED_MODULES) + ["provenance"]:
            self.assertIn(module, self.result.instance)

    def test_seven_sourced_modules_are_declared(self) -> None:
        self.assertEqual(len(SOURCED_MODULES), 7)

    def test_contract_provenance_covers_every_sourced_module(self) -> None:
        block = self.result.instance["provenance"]
        for module in SOURCED_MODULES:
            self.assertIn(module, block)

    def test_every_contract_provenance_entry_has_a_source(self) -> None:
        block = self.result.instance["provenance"]
        for module in SOURCED_MODULES:
            self.assertTrue(block[module]["source"], module)

    def test_every_contract_provenance_entry_has_a_method(self) -> None:
        block = self.result.instance["provenance"]
        for module in SOURCED_MODULES:
            self.assertTrue(block[module]["projection_method"], module)

    def test_every_contract_provenance_entry_has_a_timestamp(self) -> None:
        block = self.result.instance["provenance"]
        for module in SOURCED_MODULES:
            self.assertTrue(block[module]["timestamp"], module)

    def test_generated_by_names_this_layer(self) -> None:
        self.assertIn("creator_projection", self.result.instance["provenance"]["generated_by"])

    def test_registry_version_is_recorded(self) -> None:
        self.assertEqual(self.result.instance["provenance"]["registry_version"], "1.0.0")

    def test_report_declares_creator_id(self) -> None:
        self.assertEqual(self.result.as_report()["creator_id"], self.result.creator_id)

    def test_report_is_json_serialisable(self) -> None:
        json.dumps(self.result.as_report())

    def test_instance_is_json_serialisable(self) -> None:
        json.dumps(self.result.instance)

    def test_asset_availability_is_reported(self) -> None:
        self.assertEqual(len(self.result.asset_availability), 15)

    def test_unavailable_assets_are_visible_in_the_report(self) -> None:
        unavailable = [
            asset for asset, status in self.result.asset_availability.items() if status == "unavailable"
        ]
        self.assertEqual(len(unavailable), 6)

    def test_identity_domain_is_contract_valid(self) -> None:
        self.assertIn(
            self.result.instance["identity"]["domain"],
            ("finance", "sports", "tech", "general"),
        )

    def test_every_risk_action_is_contract_valid(self) -> None:
        for category in self.result.instance["risk_policy"]["risk_categories"]:
            self.assertIn(
                category["action"],
                ("downrank", "require_evidence", "require_review", "block"),
            )


class DeterminismTests(unittest.TestCase):
    def test_two_projections_are_identical(self) -> None:
        first = project_instance(WORKSPACE)
        second = project_instance(WORKSPACE)
        self.assertEqual(first.instance, second.instance)

    def test_two_projections_produce_identical_json(self) -> None:
        first = project_instance(WORKSPACE)
        second = project_instance(WORKSPACE)
        self.assertEqual(
            json.dumps(first.instance, sort_keys=True),
            json.dumps(second.instance, sort_keys=True),
        )

    def test_notes_are_identical_across_runs(self) -> None:
        first = [n.as_dict() for n in project_instance(WORKSPACE).notes]
        second = [n.as_dict() for n in project_instance(WORKSPACE).notes]
        self.assertEqual(first, second)

    def test_default_timestamp_is_deterministic(self) -> None:
        self.assertEqual(
            project_instance(WORKSPACE).timestamp,
            project_instance(WORKSPACE).timestamp,
        )

    def test_a_caller_supplied_timestamp_is_honoured(self) -> None:
        result = project_instance(WORKSPACE, timestamp="2026-09-28T00:00:00Z")
        self.assertEqual(result.timestamp, "2026-09-28T00:00:00Z")

    def test_caller_timestamp_reaches_provenance(self) -> None:
        result = project_instance(WORKSPACE, timestamp="2026-09-28T00:00:00Z")
        self.assertEqual(
            result.instance["provenance"]["identity"]["timestamp"],
            "2026-09-28T00:00:00Z",
        )


class WriteLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = project_instance(WORKSPACE)

    def test_write_creates_nine_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            written = write_instance(self.result, tmp)
            self.assertEqual(len(written), 9)

    def test_write_creates_the_eight_module_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_instance(self.result, tmp)
            target = Path(tmp) / self.result.creator_id
            for module in SOURCED_MODULES:
                self.assertTrue((target / f"{module}.json").is_file(), module)
            self.assertTrue((target / "provenance.json").is_file())
            self.assertTrue((target / "instance.json").is_file())

    def test_written_files_are_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            written = write_instance(self.result, tmp)
            for path in written:
                with self.subTest(path=path.name):
                    json.loads(path.read_text(encoding="utf-8"))

    def test_written_instance_file_is_schema_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_instance(self.result, tmp)
            target = Path(tmp) / self.result.creator_id
            payload = json.loads((target / "instance.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["contract_version"], "1.0.0")

    def test_provenance_file_carries_field_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_instance(self.result, tmp)
            target = Path(tmp) / self.result.creator_id
            payload = json.loads((target / "provenance.json").read_text(encoding="utf-8"))
            self.assertIn("modules", payload)
            self.assertIn("fields", payload)

    def test_written_module_matches_the_projected_document(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_instance(self.result, tmp)
            target = Path(tmp) / self.result.creator_id
            payload = json.loads((target / "identity.json").read_text(encoding="utf-8"))
            self.assertEqual(payload, self.result.instance["identity"])

    def test_write_into_a_fresh_directory_creates_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "a" / "b"
            write_instance(self.result, nested)
            self.assertTrue(nested.is_dir())


class RegistryConsistencyTests(unittest.TestCase):
    def test_consistency_check_passes(self) -> None:
        from creator_projection import AssetRegistry

        result = project_instance(WORKSPACE)
        assert_registry_consistency(result, AssetRegistry.load(WORKSPACE))

    def test_registry_version_mismatch_is_rejected(self) -> None:
        from creator_projection import AssetRegistry
        from creator_projection.mapper import ProjectionResult

        result = project_instance(WORKSPACE)
        registry = AssetRegistry.load(WORKSPACE)
        stale = ProjectionResult(
            instance=result.instance,
            notes=result.notes,
            field_provenance=result.field_provenance,
            creator_id=result.creator_id,
            registry_version="0.0.1",
            asset_availability=result.asset_availability,
            timestamp=result.timestamp,
        )
        with self.assertRaises(ProjectionError):
            assert_registry_consistency(stale, registry)

    def test_availability_mismatch_is_rejected(self) -> None:
        from creator_projection import AssetRegistry
        from creator_projection.mapper import ProjectionResult

        result = project_instance(WORKSPACE)
        registry = AssetRegistry.load(WORKSPACE)
        tampered = ProjectionResult(
            instance=result.instance,
            notes=result.notes,
            field_provenance=result.field_provenance,
            creator_id=result.creator_id,
            registry_version=result.registry_version,
            asset_availability={"only": "one"},
            timestamp=result.timestamp,
        )
        with self.assertRaises(ProjectionError):
            assert_registry_consistency(tampered, registry)

    def test_every_provenance_source_is_a_registered_asset(self) -> None:
        from creator_projection import AssetRegistry

        result = project_instance(WORKSPACE)
        registered = set(AssetRegistry.load(WORKSPACE).ids())
        block = result.instance["provenance"]
        for module in SOURCED_MODULES:
            self.assertIn(block[module]["source"], registered, module)

    def test_provenance_records_asset_status(self) -> None:
        result = project_instance(WORKSPACE)
        block = result.instance["provenance"]
        self.assertEqual(block["generation"]["asset_status"], "unavailable")
        self.assertEqual(block["visual_rules"]["asset_status"], "available")

    def test_unavailable_assets_carry_their_reason_into_provenance(self) -> None:
        result = project_instance(WORKSPACE)
        block = result.instance["provenance"]
        self.assertEqual(
            block["generation"]["asset_reason"], "generation_capability_not_available"
        )


class ExampleProjectionTests(unittest.TestCase):
    """The example projection required by the phase brief."""

    def test_example_projection_writes_the_contract_layout(self) -> None:
        result = project_instance(WORKSPACE)
        with tempfile.TemporaryDirectory() as tmp:
            write_instance(result, Path(tmp) / "creator_instance")
            target = Path(tmp) / "creator_instance" / result.creator_id
            expected = {
                "identity.json",
                "source.json",
                "text_rules.json",
                "visual_rules.json",
                "risk_policy.json",
                "generation.json",
                "publishing.json",
                "provenance.json",
                "instance.json",
            }
            self.assertEqual({p.name for p in target.iterdir()}, expected)

    def test_example_projection_notes_are_non_empty(self) -> None:
        self.assertTrue(project_instance(WORKSPACE).notes)

    def test_example_projection_reports_every_note_kind(self) -> None:
        kinds = {note.kind for note in project_instance(WORKSPACE).notes}
        self.assertIn("substitution", kinds)
        self.assertIn("capability_absent", kinds)
        self.assertIn("reference", kinds)

    def test_example_projection_note_count(self) -> None:
        self.assertEqual(len(project_instance(WORKSPACE).notes), 9)


if __name__ == "__main__":
    unittest.main()
