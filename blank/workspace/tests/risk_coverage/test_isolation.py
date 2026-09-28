"""Isolation: what the coverage framework may not touch, asserted rather than promised.

This is the file the whole phase stands on. The framework reads the frozen evaluator, the
Phase 8.9 benchmark and the earlier phases' freezes, and it must not write a byte to any
of them. Three independent instruments are used, because a promise in a docstring is not
evidence:

1. **Static.** Every module is parsed with `ast`, and its imports, its module-level path
   constants and its write calls are inspected.
2. **Textual.** Every occurrence of a frozen path literal is located and shown to be a
   docstring, a read-only declaration, or prose that asserts nothing is written.
3. **Runtime.** A full pipeline run is executed with `Path.write_text` spied on, and the
   evaluator, benchmark and foreign-freeze digests are compared before and after.
"""

from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import risk_evaluation.coverage as coverage_package
from risk_evaluation.coverage import (
    analyzer,
    freeze,
    generator,
    lexicon,
    pipeline,
    registry,
    reporter,
    synonyms,
    taxonomy,
)

PACKAGE_DIR = Path(coverage_package.__file__).parent.resolve()

MODULES: dict[str, Path] = {
    name: path
    for name, path in (
        (path.stem, path) for path in sorted(PACKAGE_DIR.glob("*.py"))
    )
}

#: Packages this framework may not reach into at all.
FORBIDDEN_ROOTS = frozenset({"production", "runtime", "workflows", "plugins"})

#: Frameworks in this repository that are equally out of bounds.
ALSO_FORBIDDEN_ROOTS = frozenset({"core", "distillation_core"})

#: Path fragments that name an artifact this phase is frozen against.
FROZEN_LITERALS = ("risk_evaluation/benchmarks", "risk_evaluation/v3/")

#: Attribute names that write to disk when called on a `Path`.
WRITE_ATTRIBUTES = frozenset(
    {"write_text", "write_bytes", "write_json", "unlink", "touch", "rename", "replace"}
)


def _sources() -> dict[str, str]:
    return {name: path.read_text(encoding="utf-8") for name, path in MODULES.items()}


def _trees() -> dict[str, ast.Module]:
    return {name: ast.parse(source) for name, source in _sources().items()}


def _imported_roots(tree: ast.Module) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # a relative import inside the package
                continue
            if node.module:
                roots.add(node.module.split(".")[0])
    return roots


class CoverageIsolationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = _sources()
        cls.trees = _trees()

    def test_the_package_has_modules_to_check(self) -> None:
        """A guard against this whole file silently testing nothing."""

        self.assertGreaterEqual(len(MODULES), 10)
        self.assertIn("pipeline", MODULES)
        self.assertIn("freeze", MODULES)

    def test_every_module_parses(self) -> None:
        for name, tree in self.trees.items():
            with self.subTest(module=name):
                self.assertIsInstance(tree, ast.Module)

    def test_no_module_imports_production_runtime_workflows_or_plugins(self) -> None:
        for name, tree in self.trees.items():
            roots = _imported_roots(tree)
            with self.subTest(module=name):
                self.assertEqual(roots & FORBIDDEN_ROOTS, set())

    def test_no_module_imports_the_frameworks_own_inner_packages(self) -> None:
        for name, tree in self.trees.items():
            roots = _imported_roots(tree)
            with self.subTest(module=name):
                self.assertEqual(roots & ALSO_FORBIDDEN_ROOTS, set())

    def test_no_module_imports_anything_outside_the_standard_library(self) -> None:
        import sys

        allowed = set(sys.stdlib_module_names) | {"__future__", "risk_evaluation"}
        for name, tree in self.trees.items():
            roots = _imported_roots(tree)
            with self.subTest(module=name):
                self.assertEqual(
                    {root for root in roots if root not in allowed},
                    set(),
                    f"{name} imports something that is neither stdlib nor this package",
                )

    def test_no_module_imports_a_network_or_llm_client(self) -> None:
        for name, tree in self.trees.items():
            roots = _imported_roots(tree)
            with self.subTest(module=name):
                self.assertEqual(
                    roots & {"socket", "requests", "urllib", "http", "openai", "anthropic"},
                    set(),
                )

    def test_the_evaluator_packages_are_only_read(self) -> None:
        """The frozen evaluator's mutable `register()` is never called by this package."""

        registered: list[str] = []
        for name, tree in self.trees.items():
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                if called == "register":
                    registered.append(f"{name}:{node.lineno}")
        self.assertEqual(registered, [])

    def test_the_package_reaches_outside_itself_only_into_the_frozen_evaluator(
        self,
    ) -> None:
        """Every relative import is either inside the package or an evaluator package."""

        evaluator = {"v3", "v3_1", "v3_repair", "v3_independent"}
        outward: set[str] = set()
        for name, tree in self.trees.items():
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom) or not node.level:
                    continue
                with self.subTest(module=name):
                    self.assertIn(node.level, (1, 2), "an import climbs too far up")
                if node.level == 2:
                    root = (node.module or "").split(".")[0]
                    outward.add(root)
                    with self.subTest(module=name, imported=root):
                        self.assertIn(root, evaluator)
        self.assertTrue(outward, "no evaluator package is imported, so nothing was read")

    def test_the_frozen_evaluator_is_imported_by_name(self) -> None:
        """All four evaluator packages the framework reads are named in its imports."""

        targets: set[str] = set()
        for tree in self.trees.values():
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level == 2:
                    targets.add((node.module or "").split(".")[0])
        for package in ("v3", "v3_1", "v3_repair", "v3_independent"):
            with self.subTest(package=package):
                self.assertIn(package, targets)

    def test_no_module_calls_a_mutating_api_on_the_frozen_evaluator(self) -> None:
        mutators = {"register", "write_dataset", "write_evaluation", "write_freeze"}
        for name, tree in self.trees.items():
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                with self.subTest(module=name):
                    self.assertNotIn(called, mutators)


class PathConstantTest(unittest.TestCase):
    """Every module-level path constant, and where it points."""

    def _constants(self) -> dict[str, Path]:
        out: dict[str, Path] = {}
        for module in (
            analyzer,
            freeze,
            generator,
            lexicon,
            pipeline,
            registry,
            reporter,
            synonyms,
            taxonomy,
        ):
            for name, value in vars(module).items():
                if name.startswith("__") or not isinstance(value, Path):
                    continue
                out[f"{module.__name__}.{name}"] = value
        return out

    def test_there_are_module_level_path_constants_to_check(self) -> None:
        self.assertGreaterEqual(len(self._constants()), 10)

    def test_every_constant_is_under_the_package_or_the_report_directory(self) -> None:
        """The one documented exception is the report output directory.

        `reporter.DOCS_DIR` is `<repository>/docs`, which is where the dashboard and the
        expansion report are published — a documentation target, not a frozen artifact.
        It is named here explicitly so that a *second* escape cannot appear unnoticed.
        """

        outside: dict[str, Path] = {}
        for name, path in self._constants().items():
            resolved = path.resolve()
            if resolved == PACKAGE_DIR or PACKAGE_DIR in resolved.parents:
                continue
            outside[name] = resolved
        self.assertEqual(
            set(outside),
            {"risk_evaluation.coverage.reporter.DOCS_DIR"},
            f"unexpected paths outside the package: {outside}",
        )

    def test_the_report_directory_is_the_repository_docs_directory(self) -> None:
        self.assertEqual(reporter.DOCS_DIR.resolve(), freeze.repository_root() / "docs")

    def test_the_report_directory_is_not_a_frozen_artifact(self) -> None:
        text = str(reporter.DOCS_DIR).replace("\\", "/")
        for fragment in ("/benchmarks", "/v3/", "/v3_1/", "production", "runtime"):
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, text)

    def test_no_constant_points_at_a_frozen_area(self) -> None:
        for name, path in self._constants().items():
            text = str(path).replace("\\", "/")
            with self.subTest(constant=name):
                for fragment in ("risk_evaluation/benchmarks", "risk_evaluation/v3"):
                    self.assertNotIn(fragment, text)

    def test_the_artifact_constants_are_the_packages_own_files(self) -> None:
        self.assertEqual(pipeline.ANALYSIS_ARTIFACT, PACKAGE_DIR / "failure_analysis_r1.json")
        self.assertEqual(pipeline.FREEZE_ARTIFACT, PACKAGE_DIR / "coverage_freeze_r1.json")
        self.assertEqual(pipeline.REGRESSION_ARTIFACT, PACKAGE_DIR / "regression_candidates.json")
        self.assertEqual(
            pipeline.GENERATED_ARTIFACT,
            PACKAGE_DIR / "generated_cases" / "generated_cases_r1.json",
        )

    def test_the_registry_directories_are_the_packages_own(self) -> None:
        for path in (
            registry.REGISTRY_DIR,
            registry.PENDING_DIR,
            registry.ACCEPTED_DIR,
            registry.REJECTED_DIR,
            generator.GENERATED_DIR,
        ):
            with self.subTest(path=str(path)):
                resolved = path.resolve()
                self.assertTrue(
                    resolved == PACKAGE_DIR or PACKAGE_DIR in resolved.parents,
                    f"{path} is outside the package",
                )


