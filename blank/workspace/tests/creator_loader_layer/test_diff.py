"""Comparing two loaded instances on four axes, plus fields, modules and shape."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from creator_loader import (
    MODULES,
    InstanceDiff,
    InstanceDiffError,
    compare_loaded_instances,
    load_creator_instance,
)

from . import fixtures


def mapped_copy(name: str, mutate: object) -> Path:
    """Return a mapped instance directory whose aggregate has been mutated."""

    source = fixtures.write_mapped(f"diff_src_{name}")
    root = fixtures.scratch_dir(f"diff_{name}") / "finance_xhs"
    root.mkdir()
    for path in source.iterdir():
        if path.is_file():
            root.joinpath(path.name).write_bytes(path.read_bytes())
    aggregate = root / "instance.json"
    document = json.loads(aggregate.read_text(encoding="utf-8"))
    document = mutate(document)  # type: ignore[operator]
    aggregate.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return root


class SameInstanceTests(unittest.TestCase):
    """An instance compared with itself is identical on every axis."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = fixtures.write_mapped("diff_same")
        cls.a = load_creator_instance(cls.directory)
        cls.b = load_creator_instance(cls.directory)
        cls.diff = compare_loaded_instances(cls.a, cls.b)

    def test_the_result_is_an_instance_diff(self) -> None:
        self.assertIsInstance(self.diff, InstanceDiff)

    def test_it_is_reported_as_the_same(self) -> None:
        self.assertTrue(self.diff.same)

    def test_changed_is_the_negation_of_same(self) -> None:
        self.assertFalse(self.diff.changed)

    def test_identity_did_not_change(self) -> None:
        self.assertEqual(self.diff.identity_changed, ())

    def test_skills_did_not_change(self) -> None:
        self.assertEqual(self.diff.skills_changed, ())

    def test_assets_did_not_change(self) -> None:
        self.assertEqual(self.diff.assets_changed, ())

    def test_capabilities_did_not_change(self) -> None:
        self.assertEqual(self.diff.capabilities_changed, ())

    def test_fields_did_not_change(self) -> None:
        self.assertEqual(self.diff.fields_changed, ())

    def test_modules_did_not_change(self) -> None:
        self.assertEqual(self.diff.modules_changed, ())

    def test_the_provenance_shape_did_not_change(self) -> None:
        self.assertEqual(self.diff.kind_changed, ())

    def test_no_axis_moved(self) -> None:
        self.assertEqual(self.diff.axes, ())

    def test_the_summary_is_identical(self) -> None:
        self.assertEqual(self.diff.summary(), "identical")

    def test_the_instance_ids_are_reported(self) -> None:
        self.assertEqual(self.diff.instance_a, "finance_xhs")
        self.assertEqual(self.diff.instance_b, "finance_xhs")

    def test_the_diff_is_json_safe(self) -> None:
        json.dumps(self.diff.as_dict())

    def test_comparison_is_deterministic(self) -> None:
        self.assertEqual(
            compare_loaded_instances(self.a, self.b).as_dict(),
            compare_loaded_instances(self.a, self.b).as_dict(),
        )

    def test_comparison_does_not_reread_the_artifact(self) -> None:
        """A comparison reads the loaded objects, so disk changes cannot affect it."""

        before = self.diff.as_dict()
        (self.directory / "instance.json").write_text("{}", encoding="utf-8")
        self.assertEqual(compare_loaded_instances(self.a, self.b).as_dict(), before)


