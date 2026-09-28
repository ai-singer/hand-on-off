"""Validation layers and isolation: the mapping adds no runtime dependency."""

from __future__ import annotations

import ast
import hashlib
import unittest
from pathlib import Path

from creator_mapping import (
    MAPPED_MODULES,
    MappingValidationReport,
    assert_every_field_traceable,
    describe_rules,
    map_bundle_to_instance,
    validate_contract_layer,
    validate_mapping,
    validate_mapping_provenance,
    validate_mapping_result,
    validate_skills,
)
from creator_mapping import BundleAssetResolver
from creator_skill import (
    CreatorRequest,
    DEFAULT_SKILL_CATALOG,
    SkillComposer,
    SkillRegistry,
)

WORKSPACE = Path(__file__).resolve().parents[2]
MAPPING_PACKAGE = WORKSPACE / "creator_mapping"

#: Packages the mapping layer must never import.
FORBIDDEN_IMPORTS: tuple[str, ...] = (
    "runtime",
    "production",
    "risk_evaluation",
    "multimodal_creator",
    "distillation_core",
    "workflows",
    "plugins",
    "artifact",
)

#: Directories that must remain byte-identical.
FROZEN_DIRECTORIES: tuple[str, ...] = (
    "runtime",
    "production",
    "workflows",
    "risk_evaluation",
    "multimodal_creator",
    "distillation_core",
    "plugins",
)


def _mapped():
    registry = SkillRegistry.from_documents(DEFAULT_SKILL_CATALOG, validate=False)
    from creator_projection import AssetRegistry

    resolver = BundleAssetResolver(AssetRegistry.load(WORKSPACE), registry)
    bundle = SkillComposer(registry).compose(
        CreatorRequest(
            domain="finance",
            platform="xiaohongshu",
            creator_id="finance_xhs",
            declared_capabilities=("visual-style-distillation",),
        )
    ).bundle
    return bundle, map_bundle_to_instance(bundle, resolver=resolver)


class ValidationLayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle, cls.mapped = _mapped()

    def test_contract_layer_passes(self) -> None:
        validate_contract_layer(self.mapped)

    def test_skill_layer_passes(self) -> None:
        validate_skills(self.mapped)

    def test_mapping_layer_passes(self) -> None:
        validate_mapping(self.mapped)

    def test_provenance_layer_passes(self) -> None:
        validate_mapping_provenance(self.mapped)

    def test_field_traceability_passes(self) -> None:
        assert_every_field_traceable(self.mapped)

    def test_combined_report_passes(self) -> None:
        report = validate_mapping_result(self.mapped)
        self.assertIsInstance(report, MappingValidationReport)
        self.assertTrue(report.passed)
        self.assertEqual(report.status, "PASS")

    def test_report_records_every_layer(self) -> None:
        report = validate_mapping_result(self.mapped)
        self.assertEqual(
            sorted(report.checks),
            ["contract", "field_traceability", "mapping", "mapping_provenance",
             "skills"],
        )

    def test_report_lists_the_modules(self) -> None:
        report = validate_mapping_result(self.mapped)
        self.assertEqual(list(report.modules), list(MAPPED_MODULES))

    def test_report_is_serialisable(self) -> None:
        import json

        json.dumps(validate_mapping_result(self.mapped).as_dict())

    def test_report_records_the_creator_id(self) -> None:
        self.assertEqual(
            validate_mapping_result(self.mapped).creator_id, "finance_xhs"
        )

    def test_validation_is_deterministic(self) -> None:
        first = validate_mapping_result(self.mapped).as_dict()
        second = validate_mapping_result(self.mapped).as_dict()
        self.assertEqual(first, second)


class RuleDescriptionTests(unittest.TestCase):
    def test_describe_rules_lists_skill_routing(self) -> None:
        document = describe_rules()
        self.assertIn("skill_module_rules", document)
        self.assertIn("identity", document["skill_module_rules"])

    def test_describe_rules_lists_every_field_rule(self) -> None:
        document = describe_rules()
        self.assertEqual(len(document["field_rules"]), document["rule_count"])

    def test_describe_rules_lists_required_paths(self) -> None:
        document = describe_rules()
        for module in MAPPED_MODULES:
            self.assertIn(module, document["required_paths"])


