"""The emitted skills: real directories in this repository's own convention."""

from __future__ import annotations

import json
import re
import unittest

from creator_library import (
    FORBIDDEN_SKILL_MANIFEST_KEYS,
    MANIFEST_KEYS,
    NO_TEST_COMMAND_REASON,
    SKILL_MANIFEST_VERSION,
    LibraryPathError,
    LibrarySkillError,
    LibrarySkillMissingError,
    declaration_for,
    emit_skill,
    library_root,
    skill_capabilities,
    skill_dir,
    skill_document,
    skill_document_member,
    skill_manifest,
    skill_manifest_member,
    skill_markdown,
    skill_md_member,
    skill_members,
    validate_emitted_manifest,
)
from creator_plugin_builder import META_SKILLS, UNIVERSAL_SKILLS

from . import fixtures


class PathTests(unittest.TestCase):
    """Every archive path is declared once, and is safe to use as one."""

    def test_the_root_is_the_library_dir(self) -> None:
        self.assertEqual(library_root(), "creator_skill_library")

    def test_a_universal_skill_directory_is_under_universal_skills(self) -> None:
        self.assertEqual(
            skill_dir("universal", "text-distillation"),
            "creator_skill_library/universal_skills/text-distillation",
        )

    def test_a_meta_skill_directory_is_under_meta_skills(self) -> None:
        self.assertEqual(
            skill_dir("meta", "domain-plugin-builder"),
            "creator_skill_library/meta_skills/domain-plugin-builder",
        )

    def test_an_unknown_layer_is_refused(self) -> None:
        with self.assertRaises(LibraryPathError):
            skill_dir("generated", "x")

    def test_a_name_with_a_slash_is_refused(self) -> None:
        with self.assertRaises(LibraryPathError):
            skill_dir("universal", "a/b")

    def test_a_name_with_a_backslash_is_refused(self) -> None:
        with self.assertRaises(LibraryPathError):
            skill_dir("universal", "a\\b")

    def test_a_dot_dot_name_is_refused(self) -> None:
        with self.assertRaises(LibraryPathError):
            skill_dir("universal", "..")

    def test_a_dot_name_is_refused(self) -> None:
        with self.assertRaises(LibraryPathError):
            skill_dir("universal", ".")

    def test_an_empty_name_is_refused(self) -> None:
        with self.assertRaises(LibraryPathError):
            skill_dir("universal", "")

    def test_a_whitespace_name_is_refused(self) -> None:
        with self.assertRaises(LibraryPathError):
            skill_dir("universal", " x ")

    def test_a_windows_reserved_character_is_refused(self) -> None:
        for character in '<>:"|?*':
            with self.assertRaises(LibraryPathError, msg=character):
                skill_dir("universal", f"a{character}b")

    def test_a_skill_has_exactly_three_files(self) -> None:
        self.assertEqual(
            sorted(skill_members("universal", "text-distillation")),
            ["SKILL.md", "manifest.json", "skill.json"],
        )

    def test_the_three_pathed_helpers_agree_with_skill_members(self) -> None:
        expected = skill_members("meta", "skill-composer")
        self.assertEqual(skill_md_member("meta", "skill-composer"),
                         expected["SKILL.md"])
        self.assertEqual(skill_manifest_member("meta", "skill-composer"),
                         expected["manifest.json"])
        self.assertEqual(skill_document_member("meta", "skill-composer"),
                         expected["skill.json"])


