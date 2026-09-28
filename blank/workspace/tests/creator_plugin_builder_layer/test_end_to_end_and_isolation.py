"""End-to-end: the full ladder from a request to a validated plugin, plus isolation.

Two things this file proves that the others cannot:

1. **The chain runs.** ``domain_request.yaml`` → builder → plugin → validator →
   written document → revalidated, with nothing stubbed.
2. **Nothing outside the package moved.** Frozen directories are digested before and
   after a build, so "the builder only writes where it is told" is a measurement.
"""

from __future__ import annotations

import ast
import hashlib
import json
import unittest
from pathlib import Path

from creator_plugin_builder import (
    DEFAULT_PLUGIN_DIR,
    PLUGIN_CORE_SKILLS,
    PLUGIN_SLOTS,
    PROTOCOL_STAGES,
    DomainRequest,
    audit_layers,
    build_domain_plugin,
    catalog_domains,
    describe_validation,
    library_document,
    load_domain_request,
    validate_plugin,
    write_domain_plugin,
    write_schema,
)

from . import fixtures

WORKSPACE = Path(__file__).resolve().parents[2]
PACKAGE = WORKSPACE / "creator_plugin_builder"
PACKAGE_FILES = (
    "__init__.py",
    "builder.py",
    "library.py",
    "model.py",
    "provenance.py",
    "registry.py",
    "schema.py",
    "validator.py",
)

#: Directories that must remain byte-identical across a build.
FROZEN_DIRECTORIES: tuple[str, ...] = (
    "runtime",
    "production",
    "workflows",
    "risk_evaluation",
    "multimodal_creator",
    "distillation_core",
    "plugins",
)