class ChangedFieldTests(unittest.TestCase):
    """A changed field value is reported under ``fields_changed``."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.a = load_creator_instance(fixtures.write_mapped("diff_field_a"))

        def mutate(document: dict) -> dict:
            document["identity"]["tone"] = "a different tone"
            return document

        cls.b = load_creator_instance(mapped_copy("field_b", mutate))
        cls.diff = compare_loaded_instances(cls.a, cls.b)

    def test_it_is_reported_as_changed(self) -> None:
        self.assertTrue(self.diff.changed)

    def test_the_field_is_named(self) -> None:
        self.assertIn("identity.tone", self.diff.fields_changed)

    def test_only_that_field_is_named(self) -> None:
        self.assertEqual(self.diff.fields_changed, ("identity.tone",))

    def test_identity_is_also_reported_changed(self) -> None:
        self.assertIn("tone", self.diff.identity_changed)

    def test_the_skills_are_unchanged(self) -> None:
        self.assertEqual(self.diff.skills_changed, ())

    def test_the_assets_are_unchanged(self) -> None:
        self.assertEqual(self.diff.assets_changed, ())

    def test_the_summary_names_the_axes(self) -> None:
        self.assertIn("identity", self.diff.summary())
        self.assertIn("fields", self.diff.summary())

    def test_the_axes_include_identity_and_fields(self) -> None:
        self.assertIn("identity", self.diff.axes)
        self.assertIn("fields", self.diff.axes)


class ChangedIdentityTests(unittest.TestCase):
    """``identity_changed`` names identity fields that differ."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.a = load_creator_instance(fixtures.write_mapped("diff_ident_a"))

        def mutate(document: dict) -> dict:
            document["identity"]["name"] = "Another Creator"
            document["identity"]["language"] = "en"
            return document

        cls.b = load_creator_instance(mapped_copy("ident_b", mutate))
        cls.diff = compare_loaded_instances(cls.a, cls.b)

    def test_both_changed_fields_are_named(self) -> None:
        self.assertEqual(self.diff.identity_changed, ("language", "name"))

    def test_the_fields_are_named_with_their_module(self) -> None:
        self.assertIn("identity.name", self.diff.fields_changed)

    def test_an_unchanged_identity_field_is_not_named(self) -> None:
        self.assertNotIn("platform", self.diff.identity_changed)

    def test_the_change_is_sorted(self) -> None:
        self.assertEqual(
            list(self.diff.identity_changed), sorted(self.diff.identity_changed)
        )


class IdenticalMeaningTests(unittest.TestCase):
    """Prose that differs without changing meaning is not a change."""

    def test_a_changed_identity_reason_is_not_an_identity_change(self) -> None:
        a = load_creator_instance(fixtures.write_mapped("diff_prose_a"))

        def mutate(document: dict) -> dict:
            if "reason" in document["identity"]:
                document["identity"]["reason"] = "reworded but equivalent"
            return document

        b = load_creator_instance(mapped_copy("prose_b", mutate))
        diff = compare_loaded_instances(a, b)
        self.assertNotIn("reason", diff.identity_changed)


class CapabilityChangeTests(unittest.TestCase):
    """``capabilities_changed`` names modules whose capability state moved."""

    def test_a_newly_available_capability_is_reported(self) -> None:
        a = load_creator_instance(fixtures.write_mapped("diff_cap_a"))

        def mutate(document: dict) -> dict:
            record = document["provenance"]["field_provenance"]["modules"]["generation"]
            record["has_available_source"] = True
            record["asset_status"] = "available"
            document["generation"]["enabled"] = True
            document["generation"]["reason"] = ""
            return document

        b = load_creator_instance(mapped_copy("cap_b", mutate))
        diff = compare_loaded_instances(a, b)
        self.assertIn("generation", diff.capabilities_changed)

    def test_an_unrelated_capability_is_not_reported(self) -> None:
        a = load_creator_instance(fixtures.write_mapped("diff_cap_c"))

        def mutate(document: dict) -> dict:
            record = document["provenance"]["field_provenance"]["modules"]["generation"]
            record["has_available_source"] = True
            record["asset_status"] = "available"
            document["generation"]["enabled"] = True
            document["generation"]["reason"] = ""
            return document

        b = load_creator_instance(mapped_copy("cap_d", mutate))
        diff = compare_loaded_instances(a, b)
        self.assertNotIn("publishing", diff.capabilities_changed)

    def test_a_changed_capability_asset_is_reported(self) -> None:
        a = load_creator_instance(fixtures.write_mapped("diff_cap_e"))

        def mutate(document: dict) -> dict:
            payload = document["provenance"]["field_provenance"]
            payload["modules"]["generation"]["asset_id"] = "other_capability"
            return document

        b = load_creator_instance(mapped_copy("cap_f", mutate))
        diff = compare_loaded_instances(a, b)
        self.assertIn("generation", diff.capabilities_changed)

    def test_a_capability_module_present_in_only_one_instance_is_reported(self) -> None:
        a = load_creator_instance(fixtures.write_mapped("diff_cap_g"))
        b = load_creator_instance(fixtures.write_projected("diff_cap_h"))
        diff = compare_loaded_instances(a, b)
        self.assertTrue(diff.capabilities_changed)

    def test_no_capability_moved_when_only_a_value_moved(self) -> None:
        a = load_creator_instance(fixtures.write_mapped("diff_cap_i"))

        def mutate(document: dict) -> dict:
            document["visual_rules"]["visual_language"] = "evidence_first"
            return document

        b = load_creator_instance(mapped_copy("cap_j", mutate))
        diff = compare_loaded_instances(a, b)
        self.assertEqual(diff.capabilities_changed, ())
        self.assertIn("visual_rules.visual_language", diff.fields_changed)


