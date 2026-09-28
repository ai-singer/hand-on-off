"""Validation, negative cases, serialization, and factory-compatibility tests."""

from __future__ import annotations

import ast
import inspect
import json
import tempfile
import unittest
from pathlib import Path

from multimodal_creator.profile import (
    FORBIDDEN_KEYS,
    PROFILE_VERSION,
    PROVENANCE_FAMILIES,
    SCHEMA_FILENAME,
    YAML_FILENAME,
    FieldProvenance,
    ProfileError,
    SerializationError,
    ValidationError,
    assert_no_contradiction,
    assert_no_generation_logic,
    assert_no_universal_override,
    assert_provenance_complete,
    assert_rules_are_sourced,
    assert_slots_are_contiguous,
    factory_config,
    from_dict,
    from_json,
    parse_emitted_yaml,
    pattern_to_profile,
    read_json,
    to_json,
    to_yaml,
    validate_document,
    validate_profile,
    validation_summary,
    write_json,
    write_profile_bundle,
    write_schema,
    write_yaml,
)

from .test_profile_model_and_derivation import build_profile, m4_bundle


def profile_document():
    return build_profile().as_dict()


def _yaml_body(payload: str) -> str:
    """The emitted YAML with comment lines removed.

    The header legitimately states that the file contains "no prompt", so a
    substring search over the whole document would flag the disclaimer. Only the
    data lines describe the profile's contents.
    """

    return "\n".join(
        line for line in payload.splitlines() if not line.lstrip().startswith("#")
    )


class SchemaValidationTests(unittest.TestCase):
    def test_valid_profile_passes_schema(self) -> None:
        validate_profile(build_profile())

    def test_missing_required_field_is_rejected(self) -> None:
        document = profile_document()
        del document["visual_identity"]
        with self.assertRaises(ProfileError):
            validate_document(document)

    def test_unknown_top_level_field_is_rejected(self) -> None:
        document = profile_document()
        document["surprise"] = True
        with self.assertRaises(ProfileError):
            validate_document(document)

    def test_unknown_identity_field_is_rejected(self) -> None:
        document = profile_document()
        document["visual_identity"]["colour"] = "red"
        with self.assertRaises(ProfileError):
            validate_document(document)

    def test_invalid_visual_language_is_rejected(self) -> None:
        document = profile_document()
        document["visual_identity"]["visual_language"] = "vibes_first"
        with self.assertRaises(ProfileError):
            validate_document(document)

    def test_empty_source_patterns_are_rejected(self) -> None:
        document = profile_document()
        document["source_pattern_ids"] = []
        with self.assertRaises(ProfileError):
            validate_document(document)

    def test_wrong_profile_version_is_rejected(self) -> None:
        document = profile_document()
        document["profile_version"] = "m9.9.9"
        with self.assertRaises(ValidationError):
            validate_document(document)

    def test_schema_writes_to_disk(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = write_schema(Path(directory) / SCHEMA_FILENAME)
            self.assertTrue(path.is_file())
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["title"], "VisualCreatorProfile")

    def test_contiguity_is_enforced(self) -> None:
        document = profile_document()
        document["attention_strategy"] = {"first": "headline", "third": "cta"}
        with self.assertRaises(ValidationError):
            assert_slots_are_contiguous(document)

    def test_contiguous_slots_pass(self) -> None:
        assert_slots_are_contiguous({"attention_strategy": {"first": "a"}, "hierarchy_pattern": {"primary": "hook"}})


