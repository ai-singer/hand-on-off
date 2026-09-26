from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from config.runtime import load_runtime_config


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


class RuntimeConfigTests(unittest.TestCase):
    def test_default_config_loads_selected_runtime_components(self) -> None:
        config = load_runtime_config()

        self.assertEqual(config.instance.name, "creator-agent-template")
        self.assertEqual(config.plugins.default, "plugins.xiaolin_finance")
        self.assertIn(config.plugins.default, config.plugins.enabled)
        self.assertEqual(
            set(config.skills.enabled),
            {"source-ingestion", "unified-distillation", "quality-review"},
        )
        self.assertTrue((WORKSPACE_ROOT / config.workflow.default).is_file())
        self.assertEqual(config.version, "1.0.0")

    def test_future_plugin_can_be_selected_without_core_change(self) -> None:
        payload = {
            "instance": {"name": "technology-creator"},
            "workflow": {
                "default": "workflows/lobster/content_distillation.lobster"
            },
            "plugins": {
                "enabled": ["plugins.technology"],
                "default": "plugins.technology",
            },
            "skills": {
                "enabled": [
                    "source-ingestion",
                    "unified-distillation",
                    "quality-review",
                ]
            },
            "version": "1.1.0",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            config = load_runtime_config(path)

        self.assertEqual(config.plugins.default, "plugins.technology")
        self.assertEqual(config.version, "1.1.0")


if __name__ == "__main__":
    unittest.main()
