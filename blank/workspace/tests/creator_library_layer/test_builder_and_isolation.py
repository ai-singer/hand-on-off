"""The builder, end to end, plus the release layer's own isolation.

This file proves the two things the others cannot:

1. **The chain completes.** Declarations → emitted skills → registry → schema →
   manifest → ledger → ``creator_skill_library.zip``, with nothing stubbed, and the
   finished archive re-validated from its own bytes.
2. **Nothing outside the package moved.** Frozen directories are digested before and
   after a build, so "the release layer only writes where it is told" is measured.
"""

from __future__ import annotations

import ast
import hashlib
import json
import unittest
import zipfile
from pathlib import Path

from creator_library import (
    ARCHIVE_FILENAME,
    CHECKSUMS_MEMBER,
    DEFAULT_LIBRARY_VERSION,
    LIBRARY_DIR,
    MANIFEST_MEMBER,
    README_MEMBER,
    REGISTRY_MEMBER,
    SCHEMA_MEMBER,
    VERSION_MEMBER,
    LibraryInputError,
    build_and_write,
    build_library,
    describe_library,
    member_listing,
    read_archive,
    verify_artifact,
    write_library,
)

from . import fixtures

WORKSPACE = Path(__file__).resolve().parents[2]

#: Directories that must remain byte-identical across a build.
FROZEN_DIRECTORIES: tuple[str, ...] = (
    "runtime",
    "production",
    "workflows",
    "risk_evaluation",
    "multimodal_creator",
    "distillation_core",
    "plugins",
)

#: Packages the release layer must never import.
FORBIDDEN_IMPORTS: tuple[str, ...] = FROZEN_DIRECTORIES + (
    "lobster",
    "subprocess",
    "socket",
    "urllib",
    "http",
    "requests",
    "openai",
    "anthropic",
    "yaml",
)


