"""Skill schema: valid documents, invalid documents, forbidden fields."""

from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy

from creator_skill import (
    SKILL_TYPE_ORDER,
    SkillError,
    SkillSchemaError,
    build_schema,
    load_document,
    minimum_capabilities,
    schema_keys,
    validate_schema_document,
    write_schema,
)
from creator_skill.catalog import DEFAULT_SKILL_CATALOG, catalog_document


class SchemaDocumentTests(unittest.TestCase):
    """The generated schema is well-formed and declares the full surface."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = build_schema()

    def test_schema_is_an_object(self) -> None:
        self.assertIsInstance(self.schema, dict)

    def test_schema_is_sealed(self) -> None:
        self.assertIs(self.schema["additionalProperties"], False)

    def test_schema_declares_required_skill_fields(self) -> None:
        declared = set(self.schema["required"])
        for key in (
            "skill_id",
            "skill_type",
            "version",
            "description",
            "capabilities",
            "inputs",
            "outputs",
            "dependencies",
            "compatibility",
            "provenance",
            "status",
        ):
            self.assertIn(key, declared)

    def test_schema_enumerates_the_seven_skill_types(self) -> None:
        self.assertEqual(
            self.schema["properties"]["skill_type"]["enum"], list(SKILL_TYPE_ORDER)
        )

    def test_schema_has_no_unsupported_keywords(self) -> None:
        raw = json.dumps(self.schema)
        for unsupported in ('"$ref"', '"allOf"', '"oneOf"', '"if"'):
            self.assertNotIn(unsupported, raw)

    def test_schema_keys_match_properties(self) -> None:
        self.assertEqual(schema_keys(), frozenset(self.schema["properties"]))

    def test_capabilities_require_at_least_one_item(self) -> None:
        self.assertEqual(self.schema["properties"]["capabilities"]["minItems"], 1)

    def test_dependency_kind_is_an_enum(self) -> None:
        items = self.schema["properties"]["dependencies"]["items"]
        self.assertIn("enum", items["properties"]["kind"])

    def test_provenance_requires_a_source(self) -> None:
        required = self.schema["properties"]["provenance"]["required"]
        self.assertIn("source_kind", required)
        self.assertIn("source_ref", required)

    def test_write_schema_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_schema(f"{tmp}/creator_skill.schema.json")
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["title"], "CreatorSkill")

    def test_minimum_capabilities_cover_every_type(self) -> None:
        for skill_type in SKILL_TYPE_ORDER:
            self.assertGreaterEqual(minimum_capabilities(skill_type), 1)


class SchemaAcceptsValidDocumentsTests(unittest.TestCase):
    def test_catalog_wrapper_document_is_rejected(self) -> None:
        """The catalog *wrapper* is not a skill, so it must not validate as one."""

        with self.assertRaises(SkillSchemaError):
            validate_schema_document(catalog_document())

    def test_every_catalog_skill_is_schema_valid(self) -> None:
        for entry in DEFAULT_SKILL_CATALOG:
            with self.subTest(skill=entry["skill_id"]):
                validate_schema_document(entry)

    def test_load_document_reads_a_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/skill.json"
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(DEFAULT_SKILL_CATALOG[0], handle)
            payload = load_document(path)
            self.assertEqual(payload["skill_id"], DEFAULT_SKILL_CATALOG[0]["skill_id"])

    def test_load_document_on_a_missing_file(self) -> None:
        with self.assertRaises(SkillSchemaError):
            load_document("no/such/skill.json")

    def test_load_document_on_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/broken.json"
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{not json")
            with self.assertRaises(SkillSchemaError):
                load_document(path)

    def test_load_document_on_a_non_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/list.json"
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("[1, 2, 3]")
            with self.assertRaises(SkillSchemaError):
                load_document(path)


class SchemaRejectsInvalidDocumentsTests(unittest.TestCase):
    def _document(self) -> dict:
        return deepcopy(DEFAULT_SKILL_CATALOG[0])

    def test_missing_skill_id_is_rejected(self) -> None:
        document = self._document()
        del document["skill_id"]
        with self.assertRaises(SkillSchemaError):
            validate_schema_document(document)

    def test_missing_provenance_is_rejected(self) -> None:
        document = self._document()
        del document["provenance"]
        with self.assertRaises(SkillSchemaError):
            validate_schema_document(document)

    def test_missing_compatibility_is_rejected(self) -> None:
        document = self._document()
        del document["compatibility"]
        with self.assertRaises(SkillSchemaError):
            validate_schema_document(document)

    def test_unknown_skill_type_is_rejected(self) -> None:
        document = self._document()
        document["skill_type"] = "sorcery"
        with self.assertRaises(SkillSchemaError):
            validate_schema_document(document)

    def test_empty_capabilities_are_rejected(self) -> None:
        document = self._document()
        document["capabilities"] = []
        with self.assertRaises(SkillSchemaError):
            validate_schema_document(document)

    def test_unknown_status_is_rejected(self) -> None:
        document = self._document()
        document["status"] = "maybe"
        with self.assertRaises(SkillSchemaError):
            validate_schema_document(document)

    def test_unknown_dependency_kind_is_rejected(self) -> None:
        document = self._document()
        document["dependencies"] = [{"target": "x", "kind": "depend"}]  # type: ignore[list-item]
        with self.assertRaises(SkillSchemaError):
            validate_schema_document(document)

    def test_unknown_provenance_source_is_rejected(self) -> None:
        document = self._document()
        document["provenance"]["source_kind"] = "vibes"
        with self.assertRaises(SkillSchemaError):
            validate_schema_document(document)

    def test_capabilities_must_be_strings(self) -> None:
        document = self._document()
        document["capabilities"] = [1, 2]
        with self.assertRaises(SkillSchemaError):
            validate_schema_document(document)

    def test_confidence_must_be_numeric(self) -> None:
        document = self._document()
        document["provenance"]["confidence"] = "high"
        with self.assertRaises(SkillSchemaError):
            validate_schema_document(document)


class ForbiddenFieldTests(unittest.TestCase):
    """A skill is a capability declaration: these fields are rejected by shape."""

    FORBIDDEN = (
        "prompt",
        "prompts",
        "system_prompt",
        "negative_prompt",
        "template_prompt",
        "model",
        "model_call",
        "model_id",
        "api_key",
        "credentials",
        "endpoint",
        "webhook",
        "code",
        "script",
        "python",
        "entrypoint",
        "handler",
        "callback",
        "executor",
        "implementation",
    )

    def test_every_forbidden_field_is_rejected_by_the_schema(self) -> None:
        for field in self.FORBIDDEN:
            with self.subTest(field=field):
                document = deepcopy(DEFAULT_SKILL_CATALOG[0])
                document[field] = "anything"
                with self.assertRaises(SkillSchemaError):
                    validate_schema_document(document)

    def test_forbidden_field_inside_provenance_is_rejected(self) -> None:
        document = deepcopy(DEFAULT_SKILL_CATALOG[0])
        document["provenance"]["prompt"] = "x"
        with self.assertRaises(SkillSchemaError):
            validate_schema_document(document)

    def test_forbidden_field_inside_compatibility_is_rejected(self) -> None:
        document = deepcopy(DEFAULT_SKILL_CATALOG[0])
        document["compatibility"]["model"] = "gpt"
        with self.assertRaises(SkillSchemaError):
            validate_schema_document(document)


class DocumentBuilderErrorTests(unittest.TestCase):
    """Building a skill from a document rejects unknown keys rather than ignoring them."""

    def test_unknown_document_key_is_rejected(self) -> None:
        from creator_skill import skill_from_document

        document = deepcopy(DEFAULT_SKILL_CATALOG[0])
        document["mystery"] = "x"
        with self.assertRaises(SkillSchemaError):
            skill_from_document(document)

    def test_non_mapping_document_is_rejected(self) -> None:
        from creator_skill import skill_from_document

        with self.assertRaises(SkillError):
            skill_from_document(["not", "a", "mapping"])  # type: ignore[arg-type]

    def test_document_without_compatibility_is_rejected(self) -> None:
        from creator_skill import skill_from_document

        document = deepcopy(DEFAULT_SKILL_CATALOG[0])
        del document["compatibility"]
        with self.assertRaises(SkillSchemaError):
            skill_from_document(document)

    def test_document_without_provenance_is_rejected(self) -> None:
        from creator_skill import skill_from_document

        document = deepcopy(DEFAULT_SKILL_CATALOG[0])
        del document["provenance"]
        with self.assertRaises(SkillSchemaError):
            skill_from_document(document)

    def test_dependencies_must_be_a_sequence(self) -> None:
        from creator_skill import skill_from_document

        document = deepcopy(DEFAULT_SKILL_CATALOG[0])
        document["dependencies"] = "not-a-list"
        with self.assertRaises(SkillSchemaError):
            skill_from_document(document)

    def test_dependency_entries_must_be_mappings(self) -> None:
        from creator_skill import skill_from_document

        document = deepcopy(DEFAULT_SKILL_CATALOG[0])
        document["dependencies"] = ["nope"]
        with self.assertRaises(SkillError):
            skill_from_document(document)


if __name__ == "__main__":
    unittest.main()
