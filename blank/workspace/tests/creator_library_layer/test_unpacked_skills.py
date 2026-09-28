"""The unpacked form: one skill directory per skill, ``SKILL.md`` at its root.

A shared skill library matches a skill by its description and then **loads
``SKILL.md``** from a skills directory. An archive would have to be extracted before
anything could read it, so the deliverable is the directory, not the zip.

These tests pin that: the unpacked tree is exactly what extracting the zip would
produce, ``SKILL.md`` sits at every skill's root, and nothing is nested twice.
"""

from __future__ import annotations

import hashlib
import json
import unittest
import zipfile

from creator_library import (
    LIBRARY_FILE,
    STANDALONE_FILES,
    package_member_sort_key,
    unpack_skill_package,
    unpack_skill_packages,
    unpacked_checksum_index,
    unpacked_index,
)

from . import fixtures


class UnpackedLayoutTests(unittest.TestCase):
    """Thirteen directories, each with SKILL.md at its root."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = fixtures.scratch_dir("unpacked")
        cls.written = unpack_skill_packages(fixtures.packages(), cls.root)
        cls.dirs = sorted(p for p in cls.root.iterdir() if p.is_dir())

    def test_it_writes_one_directory_per_skill(self) -> None:
        self.assertEqual(len(self.dirs), 13)

    def test_it_writes_the_indexes_too(self) -> None:
        self.assertTrue((self.root / "INDEX.json").is_file())
        self.assertTrue((self.root / "CHECKSUMS.json").is_file())

    def test_it_writes_no_zip(self) -> None:
        self.assertEqual(list(self.root.rglob("*.zip")), [])

    def test_no_directory_nests_another_skill_directory(self) -> None:
        for directory in self.dirs:
            self.assertEqual(
                [p.name for p in directory.iterdir() if p.is_dir()], [], directory.name
            )

    def test_skill_md_is_at_every_root(self) -> None:
        for directory in self.dirs:
            self.assertTrue((directory / "SKILL.md").is_file(), directory.name)

    def test_no_skill_md_is_nested_deeper(self) -> None:
        found = [p for p in self.root.rglob("SKILL.md") if p.parent.parent != self.root]
        self.assertEqual(found, [])

    def test_every_directory_names_a_skill(self) -> None:
        self.assertEqual(
            sorted(p.name for p in self.dirs),
            sorted(p.name for p in fixtures.packages()),
        )

    def test_every_directory_holds_the_four_files(self) -> None:
        for directory in self.dirs:
            present = sorted(p.name for p in directory.iterdir() if p.is_file())
            self.assertEqual(present, sorted(STANDALONE_FILES), directory.name)

    def test_writing_creates_the_root(self) -> None:
        deep = fixtures.scratch_dir("unpacked_deep") / "a" / "b"
        unpack_skill_packages(fixtures.packages(), deep)
        self.assertTrue(deep.is_dir())

    def test_with_indexes_can_be_turned_off(self) -> None:
        root = fixtures.scratch_dir("unpacked_no_index")
        unpack_skill_packages(fixtures.packages(), root, with_indexes=False)
        self.assertFalse((root / "INDEX.json").exists())
        self.assertEqual(len([p for p in root.iterdir() if p.is_dir()]), 13)


class UnpackedMatchesZipTests(unittest.TestCase):
    """Unpacking is the same tree as extracting — no more, no less."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = fixtures.scratch_dir("unpacked_match")
        unpack_skill_packages(fixtures.packages(), cls.root, with_indexes=False)

    def test_every_file_matches_the_archive_member(self) -> None:
        for package in fixtures.packages():
            directory = self.root / package.root
            for member, payload in package.members.items():
                filename = member.rsplit("/", 1)[-1]
                self.assertEqual(
                    (directory / filename).read_bytes(), payload,
                    f"{package.name}/{filename}",
                )

    def test_unpacking_matches_extracting_the_zip(self) -> None:
        import io

        for package in fixtures.packages():
            directory = self.root / package.root
            with zipfile.ZipFile(io.BytesIO(package.payload)) as archive:
                for info in archive.infolist():
                    relative = info.filename.split("/", 1)[1]
                    self.assertEqual(
                        (directory / relative).read_bytes(),
                        archive.read(info),
                        f"{package.name}/{relative}",
                    )

    def test_the_file_count_matches(self) -> None:
        written = sum(1 for p in self.root.rglob("*") if p.is_file())
        expected = sum(len(p.members) for p in fixtures.packages())
        self.assertEqual(written, expected)

    def test_the_written_order_is_the_declared_order(self) -> None:
        package = fixtures.package("text-distillation")
        directory = self.root / package.root
        declared = sorted(package.members, key=package_member_sort_key)
        self.assertEqual(
            [p.name for p in sorted(directory.iterdir(), key=lambda x: x.name)],
            sorted(declared[i].rsplit("/", 1)[-1] for i in range(len(declared))),
        )

    def test_unpacking_is_idempotent(self) -> None:
        root = fixtures.scratch_dir("unpacked_twice")
        unpack_skill_packages(fixtures.packages(), root)
        unpack_skill_packages(fixtures.packages(), root)
        self.assertEqual(len([p for p in root.iterdir() if p.is_dir()]), 13)


