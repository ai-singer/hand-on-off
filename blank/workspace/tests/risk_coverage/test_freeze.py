"""The freeze: three digests, and the proof that nothing frozen moved.

`source_hash` makes the run reproducible, `benchmark_hash` and `evaluator_hash` make the
phase's central prohibition checkable. The freeze is additive: the earlier phases'
freezes are recorded so a reviewer can see they were left alone, not re-frozen.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from risk_evaluation.coverage import freeze
from risk_evaluation.coverage.freeze import (
    BENCHMARK_SOURCES,
    EVALUATOR_SOURCES,
    FOREIGN_FREEZES,
    FREEZE_PATH,
    FreezeError,
    GuardReport,
    benchmark_digest,
    compute,
    digest_bytes,
    digest_file,
    digest_paths,
    evaluator_digest,
    foreign_freeze_digests,
    guard,
    load,
    package_sources,
    repository_root,
    source_digest,
    verify,
    write,
)


class ComputeTest(unittest.TestCase):
    def test_compute_records_three_non_empty_digests(self) -> None:
        body = compute()
        for key in ("source_hash", "benchmark_hash", "evaluator_hash"):
            with self.subTest(key=key):
                self.assertIsInstance(body[key], str)
                self.assertEqual(len(body[key]), 64)

    def test_compute_records_a_timestamp(self) -> None:
        stamp = compute()["timestamp"]
        self.assertIsInstance(stamp, str)
        self.assertTrue(stamp)
        self.assertRegex(stamp, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$")

    def test_the_three_digests_are_stable_across_two_calls(self) -> None:
        first = compute()
        second = compute()
        for key in ("source_hash", "benchmark_hash", "evaluator_hash"):
            with self.subTest(key=key):
                self.assertEqual(first[key], second[key])

    def test_the_whole_body_is_stable_apart_from_the_timestamp(self) -> None:
        first = compute()
        second = compute()
        first.pop("timestamp")
        second.pop("timestamp")
        self.assertEqual(first, second)

    def test_the_three_digests_differ_from_each_other(self) -> None:
        body = compute()
        self.assertEqual(
            len({body["source_hash"], body["benchmark_hash"], body["evaluator_hash"]}), 3
        )

    def test_compute_names_the_phase_and_the_artifact(self) -> None:
        body = compute()
        self.assertEqual(body["phase"], "R1")
        self.assertEqual(body["artifact"], "risk-coverage-expansion-framework")

    def test_compute_lists_the_package_sources(self) -> None:
        body = compute()
        self.assertEqual(
            body["source_files"],
            [
                str(path.relative_to(repository_root())).replace("\\", "/")
                for path in package_sources()
            ],
        )
        self.assertTrue(body["source_files"])

    def test_compute_lists_the_evaluator_and_benchmark_sources(self) -> None:
        body = compute()
        self.assertEqual(body["evaluator_sources"], list(EVALUATOR_SOURCES))
        self.assertEqual(body["benchmark_sources"], list(BENCHMARK_SOURCES))

    def test_every_invariant_is_false(self) -> None:
        invariants = compute()["invariants"]
        self.assertTrue(invariants)
        for name, value in invariants.items():
            with self.subTest(invariant=name):
                self.assertIs(value, False)

    def test_the_invariants_cover_the_prohibitions(self) -> None:
        invariants = compute()["invariants"]
        for name in (
            "modifies_evaluator",
            "modifies_benchmark",
            "modifies_taxonomy",
            "modifies_decision_policy",
            "imports_production",
            "uses_network",
        ):
            with self.subTest(invariant=name):
                self.assertIn(name, invariants)

    def test_the_scope_states_that_earlier_freezes_are_not_rewritten(self) -> None:
        scope = compute()["scope"]
        self.assertIn("neither rewrites nor", scope)
        self.assertIn("earlier phases", scope)


class DigestTest(unittest.TestCase):
    def test_the_source_digest_is_stable(self) -> None:
        self.assertEqual(source_digest(), source_digest())

    def test_the_evaluator_digest_is_stable(self) -> None:
        self.assertEqual(evaluator_digest(), evaluator_digest())

    def test_the_benchmark_digest_is_stable(self) -> None:
        self.assertEqual(benchmark_digest(), benchmark_digest())

    def test_the_source_digest_covers_the_package_modules(self) -> None:
        self.assertEqual(compute()["source_hash"], source_digest())
        names = {path.name for path in package_sources()}
        self.assertIn("freeze.py", names)
        self.assertIn("analyzer.py", names)

    def test_digest_bytes_is_sha256(self) -> None:
        self.assertEqual(digest_bytes(b"abc"), hashlib.sha256(b"abc").hexdigest())
        self.assertNotEqual(digest_bytes(b"abc"), digest_bytes(b"abd"))

    def test_digest_file_hashes_the_bytes_on_disk(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "payload.txt"
            target.write_bytes(b"frozen\n")
            self.assertEqual(digest_file(target), digest_bytes(b"frozen\n"))

    def test_digest_file_refuses_a_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(FreezeError) as caught:
                digest_file(Path(raw) / "absent.txt")
            self.assertIn("frozen file is missing", str(caught.exception))

    def test_digest_paths_refuses_an_empty_set(self) -> None:
        with self.assertRaises(FreezeError):
            digest_paths([])

    def test_digest_paths_is_order_independent(self) -> None:
        files = sorted(package_sources())[:4]
        self.assertEqual(digest_paths(files), digest_paths(list(reversed(files))))

    def test_digest_paths_changes_when_a_byte_changes(self) -> None:
        """The property the whole guard rests on, shown on a copy of a real module."""

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            copy = root / "source.py"
            original = sorted(package_sources())[0].read_bytes()
            copy.write_bytes(original)
            before = digest_paths([copy], root=root)
            copy.write_bytes(original + b"\n# a later edit\n")
            after = digest_paths([copy], root=root)
            self.assertNotEqual(before, after)

    def test_digest_paths_changes_when_a_file_is_renamed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            first = root / "one.py"
            second = root / "two.py"
            first.write_bytes(b"same bytes")
            before = digest_paths([first], root=root)
            second.write_bytes(b"same bytes")
            after = digest_paths([second], root=root)
            self.assertNotEqual(before, after)

    def test_digest_paths_is_name_bound(self) -> None:
        """Identical bytes under different names are different frozen artifacts."""

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "one").mkdir()
            (root / "two").mkdir()
            (root / "one" / "source.py").write_bytes(b"same bytes")
            (root / "two" / "source.py").write_bytes(b"same bytes")
            self.assertNotEqual(
                digest_paths([root / "one" / "source.py"], root=root),
                digest_paths([root / "two" / "source.py"], root=root),
            )


class SourcesTest(unittest.TestCase):
    def test_the_repository_root_is_the_workspace_root(self) -> None:
        root = repository_root()
        self.assertTrue((root / "risk_evaluation").is_dir())
        self.assertTrue((root / "tests").is_dir())
        self.assertEqual(root, Path(freeze.__file__).resolve().parents[2])

    def test_every_evaluator_source_exists(self) -> None:
        for name in EVALUATOR_SOURCES:
            with self.subTest(source=name):
                self.assertTrue((repository_root() / name).is_file())

    def test_every_benchmark_source_exists(self) -> None:
        for name in BENCHMARK_SOURCES:
            with self.subTest(source=name):
                self.assertTrue((repository_root() / name).is_file())

    def test_the_evaluator_sources_are_the_frozen_ones(self) -> None:
        for name in EVALUATOR_SOURCES:
            with self.subTest(source=name):
                self.assertTrue(
                    name.startswith("risk_evaluation/v3")
                    or name.startswith("risk_evaluation/v3_")
                    or name.startswith("risk_evaluation/v3_repair"),
                    name,
                )

    def test_the_benchmark_sources_are_the_phase_8_9_set(self) -> None:
        for name in BENCHMARK_SOURCES:
            with self.subTest(source=name):
                self.assertIn("risk_evaluation/benchmarks/risk/independent/v1/", name)

    def test_no_frozen_source_lives_inside_the_coverage_package(self) -> None:
        for name in EVALUATOR_SOURCES + BENCHMARK_SOURCES:
            with self.subTest(source=name):
                self.assertNotIn("coverage", name.split("/"))


class ForeignFreezeTest(unittest.TestCase):
    def test_the_earlier_phases_freezes_still_exist(self) -> None:
        for name in FOREIGN_FREEZES:
            with self.subTest(freeze=name):
                self.assertTrue((repository_root() / name).is_file())

    def test_the_earlier_phases_freezes_are_named(self) -> None:
        self.assertEqual(
            set(FOREIGN_FREEZES),
            {
                "risk_evaluation/v3_1/evaluation_freeze_v3_1.json",
                "risk_evaluation/v3_independent/evaluation_freeze_v3_2.json",
            },
        )

    def test_the_recorded_digests_match_the_files_now(self) -> None:
        """This phase did not rewrite an earlier phase's freeze."""

        recorded = load()["foreign_freezes_untouched"]
        self.assertEqual(recorded, foreign_freeze_digests())
        for name, digest in recorded.items():
            with self.subTest(freeze=name):
                self.assertEqual(
                    digest, digest_file(repository_root() / name)
                )

    def test_the_fresh_freeze_records_the_same_foreign_digests(self) -> None:
        self.assertEqual(
            compute()["foreign_freezes_untouched"], foreign_freeze_digests()
        )

    def test_this_phase_does_not_own_the_foreign_freezes(self) -> None:
        body = compute()
        self.assertNotIn("risk_evaluation/v3_1/evaluation_freeze_v3_1.json", body["source_files"])
        self.assertNotIn(
            "risk_evaluation/v3_independent/evaluation_freeze_v3_2.json",
            body["evaluator_sources"],
        )


