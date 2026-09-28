"""The thirteen standalone skill packages, and how they are validated.

A Shared Skill Library ingests skills one at a time, so the library archive is split
into thirteen uploadable units. These tests hold the split to the same rules the
library is held to, and pin the invariant that makes a split trustworthy: the
packages and the library are two representations of one thing and must not drift.
"""

from __future__ import annotations

import hashlib
import io
import json
import unittest
import zipfile

from creator_library import (
    FILENAME_PREFIX,
    FORBIDDEN_PACKAGE_KEYS,
    IDENTICAL_FILES,
    LIBRARY_FILE,
    PACKAGE_MANIFEST_KEYS,
    PACKAGE_SUFFIX,
    PACKAGE_ONLY_MANIFEST_KEYS,
    SHARED_FILES,
    STANDALONE_FILES,
    LibraryArchiveError,
    LibraryCredentialError,
    LibraryInputError,
    LibraryIsolationError,
    LibraryLayerError,
    LibraryManifestError,
    LibraryPromptError,
    LibraryRuntimeError,
    LibrarySkillMissingError,
    LibraryStructureError,
    SkillPackage,
    build_library,
    build_skill_package,
    build_skill_packages,
    checksum_index,
    describe_packages,
    package_filename,
    package_members,
    package_root,
    read_package,
    skill_layer,
    upload_index,
    validate_package,
    validate_package_isolation,
    validate_package_layer,
    validate_package_manifest,
    validate_package_matches_library,
    validate_package_structure,
    validate_packages,
    verify_package_bytes,
    write_skill_packages,
)
from creator_plugin_builder import META_SKILLS, UNIVERSAL_SKILLS

from . import fixtures


def _zip(members: dict[str, bytes]) -> bytes:
    """Repack members into a zip, for a test that needs a malformed package."""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, payload in sorted(members.items()):
            archive.writestr(path, payload)
    return buffer.getvalue()