def imported_roots(path: Path) -> set[str]:
    """Every top-level module name one file imports."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    return found


class BuildTests(unittest.TestCase):
    """The build produces the artefact the phase is judged on."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.build = fixtures.build()

    def test_the_build_succeeds(self) -> None:
        self.assertEqual(self.build.library_version, "1.0.0")

    def test_the_default_version_is_the_format_version(self) -> None:
        self.assertEqual(DEFAULT_LIBRARY_VERSION, "1.0.0")

    def test_the_archive_is_named_creator_skill_library_zip(self) -> None:
        self.assertEqual(self.build.filename, "creator_skill_library.zip")

    def test_the_root_directory_is_creator_skill_library(self) -> None:
        self.assertEqual(LIBRARY_DIR, "creator_skill_library")

    def test_every_member_is_under_the_root(self) -> None:
        for member in self.build.members:
            self.assertTrue(member.startswith(LIBRARY_DIR + "/"), member)

    def test_the_archive_carries_45_members(self) -> None:
        self.assertEqual(self.build.member_count, 45)

    def test_the_four_root_members_are_present(self) -> None:
        for member in (README_MEMBER, MANIFEST_MEMBER, CHECKSUMS_MEMBER,
                       VERSION_MEMBER):
            self.assertIn(member, self.build.members, member)

    def test_the_registry_member_is_present(self) -> None:
        self.assertIn(REGISTRY_MEMBER, self.build.members)

    def test_the_schema_member_is_present(self) -> None:
        self.assertIn(SCHEMA_MEMBER, self.build.members)

    def test_the_schema_member_is_the_domain_plugin_schema(self) -> None:
        from creator_plugin_builder import build_schema

        self.assertEqual(
            fixtures.document(SCHEMA_MEMBER), build_schema()
        )

    def test_all_ten_universal_skills_are_released(self) -> None:
        self.assertEqual(len(self.build.universal_skill_names), 10)

    def test_all_three_meta_skills_are_released(self) -> None:
        self.assertEqual(len(self.build.meta_skill_names), 3)

    def test_the_universal_skills_are_the_librarys(self) -> None:
        self.assertEqual(
            self.build.universal_skill_names, fixtures.universal_names()
        )

    def test_the_meta_skills_are_the_librarys(self) -> None:
        self.assertEqual(self.build.meta_skill_names, fixtures.meta_names())

    def test_the_builder_domain_plugins_are_present_as_skills(self) -> None:
        self.assertIn("domain-plugin-builder", self.build.meta_skill_names)

    def test_the_validator_domain_plugins_are_present_as_skills(self) -> None:
        self.assertIn("domain-plugin-validator", self.build.meta_skill_names)

    def test_three_domains_are_published(self) -> None:
        self.assertEqual(
            self.build.domains, ("finance", "sports", "technology")
        )

    def test_no_generated_plugin_is_shipped(self) -> None:
        for member in self.build.members:
            self.assertNotIn("domain_finance_plugin", member)
            self.assertNotIn("domain_sports_plugin", member)

    def test_the_content_hash_is_64_hex(self) -> None:
        self.assertEqual(len(self.build.content_hash), 64)

    def test_the_artifact_hash_is_64_hex(self) -> None:
        self.assertEqual(len(self.build.actual_artifact_hash), 64)

    def test_the_content_hash_differs_from_the_artifact_hash(self) -> None:
        """One covers content, the other the file; they cannot coincide."""

        self.assertNotEqual(self.build.content_hash, self.build.actual_artifact_hash)

    def test_the_recorded_artifact_hash_is_advisory(self) -> None:
        """Recording a file's digest changes the file, so the two differ."""

        self.assertNotEqual(
            self.build.recorded_artifact_hash, self.build.actual_artifact_hash
        )

    def test_verify_artifact_reports_every_check(self) -> None:
        checks = verify_artifact(self.build)
        self.assertIn("content_hash", checks)
        self.assertIn("artifact_hash", checks)

    def test_verify_artifact_passes_the_content_hash(self) -> None:
        self.assertEqual(verify_artifact(self.build)["content_hash"], "PASS")

    def test_verify_artifact_marks_the_artifact_hash_advisory(self) -> None:
        self.assertEqual(verify_artifact(self.build)["artifact_hash"], "ADVISORY")

    def test_the_checksums_map_covers_every_member(self) -> None:
        self.assertEqual(set(self.build.checksums), set(self.build.members))

    def test_the_checksum_map_is_empty_for_the_ledger_itself(self) -> None:
        self.assertEqual(self.build.checksums[CHECKSUMS_MEMBER], "")

    def test_the_version_document_is_loaded(self) -> None:
        self.assertEqual(self.build.version_document["library_version"], "1.0.0")

    def test_the_registry_is_loaded(self) -> None:
        self.assertEqual(self.build.registry["domain_count"], 3)

    def test_the_report_names_the_file(self) -> None:
        self.assertEqual(describe_library(self.build)["filename"], ARCHIVE_FILENAME)

    def test_the_report_says_PASS(self) -> None:
        self.assertEqual(describe_library(self.build)["status"], "PASS")

    def test_the_report_lists_the_layers(self) -> None:
        report = describe_library(self.build)
        self.assertEqual(len(report["universal_skills"]), 10)
        self.assertEqual(len(report["meta_skills"]), 3)

    def test_the_report_serialises(self) -> None:
        json.dumps(describe_library(self.build))

    def test_the_build_document_serialises(self) -> None:
        json.dumps(self.build.as_dict())

    def test_a_bad_version_is_refused(self) -> None:
        with self.assertRaises(LibraryInputError):
            build_library(library_version="")

    def test_a_whitespace_version_is_refused(self) -> None:
        with self.assertRaises(LibraryInputError):
            build_library(library_version="   ")

    def test_a_non_string_version_is_refused(self) -> None:
        with self.assertRaises(LibraryInputError):
            build_library(library_version=None)  # type: ignore[arg-type]

    def test_a_release_can_carry_a_subset_of_skills(self) -> None:
        build = build_library(
            universal=("text-distillation",), meta=("skill-composer",)
        )
        self.assertEqual(build.universal_skill_names, ("text-distillation",))
        self.assertEqual(build.meta_skill_names, ("skill-composer",))
        self.assertEqual(build.member_count, 12)

    def test_a_release_cannot_carry_an_unknown_skill(self) -> None:
        from creator_library import LibrarySkillMissingError

        with self.assertRaises(LibrarySkillMissingError):
            build_library(universal=("not-a-skill",))

    def test_member_listing_matches_the_archive(self) -> None:
        self.assertEqual(
            member_listing(self.build), tuple(member_listing(self.build))
        )

    def test_the_member_listing_has_no_duplicates(self) -> None:
        names = member_listing(self.build)
        self.assertEqual(len(set(names)), len(names))


