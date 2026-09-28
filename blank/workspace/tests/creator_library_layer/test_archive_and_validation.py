"""The archive, structure, isolation and reproducibility checks."""

from __future__ import annotations

import json
import unittest

from creator_library import (
    ARCHIVE_FILENAME,
    CHECKSUMS_MEMBER,
    LIBRARY_DIR,
    MANIFEST_MEMBER,
    README_MEMBER,
    REGISTRY_MEMBER,
    SCHEMA_MEMBER,
    VERSION_MEMBER,
    LibraryArchiveError,
    LibraryChecksumError,
    LibraryCredentialError,
    LibraryIsolationError,
    LibraryLayerError,
    LibraryManifestError,
    LibraryPromptError,
    LibraryRegistryError,
    LibraryReproducibilityError,
    LibraryRuntimeError,
    LibrarySkillMissingError,
    LibraryStructureError,
    add_ledger,
    archive_names,
    artifact_digest,
    build_library,
    classify_member,
    describe_validation,
    expected_members,
    finalise,
    layer_of,
    member_sort_key,
    read_archive,
    skill_directory_of,
    summarise_members,
    validate_archive,
    validate_checksums,
    validate_isolation,
    validate_layers,
    validate_manifest_member,
    validate_registry,
    validate_reproducibility,
    validate_skills,
    validate_structure,
    verify_ledger,
    verify_library_hash,
    write_archive,
)

from . import fixtures