class ShapeChangeTests(unittest.TestCase):
    """``kind_changed`` reports a comparison across provenance shapes."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.mapped = load_creator_instance(fixtures.write_mapped("diff_shape_mapped"))
        cls.projected = load_creator_instance(
            fixtures.write_projected("diff_shape_projected")
        )
        cls.diff = compare_loaded_instances(cls.mapped, cls.projected)

    def test_the_shape_change_is_reported(self) -> None:
        self.assertEqual(self.diff.kind_changed, ("mapped->projected",))

    def test_the_shape_change_appears_in_the_axes(self) -> None:
        self.assertIn("provenance_kind", self.diff.axes)

    def test_the_instances_are_not_the_same(self) -> None:
        self.assertFalse(self.diff.same)

    def test_two_projected_instances_agree_on_shape(self) -> None:
        another = load_creator_instance(
            fixtures.write_projected("diff_shape_projected2")
        )
        self.assertEqual(
            compare_loaded_instances(self.projected, another).kind_changed, ()
        )

    def test_a_mutated_projection_pair_differs_on_the_mutated_field(self) -> None:
        another = load_creator_instance(
            fixtures.write_projected("diff_shape_projected3")
        )
        document = json.loads(
            (another.source_path / "creator_instance.json").read_text(encoding="utf-8")
        )
        document["visual_rules"]["profile_version"] = "m9.9.9"
        (another.source_path / "creator_instance.json").write_text(
            json.dumps(document), encoding="utf-8"
        )
        mutated = load_creator_instance(another.source_path)
        diff = compare_loaded_instances(self.projected, mutated)
        self.assertFalse(diff.same)
        self.assertEqual(diff.kind_changed, ())
        self.assertIn("visual_rules.profile_version", diff.fields_changed)

    def test_two_projections_of_the_same_template_are_identical(self) -> None:
        """The projection is deterministic, so comparing two is a real equality."""

        another = load_creator_instance(
            fixtures.write_projected("diff_shape_projected4")
        )
        self.assertTrue(compare_loaded_instances(self.projected, another).same)

    def test_two_projections_agree_on_every_axis(self) -> None:
        another = load_creator_instance(
            fixtures.write_projected("diff_shape_projected5")
        )
        self.assertEqual(compare_loaded_instances(self.projected, another).axes, ())

    def test_a_projection_compared_with_its_mutated_copy_differs(self) -> None:
        another = load_creator_instance(
            fixtures.write_projected("diff_shape_projected6")
        )
        document = json.loads(
            (another.source_path / "creator_instance.json").read_text(encoding="utf-8")
        )
        document["identity"]["name"] = "Renamed"
        (another.source_path / "creator_instance.json").write_text(
            json.dumps(document), encoding="utf-8"
        )
        mutated = load_creator_instance(another.source_path)
        diff = compare_loaded_instances(self.projected, mutated)
        self.assertFalse(diff.same)
        self.assertIn("name", diff.identity_changed)
        self.assertEqual(diff.kind_changed, ())


class ModuleChangeTests(unittest.TestCase):
    """``modules_changed`` reports a module present in only one instance."""

    def test_a_module_only_the_second_instance_has_is_reported(self) -> None:
        a = load_creator_instance(fixtures.write_mapped("diff_mod_a"))
        b = load_creator_instance(fixtures.write_projected("diff_mod_b"))
        diff = compare_loaded_instances(a, b)
        self.assertEqual(diff.modules_changed, ())

    def test_a_pair_with_the_same_modules_reports_none(self) -> None:
        a = load_creator_instance(fixtures.write_mapped("diff_mod_c"))
        b = load_creator_instance(fixtures.write_mapped("diff_mod_d"))
        self.assertEqual(compare_loaded_instances(a, b).modules_changed, ())

    def test_the_diff_covers_every_module(self) -> None:
        self.assertEqual(len(MODULES), 7)


class DiffAccessTests(unittest.TestCase):
    """A diff can be read as attributes, as a mapping, or serialised."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.a = load_creator_instance(fixtures.write_mapped("diff_access_a"))

        def mutate(document: dict) -> dict:
            document["identity"]["name"] = "Other"
            return document

        cls.b = load_creator_instance(mapped_copy("access_b", mutate))
        cls.diff = compare_loaded_instances(cls.a, cls.b)

    def test_attribute_access_works(self) -> None:
        self.assertIn("name", self.diff.identity_changed)

    def test_mapping_access_works(self) -> None:
        self.assertIn("name", self.diff["identity_changed"])

    def test_mapping_access_of_same_works(self) -> None:
        self.assertFalse(self.diff["same"])

    def test_get_returns_a_known_key(self) -> None:
        self.assertFalse(self.diff.get("same"))

    def test_get_returns_a_default_for_an_unknown_key(self) -> None:
        self.assertIsNone(self.diff.get("nope"))

    def test_get_returns_the_given_default(self) -> None:
        self.assertEqual(self.diff.get("nope", "fallback"), "fallback")

    def test_an_unknown_key_is_reported(self) -> None:
        with self.assertRaises(InstanceDiffError):
            self.diff["nope"]

    def test_as_dict_has_every_axis(self) -> None:
        document = self.diff.as_dict()
        for key in ("identity_changed", "skills_changed", "assets_changed",
                    "capabilities_changed", "fields_changed", "modules_changed",
                    "kind_changed"):
            self.assertIn(key, document)

    def test_the_diff_is_frozen(self) -> None:
        from dataclasses import FrozenInstanceError

        with self.assertRaises(FrozenInstanceError):
            self.diff.same = True  # type: ignore[misc]

    def test_as_dict_lists_are_mutable_copies(self) -> None:
        document = self.diff.as_dict()
        document["fields_changed"].append("tampered")
        self.assertNotIn("tampered", self.diff.fields_changed)


