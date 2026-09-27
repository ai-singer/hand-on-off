from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from artifact.manifest import MANIFEST_NAME, generate_manifest, sha256_file
from artifact.validator import validate_artifact
from runtime import SUPPORTED_CONFIG_VERSION


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
FIXED_TIME = "2026-01-01T00:00:00Z"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_fixture(root: Path) -> None:
    """A minimal but structurally complete deployable artifact."""

    _write(root / "AGENTS.md", "# fixture agent contract\n")
    _write(
        root / "config" / "runtime" / "default.json",
        json.dumps(
            {
                "instance": {"name": "fixture-instance"},
                "workflow": {
                    "default": "workflows/lobster/content_distillation.lobster"
                },
                "plugins": {
                    "enabled": ["plugins.fixture_domain"],
                    "default": "plugins.fixture_domain",
                },
                "skills": {"enabled": ["fixture-skill"]},
                "version": "1.0.0",
            },
            indent=2,
        ),
    )
    _write(root / "plugins" / "fixture_domain" / "__init__.py", "PLUGIN = True\n")
    _write(
        root / "skills" / "openclaw" / "fixture-skill" / "manifest.json",
        json.dumps(
            {
                "name": "fixture-skill",
                "version": "1.0.0",
                "entrypoint": "SKILL.md",
                "capabilities": ["fixture"],
                "test_command": "python -m unittest -v",
            },
            indent=2,
        ),
    )
    _write(
        root / "skills" / "openclaw" / "fixture-skill" / "SKILL.md",
        "---\nname: fixture-skill\nversion: 1.0.0\n---\n",
    )
    _write(
        root / "workflows" / "lobster" / "content_distillation.lobster",
        json.dumps(
            {
                "name": "fixture-workflow",
                "steps": [{"id": "source_input", "command": "noop"}],
            },
            indent=2,
        ),
    )


def _fixture_artifact(directory: str | Path) -> Path:
    root = Path(directory) / "artifact"
    _build_fixture(root)
    generate_manifest(root, created_at=FIXED_TIME)
    return root


def _rules(result) -> set[str]:
    return {finding.rule for finding in result.findings}


