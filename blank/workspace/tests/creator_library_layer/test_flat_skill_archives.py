"""One skill, one flat archive — ``SKILL.md`` at the root, no wrapper directory.

A shared skill library matches a skill by the description in ``SKILL.md``'s front
matter and then loads that file **from the archive root**. Zipping a skill *directory*
produces ``<skill>/SKILL.md``, one level deeper than the library looks: the archive
lists correctly and still fails to load.

These tests pin the flatness, because that failure is silent otherwise.
"""

from __future__ import annotations

import hashlib
import io
import json
import unittest
import zipfile

from creator_library import (
    FILENAME_PREFIX,
    PACKAGE_SUFFIX,
    SKILL_FILES,
    STANDALONE_FILES,
    LibraryInputError,
    LibraryLayerError,
    LibraryManifestError,
    LibraryPromptError,
    LibrarySkillMissingError,
    LibraryStructureError,
    SkillPackage,
    archive_classify,
    archive_members,
    build_library,
    build_skill_package,
    build_skill_packages,
    checksum_index,
    describe_packages,
    directory_members,
    package_filename,
    package_member_sort_key,
    package_members,
    package_root,
    read_package,
    skill_layer,
    unpack_skill_packages,
    unpacked_checksum_index,
    unpacked_index,
    upload_index,
    validate_package,
    validate_package_structure,
    verify_package_bytes,
    write_skill_packages,
)
from creator_plugin_builder import META_SKILLS, UNIVERSAL_SKILLS

from . import fixtures


def _repacked(package: SkillPackage, members: dict[str, bytes]) -> SkillPackage:
    """A package with new members **and a payload that matches them**.

    :func:`validate_package` reads the archive bytes rather than the in-memory
    members — deliberately, so it checks what was actually written. Mutating
    ``members`` alone is therefore invisible to it, and a test that did so would pass
    whatever the package contained.
    """

    from dataclasses import replace

    return replace(package, members=members, payload=_zip(members))


def _zip(members: dict[str, bytes]) -> bytes:
    """Write members as an archive, verbatim.

    Deliberately does **not** filter or rename: a test that wants a nested archive
    needs the nesting to survive into the payload, or it would be testing the helper
    rather than the check.
    """

    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for name, payload in sorted(members.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, payload)
    return buffer.getvalue()