class SplitTests(unittest.TestCase):
    """Thirteen packages, one per skill, covering both halves."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.packages = fixtures.packages()
        cls.library = fixtures.build()

    def test_there_are_thirteen_packages(self) -> None:
        self.assertEqual(len(self.packages), 13)

    def test_one_package_per_library_skill(self) -> None:
        self.assertEqual(
            sorted(p.name for p in self.packages),
            sorted(set(UNIVERSAL_SKILLS) | set(META_SKILLS)),
        )

    def test_ten_are_universal(self) -> None:
        self.assertEqual(
            sum(1 for p in self.packages if p.layer == "universal"), 10
        )

    def test_three_are_meta(self) -> None:
        self.assertEqual(sum(1 for p in self.packages if p.layer == "meta"), 3)

    def test_the_universal_set_is_the_librarys(self) -> None:
        self.assertEqual(
            sorted(p.name for p in self.packages if p.layer == "universal"),
            sorted(UNIVERSAL_SKILLS),
        )

    def test_the_meta_set_is_the_librarys(self) -> None:
        self.assertEqual(
            sorted(p.name for p in self.packages if p.layer == "meta"),
            sorted(META_SKILLS),
        )

    def test_every_filename_is_unique(self) -> None:
        names = [p.filename for p in self.packages]
        self.assertEqual(len(set(names)), len(names))

    def test_every_filename_carries_the_prefix(self) -> None:
        for p in self.packages:
            self.assertTrue(p.filename.startswith(FILENAME_PREFIX), p.name)

    def test_every_filename_carries_the_suffix(self) -> None:
        for p in self.packages:
            self.assertTrue(p.filename.endswith(PACKAGE_SUFFIX), p.name)

    def test_every_filename_names_its_skill(self) -> None:
        for p in self.packages:
            self.assertEqual(p.filename, f"{FILENAME_PREFIX}{p.name}{PACKAGE_SUFFIX}")

    def test_every_package_holds_four_members(self) -> None:
        for p in self.packages:
            self.assertEqual(p.member_count, 4, p.name)

    def test_every_package_holds_the_four_declared_files(self) -> None:
        for p in self.packages:
            self.assertEqual(
                sorted(read_package(p.payload)),
                sorted(package_members(p.name).values()),
                p.name,
            )

    def test_every_package_is_a_zip(self) -> None:
        for p in self.packages:
            self.assertTrue(p.payload.startswith(b"PK"), p.name)

    def test_every_package_root_is_the_skill_name(self) -> None:
        for p in self.packages:
            self.assertEqual(p.root, p.name, p.name)

    def test_no_package_nests_under_the_library_name(self) -> None:
        for p in self.packages:
            for member in read_package(p.payload):
                self.assertNotIn("creator_skill_library/", member, p.name)

    def test_the_packages_total_under_thirty_kilobytes(self) -> None:
        self.assertLess(sum(p.size_bytes for p in self.packages), 30_000)

    def test_an_unknown_skill_is_refused(self) -> None:
        with self.assertRaises(LibrarySkillMissingError):
            build_skill_package("not-a-skill")

    def test_an_empty_skill_name_is_refused(self) -> None:
        with self.assertRaises(LibraryInputError):
            build_skill_package("")

    def test_an_empty_version_is_refused(self) -> None:
        with self.assertRaises(LibraryInputError):
            build_skill_package("text-distillation", library_version="")

    def test_selecting_no_skills_is_refused(self) -> None:
        with self.assertRaises(LibraryInputError):
            build_skill_packages(universal=(), meta=())

    def test_a_subset_can_be_built(self) -> None:
        subset = build_skill_packages(universal=("text-distillation",), meta=())
        self.assertEqual(len(subset), 1)

    def test_the_split_is_deterministic(self) -> None:
        again = build_skill_packages()
        self.assertEqual(
            [p.payload for p in again], [p.payload for p in self.packages]
        )

    def test_every_package_is_reproducible_on_its_own(self) -> None:
        for p in self.packages:
            again = build_skill_package(p.name)
            self.assertEqual(again.payload, p.payload, p.name)

    def test_a_different_version_changes_every_package(self) -> None:
        other = build_skill_packages(library_version="2.0.0")
        mine = {p.name: p.payload for p in self.packages}
        for p in other:
            self.assertNotEqual(p.payload, mine[p.name], p.name)


class PackageLayoutTests(unittest.TestCase):
    """The four files, and the zip's own determinism."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.package = fixtures.package("text-distillation")
        cls.members = read_package(cls.package.payload)

    def test_the_skill_name_is_available(self) -> None:
        self.assertEqual(self.package.name, "text-distillation")

    def test_the_layer_is_available(self) -> None:
        self.assertEqual(self.package.layer, "universal")

    def test_the_version_is_available(self) -> None:
        self.assertEqual(self.package.version, "1.0.0")

    def test_the_four_files_are_declared(self) -> None:
        self.assertEqual(
            sorted(STANDALONE_FILES),
            ["SKILL.md", "library.json", "manifest.json", "skill.json"],
        )

    def test_the_markdown_is_present(self) -> None:
        self.assertIn(f"text-distillation/SKILL.md", self.members)

    def test_the_manifest_is_present(self) -> None:
        self.assertIn("text-distillation/manifest.json", self.members)

    def test_the_declaration_is_present(self) -> None:
        self.assertIn("text-distillation/skill.json", self.members)

    def test_the_library_metadata_is_present(self) -> None:
        self.assertIn("text-distillation/library.json", self.members)

    def test_the_markdown_opens_with_front_matter(self) -> None:
        self.assertTrue(self.package.skill_md.startswith("---\n"))

    def test_the_markdown_parses_with_the_project_parser(self) -> None:
        from creator_projection import parse_frontmatter

        parsed, body = parse_frontmatter(self.package.skill_md)
        self.assertEqual(parsed["name"], "text-distillation")
        self.assertTrue(body.strip())

    def test_the_markdown_names_the_layer(self) -> None:
        self.assertIn("library_layer: universal", self.package.skill_md)

    def test_the_entrypoint_file_is_written_first(self) -> None:
        with zipfile.ZipFile(io.BytesIO(self.package.payload)) as archive:
            self.assertEqual(
                archive.namelist()[0], "text-distillation/SKILL.md"
            )

    def test_every_entry_carries_the_zip_epoch(self) -> None:
        with zipfile.ZipFile(io.BytesIO(self.package.payload)) as archive:
            for info in archive.infolist():
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))

    def test_every_entry_is_deflated(self) -> None:
        with zipfile.ZipFile(io.BytesIO(self.package.payload)) as archive:
            for info in archive.infolist():
                self.assertEqual(info.compress_type, zipfile.ZIP_DEFLATED)

    def test_the_archive_carries_no_directory_entries(self) -> None:
        with zipfile.ZipFile(io.BytesIO(self.package.payload)) as archive:
            for info in archive.infolist():
                self.assertFalse(info.is_dir())

    def test_the_member_order_is_declared(self) -> None:
        with zipfile.ZipFile(io.BytesIO(self.package.payload)) as archive:
            self.assertEqual(
                archive.namelist(),
                [
                    "text-distillation/SKILL.md",
                    "text-distillation/manifest.json",
                    "text-distillation/skill.json",
                    "text-distillation/library.json",
                ],
            )

    def test_the_digest_is_a_hex_string(self) -> None:
        self.assertEqual(len(self.package.sha256), 64)

    def test_the_digest_matches_the_payload(self) -> None:
        self.assertEqual(
            self.package.sha256,
            hashlib.sha256(self.package.payload).hexdigest(),
        )

    def test_reading_rubbish_is_refused(self) -> None:
        with self.assertRaises(LibraryArchiveError):
            read_package(b"not a zip")

    def test_the_report_serialises(self) -> None:
        json.dumps(self.package.report())

    def test_the_package_serialises(self) -> None:
        json.dumps(self.package.as_dict())