class ProvenanceValidationTests(unittest.TestCase):
    """Every family must carry a usable M4 source."""

    def test_provenance_is_complete(self) -> None:
        assert_provenance_complete(build_profile())

    def test_zero_confidence_provenance_is_rejected(self) -> None:
        profile = build_profile()
        broken = dict(profile.provenance)
        broken["constraints"] = FieldProvenance("M4", "p1", "kind", "direct", 0.0)
        rebuilt = type(profile)(
            profile_id=profile.profile_id,
            creator_id=profile.creator_id,
            version=profile.version,
            visual_identity=profile.visual_identity,
            composition_rules=profile.composition_rules,
            attention_strategy=profile.attention_strategy,
            hierarchy_pattern=profile.hierarchy_pattern,
            constraints=profile.constraints,
            provenance=broken,
            source_pattern_ids=profile.source_pattern_ids,
            support=profile.support,
            confidence=profile.confidence,
        )
        with self.assertRaises(ValidationError):
            assert_provenance_complete(rebuilt)

    def test_every_family_has_provenance(self) -> None:
        profile = build_profile()
        for family in PROVENANCE_FAMILIES:
            self.assertIn(family, profile.provenance)

    def test_provenance_names_an_m4_artifact(self) -> None:
        profile = build_profile()
        for family, record in profile.provenance.items():
            self.assertEqual(record.source_phase, "M4", family)
            self.assertTrue(record.artifact_id.strip(), family)

    def test_rules_trace_to_declared_sources(self) -> None:
        assert_rules_are_sourced(build_profile())

    def test_rules_without_a_declared_source_are_rejected(self) -> None:
        profile = build_profile()
        broken = dict(profile.provenance)
        broken["composition_rules"] = FieldProvenance(
            "M4", "some-other-pattern", "kind", "direct", 0.8
        )
        rebuilt = type(profile)(
            profile_id=profile.profile_id,
            creator_id=profile.creator_id,
            version=profile.version,
            visual_identity=profile.visual_identity,
            composition_rules=profile.composition_rules,
            attention_strategy=profile.attention_strategy,
            hierarchy_pattern=profile.hierarchy_pattern,
            constraints=profile.constraints,
            provenance=broken,
            source_pattern_ids=profile.source_pattern_ids,
            support=profile.support,
            confidence=profile.confidence,
        )
        with self.assertRaises(ValidationError):
            assert_rules_are_sourced(rebuilt)


