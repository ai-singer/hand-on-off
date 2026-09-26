from __future__ import annotations

import re
import unittest

from skills.openclaw import discover_openclaw_skills, load_openclaw_skill


class OpenClawSkillAdapterTests(unittest.TestCase):
    def test_adapters_are_discoverable_loadable_and_versioned(self) -> None:
        adapters = discover_openclaw_skills()

        self.assertEqual(
            set(adapters),
            {"source-ingestion", "unified-distillation", "quality-review"},
        )
        for name, adapter in adapters.items():
            self.assertRegex(name, r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
            self.assertRegex(adapter.version, r"^\d+\.\d+\.\d+$")
            self.assertTrue(adapter.dependencies)
            self.assertTrue(adapter.runtime_requirements)
            self.assertTrue(adapter.test)
            self.assertIn(f"name: {name}", adapter.load_instructions())

    def test_single_adapter_can_be_loaded_by_name(self) -> None:
        adapter = load_openclaw_skill("quality-review")

        self.assertEqual(adapter.metadata["adapter_for"], "quality_review")
        self.assertEqual(adapter.entrypoint, "SKILL.md")
        self.assertTrue(re.fullmatch(r"\d+\.\d+\.\d+", adapter.version))


if __name__ == "__main__":
    unittest.main()
