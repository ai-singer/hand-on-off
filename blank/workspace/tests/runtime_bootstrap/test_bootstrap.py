from __future__ import annotations

import json
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any

from core import RawSource, SourceType
from distillation_core import DistillationEngine
from plugin_interface import PluginContribution, PluginIdentity
from runtime import RuntimeBootstrapError, bootstrap
from workflows.content_distillation_pipeline import ContentDistillationPipeline


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKFLOW = "workflows/lobster/content_distillation.lobster"
DEFAULT_SKILLS = ("source-ingestion", "unified-distillation", "quality-review")
EXPECTED_STEPS = (
    "source_input",
    "unified_distillation",
    "creator_plugin_enhancement",
    "quality_gate",
    "content_generation",
)

STUB_ALPHA = "plugins.runtime_probe_alpha"
STUB_BETA = "plugins.runtime_probe_beta"
STUB_CLONE = "plugins.runtime_probe_clone"


class _StubPlugin:
    """Minimal Creator plugin used to prove configuration-driven selection."""

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


def _register_stub(module_path: str, identity_name: str) -> None:
    module = types.ModuleType(module_path)
    module.create_plugin = lambda: _StubPlugin(identity_name)  # type: ignore[attr-defined]
    sys.modules[module_path] = module


def _write_config(directory: str | Path, **overrides: Any) -> Path:
    plugins = list(overrides.get("plugins", ["plugins.xiaolin_finance"]))
    payload = {
        "instance": {"name": overrides.get("instance", "runtime-probe")},
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


def _partial_workspace(directory: str | Path, skill: str, drop: tuple[str, ...]):
    """Copy one real skill package into a throwaway workspace root."""

    root = Path(directory) / "workspace"
    target = root / "skills" / "openclaw" / skill
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(WORKSPACE_ROOT / "skills" / "openclaw" / skill, target)
    for name in drop:
        (target / name).unlink()
    return root


class RuntimeBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        _register_stub(STUB_ALPHA, "runtime-probe-alpha")
        _register_stub(STUB_BETA, "runtime-probe-beta")

    def tearDown(self) -> None:
        for module_path in (STUB_ALPHA, STUB_BETA, STUB_CLONE):
            sys.modules.pop(module_path, None)

    # Test 1 - Runtime Config Loading
    def test_runtime_config_enters_runtime_context(self) -> None:
        context = bootstrap()

        self.assertEqual(context.instance, "creator-agent-template")
        self.assertEqual(context.version, "1.0.0")
        self.assertEqual(context.config.instance.name, context.instance)
        self.assertEqual(context.config.version, context.version)
        self.assertEqual(context.workflow.name, "creator-agent-content-distillation")
        self.assertEqual(context.workflow.steps, EXPECTED_STEPS)

    # Test 2 - Plugin Selection
    def test_plugin_selection_follows_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lone = _write_config(directory, plugins=[STUB_ALPHA])
            context = bootstrap(lone)
            self.assertEqual(set(context.plugins), {STUB_ALPHA})
            self.assertEqual(context.default_plugin.identity.name, "runtime-probe-alpha")

        with tempfile.TemporaryDirectory() as directory:
            pair = _write_config(
                directory,
                plugins=["plugins.xiaolin_finance", STUB_BETA],
                default_plugin=STUB_BETA,
            )
            context = bootstrap(pair)
            self.assertEqual(
                set(context.plugins), {"plugins.xiaolin_finance", STUB_BETA}
            )
            self.assertEqual(context.default_plugin.identity.name, "runtime-probe-beta")
            self.assertNotIn(STUB_ALPHA, context.plugins)

    # Test 3 - Skill Selection
    def test_skill_selection_follows_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            single = _write_config(directory, skills=["source-ingestion"])
            context = bootstrap(single)
            self.assertEqual(set(context.skills), {"source-ingestion"})

        with tempfile.TemporaryDirectory() as directory:
            pair = _write_config(
                directory, skills=["quality-review", "unified-distillation"]
            )
            context = bootstrap(pair)
            self.assertEqual(
                set(context.skills), {"quality-review", "unified-distillation"}
            )
            self.assertNotIn("source-ingestion", context.skills)

        self.assertEqual(set(bootstrap().skills), set(DEFAULT_SKILLS))

    # Test 4 - Missing Skill Manifest
    def test_configured_skill_without_manifest_fails_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = _write_config(directory, skills=["not-a-real-skill"])
            with self.assertRaises(RuntimeBootstrapError) as caught:
                bootstrap(path)
        self.assertIn("no discoverable manifest.json", str(caught.exception))

    def test_removed_manifest_file_fails_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _partial_workspace(directory, "source-ingestion", ("manifest.json",))
            path = _write_config(
                directory,
                skills=["source-ingestion"],
                workflow=str(WORKSPACE_ROOT / DEFAULT_WORKFLOW),
            )
            with self.assertRaises(RuntimeBootstrapError) as caught:
                bootstrap(path, workspace_root=root)
        self.assertIn("no discoverable manifest.json", str(caught.exception))

    # Test 5 - Version Validation
    def test_incompatible_version_fails_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = _write_config(directory, version="2.0.0")
            with self.assertRaises(RuntimeBootstrapError) as caught:
                bootstrap(path)
        self.assertIn("not compatible", str(caught.exception))

        with tempfile.TemporaryDirectory() as directory:
            path = _write_config(directory, version="not-a-version")
            with self.assertRaises(RuntimeBootstrapError):
                bootstrap(path)

        with tempfile.TemporaryDirectory() as directory:
            path = _write_config(directory, version="1.4.7")
            self.assertEqual(bootstrap(path).version, "1.4.7")

    # Additional cross-validation
    def test_duplicate_plugin_identity_fails_bootstrap(self) -> None:
        _register_stub(STUB_CLONE, "runtime-probe-alpha")
        with tempfile.TemporaryDirectory() as directory:
            path = _write_config(directory, plugins=[STUB_ALPHA, STUB_CLONE])
            with self.assertRaises(RuntimeBootstrapError) as caught:
                bootstrap(path)
        self.assertIn("claimed by both", str(caught.exception))

    def test_unknown_plugin_module_fails_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = _write_config(directory, plugins=["plugins.does_not_exist"])
            with self.assertRaises(RuntimeBootstrapError) as caught:
                bootstrap(path)
        self.assertIn("cannot load configured plugin", str(caught.exception))

    def test_missing_workflow_definition_fails_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = _write_config(directory, workflow="workflows/missing.lobster")
            with self.assertRaises(RuntimeBootstrapError) as caught:
                bootstrap(path)
        self.assertIn("does not exist", str(caught.exception))

    def test_manifest_and_adapter_drift_fails_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _partial_workspace(directory, "source-ingestion", ())
            manifest_path = (
                root / "skills" / "openclaw" / "source-ingestion" / "manifest.json"
            )
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            payload["version"] = "9.9.9"
            manifest_path.write_text(json.dumps(payload), encoding="utf-8")
            path = _write_config(
                directory,
                skills=["source-ingestion"],
                workflow=str(WORKSPACE_ROOT / DEFAULT_WORKFLOW),
            )
            with self.assertRaises(RuntimeBootstrapError) as caught:
                bootstrap(path, workspace_root=root)
        self.assertIn("disagree", str(caught.exception))

    def test_test_packages_do_not_shadow_workspace_packages(self) -> None:
        """Guard the discovery hazard that shapes this package's name.

        `python -m unittest discover -s tests` puts `tests/` at sys.path[0],
        so a `tests/<name>/` package matching a workspace top-level package
        shadows the real module: every import of `<name>` inside it resolves to
        the test package instead. This module therefore lives in
        `tests/runtime_bootstrap` rather than `tests/runtime`.
        """

        top_level = {
            path.name
            for path in WORKSPACE_ROOT.iterdir()
            if path.is_dir() and (path / "__init__.py").is_file()
        }
        shadowing = sorted(
            path.name
            for path in (WORKSPACE_ROOT / "tests").iterdir()
            if path.is_dir()
            and (path / "__init__.py").is_file()
            and path.name in top_level
        )

        self.assertEqual(shadowing, [])

    def test_bootstrapped_context_executes_distillation(self) -> None:
        """Config -> bootstrap -> context -> component loading -> execution."""

        context = bootstrap()
        sources = [
            RawSource(
                source_id="doc-1",
                source_type=SourceType.DOCUMENT,
                content="Water changes state when temperature and pressure change.",
            )
        ]
        pipeline = ContentDistillationPipeline(
            DistillationEngine(context.default_plugin)
        )

        result = pipeline.run(sources)

        self.assertEqual(
            result.artifact["plugin"]["name"],
            context.default_plugin.identity.name,
        )
        self.assertEqual(
            result.artifact["plugin"]["version"],
            context.default_plugin.identity.version,
        )
        self.assertIn("status", result.quality_report)


if __name__ == "__main__":
    unittest.main()