class GuardTest(unittest.TestCase):
    def test_guard_is_ok_against_the_recorded_freeze(self) -> None:
        report = guard()
        self.assertTrue(
            report.ok,
            f"a frozen artifact moved: mismatches={report.mismatches} "
            f"missing={report.missing}",
        )

    def test_guard_reports_no_mismatch_and_nothing_missing(self) -> None:
        report = guard()
        self.assertEqual(report.mismatches, ())
        self.assertEqual(report.missing, ())

    def test_guard_checks_every_frozen_and_foreign_file(self) -> None:
        report = guard()
        expected = set(EVALUATOR_SOURCES) | set(BENCHMARK_SOURCES) | set(FOREIGN_FREEZES)
        self.assertEqual(set(report.checked), expected)

    def test_guard_detects_a_doctored_evaluator_digest(self) -> None:
        recorded = dict(load())
        recorded["evaluator_hash"] = "0" * 64
        report = guard(recorded)
        self.assertFalse(report.ok)
        self.assertEqual([name for name, _r, _c in report.mismatches], ["evaluator_hash"])

    def test_guard_detects_a_doctored_benchmark_digest(self) -> None:
        recorded = dict(load())
        recorded["benchmark_hash"] = "f" * 64
        report = guard(recorded)
        self.assertFalse(report.ok)
        self.assertEqual([name for name, _r, _c in report.mismatches], ["benchmark_hash"])

    def test_guard_reports_a_missing_foreign_freeze(self) -> None:
        recorded = dict(load())
        recorded["foreign_freezes_untouched"] = {"risk_evaluation/not-a-freeze.json": "abc"}
        report = guard(recorded)
        self.assertFalse(report.ok)
        self.assertIn("risk_evaluation/not-a-freeze.json", report.missing)

    def test_guard_reports_a_doctored_foreign_freeze_digest(self) -> None:
        recorded = dict(load())
        name = FOREIGN_FREEZES[0]
        recorded["foreign_freezes_untouched"] = {name: "0" * 64}
        report = guard(recorded)
        self.assertFalse(report.ok)
        self.assertEqual([item[0] for item in report.mismatches], [name])

    def test_guard_ignores_a_mismatched_source_digest(self) -> None:
        """The source digest is reported, not enforced: the run wrote the freeze."""

        recorded = dict(load())
        recorded["source_hash"] = "0" * 64
        report = guard(recorded)
        self.assertTrue(report.ok)

    def test_the_guard_report_serialises_itself(self) -> None:
        body = guard().as_dict()
        self.assertIs(body["ok"], True)
        self.assertEqual(body["mismatches"], [])
        self.assertEqual(body["missing"], [])
        self.assertIn("read-only", body["note"])

    def test_an_empty_report_is_ok_and_a_mismatch_is_not(self) -> None:
        clean = GuardReport(ok=True, checked=(), mismatches=(), missing=())
        dirty = GuardReport(
            ok=False, checked=(), mismatches=(("evaluator_hash", "a", "b"),), missing=()
        )
        self.assertTrue(clean.ok)
        self.assertFalse(dirty.ok)