class PackageManifestTests(unittest.TestCase):
    """The package manifest records what a lone reader needs."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.package = fixtures.package("domain-plugin-builder")
        cls.manifest = cls.package.manifest
        cls.members = read_package(cls.package.payload)

    def test_it_names_the_skill(self) -> None:
        self.assertEqual(self.manifest["name"], "domain-plugin-builder")

    def test_it_records_the_version(self) -> None:
        self.assertEqual(self.manifest["version"], "1.0.0")

    def test_it_records_the_layer(self) -> None:
        self.assertEqual(self.manifest["library_layer"], "meta")

    def test_it_records_the_library_version(self) -> None:
        self.assertEqual(self.manifest["library_version"], "1.0.0")

    def test_it_records_the_library_id(self) -> None:
        self.assertEqual(self.manifest["library_id"], "creator_skill_library")

    def test_it_records_its_own_filename(self) -> None:
        self.assertEqual(
            self.manifest["package_filename"], self.package.filename
        )

    def test_it_points_at_the_markdown_entrypoint(self) -> None:
        self.assertEqual(self.manifest["entrypoint"], "SKILL.md")

    def test_it_lists_capabilities(self) -> None:
        self.assertTrue(self.manifest["capabilities"])

    def test_it_states_what_it_produces(self) -> None:
        self.assertTrue(self.manifest["produces"])

    def test_it_carries_every_declared_key(self) -> None:
        for key in PACKAGE_MANIFEST_KEYS:
            self.assertIn(key, self.manifest, key)

    def test_it_carries_no_forbidden_key(self) -> None:
        for key in FORBIDDEN_PACKAGE_KEYS:
            self.assertNotIn(key, self.manifest, key)

    def test_it_carries_no_adapter_binding(self) -> None:
        self.assertNotIn("adapter", self.manifest)

    def test_it_carries_no_test_command(self) -> None:
        self.assertNotIn("test_command", self.manifest)

    def test_the_two_package_only_keys_are_the_expected_ones(self) -> None:
        self.assertEqual(
            sorted(PACKAGE_ONLY_MANIFEST_KEYS), ["library_id", "package_filename"]
        )

    def test_validation_accepts_it(self) -> None:
        validate_package_manifest(
            self.members, name=self.package.name, version=self.package.version
        )

    def test_a_wrong_version_is_refused(self) -> None:
        with self.assertRaises(LibraryManifestError):
            validate_package_manifest(
                self.members, name=self.package.name, version="9.9.9"
            )

    def test_a_wrong_name_is_refused(self) -> None:
        with self.assertRaises(LibraryManifestError):
            validate_package_manifest(
                self.members, name="other", version=self.package.version
            )

    def test_a_missing_manifest_is_refused(self) -> None:
        members = dict(self.members)
        del members[f"{self.package.name}/manifest.json"]
        with self.assertRaises(LibraryManifestError):
            validate_package_manifest(
                members, name=self.package.name, version=self.package.version
            )

    def test_a_malformed_manifest_is_refused(self) -> None:
        members = dict(self.members)
        members[f"{self.package.name}/manifest.json"] = b"{not json"
        with self.assertRaises(LibraryManifestError):
            validate_package_manifest(
                members, name=self.package.name, version=self.package.version
            )

    def test_a_forbidden_key_is_refused(self) -> None:
        members = dict(self.members)
        document = json.loads(members[f"{self.package.name}/manifest.json"])
        document["api_key"] = "x"
        members[f"{self.package.name}/manifest.json"] = json.dumps(document).encode()
        with self.assertRaises(LibraryManifestError):
            validate_package_manifest(
                members, name=self.package.name, version=self.package.version
            )

    def test_a_missing_capability_list_is_refused(self) -> None:
        members = dict(self.members)
        document = json.loads(members[f"{self.package.name}/manifest.json"])
        document["capabilities"] = []
        members[f"{self.package.name}/manifest.json"] = json.dumps(document).encode()
        with self.assertRaises(LibraryManifestError):
            validate_package_manifest(
                members, name=self.package.name, version=self.package.version
            )

    def test_a_layer_disagreement_with_skill_json_is_refused(self) -> None:
        members = dict(self.members)
        document = json.loads(members[f"{self.package.name}/manifest.json"])
        document["library_layer"] = "universal"
        members[f"{self.package.name}/manifest.json"] = json.dumps(document).encode()
        with self.assertRaises(LibraryManifestError):
            validate_package_manifest(
                members, name=self.package.name, version=self.package.version
            )

    def test_a_non_skill_md_entrypoint_is_refused(self) -> None:
        members = dict(self.members)
        document = json.loads(members[f"{self.package.name}/manifest.json"])
        document["entrypoint"] = "run.py"
        members[f"{self.package.name}/manifest.json"] = json.dumps(document).encode()
        with self.assertRaises(LibraryManifestError):
            validate_package_manifest(
                members, name=self.package.name, version=self.package.version
            )


class LibraryMetadataTests(unittest.TestCase):
    """``library.json`` gives a lone package its context back."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.package = fixtures.package("skill-composer")
        cls.meta = cls.package.library_metadata

    def test_it_records_the_library_id(self) -> None:
        self.assertEqual(self.meta["library_id"], "creator_skill_library")

    def test_it_records_the_library_version(self) -> None:
        self.assertEqual(self.meta["library_version"], "1.0.0")

    def test_it_records_the_format_version(self) -> None:
        self.assertEqual(self.meta["format_version"], "1.0.0")

    def test_it_records_the_generator(self) -> None:
        self.assertIn("creator_library", self.meta["generated_by"])

    def test_it_names_the_skill(self) -> None:
        self.assertEqual(self.meta["skill"], "skill-composer")

    def test_it_records_the_layer(self) -> None:
        self.assertEqual(self.meta["library_layer"], "meta")

    def test_it_records_the_library_counts(self) -> None:
        self.assertEqual(self.meta["universal_skill_count"], 10)
        self.assertEqual(self.meta["meta_skill_count"], 3)

    def test_it_lists_twelve_companions(self) -> None:
        self.assertEqual(len(self.meta["companions"]), 12)

    def test_it_omits_the_skill_itself(self) -> None:
        self.assertNotIn("skill-composer", self.meta["companions"])

    def test_it_flags_that_the_skill_is_packaged_alone(self) -> None:
        self.assertIs(self.meta["packaged_alone"], True)

    def test_it_explains_that_it_is_a_partition(self) -> None:
        self.assertIn("packaged alone for upload", self.meta["partition_note"])

    def test_it_names_the_whole_library_archive(self) -> None:
        self.assertIn("creator_skill_library.zip", self.meta["partition_note"])

    def test_it_serialises(self) -> None:
        json.dumps(self.meta)

    def test_every_package_carries_it(self) -> None:
        for p in fixtures.packages():
            self.assertEqual(p.library_metadata["skill"], p.name, p.name)