class NegativeCaseTests(unittest.TestCase):
    """The three rejections the phase brief names, plus the contradictions."""

    # -- Case 1: hand-written rule with no M4 source ----------------------

    def test_hand_written_colour_rule_is_rejected(self) -> None:
        """``color: red`` with no M4 origin must not enter a profile."""

        document = profile_document()
        document["visual_identity"]["color"] = "red"
        with self.assertRaises(ProfileError):
            validate_document(document)

    def test_hand_written_top_level_rule_is_rejected(self) -> None:
        document = profile_document()
        document["rules"] = ["make it red"]
        with self.assertRaises(ProfileError):
            validate_document(document)

    def test_profile_without_source_patterns_is_rejected(self) -> None:
        document = profile_document()
        document["source_pattern_ids"] = []
        with self.assertRaises(ProfileError):
            validate_document(document)

    def test_unsourced_palette_key_is_rejected(self) -> None:
        document = profile_document()
        document["identity"] = {"palette": ["#ff0000"]}
        with self.assertRaises(ProfileError):
            validate_document(document)

    # -- Case 2: generation logic mixed in --------------------------------

    def test_prompt_key_is_rejected_by_name(self) -> None:
        """``prompt: make image`` must be reported by name, not by shape."""

        document = profile_document()
        document["prompt"] = "make image"
        with self.assertRaises(ValidationError) as context:
            assert_no_generation_logic(document)
        self.assertIn("prompt", str(context.exception))

    def test_nested_prompt_is_rejected(self) -> None:
        document = profile_document()
        document["visual_identity"]["prompt"] = "a red card"
        with self.assertRaises(ValidationError):
            assert_no_generation_logic(document)

    def test_prompt_inside_a_list_is_rejected(self) -> None:
        document = profile_document()
        document["composition_rules"]["preferred"] = [{"prompt": "x"}]
        with self.assertRaises(ValidationError):
            assert_no_generation_logic(document)

    def test_model_related_keys_are_rejected(self) -> None:
        for key in ("model", "model_id", "checkpoint", "lora", "sampler", "seed", "steps"):
            document = profile_document()
            document[key] = "x"
            with self.assertRaises(ValidationError, msg=key):
                assert_no_generation_logic(document)

    def test_image_and_asset_keys_are_rejected(self) -> None:
        for key in ("image", "image_data", "pixels", "bitmap", "base64", "asset_path"):
            document = profile_document()
            document[key] = "x"
            with self.assertRaises(ValidationError, msg=key):
                assert_no_generation_logic(document)

    def test_deployment_keys_are_rejected(self) -> None:
        for key in ("deploy", "publish", "endpoint", "webhook", "credentials", "api_key"):
            document = profile_document()
            document[key] = "x"
            with self.assertRaises(ValidationError, msg=key):
                assert_no_generation_logic(document)

    def test_generation_rejection_message_explains_scope(self) -> None:
        document = profile_document()
        document["prompt"] = "x"
        with self.assertRaises(ValidationError) as context:
            assert_no_generation_logic(document)
        self.assertIn("configuration only", str(context.exception))

    def test_forbidden_key_list_is_exposed(self) -> None:
        for key in ("prompt", "model", "renderer", "image", "deploy"):
            self.assertIn(key, FORBIDDEN_KEYS)

    def test_clean_document_has_no_forbidden_keys(self) -> None:
        assert_no_generation_logic(profile_document())

    # -- Case 3: creator-specific override of universal structure ---------

    def test_universal_vocabulary_redefinition_is_rejected(self) -> None:
        document = profile_document()
        document["region_role_vocabulary"] = ["earnings_banner"]
        with self.assertRaises(ValidationError) as context:
            assert_no_universal_override(document)
        self.assertIn("region_role_vocabulary", str(context.exception))

    def test_layout_class_redefinition_is_rejected(self) -> None:
        document = profile_document()
        document["layout_template_classes"] = ["my_layout"]
        with self.assertRaises(ValidationError):
            assert_no_universal_override(document)

    def test_relation_vocabulary_redefinition_is_rejected(self) -> None:
        document = profile_document()
        document["relation_types"] = ["my_relation"]
        with self.assertRaises(ValidationError):
            assert_no_universal_override(document)

    def test_meaning_definition_is_rejected(self) -> None:
        document = profile_document()
        document["visual_identity"]["means"] = "something else"
        with self.assertRaises(ValidationError):
            assert_no_universal_override(document)

    def test_layer_key_is_rejected(self) -> None:
        document = profile_document()
        document["layer"] = "plugin"
        with self.assertRaises(ValidationError):
            assert_no_universal_override(document)

    def test_clean_document_does_not_override(self) -> None:
        assert_no_universal_override(profile_document())

    # -- Contradictions ---------------------------------------------------

    def test_contradictory_rules_are_rejected(self) -> None:
        document = profile_document()
        document["composition_rules"]["forbidden"] = list(
            document["composition_rules"]["preferred"]
        )
        with self.assertRaises(ProfileError):
            from_dict(document)

    def test_contradictory_constraints_are_rejected(self) -> None:
        document = profile_document()
        document["constraints"]["must_have"] = ["clear_entry_point"]
        document["constraints"]["avoid"] = ["clear_entry_point"]
        with self.assertRaises(ProfileError):
            from_dict(document)

    def test_assert_no_contradiction_passes_on_a_valid_profile(self) -> None:
        assert_no_contradiction(build_profile())


