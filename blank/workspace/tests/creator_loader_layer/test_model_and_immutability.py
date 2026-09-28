"""The loaded model: frozen dataclasses, mapping proxies, and real immutability."""

from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import MappingProxyType

from creator_loader import (
    ALL_MODULES,
    CAPABILITY_MODULES,
    CONFIG_MODULES,
    AssetReference,
    CapabilityState,
    FieldTrace,
    InstanceImmutableError,
    InstanceProvenance,
    LoadedCapability,
    LoadedCreatorInstance,
    ProvenanceKind,
    assert_immutable,
    freeze,
    load_creator_instance,
    thaw,
)
from creator_loader.model import LoadedCreatorInstance as ModelClass

from . import fixtures


class EnumTests(unittest.TestCase):
    """The two enums that name loader states are stable strings."""

    def test_capability_state_is_a_string_enum(self) -> None:
        self.assertEqual(CapabilityState.AVAILABLE.value, "available")

    def test_capability_state_declared_value(self) -> None:
        self.assertEqual(CapabilityState.DECLARED.value, "declared")

    def test_capability_state_unavailable_value(self) -> None:
        self.assertEqual(CapabilityState.UNAVAILABLE.value, "unavailable")

    def test_capability_state_absent_value(self) -> None:
        self.assertEqual(CapabilityState.ABSENT.value, "absent")

    def test_capability_state_has_exactly_four_members(self) -> None:
        self.assertEqual(len(list(CapabilityState)), 4)

    def test_capability_state_compares_as_a_string(self) -> None:
        self.assertEqual(CapabilityState.AVAILABLE, "available")

    def test_provenance_kind_mapped_value(self) -> None:
        self.assertEqual(ProvenanceKind.MAPPED.value, "mapped")

    def test_provenance_kind_projected_value(self) -> None:
        self.assertEqual(ProvenanceKind.PROJECTED.value, "projected")

    def test_provenance_kind_absent_value(self) -> None:
        self.assertEqual(ProvenanceKind.ABSENT.value, "absent")

    def test_provenance_kind_has_exactly_three_members(self) -> None:
        self.assertEqual(len(list(ProvenanceKind)), 3)


class ModuleConstantTests(unittest.TestCase):
    """The module lists the loader works from match the contract's own."""

    def test_seven_config_modules(self) -> None:
        self.assertEqual(len(CONFIG_MODULES), 7)

    def test_config_modules_in_contract_order(self) -> None:
        self.assertEqual(
            list(CONFIG_MODULES),
            ["identity", "source", "text_rules", "visual_rules", "risk_policy",
             "generation", "publishing"],
        )

    def test_all_modules_adds_provenance(self) -> None:
        self.assertEqual(ALL_MODULES, CONFIG_MODULES + ("provenance",))

    def test_capability_modules_are_generation_and_publishing(self) -> None:
        self.assertEqual(CAPABILITY_MODULES, ("generation", "publishing"))


class FreezeTests(unittest.TestCase):
    """:func:`freeze` makes a document unwritable, at every depth."""

    def test_freeze_returns_a_mapping_proxy(self) -> None:
        self.assertIsInstance(freeze({"a": 1}), MappingProxyType)

    def test_frozen_mapping_rejects_a_write(self) -> None:
        frozen = freeze({"a": 1})
        with self.assertRaises(TypeError):
            frozen["a"] = 2  # type: ignore[index]

    def test_frozen_mapping_rejects_a_delete(self) -> None:
        frozen = freeze({"a": 1})
        with self.assertRaises(TypeError):
            del frozen["a"]  # type: ignore[attr-defined]

    def test_freeze_converts_a_list_to_a_tuple(self) -> None:
        self.assertEqual(freeze([1, 2, 3]), (1, 2, 3))

    def test_freeze_recurses_into_nested_mappings(self) -> None:
        frozen = freeze({"outer": {"inner": 1}})
        self.assertIsInstance(frozen["outer"], MappingProxyType)

    def test_freeze_recurses_into_mappings_inside_sequences(self) -> None:
        frozen = freeze([{"a": 1}])
        self.assertIsInstance(frozen[0], MappingProxyType)

    def test_freeze_recurses_into_nested_sequences(self) -> None:
        frozen = freeze({"a": [[1], [2]]})
        self.assertEqual(frozen["a"], ((1,), (2,)))

    def test_nested_frozen_write_is_rejected(self) -> None:
        frozen = freeze({"outer": {"inner": 1}})
        with self.assertRaises(TypeError):
            frozen["outer"]["inner"] = 2

    def test_freeze_leaves_scalars_alone(self) -> None:
        self.assertEqual(freeze(7), 7)

    def test_freeze_leaves_none_alone(self) -> None:
        self.assertIsNone(freeze(None))

    def test_freeze_leaves_strings_alone(self) -> None:
        self.assertEqual(freeze("text"), "text")

    def test_freeze_leaves_booleans_alone(self) -> None:
        self.assertIs(freeze(True), True)

    def test_freeze_stringifies_keys(self) -> None:
        self.assertIn("1", freeze({1: "a"}))

    def test_thaw_returns_a_dict(self) -> None:
        self.assertIsInstance(thaw(freeze({"a": 1})), dict)

    def test_thaw_returns_a_list_for_a_tuple(self) -> None:
        self.assertIsInstance(thaw(freeze([1, 2])), list)

    def test_thaw_recurses(self) -> None:
        self.assertEqual(thaw(freeze({"a": [{"b": 1}]})), {"a": [{"b": 1}]})

    def test_thaw_result_is_mutable(self) -> None:
        mutable = thaw(freeze({"a": 1}))
        mutable["a"] = 2
        self.assertEqual(mutable["a"], 2)

    def test_freeze_then_thaw_round_trips(self) -> None:
        original = {"a": [1, {"b": "c"}], "d": None}
        self.assertEqual(thaw(freeze(original)), original)