class ArchiveTests(unittest.TestCase):
    """The zip is deterministic, and reads back what it was given."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.build = fixtures.build()

    def test_the_filename_is_the_library_zip(self) -> None:
        self.assertEqual(ARCHIVE_FILENAME, "creator_skill_library.zip")

    def test_the_build_reports_that_filename(self) -> None:
        self.assertEqual(self.build.filename, ARCHIVE_FILENAME)

    def test_the_archive_is_a_zip(self) -> None:
        self.assertTrue(self.build.payload.startswith(b"PK"))

    def test_the_archive_reads_back(self) -> None:
        self.assertEqual(read_archive(self.build.payload), dict(self.build.members))

    def test_the_member_count_is_45(self) -> None:
        self.assertEqual(self.build.member_count, 45)

    def test_writing_the_same_members_twice_gives_the_same_bytes(self) -> None:
        first = write_archive(self.build.members)
        second = write_archive(self.build.members)
        self.assertEqual(first, second)

    def test_member_order_does_not_affect_the_bytes(self) -> None:
        reversed_members = dict(reversed(list(self.build.members.items())))
        self.assertEqual(
            write_archive(reversed_members), write_archive(self.build.members)
        )

    def test_the_archive_members_are_in_the_declared_order(self) -> None:
        """Root files first, then skills, then the registry and the schema."""

        names = archive_names(self.build.payload)
        ranks = [member_sort_key(n)[0] for n in names]
        self.assertEqual(ranks, sorted(ranks))

    def test_the_archive_order_matches_the_declared_sort(self) -> None:
        names = archive_names(self.build.payload)
        self.assertEqual(list(names), sorted(names, key=member_sort_key))

    def test_the_archive_starts_with_a_root_member(self) -> None:
        self.assertEqual(archive_names(self.build.payload)[0], README_MEMBER)

    def test_the_schema_is_written_last(self) -> None:
        self.assertEqual(archive_names(self.build.payload)[-1], SCHEMA_MEMBER)

    def test_the_registry_precedes_the_schema(self) -> None:
        names = archive_names(self.build.payload)
        self.assertLess(names.index(REGISTRY_MEMBER), names.index(SCHEMA_MEMBER))

    def test_reading_rubbish_is_reported(self) -> None:
        with self.assertRaises(LibraryArchiveError):
            read_archive(b"not a zip at all")

    def test_listing_rubbish_is_reported(self) -> None:
        with self.assertRaises(LibraryArchiveError):
            archive_names(b"not a zip at all")

    def test_the_artifact_digest_matches_the_payload(self) -> None:
        self.assertEqual(
            self.build.actual_artifact_hash, artifact_digest(self.build.payload)
        )

    def test_the_size_is_recorded(self) -> None:
        self.assertEqual(self.build.size_bytes, len(self.build.payload))

    def test_the_archive_carries_no_directory_entries(self) -> None:
        import io
        import zipfile

        with zipfile.ZipFile(io.BytesIO(self.build.payload)) as archive:
            for info in archive.infolist():
                self.assertFalse(info.is_dir(), info.filename)

    def test_every_entry_carries_the_zip_epoch(self) -> None:
        import io
        import zipfile

        with zipfile.ZipFile(io.BytesIO(self.build.payload)) as archive:
            for info in archive.infolist():
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0), info.filename)

    def test_the_archive_stores_entries_deflated(self) -> None:
        import io
        import zipfile

        with zipfile.ZipFile(io.BytesIO(self.build.payload)) as archive:
            for info in archive.infolist():
                self.assertEqual(info.compress_type, zipfile.ZIP_DEFLATED)


class LedgerTests(unittest.TestCase):
    """The checksum ledger describes the finished archive."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.build = fixtures.build()
        cls.ledger = fixtures.document(CHECKSUMS_MEMBER)

    def test_the_ledger_names_the_algorithm(self) -> None:
        self.assertEqual(self.ledger["algorithm"], "sha256")

    def test_the_ledger_counts_every_member(self) -> None:
        self.assertEqual(self.ledger["file_count"], self.build.member_count)

    def test_the_ledger_has_a_row_per_member(self) -> None:
        self.assertEqual(set(self.ledger["files"]), set(self.build.members))

    def test_the_ledger_has_no_extra_rows(self) -> None:
        self.assertEqual(set(self.ledger["files"]), set(self.build.members))

    def test_the_self_reference_is_the_ledger_itself(self) -> None:
        self.assertEqual(self.ledger["self_reference"], [CHECKSUMS_MEMBER])

    def test_the_ledger_record_its_own_row(self) -> None:
        self.assertIn(CHECKSUMS_MEMBER, self.ledger["files"])

    def test_the_ledger_row_for_itself_has_a_null_digest(self) -> None:
        self.assertIsNone(self.ledger["files"][CHECKSUMS_MEMBER]["sha256"])

    def test_the_ledger_row_for_itself_records_its_byte_count(self) -> None:
        self.assertEqual(
            self.ledger["files"][CHECKSUMS_MEMBER]["bytes"],
            len(fixtures.member(CHECKSUMS_MEMBER)),
        )

    def test_the_manifest_row_has_a_real_digest(self) -> None:
        """The manifest *can* be digested: a different hash covers the content."""

        self.assertIsNotNone(self.ledger["files"][MANIFEST_MEMBER]["sha256"])

    def test_the_excluded_list_is_recorded(self) -> None:
        self.assertEqual(
            self.ledger["excluded_from_package_hash"],
            ["manifest.json", "checksums.json"],
        )

    def test_every_other_row_has_a_digest(self) -> None:
        for path, row in self.ledger["files"].items():
            if path == CHECKSUMS_MEMBER:
                continue
            self.assertIsNotNone(row["sha256"], path)

    def test_verify_ledger_finds_no_mismatch(self) -> None:
        self.assertEqual(
            verify_ledger(self.build.members, self.ledger), ()
        )

    def test_verify_ledger_detects_a_changed_member(self) -> None:
        staged = fixtures.mutated(README_MEMBER, b"changed")
        mismatches = verify_ledger(staged, self.ledger)
        self.assertTrue(any(README_MEMBER in m for m in mismatches))

    def test_verify_ledger_detects_a_missing_row(self) -> None:
        broken = dict(self.ledger)
        broken["files"] = {
            k: v for k, v in self.ledger["files"].items() if k != README_MEMBER
        }
        mismatches = verify_ledger(self.build.members, broken)
        self.assertTrue(any(README_MEMBER in m for m in mismatches))

    def test_verify_ledger_refuses_a_ledger_without_files(self) -> None:
        with self.assertRaises(LibraryArchiveError):
            verify_ledger(self.build.members, {})

    def test_add_ledger_records_the_byte_count_exactly(self) -> None:
        staged, ledger = add_ledger({f"{LIBRARY_DIR}/x.json": b"{}"})
        payload = staged[CHECKSUMS_MEMBER]
        self.assertEqual(ledger["files"][CHECKSUMS_MEMBER]["bytes"], len(payload))

    def test_add_ledger_does_not_add_a_digest_for_itself(self) -> None:
        _staged, ledger = add_ledger({f"{LIBRARY_DIR}/x.json": b"{}"})
        self.assertIsNone(ledger["files"][CHECKSUMS_MEMBER]["sha256"])

    def test_finalise_does_not_add_the_ledger(self) -> None:
        """It is returned, not added: it has to describe the finished archive."""

        state = finalise({f"{LIBRARY_DIR}/x.json": b"{}"})
        self.assertNotIn(CHECKSUMS_MEMBER, state["members"])