class FlatArchiveTests(unittest.TestCase):
    """The archive is flat: three files, no wrapper, no directory entries."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.packages = fixtures.packages()

    def test_there_are_thirteen_archives(self) -> None:
        self.assertEqual(len(self.packages), 13)

    def test_every_archive_holds_three_members(self) -> None:
        for p in self.packages:
            self.assertEqual(p.member_count, 3, p.name)

    def test_every_archive_holds_the_three_declared_files(self) -> None:
        for p in self.packages:
            self.assertEqual(sorted(p.members), sorted(SKILL_FILES), p.name)

    def test_skill_md_is_at_the_root_of_every_archive(self) -> None:
        for p in self.packages:
            self.assertIn("SKILL.md", p.members, p.name)

    def test_no_member_is_nested(self) -> None:
        """The defect this whole file exists for."""

        for p in self.packages:
            nested = [m for m in p.members if "/" in m]
            self.assertEqual(nested, [], f"{p.name}: {nested}")

    def test_no_archive_carries_a_directory_entry(self) -> None:
        for p in self.packages:
            with zipfile.ZipFile(io.BytesIO(p.payload)) as archive:
                dirs = [i.filename for i in archive.infolist() if i.is_dir()]
            self.assertEqual(dirs, [], p.name)

    def test_the_zip_stores_the_three_names_exactly(self) -> None:
        for p in self.packages:
            with zipfile.ZipFile(io.BytesIO(p.payload)) as archive:
                self.assertEqual(
                    archive.namelist(),
                    ["SKILL.md", "manifest.json", "skill.json"],
                    p.name,
                )

    def test_no_archive_prefixes_the_skill_name(self) -> None:
        for p in self.packages:
            for member in p.members:
                self.assertFalse(member.startswith(p.name), p.name)

    def test_skill_md_is_written_first(self) -> None:
        for p in self.packages:
            with zipfile.ZipFile(io.BytesIO(p.payload)) as archive:
                self.assertEqual(archive.namelist()[0], "SKILL.md", p.name)

    def test_every_archive_reads_back_flat(self) -> None:
        for p in self.packages:
            self.assertEqual(sorted(read_package(p.payload)), sorted(SKILL_FILES))

    def test_the_archives_are_small(self) -> None:
        """Flat archives are compact; a nested one would also be larger."""

        for p in self.packages:
            self.assertLess(p.size_bytes, 2_000, p.name)

    def test_archive_members_is_flat_by_construction(self) -> None:
        """The helper cannot express a nested layout, so the bug cannot recur."""

        self.assertEqual(
            archive_members(), {name: name for name in SKILL_FILES}
        )

    def test_archive_members_ignores_any_name_passed(self) -> None:
        """It takes a name and deliberately does not use it as a prefix."""

        self.assertEqual(archive_members("text-distillation"), archive_members())

    def test_directory_members_is_the_readable_form(self) -> None:
        self.assertEqual(
            directory_members("text-distillation")["SKILL.md"],
            "text-distillation/SKILL.md",
        )

    def test_package_members_is_the_directory_form(self) -> None:
        self.assertEqual(
            package_members("text-distillation"), directory_members("text-distillation")
        )

    def test_archive_classify_flags_nesting(self) -> None:
        self.assertEqual(archive_classify("SKILL.md"), "skill")
        self.assertEqual(archive_classify("text-distillation/SKILL.md"), "nested")

    def test_a_nested_archive_is_refused(self) -> None:
        members = {"text-distillation/SKILL.md": b"x"}
        with self.assertRaises(LibraryStructureError) as context:
            validate_package_structure(members, name="text-distillation")
        self.assertIn("nests", str(context.exception))

    def test_the_nesting_refusal_explains_why(self) -> None:
        try:
            validate_package_structure({"a/SKILL.md": b"x"}, name="a")
        except LibraryStructureError as exc:
            self.assertIn("archive root", exc.detail)
        else:  # pragma: no cover
            self.fail("expected LibraryStructureError")

    def test_an_archive_with_no_skill_md_is_refused(self) -> None:
        with self.assertRaises(LibraryStructureError):
            validate_package_structure({"manifest.json": b"{}"}, name="x")

    def test_an_archive_with_an_extra_member_is_refused(self) -> None:
        members = {
            "SKILL.md": b"x",
            "manifest.json": b"{}",
            "skill.json": b"{}",
            "extra.md": b"x",
        }
        with self.assertRaises(LibraryStructureError):
            validate_package_structure(members, name="x")

    def test_a_missing_member_is_refused(self) -> None:
        for filename in SKILL_FILES:
            members = {name: b"{}" for name in SKILL_FILES}
            members["SKILL.md"] = b"---\nname: x\n---\n"
            del members[filename]
            with self.assertRaises(LibraryStructureError, msg=filename):
                validate_package_structure(members, name="x")

    def test_a_real_archive_passes_the_structure_check(self) -> None:
        for p in self.packages:
            validate_package_structure(read_package(p.payload), name=p.name)


class ArchiveNamingTests(unittest.TestCase):
    """The filename identifies the skill without a directory inside."""

    def test_the_suffix_is_zip(self) -> None:
        self.assertEqual(PACKAGE_SUFFIX, ".zip")

    def test_the_prefix_groups_the_family(self) -> None:
        self.assertEqual(FILENAME_PREFIX, "creator-")

    def test_the_filename_names_the_skill(self) -> None:
        self.assertEqual(
            package_filename("text-distillation", prefix="creator-"),
            "creator-text-distillation.zip",
        )

    def test_every_filename_is_unique(self) -> None:
        names = [p.filename for p in fixtures.packages()]
        self.assertEqual(len(set(names)), len(names))

    def test_the_filename_does_not_appear_inside_the_archive(self) -> None:
        """The name lives in the filename, not in a wrapper directory."""

        for p in fixtures.packages():
            self.assertNotIn(p.filename, p.members)

    def test_the_root_is_the_skill_name_for_the_readable_form(self) -> None:
        self.assertEqual(package_root("risk-review"), "risk-review")

    def test_the_sort_key_puts_skill_md_first(self) -> None:
        key = package_member_sort_key
        self.assertLess(key("SKILL.md"), key("manifest.json"))
        self.assertLess(key("manifest.json"), key("skill.json"))


class ArchiveContentTests(unittest.TestCase):
    """The three files are the right three files."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.package = fixtures.package("text-distillation")

    def test_skill_md_starts_with_front_matter(self) -> None:
        self.assertTrue(self.package.skill_md.startswith("---\n"))

    def test_skill_md_parses_with_the_project_parser(self) -> None:
        from creator_projection import parse_frontmatter

        parsed, body = parse_frontmatter(self.package.skill_md)
        self.assertEqual(parsed["name"], "text-distillation")
        self.assertTrue(body.strip())

    def test_skill_md_declares_a_description(self) -> None:
        from creator_projection import parse_frontmatter

        parsed, _ = parse_frontmatter(self.package.skill_md)
        self.assertTrue(parsed["description"].strip())

    def test_skill_json_is_present_in_the_archive(self) -> None:
        self.assertIn("skill.json", self.package.members)

    def test_skill_json_is_valid(self) -> None:
        document = json.loads(self.package.members["skill.json"].decode("utf-8"))
        self.assertEqual(document["name"], "text-distillation")

    def test_skill_json_records_the_layer(self) -> None:
        document = json.loads(self.package.members["skill.json"].decode("utf-8"))
        self.assertEqual(document["library_layer"], "universal")

    def test_the_manifest_records_the_library_id(self) -> None:
        self.assertEqual(self.package.manifest["library_id"], "creator_skill_library")

    def test_the_manifest_records_the_library_version(self) -> None:
        self.assertEqual(self.package.manifest["library_version"], "1.0.0")

    def test_the_manifest_carries_no_package_filename(self) -> None:
        """The filename is the archive's name; it need not be repeated inside."""

        self.assertNotIn("package_filename", self.package.manifest)

    def test_the_manifest_lists_capabilities(self) -> None:
        self.assertTrue(self.package.manifest["capabilities"])

    def test_the_package_exposes_its_capabilities(self) -> None:
        self.assertEqual(
            self.package.capabilities, tuple(self.package.manifest["capabilities"])
        )

    def test_the_package_exposes_its_skill_type(self) -> None:
        self.assertEqual(self.package.skill_type, "distillation")

    def test_there_is_no_library_json(self) -> None:
        for p in fixtures.packages():
            self.assertNotIn("library.json", p.members, p.name)

    def test_there_is_no_json_beyond_the_two_expected(self) -> None:
        for p in fixtures.packages():
            jsons = [m for m in p.members if m.endswith(".json")]
            self.assertEqual(sorted(jsons), ["manifest.json", "skill.json"], p.name)


