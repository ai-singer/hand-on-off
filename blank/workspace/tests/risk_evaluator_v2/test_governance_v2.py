"""Governance for the Phase 7.5 artefacts.

Phase 7.5 added a taxonomy, an evaluator and two benchmark versions. Everything
it added has to obey the Phase 7.4 rules: versions are never rewritten, a
contaminated benchmark is reported rather than quietly fixed, and a freeze is
taken only over a dataset that passed its own audit.
"""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from risk_evaluation import benchmark_audit, benchmark_registry
from risk_evaluation.benchmark_audit import FAIL, PASS
from risk_evaluation.benchmark_registry import (
    ANNOTATION_PROTOCOL_V2,
    ANNOTATION_VERSION_V2,
    BenchmarkRegistry,
)
from risk_evaluation.benchmark_v2 import V3_CASES, decontaminated_v3_cases
from risk_evaluation.release_freeze import (
    FROZEN_VERSION_SCOPE,
    all_benchmarks_hash,
    load_evaluation_freeze,
    verify_evaluation_freeze,
)
from risk_evaluation.release_freeze_v2 import (
    FREEZE_V2_PATH,
    FREEZE_V2_SCHEMA_VERSION,
    GOVERNED_BENCHMARK,
    MEASURED_BENCHMARK,
    VERIFIED_KEYS,
    EvaluationFreezeV2Error,
    benchmark_hash,
    evaluator_hash,
    load_evaluation_freeze as load_freeze_v2,
    taxonomy_hash,
    verify_evaluation_freeze as verify_freeze_v2,
)


class RegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = BenchmarkRegistry()

    def test_all_four_versions_are_registered(self) -> None:
        keys = {
            f"{record.benchmark_id}/{record.version}"
            for record in self.registry.list_benchmarks()
        }

        self.assertEqual(
            keys, {"semantic/v1", "semantic/v2", "semantic/v3", "semantic/v4"}
        )

    def test_every_exported_benchmark_verifies_against_its_manifest(self) -> None:
        self.assertEqual(set(self.registry.verify_all().values()), {True})

    def test_v3_is_registered_as_contaminated(self) -> None:
        self.assertEqual(self.registry.get("semantic", "v3").status, "contaminated")

    def test_v4_is_registered_as_frozen(self) -> None:
        self.assertEqual(self.registry.get("semantic", "v4").status, "frozen")

    def test_v1_and_v2_keep_their_recorded_status(self) -> None:
        self.assertEqual(self.registry.get("semantic", "v1").status, "contaminated")
        self.assertEqual(self.registry.get("semantic", "v2").status, "frozen")

    def test_v3_and_v4_record_the_v2_annotation_protocol(self) -> None:
        for version in ("v3", "v4"):
            record = self.registry.get("semantic", version)

            self.assertEqual(record.annotation_version, ANNOTATION_VERSION_V2)
            self.assertEqual(record.annotation_protocol, ANNOTATION_PROTOCOL_V2)

    def test_exported_case_counts_match_the_source_data(self) -> None:
        self.assertEqual(
            self.registry.get("semantic", "v3").case_count, len(V3_CASES)
        )
        self.assertEqual(
            self.registry.get("semantic", "v4").case_count,
            len(decontaminated_v3_cases()),
        )

    def test_v3_and_v4_have_distinct_dataset_hashes(self) -> None:
        self.assertNotEqual(
            self.registry.get("semantic", "v3").dataset_hash,
            self.registry.get("semantic", "v4").dataset_hash,
        )

    def test_exported_records_round_trip(self) -> None:
        for version in ("v3", "v4"):
            record = self.registry.get("semantic", version)
            records = self.registry.load_records(record)

            self.assertEqual(len(records), record.case_count)
            for entry in records:
                self.assertIn("statement_source", entry)
                self.assertIn("certainty_level", entry)


