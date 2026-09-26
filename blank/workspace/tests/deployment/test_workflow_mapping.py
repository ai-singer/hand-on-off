from __future__ import annotations

import json
import unittest
from pathlib import Path

from workflows.lobster.runtime_adapter import (
    build_generation_handoff,
    distill_payload,
    evaluate_gate,
    normalize_source_input,
    verify_plugin_checkpoint,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = (
    WORKSPACE_ROOT / "workflows" / "lobster" / "content_distillation.lobster"
)
CONTRACT_PATH = WORKSPACE_ROOT / "workflows" / "lobster" / "node_contracts.json"
EXPECTED_ORDER = [
    "source_input",
    "unified_distillation",
    "creator_plugin_enhancement",
    "quality_gate",
    "content_generation",
]


class LobsterWorkflowMappingTests(unittest.TestCase):
    def test_node_order_and_contracts_are_complete(self) -> None:
        workflow = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
        contracts = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

        self.assertEqual(
            [step["id"] for step in workflow["steps"]],
            EXPECTED_ORDER,
        )
        self.assertEqual(
            [node["id"] for node in contracts["nodes"]],
            EXPECTED_ORDER,
        )
        for step in workflow["steps"]:
            self.assertTrue(step["command"])
        for node in contracts["nodes"]:
            self.assertTrue(
                {
                    "name",
                    "purpose",
                    "input",
                    "output",
                    "dependency",
                    "failure_behavior",
                }.issubset(node)
            )
        generation = workflow["steps"][-1]
        self.assertEqual(
            generation["condition"],
            "$quality_gate.json.can_continue",
        )

    def test_runtime_adapter_executes_safe_mapping(self) -> None:
        source_envelope = normalize_source_input(
            [
                {
                    "source_id": "safe-1",
                    "source_type": "data",
                    "content": (
                        "The company business model connects revenue, cash flow, "
                        "margin data, and earnings."
                    ),
                }
            ]
        )
        artifact_envelope = distill_payload(source_envelope)
        checked = verify_plugin_checkpoint(artifact_envelope)
        gate = evaluate_gate(checked)
        handoff = build_generation_handoff(gate)

        self.assertEqual(gate["decision"], "PASS")
        self.assertTrue(gate["can_continue"])
        self.assertEqual(handoff["status"], "ready_for_generation")


if __name__ == "__main__":
    unittest.main()