class StructureTests(unittest.TestCase):
    """Every member is a library member, and the layout is complete."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.build = fixtures.build()

    def test_the_real_library_passes(self) -> None:
        validate_structure(self.build.members)

    def test_an_empty_archive_is_refused(self) -> None:
        with self.assertRaises(LibraryStructureError):
            validate_structure({})

    def test_the_expected_member_set_is_complete(self) -> None:
        expected = expected_members(
            {
                "universal": fixtures.universal_names(),
                "meta": fixtures.meta_names(),
            }
        )
        self.assertEqual(expected - set(self.build.members), set())

    def test_an_unknown_member_is_refused(self) -> None:
        staged = fixtures.mutated(f"{LIBRARY_DIR}/extra.txt", b"x")
        with self.assertRaises(LibraryStructureError):
            validate_structure(staged, skills={"universal": (), "meta": ()})

    def test_a_forbidden_directory_is_refused(self) -> None:
        staged = fixtures.mutated(
            f"{LIBRARY_DIR}/universal_skills/runtime/x.json", b"{}"
        )
        with self.assertRaises(LibraryStructureError):
            validate_structure(staged, skills={"universal": ("runtime",), "meta": ()})

    def test_a_forbidden_filename_is_refused(self) -> None:
        staged = fixtures.mutated(f"{LIBRARY_DIR}/.env", b"x")
        with self.assertRaises(LibraryStructureError):
            validate_structure(staged, skills={"universal": (), "meta": ()})

    def test_a_disallowed_suffix_is_refused(self) -> None:
        staged = fixtures.mutated(
            f"{LIBRARY_DIR}/universal_skills/x/notes.txt", b"x"
        )
        with self.assertRaises(LibraryStructureError):
            validate_structure(staged, skills={"universal": ("x",), "meta": ()})

    def test_a_missing_member_is_refused(self) -> None:
        staged = dict(self.build.members)
        del staged[README_MEMBER]
        with self.assertRaises(LibraryStructureError):
            validate_structure(
                staged,
                skills={
                    "universal": fixtures.universal_names(),
                    "meta": fixtures.meta_names(),
                },
            )

    def test_every_real_member_classifies(self) -> None:
        for member in self.build.members:
            self.assertNotEqual(classify_member(member), "unknown", member)

    def test_every_root_member_classifies_as_root(self) -> None:
        for member in (README_MEMBER, MANIFEST_MEMBER, CHECKSUMS_MEMBER,
                       VERSION_MEMBER):
            self.assertEqual(classify_member(member), "root", member)

    def test_the_registry_classifies_as_registry(self) -> None:
        self.assertEqual(classify_member(REGISTRY_MEMBER), "registry")

    def test_the_schema_classifies_as_schema(self) -> None:
        self.assertEqual(classify_member(SCHEMA_MEMBER), "schema")

    def test_a_skill_file_classifies_as_skill(self) -> None:
        self.assertEqual(
            classify_member(
                f"{LIBRARY_DIR}/universal_skills/text-distillation/SKILL.md"
            ),
            "skill",
        )

    def test_layer_of_finds_the_universal_layer(self) -> None:
        self.assertEqual(
            layer_of(f"{LIBRARY_DIR}/universal_skills/x/SKILL.md"), "universal"
        )

    def test_layer_of_finds_the_meta_layer(self) -> None:
        self.assertEqual(layer_of(f"{LIBRARY_DIR}/meta_skills/x/SKILL.md"), "meta")

    def test_layer_of_returns_empty_for_a_root_member(self) -> None:
        self.assertEqual(layer_of(README_MEMBER), "")

    def test_skill_directory_of_finds_a_skill(self) -> None:
        self.assertEqual(
            skill_directory_of(f"{LIBRARY_DIR}/meta_skills/x/skill.json"),
            f"{LIBRARY_DIR}/meta_skills/x",
        )

    def test_skill_directory_of_returns_empty_for_a_root_member(self) -> None:
        self.assertEqual(skill_directory_of(MANIFEST_MEMBER), "")

    def test_the_summary_counts_members(self) -> None:
        summary = summarise_members(dict(self.build.members))
        self.assertEqual(summary["member_count"], self.build.member_count)

    def test_the_summary_counts_skills(self) -> None:
        summary = summarise_members(dict(self.build.members))
        self.assertEqual(summary["by_kind"]["skill"], 39)

    def test_the_summary_counts_root_members(self) -> None:
        summary = summarise_members(dict(self.build.members))
        self.assertEqual(summary["by_kind"]["root"], 4)


class ManifestMemberTests(unittest.TestCase):
    """The manifest member is present, valid, and carries no forbidden key."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.build = fixtures.build()
        cls.manifest = validate_manifest_member(cls.build.members)

    def test_the_manifest_member_validates(self) -> None:
        self.assertEqual(self.manifest["library_id"], "creator_skill_library")

    def test_a_missing_manifest_is_refused(self) -> None:
        staged = dict(self.build.members)
        del staged[MANIFEST_MEMBER]
        with self.assertRaises(LibraryManifestError):
            validate_manifest_member(staged)

    def test_a_malformed_manifest_is_refused(self) -> None:
        staged = fixtures.mutated(MANIFEST_MEMBER, b"{not json")
        with self.assertRaises(LibraryManifestError):
            validate_manifest_member(staged)

    def test_a_non_object_manifest_is_refused(self) -> None:
        staged = fixtures.mutated(MANIFEST_MEMBER, b"[1, 2]")
        with self.assertRaises(LibraryManifestError):
            validate_manifest_member(staged)

    def test_a_nested_forbidden_key_is_refused(self) -> None:
        manifest = fixtures.document(MANIFEST_MEMBER)
        manifest["hashes"]["api_key"] = "x"
        staged = fixtures.mutated(
            MANIFEST_MEMBER, json.dumps(manifest).encode("utf-8")
        )
        with self.assertRaises(LibraryManifestError):
            validate_manifest_member(staged)

    def test_a_deeply_nested_forbidden_key_is_refused(self) -> None:
        manifest = fixtures.document(MANIFEST_MEMBER)
        manifest["skills"][0]["prompt"] = "x"
        staged = fixtures.mutated(
            MANIFEST_MEMBER, json.dumps(manifest).encode("utf-8")
        )
        with self.assertRaises(LibraryManifestError):
            validate_manifest_member(staged)