class PackageStructureTests(unittest.TestCase):
    """Check 1: the members are the four files, under the skill's own name."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.package = fixtures.package("quality-review")
        cls.members = read_package(cls.package.payload)

    def test_the_real_package_passes(self) -> None:
        validate_package_structure(self.members, name=self.package.name)

    def test_every_package_passes(self) -> None:
        for p in fixtures.packages():
            validate_package_structure(read_package(p.payload), name=p.name)

    def test_an_extra_member_is_refused(self) -> None:
        members = dict(self.members)
        members[f"{self.package.name}/extra.json"] = b"{}"
        with self.assertRaises(LibraryStructureError):
            validate_package_structure(members, name=self.package.name)

    def test_a_missing_member_is_refused(self) -> None:
        for filename in STANDALONE_FILES:
            members = dict(self.members)
            del members[f"{self.package.name}/{filename}"]
            with self.assertRaises(LibraryStructureError, msg=filename):
                validate_package_structure(members, name=self.package.name)

    def test_a_member_under_the_wrong_root_is_refused(self) -> None:
        members = dict(self.members)
        members["other/SKILL.md"] = members[f"{self.package.name}/SKILL.md"]
        del members[f"{self.package.name}/SKILL.md"]
        with self.assertRaises(LibraryStructureError):
            validate_package_structure(members, name=self.package.name)

    def test_a_nested_member_is_refused(self) -> None:
        members = dict(self.members)
        members[f"{self.package.name}/sub/extra.json"] = b"{}"
        with self.assertRaises(LibraryStructureError):
            validate_package_structure(members, name=self.package.name)


class PackageIsolationTests(unittest.TestCase):
    """Check 3: no runtime, no credential, no prompt."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.package = fixtures.package("risk-review")
        cls.members = read_package(cls.package.payload)

    def _with(self, filename: str, payload: bytes) -> dict[str, bytes]:
        members = dict(self.members)
        members[f"{self.package.name}/{filename}"] = payload
        return members

    def test_the_real_package_is_isolated(self) -> None:
        validate_package_isolation(self.members, name=self.package.name)

    def test_every_package_is_isolated(self) -> None:
        for p in fixtures.packages():
            validate_package_isolation(read_package(p.payload), name=p.name)

    def test_a_prompt_phrase_is_refused(self) -> None:
        with self.assertRaises(LibraryPromptError):
            validate_package_isolation(
                self._with("extra.md", b"you are a helpful expert"),
                name=self.package.name,
            )

    def test_a_prompt_key_is_refused(self) -> None:
        document = json.loads(self.members[f"{self.package.name}/skill.json"])
        document["prompt"] = "x"
        with self.assertRaises(LibraryPromptError):
            validate_package_isolation(
                self._with("skill.json", json.dumps(document).encode()),
                name=self.package.name,
            )

    def test_a_private_key_is_refused(self) -> None:
        with self.assertRaises(LibraryCredentialError):
            validate_package_isolation(
                self._with("extra.md", b"-----BEGIN RSA " + b"PRIVATE KEY-----\n"),
                name=self.package.name,
            )

    def test_an_openai_token_is_refused(self) -> None:
        with self.assertRaises(LibraryCredentialError):
            validate_package_isolation(
                self._with("extra.md", b"sk-" + b"AbCdEfGhIjKlMnOpQrStUvWx"),
                name=self.package.name,
            )

    def test_a_secret_assignment_is_refused(self) -> None:
        with self.assertRaises(LibraryCredentialError):
            validate_package_isolation(
                self._with("extra.md", b"api_key = a1b2c3d4e5f6g7h8i9j0"),
                name=self.package.name,
            )

    def test_an_assignment_to_prose_is_not_a_secret(self) -> None:
        validate_package_isolation(
            self._with("extra.md", b"api_key = read from the environment"),
            name=self.package.name,
        )

    def test_a_forbidden_module_reference_is_refused(self) -> None:
        with self.assertRaises(LibraryRuntimeError):
            validate_package_isolation(
                self._with("extra.md", b"reads from workflows/"),
                name=self.package.name,
            )

    def test_a_runtime_key_is_refused(self) -> None:
        document = json.loads(self.members[f"{self.package.name}/skill.json"])
        document["executor"] = "x"
        with self.assertRaises(LibraryRuntimeError):
            validate_package_isolation(
                self._with("skill.json", json.dumps(document).encode()),
                name=self.package.name,
            )

    def test_the_entrypoint_key_is_not_a_runtime_violation(self) -> None:
        """`entrypoint: SKILL.md` is this repository's own convention."""

        validate_package_isolation(self.members, name=self.package.name)

    def test_the_library_may_name_what_it_excludes(self) -> None:
        validate_package_isolation(
            self._with("extra.md", b"No credential, token or key is present."),
            name=self.package.name,
        )

    def test_non_utf8_content_is_refused(self) -> None:
        with self.assertRaises(LibraryRuntimeError):
            validate_package_isolation(
                self._with("extra.md", b"\xff\xfe\x00binary"),
                name=self.package.name,
            )


