"""Isolation: the loader adds no runtime dependency and writes nothing at all.

Two claims are checked mechanically rather than by inspection:

1. **No forbidden import.** The package's modules are parsed with :mod:`ast` and
   every import is checked against the packages this programme forbids.
2. **Nothing outside the package changes.** Frozen directories are digested before
   and after a load, so "the loader is read-only" is a measurement, not a promise.

The loader is the first layer in this programme whose whole job is reading, so it
carries the strongest version of the second claim: it must not write *anywhere*.
"""

from __future__ import annotations

import ast
import hashlib
import unittest
from pathlib import Path

from creator_loader import (
    load_creator_instance,
    read_artifact,
    trace_instance,
    validate_instance,
    validate_loaded,
)

from . import fixtures

WORKSPACE = Path(__file__).resolve().parents[2]
LOADER_PACKAGE = WORKSPACE / "creator_loader"

#: Packages the loader must never import.
FORBIDDEN_IMPORTS: tuple[str, ...] = (
    "runtime",
    "production",
    "risk_evaluation",
    "multimodal_creator",
    "distillation_core",
    "workflows",
    "plugins",
    "artifact",
    "lobster",
    "subprocess",
    "socket",
    "urllib",
    "http",
    "requests",
    "openai",
    "anthropic",
    "transformers",
    "torch",
    "PIL",
    "numpy",
    "pandas",
    "yaml",
)

#: Directories that must remain byte-identical across a load.
FROZEN_DIRECTORIES: tuple[str, ...] = (
    "runtime",
    "production",
    "workflows",
    "risk_evaluation",
    "multimodal_creator",
    "distillation_core",
    "plugins",
)

#: The loader's own files.
LOADER_FILES: tuple[str, ...] = (
    "__init__.py",
    "errors.py",
    "loader.py",
    "model.py",
    "provenance.py",
    "resolver.py",
    "validation.py",
)


def imported_roots(path: Path) -> set[str]:
    """Every top-level module name one file imports."""

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