class AssetReferenceTests(unittest.TestCase):
    """An asset reference records a pointer, never content."""

    def test_minimal_reference(self) -> None:
        ref = AssetReference(asset_id="visual_profile_m5", asset_type="visual_rules",
                             asset_status="available")
        self.assertEqual(ref.asset_id, "visual_profile_m5")

    def test_reference_defaults_to_unregistered(self) -> None:
        ref = AssetReference(asset_id="a", asset_type="t", asset_status="s")
        self.assertFalse(ref.registered)

    def test_reference_is_frozen(self) -> None:
        ref = AssetReference(asset_id="a", asset_type="t", asset_status="s")
        with self.assertRaises(FrozenInstanceError):
            ref.asset_id = "b"  # type: ignore[misc]

    def test_resolvable_is_registered(self) -> None:
        ref = AssetReference(asset_id="a", asset_type="t", asset_status="s",
                             registered=True)
        self.assertTrue(ref.resolvable)

    def test_unregistered_reference_is_not_resolvable(self) -> None:
        ref = AssetReference(asset_id="a", asset_type="t", asset_status="s")
        self.assertFalse(ref.resolvable)

    def test_available_requires_the_available_status(self) -> None:
        ref = AssetReference(asset_id="a", asset_type="t", asset_status="available")
        self.assertTrue(ref.available)

    def test_unavailable_status_is_not_available(self) -> None:
        ref = AssetReference(asset_id="a", asset_type="t", asset_status="unavailable")
        self.assertFalse(ref.available)

    def test_reference_serialises(self) -> None:
        ref = AssetReference(asset_id="a", asset_type="t", asset_status="s")
        self.assertEqual(
            sorted(ref.as_dict()),
            ["asset_id", "asset_status", "asset_type", "location", "reason",
             "registered", "skill_id", "version"],
        )

    def test_reference_serialisation_is_json_safe(self) -> None:
        ref = AssetReference(asset_id="a", asset_type="t", asset_status="s")
        json.dumps(ref.as_dict())

    def test_reference_carries_no_content_field(self) -> None:
        """The record must not be able to hold an asset's contents."""

        ref = AssetReference(asset_id="a", asset_type="t", asset_status="s")
        for forbidden in ("content", "body", "document", "payload", "data"):
            self.assertNotIn(forbidden, ref.as_dict())