class ArchiveValidationTests(unittest.TestCase):
    """Every archive passes every check, validated from its own bytes."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.packages = fixtures.packages()
        cls.library = build_library()

    def test_every_archive_passes(self) -> None:
        for p in self.packages:
            report = validate_package(p, library_build=self.library)
            self.assertTrue(report.passed, report.as_dict())

    def test_every_check_runs(self) -> None:
        report = validate_package(self.packages[0], library_build=self.library)
        self.assertEqual(
            sorted(report.checks),
            ["isolation", "layer", "library_agreement", "manifest", "structure"],
        )

    def test_every_archive_verifies_from_its_own_bytes(self) -> None:
        for p in self.packages:
            verify_package_bytes(p.payload, name=p.name, version=p.version)

    def test_the_batch_says_PASS(self) -> None:
        self.assertEqual(
            describe_packages(self.packages, library_build=self.library)["status"],
            "PASS",
        )

    def test_thirteen_passed_and_none_failed(self) -> None:
        document = describe_packages(self.packages, library_build=self.library)
        self.assertEqual(document["passed"], 13)
        self.assertEqual(document["failed"], 0)

    def test_a_domain_word_in_a_universal_archive_is_refused(self) -> None:
        package = self.packages[0]
        if package.layer != "universal":
            self.skipTest("sample is not universal")
        members = dict(package.members)
        members["SKILL.md"] = (
            "---\nname: x\nversion: 1.0.0\ndescription: finance\n---\n"
        ).encode()
        with self.assertRaises(LibraryLayerError):
            validate_package(_repacked(package, members))

    def test_a_prompt_phrase_is_refused(self) -> None:
        package = self.packages[0]
        members = dict(package.members)
        members["SKILL.md"] = b"you are a helpful expert"
        with self.assertRaises(LibraryPromptError):
            validate_package(_repacked(package, members))

    def test_a_missing_manifest_is_refused(self) -> None:
        package = self.packages[0]
        members = {k: v for k, v in package.members.items() if k != "manifest.json"}
        with self.assertRaises(LibraryStructureError):
            validate_package(_repacked(package, members))

    def test_a_nested_archive_is_refused_end_to_end(self) -> None:
        """The real defect, through the whole validation path."""

        package = self.packages[0]
        nested = {
            f"{package.name}/{name}": payload
            for name, payload in package.members.items()
        }
        with self.assertRaises(LibraryStructureError) as context:
            validate_package(_repacked(package, nested))
        self.assertIn("nests", str(context.exception))

    def test_the_structure_check_runs_before_the_others(self) -> None:
        """A nested archive is reported as nesting, not as a missing manifest."""

        package = self.packages[0]
        nested = {
            f"{package.name}/{name}": payload
            for name, payload in package.members.items()
        }
        try:
            validate_package(_repacked(package, nested))
        except LibraryStructureError as exc:
            self.assertIn("archive root", exc.detail)
        else:  # pragma: no cover
            self.fail("expected LibraryStructureError")


class DeterminismTests(unittest.TestCase):
    """The same input produces the same bytes, twice."""

    def test_every_archive_is_reproducible(self) -> None:
        for p in fixtures.packages():
            self.assertEqual(build_skill_package(p.name).payload, p.payload, p.name)

    def test_the_whole_set_is_reproducible(self) -> None:
        again = build_skill_packages()
        self.assertEqual(
            [p.payload for p in again], [p.payload for p in fixtures.packages()]
        )

    def test_the_digest_matches_the_payload(self) -> None:
        for p in fixtures.packages():
            self.assertEqual(p.sha256, hashlib.sha256(p.payload).hexdigest(), p.name)

    def test_a_different_version_changes_every_archive(self) -> None:
        mine = {p.name: p.payload for p in fixtures.packages()}
        for p in build_skill_packages(library_version="2.0.0"):
            self.assertNotEqual(p.payload, mine[p.name], p.name)

    def test_an_unknown_skill_is_refused(self) -> None:
        with self.assertRaises(LibrarySkillMissingError):
            build_skill_package("not-a-skill")

    def test_an_empty_skill_name_is_refused(self) -> None:
        with self.assertRaises(LibraryInputError):
            build_skill_package("")

    def test_selecting_no_skills_is_refused(self) -> None:
        with self.assertRaises(LibraryInputError):
            build_skill_packages(universal=(), meta=())

    def test_the_split_covers_the_library(self) -> None:
        self.assertEqual(
            sorted(p.name for p in fixtures.packages()),
            sorted(set(UNIVERSAL_SKILLS) | set(META_SKILLS)),
        )

    def test_skill_layer_resolves_both_halves(self) -> None:
        self.assertEqual(skill_layer("text-distillation"), "universal")
        self.assertEqual(skill_layer("skill-composer"), "meta")

    def test_skill_layer_rejects_an_unknown_skill(self) -> None:
        with self.assertRaises(LibrarySkillMissingError):
            skill_layer("not-a-skill")


class WriteAndIndexTests(unittest.TestCase):
    """Writing the archives, and the indexes a reviewer checks them against."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = fixtures.scratch_dir("flat_write")
        cls.written = write_skill_packages(fixtures.packages(), cls.root)

    def test_it_writes_fifteen_files(self) -> None:
        self.assertEqual(len(self.written), 15)

    def test_it_writes_thirteen_archives(self) -> None:
        self.assertEqual(len(list(self.root.glob("*.zip"))), 13)

    def test_it_writes_the_two_indexes(self) -> None:
        self.assertTrue((self.root / "INDEX.json").is_file())
        self.assertTrue((self.root / "CHECKSUMS.json").is_file())

    def test_no_directory_is_written_beside_the_archives(self) -> None:
        """The upload directory is flat."""

        self.assertEqual([p.name for p in self.root.iterdir() if p.is_dir()], [])

    def test_the_written_bytes_match(self) -> None:
        for p in fixtures.packages():
            self.assertEqual((self.root / p.filename).read_bytes(), p.payload, p.name)

    def test_the_checksums_match(self) -> None:
        ledger = json.loads((self.root / "CHECKSUMS.json").read_text("utf-8"))
        for p in fixtures.packages():
            self.assertEqual(
                ledger["packages"][p.filename]["sha256"], p.sha256, p.name
            )

    def test_writing_is_deterministic(self) -> None:
        other = fixtures.scratch_dir("flat_write2")
        write_skill_packages(fixtures.packages(), other)
        for p in fixtures.packages():
            self.assertEqual(
                (other / p.filename).read_bytes(), (self.root / p.filename).read_bytes()
            )

    def test_the_index_counts_thirteen(self) -> None:
        self.assertEqual(upload_index(fixtures.packages())["package_count"], 13)

    def test_the_index_splits_the_layers(self) -> None:
        index = upload_index(fixtures.packages())
        self.assertEqual(index["universal_skill_count"], 10)
        self.assertEqual(index["meta_skill_count"], 3)

    def test_every_index_entry_lists_the_three_files(self) -> None:
        for entry in upload_index(fixtures.packages())["packages"]:
            self.assertEqual(sorted(entry["files"]), sorted(SKILL_FILES))

    def test_the_checksum_index_has_a_row_per_archive(self) -> None:
        self.assertEqual(len(checksum_index(fixtures.packages())["packages"]), 13)

    def test_the_index_serialises(self) -> None:
        json.dumps(upload_index(fixtures.packages()))

    def test_the_checksums_serialise(self) -> None:
        json.dumps(checksum_index(fixtures.packages()))