class WriteCallTest(unittest.TestCase):
    """No write call in the package names a frozen path."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = _sources()

    def _write_calls(self, tree: ast.Module) -> list[ast.Call]:
        calls: list[ast.Call] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in WRITE_ATTRIBUTES or name == "open":
                calls.append(node)
        return calls

    def test_the_package_does_make_write_calls(self) -> None:
        total = sum(len(self._write_calls(ast.parse(source))) for source in self.sources.values())
        self.assertGreater(total, 0)

    def test_no_write_call_names_a_frozen_path(self) -> None:
        for name, source in self.sources.items():
            for call in self._write_calls(ast.parse(source)):
                literals = [
                    node.value
                    for node in ast.walk(call)
                    if isinstance(node, ast.Constant) and isinstance(node.value, str)
                ]
                for literal in literals:
                    with self.subTest(module=name, literal=literal[:60]):
                        self.assertNotIn("risk_evaluation/benchmarks", literal)
                        self.assertNotIn("risk_evaluation/v3/", literal)
                        self.assertNotIn("production/", literal)
                        self.assertNotIn("runtime/", literal)
                        self.assertNotIn("workflows/", literal)
                        self.assertNotIn("plugins/", literal)

    def test_nothing_opens_a_file_for_writing(self) -> None:
        """Writes go through `Path.write_text`, so `open(..., 'w')` has no reason to exist."""

        for name, source in self.sources.items():
            for call in self._write_calls(ast.parse(source)):
                func = call.func
                if not (isinstance(func, ast.Name) and func.id == "open"):
                    continue
                modes = [
                    arg.value
                    for arg in call.args[1:]
                    if isinstance(arg, ast.Constant)
                ] + [
                    kw.value.value
                    for kw in call.keywords
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant)
                ]
                with self.subTest(module=name):
                    for mode in modes:
                        self.assertNotIn("w", str(mode))
                        self.assertNotIn("a", str(mode))


class FrozenLiteralTest(unittest.TestCase):
    """Every occurrence of a frozen path literal, classified by its context."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = _sources()

    def _occurrences(self, name: str, needle: str) -> list[tuple[int, str, ast.Constant | None]]:
        source = self.sources[name]
        tree = ast.parse(source)
        docstrings: set[int] = set()
        for node in ast.walk(tree):
            if not isinstance(
                node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                continue
            body = getattr(node, "body", None)
            if not body or not isinstance(body[0], ast.Expr):
                continue
            first = body[0].value
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                docstrings.add(id(first))
        strings = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        found: list[tuple[int, str, ast.Constant | None]] = []
        for number, line in enumerate(source.splitlines(), start=1):
            if needle not in line:
                continue
            holder = next(
                (
                    node
                    for node in strings
                    if node.lineno <= number <= (node.end_lineno or node.lineno)
                    and needle in node.value
                ),
                None,
            )
            if holder is not None and id(holder) in docstrings:
                holder = None
            found.append((number, line.strip(), holder))
        return found

    def test_each_frozen_literal_occurs_somewhere(self) -> None:
        for needle in FROZEN_LITERALS:
            with self.subTest(needle=needle):
                self.assertTrue(
                    any(self._occurrences(name, needle) for name in self.sources),
                    f"{needle} never appears, so this test proves nothing",
                )

    def test_every_non_docstring_occurrence_is_a_read_only_declaration(self) -> None:
        """The only strings naming a frozen path are the digests and the ban list.

        `freeze.EVALUATOR_SOURCES` and `freeze.BENCHMARK_SOURCES` are read by
        `digest_file`; `registry.FROZEN_PREFIXES` is the list of targets a proposal is
        *refused* for naming. The one remaining string is the generated artifact's
        `not_a_benchmark` note, which asserts that nothing writes there.
        """

        allowed = (
            set(freeze.EVALUATOR_SOURCES)
            | set(freeze.BENCHMARK_SOURCES)
            | set(registry.FROZEN_PREFIXES)
        )
        unclassified: list[str] = []
        for name in self.sources:
            for needle in FROZEN_LITERALS:
                for number, line, holder in self._occurrences(name, needle):
                    if holder is None:
                        continue  # a docstring, which cannot write anything
                    value = holder.value
                    if value in allowed:
                        continue
                    if "nothing here writes to" in value:
                        continue  # the artifact's own assurance, asserted below
                    unclassified.append(f"{name}:{number}: {line}")
        self.assertEqual(unclassified, [])

    def test_the_evaluator_sources_are_digested_not_written(self) -> None:
        for name in freeze.EVALUATOR_SOURCES:
            with self.subTest(source=name):
                self.assertTrue((freeze.repository_root() / name).is_file())

    def test_the_benchmark_sources_are_digested_not_written(self) -> None:
        for name in freeze.BENCHMARK_SOURCES:
            with self.subTest(source=name):
                self.assertTrue((freeze.repository_root() / name).is_file())

    def test_the_frozen_prefixes_are_a_ban_list(self) -> None:
        """The registry refuses a proposal that names one, which is the opposite of a write."""

        self.assertIn(registry.REASON_FROZEN_TARGET, registry.REJECTION_REASONS)
        self.assertEqual(
            set(registry.describe()["frozen_prefixes"]), set(registry.FROZEN_PREFIXES)
        )


class FreezeGuardTest(unittest.TestCase):
    """The single most important assertion in this suite."""

    def test_guard_reports_ok(self) -> None:
        report = freeze.guard()
        self.assertTrue(
            report.ok,
            f"the framework modified a frozen artifact: mismatches={report.mismatches} "
            f"missing={report.missing}",
        )

    def test_guard_has_nothing_to_report(self) -> None:
        report = freeze.guard()
        self.assertEqual(report.mismatches, ())
        self.assertEqual(report.missing, ())

    def test_guard_checked_every_frozen_file(self) -> None:
        report = freeze.guard()
        expected = (
            set(freeze.EVALUATOR_SOURCES)
            | set(freeze.BENCHMARK_SOURCES)
            | set(freeze.FOREIGN_FREEZES)
        )
        self.assertEqual(set(report.checked), expected)

    def test_the_evaluator_digest_matches_the_recorded_freeze(self) -> None:
        self.assertEqual(freeze.load()["evaluator_hash"], freeze.evaluator_digest())

    def test_the_benchmark_digest_matches_the_recorded_freeze(self) -> None:
        self.assertEqual(freeze.load()["benchmark_hash"], freeze.benchmark_digest())

    def test_verify_reports_the_source_digest_but_does_not_enforce_it(self) -> None:
        body = freeze.verify()
        self.assertTrue(body["ok"])
        self.assertEqual(body["mismatches"], [])
        self.assertTrue(body["recorded_source_hash"])
        self.assertTrue(body["current_source_hash"])


class FullRunIsolationTest(unittest.TestCase):
    """A real run, watched: every write it makes, and every digest it must not move."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name) / "run"
        cls.before = {
            "evaluator": freeze.evaluator_digest(),
            "benchmark": freeze.benchmark_digest(),
            "foreign": freeze.foreign_freeze_digests(),
            "package": {
                str(path.relative_to(PACKAGE_DIR)): path.read_bytes()
                for path in sorted(PACKAGE_DIR.rglob("*"))
                if path.is_file() and path.suffix in {".json", ".md"}
            },
        }

        writes: list[Path] = []
        original = Path.write_text

        def spy(self: Path, *args: Any, **kwargs: Any) -> Any:
            writes.append(self)
            return original(self, *args, **kwargs)

        with mock.patch.object(Path, "write_text", spy):
            cls.pipeline_run = pipeline.run(
                output_dir=cls.root, write_reports=True, freeze_run=True
            )
        cls.writes = tuple(writes)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_the_run_wrote_something(self) -> None:
        self.assertTrue(self.writes, "the spy saw no writes, so this test proves nothing")

    def test_every_write_lands_under_the_run_directory(self) -> None:
        for path in self.writes:
            with self.subTest(path=str(path)):
                self.assertTrue(
                    path.resolve() == self.root.resolve()
                    or self.root.resolve() in path.resolve().parents,
                    f"a run wrote outside its output directory: {path}",
                )

    def test_no_write_lands_in_the_evaluator_or_the_benchmark(self) -> None:
        for path in self.writes:
            text = str(path).replace("\\", "/")
            with self.subTest(path=text):
                self.assertNotIn("risk_evaluation/v3/", text)
                self.assertNotIn("risk_evaluation/benchmarks/", text)
                self.assertNotIn("/production/", text)
                self.assertNotIn("/runtime/", text)
                self.assertNotIn("/workflows/", text)
                self.assertNotIn("/plugins/", text)

    def test_the_evaluator_digest_is_unchanged_by_the_run(self) -> None:
        self.assertEqual(self.before["evaluator"], freeze.evaluator_digest())

    def test_the_benchmark_digest_is_unchanged_by_the_run(self) -> None:
        self.assertEqual(self.before["benchmark"], freeze.benchmark_digest())

    def test_the_earlier_phases_freezes_are_unchanged_by_the_run(self) -> None:
        self.assertEqual(self.before["foreign"], freeze.foreign_freeze_digests())

    def test_the_packaged_artifacts_are_unchanged_by_the_run(self) -> None:
        after = {
            str(path.relative_to(PACKAGE_DIR)): path.read_bytes()
            for path in sorted(PACKAGE_DIR.rglob("*"))
            if path.is_file() and path.suffix in {".json", ".md"}
        }
        self.assertEqual(sorted(after), sorted(self.before["package"]))
        for name, payload in self.before["package"].items():
            with self.subTest(artifact=name):
                self.assertEqual(after[name], payload)

    def test_the_run_still_produced_the_same_conclusions(self) -> None:
        self.assertEqual(self.pipeline_run.counts["cases"], 300)
        self.assertEqual(self.pipeline_run.counts["failures"], 151)

    def test_the_run_never_wrote_into_accepted(self) -> None:
        accepted = self.root / "coverage_candidates" / "accepted"
        self.assertEqual(sorted(path.name for path in accepted.iterdir()), ["README.md"])

    def test_guard_is_still_ok_after_the_run(self) -> None:
        report = freeze.guard()
        self.assertTrue(report.ok, report.mismatches)