class SerializationTests(unittest.TestCase):
    """Serialisation must round-trip exactly and stay traceable."""

    def test_json_round_trip(self) -> None:
        profile = build_profile()
        restored = from_json(to_json(profile))
        self.assertEqual(restored.as_dict(), profile.as_dict())

    def test_json_is_valid(self) -> None:
        payload = json.loads(to_json(build_profile()))
        self.assertEqual(payload["profile_version"], PROFILE_VERSION)

    def test_document_round_trip(self) -> None:
        profile = build_profile()
        restored = from_dict(profile.as_dict())
        self.assertEqual(restored.profile_id, profile.profile_id)

    def test_json_rejects_a_forbidden_key(self) -> None:
        payload = to_json(build_profile())
        broken = json.loads(payload)
        broken["prompt"] = "make image"
        with self.assertRaises(ValidationError):
            from_json(json.dumps(broken))

    def test_invalid_json_is_reported(self) -> None:
        with self.assertRaises(SerializationError):
            from_json("{not json")

    def test_write_and_read_json(self) -> None:
        profile = build_profile()
        with tempfile.TemporaryDirectory() as directory:
            path = write_json(profile, Path(directory) / "profile.json")
            restored = read_json(path)
            self.assertEqual(restored.as_dict(), profile.as_dict())

    def test_yaml_contains_every_rule_group(self) -> None:
        text = to_yaml(build_profile())
        for key in (
            "visual_profile:",
            "identity:",
            "composition:",
            "attention:",
            "hierarchy:",
            "constraints:",
            "provenance:",
        ):
            self.assertIn(key, text, key)

    def test_yaml_carries_provenance_per_group(self) -> None:
        """Provenance is emitted as a nested source block, not a flat key."""

        text = _yaml_body(to_yaml(build_profile()))
        self.assertIn("source:", text)
        self.assertIn("artifact:", text)
        self.assertIn("artifact_kind:", text)
        self.assertIn("derivation:", text)
        for family in PROVENANCE_FAMILIES:
            self.assertIn(f"  {family}:", text, family)

    def test_yaml_contains_no_generation_logic(self) -> None:
        """Check the emitted data, not the header comment describing its absence."""

        text = _yaml_body(to_yaml(build_profile())).lower()
        for forbidden in ("prompt", "renderer", "checkpoint", "base64", "deploy"):
            self.assertNotIn(forbidden, text, forbidden)

    def test_yaml_states_the_absence_of_generation_logic(self) -> None:
        text = to_yaml(build_profile())
        self.assertIn("no generation logic", text)

    def test_yaml_round_trips_through_the_subset_parser(self) -> None:
        profile = build_profile()
        parsed = parse_emitted_yaml(to_yaml(profile))
        self.assertEqual(parsed["visual_profile"]["profile_id"], profile.profile_id)
        self.assertEqual(parsed["identity"]["visual_language"], profile.visual_identity.visual_language)
        self.assertEqual(
            parsed["composition"]["preferred_layout"],
            list(profile.composition_rules.preferred),
        )
        self.assertEqual(parsed["attention"], dict(profile.attention_strategy.order))

    def test_yaml_quotes_scalars_so_types_cannot_drift(self) -> None:
        text = to_yaml(build_profile())
        self.assertIn('"', text)

    def test_write_and_read_yaml(self) -> None:
        profile = build_profile()
        with tempfile.TemporaryDirectory() as directory:
            path = write_yaml(profile, Path(directory) / YAML_FILENAME)
            self.assertTrue(path.is_file())
            self.assertIn("visual_profile:", path.read_text(encoding="utf-8"))

    def test_bundle_writes_both_files(self) -> None:
        profile = build_profile()
        with tempfile.TemporaryDirectory() as directory:
            written = write_profile_bundle(profile, directory)
            self.assertTrue(written.json_path.is_file())
            self.assertTrue(written.yaml_path.is_file())
            self.assertEqual(written.yaml_path.name, YAML_FILENAME)

    def test_yaml_parser_rejects_a_broken_line(self) -> None:
        with self.assertRaises(SerializationError):
            parse_emitted_yaml("this line has no colon\n")


class FactoryCompatibilityTests(unittest.TestCase):
    """Task 4: the profile must be usable as Creator Factory input."""

    def test_factory_config_has_every_section(self) -> None:
        config = factory_config(build_profile())
        for key in (
            "visual_profile",
            "identity",
            "composition",
            "attention",
            "hierarchy",
            "constraints",
            "provenance",
            "source_pattern_ids",
        ):
            self.assertIn(key, config, key)

    def test_factory_config_uses_the_brief_field_names(self) -> None:
        composition = factory_config(build_profile())["composition"]
        self.assertIn("preferred_layout", composition)
        self.assertIn("forbidden_layout", composition)

    def test_factory_config_constraints_use_the_brief_field_names(self) -> None:
        constraints = factory_config(build_profile())["constraints"]
        self.assertIn("must_have", constraints)
        self.assertIn("avoid", constraints)

    def test_factory_config_carries_a_confidence_floor(self) -> None:
        config = factory_config(build_profile())
        self.assertIn("confidence_floor", config["visual_profile"])

    def test_factory_config_attributes_every_rule(self) -> None:
        config = factory_config(build_profile())
        for record in config["provenance"].values():
            self.assertIn("source", record)
            self.assertEqual(record["source"]["phase"], "M4")

    def test_factory_config_has_no_forbidden_keys(self) -> None:
        raw = json.dumps(factory_config(build_profile())).lower()
        for forbidden in ('"prompt"', '"renderer"', '"base64"', '"deploy"'):
            self.assertNotIn(forbidden, raw)

    def test_factory_config_marks_its_generator(self) -> None:
        self.assertIn("multimodal_creator.profile", factory_config(build_profile())["generated_by"])

    def test_factory_config_is_json_serialisable(self) -> None:
        payload = json.dumps(factory_config(build_profile()))
        self.assertIn("visual_profile", payload)

    def test_model_refuses_a_profile_with_incomplete_provenance(self) -> None:
        """The model is the last line of defence before emission."""

        profile = build_profile()
        broken = dict(profile.provenance)
        broken.pop("constraints")
        with self.assertRaises(ProfileError):
            type(profile)(
                profile_id=profile.profile_id,
                creator_id=profile.creator_id,
                version=profile.version,
                visual_identity=profile.visual_identity,
                composition_rules=profile.composition_rules,
                attention_strategy=profile.attention_strategy,
                hierarchy_pattern=profile.hierarchy_pattern,
                constraints=profile.constraints,
                provenance=broken,
                source_pattern_ids=profile.source_pattern_ids,
                support=profile.support,
                confidence=profile.confidence,
            )


