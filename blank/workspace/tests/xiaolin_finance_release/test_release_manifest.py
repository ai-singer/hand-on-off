from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path

from core import RawSource, SourceType, load_plugin
from core.schema_validation import validate_schema_instance
from distillation_core import DistillationEngine
from runtime import SUPPORTED_CONFIG_VERSION, bootstrap
from schema_validation import validate_runtime_schemas


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = WORKSPACE_ROOT / "plugins" / "xiaolin_finance"
PLUGIN_MODULE_PATH = "plugins.xiaolin_finance"
SHARED_SCHEMA_PATH = WORKSPACE_ROOT / "schemas" / "unified_distillation_artifact.json"
DOMAIN_SCHEMA_PATH = PLUGIN_ROOT / "schemas" / "domain_extension.schema.json"
SPEC_PATH = WORKSPACE_ROOT / "plugin_interface" / "creator_distillation_plugin_spec.md"

RELEASE_REQUIRED_FIELDS = {
    "name",
    "version",
    "framework_compatibility",
    "artifact_schema_version",
    "runtime_requirement",
    "capabilities",
}
RISK_REQUIRED_FIELDS = {"rule_id", "severity", "action", "message", "source_ids"}

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_CAPABILITY = re.compile(r"^(distill|prohibit|evaluate):[a-z0-9_]+$")
_PINNED = re.compile(r"^(?P<name>[a-z0-9-]+)@(?P<version>\d+(?:\.\d+){0,2})$")

RISK_SOURCE = RawSource(
    source_id="release-risk-1",
    source_type=SourceType.DOCUMENT,
    content="Company price will definitely rise.",
)
BENIGN_SOURCE = RawSource(
    source_id="release-benign-1",
    source_type=SourceType.DATA,
    content=(
        "The company business model links subscription revenue to "
        "cash flow and margin data."
    ),
)


def _load(relative_path: str) -> dict:
    return json.loads((PLUGIN_ROOT / relative_path).read_text(encoding="utf-8"))


def _release() -> dict:
    return _load("release.json")


def _manifest() -> dict:
    return _load("plugin.json")


def _rubric() -> dict:
    return _load("evaluation/rubric.json")


def _shared_schema() -> dict:
    return json.loads(SHARED_SCHEMA_PATH.read_text(encoding="utf-8"))


def _specification_version() -> str:
    for line in SPEC_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("Specification version:"):
            return line.split("`")[1]
    raise AssertionError("specification version not found")


class ReleaseManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.release = _release()

    # Test 1 - release.json is valid
    def test_release_manifest_is_valid(self) -> None:
        missing = RELEASE_REQUIRED_FIELDS - self.release.keys()
        self.assertEqual(missing, set())
        self.assertEqual(self.release["name"], "xiaolin_finance")
        self.assertRegex(self.release["version"], _SEMVER)

        capabilities = self.release["capabilities"]
        self.assertIsInstance(capabilities, list)
        self.assertTrue(capabilities)
        self.assertEqual(len(capabilities), len(set(capabilities)))
        for capability in capabilities:
            self.assertRegex(capability, _CAPABILITY)

    def test_capabilities_match_the_declared_taxonomy(self) -> None:
        capabilities = set(self.release["capabilities"])
        manifest = _manifest()
        rubric = _rubric()

        self.assertEqual(
            {item.split(":", 1)[1] for item in capabilities if item.startswith("distill:")},
            set(manifest["distills"]),
        )
        self.assertEqual(
            {item.split(":", 1)[1] for item in capabilities if item.startswith("prohibit:")},
            set(manifest["prohibits"]),
        )
        self.assertEqual(
            {item.split(":", 1)[1] for item in capabilities if item.startswith("evaluate:")},
            set(rubric["inherited_checks"]) | set(rubric["finance_checks"]),
        )

    # Test 2 - versions agree across every declaration
    def test_versions_agree_across_declarations(self) -> None:
        manifest = _manifest()
        rubric = _rubric()
        plugin = load_plugin(PLUGIN_MODULE_PATH)

        self.assertEqual(self.release["version"], manifest["plugin"]["version"])
        self.assertEqual(self.release["version"], plugin.identity.version)
        self.assertEqual(self.release["name"], plugin.identity.name)
        self.assertEqual(
            self.release["domain_contract_version"], manifest["domain_schema"]["version"]
        )
        self.assertEqual(manifest["evaluation"]["version"], rubric["version"])

        # Rule files version their own revisions, so their values need not equal
        # the plugin version; they must simply be valid and present.
        for relative_path in (
            "rules/value_rules.json",
            "rules/filter_rules.json",
            "rules/structure_templates.json",
            "evaluation/rubric.json",
        ):
            self.assertRegex(_load(relative_path)["version"], _SEMVER, relative_path)

    # Test 3 - declared schema compatibility matches reality
    def test_declared_schema_compatibility_matches_reality(self) -> None:
        plugin = load_plugin(PLUGIN_MODULE_PATH)
        artifact = DistillationEngine(plugin).distill([BENIGN_SOURCE])

        framework = _PINNED.fullmatch(self.release["framework_compatibility"])
        self.assertIsNotNone(framework, self.release["framework_compatibility"])
        self.assertEqual(framework.group("name"), "creator-distillation-plugin")
        self.assertEqual(framework.group("version"), _specification_version())

        runtime = _PINNED.fullmatch(self.release["runtime_requirement"])
        self.assertIsNotNone(runtime, self.release["runtime_requirement"])
        self.assertEqual(runtime.group("version"), SUPPORTED_CONFIG_VERSION)

        self.assertEqual(
            self.release["artifact_schema_version"], artifact["artifact_version"]
        )
        self.assertEqual(
            artifact["domain_extension"]["schema_version"],
            self.release["domain_contract_version"],
        )

        validation = validate_runtime_schemas(
            artifact, plugin=plugin, shared_schema_path=SHARED_SCHEMA_PATH
        )
        self.assertEqual(validation.status, "PASS")
        self.assertTrue(validation.domain_schema_applied)

    # Test 4 - the runtime loads the release plugin
    def test_runtime_loads_the_release_plugin(self) -> None:
        context = bootstrap()

        self.assertIn(PLUGIN_MODULE_PATH, context.plugins)
        plugin = context.default_plugin
        self.assertEqual(plugin.identity.name, self.release["name"])
        self.assertEqual(plugin.identity.version, self.release["version"])

        artifact = DistillationEngine(plugin).distill([BENIGN_SOURCE])
        self.assertEqual(artifact["plugin"]["version"], self.release["version"])
        self.assertEqual(
            artifact["domain_extension"]["plugin_identity"]["version"],
            self.release["version"],
        )


class ReleaseCompatibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plugin = load_plugin(PLUGIN_MODULE_PATH)

    # Test 5 - artifacts without the new field remain valid
    def test_artifacts_predating_the_new_field_remain_valid(self) -> None:
        artifact = DistillationEngine(self.plugin).distill([RISK_SOURCE])
        self.assertTrue(artifact["risk_constraints"])

        shared = _shared_schema()
        item_schema = shared["properties"]["risk_constraints"]["items"]
        self.assertNotIn("category", item_schema["required"])
        self.assertNotIn("category", item_schema["properties"])

        legacy = copy.deepcopy(artifact)
        for item in legacy["risk_constraints"]:
            item.pop("category", None)

        validate_schema_instance(legacy, SHARED_SCHEMA_PATH, root_name="artifact")
        self.assertEqual(legacy["artifact_version"], "1.0.0")

    def test_domain_extension_shape_is_unchanged_by_the_release(self) -> None:
        artifact = DistillationEngine(self.plugin).distill([BENIGN_SOURCE])
        declared = _manifest()["domain_schema"]["version"]
        release_contract = _release()["domain_contract_version"]

        self.assertEqual(declared, release_contract)
        self.assertEqual(artifact["domain_extension"]["schema_version"], release_contract)
        validate_schema_instance(
            artifact["domain_extension"],
            DOMAIN_SCHEMA_PATH,
            root_name="domain_extension",
        )

    # Test 6 - risk constraint fields stay compatible
    def test_risk_constraint_fields_stay_compatible(self) -> None:
        artifact = DistillationEngine(self.plugin).distill([RISK_SOURCE])
        prohibited = set(_manifest()["prohibits"])
        shared = _shared_schema()
        item_schema = shared["properties"]["risk_constraints"]["items"]

        self.assertEqual(set(item_schema["properties"]), RISK_REQUIRED_FIELDS)
        self.assertEqual(set(item_schema["required"]), RISK_REQUIRED_FIELDS)

        self.assertTrue(artifact["risk_constraints"])
        for item in artifact["risk_constraints"]:
            self.assertTrue(
                RISK_REQUIRED_FIELDS.issubset(item), sorted(item)
            )
            self.assertIn(item["category"], prohibited)
            self.assertIn(item["severity"], {"info", "warning", "block"})
            self.assertIn(
                item["action"],
                {"downrank", "require_evidence", "require_review", "block"},
            )

        minimal = copy.deepcopy(artifact)
        for item in minimal["risk_constraints"]:
            for field in set(item) - RISK_REQUIRED_FIELDS:
                item.pop(field)
        validate_schema_instance(minimal, SHARED_SCHEMA_PATH, root_name="artifact")


if __name__ == "__main__":
    unittest.main()
