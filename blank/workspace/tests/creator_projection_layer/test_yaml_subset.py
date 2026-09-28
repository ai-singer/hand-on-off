"""The dependency-free YAML-subset reader."""

from __future__ import annotations

import unittest

from creator_projection import ProjectionParseError, parse_yaml_subset


class ScalarTests(unittest.TestCase):
    def test_string_value(self) -> None:
        self.assertEqual(parse_yaml_subset("a: hello\n"), {"a": "hello"})

    def test_integer_value(self) -> None:
        self.assertEqual(parse_yaml_subset("a: 42\n"), {"a": 42})

    def test_float_value(self) -> None:
        self.assertEqual(parse_yaml_subset("a: 0.5\n"), {"a": 0.5})

    def test_true_value(self) -> None:
        self.assertIs(parse_yaml_subset("a: true\n")["a"], True)

    def test_false_value(self) -> None:
        self.assertIs(parse_yaml_subset("a: false\n")["a"], False)

    def test_null_value(self) -> None:
        self.assertIsNone(parse_yaml_subset("a: null\n")["a"])

    def test_double_quoted_string_is_preserved(self) -> None:
        self.assertEqual(parse_yaml_subset('a: "1.2.3"\n'), {"a": "1.2.3"})

    def test_single_quoted_string_is_preserved(self) -> None:
        self.assertEqual(parse_yaml_subset("a: 'yes'\n"), {"a": "yes"})

    def test_colon_inside_a_value_is_preserved(self) -> None:
        self.assertEqual(
            parse_yaml_subset('a: "16:9"\n'), {"a": "16:9"}
        )


class StructureTests(unittest.TestCase):
    def test_nested_mapping(self) -> None:
        self.assertEqual(
            parse_yaml_subset("a:\n  b: 1\n  c: 2\n"), {"a": {"b": 1, "c": 2}}
        )

    def test_deeply_nested_mapping(self) -> None:
        payload = "a:\n  b:\n    c:\n      d: 4\n"
        self.assertEqual(parse_yaml_subset(payload), {"a": {"b": {"c": {"d": 4}}}})

    def test_sequence_of_scalars(self) -> None:
        self.assertEqual(
            parse_yaml_subset("a:\n  - x\n  - y\n"), {"a": ["x", "y"]}
        )

    def test_sequence_of_mappings(self) -> None:
        payload = "a:\n  - id: one\n    v: 1\n  - id: two\n    v: 2\n"
        self.assertEqual(
            parse_yaml_subset(payload),
            {"a": [{"id": "one", "v": 1}, {"id": "two", "v": 2}]},
        )

    def test_sequence_inside_a_sequence_item(self) -> None:
        payload = "a:\n  - id: one\n    tags:\n      - x\n      - y\n"
        self.assertEqual(
            parse_yaml_subset(payload), {"a": [{"id": "one", "tags": ["x", "y"]}]}
        )

    def test_empty_mapping_value(self) -> None:
        self.assertEqual(parse_yaml_subset("a:\n"), {"a": {}})

    def test_multiple_top_level_keys(self) -> None:
        self.assertEqual(parse_yaml_subset("a: 1\nb: 2\n"), {"a": 1, "b": 2})

    def test_nested_sequence_after_mapping(self) -> None:
        payload = "outer:\n  inner: 1\n  items:\n    - a\n    - b\n"
        self.assertEqual(
            parse_yaml_subset(payload), {"outer": {"inner": 1, "items": ["a", "b"]}}
        )


class CommentAndBlockTests(unittest.TestCase):
    def test_comments_are_skipped(self) -> None:
        self.assertEqual(parse_yaml_subset("# c\na: 1\n# d\nb: 2\n"), {"a": 1, "b": 2})

    def test_blank_lines_are_skipped(self) -> None:
        self.assertEqual(parse_yaml_subset("a: 1\n\n\nb: 2\n"), {"a": 1, "b": 2})

    def test_folded_block_scalar(self) -> None:
        payload = "a: >\n  one\n  two\n"
        self.assertEqual(parse_yaml_subset(payload), {"a": "one two"})

    def test_literal_block_scalar(self) -> None:
        payload = "a: |\n  one\n  two\n"
        self.assertEqual(parse_yaml_subset(payload), {"a": "one\ntwo"})

    def test_folded_scalar_in_a_sequence_item(self) -> None:
        payload = "a:\n  - id: x\n    note: >\n      hello there\n"
        self.assertEqual(
            parse_yaml_subset(payload), {"a": [{"id": "x", "note": "hello there"}]}
        )


class RejectionTests(unittest.TestCase):
    def test_non_string_payload_is_rejected(self) -> None:
        with self.assertRaises(ProjectionParseError):
            parse_yaml_subset(["not", "a", "string"])  # type: ignore[arg-type]

    def test_sequence_at_the_root_is_rejected(self) -> None:
        with self.assertRaises(ProjectionParseError):
            parse_yaml_subset("- a\n- b\n")

    def test_line_without_a_colon_is_rejected(self) -> None:
        with self.assertRaises(ProjectionParseError):
            parse_yaml_subset("just a bare line\n")

    def test_empty_key_is_rejected(self) -> None:
        with self.assertRaises(ProjectionParseError):
            parse_yaml_subset(": value\n")

    def test_sequence_where_a_mapping_key_is_expected_is_rejected(self) -> None:
        with self.assertRaises(ProjectionParseError):
            parse_yaml_subset("a: 1\n  - x\n")


class RealDocumentTests(unittest.TestCase):
    """The reader must handle the two documents the layer actually parses."""

    @classmethod
    def setUpClass(cls) -> None:
        from creator_projection.asset_registry import REGISTRY_FILENAME
        from pathlib import Path

        cls.registry_path = Path(__file__).resolve().parents[2] / "creator_projection" / REGISTRY_FILENAME
        cls.workspace = Path(__file__).resolve().parents[2]

    def test_registry_document_parses(self) -> None:
        payload = parse_yaml_subset(
            self.registry_path.read_text(encoding="utf-8"), origin="assets.yaml"
        )
        self.assertIn("assets", payload)
        self.assertIsInstance(payload["assets"], list)

    def test_registry_version_parses_as_a_string(self) -> None:
        payload = parse_yaml_subset(
            self.registry_path.read_text(encoding="utf-8"), origin="assets.yaml"
        )
        self.assertEqual(payload["version"], "1.0.0")

    def test_m5_profile_document_parses(self) -> None:
        path = self.workspace / "docs" / "m5" / "profiles" / "visual_profile.yaml"
        payload = parse_yaml_subset(path.read_text(encoding="utf-8"), origin=str(path))
        self.assertIn("visual_profile", payload)
        self.assertIn("composition", payload)

    def test_m5_profile_version_parses_as_a_string(self) -> None:
        path = self.workspace / "docs" / "m5" / "profiles" / "visual_profile.yaml"
        payload = parse_yaml_subset(path.read_text(encoding="utf-8"), origin=str(path))
        self.assertEqual(payload["visual_profile"]["profile_version"], "m5.0.0")

    def test_m5_profile_lists_parse(self) -> None:
        path = self.workspace / "docs" / "m5" / "profiles" / "visual_profile.yaml"
        payload = parse_yaml_subset(path.read_text(encoding="utf-8"), origin=str(path))
        self.assertIsInstance(payload["composition"]["preferred_layout"], list)
        self.assertTrue(payload["composition"]["preferred_layout"])


if __name__ == "__main__":
    unittest.main()