class ContaminationAuditTests(unittest.TestCase):
    """The audit that caught v3, and the reason v4 exists."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = BenchmarkRegistry()

    def _audit(self, version: str):
        return benchmark_audit.audit_benchmark(
            self.registry.get("semantic", version), self.registry
        )

    def test_v3_fails_with_exactly_the_development_overlaps(self) -> None:
        report = self._audit("v3")

        self.assertEqual(report.status, FAIL)
        self.assertEqual(len(report.findings), 32)
        self.assertEqual(report.counts()["development_overlap"], 32)
        self.assertEqual(report.counts()["exact_duplicate"], 0)
        self.assertEqual(report.counts()["near_duplicate"], 0)

    def test_v4_passes_cleanly(self) -> None:
        report = self._audit("v4")

        self.assertEqual(report.status, PASS)
        self.assertEqual(report.findings, ())

    def test_v1_still_fails_and_v2_still_passes(self) -> None:
        """The Phase 7.4 findings are unchanged by Phase 7.5."""

        self.assertEqual(self._audit("v1").status, FAIL)
        self.assertEqual(len(self._audit("v1").findings), 38)
        self.assertEqual(self._audit("v2").status, PASS)

    def test_the_contaminated_set_is_exactly_what_v4_removes(self) -> None:
        report = self._audit("v3")
        removed = {case.case_id for case in V3_CASES} - {
            case.case_id for case in decontaminated_v3_cases()
        }

        self.assertEqual(removed, set(report.affected_case_ids))

    def test_v3_was_not_repaired_after_measurement(self) -> None:
        """The rule Phase 7.4 set: do not delete cases after seeing results."""

        self.assertEqual(self.registry.get("semantic", "v3").case_count, 120)
        self.assertEqual(len(V3_CASES), 120)


class FreezeV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frozen = load_freeze_v2()
        cls.registry = BenchmarkRegistry()

    def test_freeze_file_exists(self) -> None:
        self.assertTrue(FREEZE_V2_PATH.is_file())

    def test_freeze_carries_every_required_component(self) -> None:
        for key in (
            "freeze_schema_version",
            "evaluator_hash",
            "taxonomy_hash",
            "benchmark_hash",
            "annotation_version",
            "config_hash",
            "timestamp",
        ):
            self.assertIn(key, self.frozen, key)

    def test_freeze_declares_the_v2_schema(self) -> None:
        self.assertEqual(self.frozen["freeze_schema_version"], FREEZE_V2_SCHEMA_VERSION)

    def test_hashes_are_sha256_digests(self) -> None:
        for key in ("evaluator_hash", "taxonomy_hash", "benchmark_hash", "config_hash"):
            digest = self.frozen[key]

            self.assertEqual(len(digest), 64, key)
            int(digest, 16)

    def test_annotation_version_is_recorded(self) -> None:
        self.assertEqual(self.frozen["annotation_version"], "2.0.0")

    def test_annotation_protocol_names_the_v2_guide(self) -> None:
        self.assertIn("RISK_ANNOTATION_GUIDE_v2.md", self.frozen["annotation_protocol"])

    def test_the_governed_benchmark_is_the_clean_one(self) -> None:
        self.assertEqual(self.frozen["governed_benchmark"], GOVERNED_BENCHMARK)
        self.assertEqual(GOVERNED_BENCHMARK, "semantic/v4")

    def test_the_measured_benchmark_is_recorded_separately(self) -> None:
        self.assertEqual(self.frozen["measured_benchmark"], MEASURED_BENCHMARK)
        self.assertEqual(MEASURED_BENCHMARK, "semantic/v3")

    def test_the_freeze_records_the_status_of_both_benchmarks(self) -> None:
        benchmarks = self.frozen["benchmarks"]

        self.assertEqual(benchmarks[MEASURED_BENCHMARK]["status"], "contaminated")
        self.assertEqual(benchmarks[GOVERNED_BENCHMARK]["status"], "frozen")
        self.assertEqual(benchmarks[MEASURED_BENCHMARK]["case_count"], 120)
        self.assertEqual(benchmarks[GOVERNED_BENCHMARK]["case_count"], 88)

    def test_current_state_matches_the_recorded_freeze(self) -> None:
        result = verify_freeze_v2()

        self.assertTrue(result.matches, result.render())
        self.assertEqual(result.mismatches, ())

    def test_render_states_the_outcome(self) -> None:
        self.assertIn("MATCH", verify_freeze_v2().render())

    def test_a_tampered_hash_is_detected(self) -> None:
        tampered = copy.deepcopy(load_freeze_v2())
        tampered["evaluator_hash"] = "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "freeze_v2.json"
            target.write_text(json.dumps(tampered), encoding="utf-8")

            result = verify_freeze_v2(target)

        self.assertFalse(result.matches)
        self.assertEqual(result.mismatches, ("evaluator_hash",))

    def test_an_annotation_change_is_detected(self) -> None:
        tampered = copy.deepcopy(load_freeze_v2())
        tampered["annotation_version"] = "1.0.0"
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "freeze_v2.json"
            target.write_text(json.dumps(tampered), encoding="utf-8")

            result = verify_freeze_v2(target)

        self.assertIn("annotation_version", result.mismatches)

    def test_timestamp_is_excluded_from_verification(self) -> None:
        tampered = copy.deepcopy(load_freeze_v2())
        tampered["timestamp"] = "1999-01-01T00:00:00Z"
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "freeze_v2.json"
            target.write_text(json.dumps(tampered), encoding="utf-8")

            self.assertTrue(verify_freeze_v2(target).matches)

    def test_missing_freeze_is_reported(self) -> None:
        with self.assertRaises(EvaluationFreezeV2Error):
            load_freeze_v2(Path(tempfile.gettempdir()) / "no-such-freeze-v2.json")

    def test_verified_keys_are_the_ones_that_matter(self) -> None:
        self.assertEqual(
            set(VERIFIED_KEYS),
            {
                "evaluator_hash",
                "taxonomy_hash",
                "benchmark_hash",
                "annotation_version",
                "config_hash",
            },
        )


class FreezeComponentTests(unittest.TestCase):
    def test_evaluator_hash_is_stable(self) -> None:
        self.assertEqual(evaluator_hash(), evaluator_hash())

    def test_taxonomy_hash_is_stable(self) -> None:
        self.assertEqual(taxonomy_hash(), taxonomy_hash())

    def test_the_four_hashes_are_mutually_distinct(self) -> None:
        from risk_evaluation.release_freeze_v2 import config_hash

        digests = {
            evaluator_hash(),
            taxonomy_hash(),
            benchmark_hash(),
            config_hash(),
        }

        self.assertEqual(len(digests), 4)

    def test_benchmark_hash_covers_the_declared_scope(self) -> None:
        remaining = set(benchmark_registry.BENCHMARK_STATUS) - {
            ("semantic", "v3"),
            ("semantic", "v4"),
        }

        self.assertEqual(remaining, {("semantic", "v1"), ("semantic", "v2")})
        self.assertNotEqual(benchmark_hash(), all_benchmarks_hash())

    def test_benchmark_hash_changes_when_the_scope_changes(self) -> None:
        self.assertNotEqual(
            benchmark_hash(versions=("semantic/v4",)),
            benchmark_hash(versions=("semantic/v3",)),
        )


class HistoricalFreezeTests(unittest.TestCase):
    """Phase 7.5 registered two versions; the Phase 7.4 freeze must survive."""

    def test_the_v1_freeze_still_verifies(self) -> None:
        result = verify_evaluation_freeze()

        self.assertTrue(result.matches, result.render())

    def test_the_v1_freeze_hash_is_unchanged(self) -> None:
        """The recorded digest cannot have moved: nothing was rewritten."""

        self.assertEqual(
            load_evaluation_freeze()["benchmark_hash"],
            "401983f377e28a9aea368fbfaaae551dc59d86d13278a8134fef7c7a318ab197",
        )

    def test_the_v1_scope_names_only_the_versions_it_covered(self) -> None:
        self.assertEqual(FROZEN_VERSION_SCOPE, ("semantic/v1", "semantic/v2"))

    def test_the_two_freezes_are_different_files(self) -> None:
        self.assertNotEqual(
            load_evaluation_freeze()["benchmark_hash"],
            load_freeze_v2()["benchmark_hash"],
        )

    def test_the_v1_freeze_does_not_mention_the_phase_7_5_evaluator(self) -> None:
        self.assertNotIn("evaluator_name", load_evaluation_freeze())

    def test_the_v2_freeze_does_not_rewrite_the_v1_evaluator_hash(self) -> None:
        self.assertNotEqual(
            load_evaluation_freeze()["evaluator_hash"],
            load_freeze_v2()["evaluator_hash"],
        )


if __name__ == "__main__":
    unittest.main()