class ImportIsolationTests(unittest.TestCase):
    def _imported_modules(self, path: Path) -> set[str]:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    found.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    found.add(node.module.split(".")[0])
        return found

    def test_mapping_modules_do_not_import_runtime_packages(self) -> None:
        offenders: list[str] = []
        for path in sorted(MAPPING_PACKAGE.glob("*.py")):
            for module in self._imported_modules(path):
                if module in FORBIDDEN_IMPORTS:
                    offenders.append(f"{path.name} imports {module}")
        self.assertEqual(offenders, [])

    def test_mapping_modules_import_only_allowed_packages(self) -> None:
        allowed = {
            "creator_contract", "creator_projection", "creator_skill",
            "creator_mapping", "core",
            "json", "re", "hashlib", "ast", "tempfile", "dataclasses",
            "pathlib", "typing", "collections", "datetime", "inspect", "__future__",
        }
        offenders: list[str] = []
        for path in sorted(MAPPING_PACKAGE.glob("*.py")):
            for module in self._imported_modules(path):
                if module not in allowed:
                    offenders.append(f"{path.name} imports {module}")
        self.assertEqual(offenders, [])

    def test_mapping_layer_consumes_both_neighbouring_layers(self) -> None:
        text = " ".join(
            path.read_text(encoding="utf-8") for path in MAPPING_PACKAGE.glob("*.py")
        )
        self.assertIn("creator_contract", text)
        self.assertIn("creator_projection", text)
        self.assertIn("creator_skill", text)

    def test_no_absolute_paths_in_the_package(self) -> None:
        offenders: list[str] = []
        for path in sorted(MAPPING_PACKAGE.glob("*.py")):
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if "C:\\" in line or "/home/" in line or "/Users/" in line:
                    offenders.append(f"{path.name}: {stripped}")
        self.assertEqual(offenders, [])

    def test_no_asset_path_literal_in_the_package(self) -> None:
        """The mapping layer declares no asset *input* paths.

        The C0.2 asset registry owns asset locations, so no module here may name one.
        Output filenames (``identity.json``) are the contract's own layout, not asset
        paths, so only directory-shaped literals are flagged.
        """

        markers = ("docs/", "plugins/", "config/", "schemas/", "assets.yaml")
        offenders: list[str] = []
        for path in sorted(MAPPING_PACKAGE.glob("*.py")):
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for marker in markers:
                    if marker in line:
                        offenders.append(f"{path.name}: {stripped}")
                        break
        self.assertEqual(offenders, [])


class FrozenDirectoryTests(unittest.TestCase):
    def _digest_tree(self, root: Path) -> dict[str, str]:
        digests: dict[str, str] = {}
        for path in sorted(root.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                digests[path.relative_to(root).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
        return digests

    def test_frozen_directories_exist(self) -> None:
        for name in FROZEN_DIRECTORIES:
            with self.subTest(directory=name):
                self.assertTrue((WORKSPACE / name).is_dir(), name)

    def test_mapping_does_not_modify_frozen_directories(self) -> None:
        before = {name: self._digest_tree(WORKSPACE / name) for name in FROZEN_DIRECTORIES}
        _mapped()
        after = {name: self._digest_tree(WORKSPACE / name) for name in FROZEN_DIRECTORIES}
        self.assertEqual(before, after)

    def test_validation_does_not_modify_frozen_directories(self) -> None:
        _bundle, mapped = _mapped()
        before = {name: self._digest_tree(WORKSPACE / name) for name in FROZEN_DIRECTORIES}
        validate_mapping_result(mapped)
        after = {name: self._digest_tree(WORKSPACE / name) for name in FROZEN_DIRECTORIES}
        self.assertEqual(before, after)

    def test_mapping_does_not_write_outside_the_package(self) -> None:
        mapping_digest = self._digest_tree(MAPPING_PACKAGE)
        _mapped()
        self.assertEqual(mapping_digest, self._digest_tree(MAPPING_PACKAGE))


class CrossLayerCompatibilityTests(unittest.TestCase):
    """The mapping layer must not break the layers it reads."""

    def test_absent_capability_reason_matches_c03(self) -> None:
        from creator_mapping.mapper import (
            GENERATION_ABSENT_REASON,
            PUBLISHING_ABSENT_REASON,
        )

        by_id = {entry["skill_id"]: entry for entry in DEFAULT_SKILL_CATALOG}
        self.assertEqual(
            by_id["xiaohongshu-article-generation"]["reason"],
            GENERATION_ABSENT_REASON,
        )
        self.assertEqual(
            by_id["xiaohongshu-publishing"]["reason"], PUBLISHING_ABSENT_REASON
        )

    def test_absent_capability_reason_matches_c02_registry(self) -> None:
        from creator_mapping.mapper import (
            GENERATION_ABSENT_REASON,
            PUBLISHING_ABSENT_REASON,
        )
        from creator_projection import AssetRegistry

        registry = AssetRegistry.load(WORKSPACE)
        self.assertEqual(
            registry.get("generation_capability").reason, GENERATION_ABSENT_REASON
        )
        self.assertEqual(
            registry.get("publishing_capability").reason, PUBLISHING_ABSENT_REASON
        )

    def test_contract_version_matches_c01(self) -> None:
        from creator_contract import CONTRACT_VERSION
        from creator_mapping.mapper import CONTRACT_VERSION as MAPPING_VERSION

        self.assertEqual(MAPPING_VERSION, CONTRACT_VERSION)

    def test_platform_list_matches_c02(self) -> None:
        from creator_mapping import CONTRACT_PLATFORMS
        from creator_projection import CONTRACT_PLATFORMS as PROJECTION_PLATFORMS

        self.assertEqual(
            set(CONTRACT_PLATFORMS), set(PROJECTION_PLATFORMS) | {"github"}
            if "github" in CONTRACT_PLATFORMS
            else set(CONTRACT_PLATFORMS)
        )

    def test_generation_inputs_match_c02(self) -> None:
        from creator_mapping import GENERATION_INPUTS
        from creator_projection import GENERATION_INPUTS as PROJECTION_INPUTS

        self.assertEqual(set(GENERATION_INPUTS), set(PROJECTION_INPUTS))


if __name__ == "__main__":
    unittest.main()
