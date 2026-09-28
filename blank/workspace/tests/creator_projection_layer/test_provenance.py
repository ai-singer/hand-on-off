"""Provenance: every field must be traceable, or validation fails."""

from __future__ import annotations

import unittest
from pathlib import Path

from creator_projection import (
    DECLARATION_CONFIDENCE,
    DEFAULT_TIMESTAMP,
    PROJECTION_METHODS,
    REQUIRED_PROVENANCE_KEYS,
    SUBSTITUTION_CONFIDENCE,
    FieldProvenance,
    ProjectionProvenanceError,
    ProvenanceBuilder,
    assert_fields_traceable,
    assert_projection_provenance,
    assert_provenance_keys_complete,
    project_instance,
    utc_now,
)

WORKSPACE = Path(__file__).resolve().parents[2]


class FieldProvenanceTests(unittest.TestCase):
    def test_valid_record_is_accepted(self) -> None:
        record = FieldProvenance(
            field="f",
            source_asset="a",
            source_path="p",
            projection_method="config_read",
        )
        self.assertEqual(record.field, "f")

    def test_empty_field_is_rejected(self) -> None:
        with self.assertRaises(ProjectionProvenanceError):
            FieldProvenance(field="", source_asset="a", source_path="p", projection_method="config_read")

    def test_empty_source_asset_is_rejected(self) -> None:
        with self.assertRaises(ProjectionProvenanceError):
            FieldProvenance(field="f", source_asset=" ", source_path="p", projection_method="config_read")

    def test_empty_source_path_is_rejected(self) -> None:
        with self.assertRaises(ProjectionProvenanceError):
            FieldProvenance(field="f", source_asset="a", source_path="", projection_method="config_read")

    def test_unknown_method_is_rejected(self) -> None:
        with self.assertRaises(ProjectionProvenanceError):
            FieldProvenance(field="f", source_asset="a", source_path="p", projection_method="guessing")

    def test_every_declared_method_is_accepted(self) -> None:
        for method in PROJECTION_METHODS:
            with self.subTest(method=method):
                FieldProvenance(field="f", source_asset="a", source_path="p", projection_method=method)

    def test_confidence_above_one_is_rejected(self) -> None:
        with self.assertRaises(ProjectionProvenanceError):
            FieldProvenance(field="f", source_asset="a", source_path="p", projection_method="config_read", confidence=1.5)

    def test_negative_confidence_is_rejected(self) -> None:
        with self.assertRaises(ProjectionProvenanceError):
            FieldProvenance(field="f", source_asset="a", source_path="p", projection_method="config_read", confidence=-0.1)

    def test_non_numeric_confidence_is_rejected(self) -> None:
        with self.assertRaises(ProjectionProvenanceError):
            FieldProvenance(field="f", source_asset="a", source_path="p", projection_method="config_read", confidence="high")  # type: ignore[arg-type]

    def test_boolean_confidence_is_rejected(self) -> None:
        with self.assertRaises(ProjectionProvenanceError):
            FieldProvenance(field="f", source_asset="a", source_path="p", projection_method="config_read", confidence=True)  # type: ignore[arg-type]

    def test_as_dict_carries_exactly_the_required_keys(self) -> None:
        record = FieldProvenance(
            field="f", source_asset="a", source_path="p", projection_method="config_read"
        ).as_dict()
        self.assertEqual(sorted(record), sorted(REQUIRED_PROVENANCE_KEYS))

    def test_default_timestamp_is_deterministic(self) -> None:
        record = FieldProvenance(
            field="f", source_asset="a", source_path="p", projection_method="config_read"
        )
        self.assertEqual(record.timestamp, DEFAULT_TIMESTAMP)

    def test_utc_now_has_the_expected_shape(self) -> None:
        value = utc_now()
        self.assertRegex(value, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_confidence_constants_are_ordered(self) -> None:
        self.assertLess(DECLARATION_CONFIDENCE, SUBSTITUTION_CONFIDENCE)
        self.assertLess(SUBSTITUTION_CONFIDENCE, 1.0)


class ProvenanceBuilderTests(unittest.TestCase):
    def test_records_are_collected_per_module(self) -> None:
        builder = ProvenanceBuilder()
        builder.add("identity", "name", source_asset="a", source_path="p", projection_method="config_read")
        self.assertIn("identity", builder.as_dict())

    def test_multiple_fields_are_collected(self) -> None:
        builder = ProvenanceBuilder()
        for field in ("a", "b", "c"):
            builder.add("m", field, source_asset="s", source_path="p", projection_method="config_read")
        self.assertEqual(len(builder.module_fields("m")), 3)

    def test_empty_module_name_is_rejected(self) -> None:
        builder = ProvenanceBuilder()
        with self.assertRaises(ProjectionProvenanceError):
            builder.add("", "f", source_asset="a", source_path="p", projection_method="config_read")

    def test_modules_are_sorted(self) -> None:
        builder = ProvenanceBuilder()
        for module in ("zeta", "alpha"):
            builder.add(module, "f", source_asset="a", source_path="p", projection_method="config_read")
        self.assertEqual(builder.modules(), ("alpha", "zeta"))

    def test_fields_are_sorted(self) -> None:
        builder = ProvenanceBuilder()
        for field in ("zeta", "alpha"):
            builder.add("m", field, source_asset="a", source_path="p", projection_method="config_read")
        self.assertEqual(list(builder.as_dict()["m"]), ["alpha", "zeta"])

    def test_timestamp_is_propagated(self) -> None:
        builder = ProvenanceBuilder(timestamp="2026-01-01T00:00:00Z")
        builder.add("m", "f", source_asset="a", source_path="p", projection_method="config_read")
        self.assertEqual(builder.as_dict()["m"]["f"]["timestamp"], "2026-01-01T00:00:00Z")

    def test_unknown_module_fields_are_empty(self) -> None:
        self.assertEqual(ProvenanceBuilder().module_fields("absent"), {})


class TraceabilityTests(unittest.TestCase):
    def _provenance(self) -> dict:
        builder = ProvenanceBuilder()
        builder.add("identity", "name", source_asset="a", source_path="p", projection_method="config_read")
        return builder.as_dict()

    def test_complete_record_passes(self) -> None:
        assert_fields_traceable(self._provenance(), "identity", ("name",))

    def test_missing_module_is_rejected(self) -> None:
        with self.assertRaises(ProjectionProvenanceError):
            assert_fields_traceable(self._provenance(), "source", ("keywords",))

    def test_missing_field_is_rejected(self) -> None:
        with self.assertRaises(ProjectionProvenanceError):
            assert_fields_traceable(self._provenance(), "identity", ("audience",))

    def test_record_missing_a_key_is_rejected(self) -> None:
        payload = self._provenance()
        del payload["identity"]["name"]["projection_method"]
        with self.assertRaises(ProjectionProvenanceError):
            assert_fields_traceable(payload, "identity", ("name",))

    def test_record_with_empty_source_is_rejected(self) -> None:
        payload = self._provenance()
        payload["identity"]["name"]["source_asset"] = ""
        with self.assertRaises(ProjectionProvenanceError):
            assert_fields_traceable(payload, "identity", ("name",))

    def test_record_with_unknown_method_is_rejected(self) -> None:
        payload = self._provenance()
        payload["identity"]["name"]["projection_method"] = "invented"
        with self.assertRaises(ProjectionProvenanceError):
            assert_fields_traceable(payload, "identity", ("name",))


class RealProjectionProvenanceTests(unittest.TestCase):
    """The projected instance must be fully traceable."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = project_instance(WORKSPACE)

    def test_every_module_has_field_provenance(self) -> None:
        for module in ("identity", "source", "text_rules", "visual_rules", "risk_policy", "generation", "publishing"):
            self.assertIn(module, self.result.field_provenance)

    def test_every_field_of_every_module_is_covered(self) -> None:
        for module, document in (
            ("identity", self.result.instance["identity"]),
            ("source", self.result.instance["source"]),
            ("text_rules", self.result.instance["text_rules"]),
            ("visual_rules", self.result.instance["visual_rules"]),
            ("risk_policy", self.result.instance["risk_policy"]),
            ("generation", self.result.instance["generation"]),
            ("publishing", self.result.instance["publishing"]),
        ):
            with self.subTest(module=module):
                assert_fields_traceable(
                    self.result.field_provenance, module, tuple(document)
                )

    def test_projection_provenance_check_passes(self) -> None:
        assert_projection_provenance(self.result)

    def test_provenance_keys_are_complete(self) -> None:
        assert_provenance_keys_complete(self.result)

    def test_all_records_carry_the_required_keys(self) -> None:
        for module, fields in self.result.field_provenance.items():
            for field_name, record in fields.items():
                with self.subTest(module=module, field=field_name):
                    for key in REQUIRED_PROVENANCE_KEYS:
                        self.assertIn(key, record)

    def test_all_records_name_a_registered_asset(self) -> None:
        registered = set(self.result.asset_availability)
        for module, fields in self.result.field_provenance.items():
            for field_name, record in fields.items():
                with self.subTest(module=module, field=field_name):
                    self.assertIn(record["source_asset"], registered)

    def test_provenance_is_deterministic(self) -> None:
        again = project_instance(WORKSPACE)
        self.assertEqual(self.result.field_provenance, again.field_provenance)

    def test_substituted_fields_have_lower_confidence(self) -> None:
        identity_name = self.result.field_provenance["identity"]["name"]
        self.assertEqual(identity_name["projection_method"], "asset_substitution")
        self.assertLess(identity_name["confidence"], 1.0)

    def test_referenced_visual_fields_have_full_confidence(self) -> None:
        record = self.result.field_provenance["visual_rules"]["profile_id"]
        self.assertEqual(record["projection_method"], "declared_reference")
        self.assertEqual(record["confidence"], 1.0)

    def test_declared_absence_fields_have_zero_confidence(self) -> None:
        record = self.result.field_provenance["generation"]["enabled"]
        self.assertEqual(record["projection_method"], "capability_declaration")
        self.assertEqual(record["confidence"], DECLARATION_CONFIDENCE)


if __name__ == "__main__":
    unittest.main()