class SkillValidationTests(unittest.TestCase):
    """Every declared skill has its files, and they agree with the manifest."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.build = fixtures.build()
        cls.manifest = fixtures.document(MANIFEST_MEMBER)

    def test_the_real_library_passes(self) -> None:
        validate_skills(self.build.members, self.manifest)

    def test_a_missing_skill_file_is_refused(self) -> None:
        staged = dict(self.build.members)
        del staged[
            f"{LIBRARY_DIR}/universal_skills/text-distillation/SKILL.md"
        ]
        with self.assertRaises(LibrarySkillMissingError):
            validate_skills(staged, self.manifest)

    def test_every_skill_file_is_required(self) -> None:
        for filename in ("SKILL.md", "manifest.json", "skill.json"):
            staged = dict(self.build.members)
            del staged[f"{LIBRARY_DIR}/meta_skills/skill-composer/{filename}"]
            with self.assertRaises(LibrarySkillMissingError, msg=filename):
                validate_skills(staged, self.manifest)

    def test_an_undeclared_skill_directory_is_refused(self) -> None:
        staged = fixtures.mutated(
            f"{LIBRARY_DIR}/universal_skills/mystery/SKILL.md", b"x"
        )
        with self.assertRaises(LibrarySkillMissingError):
            validate_skills(staged, self.manifest)

    def test_a_misnamed_skill_manifest_is_refused(self) -> None:
        path = f"{LIBRARY_DIR}/universal_skills/text-distillation/manifest.json"
        document = fixtures.document(path)
        document["name"] = "other"
        staged = fixtures.mutated(path, json.dumps(document).encode("utf-8"))
        with self.assertRaises(LibrarySkillMissingError):
            validate_skills(staged, self.manifest)

    def test_a_wrong_layer_in_a_skill_manifest_is_refused(self) -> None:
        path = f"{LIBRARY_DIR}/universal_skills/text-distillation/manifest.json"
        document = fixtures.document(path)
        document["library_layer"] = "meta"
        staged = fixtures.mutated(path, json.dumps(document).encode("utf-8"))
        with self.assertRaises(LibrarySkillMissingError):
            validate_skills(staged, self.manifest)

    def test_a_wrong_version_in_a_skill_manifest_is_refused(self) -> None:
        path = f"{LIBRARY_DIR}/meta_skills/skill-composer/manifest.json"
        document = fixtures.document(path)
        document["version"] = "9.9.9"
        staged = fixtures.mutated(path, json.dumps(document).encode("utf-8"))
        with self.assertRaises(LibrarySkillMissingError):
            validate_skills(staged, self.manifest)


class LayerValidationTests(unittest.TestCase):
    """Check 4: the released layers are the library's layers, and are domain-free."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = fixtures.document(MANIFEST_MEMBER)

    def test_the_real_manifest_passes(self) -> None:
        validate_layers(self.manifest)

    def test_a_missing_universal_skill_is_allowed_for_a_subset(self) -> None:
        """A deliberate subset is drawn from the library; it need not be all of it."""

        manifest = json.loads(json.dumps(self.manifest))
        manifest["skills"] = [
            s for s in manifest["skills"]
            if s["name"] != "text-distillation"
        ]
        validate_layers(manifest)

    def test_a_missing_universal_skill_is_refused_when_completeness_is_required(self) -> None:
        manifest = json.loads(json.dumps(self.manifest))
        manifest["skills"] = [
            s for s in manifest["skills"]
            if s["name"] != "text-distillation"
        ]
        with self.assertRaises(LibraryLayerError):
            validate_layers(manifest, require_complete=True)

    def test_an_extra_universal_skill_is_refused(self) -> None:
        manifest = json.loads(json.dumps(self.manifest))
        manifest["skills"].append(
            {"name": "invented-skill", "library_layer": "universal"}
        )
        with self.assertRaises(LibraryLayerError):
            validate_layers(manifest)

    def test_a_missing_meta_skill_is_refused_when_completeness_is_required(self) -> None:
        manifest = json.loads(json.dumps(self.manifest))
        manifest["skills"] = [
            s for s in manifest["skills"] if s["name"] != "skill-composer"
        ]
        with self.assertRaises(LibraryLayerError):
            validate_layers(manifest, require_complete=True)

    def test_a_domain_vocabulary_in_a_universal_skill_is_refused(self) -> None:
        manifest = json.loads(json.dumps(self.manifest))
        for skill in manifest["skills"]:
            if skill["name"] == "text-distillation":
                skill["purpose"] = "Distill finance material into finance keywords."
        with self.assertRaises(LibraryLayerError):
            validate_layers(manifest)

    def test_the_real_universal_entries_are_domain_free(self) -> None:
        from creator_plugin_builder import DOMAIN_MARKERS

        for skill in self.manifest["skills"]:
            if skill["library_layer"] != "universal":
                continue
            blob = json.dumps(skill).lower()
            hits = sorted({m for m in DOMAIN_MARKERS if m in blob})
            self.assertEqual(hits, [], skill["name"])

    def test_no_released_universal_skill_has_domain_vocabulary_in_markdown(self) -> None:
        from creator_plugin_builder import DOMAIN_MARKERS

        for name in fixtures.universal_names():
            text = fixtures.text(
                f"{LIBRARY_DIR}/universal_skills/{name}/SKILL.md"
            ).lower()
            hits = sorted({m for m in DOMAIN_MARKERS if m in text})
            self.assertEqual(hits, [], name)