class PackageLayerTests(unittest.TestCase):
    """Check 4: a universal skill carries no domain knowledge."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.package = fixtures.package("source-discovery")
        cls.members = read_package(cls.package.payload)

    def test_the_real_universal_package_passes(self) -> None:
        validate_package_layer(self.members, name=self.package.name)

    def test_every_package_passes(self) -> None:
        for p in fixtures.packages():
            validate_package_layer(read_package(p.payload), name=p.name)

    def test_every_universal_package_is_domain_free(self) -> None:
        from creator_plugin_builder import DOMAIN_MARKERS

        for p in fixtures.packages():
            if p.layer != "universal":
                continue
            members = read_package(p.payload)
            for filename in STANDALONE_FILES:
                blob = members[f"{p.name}/{filename}"].decode("utf-8").lower()
                hits = sorted({m for m in DOMAIN_MARKERS if m in blob})
                self.assertEqual(hits, [], f"{p.name}/{filename}: {hits}")

    def test_a_domain_word_in_a_universal_package_is_refused(self) -> None:
        members = dict(self.members)
        members[f"{self.package.name}/skill.json"] = json.dumps(
            {"name": self.package.name, "library_layer": "universal",
             "purpose": "Find finance material."}
        ).encode()
        with self.assertRaises(LibraryLayerError):
            validate_package_layer(members, name=self.package.name)

    def test_a_wrong_layer_declaration_is_refused(self) -> None:
        members = dict(self.members)
        document = json.loads(members[f"{self.package.name}/manifest.json"])
        document["library_layer"] = "meta"
        members[f"{self.package.name}/manifest.json"] = json.dumps(document).encode()
        with self.assertRaises(LibraryLayerError):
            validate_package_layer(members, name=self.package.name)

    def test_the_meta_packages_are_not_domain_scanned(self) -> None:
        """A meta skill operates on plugins; it is not held to the marker scan."""

        meta = fixtures.package("domain-plugin-builder")
        validate_package_layer(read_package(meta.payload), name=meta.name)


class AgreementTests(unittest.TestCase):
    """Check 5: the packages and the library must not drift apart."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.library = fixtures.build()

    def test_every_package_agrees_with_the_library(self) -> None:
        for p in fixtures.packages():
            validate_package_matches_library(p, self.library)

    def test_the_two_identical_files_are_declared(self) -> None:
        self.assertEqual(sorted(IDENTICAL_FILES), ["SKILL.md", "skill.json"])

    def test_the_shared_files_are_declared(self) -> None:
        self.assertEqual(
            sorted(SHARED_FILES), ["SKILL.md", "manifest.json", "skill.json"]
        )

    def test_skill_markdown_is_byte_identical(self) -> None:
        from creator_library import skill_members

        for p in fixtures.packages():
            paths = skill_members(p.layer, p.name)
            ours = read_package(p.payload)[f"{p.name}/SKILL.md"]
            self.assertEqual(ours, self.library.members[paths["SKILL.md"]], p.name)

    def test_skill_json_is_byte_identical(self) -> None:
        from creator_library import skill_members

        for p in fixtures.packages():
            paths = skill_members(p.layer, p.name)
            ours = read_package(p.payload)[f"{p.name}/skill.json"]
            self.assertEqual(ours, self.library.members[paths["skill.json"]], p.name)

    def test_the_manifest_agrees_on_every_shared_key(self) -> None:
        from creator_library import skill_members

        for p in fixtures.packages():
            paths = skill_members(p.layer, p.name)
            theirs = json.loads(
                self.library.members[paths["manifest.json"]].decode("utf-8")
            )
            ours = p.manifest
            for key, value in theirs.items():
                self.assertEqual(ours.get(key), value, f"{p.name}.{key}")

    def test_the_package_manifest_adds_exactly_two_keys(self) -> None:
        from creator_library import skill_members

        for p in fixtures.packages():
            paths = skill_members(p.layer, p.name)
            theirs = set(
                json.loads(self.library.members[paths["manifest.json"]].decode("utf-8"))
            )
            extra = set(p.manifest) - theirs
            self.assertEqual(
                sorted(extra), sorted(PACKAGE_ONLY_MANIFEST_KEYS), p.name
            )

    def test_a_drifted_package_is_refused(self) -> None:
        from dataclasses import replace

        good = fixtures.package("text-distillation")
        members = dict(good.members)
        members[f"{good.name}/skill.json"] = b'{"name": "text-distillation"}'
        drifted = replace(good, members=members)
        with self.assertRaises(LibraryStructureError):
            validate_package_matches_library(drifted, self.library)