class FieldTraceTests(unittest.TestCase):
    """A field trace is the chain that produced one instance field."""

    def _trace(self, **overrides: object) -> FieldTrace:
        base = dict(
            field="visual_rules.profile_id",
            module="visual_rules",
            skill_id="visual-style-distillation",
            asset_id="visual_profile_m5",
            version="1.0.0",
            rule_id="RULE_VISUAL_001",
            mode="asset",
        )
        base.update(overrides)
        return FieldTrace(**base)  # type: ignore[arg-type]

    def test_trace_keeps_its_field(self) -> None:
        self.assertEqual(self._trace().field, "visual_rules.profile_id")

    def test_trace_keeps_its_module(self) -> None:
        self.assertEqual(self._trace().module, "visual_rules")

    def test_trace_is_frozen(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            self._trace().skill_id = "other"  # type: ignore[misc]

    def test_skill_type_defaults_to_empty(self) -> None:
        self.assertEqual(self._trace().skill_type, "")

    def test_skill_type_is_recorded_when_present(self) -> None:
        self.assertEqual(self._trace(skill_type="distillation").skill_type,
                         "distillation")

    def test_asset_ref_defaults_to_none(self) -> None:
        self.assertIsNone(self._trace().asset_ref)

    def test_trace_serialises_its_required_keys(self) -> None:
        record = self._trace().as_dict()
        for key in ("field", "module", "skill_id", "asset_id", "version",
                    "rule_id", "mode"):
            self.assertIn(key, record)

    def test_trace_omits_skill_type_when_empty(self) -> None:
        self.assertNotIn("skill_type", self._trace().as_dict())

    def test_trace_includes_skill_type_when_set(self) -> None:
        self.assertIn("skill_type", self._trace(skill_type="distillation").as_dict())

    def test_trace_omits_the_asset_block_when_unresolved(self) -> None:
        self.assertNotIn("asset", self._trace().as_dict())

    def test_trace_includes_the_asset_block_when_resolved(self) -> None:
        ref = AssetReference(asset_id="visual_profile_m5", asset_type="visual_rules",
                             asset_status="available")
        self.assertIn("asset", self._trace(asset_ref=ref).as_dict())

    def test_trace_serialisation_is_json_safe(self) -> None:
        json.dumps(self._trace().as_dict())


class LoadedCapabilityTests(unittest.TestCase):
    """A capability record reports a state; it cannot change one."""

    def _capability(self, **overrides: object) -> LoadedCapability:
        base: dict[str, object] = dict(
            module="generation",
            state=CapabilityState.DECLARED,
            enabled=False,
            reason="generation_capability_not_available",
            skill_type="",
            skill_ids=(),
            asset_id="generation_capability",
            asset_status="unavailable",
        )
        base.update(overrides)
        return LoadedCapability(**base)  # type: ignore[arg-type]

    def test_capability_keeps_its_module(self) -> None:
        self.assertEqual(self._capability().module, "generation")

    def test_capability_keeps_its_state(self) -> None:
        self.assertEqual(self._capability().state, CapabilityState.DECLARED)

    def test_capability_keeps_a_disabled_flag(self) -> None:
        self.assertFalse(self._capability().enabled)

    def test_capability_is_frozen(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            self._capability().enabled = True  # type: ignore[misc]

    def test_capability_cannot_be_enabled_by_assignment(self) -> None:
        """The one write that would matter most is the one that must not work."""

        cap = self._capability()
        with self.assertRaises(FrozenInstanceError):
            cap.state = CapabilityState.AVAILABLE  # type: ignore[misc]

    def test_capability_serialises_its_state_as_a_plain_string(self) -> None:
        self.assertEqual(self._capability().as_dict()["state"], "declared")

    def test_capability_serialises_skill_ids_as_a_list(self) -> None:
        cap = self._capability(skill_ids=("s1", "s2"))
        self.assertEqual(cap.as_dict()["skill_ids"], ["s1", "s2"])

    def test_capability_serialisation_is_json_safe(self) -> None:
        json.dumps(self._capability().as_dict())


class InstanceProvenanceTests(unittest.TestCase):
    """Provenance separates factory identity, traces, records and references."""

    def _provenance(self, **overrides: object) -> InstanceProvenance:
        base: dict[str, object] = dict(
            kind=ProvenanceKind.MAPPED.value,
            generated_by="creator_mapping.mapper c0.4-a bundle=b1 rules=46",
            bundle_id="b1",
            factory_version="c0.4-a",
            mapping_version="c0.4-a",
            mapping_rule_count=46,
        )
        base.update(overrides)
        return InstanceProvenance(**base)  # type: ignore[arg-type]

    def test_provenance_is_frozen(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            self._provenance().bundle_id = "b2"  # type: ignore[misc]

    def test_mapped_is_true_for_a_mapped_kind(self) -> None:
        self.assertTrue(self._provenance().mapped)

    def test_mapped_is_false_for_a_projected_kind(self) -> None:
        self.assertFalse(
            self._provenance(kind=ProvenanceKind.PROJECTED.value).mapped
        )

    def test_trace_rejects_an_unknown_field(self) -> None:
        from creator_loader import InstanceProvenanceError

        with self.assertRaises(InstanceProvenanceError):
            self._provenance().trace("identity.nope")

    def test_trace_returns_a_known_field(self) -> None:
        trace = FieldTrace(field="identity.name", module="identity", skill_id="s",
                           asset_id="a", version="1.0.0", rule_id="r", mode="asset")
        provenance = self._provenance(field_traces={"identity.name": trace})
        self.assertEqual(provenance.trace("identity.name").skill_id, "s")

    def test_skills_are_sorted_and_unique(self) -> None:
        traces = {
            "identity.name": FieldTrace(field="identity.name", module="identity",
                                        skill_id="b", asset_id="a", version="1",
                                        rule_id="r", mode="asset"),
            "identity.tone": FieldTrace(field="identity.tone", module="identity",
                                        skill_id="a", asset_id="a", version="1",
                                        rule_id="r", mode="asset"),
        }
        self.assertEqual(self._provenance(field_traces=traces).skills(), ("a", "b"))

    def test_provenance_assets_are_sorted(self) -> None:
        refs = {
            "z": AssetReference(asset_id="z", asset_type="t", asset_status="s"),
            "a": AssetReference(asset_id="a", asset_type="t", asset_status="s"),
        }
        self.assertEqual(
            self._provenance(asset_references=refs).assets(), ("a", "z")
        )

    def test_provenance_wraps_its_mappings_on_construction(self) -> None:
        """Provenance is immutable however it was built, not only via the loader."""

        self.assertIsInstance(self._provenance().field_traces, MappingProxyType)

    def test_provenance_module_records_are_wrapped(self) -> None:
        provenance = self._provenance(module_records={"generation": {"a": 1}})
        self.assertIsInstance(provenance.module_records, MappingProxyType)

    def test_provenance_asset_references_are_wrapped(self) -> None:
        provenance = self._provenance(
            asset_references={
                "a": AssetReference(asset_id="a", asset_type="t", asset_status="s")
            }
        )
        self.assertIsInstance(provenance.asset_references, MappingProxyType)

    def test_provenance_mapping_cannot_be_written(self) -> None:
        with self.assertRaises(TypeError):
            self._provenance().field_traces["x"] = None  # type: ignore[index]

    def test_provenance_serialises_its_kind(self) -> None:
        self.assertEqual(self._provenance().as_dict()["kind"], "mapped")

    def test_provenance_serialisation_thaws_module_records(self) -> None:
        provenance = self._provenance(module_records={"generation": {"a": 1}})
        self.assertEqual(provenance.as_dict()["module_records"]["generation"],
                         {"a": 1})

    def test_provenance_serialisation_is_json_safe(self) -> None:
        json.dumps(self._provenance().as_dict())


class LoadedCreatorInstanceTests(unittest.TestCase):
    """The loaded object's accessor surface, exercised on a real artifact."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.loaded = load_creator_instance(fixtures.write_mapped("model_mapped"))

    def test_the_object_is_a_loaded_creator_instance(self) -> None:
        self.assertIsInstance(self.loaded, ModelClass)

    def test_it_is_frozen(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            self.loaded.instance_id = "other"  # type: ignore[misc]

    def test_creator_id_is_read_from_the_identity_module(self) -> None:
        self.assertEqual(self.loaded.creator_id, "finance_xhs")

    def test_domain_is_read_from_the_identity_module(self) -> None:
        self.assertEqual(self.loaded.domain, "finance")

    def test_platform_is_read_from_the_identity_module(self) -> None:
        self.assertEqual(self.loaded.platform, "xiaohongshu")

    def test_contract_version_is_read(self) -> None:
        self.assertEqual(self.loaded.contract_version, "1.0.0")

    def test_provenance_kind_and_kind_agree(self) -> None:
        self.assertEqual(self.loaded.kind, self.loaded.provenance_kind)

    def test_module_returns_a_mapping(self) -> None:
        from collections.abc import Mapping

        self.assertIsInstance(self.loaded.module("identity"), Mapping)

    def test_module_rejects_an_unknown_name(self) -> None:
        from creator_loader import InstanceModuleMissingError

        with self.assertRaises(InstanceModuleMissingError):
            self.loaded.module("nope")

    def test_get_reads_a_present_field(self) -> None:
        self.assertEqual(self.loaded.get("identity", "creator_id"), "finance_xhs")

    def test_get_returns_the_default_for_an_absent_field(self) -> None:
        self.assertIsNone(self.loaded.get("identity", "nope"))

    def test_get_returns_the_given_default(self) -> None:
        self.assertEqual(self.loaded.get("identity", "nope", "fallback"), "fallback")

    def test_get_returns_the_default_for_an_unknown_module(self) -> None:
        self.assertIsNone(self.loaded.get("nope", "field"))

    def test_field_reads_a_dotted_path(self) -> None:
        self.assertEqual(self.loaded.field("identity.creator_id"), "finance_xhs")

    def test_field_rejects_a_malformed_path(self) -> None:
        from creator_loader import InstanceFieldMissingError

        with self.assertRaises(InstanceFieldMissingError):
            self.loaded.field("identity")

    def test_field_rejects_an_absent_field(self) -> None:
        from creator_loader import InstanceFieldMissingError

        with self.assertRaises(InstanceFieldMissingError):
            self.loaded.field("identity.nope")

    def test_capability_returns_a_loaded_capability(self) -> None:
        self.assertIsInstance(self.loaded.capability("generation"), LoadedCapability)

    def test_capability_rejects_an_unknown_module(self) -> None:
        from creator_loader import InstanceCapabilityError

        with self.assertRaises(InstanceCapabilityError):
            self.loaded.capability("provenance")

    def test_capability_states_covers_every_module(self) -> None:
        self.assertEqual(len(self.loaded.capability_states()), 7)

    def test_as_dict_returns_a_mutable_mapping(self) -> None:
        self.assertIsInstance(self.loaded.as_dict(), dict)

    def test_as_dict_is_json_safe(self) -> None:
        json.dumps(self.loaded.as_dict())

    def test_as_dict_does_not_expose_a_mapping_proxy(self) -> None:
        self.assertNotIsInstance(self.loaded.as_dict()["modules"], MappingProxyType)

    def test_as_dict_can_be_mutated_without_touching_the_loaded_object(self) -> None:
        document = self.loaded.as_dict()
        document["instance_id"] = "tampered"
        self.assertEqual(self.loaded.instance_id, "finance_xhs")

    def test_mutating_a_thawed_module_does_not_touch_the_loaded_object(self) -> None:
        document = self.loaded.as_dict()
        document["modules"]["identity"]["creator_id"] = "tampered"
        self.assertEqual(self.loaded.creator_id, "finance_xhs")


class ImmutabilityTests(unittest.TestCase):
    """Immutability is proven, not asserted about a decorator."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.loaded = load_creator_instance(fixtures.write_mapped("immutable_mapped"))

    def test_assert_immutable_accepts_a_loaded_instance(self) -> None:
        assert_immutable(self.loaded)

    def test_modules_is_a_mapping_proxy(self) -> None:
        self.assertIsInstance(self.loaded.modules, MappingProxyType)

    def test_capabilities_is_a_mapping_proxy(self) -> None:
        self.assertIsInstance(self.loaded.capabilities, MappingProxyType)

    def test_asset_references_is_a_mapping_proxy(self) -> None:
        self.assertIsInstance(self.loaded.asset_references, MappingProxyType)

    def test_validation_is_a_mapping_proxy(self) -> None:
        self.assertIsInstance(self.loaded.validation, MappingProxyType)

    def test_raw_provenance_is_a_mapping_proxy(self) -> None:
        self.assertIsInstance(self.loaded.raw_provenance, MappingProxyType)

    def test_writing_to_modules_raises(self) -> None:
        with self.assertRaises(TypeError):
            self.loaded.modules["identity"] = {}  # type: ignore[index]

    def test_writing_to_capabilities_raises(self) -> None:
        with self.assertRaises(TypeError):
            self.loaded.capabilities["generation"] = None  # type: ignore[index]

    def test_writing_to_validation_raises(self) -> None:
        with self.assertRaises(TypeError):
            self.loaded.validation["schema"] = "FAIL"  # type: ignore[index]

    def test_writing_to_a_nested_module_raises(self) -> None:
        identity = self.loaded.module("identity")
        with self.assertRaises(TypeError):
            identity["creator_id"] = "tampered"  # type: ignore[index]

    def test_nested_module_mappings_are_proxies(self) -> None:
        generation = self.loaded.module("generation")
        self.assertIsInstance(generation, MappingProxyType)

    def test_nested_module_sequences_are_tuples(self) -> None:
        quality_gate = self.loaded.module("generation")["quality_gate"]
        self.assertIsInstance(quality_gate, MappingProxyType)

    def test_a_list_field_is_frozen_to_a_tuple(self) -> None:
        self.assertIsInstance(self.loaded.module("generation")["input"], tuple)

    def test_asset_reference_records_are_frozen(self) -> None:
        ref = self.loaded.asset_references["visual_profile_m5"]
        with self.assertRaises(FrozenInstanceError):
            ref.asset_id = "other"  # type: ignore[misc]

    def test_capability_records_are_frozen(self) -> None:
        cap = self.loaded.capability("generation")
        with self.assertRaises(FrozenInstanceError):
            cap.enabled = True  # type: ignore[misc]

    def test_provenance_field_traces_are_a_proxy(self) -> None:
        self.assertIsInstance(self.loaded.provenance.field_traces, MappingProxyType)

    def test_provenance_module_records_are_a_proxy(self) -> None:
        self.assertIsInstance(self.loaded.provenance.module_records, MappingProxyType)

    def test_provenance_asset_references_are_a_proxy(self) -> None:
        self.assertIsInstance(
            self.loaded.provenance.asset_references, MappingProxyType
        )

    def test_raw_provenance_is_frozen_at_depth(self) -> None:
        payload = self.loaded.raw_provenance["field_provenance"]
        self.assertIsInstance(payload, MappingProxyType)

    def test_assert_immutable_rejects_a_mutable_object(self) -> None:
        class Mutable:
            instance_id = "tampered"
            modules: dict[str, object] = {}

        with self.assertRaises(InstanceImmutableError):
            assert_immutable(Mutable())  # type: ignore[arg-type]

    def test_assert_immutable_rejects_a_plain_mapping_for_modules(self) -> None:
        class Partial:
            instance_id = "x"

            def __setattr__(self, name: str, value: object) -> None:
                raise AttributeError(name)

            modules: dict[str, object] = {}

        with self.assertRaises(InstanceImmutableError):
            assert_immutable(Partial())  # type: ignore[arg-type]

    def test_two_loads_of_one_artifact_are_equal(self) -> None:
        again = load_creator_instance(fixtures.write_mapped("immutable_mapped"))
        self.assertEqual(self.loaded.as_dict(), again.as_dict())


class PublicSurfaceTests(unittest.TestCase):
    """The package's declared surface is real, unique and importable."""

    def test_every_declared_name_exists(self) -> None:
        import creator_loader

        for name in creator_loader.__all__:
            self.assertTrue(hasattr(creator_loader, name), name)

    def test_every_declared_name_is_unique(self) -> None:
        import creator_loader

        self.assertEqual(
            len(creator_loader.__all__), len(set(creator_loader.__all__))
        )

    def test_the_surface_has_a_declared_order(self) -> None:
        """The list is written out, not derived, so its order can be checked."""

        import creator_loader

        source = Path(creator_loader.__file__).read_text(encoding="utf-8")
        block = source.partition("__all__ = [")[2].partition("]")[0]
        written = [
            line.strip().strip('",')
            for line in block.splitlines()
            if line.strip().startswith('"')
        ]
        self.assertEqual(written, list(creator_loader.__all__))

    def test_the_surface_is_grouped_constants_first(self) -> None:
        import creator_loader

        first = creator_loader.__all__[0]
        self.assertEqual(first, first.upper())

    def test_class_names_are_exported_alongside_their_modules(self) -> None:
        import creator_loader

        for name in ("LoadedCreatorInstance", "InstanceProvenance", "AssetReference",
                     "InstanceDiff", "CapabilityState", "ProvenanceKind"):
            self.assertIn(name, creator_loader.__all__)

    def test_the_surface_is_substantial(self) -> None:
        import creator_loader

        self.assertGreater(len(creator_loader.__all__), 60)

    def test_every_error_class_is_exported(self) -> None:
        import creator_loader
        from creator_loader import errors

        for name in errors.__all__:
            self.assertIn(name, creator_loader.__all__, name)

    def test_every_module_all_is_exported_at_package_level(self) -> None:
        """A module's public name that the package hides is a name nobody can reach."""

        import creator_loader
        from creator_loader import loader, model, provenance, resolver, validation

        missing: list[str] = []
        for module in (loader, model, provenance, resolver, validation):
            for name in getattr(module, "__all__", ()):
                if not name.startswith("_") and name not in creator_loader.__all__:
                    missing.append(f"{module.__name__}.{name}")
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
