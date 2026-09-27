from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from risk_evaluation.benchmark_registry import BenchmarkRegistry
from risk_evaluation.release_freeze import (
    EVALUATION_CONFIG,
    FREEZE_PATH,
    EvaluationFreezeError,
    benchmark_hash,
    build_freeze,
    config_hash,
    evaluator_hash,
    load_evaluation_freeze,
    taxonomy_hash,
    verify_evaluation_freeze,
    write_evaluation_freeze,
)


class FreezeFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frozen = load_evaluation_freeze()

    def test_freeze_file_exists(self) -> None:
        self.assertTrue(FREEZE_PATH.is_file())

    def test_freeze_carries_every_required_hash(self) -> None:
        for key in (
            "freeze_schema_version",
            "evaluator_hash",
            "taxonomy_hash",
            "benchmark_hash",
            "config_hash",
            "timestamp",
        ):
            self.assertIn(key, self.frozen, key)

    def test_hashes_are_sha256_digests(self) -> None:
        for key in ("evaluator_hash", "taxonomy_hash", "benchmark_hash", "config_hash"):
            digest = self.frozen[key]
            self.assertEqual(len(digest), 64, key)
            int(digest, 16)

    def test_timestamp_is_iso8601_utc(self) -> None:
        stamp = self.frozen["timestamp"]

        self.assertRegex(stamp, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_missing_freeze_is_reported(self) -> None:
        with self.assertRaises(EvaluationFreezeError):
            load_evaluation_freeze(Path(tempfile.gettempdir()) / "no-such-freeze.json")


class FreezeVerificationTests(unittest.TestCase):
    def test_current_state_matches_the_recorded_freeze(self) -> None:
        result = verify_evaluation_freeze()

        self.assertTrue(result.matches, result.render())
        self.assertEqual(result.mismatches, ())

    def test_a_tampered_hash_is_detected(self) -> None:
        tampered = copy.deepcopy(load_evaluation_freeze())
        tampered["evaluator_hash"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "freeze.json"
            target.write_text(json.dumps(tampered), encoding="utf-8")

            result = verify_evaluation_freeze(target)

        self.assertFalse(result.matches)
        self.assertEqual(result.mismatches, ("evaluator_hash",))

    def test_multiple_mismatches_are_all_reported(self) -> None:
        tampered = copy.deepcopy(load_evaluation_freeze())
        tampered["evaluator_hash"] = "0" * 64
        tampered["config_hash"] = "1" * 64
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "freeze.json"
            target.write_text(json.dumps(tampered), encoding="utf-8")

            result = verify_evaluation_freeze(target)

        self.assertEqual(set(result.mismatches), {"evaluator_hash", "config_hash"})

    def test_render_states_the_outcome(self) -> None:
        self.assertIn("MATCH", verify_evaluation_freeze().render())

    def test_timestamp_is_excluded_from_verification(self) -> None:
        tampered = copy.deepcopy(load_evaluation_freeze())
        tampered["timestamp"] = "1999-01-01T00:00:00Z"
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "freeze.json"
            target.write_text(json.dumps(tampered), encoding="utf-8")

            result = verify_evaluation_freeze(target)

        self.assertTrue(result.matches)


class FreezeComponentTests(unittest.TestCase):
    def test_evaluator_hash_is_stable(self) -> None:
        self.assertEqual(evaluator_hash(), evaluator_hash())

    def test_evaluator_hash_covers_the_keyword_rules(self) -> None:
        """The keyword evaluator's behaviour lives in its plugin rule file."""

        from risk_evaluation.release_freeze import KEYWORD_RULES

        payload = json.loads(KEYWORD_RULES.read_text(encoding="utf-8"))

        self.assertTrue(payload["rules"])
        self.assertIn("investment-advice", json.dumps(payload))

    def test_taxonomy_hash_is_stable_and_distinct(self) -> None:
        self.assertEqual(taxonomy_hash(), taxonomy_hash())
        self.assertNotEqual(taxonomy_hash(), config_hash())

    def test_benchmark_hash_covers_exactly_the_declared_scope(self) -> None:
        """A freeze covers the versions it was taken against, not the registry."""

        from risk_evaluation.release_freeze import FROZEN_VERSION_SCOPE, _hash_payload

        registry = BenchmarkRegistry()
        scope = set(FROZEN_VERSION_SCOPE)
        expected = _hash_payload(
            {
                f"{record.benchmark_id}/{record.version}": {
                    "dataset_hash": record.dataset_hash,
                    "case_count": record.case_count,
                    "status": record.status,
                }
                for record in registry.list_benchmarks()
                if f"{record.benchmark_id}/{record.version}" in scope
            }
        )

        self.assertEqual(benchmark_hash(registry), expected)

    def test_a_later_registered_version_does_not_move_the_scoped_hash(self) -> None:
        """Phase 7.5 added semantic/v3 and v4 after this freeze was recorded.

        Registering a benchmark must not retroactively invalidate an older
        freeze, or history stops being verifiable the moment the project grows.
        """

        from risk_evaluation.release_freeze import all_benchmarks_hash

        registry = BenchmarkRegistry()
        registered = {f"{r.benchmark_id}/{r.version}" for r in registry.list_benchmarks()}

        self.assertTrue({"semantic/v3", "semantic/v4"} <= registered)
        self.assertNotEqual(benchmark_hash(registry), all_benchmarks_hash(registry))
        self.assertEqual(
            benchmark_hash(registry), load_evaluation_freeze()["benchmark_hash"]
        )

    def test_every_registered_benchmark_is_covered_by_a_full_registry_hash(self) -> None:
        from risk_evaluation.release_freeze import _hash_payload, all_benchmarks_hash

        registry = BenchmarkRegistry()
        expected = _hash_payload(
            {
                f"{record.benchmark_id}/{record.version}": {
                    "dataset_hash": record.dataset_hash,
                    "case_count": record.case_count,
                    "status": record.status,
                }
                for record in registry.list_benchmarks()
            }
        )

        self.assertEqual(all_benchmarks_hash(registry), expected)

    def test_config_hash_covers_the_governance_parameters(self) -> None:
        from risk_evaluation.release_freeze import _hash_payload

        self.assertEqual(config_hash(), _hash_payload(EVALUATION_CONFIG))

    def test_config_records_the_governance_decisions(self) -> None:
        for key in (
            "annotation_version",
            "annotation_protocol",
            "near_duplicate_threshold",
            "primary_metric",
            "regression_tolerance",
            "benchmark_versions",
        ):
            self.assertIn(key, EVALUATION_CONFIG)

    def test_config_lists_both_benchmark_versions(self) -> None:
        self.assertEqual(
            set(EVALUATION_CONFIG["benchmark_versions"]), {"semantic/v1", "semantic/v2"}
        )

    def test_build_freeze_contains_all_four_hashes(self) -> None:
        payload = build_freeze()

        self.assertEqual(
            set(payload),
            {
                "freeze_schema_version",
                "evaluator_hash",
                "taxonomy_hash",
                "benchmark_hash",
                "config_hash",
                "timestamp",
            },
        )
        self.assertEqual(payload["evaluator_hash"], evaluator_hash())

    def test_write_and_verify_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "evaluation_freeze.json"

            write_evaluation_freeze(target)
            result = verify_evaluation_freeze(target)

        self.assertTrue(result.matches)

    def test_hash_components_are_mutually_distinct(self) -> None:
        digests = {evaluator_hash(), taxonomy_hash(), benchmark_hash(), config_hash()}

        self.assertEqual(len(digests), 4)


if __name__ == "__main__":
    unittest.main()
