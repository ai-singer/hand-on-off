from __future__ import annotations

import unittest

from core import RawSource, SourceType, load_plugin
from core.errors import InvalidSourceError
from distillation_core import DistillationEngine

from ._fixtures import (
    ARTIFACT_SECTIONS,
    COMMON_FAMILIES,
    DATA_SOURCE,
    DOCUMENT_SOURCE,
    IMAGE_SOURCE,
    PLUGIN_MODULE_PATH,
    ROLE_SOURCES,
    SOURCE_KIND_FIXTURES,
    VIDEO_SOURCE,
)


class SourceAdapterTests(unittest.TestCase):
    """Step 2 - all four adapter kinds enter one RawSource contract."""

    def setUp(self) -> None:
        self.plugin = load_plugin(PLUGIN_MODULE_PATH)

    def _artifact(self, source: RawSource) -> dict:
        return DistillationEngine(self.plugin).distill([source])

    def _assert_adapter(self, source: RawSource, expected_type: SourceType) -> None:
        self.assertIsInstance(source.source_type, SourceType)
        self.assertEqual(source.source_type, expected_type)
        self.assertTrue(source.source_id)
        self.assertIsNotNone(source.content)
        self.assertIsInstance(source.metadata, dict)

        artifact = self._artifact(source)
        for section in ARTIFACT_SECTIONS:
            self.assertIn(section, artifact, section)
        self.assertEqual(artifact["plugin"]["name"], "xiaolin_finance")

    # Test A - business analysis text
    def test_text_material_enters_the_document_contract(self) -> None:
        self._assert_adapter(DOCUMENT_SOURCE, SourceType.DOCUMENT)

    def test_the_contract_has_no_text_source_type(self) -> None:
        """The adapter kind is called "text" but the contract has no such value.

        Four values exist: video, document, data, image. Text material is
        `document`. Rejecting "text" rather than coercing it keeps the contract
        explicit.
        """

        self.assertNotIn("text", {item.value for item in SourceType})
        with self.assertRaises(InvalidSourceError):
            RawSource(source_id="bad-1", source_type="text", content="anything")

    # Test B - structured financial metrics
    def test_structured_data_enters_the_data_contract(self) -> None:
        self._assert_adapter(DATA_SOURCE, SourceType.DATA)

    # Test C - video summary input
    def test_video_summary_enters_the_video_contract(self) -> None:
        self._assert_adapter(VIDEO_SOURCE, SourceType.VIDEO)

    # Test D - image / OCR description input
    def test_image_description_enters_the_image_contract(self) -> None:
        self._assert_adapter(IMAGE_SOURCE, SourceType.IMAGE)


class DistillationUniformityTests(unittest.TestCase):
    """Step 3 - one structure regardless of source kind."""

    def setUp(self) -> None:
        self.plugin = load_plugin(PLUGIN_MODULE_PATH)

    def test_every_source_kind_produces_the_same_artifact_structure(self) -> None:
        structures = {}
        for kind, source in SOURCE_KIND_FIXTURES:
            artifact = DistillationEngine(self.plugin).distill([source])
            structures[kind] = (tuple(sorted(artifact)), artifact["artifact_version"])

        reference = structures["document"]
        for kind, structure in structures.items():
            self.assertEqual(structure[0], reference[0], kind)
            self.assertEqual(structure[1], "1.0.0", kind)

        self.assertEqual(set(reference[0]), set(ARTIFACT_SECTIONS))

    def test_mixed_source_kinds_populate_all_four_common_families(self) -> None:
        artifact = DistillationEngine(self.plugin).distill(list(ROLE_SOURCES))

        for family in COMMON_FAMILIES:
            self.assertTrue(artifact[family], family)

        referenced = {
            source_id
            for family in COMMON_FAMILIES
            for item in artifact[family]
            for source_id in item.get("source_ids", [])
        }
        self.assertEqual(
            referenced, {source.source_id for source in ROLE_SOURCES}
        )
        self.assertEqual(
            len(artifact["knowledge_unit"][0]["evidence_refs"][0]), 2
        )


if __name__ == "__main__":
    unittest.main()