def digest_tree(root: Path) -> dict[str, str]:
    """SHA256 every file under ``root``, keyed by relative posix path."""

    digests: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            digests[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return digests


class PackageShapeTests(unittest.TestCase):
    """The package is exactly the seven modules the brief specifies."""

    def test_the_package_exists(self) -> None:
        self.assertTrue(LOADER_PACKAGE.is_dir())

    def test_every_specified_file_exists(self) -> None:
        for name in LOADER_FILES:
            self.assertTrue((LOADER_PACKAGE / name).is_file(), name)

    def test_the_package_has_no_extra_modules(self) -> None:
        present = sorted(path.name for path in LOADER_PACKAGE.glob("*.py"))
        self.assertEqual(present, sorted(LOADER_FILES))

    def test_the_package_has_no_subpackages(self) -> None:
        subpackages = [
            path.name
            for path in LOADER_PACKAGE.iterdir()
            if path.is_dir() and path.name != "__pycache__"
        ]
        self.assertEqual(subpackages, [])

    def test_every_module_declares_its_exports(self) -> None:
        for name in LOADER_FILES:
            text = (LOADER_PACKAGE / name).read_text(encoding="utf-8")
            self.assertIn("__all__", text, name)

    def test_every_module_has_a_docstring(self) -> None:
        for name in LOADER_FILES:
            tree = ast.parse((LOADER_PACKAGE / name).read_text(encoding="utf-8"))
            self.assertIsNotNone(ast.get_docstring(tree), name)

    def test_every_module_uses_future_annotations(self) -> None:
        for name in LOADER_FILES:
            text = (LOADER_PACKAGE / name).read_text(encoding="utf-8")
            self.assertIn("from __future__ import annotations", text, name)


class ImportIsolationTests(unittest.TestCase):
    """The loader imports nothing that could run, reach out, or generate."""

    def test_no_module_imports_a_forbidden_package(self) -> None:
        offenders: list[str] = []
        for name in LOADER_FILES:
            for module in imported_roots(LOADER_PACKAGE / name):
                if module in FORBIDDEN_IMPORTS:
                    offenders.append(f"{name} imports {module}")
        self.assertEqual(offenders, [])

    def test_no_module_imports_anything_outside_the_allowed_set(self) -> None:
        allowed = {
            # The layers this one reads.
            "creator_contract",
            "creator_projection",
            "creator_mapping",
            "creator_skill",
            "creator_loader",
            # Standard library only.
            "json",
            "re",
            "dataclasses",
            "enum",
            "pathlib",
            "types",
            "typing",
            "collections",
            "__future__",
        }
        offenders: list[str] = []
        for name in LOADER_FILES:
            for module in imported_roots(LOADER_PACKAGE / name):
                if module not in allowed:
                    offenders.append(f"{name} imports {module}")
        self.assertEqual(offenders, [])

    def test_the_package_imports_no_third_party_library(self) -> None:
        """The project declares no dependencies, so nothing here may need one."""

        third_party = {"yaml", "numpy", "pandas", "requests", "pytest"}
        offenders: list[str] = []
        for name in LOADER_FILES:
            offenders.extend(
                f"{name} imports {module}"
                for module in imported_roots(LOADER_PACKAGE / name)
                if module in third_party
            )
        self.assertEqual(offenders, [])

    def test_the_package_consumes_the_layers_it_reads(self) -> None:
        text = " ".join(
            (LOADER_PACKAGE / name).read_text(encoding="utf-8")
            for name in LOADER_FILES
        )
        for module in ("creator_contract", "creator_mapping", "creator_projection"):
            self.assertIn(module, text)

    def test_no_module_calls_a_model_client(self) -> None:
        markers = ("openai", "anthropic", "chat.completions", "generate_content")
        offenders: list[str] = []
        for name in LOADER_FILES:
            text = (LOADER_PACKAGE / name).read_text(encoding="utf-8")
            offenders.extend(
                f"{name}: {marker}" for marker in markers if marker in text
            )
        self.assertEqual(offenders, [])

    def test_no_module_opens_a_network_connection(self) -> None:
        markers = ("urllib", "requests.", "socket.", "http.client")
        offenders: list[str] = []
        for name in LOADER_FILES:
            text = (LOADER_PACKAGE / name).read_text(encoding="utf-8")
            offenders.extend(
                f"{name}: {marker}" for marker in markers if marker in text
            )
        self.assertEqual(offenders, [])

    def test_no_module_writes_a_file(self) -> None:
        """The loader is read-only: no write, replace, unlink, mkdir, or open-for-write."""

        write_markers = (
            "write_text(",
            "write_bytes(",
            ".replace(",
            ".unlink(",
            ".mkdir(",
            ".touch(",
            "open(",
            "shutil",
        )
        offenders: list[str] = []
        for name in LOADER_FILES:
            for number, line in enumerate(
                (LOADER_PACKAGE / name).read_text(encoding="utf-8").splitlines(), 1
            ):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for marker in write_markers:
                    if marker in line and "read_text" not in line:
                        offenders.append(f"{name}:{number}: {stripped}")
                        break
        self.assertEqual(offenders, [])

    def test_no_module_removes_a_field(self) -> None:
        """Nothing in the loader deletes from an artifact."""

        offenders: list[str] = []
        for name in LOADER_FILES:
            for number, line in enumerate(
                (LOADER_PACKAGE / name).read_text(encoding="utf-8").splitlines(), 1
            ):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if stripped.startswith("del ") or ".pop(" in line:
                    offenders.append(f"{name}:{number}: {stripped}")
        self.assertEqual(offenders, [])

    def test_no_module_enables_a_capability(self) -> None:
        """No assignment may set an ``enabled`` key true."""

        offenders: list[str] = []
        for name in LOADER_FILES:
            for number, line in enumerate(
                (LOADER_PACKAGE / name).read_text(encoding="utf-8").splitlines(), 1
            ):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if '"enabled"' in stripped and "True" in stripped and "=" in stripped:
                    offenders.append(f"{name}:{number}: {stripped}")
        self.assertEqual(offenders, [])

    def test_no_absolute_path_in_the_package(self) -> None:
        offenders: list[str] = []
        for name in LOADER_FILES:
            for number, line in enumerate(
                (LOADER_PACKAGE / name).read_text(encoding="utf-8").splitlines(), 1
            ):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if "C:\\" in line or "/home/" in line or "/Users/" in line:
                    offenders.append(f"{name}:{number}: {stripped}")
        self.assertEqual(offenders, [])

    def test_no_asset_path_literal_in_the_package(self) -> None:
        """The registry owns asset locations; the loader must not name one."""

        markers = ("docs/", "plugins/", "config/", "schemas/", "assets.yaml",
                   "visual_profile.yaml")
        offenders: list[str] = []
        for name in LOADER_FILES:
            for number, line in enumerate(
                (LOADER_PACKAGE / name).read_text(encoding="utf-8").splitlines(), 1
            ):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for marker in markers:
                    if marker in line:
                        offenders.append(f"{name}:{number}: {stripped}")
                        break
        self.assertEqual(offenders, [])


class FrozenDirectoryTests(unittest.TestCase):
    """A load changes nothing in the directories the programme protects."""

    def test_the_frozen_directories_exist(self) -> None:
        for name in FROZEN_DIRECTORIES:
            self.assertTrue((WORKSPACE / name).is_dir(), name)

    def test_loading_does_not_modify_a_frozen_directory(self) -> None:
        directory = fixtures.write_mapped("isolation_frozen")
        before = {name: digest_tree(WORKSPACE / name) for name in FROZEN_DIRECTORIES}
        load_creator_instance(directory)
        after = {name: digest_tree(WORKSPACE / name) for name in FROZEN_DIRECTORIES}
        self.assertEqual(before, after)

    def test_reading_does_not_modify_a_frozen_directory(self) -> None:
        directory = fixtures.write_mapped("isolation_frozen2")
        before = {name: digest_tree(WORKSPACE / name) for name in FROZEN_DIRECTORIES}
        read_artifact(directory)
        after = {name: digest_tree(WORKSPACE / name) for name in FROZEN_DIRECTORIES}
        self.assertEqual(before, after)

    def test_validating_does_not_modify_a_frozen_directory(self) -> None:
        document = read_artifact(fixtures.write_mapped("isolation_frozen3"))
        before = {name: digest_tree(WORKSPACE / name) for name in FROZEN_DIRECTORIES}
        validate_instance(document)
        after = {name: digest_tree(WORKSPACE / name) for name in FROZEN_DIRECTORIES}
        self.assertEqual(before, after)

    def test_tracing_does_not_modify_a_frozen_directory(self) -> None:
        loaded = load_creator_instance(fixtures.write_mapped("isolation_frozen4"))
        before = {name: digest_tree(WORKSPACE / name) for name in FROZEN_DIRECTORIES}
        trace_instance(loaded)
        after = {name: digest_tree(WORKSPACE / name) for name in FROZEN_DIRECTORIES}
        self.assertEqual(before, after)

    def test_loading_does_not_modify_the_loader_package(self) -> None:
        directory = fixtures.write_mapped("isolation_self")
        before = digest_tree(LOADER_PACKAGE)
        load_creator_instance(directory)
        self.assertEqual(digest_tree(LOADER_PACKAGE), before)

    def test_loading_does_not_modify_the_creator_contract_package(self) -> None:
        directory = fixtures.write_mapped("isolation_contract")
        target = WORKSPACE / "creator_contract"
        before = digest_tree(target)
        load_creator_instance(directory)
        self.assertEqual(digest_tree(target), before)

    def test_loading_does_not_modify_the_creator_mapping_package(self) -> None:
        directory = fixtures.write_mapped("isolation_mapping")
        target = WORKSPACE / "creator_mapping"
        before = digest_tree(target)
        load_creator_instance(directory)
        self.assertEqual(digest_tree(target), before)

    def test_loading_does_not_modify_the_creator_projection_package(self) -> None:
        directory = fixtures.write_mapped("isolation_projection")
        target = WORKSPACE / "creator_projection"
        before = digest_tree(target)
        load_creator_instance(directory)
        self.assertEqual(digest_tree(target), before)

    def test_loading_does_not_modify_the_workspace_instance_directory(self) -> None:
        directory = fixtures.write_mapped("isolation_instance_root")
        target = WORKSPACE / "creator_instance"
        if not target.is_dir():  # pragma: no cover - present in this workspace
            self.skipTest("no workspace instance directory")
        before = digest_tree(target)
        load_creator_instance(directory)
        self.assertEqual(digest_tree(target), before)


class ArtifactReadOnlyTests(unittest.TestCase):
    """The artifact itself is byte-identical after every loader operation."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = fixtures.write_mapped("isolation_artifacts")
        cls.before = digest_tree(cls.directory)

    def test_loading_leaves_every_artifact_file_unchanged(self) -> None:
        load_creator_instance(self.directory)
        self.assertEqual(digest_tree(self.directory), self.before)

    def test_loading_creates_no_file(self) -> None:
        names = sorted(path.name for path in self.directory.iterdir())
        load_creator_instance(self.directory)
        self.assertEqual(sorted(path.name for path in self.directory.iterdir()), names)

    def test_a_failed_load_leaves_the_artifact_unchanged(self) -> None:
        from creator_loader import LoaderError

        broken = fixtures.scratch_dir("isolation_broken") / "finance_xhs"
        broken.mkdir()
        for path in self.directory.iterdir():
            if path.is_file():
                broken.joinpath(path.name).write_bytes(path.read_bytes())
        (broken / "instance.json").unlink()
        (broken / "visual_rules.json").unlink()
        before = digest_tree(broken)
        try:
            load_creator_instance(broken)
        except LoaderError:
            pass
        self.assertEqual(digest_tree(broken), before)

    def test_the_modules_layout_leaves_the_artifact_unchanged(self) -> None:
        load_creator_instance(self.directory, layout="modules")
        self.assertEqual(digest_tree(self.directory), self.before)

    def test_the_non_strict_load_leaves_the_artifact_unchanged(self) -> None:
        load_creator_instance(self.directory, strict=False)
        self.assertEqual(digest_tree(self.directory), self.before)

    def test_a_load_never_writes_a_pycache_into_the_artifact(self) -> None:
        load_creator_instance(self.directory)
        self.assertFalse((self.directory / "__pycache__").exists())

    def test_tracing_a_loaded_instance_changes_no_file(self) -> None:
        loaded = load_creator_instance(self.directory)
        trace_instance(loaded)
        self.assertEqual(digest_tree(self.directory), self.before)

    def test_validate_loaded_changes_no_file(self) -> None:
        loaded = load_creator_instance(self.directory)
        validate_loaded(loaded)
        self.assertEqual(digest_tree(self.directory), self.before)


class NoCapabilityEnablementTests(unittest.TestCase):
    """Across every artifact shape, the loader never enables a capability."""

    def test_a_mapped_instance_enables_nothing(self) -> None:
        loaded = load_creator_instance(fixtures.write_mapped("isolation_cap_mapped"))
        self.assertEqual(loaded.enabled_capabilities(), ())

    def test_a_projected_instance_enables_nothing(self) -> None:
        loaded = load_creator_instance(
            fixtures.write_projected("isolation_cap_projected")
        )
        self.assertEqual(loaded.enabled_capabilities(), ())

    def test_a_projected_directory_instance_enables_nothing(self) -> None:
        loaded = load_creator_instance(
            fixtures.write_projection_directory("isolation_cap_dir")
        )
        self.assertEqual(loaded.enabled_capabilities(), ())

    def test_a_non_strict_load_enables_nothing(self) -> None:
        loaded = load_creator_instance(
            fixtures.write_mapped("isolation_cap_non_strict"), strict=False
        )
        self.assertEqual(loaded.enabled_capabilities(), ())

    def test_the_capability_module_list_is_still_two(self) -> None:
        from creator_loader import CAPABILITY_MODULES

        self.assertEqual(CAPABILITY_MODULES, ("generation", "publishing"))

    def test_no_loaded_capability_reports_available_for_an_unavailable_asset(self) -> None:
        loaded = load_creator_instance(fixtures.write_mapped("isolation_cap_honest"))
        for module, capability in loaded.capabilities.items():
            if capability.asset_status == "unavailable":
                self.assertNotEqual(capability.state.value, "available", module)

    def test_the_loader_has_no_public_enable_function(self) -> None:
        import creator_loader

        for name in creator_loader.__all__:
            self.assertNotIn("enable", name.lower(), name)


class NoModelCallTests(unittest.TestCase):
    """Nothing in a load reaches a model, a network, or a generator."""

    def test_the_package_defines_no_generation_entry_point(self) -> None:
        import creator_loader

        for name in creator_loader.__all__:
            self.assertNotIn("generat", name.lower().replace("generation", ""), name)

    def test_no_public_name_suggests_execution(self) -> None:
        import creator_loader

        forbidden = ("run", "execute", "deploy", "publish", "render", "crawl")
        for name in creator_loader.__all__:
            for marker in forbidden:
                self.assertNotIn(marker, name.lower(), f"{name} contains {marker}")

    def test_no_public_name_suggests_a_model(self) -> None:
        import creator_loader

        forbidden = ("model_call", "prompt", "llm", "inference", "embedding")
        for name in creator_loader.__all__:
            for marker in forbidden:
                self.assertNotIn(marker, name.lower(), f"{name} contains {marker}")

    def test_a_load_makes_no_network_import_available(self) -> None:
        """If a load needed the network, the package would have to import it."""

        for name in LOADER_FILES:
            modules = imported_roots(LOADER_PACKAGE / name)
            for forbidden in ("socket", "urllib", "http", "requests"):
                self.assertNotIn(forbidden, modules, name)


class CrossLayerCompatibilityTests(unittest.TestCase):
    """The loader must not break the layers it reads."""

    def test_the_loaded_instance_still_satisfies_its_own_contract(self) -> None:
        from creator_contract import validate as contract_validate
        from creator_loader import thaw

        loaded = load_creator_instance(fixtures.write_mapped("isolation_contract_ok"))
        document = thaw(
            {
                "contract_version": loaded.contract_version,
                "provenance": loaded.raw_provenance,
                **{module: loaded.module(module) for module in loaded.modules},
            }
        )
        report = contract_validate(document)
        self.assertEqual(report.status, "PASS")

    def test_the_loaded_document_matches_what_the_loader_validated(self) -> None:
        """Reloading the aggregate the loader read gives the same verdict."""

        from creator_loader import thaw

        loaded = load_creator_instance(fixtures.write_mapped("isolation_contract_ok2"))
        document = thaw(
            {
                "contract_version": loaded.contract_version,
                "provenance": loaded.raw_provenance,
                **{module: loaded.module(module) for module in loaded.modules},
            }
        )
        self.assertEqual(validate_instance(document), dict(loaded.validation))

    def test_the_loaded_field_traces_still_match_the_mapping_rules(self) -> None:
        from creator_mapping import rule_ids

        loaded = load_creator_instance(fixtures.write_mapped("isolation_rules"))
        known = set(rule_ids())
        for trace in loaded.provenance.field_traces.values():
            self.assertIn(trace.rule_id, known, trace.field)

    def test_the_loaded_assets_still_come_from_the_projection_registry(self) -> None:
        from creator_projection import AssetRegistry

        loaded = load_creator_instance(fixtures.write_mapped("isolation_registry"))
        registry = AssetRegistry.load(fixtures.WORKSPACE)
        for asset_id, reference in loaded.asset_references.items():
            self.assertEqual(reference.registered, asset_id in registry.ids(), asset_id)

    def test_the_loader_does_not_import_the_skill_layer_at_runtime(self) -> None:
        """Skills are read through the artifact, not re-composed by the loader."""

        for name in LOADER_FILES:
            self.assertNotIn(
                "creator_skill", imported_roots(LOADER_PACKAGE / name), name
            )


if __name__ == "__main__":
    unittest.main()