class ValidationSummaryTests(unittest.TestCase):
    def test_summary_reports_every_check(self) -> None:
        summary = validation_summary(build_profile())
        for name in (
            "schema",
            "provenance_complete",
            "rules_are_sourced",
            "no_contradiction",
            "no_generation_logic",
            "no_universal_override",
        ):
            self.assertIn(name, summary["checks"])
            self.assertTrue(summary["checks"][name], name)

    def test_summary_passes_for_a_valid_profile(self) -> None:
        self.assertTrue(validation_summary(build_profile())["passed"])

    def test_summary_lists_provenance_families(self) -> None:
        summary = validation_summary(build_profile())
        self.assertEqual(
            summary["provenance_families"], sorted(PROVENANCE_FAMILIES)
        )


class IsolationTests(unittest.TestCase):
    """Task 6: the profile layer is a config layer and reaches nothing else."""

    def _package_files(self):
        root = Path(__file__).resolve().parents[2] / "multimodal_creator" / "profile"
        return sorted(root.rglob("*.py"))

    def test_profile_package_exists(self) -> None:
        self.assertTrue(self._package_files())

    def test_no_runtime_or_engine_imports(self) -> None:
        forbidden = {
            "distillation_core",
            "workflows",
            "runtime",
            "production",
            "security",
            "artifact",
            "plugins",
            "risk_evaluation",
        }
        offenders: list[str] = []
        for path in self._package_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] in forbidden:
                            offenders.append(f"{path.name}:{alias.name}")
                elif isinstance(node, ast.ImportFrom) and node.module:
                    if node.module.split(".")[0] in forbidden:
                        offenders.append(f"{path.name}:{node.module}")
        self.assertEqual(offenders, [], f"forbidden imports: {offenders}")

    def test_no_generation_library_is_imported(self) -> None:
        forbidden = ("torch", "diffusers", "transformers", "openai", "requests", "urllib", "PIL")
        offenders: list[str] = []
        for path in self._package_files():
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                if f"import {token}" in text or f"from {token}" in text:
                    offenders.append(f"{path.name}:{token}")
        self.assertEqual(offenders, [], f"generation imports: {offenders}")

    def test_no_distillation_engine_reference(self) -> None:
        for path in self._package_files():
            self.assertNotIn(
                "DistillationEngine", path.read_text(encoding="utf-8"), str(path)
            )

    def test_no_existing_artifact_schema_is_written(self) -> None:
        """The profile schema is generated; existing schemas stay untouched."""

        for path in self._package_files():
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("unified_distillation_artifact.json", text, str(path))
            self.assertNotIn("multimodal_artifact.schema.json", text, str(path))

    def test_profile_layer_defines_no_generation_callable(self) -> None:
        offenders: list[str] = []
        for path in self._package_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    lowered = node.name.lower()
                    for token in ("generate", "render_image", "publish", "deploy", "upload"):
                        if token in lowered:
                            offenders.append(f"{path.name}:{node.name}")
        self.assertEqual(offenders, [], f"generation callables: {offenders}")

    def test_profile_files_are_only_the_declared_five_plus_init(self) -> None:
        names = sorted(path.name for path in self._package_files())
        self.assertEqual(
            names,
            [
                "__init__.py",
                "model.py",
                "pattern_to_profile.py",
                "schema.py",
                "serialization.py",
                "validation.py",
            ],
        )


if __name__ == "__main__":
    unittest.main()