class ValidationReportTests(unittest.TestCase):
    """Each package validates on its own; the batch reports as one."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.packages = fixtures.packages()
        cls.library = fixtures.build()

    def test_every_package_passes(self) -> None:
        for p in self.packages:
            report = validate_package(p, library_build=self.library)
            self.assertTrue(report.passed, report.as_dict())

    def test_every_check_runs(self) -> None:
        report = validate_package(self.packages[0], library_build=self.library)
        self.assertEqual(
            sorted(report.checks),
            ["isolation", "layer", "library_agreement", "manifest", "structure"],
        )

    def test_validation_without_the_library_runs_four_checks(self) -> None:
        report = validate_package(self.packages[0])
        self.assertEqual(len(report.checks), 4)
        self.assertNotIn("library_agreement", report.checks)

    def test_the_report_names_the_skill(self) -> None:
        report = validate_package(self.packages[0])
        self.assertEqual(report.skill, self.packages[0].name)

    def test_the_report_names_the_filename(self) -> None:
        report = validate_package(self.packages[0])
        self.assertEqual(report.filename, self.packages[0].filename)

    def test_the_report_says_PASS(self) -> None:
        self.assertEqual(validate_package(self.packages[0]).status, "PASS")

    def test_the_report_serialises(self) -> None:
        json.dumps(validate_package(self.packages[0]).as_dict())

    def test_validate_packages_returns_one_report_each(self) -> None:
        reports = validate_packages(self.packages, library_build=self.library)
        self.assertEqual(len(reports), len(self.packages))

    def test_the_batch_preserves_order(self) -> None:
        reports = validate_packages(self.packages)
        self.assertEqual(
            [r.skill for r in reports], [p.name for p in self.packages]
        )

    def test_describe_packages_counts_them(self) -> None:
        document = describe_packages(self.packages, library_build=self.library)
        self.assertEqual(document["package_count"], 13)

    def test_describe_packages_reports_thirteen_passed(self) -> None:
        document = describe_packages(self.packages, library_build=self.library)
        self.assertEqual(document["passed"], 13)
        self.assertEqual(document["failed"], 0)

    def test_describe_packages_says_PASS(self) -> None:
        self.assertEqual(
            describe_packages(self.packages, library_build=self.library)["status"],
            "PASS",
        )

    def test_describe_packages_lists_the_checks(self) -> None:
        document = describe_packages(self.packages, library_build=self.library)
        self.assertEqual(
            document["checks"],
            ["isolation", "layer", "library_agreement", "manifest", "structure"],
        )

    def test_describe_packages_serialises(self) -> None:
        json.dumps(describe_packages(self.packages, library_build=self.library))

    def test_verify_package_bytes_accepts_a_real_package(self) -> None:
        for p in self.packages:
            verify_package_bytes(p.payload, name=p.name, version=p.version)

    def test_verify_package_bytes_refuses_a_broken_package(self) -> None:
        with self.assertRaises(LibraryArchiveError):
            verify_package_bytes(b"not a zip", name="x", version="1.0.0")

    def test_verify_package_bytes_refuses_a_structurally_wrong_package(self) -> None:
        members = dict(fixtures.package_members("text-distillation"))
        members["text-distillation/extra.json"] = b"{}"
        payload = _zip(members)
        with self.assertRaises(LibraryStructureError):
            verify_package_bytes(payload, name="text-distillation", version="1.0.0")


class IndexTests(unittest.TestCase):
    """The two index files a reviewer checks against."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.packages = fixtures.packages()
        cls.index = upload_index(cls.packages)
        cls.checksums = checksum_index(cls.packages)

    def test_the_index_counts_thirteen(self) -> None:
        self.assertEqual(self.index["package_count"], 13)

    def test_the_index_splits_the_layers(self) -> None:
        self.assertEqual(self.index["universal_skill_count"], 10)
        self.assertEqual(self.index["meta_skill_count"], 3)

    def test_the_index_totals_the_bytes(self) -> None:
        self.assertEqual(
            self.index["total_bytes"], sum(p.size_bytes for p in self.packages)
        )

    def test_the_index_names_the_prefix(self) -> None:
        self.assertEqual(self.index["filename_prefix"], FILENAME_PREFIX)

    def test_the_index_explains_why_it_is_split(self) -> None:
        self.assertIn("individually", self.index["purpose"])

    def test_every_index_entry_names_its_entrypoint(self) -> None:
        for entry in self.index["packages"]:
            self.assertEqual(entry["entrypoint"], f"{entry['root']}/SKILL.md")

    def test_every_index_entry_carries_a_digest(self) -> None:
        for entry in self.index["packages"]:
            self.assertEqual(len(entry["sha256"]), 64)

    def test_the_checksum_index_has_a_row_per_package(self) -> None:
        self.assertEqual(len(self.checksums["packages"]), 13)

    def test_the_checksum_rows_match_the_packages(self) -> None:
        for p in self.packages:
            row = self.checksums["packages"][p.filename]
            self.assertEqual(row["sha256"], p.sha256, p.name)
            self.assertEqual(row["bytes"], p.size_bytes, p.name)

    def test_the_checksum_index_names_the_algorithm(self) -> None:
        self.assertEqual(self.checksums["algorithm"], "sha256")

    def test_the_index_serialises(self) -> None:
        json.dumps(self.index)

    def test_the_checksums_serialise(self) -> None:
        json.dumps(self.checksums)