class WriteTests(unittest.TestCase):
    """Writing the archive to disk."""

    def test_writing_produces_the_zip(self) -> None:
        root = fixtures.scratch_dir("write")
        path = write_library(fixtures.build(), root)
        self.assertTrue(path.is_file())
        self.assertEqual(path.name, ARCHIVE_FILENAME)

    def test_the_written_bytes_match_the_build(self) -> None:
        root = fixtures.scratch_dir("write_bytes")
        build = fixtures.build()
        path = write_library(build, root)
        self.assertEqual(path.read_bytes(), build.payload)

    def test_the_written_zip_opens(self) -> None:
        root = fixtures.scratch_dir("write_open")
        path = write_library(fixtures.build(), root)
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(len(archive.infolist()), 45)

    def test_writing_is_deterministic(self) -> None:
        first = write_library(fixtures.build(), fixtures.scratch_dir("w1"))
        second = write_library(fixtures.build(), fixtures.scratch_dir("w2"))
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_writing_creates_the_directory(self) -> None:
        root = fixtures.scratch_dir("write_mkdir") / "deep" / "nested"
        write_library(fixtures.build(), root)
        self.assertTrue(root.is_dir())

    def test_a_custom_filename_is_honoured(self) -> None:
        root = fixtures.scratch_dir("write_custom")
        path = write_library(fixtures.build(), root, filename="other.zip")
        self.assertEqual(path.name, "other.zip")

    def test_build_and_write_returns_both(self) -> None:
        root = fixtures.scratch_dir("build_write")
        build, path = build_and_write(root)
        self.assertEqual(build.payload, path.read_bytes())

    def test_a_written_archive_revalidates(self) -> None:
        from creator_library import validate_archive

        root = fixtures.scratch_dir("write_revalidate")
        path = write_library(fixtures.build(), root)
        report = validate_archive(path.read_bytes())
        self.assertTrue(report.passed, report.as_dict())