class IsolationValidationTests(unittest.TestCase):
    """Check 5: no runtime, no credential, no prompt."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.build = fixtures.build()

    def test_the_real_library_is_isolated(self) -> None:
        validate_isolation(self.build.members)

    def test_a_python_member_is_refused(self) -> None:
        staged = fixtures.mutated(
            f"{LIBRARY_DIR}/universal_skills/x/run.py", b"print('x')\n"
        )
        with self.assertRaises(LibraryRuntimeError):
            validate_isolation(staged)

    def test_a_shell_member_is_refused(self) -> None:
        staged = fixtures.mutated(f"{LIBRARY_DIR}/setup.sh", b"echo hi\n")
        with self.assertRaises(LibraryRuntimeError):
            validate_isolation(staged)

    def test_a_runtime_key_in_a_json_member_is_refused(self) -> None:
        staged = fixtures.mutated(
            f"{LIBRARY_DIR}/version.json", b'{"executor": "x"}'
        )
        with self.assertRaises(LibraryRuntimeError):
            validate_isolation(staged)

    def test_an_entrypoint_to_something_other_than_markdown_is_refused(self) -> None:
        staged = fixtures.mutated(
            f"{LIBRARY_DIR}/version.json", b'{"entrypoint": "run.py"}'
        )
        with self.assertRaises(LibraryRuntimeError):
            validate_isolation(staged)

    def test_a_prompt_key_is_refused(self) -> None:
        staged = fixtures.mutated(
            f"{LIBRARY_DIR}/version.json", b'{"prompt": "x"}'
        )
        with self.assertRaises(LibraryPromptError):
            validate_isolation(staged)

    def test_a_prompt_phrase_is_refused(self) -> None:
        staged = fixtures.mutated(
            f"{LIBRARY_DIR}/universal_skills/x/SKILL.md", b"you are a helpful expert"
        )
        with self.assertRaises(LibraryPromptError):
            validate_isolation(staged)

    def test_a_private_key_is_refused(self) -> None:
        staged = fixtures.mutated(
            f"{LIBRARY_DIR}/notes.md",
            b"-----BEGIN RSA " + b"PRIVATE KEY-----\nMIIabc\n",
        )
        with self.assertRaises(LibraryCredentialError):
            validate_isolation(staged)

    def test_an_openai_token_is_refused(self) -> None:
        staged = fixtures.mutated(
            f"{LIBRARY_DIR}/notes.md",
            b"key " + b"sk-" + b"AbCdEfGhIjKlMnOpQrStUvWx\n",
        )
        with self.assertRaises(LibraryCredentialError):
            validate_isolation(staged)

    def test_a_github_token_is_refused(self) -> None:
        staged = fixtures.mutated(
            f"{LIBRARY_DIR}/notes.md", b"ghp_" + b"A" * 24 + b"\n"
        )
        with self.assertRaises(LibraryCredentialError):
            validate_isolation(staged)

    def test_an_aws_key_is_refused(self) -> None:
        staged = fixtures.mutated(
            f"{LIBRARY_DIR}/notes.md", b"AKIA" + b"ABCDEFGHIJKLMNOP" + b"\n"
        )
        with self.assertRaises(LibraryCredentialError):
            validate_isolation(staged)

    def test_a_jwt_is_refused(self) -> None:
        staged = fixtures.mutated(
            f"{LIBRARY_DIR}/notes.md",
            b"eyJhbGciOiJIUzI1NiJ9"
            b".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
            b".dozjgNryP4J3jVmNHl0w5N\n",
        )
        with self.assertRaises(LibraryCredentialError):
            validate_isolation(staged)

    def test_a_real_secret_assignment_is_refused(self) -> None:
        staged = fixtures.mutated(
            f"{LIBRARY_DIR}/notes.md", b"api_key = a1b2c3d4e5f6g7h8i9j0\n"
        )
        with self.assertRaises(LibraryCredentialError):
            validate_isolation(staged)

    def test_an_assignment_to_prose_is_not_a_secret(self) -> None:
        """`api_key = set from the environment` names a key, not a value."""

        staged = fixtures.mutated(
            f"{LIBRARY_DIR}/notes.md",
            b"api_key = read from the environment at runtime\n",
        )
        validate_isolation(staged)

    def test_the_library_may_name_the_credentials_it_excludes(self) -> None:
        """A library must be able to say it carries none."""

        staged = fixtures.mutated(
            f"{LIBRARY_DIR}/notes.md",
            b"No credential, token or key is present.\napi_key is forbidden.\n",
        )
        validate_isolation(staged)

    def test_a_placeholder_value_is_not_a_secret(self) -> None:
        staged = fixtures.mutated(
            f"{LIBRARY_DIR}/notes.md", b"api_key = ${API_KEY_FROM_ENV}\n"
        )
        validate_isolation(staged)

    def test_a_skill_naming_a_forbidden_module_is_refused(self) -> None:
        staged = fixtures.mutated(
            f"{LIBRARY_DIR}/universal_skills/x/SKILL.md",
            b"this skill reads from workflows/\n",
        )
        with self.assertRaises(LibraryRuntimeError):
            validate_isolation(staged)

    def test_the_root_readme_may_name_the_modules_it_excludes(self) -> None:
        """The exclusion list names them; that is the library being honest."""

        staged = fixtures.mutated(
            README_MEMBER, b"no runtime, no workflows, no deployment\n"
        )
        validate_isolation(staged)


class ChecksumValidationTests(unittest.TestCase):
    """Check 6: the ledger agrees with the archive."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.build = fixtures.build()

    def test_the_real_ledger_passes(self) -> None:
        validate_checksums(self.build.members)

    def test_a_missing_ledger_is_refused(self) -> None:
        staged = dict(self.build.members)
        del staged[CHECKSUMS_MEMBER]
        with self.assertRaises(LibraryChecksumError):
            validate_checksums(staged)

    def test_a_malformed_ledger_is_refused(self) -> None:
        staged = fixtures.mutated(CHECKSUMS_MEMBER, b"{not json")
        with self.assertRaises(LibraryChecksumError):
            validate_checksums(staged)

    def test_a_changed_member_is_refused(self) -> None:
        staged = fixtures.mutated(README_MEMBER, b"changed after the ledger")
        with self.assertRaises(LibraryChecksumError):
            validate_checksums(staged)

    def test_a_wrong_file_count_is_refused(self) -> None:
        ledger = fixtures.document(CHECKSUMS_MEMBER)
        ledger["file_count"] = 999
        staged = fixtures.mutated(
            CHECKSUMS_MEMBER, json.dumps(ledger).encode("utf-8")
        )
        with self.assertRaises(LibraryChecksumError):
            validate_checksums(staged)