class WriteTests(unittest.TestCase):
    """Writing the thirteen packages plus the two indexes."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = fixtures.scratch_dir("packages_write")
        cls.written = write_skill_packages(fixtures.packages(), cls.root)

    def test_it_writes_fifteen_files(self) -> None:
        self.assertEqual(len(self.written), 15)

    def test_it_writes_thirteen_zips(self) -> None:
        self.assertEqual(len(list(self.root.glob("*.zip"))), 13)

    def test_it_writes_the_index(self) -> None:
        self.assertTrue((self.root / "INDEX.json").is_file())

    def test_it_writes_the_checksums(self) -> None:
        self.assertTrue((self.root / "CHECKSUMS.json").is_file())

    def test_every_written_file_exists(self) -> None:
        for path in self.written:
            self.assertTrue(path.is_file(), path.name)

    def test_the_written_bytes_match_the_packages(self) -> None:
        for p in fixtures.packages():
            self.assertEqual((self.root / p.filename).read_bytes(), p.payload, p.name)

    def test_the_ledger_on_disk_matches_the_packages(self) -> None:
        ledger = json.loads((self.root / "CHECKSUMS.json").read_text("utf-8"))
        for p in fixtures.packages():
            self.assertEqual(
                ledger["packages"][p.filename]["sha256"], p.sha256, p.name
            )

    def test_writing_is_deterministic(self) -> None:
        other = fixtures.scratch_dir("packages_write2")
        write_skill_packages(fixtures.packages(), other)
        for p in fixtures.packages():
            self.assertEqual(
                (other / p.filename).read_bytes(), (self.root / p.filename).read_bytes()
            )

    def test_writing_creates_the_directory(self) -> None:
        deep = fixtures.scratch_dir("packages_deep") / "a" / "b"
        write_skill_packages(fixtures.packages(), deep)
        self.assertTrue(deep.is_dir())


class PathHelperTests(unittest.TestCase):
    """The path helpers that make the flatter layout possible."""

    def test_a_package_root_is_the_skill_name(self) -> None:
        self.assertEqual(package_root("text-distillation"), "text-distillation")

    def test_a_package_root_rejects_a_path_traversal(self) -> None:
        from creator_library import LibraryPathError

        with self.assertRaises(LibraryPathError):
            package_root("../escape")

    def test_a_package_root_rejects_an_empty_name(self) -> None:
        from creator_library import LibraryPathError

        with self.assertRaises(LibraryPathError):
            package_root("")

    def test_the_filename_carries_the_prefix_and_suffix(self) -> None:
        self.assertEqual(
            package_filename("text-distillation", prefix="creator-"),
            "creator-text-distillation.zip",
        )

    def test_the_filename_defaults_to_no_prefix(self) -> None:
        self.assertEqual(package_filename("x"), "x.zip")

    def test_the_members_are_four(self) -> None:
        self.assertEqual(len(package_members("x")), 4)

    def test_the_members_sit_under_the_root(self) -> None:
        for path in package_members("x").values():
            self.assertTrue(path.startswith("x/"), path)

    def test_the_library_file_name_is_declared(self) -> None:
        self.assertEqual(LIBRARY_FILE, "library.json")

    def test_skill_layer_finds_the_universal_half(self) -> None:
        self.assertEqual(skill_layer("text-distillation"), "universal")

    def test_skill_layer_finds_the_meta_half(self) -> None:
        self.assertEqual(skill_layer("skill-composer"), "meta")

    def test_skill_layer_rejects_an_unknown_skill(self) -> None:
        with self.assertRaises(LibrarySkillMissingError):
            skill_layer("not-a-skill")


class SplitInvariantTests(unittest.TestCase):
    """The property that makes a split trustworthy, stated once, plainly."""

    def test_the_thirteen_cover_the_library_exactly(self) -> None:
        library = fixtures.build()
        packaged = {
            (p.layer, p.name) for p in fixtures.packages()
        }
        in_library = set()
        for layer, names in (
            ("universal", UNIVERSAL_SKILLS),
            ("meta", META_SKILLS),
        ):
            for name in names:
                in_library.add((layer, name))
        self.assertEqual(packaged, in_library)

    def test_the_library_carries_the_whole_split(self) -> None:
        library = fixtures.build()
        for p in fixtures.packages():
            prefix = (
                "creator_skill_library/universal_skills/"
                if p.layer == "universal"
                else "creator_skill_library/meta_skills/"
            )
            self.assertIn(f"{prefix}{p.name}/SKILL.md", library.members, p.name)

    def test_no_library_skill_is_left_unpackaged(self) -> None:
        library = fixtures.build()
        packaged = {p.name for p in fixtures.packages()}
        declared = {s["name"] for s in library.manifest["skills"]}
        self.assertEqual(packaged, declared)

    def test_the_split_changes_nothing_about_the_declarations(self) -> None:
        library = fixtures.build()
        for p in fixtures.packages():
            for skill in library.manifest["skills"]:
                if skill["name"] != p.name:
                    continue
                self.assertEqual(p.entry["purpose"], skill["purpose"], p.name)
                self.assertEqual(p.entry["produces"], skill["produces"], p.name)
                self.assertEqual(p.entry["capabilities"], skill["capabilities"], p.name)


if __name__ == "__main__":
    unittest.main()