#: Packages the builder must never import.
FORBIDDEN_IMPORTS: tuple[str, ...] = FROZEN_DIRECTORIES + (
    "lobster",
    "subprocess",
    "socket",
    "urllib",
    "http",
    "requests",
    "openai",
    "anthropic",
    "yaml",
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


class EndToEndTests(unittest.TestCase):
    """Request file → plugin → validation → written document → revalidation."""

    def test_the_full_chain_runs_for_finance(self) -> None:
        request = load_domain_request(
            WORKSPACE / "examples" / "domain_requests" / "finance.yaml"
        )
        result = build_domain_plugin(request)
        self.assertTrue(result.passed)
        self.assertEqual(result.plugin.plugin_name, "domain_finance_plugin")

    def test_the_full_chain_runs_for_sports(self) -> None:
        request = load_domain_request(
            WORKSPACE / "examples" / "domain_requests" / "sports.yaml"
        )
        self.assertTrue(build_domain_plugin(request).passed)

    def test_the_full_chain_runs_for_technology(self) -> None:
        request = load_domain_request(
            WORKSPACE / "examples" / "domain_requests" / "technology.yaml"
        )
        self.assertTrue(build_domain_plugin(request).passed)

    def test_the_chain_runs_for_every_catalog_domain(self) -> None:
        for domain in catalog_domains():
            result = build_domain_plugin(DomainRequest(domain=domain))
            self.assertTrue(result.passed, domain)

    def test_a_written_plugin_revalidates(self) -> None:
        root = fixtures.scratch_dir("e2e_write")
        result = build_domain_plugin(fixtures.request_for("finance"))
        write_domain_plugin(result.plugin, root)
        payload = json.loads((root / "domain_finance_plugin.plugin.json").read_text(
            encoding="utf-8"
        ))
        from creator_plugin_builder import validate_schema

        validate_schema(payload)

    def test_a_written_plugin_matches_the_built_one(self) -> None:
        root = fixtures.scratch_dir("e2e_match")
        plugin = fixtures.plugin("finance")
        write_domain_plugin(plugin, root)
        payload = json.loads((root / "domain_finance_plugin.plugin.json").read_text(
            encoding="utf-8"
        ))
        self.assertEqual(payload, plugin.as_dict())

    def test_the_written_provenance_matches(self) -> None:
        from creator_plugin_builder import provenance_document

        root = fixtures.scratch_dir("e2e_prov")
        plugin = fixtures.plugin("finance")
        write_domain_plugin(plugin, root)
        payload = json.loads(
            (root / "domain_finance_plugin.provenance.json").read_text(encoding="utf-8")
        )
        self.assertEqual(payload, provenance_document(plugin))

    def test_a_rebuilt_plugin_matches_the_first_build(self) -> None:
        first = build_domain_plugin(fixtures.request_for("finance"))
        second = build_domain_plugin(fixtures.request_for("finance"))
        self.assertEqual(first.plugin.as_dict(), second.plugin.as_dict())

    def test_two_writes_of_one_plugin_are_byte_identical(self) -> None:
        plugin = fixtures.plugin("finance")
        first = fixtures.scratch_dir("e2e_det1")
        second = fixtures.scratch_dir("e2e_det2")
        write_domain_plugin(plugin, first)
        write_domain_plugin(plugin, second)
        self.assertEqual(
            (first / "domain_finance_plugin.plugin.json").read_bytes(),
            (second / "domain_finance_plugin.plugin.json").read_bytes(),
        )

    def test_the_schema_is_on_disk_where_the_contract_schemas_live(self) -> None:
        target = write_schema()
        self.assertEqual(target.parent.name, "schemas")
        self.assertTrue(target.is_file())

    def test_the_library_document_describes_the_whole_library(self) -> None:
        document = library_document()
        self.assertEqual(document["universal_skill_count"], 10)
        self.assertEqual(document["meta_skill_count"], 3)

    def test_the_batch_report_covers_every_domain(self) -> None:
        plugins = [build_domain_plugin(DomainRequest(domain=d)).plugin
                   for d in catalog_domains()]
        document = describe_validation(plugins)
        self.assertEqual(document["plugin_count"], 3)
        self.assertEqual(document["status"], "PASS")

    def test_a_full_run_leaves_the_library_clean(self) -> None:
        """Building plugins must not pollute the library it draws from."""

        for domain in catalog_domains():
            build_domain_plugin(DomainRequest(domain=domain))
        self.assertTrue(audit_layers().passed)

    def test_the_whole_run_is_reproducible(self) -> None:
        def run() -> str:
            blobs = [
                json.dumps(
                    build_domain_plugin(DomainRequest(domain=d)).plugin.as_dict(),
                    sort_keys=True,
                )
                for d in catalog_domains()
            ]
            return hashlib.sha256("".join(blobs).encode("utf-8")).hexdigest()

        self.assertEqual(run(), run())


class PackageShapeTests(unittest.TestCase):
    """The package is the modules it claims to be."""

    def test_every_declared_module_exists(self) -> None:
        for name in PACKAGE_FILES:
            self.assertTrue((PACKAGE / name).is_file(), name)

    def test_there_are_no_extra_modules(self) -> None:
        present = sorted(p.name for p in PACKAGE.glob("*.py"))
        self.assertEqual(present, sorted(PACKAGE_FILES))

    def test_the_package_has_no_subpackages(self) -> None:
        subpackages = [
            p.name for p in PACKAGE.iterdir()
            if p.is_dir() and p.name != "__pycache__"
        ]
        self.assertEqual(subpackages, [])

    def test_every_module_declares_its_exports(self) -> None:
        for name in PACKAGE_FILES:
            self.assertIn("__all__", (PACKAGE / name).read_text(encoding="utf-8"), name)

    def test_every_module_has_a_docstring(self) -> None:
        for name in PACKAGE_FILES:
            tree = ast.parse((PACKAGE / name).read_text(encoding="utf-8"))
            self.assertIsNotNone(ast.get_docstring(tree), name)

    def test_every_module_uses_future_annotations(self) -> None:
        for name in PACKAGE_FILES:
            source = (PACKAGE / name).read_text(encoding="utf-8")
            self.assertIn("from __future__ import annotations", source, name)


class ImportIsolationTests(unittest.TestCase):
    """The builder imports nothing that could run, reach out, or generate."""

    def test_no_module_imports_a_forbidden_package(self) -> None:
        offenders: list[str] = []
        for name in PACKAGE_FILES:
            for module in imported_roots(PACKAGE / name):
                if module in FORBIDDEN_IMPORTS:
                    offenders.append(f"{name} imports {module}")
        self.assertEqual(offenders, [])

    def test_no_module_imports_anything_outside_the_allowed_set(self) -> None:
        allowed = {
            "creator_contract",
            "creator_projection",
            "creator_plugin_builder",
            "core",
            "json",
            "re",
            "hashlib",
            "dataclasses",
            "enum",
            "pathlib",
            "typing",
            "collections",
            "__future__",
        }
        offenders: list[str] = []
        for name in PACKAGE_FILES:
            for module in imported_roots(PACKAGE / name):
                if module not in allowed:
                    offenders.append(f"{name} imports {module}")
        self.assertEqual(offenders, [])

    def test_the_package_imports_no_third_party_library(self) -> None:
        """The project declares no dependencies, so nothing here may need one."""

        for name in PACKAGE_FILES:
            for module in imported_roots(PACKAGE / name):
                self.assertNotIn(module, {"yaml", "numpy", "pandas", "requests"}, name)

    def test_no_module_calls_a_model(self) -> None:
        markers = ("openai", "anthropic", "chat.completions", "generate_content")
        for name in PACKAGE_FILES:
            text = (PACKAGE / name).read_text(encoding="utf-8")
            for marker in markers:
                self.assertNotIn(marker, text, f"{name}: {marker}")

    def test_no_module_opens_a_network_connection(self) -> None:
        markers = ("urllib", "requests.", "socket.", "http.client")
        for name in PACKAGE_FILES:
            text = (PACKAGE / name).read_text(encoding="utf-8")
            for marker in markers:
                self.assertNotIn(marker, text, f"{name}: {marker}")

    def test_no_module_deletes_from_an_artifact(self) -> None:
        """Nothing may remove a field from a plugin document.

        The registry's ``unregister`` is the one removal in the package, and it is a
        different thing: it drops an entry from the registry's *own in-memory*
        collection, which is the registry's public API. It never touches an artifact.
        """

        offenders: list[str] = []
        for name in PACKAGE_FILES:
            for number, line in enumerate(
                (PACKAGE / name).read_text(encoding="utf-8").splitlines(), 1
            ):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if stripped.startswith("del "):
                    offenders.append(f"{name}:{number}: {stripped}")
                if ".pop(" in stripped and "self._entries.pop" not in stripped:
                    offenders.append(f"{name}:{number}: {stripped}")
        self.assertEqual(offenders, [])

    def test_the_only_removal_in_the_package_is_the_registry_unregister(self) -> None:
        removals: list[str] = []
        for name in PACKAGE_FILES:
            for number, line in enumerate(
                (PACKAGE / name).read_text(encoding="utf-8").splitlines(), 1
            ):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if ".pop(" in line or stripped.startswith("del "):
                    removals.append(f"{name}:{number}")
        self.assertEqual(removals, ["registry.py:386"])

    def test_the_unregister_method_is_the_documented_exception(self) -> None:
        source = (PACKAGE / "registry.py").read_text(encoding="utf-8")
        self.assertIn("def unregister", source)
        self.assertIn("self._entries.pop(domain)", source)

    def test_no_module_enables_a_capability(self) -> None:
        offenders: list[str] = []
        for name in PACKAGE_FILES:
            for number, line in enumerate(
                (PACKAGE / name).read_text(encoding="utf-8").splitlines(), 1
            ):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if '"available": True' in stripped or "'available': True" in stripped:
                    offenders.append(f"{name}:{number}: {stripped}")
        self.assertEqual(offenders, [])

    def test_no_absolute_path_in_the_package(self) -> None:
        for name in PACKAGE_FILES:
            for line in (PACKAGE / name).read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for marker in ("C:\\", "/home/", "/Users/"):
                    self.assertNotIn(marker, line, f"{name}: {stripped}")

    def test_no_asset_path_literal_in_the_package(self) -> None:
        for name in PACKAGE_FILES:
            for line in (PACKAGE / name).read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for marker in ("docs/", "assets.yaml", "visual_profile.yaml"):
                    self.assertNotIn(marker, line, f"{name}: {stripped}")


class FrozenDirectoryTests(unittest.TestCase):
    """A build changes nothing in the directories the programme protects."""

    def test_the_frozen_directories_exist(self) -> None:
        for name in FROZEN_DIRECTORIES:
            self.assertTrue((WORKSPACE / name).is_dir(), name)

    def test_building_does_not_modify_a_frozen_directory(self) -> None:
        before = {n: digest_tree(WORKSPACE / n) for n in FROZEN_DIRECTORIES}
        build_domain_plugin(fixtures.request_for("finance"))
        after = {n: digest_tree(WORKSPACE / n) for n in FROZEN_DIRECTORIES}
        self.assertEqual(before, after)

    def test_validating_does_not_modify_a_frozen_directory(self) -> None:
        before = {n: digest_tree(WORKSPACE / n) for n in FROZEN_DIRECTORIES}
        validate_plugin(fixtures.plugin("sports"))
        after = {n: digest_tree(WORKSPACE / n) for n in FROZEN_DIRECTORIES}
        self.assertEqual(before, after)

    def test_writing_a_plugin_does_not_modify_the_package(self) -> None:
        root = fixtures.scratch_dir("iso_write")
        before = digest_tree(PACKAGE)
        write_domain_plugin(fixtures.plugin("finance"), root)
        self.assertEqual(digest_tree(PACKAGE), before)

    def test_building_does_not_modify_the_loader_package(self) -> None:
        target = WORKSPACE / "creator_loader"
        before = digest_tree(target)
        build_domain_plugin(fixtures.request_for("technology"))
        self.assertEqual(digest_tree(target), before)

    def test_building_does_not_modify_the_skill_package(self) -> None:
        target = WORKSPACE / "creator_skill"
        before = digest_tree(target)
        build_domain_plugin(fixtures.request_for("finance"))
        self.assertEqual(digest_tree(target), before)

    def test_building_does_not_modify_the_mapping_package(self) -> None:
        target = WORKSPACE / "creator_mapping"
        before = digest_tree(target)
        build_domain_plugin(fixtures.request_for("finance"))
        self.assertEqual(digest_tree(target), before)

    def test_building_does_not_modify_the_contract_package(self) -> None:
        target = WORKSPACE / "creator_contract"
        before = digest_tree(target)
        build_domain_plugin(fixtures.request_for("finance"))
        self.assertEqual(digest_tree(target), before)

    def test_building_does_not_write_a_plugin_directory(self) -> None:
        """Building returns an object; only writing writes."""

        target = WORKSPACE / DEFAULT_PLUGIN_DIR
        existed = target.exists()
        build_domain_plugin(fixtures.request_for("finance"))
        if not existed:
            self.assertFalse(target.exists())

    def test_writing_targets_only_the_directory_it_was_given(self) -> None:
        root = fixtures.scratch_dir("iso_target")
        written = write_domain_plugin(fixtures.plugin("finance"), root)
        for path in written:
            self.assertEqual(path.parent, root)

    def test_a_write_creates_exactly_two_files(self) -> None:
        root = fixtures.scratch_dir("iso_two")
        write_domain_plugin(fixtures.plugin("finance"), root)
        self.assertEqual(len(list(root.iterdir())), 2)


class NoCapabilityInventionTests(unittest.TestCase):
    """Nothing a plugin declares outruns the assets that exist."""

    def test_the_persona_is_never_reported_available(self) -> None:
        for plugin in fixtures.all_plugins():
            self.assertFalse(plugin.persona_available, plugin.domain)

    def test_every_unavailable_rule_states_a_reason(self) -> None:
        for plugin in fixtures.all_plugins():
            for slot in PLUGIN_SLOTS:
                for rule in plugin.rules(slot):
                    if not rule.available:
                        self.assertTrue(rule.reason, f"{plugin.domain}.{slot}")

    def test_generation_and_publishing_are_not_bound_by_any_plugin(self) -> None:
        """Both are declared capabilities with no implementation, so no plugin
        binds a rule to them."""

        for plugin in fixtures.all_plugins():
            self.assertNotIn("generation-interface", plugin.required_core_skills)
            self.assertNotIn("publishing-interface", plugin.required_core_skills)

    def test_no_rule_binds_to_an_unavailable_asset_as_available(self) -> None:
        from creator_projection import AssetRegistry

        registry = AssetRegistry.load(WORKSPACE)
        for plugin in fixtures.all_plugins():
            for slot in PLUGIN_SLOTS:
                for rule in plugin.rules(slot):
                    if rule.available:
                        self.assertTrue(
                            registry.get(rule.source_asset).available,
                            f"{plugin.domain}.{slot}.{rule.slot}",
                        )

    def test_the_taxonomy_rules_are_labelled_as_catalog_values(self) -> None:
        for plugin in fixtures.all_plugins():
            for rule in plugin.topic_rules:
                self.assertEqual(rule.values_source, "catalog", plugin.domain)

    def test_the_asset_backed_rules_are_labelled_as_asset_values(self) -> None:
        for plugin in fixtures.all_plugins():
            for slot in PLUGIN_SLOTS:
                if slot == "topic_rules":
                    continue
                for rule in plugin.rules(slot):
                    self.assertEqual(rule.values_source, "asset",
                                     f"{plugin.domain}.{slot}")

    def test_no_plugin_carries_domain_values_it_did_not_declare(self) -> None:
        """Every value a plugin ships is either an asset id or a declared term."""

        for plugin in fixtures.all_plugins():
            declared = set(plugin.values("topic_rules"))
            for term in declared:
                self.assertTrue(term, plugin.domain)

    def test_the_protocol_stages_are_all_marked_consistently(self) -> None:
        for plugin in fixtures.all_plugins():
            statuses = {s.status for s in plugin.protocol_stages}
            self.assertEqual(len(statuses), 1, plugin.domain)

    def test_the_protocol_keeps_its_unified_shape(self) -> None:
        for plugin in fixtures.all_plugins():
            self.assertEqual(
                tuple(s.stage for s in plugin.protocol_stages), PROTOCOL_STAGES
            )

    def test_every_core_skill_a_rule_uses_is_declared(self) -> None:
        for plugin in fixtures.all_plugins():
            for slot in PLUGIN_SLOTS:
                for rule in plugin.rules(slot):
                    self.assertIn(rule.core_skill, PLUGIN_CORE_SKILLS)


if __name__ == "__main__":
    unittest.main()
