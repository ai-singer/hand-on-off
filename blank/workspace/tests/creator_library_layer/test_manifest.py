"""The release manifest, and the other library-root documents."""

from __future__ import annotations

import json
import unittest

from creator_library import (
    FORBIDDEN_MANIFEST_KEYS,
    INTEGRITY_RULE,
    LIBRARY_FORMAT_VERSION,
    LIBRARY_ID,
    MANIFEST_SCHEMA_VERSION,
    MANIFEST_MEMBER,
    REQUIRED_MANIFEST_KEYS,
    build_domain_registry,
    build_manifest,
    build_readme,
    build_schema_entry,
    build_version_document,
    standard_exclusions,
    validate_manifest,
)
from creator_library.errors import LibraryManifestError

from . import fixtures


def _all_keys(node: object) -> set[str]:
    """Every key in a document, at any depth."""

    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(str(key))
            found |= _all_keys(value)
    elif isinstance(node, list):
        for item in node:
            found |= _all_keys(item)
    return found


def a_manifest(**overrides: object) -> dict:
    """A minimal valid manifest, with overrides applied."""

    base: dict = {
        "library_version": "1.0.0",
        "skills": [
            {
                "name": "text-distillation",
                "library_layer": "universal",
                "version": "1.0.0",
            }
        ],
        "domain_plugins": {"domain_count": 1, "domains": []},
        "schemas": [],
        "content_hash": "a" * 64,
        "artifact_hash": "b" * 64,
        "member_summary": {"member_count": 1},
        "exclusions": [],
    }
    base.update(overrides)
    return build_manifest(**base)  # type: ignore[arg-type]