class ReproducibilityTests(unittest.TestCase):
    """Check 7: same input, same bytes."""

    def test_identical_payloads_pass(self) -> None:
        validate_reproducibility(b"abc", b"abc")

    def test_different_payloads_are_refused(self) -> None:
        with self.assertRaises(LibraryReproducibilityError):
            validate_reproducibility(b"abc", b"abd")

    def test_the_refusal_names_both_digests(self) -> None:
        try:
            validate_reproducibility(b"abc", b"abd")
        except LibraryReproducibilityError as exc:
            self.assertIn("first", exc.detail)
            self.assertIn("second", exc.detail)
        else:  # pragma: no cover
            self.fail("expected LibraryReproducibilityError")

    def test_two_builds_are_byte_identical(self) -> None:
        first = build_library()
        second = build_library()
        self.assertEqual(first.payload, second.payload)

    def test_two_builds_share_a_content_hash(self) -> None:
        first = build_library()
        second = build_library()
        self.assertEqual(first.content_hash, second.content_hash)

    def test_two_builds_share_an_artifact_hash(self) -> None:
        first = build_library()
        second = build_library()
        self.assertEqual(first.actual_artifact_hash, second.actual_artifact_hash)

    def test_a_different_version_changes_the_bytes(self) -> None:
        first = build_library(library_version="1.0.0")
        second = build_library(library_version="2.0.0")
        self.assertNotEqual(first.payload, second.payload)

    def test_a_different_version_changes_the_content_hash(self) -> None:
        first = build_library(library_version="1.0.0")
        second = build_library(library_version="3.0.0")
        self.assertNotEqual(first.content_hash, second.content_hash)