class ReadableFormTests(unittest.TestCase):
    """The on-disk directory form still exists, for a person to read."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = fixtures.scratch_dir("flat_unpack")
        unpack_skill_packages(fixtures.packages(), cls.root, with_indexes=False)

    def test_it_writes_thirteen_directories(self) -> None:
        self.assertEqual(len([p for p in self.root.iterdir() if p.is_dir()]), 13)

    def test_every_directory_holds_three_files(self) -> None:
        for p in fixtures.packages():
            self.assertEqual(
                sorted(f.name for f in (self.root / p.name).iterdir()),
                sorted(SKILL_FILES),
                p.name,
            )

    def test_skill_md_is_in_every_directory(self) -> None:
        for p in fixtures.packages():
            self.assertTrue((self.root / p.name / "SKILL.md").is_file(), p.name)

    def test_unpacking_matches_extracting_the_archive(self) -> None:
        for p in fixtures.packages():
            directory = self.root / p.name
            with zipfile.ZipFile(io.BytesIO(p.payload)) as archive:
                for info in archive.infolist():
                    self.assertEqual(
                        (directory / info.filename).read_bytes(),
                        archive.read(info),
                        f"{p.name}/{info.filename}",
                    )

    def test_the_directory_and_archive_forms_hold_the_same_bytes(self) -> None:
        for p in fixtures.packages():
            for filename in SKILL_FILES:
                self.assertEqual(
                    (self.root / p.name / filename).read_bytes(),
                    p.members[filename],
                    f"{p.name}/{filename}",
                )

    def test_an_unpacked_set_writes_no_archive(self) -> None:
        self.assertEqual(list(self.root.rglob("*.zip")), [])

    def test_the_unpacked_index_is_written(self) -> None:
        root = fixtures.scratch_dir("flat_unpack_idx")
        unpack_skill_packages(fixtures.packages(), root)
        self.assertTrue((root / "INDEX.json").is_file())

    def test_the_unpacked_index_lists_directories(self) -> None:
        index = unpacked_index(fixtures.packages())
        for entry in index["skills"]:
            self.assertEqual(entry["directory"], entry["skill"])

    def test_the_unpacked_checksums_cover_every_file(self) -> None:
        self.assertEqual(unpacked_checksum_index(fixtures.packages())["file_count"], 39)

    def test_the_two_forms_are_both_reproducible(self) -> None:
        first = fixtures.scratch_dir("flat_cmp1")
        second = fixtures.scratch_dir("flat_cmp2")
        unpack_skill_packages(fixtures.packages(), first, with_indexes=False)
        unpack_skill_packages(fixtures.packages(), second, with_indexes=False)
        for p in fixtures.packages():
            for filename in SKILL_FILES:
                self.assertEqual(
                    (first / p.name / filename).read_bytes(),
                    (second / p.name / filename).read_bytes(),
                )


if __name__ == "__main__":
    unittest.main()