class EndToEndTests(unittest.TestCase):
    """The whole production chain, from a request to a released library."""

    def test_a_domain_request_still_produces_a_plugin(self) -> None:
        """The library releases the builder; the builder still builds."""

        from creator_plugin_builder import DomainRequest, build_domain_plugin

        result = build_domain_plugin(DomainRequest(domain="finance"))
        self.assertTrue(result.passed)
        self.assertEqual(result.plugin.plugin_name, "domain_finance_plugin")

    def test_every_published_domain_still_builds(self) -> None:
        from creator_plugin_builder import DomainRequest, build_domain_plugin

        for domain in fixtures.build().domains:
            self.assertTrue(
                build_domain_plugin(DomainRequest(domain=domain)).passed, domain
            )

    def test_the_released_schema_validates_the_built_plugins(self) -> None:
        """The schema inside the archive is the one the plugins are checked against."""

        from creator_plugin_builder import DomainRequest, build_domain_plugin
        from creator_plugin_builder.schema import validate_schema_document

        schema = fixtures.document(SCHEMA_MEMBER)
        for domain in fixtures.build().domains:
            plugin = build_domain_plugin(DomainRequest(domain=domain)).plugin
            validate_schema_document(plugin.as_dict(), schema=schema)

    def test_the_released_registry_matches_the_live_catalog(self) -> None:
        from creator_plugin_builder import catalog_domains

        registry = fixtures.document(REGISTRY_MEMBER)
        self.assertEqual(
            {d["domain"] for d in registry["domains"]}, set(catalog_domains())
        )

    def test_the_whole_chain_hashes_the_same_twice(self) -> None:
        def run() -> str:
            build = build_library()
            return build.content_hash

        self.assertEqual(run(), run())

    def test_the_release_layer_does_not_import_the_builder_at_module_scope(self) -> None:
        """It reads the library's declarations; it does not run the builder."""

        text = (WORKSPACE / "creator_library" / "builder.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("build_domain_plugin(", text)

    def test_the_archive_carries_no_generated_plugin_document(self) -> None:
        members = read_archive(fixtures.build().payload)
        for member in members:
            self.assertNotIn(".plugin.json", member)


class PackageShapeTests(unittest.TestCase):
    """The release package is the modules it claims to be."""

    def test_every_declared_module_exists(self) -> None:
        for name in fixtures.PACKAGE_FILES:
            self.assertTrue((fixtures.PACKAGE / name).is_file(), name)

    def test_there_are_no_extra_modules(self) -> None:
        present = sorted(p.name for p in fixtures.PACKAGE.glob("*.py"))
        self.assertEqual(present, sorted(fixtures.PACKAGE_FILES))

    def test_the_package_has_no_subpackages(self) -> None:
        subpackages = [
            p.name
            for p in fixtures.PACKAGE.iterdir()
            if p.is_dir() and p.name != "__pycache__"
        ]
        self.assertEqual(subpackages, [])

    def test_every_module_declares_its_exports(self) -> None:
        for name in fixtures.PACKAGE_FILES:
            source = (fixtures.PACKAGE / name).read_text(encoding="utf-8")
            self.assertIn("__all__", source, name)

    def test_every_module_has_a_docstring(self) -> None:
        for name in fixtures.PACKAGE_FILES:
            tree = ast.parse((fixtures.PACKAGE / name).read_text(encoding="utf-8"))
            self.assertIsNotNone(ast.get_docstring(tree), name)

    def test_every_module_uses_future_annotations(self) -> None:
        for name in fixtures.PACKAGE_FILES:
            source = (fixtures.PACKAGE / name).read_text(encoding="utf-8")
            self.assertIn("from __future__ import annotations", source, name)


class ImportIsolationTests(unittest.TestCase):
    """The release layer imports nothing that could run, reach out or generate."""

    def test_no_module_imports_a_forbidden_package(self) -> None:
        offenders: list[str] = []
        for name in fixtures.PACKAGE_FILES:
            for module in imported_roots(fixtures.PACKAGE / name):
                if module in FORBIDDEN_IMPORTS:
                    offenders.append(f"{name} imports {module}")
        self.assertEqual(offenders, [])

    def test_no_module_imports_anything_outside_the_allowed_set(self) -> None:
        allowed = {
            "creator_contract",
            "creator_projection",
            "creator_package",
            "creator_plugin_builder",
            "creator_library",
            "core",
            "json",
            "re",
            "io",
            "hashlib",
            "shutil",
            "zipfile",
            "dataclasses",
            "enum",
            "pathlib",
            "typing",
            "collections",
            "__future__",
        }
        offenders: list[str] = []
        for name in fixtures.PACKAGE_FILES:
            for module in imported_roots(fixtures.PACKAGE / name):
                if module not in allowed:
                    offenders.append(f"{name} imports {module}")
        self.assertEqual(offenders, [])

    def test_the_package_imports_no_third_party_library(self) -> None:
        for name in fixtures.PACKAGE_FILES:
            for module in imported_roots(fixtures.PACKAGE / name):
                self.assertNotIn(
                    module, {"yaml", "numpy", "pandas", "requests"}, name
                )

    def test_no_module_calls_a_model(self) -> None:
        """Naming a token *shape* is not calling a model; importing a client is."""

        for name in fixtures.PACKAGE_FILES:
            text = (fixtures.PACKAGE / name).read_text(encoding="utf-8")
            for marker in (
                "import openai",
                "from openai",
                "openai.",
                "import anthropic",
                "from anthropic",
                "anthropic.",
                "chat.completions",
            ):
                self.assertNotIn(marker, text, f"{name}: {marker}")

    def test_no_module_opens_a_network_connection(self) -> None:
        for name in fixtures.PACKAGE_FILES:
            text = (fixtures.PACKAGE / name).read_text(encoding="utf-8")
            for marker in ("urllib", "requests.", "socket.", "http.client"):
                self.assertNotIn(marker, text, f"{name}: {marker}")

    def test_no_module_reaches_lobster(self) -> None:
        for name in fixtures.PACKAGE_FILES:
            text = (fixtures.PACKAGE / name).read_text(encoding="utf-8")
            for marker in ("import lobster", "from lobster", "LobsterClient"):
                self.assertNotIn(marker, text, f"{name}: {marker}")

    def test_no_module_deletes_an_artifact_field(self) -> None:
        """The one removal is dropping an optional key while *building* a document.

        Check 5 of the validator inspects a released skill document, so an absent
        optional key is a real distinction the emitter has to be able to make. What
        must never happen is a removal applied to an artifact that already exists.
        """

        offenders: list[str] = []
        for name in fixtures.PACKAGE_FILES:
            for number, line in enumerate(
                (fixtures.PACKAGE / name).read_text(encoding="utf-8").splitlines(), 1
            ):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if stripped.startswith("del "):
                    offenders.append(f"{name}:{number}: {stripped}")
                if ".pop(" in stripped and 'pop("accepts")' not in stripped:
                    offenders.append(f"{name}:{number}: {stripped}")
        self.assertEqual(offenders, [])

    def test_the_only_removal_is_the_optional_accepts_key(self) -> None:
        removals: list[str] = []
        for name in fixtures.PACKAGE_FILES:
            for number, line in enumerate(
                (fixtures.PACKAGE / name).read_text(encoding="utf-8").splitlines(), 1
            ):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if ".pop(" in line or stripped.startswith("del "):
                    removals.append(f"{name}:{number}: {stripped}")
        self.assertEqual(len(removals), 1)
        self.assertIn('pop("accepts")', removals[0])

    def test_no_absolute_path_in_the_package(self) -> None:
        for name in fixtures.PACKAGE_FILES:
            for line in (fixtures.PACKAGE / name).read_text(
                encoding="utf-8"
            ).splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for marker in ("C:\\", "/home/", "/Users/"):
                    self.assertNotIn(marker, line, f"{name}: {stripped}")

    def test_no_asset_path_literal_in_the_package(self) -> None:
        for name in fixtures.PACKAGE_FILES:
            for line in (fixtures.PACKAGE / name).read_text(
                encoding="utf-8"
            ).splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for marker in ("docs/", "assets.yaml", "visual_profile.yaml"):
                    self.assertNotIn(marker, line, f"{name}: {stripped}")


class FrozenDirectoryTests(unittest.TestCase):
    """A build changes nothing in the directories the programme protects."""

    def test_the_frozen_directories_exist(self) -> None:
        for name in FROZEN_DIRECTORIES:
            self.assertTrue((WORKSPACE / name).is_dir(), name)

    def test_building_does_not_modify_a_frozen_directory(self) -> None:
        before = {n: fixtures.digest_tree(WORKSPACE / n) for n in FROZEN_DIRECTORIES}
        build_library()
        after = {n: fixtures.digest_tree(WORKSPACE / n) for n in FROZEN_DIRECTORIES}
        self.assertEqual(before, after)

    def test_building_does_not_modify_the_package(self) -> None:
        before = fixtures.digest_tree(fixtures.PACKAGE)
        build_library()
        self.assertEqual(fixtures.digest_tree(fixtures.PACKAGE), before)

    def test_building_does_not_modify_the_plugin_builder_package(self) -> None:
        target = WORKSPACE / "creator_plugin_builder"
        before = fixtures.digest_tree(target)
        build_library()
        self.assertEqual(fixtures.digest_tree(target), before)

    def test_building_does_not_modify_the_package_layer(self) -> None:
        target = WORKSPACE / "creator_package"
        before = fixtures.digest_tree(target)
        build_library()
        self.assertEqual(fixtures.digest_tree(target), before)

    def test_building_does_not_modify_the_contract_package(self) -> None:
        target = WORKSPACE / "creator_contract"
        before = fixtures.digest_tree(target)
        build_library()
        self.assertEqual(fixtures.digest_tree(target), before)

    def test_building_writes_no_file(self) -> None:
        """Building returns bytes; only writing writes."""

        target = WORKSPACE / "creator_skill_library.zip"
        existed = target.exists()
        build_library()
        if not existed:
            self.assertFalse(target.exists())

    def test_writing_targets_only_the_directory_it_was_given(self) -> None:
        root = fixtures.scratch_dir("iso_target")
        path = write_library(fixtures.build(), root)
        self.assertEqual(path.parent, root)

    def test_writing_creates_exactly_one_file(self) -> None:
        root = fixtures.scratch_dir("iso_one")
        write_library(fixtures.build(), root)
        self.assertEqual(len(list(root.iterdir())), 1)


class NoCapabilityInventionTests(unittest.TestCase):
    """The library declares only what exists."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.build = fixtures.build()

    def test_every_released_skill_is_declared_in_the_library(self) -> None:
        from creator_plugin_builder import META_SKILLS, UNIVERSAL_SKILLS

        for name in self.build.skill_names:
            self.assertIn(name, set(UNIVERSAL_SKILLS) | set(META_SKILLS), name)

    def test_no_skill_is_released_that_the_library_does_not_declare(self) -> None:
        self.assertEqual(len(self.build.skill_names), 13)

    def test_the_generation_interface_is_released_as_a_declaration(self) -> None:
        """It exists in the library, and its manifest does not claim an implementation."""

        manifest = fixtures.document(
            f"{LIBRARY_DIR}/universal_skills/generation-interface/manifest.json"
        )
        self.assertNotIn("implementation", manifest)
        self.assertNotIn("test_command", manifest)

    def test_the_publishing_interface_is_released_as_a_declaration(self) -> None:
        manifest = fixtures.document(
            f"{LIBRARY_DIR}/universal_skills/publishing-interface/manifest.json"
        )
        self.assertNotIn("implementation", manifest)

    def test_no_released_skill_claims_an_adapter(self) -> None:
        for name in self.build.skill_names:
            for layer in ("universal", "meta"):
                member = f"{LIBRARY_DIR}/{'universal_skills' if layer == 'universal' else 'meta_skills'}/{name}/manifest.json"
                if member not in self.build.members:
                    continue
                manifest = fixtures.document(member)
                self.assertNotIn("adapter", manifest, name)

    def test_the_exclusions_record_what_is_absent(self) -> None:
        manifest = fixtures.document(MANIFEST_MEMBER)
        absent = " ".join(e["absent"] for e in manifest["exclusions"])
        self.assertIn("generated domain plugins", absent)

    def test_the_library_version_is_honest_about_being_1_0_0(self) -> None:
        self.assertEqual(self.build.library_version, "1.0.0")


if __name__ == "__main__":
    unittest.main()
