from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

# `runtime` is imported before `plugin_interface` on purpose: importing
# `plugin_interface` first trips a pre-existing circular import
# (plugin_interface.base -> core.models -> core.__init__ -> core.plugin_loader
# -> plugin_interface.base). Production code imports `core` first as well.
from runtime import RuntimeBootstrapError, bootstrap
from plugin_interface import PluginContribution, PluginIdentity
from workflows.lobster import runtime_adapter
from workflows.lobster.runtime_adapter import (
    build_generation_handoff,
    distill_payload,
    evaluate_gate,
    normalize_source_input,
    resolve_context,
    verify_plugin_checkpoint,
)


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = WORKSPACE_ROOT / "config" / "runtime" / "default.json"
DEFAULT_WORKFLOW = "workflows/lobster/content_distillation.lobster"
DEFAULT_SKILLS = ("source-ingestion", "unified-distillation", "quality-review")
STUB_MODULE = "plugins.lobster_integration_probe"

WORKFLOW_COMMANDS = (
    "source-input",
    "distill",
    "plugin-check",
    "gate",
    "generation-handoff",
)

SAFE_SOURCES = [
    {
        "source_id": "safe-1",
        "source_type": "data",
        "content": (
            "The company business model connects revenue, cash flow, "
            "margin data, and earnings."
        ),
    }
]


class _StubPlugin:
    def __init__(self, name: str, version: str = "0.1.0") -> None:
        self._identity = PluginIdentity(
            name=name,
            version=version,
            domain="probe",
            creator_target="probe-creator",
        )

    @property
    def identity(self) -> PluginIdentity:
        return self._identity

    def enhance(self, raw_sources, common_signals) -> PluginContribution:
        return PluginContribution(domain_extension={"schema_version": "1.0.0"})