class EmitSkillTests(unittest.TestCase):
    """One declaration in, three real files out."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.emitted = emit_skill(
            "text-distillation",
            declaration_for("text-distillation"),
            layer="universal",
            library_version="1.0.0",
        )

    def test_it_emits_three_members(self) -> None:
        self.assertEqual(len(self.emitted), 3)

    def test_every_member_is_bytes(self) -> None:
        for payload in self.emitted.values():
            self.assertIsInstance(payload, bytes)

    def test_the_members_are_the_declared_paths(self) -> None:
        self.assertEqual(
            set(self.emitted), set(skill_members("universal", "text-distillation").values())
        )

    def test_the_markdown_member_is_present(self) -> None:
        self.assertIn(skill_md_member("universal", "text-distillation"), self.emitted)

    def test_emitting_is_deterministic(self) -> None:
        again = emit_skill(
            "text-distillation",
            declaration_for("text-distillation"),
            layer="universal",
            library_version="1.0.0",
        )
        self.assertEqual(again, self.emitted)

    def test_a_skill_with_no_declaration_is_refused(self) -> None:
        with self.assertRaises(LibrarySkillMissingError):
            declaration_for("not-a-skill")

    def test_an_unknown_skill_names_the_declared_ones(self) -> None:
        try:
            declaration_for("not-a-skill")
        except LibrarySkillMissingError as exc:
            self.assertIn("text-distillation", exc.detail)
        else:  # pragma: no cover
            self.fail("expected LibrarySkillError")

    def test_every_universal_skill_emits(self) -> None:
        for name in UNIVERSAL_SKILLS:
            emitted = emit_skill(
                name,
                declaration_for(name),
                layer="universal",
                library_version="1.0.0",
            )
            self.assertEqual(len(emitted), 3, name)

    def test_every_meta_skill_emits(self) -> None:
        for name in META_SKILLS:
            emitted = emit_skill(
                name,
                declaration_for(name),
                layer="meta",
                library_version="1.0.0",
            )
            self.assertEqual(len(emitted), 3, name)


class ManifestFileTests(unittest.TestCase):
    """``manifest.json`` follows the repository's existing skill convention."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = skill_manifest(
            "text-distillation",
            declaration_for("text-distillation"),
            layer="universal",
            library_version="1.0.0",
        )

    def test_it_names_the_skill(self) -> None:
        self.assertEqual(self.manifest["name"], "text-distillation")

    def test_it_declares_the_library_version(self) -> None:
        self.assertEqual(self.manifest["version"], "1.0.0")

    def test_it_declares_the_layer(self) -> None:
        self.assertEqual(self.manifest["library_layer"], "universal")

    def test_it_points_at_the_markdown_entrypoint(self) -> None:
        self.assertEqual(self.manifest["entrypoint"], "SKILL.md")

    def test_it_lists_capabilities(self) -> None:
        self.assertTrue(self.manifest["capabilities"])

    def test_it_states_what_it_produces(self) -> None:
        self.assertTrue(self.manifest["produces"])

    def test_it_records_why_no_test_command_is_present(self) -> None:
        self.assertEqual(self.manifest["note"], NO_TEST_COMMAND_REASON)

    def test_it_carries_no_test_command_key(self) -> None:
        self.assertNotIn("test_command", self.manifest)

    def test_it_carries_exactly_the_declared_keys(self) -> None:
        self.assertEqual(sorted(self.manifest), sorted(MANIFEST_KEYS))

    def test_it_carries_no_forbidden_key(self) -> None:
        for key in FORBIDDEN_SKILL_MANIFEST_KEYS:
            self.assertNotIn(key, self.manifest, key)

    def test_validation_accepts_it(self) -> None:
        validate_emitted_manifest(self.manifest)

    def test_validation_refuses_a_missing_key(self) -> None:
        broken = dict(self.manifest)
        del broken["entrypoint"]
        with self.assertRaises(LibrarySkillError):
            validate_emitted_manifest(broken)

    def test_validation_refuses_a_credential_key(self) -> None:
        broken = dict(self.manifest)
        broken["api_key"] = "x"
        with self.assertRaises(LibrarySkillError):
            validate_emitted_manifest(broken)

    def test_validation_refuses_a_prompt_key(self) -> None:
        broken = dict(self.manifest)
        broken["prompt"] = "x"
        with self.assertRaises(LibrarySkillError):
            validate_emitted_manifest(broken)

    def test_validation_refuses_a_test_command(self) -> None:
        broken = dict(self.manifest)
        broken["test_command"] = "python -m unittest"
        with self.assertRaises(LibrarySkillError):
            validate_emitted_manifest(broken)

    def test_a_skill_with_no_declaration_is_refused(self) -> None:
        with self.assertRaises(LibrarySkillError):
            skill_manifest("x", "not a mapping", layer="universal",
                           library_version="1.0.0")  # type: ignore[arg-type]

    def test_an_empty_purpose_is_refused(self) -> None:
        with self.assertRaises(LibrarySkillError):
            skill_manifest(
                "x",
                {"purpose": "", "produces": "y", "skill_type": "t"},
                layer="universal",
                library_version="1.0.0",
            )

    def test_the_manifest_serialises(self) -> None:
        json.dumps(self.manifest)