class SkillMdIsReadableTests(unittest.TestCase):
    """The file the library actually reads is present and well formed."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = fixtures.scratch_dir("unpacked_skillmd")
        unpack_skill_packages(fixtures.packages(), cls.root, with_indexes=False)

    def test_every_skill_md_starts_with_front_matter(self) -> None:
        for package in fixtures.packages():
            text = (self.root / package.root / "SKILL.md").read_text("utf-8")
            self.assertTrue(text.startswith("---\n"), package.name)

    def test_every_skill_md_parses_with_the_project_parser(self) -> None:
        from creator_projection import parse_frontmatter

        for package in fixtures.packages():
            text = (self.root / package.root / "SKILL.md").read_text("utf-8")
            parsed, body = parse_frontmatter(text)
            self.assertEqual(parsed["name"], package.name, package.name)
            self.assertTrue(body.strip(), package.name)

    def test_every_skill_md_declares_a_description(self) -> None:
        """A library matches a skill by its description, so it must be there."""

        from creator_projection import parse_frontmatter

        for package in fixtures.packages():
            text = (self.root / package.root / "SKILL.md").read_text("utf-8")
            parsed, _ = parse_frontmatter(text)
            self.assertTrue(parsed.get("description", "").strip(), package.name)

    def test_every_skill_md_declares_a_version(self) -> None:
        from creator_projection import parse_frontmatter

        for package in fixtures.packages():
            text = (self.root / package.root / "SKILL.md").read_text("utf-8")
            parsed, _ = parse_frontmatter(text)
            self.assertEqual(parsed["version"], package.version, package.name)

    def test_every_skill_md_declares_its_layer(self) -> None:
        from creator_projection import parse_frontmatter

        for package in fixtures.packages():
            text = (self.root / package.root / "SKILL.md").read_text("utf-8")
            parsed, _ = parse_frontmatter(text)
            self.assertEqual(parsed["library_layer"], package.layer, package.name)


class UnpackedIndexTests(unittest.TestCase):
    """The indexes describe directories and files, not archives."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.packages = fixtures.packages()
        cls.index = unpacked_index(cls.packages)
        cls.checksums = unpacked_checksum_index(cls.packages)

    def test_the_index_says_unpacked(self) -> None:
        self.assertEqual(self.index["distribution"], "unpacked")

    def test_the_index_counts_thirteen(self) -> None:
        self.assertEqual(self.index["skill_count"], 13)

    def test_the_index_splits_the_layers(self) -> None:
        self.assertEqual(self.index["universal_skill_count"], 10)
        self.assertEqual(self.index["meta_skill_count"], 3)

    def test_every_entry_names_a_directory(self) -> None:
        for entry in self.index["skills"]:
            self.assertEqual(entry["directory"], entry["skill"])

    def test_every_entry_names_its_entrypoint(self) -> None:
        for entry in self.index["skills"]:
            self.assertEqual(entry["entrypoint"], f"{entry['skill']}/SKILL.md")

    def test_every_entry_lists_its_files(self) -> None:
        for entry in self.index["skills"]:
            self.assertEqual(sorted(entry["files"]), sorted(STANDALONE_FILES))

    def test_the_index_explains_why_it_is_unpacked(self) -> None:
        self.assertIn("SKILL.md", self.index["purpose"])

    def test_the_index_records_that_a_zip_would_need_extracting(self) -> None:
        self.assertIn("extracted", self.index["note"])

    def test_the_checksums_say_unpacked(self) -> None:
        self.assertEqual(self.checksums["distribution"], "unpacked")

    def test_the_checksums_cover_every_file(self) -> None:
        self.assertEqual(self.checksums["file_count"], 13 * 4)

    def test_every_file_has_a_digest(self) -> None:
        for path, row in self.checksums["files"].items():
            self.assertEqual(len(row["sha256"]), 64, path)

    def test_the_checksum_digests_match_the_packages(self) -> None:
        for package in self.packages:
            for filename in STANDALONE_FILES:
                member = f"{package.root}/{filename}"
                payload = package.members[member]
                self.assertEqual(
                    self.checksums["files"][member]["sha256"],
                    hashlib.sha256(payload).hexdigest(),
                    member,
                )

    def test_the_checksums_mark_the_entrypoint_first(self) -> None:
        self.assertIs(self.checksums["entrypoint_first"], True)

    def test_the_index_serialises(self) -> None:
        json.dumps(self.index)

    def test_the_checksums_serialise(self) -> None:
        json.dumps(self.checksums)