def _write_config(directory: str | Path, **overrides: Any) -> Path:
    plugins = list(overrides.get("plugins", ["plugins.xiaolin_finance"]))
    payload = {
        "instance": {"name": overrides.get("instance", "lobster-integration")},
        "workflow": {"default": overrides.get("workflow", DEFAULT_WORKFLOW)},
        "plugins": {
            "enabled": plugins,
            "default": overrides.get("default_plugin", plugins[0]),
        },
        "skills": {"enabled": list(overrides.get("skills", DEFAULT_SKILLS))},
        "version": overrides.get("version", "1.0.0"),
    }
    path = Path(directory) / "runtime.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class LobsterBootstrapIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        module = types.ModuleType(STUB_MODULE)
        module.create_plugin = lambda: _StubPlugin("lobster-probe")  # type: ignore[attr-defined]
        sys.modules[STUB_MODULE] = module

    def tearDown(self) -> None:
        sys.modules.pop(STUB_MODULE, None)

    # Test 1 - Bootstrap -> Lobster Adapter
    def test_adapter_initializes_through_bootstrap(self) -> None:
        self.assertFalse(hasattr(runtime_adapter, "load_runtime_config"))
        self.assertFalse(hasattr(runtime_adapter, "load_plugin"))

        envelope = normalize_source_input(SAFE_SOURCES)
        with mock.patch.object(
            runtime_adapter, "bootstrap", wraps=runtime_adapter.bootstrap
        ) as spy:
            artifact_envelope = distill_payload(envelope)

        self.assertEqual(spy.call_count, 1)
        self.assertIn("artifact", artifact_envelope)

    def test_supplied_context_is_not_re_bootstrapped(self) -> None:
        context = bootstrap(DEFAULT_CONFIG)
        envelope = normalize_source_input(SAFE_SOURCES)

        with mock.patch.object(
            runtime_adapter,
            "bootstrap",
            side_effect=AssertionError("adapter must not re-read runtime config"),
        ) as spy:
            artifact_envelope = distill_payload(envelope, context=context)
            checked = verify_plugin_checkpoint(artifact_envelope, context=context)

        spy.assert_not_called()
        self.assertIn("artifact", checked)
        self.assertIs(resolve_context(context=context), context)

    # Test 2 - Runtime Config Plugin Selection
    def test_configured_plugin_is_the_one_the_workflow_uses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = _write_config(directory, plugins=[STUB_MODULE])

            envelope = normalize_source_input(SAFE_SOURCES)
            artifact_envelope = distill_payload(envelope, path)

            self.assertEqual(
                artifact_envelope["artifact"]["plugin"]["name"], "lobster-probe"
            )
            # The checkpoint accepts the artifact under the config that produced it.
            verify_plugin_checkpoint(artifact_envelope, path)

            # ...and rejects it under a config that selects a different plugin,
            # proving selection really comes from the runtime configuration.
            with self.assertRaises(ValueError):
                verify_plugin_checkpoint(artifact_envelope, DEFAULT_CONFIG)

    # Test 3 - Runtime Config Skill Selection
    def test_configured_skill_registry_matches_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = _write_config(directory, skills=["quality-review"])

            context = resolve_context(path)

            self.assertEqual(set(context.skills), {"quality-review"})
            self.assertEqual(set(context.skills), set(bootstrap(path).skills))

        self.assertEqual(set(bootstrap(DEFAULT_CONFIG).skills), set(DEFAULT_SKILLS))

    # Test 4 - Bootstrap Failure Propagation
    def test_invalid_config_propagates_without_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = _write_config(directory, version="2.0.0")
            envelope = normalize_source_input(SAFE_SOURCES)

            with self.assertRaises(RuntimeBootstrapError):
                distill_payload(envelope, path)
            with self.assertRaises(RuntimeBootstrapError):
                verify_plugin_checkpoint({"artifact": {}}, path)

    def test_cli_reports_bootstrap_failure_instead_of_running(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = _write_config(directory, version="2.0.0")
            stderr = io.StringIO()

            with mock.patch.dict(
                os.environ, {"LOBSTER_ARG_RUNTIME_CONFIG": str(path)}
            ), mock.patch.object(
                sys, "stdin", io.StringIO(json.dumps({"sources": SAFE_SOURCES}))
            ), mock.patch.object(
                sys, "stderr", stderr
            ):
                code = runtime_adapter.main(["distill"])

        self.assertEqual(code, 1)
        self.assertIn("RuntimeBootstrapError", stderr.getvalue())
        self.assertIn("not compatible", stderr.getvalue())

    def test_workflow_binding_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            other = Path(directory) / "other.lobster"
            other.write_text(
                json.dumps(
                    {
                        "name": "other-workflow",
                        "steps": [{"id": "source_input", "command": "noop"}],
                    }
                ),
                encoding="utf-8",
            )
            path = _write_config(directory, workflow=str(other))
            stderr = io.StringIO()

            with mock.patch.dict(
                os.environ, {"LOBSTER_ARG_RUNTIME_CONFIG": str(path)}
            ), mock.patch.object(
                sys, "stdin", io.StringIO(json.dumps({"artifact": {}}))
            ), mock.patch.object(
                sys, "stderr", stderr
            ):
                code = runtime_adapter.main(["gate"])

        self.assertEqual(code, 1)
        self.assertIn("does not declare node", stderr.getvalue())

    # Test 5 - End-to-End Dry Run
    def test_end_to_end_dry_run_shares_one_context(self) -> None:
        context = bootstrap(DEFAULT_CONFIG)

        envelope = normalize_source_input(SAFE_SOURCES)
        distilled = distill_payload(envelope, context=context)
        checked = verify_plugin_checkpoint(distilled, context=context)
        gate = evaluate_gate(checked)
        handoff = build_generation_handoff(gate)

        self.assertEqual(
            distilled["artifact"]["plugin"]["name"],
            context.default_plugin.identity.name,
        )
        self.assertEqual(gate["decision"], "PASS")
        self.assertTrue(gate["can_continue"])
        self.assertEqual(handoff["status"], "ready_for_generation")

    def test_workflow_commands_run_as_separate_processes(self) -> None:
        """The real Lobster invocation chain, exactly as the workflow runs it."""

        env = {**os.environ, "LOBSTER_ARG_RUNTIME_CONFIG": str(DEFAULT_CONFIG)}
        payload = json.dumps({"sources": SAFE_SOURCES})
        outputs: dict[str, Any] = {}

        for command in WORKFLOW_COMMANDS:
            result = subprocess.run(
                [sys.executable, "-m", "workflows.lobster.runtime_adapter", command],
                input=payload,
                capture_output=True,
                text=True,
                cwd=str(WORKSPACE_ROOT),
                env=env,
                timeout=180,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs[command] = json.loads(result.stdout)
            payload = result.stdout

        self.assertEqual(outputs["gate"]["decision"], "PASS")
        self.assertTrue(outputs["gate"]["can_continue"])
        self.assertEqual(
            outputs["generation-handoff"]["status"], "ready_for_generation"
        )
        self.assertEqual(
            outputs["distill"]["artifact"]["plugin"]["name"],
            "xiaolin_finance",
        )


if __name__ == "__main__":
    unittest.main()