class RegistryValidationTests(unittest.TestCase):
    """Check 8: the published registry matches the builder's catalog."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.build = fixtures.build()

    def test_the_real_registry_passes(self) -> None:
        validate_registry(self.build.members, catalog_domains=self.build.domains)

    def test_a_missing_registry_is_refused(self) -> None:
        staged = dict(self.build.members)
        del staged[REGISTRY_MEMBER]
        with self.assertRaises(LibraryRegistryError):
            validate_registry(staged, catalog_domains=("finance",))

    def test_a_malformed_registry_is_refused(self) -> None:
        staged = fixtures.mutated(REGISTRY_MEMBER, b"{not json")
        with self.assertRaises(LibraryRegistryError):
            validate_registry(staged, catalog_domains=("finance",))

    def test_a_registry_missing_a_domain_is_refused(self) -> None:
        registry = fixtures.document(REGISTRY_MEMBER)
        registry["domains"] = [
            d for d in registry["domains"] if d["domain"] != "finance"
        ]
        staged = fixtures.mutated(
            REGISTRY_MEMBER, json.dumps(registry).encode("utf-8")
        )
        with self.assertRaises(LibraryRegistryError):
            validate_registry(staged, catalog_domains=("finance", "sports",
                                                      "technology"))

    def test_an_invented_domain_is_refused(self) -> None:
        registry = fixtures.document(REGISTRY_MEMBER)
        registry["domains"].append({"domain": "astrology", "plugin_name": "x"})
        staged = fixtures.mutated(
            REGISTRY_MEMBER, json.dumps(registry).encode("utf-8")
        )
        with self.assertRaises(LibraryRegistryError):
            validate_registry(staged, catalog_domains=("finance", "sports",
                                                      "technology"))

    def test_a_wrong_domain_count_is_refused(self) -> None:
        registry = fixtures.document(REGISTRY_MEMBER)
        registry["domain_count"] = 99
        staged = fixtures.mutated(
            REGISTRY_MEMBER, json.dumps(registry).encode("utf-8")
        )
        with self.assertRaises(LibraryRegistryError):
            validate_registry(staged, catalog_domains=("finance", "sports",
                                                      "technology"))


class CombinedValidationTests(unittest.TestCase):
    """The whole archive validates, and every check is reported."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.build = fixtures.build()
        cls.report = validate_archive(
            cls.build.payload, catalog_domains=cls.build.domains
        )

    def test_the_library_passes(self) -> None:
        self.assertTrue(self.report.passed, self.report.as_dict())

    def test_the_status_is_PASS(self) -> None:
        self.assertEqual(self.report.status, "PASS")

    def test_every_check_ran(self) -> None:
        self.assertEqual(
            sorted(self.report.checks),
            ["checksums", "isolation", "layers", "manifest", "registry",
             "reproducibility", "skills", "structure"],
        )

    def test_every_check_passed(self) -> None:
        for name, status in self.report.checks.items():
            self.assertEqual(status, "PASS", name)

    def test_the_report_names_the_version(self) -> None:
        self.assertEqual(self.report.library_version, "1.0.0")

    def test_the_report_serialises(self) -> None:
        json.dumps(self.report.as_dict())

    def test_validation_works_without_a_catalog(self) -> None:
        report = validate_archive(self.build.payload)
        self.assertNotIn("registry", report.checks)

    def test_the_content_hash_re_derives(self) -> None:
        self.assertTrue(
            verify_library_hash(self.build.members, self.build.manifest)
        )

    def test_the_content_hash_refuses_a_changed_member(self) -> None:
        staged = fixtures.mutated(README_MEMBER, b"changed")
        self.assertFalse(verify_library_hash(staged, self.build.manifest))

    def test_verify_library_hash_needs_a_recorded_hash(self) -> None:
        with self.assertRaises(LibraryManifestError):
            verify_library_hash(self.build.members, {"hashes": {}})

    def test_describe_validation_counts_the_members(self) -> None:
        document = describe_validation(self.build.members)
        self.assertEqual(
            document["members"]["member_count"], self.build.member_count
        )

    def test_describe_validation_lists_both_layers(self) -> None:
        document = describe_validation(self.build.members)
        self.assertEqual(
            sorted(document["skills_by_layer"]), ["meta", "universal"]
        )

    def test_describe_validation_finds_the_schema(self) -> None:
        self.assertTrue(
            describe_validation(self.build.members)["schema_present"]
        )

    def test_describe_validation_serialises(self) -> None:
        json.dumps(describe_validation(self.build.members))


if __name__ == "__main__":
    unittest.main()