class SkillDocumentTests(unittest.TestCase):
    """``skill.json`` is the declaration, machine-readable."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.document = skill_document(
            "domain-plugin-builder",
            declaration_for("domain-plugin-builder"),
            layer="meta",
            library_version="1.0.0",
        )

    def test_it_names_the_skill(self) -> None:
        self.assertEqual(self.document["name"], "domain-plugin-builder")

    def test_it_declares_the_layer(self) -> None:
        self.assertEqual(self.document["library_layer"], "meta")

    def test_it_declares_the_library_version(self) -> None:
        self.assertEqual(self.document["library_version"], "1.0.0")

    def test_it_carries_the_purpose(self) -> None:
        self.assertTrue(self.document["purpose"])

    def test_it_carries_what_it_produces(self) -> None:
        self.assertTrue(self.document["produces"])

    def test_it_carries_what_it_accepts(self) -> None:
        self.assertEqual(self.document["accepts"], "domain_request")

    def test_it_carries_the_declaration_version(self) -> None:
        self.assertEqual(self.document["declaration_version"], SKILL_MANIFEST_VERSION)

    def test_a_universal_skill_has_no_accepts_key(self) -> None:
        document = skill_document(
            "text-distillation",
            declaration_for("text-distillation"),
            layer="universal",
            library_version="1.0.0",
        )
        self.assertNotIn("accepts", document)

    def test_it_serialises(self) -> None:
        json.dumps(self.document)


class CapabilityTests(unittest.TestCase):
    """A skill's capabilities are its own name plus what it produces."""

    def test_the_skill_name_is_a_capability(self) -> None:
        capabilities = skill_capabilities(
            "text-distillation", {"produces": "text rules"}
        )
        self.assertIn("text-distillation", capabilities)

    def test_what_it_produces_is_a_capability(self) -> None:
        capabilities = skill_capabilities(
            "text-distillation", {"produces": "text rules"}
        )
        self.assertIn("produces:text rules", capabilities)

    def test_an_empty_produces_adds_no_capability(self) -> None:
        self.assertEqual(skill_capabilities("x", {"produces": ""}), ("x",))

    def test_produces_equal_to_the_name_adds_no_duplicate(self) -> None:
        self.assertEqual(skill_capabilities("x", {"produces": "x"}), ("x",))

    def test_capabilities_are_a_tuple(self) -> None:
        self.assertIsInstance(skill_capabilities("x", {"produces": "y"}), tuple)

    def test_every_skill_has_at_least_one_capability(self) -> None:
        for name in fixtures.all_skill_names():
            capabilities = skill_capabilities(name, declaration_for(name))
            self.assertTrue(capabilities, name)