class UnpackOneTests(unittest.TestCase):
    """Unpacking a single skill, and replacing what was there before."""

    def test_one_skill_unpacks(self) -> None:
        root = fixtures.scratch_dir("unpack_one")
        target = unpack_skill_package(fixtures.package("risk-review"), root)
        self.assertEqual(target.name, "risk-review")

    def test_the_directory_holds_four_files(self) -> None:
        root = fixtures.scratch_dir("unpack_one2")
        target = unpack_skill_package(fixtures.package("risk-review"), root)
        self.assertEqual(len(list(target.iterdir())), 4)

    def test_skill_md_is_present(self) -> None:
        root = fixtures.scratch_dir("unpack_one3")
        target = unpack_skill_package(fixtures.package("risk-review"), root)
        self.assertTrue((target / "SKILL.md").is_file())

    def test_a_stale_file_is_removed_on_reunpack(self) -> None:
        root = fixtures.scratch_dir("unpack_stale")
        target = unpack_skill_package(fixtures.package("risk-review"), root)
        (target / "stale.md").write_text("old", encoding="utf-8")
        unpack_skill_package(fixtures.package("risk-review"), root)
        self.assertFalse((target / "stale.md").exists())

    def test_the_library_metadata_is_present(self) -> None:
        root = fixtures.scratch_dir("unpack_meta")
        target = unpack_skill_package(fixtures.package("risk-review"), root)
        self.assertTrue((target / LIBRARY_FILE).is_file())

    def test_the_manifest_is_readable(self) -> None:
        root = fixtures.scratch_dir("unpack_manifest")
        target = unpack_skill_package(fixtures.package("risk-review"), root)
        document = json.loads((target / "manifest.json").read_text("utf-8"))
        self.assertEqual(document["name"], "risk-review")


class DesktopShapeTests(unittest.TestCase):
    """The shape a caller points a shared library at, stated once."""

    def test_the_unit_is_a_directory_per_skill(self) -> None:
        root = fixtures.scratch_dir("shape")
        unpack_skill_packages(fixtures.packages(), root, with_indexes=False)
        for package in fixtures.packages():
            self.assertTrue((root / package.name / "SKILL.md").is_file(), package.name)

    def test_there_is_exactly_one_level_of_nesting(self) -> None:
        root = fixtures.scratch_dir("shape_depth")
        unpack_skill_packages(fixtures.packages(), root, with_indexes=False)
        for path in root.rglob("SKILL.md"):
            depth = len(path.relative_to(root).parts)
            self.assertEqual(depth, 2, str(path))

    def test_no_archive_survives_into_the_output(self) -> None:
        root = fixtures.scratch_dir("shape_nozip")
        unpack_skill_packages(fixtures.packages(), root)
        self.assertEqual(list(root.rglob("*.zip")), [])


if __name__ == "__main__":
    unittest.main()