class ManifestBuildTests(unittest.TestCase):
    """The manifest is built from the archive's own facts."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = fixtures.document(MANIFEST_MEMBER)

    def test_the_library_id_is_the_declared_one(self) -> None:
        self.assertEqual(self.manifest["library_id"], LIBRARY_ID)

    def test_the_library_id_is_creator_skill_library(self) -> None:
        self.assertEqual(self.manifest["library_id"], "creator_skill_library")

    def test_the_version_is_recorded(self) -> None:
        self.assertEqual(self.manifest["library_version"], "1.0.0")

    def test_the_format_version_is_recorded(self) -> None:
        self.assertEqual(self.manifest["format_version"], LIBRARY_FORMAT_VERSION)

    def test_the_schema_version_is_recorded(self) -> None:
        self.assertEqual(
            self.manifest["manifest_schema_version"], MANIFEST_SCHEMA_VERSION
        )

    def test_the_builder_is_recorded(self) -> None:
        self.assertTrue(self.manifest["generated_by"])

    def test_the_builder_names_the_release_layer(self) -> None:
        self.assertIn("creator_library", self.manifest["generated_by"])

    def test_the_timestamp_is_deterministic(self) -> None:
        self.assertEqual(self.manifest["created_at"], "1970-01-01T00:00:00Z")

    def test_every_required_key_is_present(self) -> None:
        for key in REQUIRED_MANIFEST_KEYS:
            self.assertIn(key, self.manifest, key)

    def test_the_layers_block_names_both_layers(self) -> None:
        self.assertEqual(sorted(self.manifest["layers"]), ["meta", "universal"])

    def test_the_universal_layer_counts_ten(self) -> None:
        self.assertEqual(self.manifest["layers"]["universal"]["count"], 10)

    def test_the_meta_layer_counts_three(self) -> None:
        self.assertEqual(self.manifest["layers"]["meta"]["count"], 3)

    def test_every_layer_lists_its_skills(self) -> None:
        for layer in self.manifest["layers"].values():
            self.assertTrue(layer["skills"])

    def test_the_skill_list_covers_every_skill(self) -> None:
        self.assertEqual(len(self.manifest["skills"]), 13)

    def test_every_skill_names_its_layer(self) -> None:
        for skill in self.manifest["skills"]:
            self.assertIn(skill["library_layer"], ("universal", "meta"))

    def test_every_skill_names_its_entrypoint(self) -> None:
        for skill in self.manifest["skills"]:
            self.assertEqual(skill["entrypoint"], "SKILL.md")

    def test_every_skill_names_its_directory(self) -> None:
        for skill in self.manifest["skills"]:
            self.assertTrue(skill["directory"].endswith(skill["name"]))

    def test_the_domain_block_records_three_domains(self) -> None:
        self.assertEqual(self.manifest["domain_plugins"]["domain_count"], 3)

    def test_the_domain_block_lists_finance(self) -> None:
        domains = [d["domain"] for d in self.manifest["domain_plugins"]["domains"]]
        self.assertIn("finance", domains)

    def test_the_domain_block_says_plugins_are_generated_at_runtime(self) -> None:
        self.assertIs(
            self.manifest["domain_plugins"]["generated_at_runtime"], True
        )

    def test_the_schemas_block_names_the_domain_plugin_schema(self) -> None:
        self.assertEqual(self.manifest["schemas"][0]["name"], "domain_plugin")

    def test_the_hashes_block_names_the_algorithm(self) -> None:
        self.assertEqual(self.manifest["hashes"]["algorithm"], "sha256")

    def test_both_hashes_are_hex_digests(self) -> None:
        for key in ("content_hash", "artifact_hash"):
            self.assertEqual(len(self.manifest["hashes"][key]), 64, key)

    def test_the_integrity_rule_is_stated(self) -> None:
        self.assertEqual(self.manifest["integrity"]["rule"], INTEGRITY_RULE)

    def test_the_integrity_block_names_the_self_referential_members(self) -> None:
        self.assertEqual(
            sorted(self.manifest["integrity"]["self_reference"]),
            ["checksums.json", "manifest.json"],
        )

    def test_the_exclusions_are_recorded(self) -> None:
        self.assertTrue(self.manifest["exclusions"])

    def test_every_exclusion_states_what_and_why(self) -> None:
        for entry in self.manifest["exclusions"]:
            self.assertTrue(entry["absent"])
            self.assertTrue(entry["reason"])

    def test_the_exclusions_name_the_generated_plugins(self) -> None:
        absent = " ".join(entry["absent"] for entry in self.manifest["exclusions"])
        self.assertIn("generated domain plugins", absent)

    def test_the_manifest_serialises(self) -> None:
        json.dumps(self.manifest)

    def test_building_the_manifest_is_deterministic(self) -> None:
        again = fixtures.document(MANIFEST_MEMBER)
        self.assertEqual(again, self.manifest)


class ManifestForbiddenKeyTests(unittest.TestCase):
    """A library manifest must never carry a runtime, prompt or credential key."""

    def test_the_forbidden_list_covers_prompts(self) -> None:
        for key in ("prompt", "prompts", "system_prompt", "prompt_template"):
            self.assertIn(key, FORBIDDEN_MANIFEST_KEYS, key)

    def test_the_forbidden_list_covers_models(self) -> None:
        for key in ("model", "model_id", "provider"):
            self.assertIn(key, FORBIDDEN_MANIFEST_KEYS, key)

    def test_the_forbidden_list_covers_credentials(self) -> None:
        for key in ("api_key", "credentials", "secret", "token", "password",
                    "passwd", "private_key", "access_token"):
            self.assertIn(key, FORBIDDEN_MANIFEST_KEYS, key)

    def test_the_forbidden_list_covers_runtime(self) -> None:
        for key in ("runtime", "executor", "handler", "callback", "script"):
            self.assertIn(key, FORBIDDEN_MANIFEST_KEYS, key)

    def test_the_forbidden_list_covers_deployment(self) -> None:
        for key in ("deploy", "deployment", "endpoint", "webhook"):
            self.assertIn(key, FORBIDDEN_MANIFEST_KEYS, key)

    def test_the_real_manifest_carries_no_forbidden_key(self) -> None:
        manifest = fixtures.document(MANIFEST_MEMBER)
        for key in FORBIDDEN_MANIFEST_KEYS:
            self.assertNotIn(key, manifest, key)

    def test_the_real_manifest_carries_no_forbidden_key_anywhere(self) -> None:
        """Checked over the document's *keys*, at every depth.

        Not over its text: the manifest has to be able to say that it excludes a
        `test_command`, and that sentence puts the word in the file. The distinction
        is between carrying a key and naming one.
        """

        found = _all_keys(fixtures.document(MANIFEST_MEMBER))
        for key in FORBIDDEN_MANIFEST_KEYS:
            self.assertNotIn(key, found, key)

    def test_the_manifest_may_name_what_it_excludes(self) -> None:
        blob = json.dumps(fixtures.document(MANIFEST_MEMBER))
        self.assertIn("test_command", blob)


class ManifestValidationTests(unittest.TestCase):
    """The manifest refuses what it must."""

    def test_a_valid_manifest_passes(self) -> None:
        validate_manifest(a_manifest())

    def test_a_non_mapping_is_refused(self) -> None:
        with self.assertRaises(LibraryManifestError):
            validate_manifest(["not", "a", "manifest"])  # type: ignore[arg-type]

    def test_each_missing_key_is_refused(self) -> None:
        for key in REQUIRED_MANIFEST_KEYS:
            manifest = a_manifest()
            del manifest[key]
            with self.assertRaises(LibraryManifestError, msg=key):
                validate_manifest(manifest)

    def test_a_credential_key_is_refused(self) -> None:
        manifest = a_manifest()
        manifest["api_key"] = "x"
        with self.assertRaises(LibraryManifestError):
            validate_manifest(manifest)

    def test_a_prompt_key_is_refused(self) -> None:
        manifest = a_manifest()
        manifest["prompt"] = "x"
        with self.assertRaises(LibraryManifestError):
            validate_manifest(manifest)

    def test_a_runtime_key_is_refused(self) -> None:
        manifest = a_manifest()
        manifest["runtime"] = {}
        with self.assertRaises(LibraryManifestError):
            validate_manifest(manifest)

    def test_a_wrong_library_id_is_refused(self) -> None:
        manifest = a_manifest()
        manifest["library_id"] = "other_library"
        with self.assertRaises(LibraryManifestError):
            validate_manifest(manifest)

    def test_a_short_content_hash_is_refused(self) -> None:
        manifest = a_manifest()
        manifest["hashes"]["content_hash"] = "abc"
        with self.assertRaises(LibraryManifestError):
            validate_manifest(manifest)

    def test_a_short_artifact_hash_is_refused(self) -> None:
        manifest = a_manifest()
        manifest["hashes"]["artifact_hash"] = "abc"
        with self.assertRaises(LibraryManifestError):
            validate_manifest(manifest)

    def test_an_empty_skill_list_is_refused(self) -> None:
        with self.assertRaises(LibraryManifestError):
            a_manifest(skills=[])

    def test_no_version_is_refused(self) -> None:
        with self.assertRaises(LibraryManifestError):
            a_manifest(library_version="")

    def test_no_content_hash_is_refused(self) -> None:
        with self.assertRaises(LibraryManifestError):
            a_manifest(content_hash="")

    def test_no_artifact_hash_is_refused(self) -> None:
        with self.assertRaises(LibraryManifestError):
            a_manifest(artifact_hash="")

    def test_the_refusal_is_typed(self) -> None:
        try:
            a_manifest(skills=[])
        except LibraryManifestError as exc:
            self.assertEqual(exc.code, "LIBRARY_MANIFEST_INVALID")
        else:  # pragma: no cover
            self.fail("expected LibraryManifestError")


class VersionDocumentTests(unittest.TestCase):
    """``version.json`` records the format, the builder and the archive clock."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.document = fixtures.document(f"{fixtures.LIB}/version.json")

    def test_it_names_the_library(self) -> None:
        self.assertEqual(self.document["library_id"], LIBRARY_ID)

    def test_it_records_the_library_version(self) -> None:
        self.assertEqual(self.document["library_version"], "1.0.0")

    def test_it_records_the_format_version(self) -> None:
        self.assertEqual(self.document["format_version"], LIBRARY_FORMAT_VERSION)

    def test_it_records_the_builder_version(self) -> None:
        self.assertTrue(self.document["builder_version"])

    def test_it_records_the_archive_clock(self) -> None:
        self.assertEqual(self.document["archive_clock"], [1980, 1, 1, 0, 0, 0])

    def test_it_records_the_skill_count(self) -> None:
        self.assertEqual(self.document["counts"]["skills"], 13)

    def test_it_records_the_domain_count(self) -> None:
        self.assertEqual(self.document["counts"]["domain_plugins"], 3)

    def test_it_is_deterministic(self) -> None:
        again = build_version_document(
            library_version="1.0.0", skill_count=13, domain_count=3
        )
        self.assertEqual(again, self.document)

    def test_it_serialises(self) -> None:
        json.dumps(self.document)