class VerifyAndFileTest(unittest.TestCase):
    def test_verify_is_ok(self) -> None:
        body = verify()
        self.assertTrue(body["ok"])
        self.assertEqual(body["mismatches"], [])
        self.assertTrue(body["recorded_source_hash"])
        self.assertTrue(body["current_source_hash"])

    def test_verify_reports_both_source_digests(self) -> None:
        body = verify()
        self.assertEqual(body["recorded_source_hash"], source_digest())
        self.assertEqual(body["current_source_hash"], source_digest())

    def test_the_freeze_file_exists_and_parses(self) -> None:
        self.assertTrue(FREEZE_PATH.is_file())
        body = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(body["phase"], "R1")

    def test_the_freeze_file_lives_inside_the_package(self) -> None:
        self.assertEqual(FREEZE_PATH.parent, Path(freeze.__file__).parent)

    def test_load_returns_the_recorded_body(self) -> None:
        body = load()
        for key in ("source_hash", "benchmark_hash", "evaluator_hash", "timestamp"):
            with self.subTest(key=key):
                self.assertTrue(body[key])

    def test_load_refuses_a_missing_freeze(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(FreezeError) as caught:
                load(Path(raw) / "absent.json")
            self.assertIn("no freeze recorded", str(caught.exception))

    def test_write_then_load_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "freeze.json"
            body = write(target)
            self.assertEqual(load(target), body)
            self.assertEqual(load(target)["evaluator_hash"], evaluator_digest())

    def test_write_does_not_touch_the_packaged_freeze(self) -> None:
        before = FREEZE_PATH.read_bytes()
        with tempfile.TemporaryDirectory() as raw:
            write(Path(raw) / "freeze.json")
        self.assertEqual(FREEZE_PATH.read_bytes(), before)

    def test_the_written_file_is_sorted_by_declaration_not_alphabetically(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "freeze.json"
            write(target)
            text = target.read_text(encoding="utf-8")
            self.assertLess(text.index('"phase"'), text.index('"source_hash"'))