class ArtifactManifestTests(unittest.TestCase):
    # Test 1 - Manifest generation
    def test_manifest_records_identity_runtime_and_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _fixture_artifact(directory)

            manifest = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))

            self.assertEqual(manifest["artifact_id"], "fixture-instance")
            self.assertEqual(manifest["version"], "1.0.0")
            self.assertEqual(manifest["created_at"], FIXED_TIME)
            self.assertEqual(manifest["runtime_version"], SUPPORTED_CONFIG_VERSION)
            self.assertEqual(manifest["config_version"], "1.0.0")
            self.assertEqual(manifest["enabled_plugins"], ["plugins.fixture_domain"])
            self.assertEqual(manifest["enabled_skills"], ["fixture-skill"])

            paths = [entry["path"] for entry in manifest["files"]]
            self.assertEqual(paths, sorted(paths))
            self.assertNotIn(MANIFEST_NAME, paths)
            self.assertIn("AGENTS.md", paths)

            entry = next(item for item in manifest["files"] if item["path"] == "AGENTS.md")
            self.assertEqual(entry["sha256"], sha256_file(root / "AGENTS.md"))
            self.assertEqual(entry["size"], (root / "AGENTS.md").stat().st_size)

    def test_manifest_stored_inside_artifact_excludes_itself(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "artifact"
            _build_fixture(root)

            generate_manifest(
                root, manifest_path=root / "nested" / "custom-manifest.json"
            )

            manifest = json.loads(
                (root / "nested" / "custom-manifest.json").read_text(encoding="utf-8")
            )
            paths = [entry["path"] for entry in manifest["files"]]
            self.assertNotIn("nested/custom-manifest.json", paths)
            result = validate_artifact(root, manifest_path=root / "nested" / "custom-manifest.json")
            self.assertTrue(result.ok, result.render())


class ArtifactValidationTests(unittest.TestCase):
    # Test 2 - Complete artifact
    def test_complete_artifact_validates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _fixture_artifact(directory)

            result = validate_artifact(root)

            self.assertTrue(result.ok, result.render())
            self.assertEqual(result.findings, ())

    # Test 3 - Missing declared file
    def test_missing_declared_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _fixture_artifact(directory)
            (root / "AGENTS.md").unlink()

            result = validate_artifact(root)

            self.assertFalse(result.ok)
            self.assertIn("file-missing", _rules(result))

    # Test 4 - Changed hash
    def test_changed_file_content_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _fixture_artifact(directory)
            with (root / "AGENTS.md").open("a", encoding="utf-8") as handle:
                handle.write("tampered\n")

            result = validate_artifact(root)

            self.assertFalse(result.ok)
            self.assertIn("hash-mismatch", _rules(result))
            self.assertIn("size-mismatch", _rules(result))

    # Test 5 - Missing plugin
    def test_missing_plugin_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _fixture_artifact(directory)
            shutil.rmtree(root / "plugins" / "fixture_domain")

            result = validate_artifact(root)

            self.assertFalse(result.ok)
            self.assertIn("plugin-missing", _rules(result))

    # Test 6 - Missing skill
    def test_missing_skill_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _fixture_artifact(directory)
            shutil.rmtree(root / "skills" / "openclaw" / "fixture-skill")

            result = validate_artifact(root)

            self.assertFalse(result.ok)
            self.assertIn("skill-missing", _rules(result))

    # Test 7 - Incompatible runtime version
    def test_incompatible_runtime_version_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "artifact"
            _build_fixture(root)
            generate_manifest(root, created_at=FIXED_TIME, runtime_version="2.0.0")

            result = validate_artifact(root)

            self.assertFalse(result.ok)
            self.assertIn("runtime-incompatible", _rules(result))

    def test_runtime_version_mismatch_in_either_direction_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _fixture_artifact(directory)

            result = validate_artifact(root, runtime_version="2.0.0")

            self.assertFalse(result.ok)
            self.assertIn("runtime-incompatible", _rules(result))


class ArtifactIntegrityTests(unittest.TestCase):
    def test_missing_manifest_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "artifact"
            _build_fixture(root)

            result = validate_artifact(root)

            self.assertFalse(result.ok)
            self.assertEqual(_rules(result), {"manifest-missing"})

    def test_structurally_invalid_manifest_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _fixture_artifact(directory)
            payload = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
            del payload["runtime_version"]
            payload["unexpected_field"] = True
            (root / MANIFEST_NAME).write_text(json.dumps(payload), encoding="utf-8")

            result = validate_artifact(root)

            self.assertFalse(result.ok)
            self.assertEqual(_rules(result), {"manifest-invalid"})

    def test_undeclared_extra_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _fixture_artifact(directory)
            _write(root / "smuggled.txt", "not declared\n")

            result = validate_artifact(root)

            self.assertFalse(result.ok)
            self.assertIn("extra-file", _rules(result))

    def test_config_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _fixture_artifact(directory)
            config_path = root / "config" / "runtime" / "default.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["skills"] = {"enabled": ["other-skill"]}
            config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

            result = validate_artifact(root)

            self.assertFalse(result.ok)
            self.assertIn("config-mismatch", _rules(result))

    def test_missing_runtime_config_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _fixture_artifact(directory)
            (root / "config" / "runtime" / "default.json").unlink()

            result = validate_artifact(root)

            self.assertFalse(result.ok)
            self.assertIn("config-missing", _rules(result))


class RealWorkspaceArtifactTests(unittest.TestCase):
    """Integration evidence: the shipped workspace is a valid artifact."""

    def test_workspace_round_trip_validates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "workspace-manifest.json"

            generate_manifest(
                WORKSPACE_ROOT, manifest_path=manifest_path, created_at=FIXED_TIME
            )
            result = validate_artifact(WORKSPACE_ROOT, manifest_path=manifest_path)

            self.assertTrue(result.ok, result.render())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifact_id"], "creator-agent-template")
            self.assertEqual(
                manifest["enabled_plugins"], ["plugins.xiaolin_finance"]
            )
            self.assertEqual(
                sorted(manifest["enabled_skills"]),
                ["quality-review", "source-ingestion", "unified-distillation"],
            )

    def test_packaging_excludes_are_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "workspace-manifest.json"

            generate_manifest(
                WORKSPACE_ROOT,
                manifest_path=manifest_path,
                created_at=FIXED_TIME,
                exclude=("tests",),
            )

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            paths = [entry["path"] for entry in manifest["files"]]
            self.assertFalse([path for path in paths if path.startswith("tests/")])
            self.assertTrue(any(path.startswith("artifact/") for path in paths))


if __name__ == "__main__":
    unittest.main()