class ReadmeTests(unittest.TestCase):
    """``LIBRARY.md`` says what the library is, and what it is not."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = fixtures.text(f"{fixtures.LIB}/LIBRARY.md")

    def test_it_opens_with_front_matter(self) -> None:
        self.assertTrue(self.text.startswith("---\n"))

    def test_the_front_matter_names_the_library(self) -> None:
        self.assertIn("name: creator_skill_library", self.text)

    def test_it_names_both_halves(self) -> None:
        self.assertIn("Universal Creator Skills", self.text)
        self.assertIn("Meta Skills", self.text)

    def test_it_lists_the_buildable_domains(self) -> None:
        self.assertIn("Buildable Domains", self.text)

    def test_it_names_finance(self) -> None:
        self.assertIn("finance", self.text)

    def test_it_states_plugins_are_not_shipped(self) -> None:
        self.assertIn("not** in this archive", self.text)

    def test_it_states_the_library_carries_no_runtime(self) -> None:
        self.assertIn("no runtime", self.text)

    def test_it_states_the_library_carries_no_prompt(self) -> None:
        self.assertIn("no prompt", self.text)

    def test_it_states_the_library_carries_no_credential(self) -> None:
        self.assertIn("no credential", self.text)

    def test_it_does_not_quote_a_digest(self) -> None:
        """A document cannot contain the hash of the archive that contains it."""

        self.assertNotIn("content hash:", self.text)

    def test_it_points_at_where_the_digests_live(self) -> None:
        self.assertIn("manifest.json", self.text)
        self.assertIn("checksums.json", self.text)

    def test_it_shows_the_layout(self) -> None:
        self.assertIn("universal_skills/<skill>", self.text)

    def test_it_describes_how_it_is_used(self) -> None:
        self.assertIn("Upload this library", self.text)

    def test_it_names_the_builder_skill(self) -> None:
        self.assertIn("domain-plugin-builder", self.text)

    def test_it_names_the_validator_skill(self) -> None:
        self.assertIn("domain-plugin-validator", self.text)

    def test_it_is_deterministic(self) -> None:
        again = build_readme(
            library_version="1.0.0",
            skills=fixtures.document(MANIFEST_MEMBER)["skills"],
            domain_plugins={"domains": fixtures.document(MANIFEST_MEMBER)[
                "domain_plugins"
            ]["domains"]},
        )
        self.assertTrue(again)


class DomainRegistryTests(unittest.TestCase):
    """``registry.json`` publishes which domains the library can build."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = fixtures.document(f"{fixtures.LIB}/domain_plugins/registry.json")

    def test_it_names_the_library(self) -> None:
        self.assertEqual(self.registry["library_id"], LIBRARY_ID)

    def test_it_records_the_library_version(self) -> None:
        self.assertEqual(self.registry["library_version"], "1.0.0")

    def test_it_records_the_catalog_version(self) -> None:
        self.assertTrue(self.registry["catalog_version"])

    def test_it_counts_three_domains(self) -> None:
        self.assertEqual(self.registry["domain_count"], 3)

    def test_the_count_matches_the_entries(self) -> None:
        self.assertEqual(len(self.registry["domains"]), self.registry["domain_count"])

    def test_every_domain_names_its_plugin(self) -> None:
        for entry in self.registry["domains"]:
            self.assertEqual(
                entry["plugin_name"], f"domain_{entry['domain']}_plugin"
            )

    def test_every_domain_is_marked_buildable(self) -> None:
        for entry in self.registry["domains"]:
            self.assertIs(entry["buildable"], True)

    def test_every_domain_lists_its_requirements(self) -> None:
        for entry in self.registry["domains"]:
            self.assertTrue(entry["requirements"])

    def test_every_domain_says_it_is_generated_at_runtime(self) -> None:
        for entry in self.registry["domains"]:
            self.assertIn("run time", entry["note"])

    def test_it_says_it_is_generated_at_runtime(self) -> None:
        self.assertIs(self.registry["generated_at_runtime"], True)

    def test_the_domains_are_sorted(self) -> None:
        names = [entry["domain"] for entry in self.registry["domains"]]
        self.assertEqual(names, sorted(names))

    def test_it_serialises(self) -> None:
        json.dumps(self.registry)

    def test_building_it_is_deterministic(self) -> None:
        again = build_domain_registry(
            catalog_version=self.registry["catalog_version"],
            entries=[
                {
                    "domain": entry["domain"],
                    "display_name": entry["display_name"],
                    "version": entry["version"],
                    "requirements": entry["requirements"],
                    "platforms": entry["platforms"],
                }
                for entry in self.registry["domains"]
            ],
            library_version="1.0.0",
        )
        self.assertEqual(again, self.registry)