class MarkdownTests(unittest.TestCase):
    """``SKILL.md`` follows the front-matter convention, and is domain-free prose."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = skill_markdown(
            "text-distillation",
            declaration_for("text-distillation"),
            layer="universal",
            library_version="1.0.0",
        )
        cls.meta_text = skill_markdown(
            "domain-plugin-builder",
            declaration_for("domain-plugin-builder"),
            layer="meta",
            library_version="1.0.0",
            companions=("domain-plugin-validator", "text-distillation"),
        )

    def test_it_opens_with_front_matter(self) -> None:
        self.assertTrue(self.text.startswith("---\n"))

    def test_the_front_matter_closes(self) -> None:
        self.assertGreaterEqual(self.text.count("\n---\n"), 1)

    def test_the_front_matter_names_the_skill(self) -> None:
        self.assertIn("name: text-distillation", self.text)

    def test_the_front_matter_declares_the_version(self) -> None:
        self.assertIn("version: 1.0.0", self.text)

    def test_the_front_matter_declares_the_layer(self) -> None:
        self.assertIn("library_layer: universal", self.text)

    def test_the_front_matter_carries_a_description(self) -> None:
        self.assertIn("description:", self.text)

    def test_the_front_matter_is_parseable_by_the_project_parser(self) -> None:
        from creator_projection import parse_frontmatter

        parsed, body = parse_frontmatter(self.text)
        self.assertEqual(parsed["name"], "text-distillation")
        self.assertTrue(body.strip())

    def test_it_has_a_heading_naming_the_skill(self) -> None:
        self.assertIn("# text-distillation", self.text)

    def test_a_universal_skill_says_it_is_domain_free(self) -> None:
        self.assertIn("carries no domain knowledge", self.text)

    def test_a_meta_skill_says_what_it_operates_on(self) -> None:
        self.assertIn("Meta Skill", self.meta_text)

    def test_it_lists_companions(self) -> None:
        self.assertIn("`domain-plugin-validator`", self.meta_text)

    def test_it_omits_the_skill_itself_from_companions(self) -> None:
        with_self = skill_markdown(
            "domain-plugin-builder",
            declaration_for("domain-plugin-builder"),
            layer="meta",
            library_version="1.0.0",
            companions=("domain-plugin-builder", "text-distillation"),
        )
        body = with_self.split("## Companions", 1)[1]
        self.assertNotIn("- `domain-plugin-builder`", body)

    def test_it_records_the_provenance(self) -> None:
        self.assertIn("## Provenance", self.text)

    def test_it_records_the_layer_in_provenance(self) -> None:
        self.assertIn("layer: `universal`", self.text)

    def test_it_declares_itself_a_declaration(self) -> None:
        self.assertIn("**declaration**, not an implementation", self.text)

    def test_it_carries_no_prompt_phrase(self) -> None:
        from creator_plugin_builder import PROMPT_PHRASES

        lowered = self.text.lower()
        for phrase in PROMPT_PHRASES:
            self.assertNotIn(phrase, lowered, phrase)

    def test_the_front_matter_stays_one_block(self) -> None:
        front = self.text.split("---", 2)[1]
        for line in front.strip().splitlines():
            self.assertNotIn("\n\n", line)

    def test_every_skill_emits_parseable_front_matter(self) -> None:
        from creator_projection import parse_frontmatter

        for name in fixtures.all_skill_names():
            for layer in ("universal", "meta"):
                if layer == "universal" and name not in UNIVERSAL_SKILLS:
                    continue
                if layer == "meta" and name not in META_SKILLS:
                    continue
                text = skill_markdown(
                    name,
                    declaration_for(name),
                    layer=layer,
                    library_version="1.0.0",
                )
                parsed, _body = parse_frontmatter(text)
                self.assertEqual(parsed["name"], name)

    def test_no_emitted_skill_markdown_names_a_domain(self) -> None:
        from creator_plugin_builder import DOMAIN_MARKERS

        for name in UNIVERSAL_SKILLS:
            text = skill_markdown(
                name,
                declaration_for(name),
                layer="universal",
                library_version="1.0.0",
            ).lower()
            hits = sorted({m for m in DOMAIN_MARKERS if m in text})
            self.assertEqual(hits, [], f"{name}: {hits}")

    def test_no_emitted_skill_markdown_names_a_forbidden_module(self) -> None:
        from creator_plugin_builder import FORBIDDEN_MODULES

        for name in fixtures.all_skill_names():
            for layer in ("universal", "meta"):
                if layer == "universal" and name not in UNIVERSAL_SKILLS:
                    continue
                if layer == "meta" and name not in META_SKILLS:
                    continue
                text = skill_markdown(
                    name,
                    declaration_for(name),
                    layer=layer,
                    library_version="1.0.0",
                )
                for module in FORBIDDEN_MODULES:
                    self.assertNotIn(
                        module, text, f"{name}: {module}"
                    )


class EmittedInArchiveTests(unittest.TestCase):
    """What was emitted is what shipped."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.build = fixtures.build()

    def test_every_declared_skill_has_a_directory(self) -> None:
        for name in fixtures.universal_names():
            self.assertIn(
                f"{fixtures.LIB}/universal_skills/{name}/SKILL.md", self.build.members
            )

    def test_every_meta_skill_has_a_directory(self) -> None:
        for name in fixtures.meta_names():
            self.assertIn(
                f"{fixtures.LIB}/meta_skills/{name}/SKILL.md", self.build.members
            )

    def test_the_shipped_manifests_are_valid(self) -> None:
        for name in fixtures.all_skill_names():
            for layer in ("universal", "meta"):
                member = skill_manifest_member(layer, name)
                if member not in self.build.members:
                    continue
                validate_emitted_manifest(json.loads(fixtures.text(member)))

    def test_the_shipped_markdown_parses(self) -> None:
        from creator_projection import parse_frontmatter

        for name in fixtures.all_skill_names():
            for layer in ("universal", "meta"):
                member = skill_md_member(layer, name)
                if member not in self.build.members:
                    continue
                parsed, _body = parse_frontmatter(fixtures.text(member))
                self.assertEqual(parsed["name"], name)


if __name__ == "__main__":
    unittest.main()
