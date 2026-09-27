from __future__ import annotations

import unittest

from core import load_plugin
from distillation_core import DistillationEngine

from ._fixtures import PLUGIN_MODULE_PATH, SECTION_FIXTURES, source


class DomainEnhancementTests(unittest.TestCase):
    """Step 3 - each distilled section is proven by its own fixture."""

    def setUp(self) -> None:
        self.plugin = load_plugin(PLUGIN_MODULE_PATH)

    def _extension(self, section: str) -> dict:
        artifact = DistillationEngine(self.plugin).distill(
            [source(SECTION_FIXTURES[section], source_id=section)]
        )
        return artifact["domain_extension"]

    def _assert_section(self, section: str) -> None:
        extension = self._extension(section)
        block = extension[section]

        self.assertTrue(block["matched"], section)
        self.assertTrue(block["signals"], section)
        self.assertEqual(block["source_ids"], [section])
        for signal in block["signals"]:
            self.assertEqual(signal["section"], section)
            self.assertEqual(signal["source_ids"], [section])
            self.assertTrue(signal["matched_terms"])

    # Test A - business mechanism
    def test_business_mechanism_is_distilled(self) -> None:
        self._assert_section("business_mechanism")

    # Test B - financial statement structure
    def test_financial_structure_is_distilled(self) -> None:
        self._assert_section("financial_structure")

    # Test C - data expression
    def test_data_expression_pattern_is_distilled(self) -> None:
        self._assert_section("data_expression_pattern")

    # Test D - case selection logic
    def test_case_selection_logic_is_distilled(self) -> None:
        self._assert_section("case_selection_logic")

    # Test E - misconception analysis
    def test_misconception_analysis_is_distilled(self) -> None:
        self._assert_section("misconception_analysis")

    def test_sections_are_independent_of_each_other(self) -> None:
        """A fixture for one section leaves the unrelated ones unmatched."""

        extension = self._extension("misconception_analysis")

        self.assertTrue(extension["misconception_analysis"]["matched"])
        self.assertFalse(extension["financial_structure"]["matched"])
        self.assertFalse(extension["data_expression_pattern"]["matched"])


if __name__ == "__main__":
    unittest.main()