class SchemaEntryTests(unittest.TestCase):
    """The manifest's schema entries point at real members."""

    def test_the_entry_names_the_schema(self) -> None:
        entry = build_schema_entry(
            name="domain_plugin", version="1.0.0", member="x", validates="y"
        )
        self.assertEqual(entry["name"], "domain_plugin")

    def test_the_entry_names_the_member(self) -> None:
        entry = build_schema_entry(
            name="n", version="v", member="m", validates="y"
        )
        self.assertEqual(entry["member"], "m")

    def test_the_entry_says_what_it_validates(self) -> None:
        entry = build_schema_entry(
            name="n", version="v", member="m", validates="a domain plugin"
        )
        self.assertIn("domain plugin", entry["validates"])

    def test_the_manifest_schema_member_exists(self) -> None:
        manifest = fixtures.document(MANIFEST_MEMBER)
        for entry in manifest["schemas"]:
            self.assertIn(entry["member"], fixtures.members(), entry["member"])


class ExclusionTests(unittest.TestCase):
    """Every exclusion is recorded with a reason."""

    def test_there_are_four_recorded_exclusions(self) -> None:
        self.assertEqual(len(standard_exclusions()), 4)

    def test_every_exclusion_has_both_fields(self) -> None:
        for entry in standard_exclusions():
            self.assertEqual(sorted(entry), ["absent", "reason"])

    def test_the_exclusions_name_the_plugins(self) -> None:
        absent = " ".join(e["absent"] for e in standard_exclusions())
        self.assertIn("generated domain plugins", absent)

    def test_the_exclusions_name_the_test_command(self) -> None:
        absent = " ".join(e["absent"] for e in standard_exclusions())
        self.assertIn("test_command", absent)

    def test_the_exclusions_are_deterministic(self) -> None:
        self.assertEqual(standard_exclusions(), standard_exclusions())


if __name__ == "__main__":
    unittest.main()
