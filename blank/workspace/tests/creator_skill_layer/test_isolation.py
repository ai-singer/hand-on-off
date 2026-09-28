"""Isolation: the skill layer adds no runtime dependency and reads no runtime code."""

from __future__ import annotations

import ast
import hashlib
import unittest
from pathlib import Path

from creator_skill import DEFAULT_SKILL_CATALOG, SkillRegistry
from creator_skill.catalog import catalog_asset_references

WORKSPACE = Path(__file__).resolve().parents[2]
SKILL_PACKAGE = WORKSPACE / "creator_skill"

#: Packages the skill layer must never import. These are the phases C0.3 is
#: forbidden from touching.
FORBIDDEN_IMPORTS: tuple[str, ...] = (
    "runtime",
    "production",
    "risk_evaluation",
    "multimodal_creator",
    "distillation_core",
    "workflows",
    "plugins",
    "artifact",
    "security",
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


def _imported_modules(path: Path) -> set[str]:
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


def _digest_tree(root: Path) -> dict[str, str]:
    digests: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            digests[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return digests


class ImportIsolationTests(unittest.TestCase):
    def test_skill_modules_do_not_import_runtime_packages(self) -> None:
        offenders: list[str] = []
        for path in sorted(SKILL_PACKAGE.glob("*.py")):
            for module in _imported_modules(path):
                if module in FORBIDDEN_IMPORTS:
                    offenders.append(f"{path.name} imports {module}")
        self.assertEqual(offenders, [])

    def test_skill_package_imports_only_contract_and_projection(self) -> None:
        local = {"creator_contract", "creator_projection", "creator_skill", "core"}
        offenders: list[str] = []
        for path in sorted(SKILL_PACKAGE.glob("*.py")):
            for module in _imported_modules(path):
                if module in FORBIDDEN_IMPORTS:
                    continue
                if module in {"json", "re", "hashlib", "ast", "tempfile", "dataclasses",
                              "pathlib", "typing", "collections", "datetime", "__future__"}:
                    continue
                if module not in local:
                    offenders.append(f"{path.name} imports {module}")
        self.assertEqual(offenders, [])

    def test_skill_layer_depends_on_the_projection_layer(self) -> None:
        """C0.3 maps existing assets, so it must actually read them."""

        text = " ".join(
            path.read_text(encoding="utf-8") for path in SKILL_PACKAGE.glob("*.py")
        )
        self.assertIn("creator_projection", text)


class FrozenDirectoryTests(unittest.TestCase):
    """The forbidden directories must be untouched by this phase."""

    def test_frozen_directories_exist(self) -> None:
        for name in FROZEN_DIRECTORIES:
            with self.subTest(directory=name):
                self.assertTrue((WORKSPACE / name).is_dir(), name)

    def test_skill_layer_writes_nothing_outside_itself(self) -> None:
        before = {
            name: _digest_tree(WORKSPACE / name) for name in FROZEN_DIRECTORIES
        }
        registry = SkillRegistry.from_documents(DEFAULT_SKILL_CATALOG, validate=False)
        for skill_id in registry.ids():
            registry.validate_dependency(skill_id)
        registry.list_available()
        registry.topological_order()
        after = {name: _digest_tree(WORKSPACE / name) for name in FROZEN_DIRECTORIES}
        self.assertEqual(before, after)

    def test_composition_does_not_modify_frozen_directories(self) -> None:
        from creator_skill import CreatorRequest, SkillComposer

        before = {name: _digest_tree(WORKSPACE / name) for name in FROZEN_DIRECTORIES}
        composer = SkillComposer(
            SkillRegistry.from_documents(DEFAULT_SKILL_CATALOG, validate=False)
        )
        composer.compose(CreatorRequest(domain="finance", platform="xiaohongshu"))
        after = {name: _digest_tree(WORKSPACE / name) for name in FROZEN_DIRECTORIES}
        self.assertEqual(before, after)


class CatalogAssetBindingTests(unittest.TestCase):
    """Every catalog skill is bound to a real, registered asset."""

    @classmethod
    def setUpClass(cls) -> None:
        import creator_projection as projection

        cls.asset_ids = set(projection.AssetRegistry.load(WORKSPACE).ids())

    def test_every_catalog_source_ref_is_registered(self) -> None:
        for reference in catalog_asset_references():
            with self.subTest(asset=reference):
                self.assertIn(reference, self.asset_ids)

    def test_catalog_does_not_reference_unavailable_assets_as_available(self) -> None:
        """A skill whose asset is unavailable must not claim to be available."""

        import creator_projection as projection

        registry = projection.AssetRegistry.load(WORKSPACE)
        for entry in DEFAULT_SKILL_CATALOG:
            reference = entry["provenance"]["source_ref"]
            if reference not in self.asset_ids:
                continue
            asset = registry.get(reference)
            if asset.available:
                continue
            with self.subTest(skill=entry["skill_id"], asset=reference):
                self.assertNotEqual(
                    entry["status"],
                    "available",
                    f"{entry['skill_id']} claims available but asset {reference} is "
                    f"unavailable ({asset.reason})",
                )

    def test_the_three_absent_capabilities_are_declared_not_available(self) -> None:
        by_id = {entry["skill_id"]: entry for entry in DEFAULT_SKILL_CATALOG}
        for skill_id in (
            "xiaohongshu-source",
            "xiaohongshu-article-generation",
            "xiaohongshu-publishing",
        ):
            with self.subTest(skill=skill_id):
                self.assertNotEqual(by_id[skill_id]["status"], "available")

    def test_visual_skill_binds_to_the_m5_profile(self) -> None:
        by_id = {entry["skill_id"]: entry for entry in DEFAULT_SKILL_CATALOG}
        provenance = by_id["visual-style-distillation"]["provenance"]
        self.assertEqual(provenance["source_kind"], "distillation_artifact")
        self.assertEqual(provenance["source_ref"], "visual_profile_m5")

    def test_text_skill_binds_to_the_structure_templates(self) -> None:
        by_id = {entry["skill_id"]: entry for entry in DEFAULT_SKILL_CATALOG}
        self.assertEqual(
            by_id["text-distillation"]["provenance"]["source_ref"],
            "text_structure_templates",
        )

    def test_risk_skill_binds_to_the_filter_rules(self) -> None:
        by_id = {entry["skill_id"]: entry for entry in DEFAULT_SKILL_CATALOG}
        self.assertEqual(
            by_id["finance-risk-review"]["provenance"]["source_ref"],
            "risk_policy_reference",
        )


class NoHardCodedPathTests(unittest.TestCase):
    """The registry must not hard-code skill file paths."""

    def test_skill_modules_contain_no_absolute_paths(self) -> None:
        offenders: list[str] = []
        for path in sorted(SKILL_PACKAGE.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if "C:\\" in line or "/home/" in line or "/Users/" in line:
                    offenders.append(f"{path.name}: {stripped}")
        self.assertEqual(offenders, [])

    def test_skill_modules_contain_no_skill_json_paths(self) -> None:
        """No module may name a skill *location*; the registry owns discovery.

        The schema filename and its ``$id`` URL are permitted - they name the
        schema artifact, not a skill file.
        """

        allowed = (
            "creator_skill.schema.json",
            "creator_skill_schema_",
            "skills/",
        )
        offenders: list[str] = []
        for path in sorted(SKILL_PACKAGE.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if ".json" in line and not any(token in line for token in allowed):
                    offenders.append(f"{path.name}: {stripped}")
        self.assertEqual(offenders, [])

    def test_skill_modules_do_not_embed_a_skill_path_string(self) -> None:
        """No module may hold a skill path literal, which is what ``skills/`` would be."""

        offenders: list[str] = []
        for path in sorted(SKILL_PACKAGE.glob("*.py")):
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if '"skills/' in line or "'skills/" in line:
                    if 'in lowered' in line or 'in text' in line:
                        continue
                    offenders.append(f"{path.name}: {stripped}")
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
