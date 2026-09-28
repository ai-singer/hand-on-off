"""Markdown -> structure conversion. Structure only, original text preserved."""

from __future__ import annotations

import unittest

from creator_projection import (
    MarkdownDocument,
    ProjectionParseError,
    parse_frontmatter,
    parse_markdown,
    section_titles,
    sections_as_dicts,
)

SAMPLE = """---
name: sample-perspective
description: |
  A sample persona skill used for parser tests.
---

# Sample Person

Preamble line.

## Identity card

I am a sample.

## Mental models

### Model 1: First model

- Mechanism: it works by doing the thing.
- Evidence: seen in two places.
- Apply when: problems of type A.
- Failure condition: fails when B.

### Model 2: Second model

- Mechanism: another mechanism.
- Evidence: seen elsewhere.
- Apply when: problems of type C.
- Failure condition: fails when D.

## Decision heuristics

- When X, do Y.
- When Z, do W.

## Honest boundaries

- Cannot know private data.
- Research cutoff applies.
"""


class FrontmatterTests(unittest.TestCase):
    def test_frontmatter_is_extracted(self) -> None:
        front, _body = parse_frontmatter(SAMPLE)
        self.assertEqual(front["name"], "sample-perspective")

    def test_folded_frontmatter_value_is_joined(self) -> None:
        front, _body = parse_frontmatter(SAMPLE)
        self.assertIn("sample persona skill", front["description"])

    def test_body_excludes_frontmatter(self) -> None:
        _front, body = parse_frontmatter(SAMPLE)
        self.assertNotIn("sample-perspective", body)

    def test_document_without_frontmatter(self) -> None:
        front, body = parse_frontmatter("# Title\n\nbody\n")
        self.assertEqual(front, {})
        self.assertIn("# Title", body)

    def test_unterminated_frontmatter_treated_as_body(self) -> None:
        front, body = parse_frontmatter("---\nname: x\n")
        self.assertEqual(front, {})
        self.assertIn("name: x", body)


class SectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = parse_markdown(SAMPLE)

    def test_returns_a_document(self) -> None:
        self.assertIsInstance(self.document, MarkdownDocument)

    def test_section_count(self) -> None:
        self.assertEqual(len(self.document.sections), 7)

    def test_level_one_title_is_first(self) -> None:
        self.assertEqual(self.document.sections[0].title, "Sample Person")

    def test_heading_levels_are_recorded(self) -> None:
        by_title = {s.title: s.level for s in self.document.sections}
        self.assertEqual(by_title["Sample Person"], 1)
        self.assertEqual(by_title["Mental models"], 2)
        self.assertEqual(by_title["Model 1: First model"], 3)

    def test_preamble_is_captured(self) -> None:
        document = parse_markdown("intro prose\n\n# Title\n\nbody\n")
        self.assertEqual(document.preamble, "intro prose")

    def test_preamble_is_empty_when_the_document_opens_with_a_heading(self) -> None:
        document = parse_markdown("# Title\n\nbody\n")
        self.assertEqual(document.preamble, "")

    def test_section_content_is_preserved_verbatim(self) -> None:
        section = self.document.section("Identity card")
        self.assertIsNotNone(section)
        self.assertEqual(section.content, "I am a sample.")

    def test_bullets_are_collected(self) -> None:
        section = self.document.section("Decision heuristics")
        self.assertEqual(section.bullets, ("When X, do Y.", "When Z, do W."))

    def test_find_is_case_insensitive(self) -> None:
        self.assertIsNotNone(self.document.find("HONEST BOUNDARIES"))

    def test_find_accepts_alternatives(self) -> None:
        self.assertIsNotNone(self.document.find("nope", "boundaries"))

    def test_find_returns_none_when_absent(self) -> None:
        self.assertIsNone(self.document.find("nonexistent section"))

    def test_section_lookup_by_exact_title(self) -> None:
        self.assertIsNotNone(self.document.section("Mental models"))

    def test_titles_helper(self) -> None:
        titles = section_titles(self.document)
        self.assertIn("Honest boundaries", titles)

    def test_sections_as_dicts_shape(self) -> None:
        payload = sections_as_dicts(self.document)
        self.assertIsInstance(payload, list)
        self.assertIn("title", payload[0])
        self.assertIn("content", payload[0])

    def test_as_dict_round_trips_through_json(self) -> None:
        import json

        json.dumps(self.document.as_dict())

    def test_nested_heading_body_excludes_the_child_heading(self) -> None:
        section = self.document.section("Mental models")
        self.assertNotIn("### Model 1", section.content)


class ModelSectionTests(unittest.TestCase):
    """The persona-skill shape the identity mapper depends on."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.document = parse_markdown(SAMPLE)

    def test_model_sections_are_discoverable_by_title_prefix(self) -> None:
        models = [s for s in self.document.sections if s.title.startswith("Model ")]
        self.assertEqual(len(models), 2)

    def test_model_bullets_are_verbatim(self) -> None:
        model = self.document.section("Model 1: First model")
        self.assertIn("Mechanism: it works by doing the thing.", model.bullets)
        self.assertIn("Failure condition: fails when B.", model.bullets)

    def test_model_identifier_sits_after_the_colon(self) -> None:
        model = self.document.section("Model 2: Second model")
        self.assertEqual(model.title.partition(":")[2].strip(), "Second model")


class CodeFenceTests(unittest.TestCase):
    def test_headings_inside_code_fences_are_not_sections(self) -> None:
        payload = "# Real\n\n```\n# Not a heading\n```\n\n## Second\n"
        document = parse_markdown(payload)
        self.assertEqual(document.titles(), ("Real", "Second"))

    def test_bullets_inside_code_fences_are_not_collected(self) -> None:
        payload = "# S\n\n```\n- not a bullet\n```\n\n- real bullet\n"
        document = parse_markdown(payload)
        self.assertEqual(document.section("S").bullets, ("real bullet",))


class RejectionTests(unittest.TestCase):
    def test_non_string_payload_is_rejected(self) -> None:
        with self.assertRaises(ProjectionParseError):
            parse_markdown(123)  # type: ignore[arg-type]

    def test_empty_heading_is_rejected(self) -> None:
        with self.assertRaises(ProjectionParseError):
            parse_markdown("#\n")

    def test_document_with_no_headings_has_no_sections(self) -> None:
        document = parse_markdown("just prose\n")
        self.assertEqual(document.sections, ())

    def test_empty_document_is_accepted(self) -> None:
        document = parse_markdown("")
        self.assertEqual(document.sections, ())


class PreservationTests(unittest.TestCase):
    """The parser must not summarise, rewrite, or reinterpret."""

    def test_long_content_is_preserved_exactly(self) -> None:
        body = "line one\nline two\nline three"
        document = parse_markdown(f"# S\n\n{body}\n")
        self.assertEqual(document.section("S").content, body)

    def test_non_ascii_content_is_preserved(self) -> None:
        document = parse_markdown("# 标题\n\n中文内容保留。\n")
        self.assertEqual(document.section("标题").content, "中文内容保留。")

    def test_bullet_text_is_not_modified(self) -> None:
        document = parse_markdown("# S\n\n- 保持原文，不要总结\n")
        self.assertEqual(document.section("S").bullets, ("保持原文，不要总结",))

    def test_numbered_list_is_not_treated_as_a_bullet(self) -> None:
        document = parse_markdown("# S\n\n1. first\n2. second\n")
        self.assertEqual(document.section("S").bullets, ())


if __name__ == "__main__":
    unittest.main()