class DiffArgumentTests(unittest.TestCase):
    """A comparison rejects anything that is not a loaded instance."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.loaded = load_creator_instance(fixtures.write_mapped("diff_args"))

    def test_a_mapping_is_rejected(self) -> None:
        with self.assertRaises(InstanceDiffError):
            compare_loaded_instances(self.loaded, {})  # type: ignore[arg-type]

    def test_none_is_rejected(self) -> None:
        with self.assertRaises(InstanceDiffError):
            compare_loaded_instances(None, self.loaded)  # type: ignore[arg-type]

    def test_a_string_is_rejected(self) -> None:
        with self.assertRaises(InstanceDiffError):
            compare_loaded_instances(self.loaded, "x")  # type: ignore[arg-type]

    def test_the_rejection_carries_a_code(self) -> None:
        try:
            compare_loaded_instances(self.loaded, None)  # type: ignore[arg-type]
        except InstanceDiffError as exc:
            self.assertEqual(exc.code, "INSTANCE_DIFF_INVALID")
        else:  # pragma: no cover
            self.fail("expected InstanceDiffError")

    def test_a_loaded_instance_is_accepted(self) -> None:
        compare_loaded_instances(self.loaded, self.loaded)

    def test_comparison_is_symmetric_on_the_same_axes(self) -> None:
        other = load_creator_instance(fixtures.write_mapped("diff_args2"))
        forward = compare_loaded_instances(self.loaded, other)
        backward = compare_loaded_instances(other, self.loaded)
        self.assertEqual(forward.axes, backward.axes)
        self.assertEqual(
            forward.identity_changed, backward.identity_changed
        )
        self.assertEqual(forward.fields_changed, backward.fields_changed)


class DiffEndToEndTests(unittest.TestCase):
    """The whole ladder, compared against itself and against a projection."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.mapped = load_creator_instance(fixtures.write_mapped("diff_e2e_mapped"))
        cls.projected = load_creator_instance(
            fixtures.write_projected("diff_e2e_projected")
        )
        cls.diff = compare_loaded_instances(cls.mapped, cls.projected)

    def test_the_mapped_instance_has_no_enabled_capability(self) -> None:
        self.assertEqual(self.mapped.enabled_capabilities(), ())

    def test_the_projected_instance_has_no_enabled_capability(self) -> None:
        self.assertEqual(self.projected.enabled_capabilities(), ())

    def test_the_creators_differ(self) -> None:
        self.assertNotEqual(self.mapped.creator_id, self.projected.creator_id)

    def test_the_creator_id_change_is_reported(self) -> None:
        self.assertIn("creator_id", self.diff.identity_changed)

    def test_the_shapes_differ(self) -> None:
        self.assertNotEqual(self.mapped.provenance_kind,
                            self.projected.provenance_kind)

    def test_the_projected_instance_has_no_field_level_skills(self) -> None:
        self.assertEqual(self.projected.provenance.skills(), ())

    def test_the_mapped_instance_does_have_field_level_skills(self) -> None:
        self.assertTrue(self.mapped.provenance.skills())

    def test_both_instances_resolve_assets_from_the_same_registry(self) -> None:
        self.assertTrue(self.mapped.provenance.assets())
        self.assertTrue(self.projected.provenance.assets())

    def test_the_axes_are_a_stable_ordered_tuple(self) -> None:
        axes = self.diff.axes
        self.assertIsInstance(axes, tuple)
        self.assertEqual(
            list(axes),
            [a for a in ("identity", "skills", "assets", "capabilities", "fields",
                         "modules", "provenance_kind") if a in axes],
        )


if __name__ == "__main__":
    unittest.main()
