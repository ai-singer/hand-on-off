"""The generated cases as a registry benchmark, and what governance says of it.

`semantic/adversarial/v1` is a normal registered version: it has a manifest, a
hash, a status, a baseline and a contamination audit result. Being generated
rather than hand-authored does not exempt it from any of that.
"""

from __future__ import annotations

import json
import unittest

from risk_evaluation import benchmark_audit, benchmark_registry
from risk_evaluation.benchmark_audit import PASS
from risk_evaluation.benchmark_registry import (
    ADVERSARIAL_ANNOTATION_PROTOCOL,
    ADVERSARIAL_BENCHMARK,
    ADVERSARIAL_VERSION,
    BenchmarkRegistry,
)
from risk_evaluation.adversarial.generator import (
    attack_counts,
    control_counts,
    default_cases,
)
from risk_evaluation.adversarial.strategies import REQUIRED_ATTACKS
from risk_evaluation.regression import EVALUATORS, load_baseline


class RegistryEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = BenchmarkRegistry()
        cls.record = cls.registry.get(ADVERSARIAL_BENCHMARK, ADVERSARIAL_VERSION)

    def test_the_benchmark_is_registered(self) -> None:
        self.assertEqual(self.record.benchmark_id, "semantic/adversarial")
        self.assertEqual(self.record.version, "v1")

    def test_it_holds_the_generated_cases(self) -> None:
        self.assertEqual(self.record.case_count, len(default_cases()))

    def test_it_is_frozen(self) -> None:
        self.assertEqual(self.record.status, "frozen")

    def test_it_records_the_adversarial_annotation_protocol(self) -> None:
        self.assertEqual(
            self.record.annotation_protocol, ADVERSARIAL_ANNOTATION_PROTOCOL
        )

    def test_provenance_names_phase_8_1(self) -> None:
        self.assertIn("phase-8.1", self.record.created_by)

    def test_the_directory_is_nested_under_the_namespaced_id(self) -> None:
        self.assertEqual(
            self.registry.directory(self.record)
            .relative_to(self.registry.root)
            .parts,
            ("semantic", "adversarial", "v1"),
        )

    def test_the_dataset_hash_matches_the_exported_cases(self) -> None:
        records = self.registry.load_records(self.record)

        self.assertEqual(
            benchmark_registry.dataset_hash(records), self.record.dataset_hash
        )

    def test_registering_it_did_not_move_any_existing_hash(self) -> None:
        """The Phase 7.4/7.5 datasets are unchanged by Phase 8.1."""

        expected = {
            ("semantic", "v1"): "950428a98d52fad3",
            ("semantic", "v2"): "c01fe03efe22c441",
            ("semantic", "v3"): "1432cda8ed1d7fc4",
            ("semantic", "v4"): "8765b6fec4a115a9",
        }
        for key, digest in expected.items():
            self.assertTrue(
                self.registry.get(*key).dataset_hash.startswith(digest), str(key)
            )

    def test_records_carry_the_adversarial_fields(self) -> None:
        for record in self.registry.load_records(self.record):
            self.assertIn("attack_strategy", record)
            self.assertIn("expected_detection", record)

    def test_the_exported_group_counts_split_attacks_from_controls(self) -> None:
        self.assertEqual(
            dict(self.record.group_counts), {"attack": 60, "control": 13}
        )

    def test_the_export_is_deterministic(self) -> None:
        cases = default_cases()
        records = self.registry.load_records(self.record)

        self.assertEqual(
            [record["id"] for record in records], [case.case_id for case in cases]
        )

    def test_labels_index_every_case(self) -> None:
        labels = self.registry.load_labels(self.record)

        self.assertEqual(len(labels["by_case"]), len(default_cases()))


class BenchmarkCompositionTests(unittest.TestCase):
    """The Phase 8.1 composition requirement, checked on the exported dataset."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.records = BenchmarkRegistry().load_records(
            BenchmarkRegistry().get(ADVERSARIAL_BENCHMARK, ADVERSARIAL_VERSION)
        )

    def test_at_least_fifty_generated_cases_are_exported(self) -> None:
        self.assertGreaterEqual(len(self.records), 50)

    def test_every_exported_case_states_its_strategy(self) -> None:
        for record in self.records:
            self.assertTrue(record["attack_strategy"], record["id"])

    def test_attack_family_counts_meet_the_requirement(self) -> None:
        cases = default_cases()
        counts = attack_counts(cases)

        for family, required in REQUIRED_ATTACKS.items():
            self.assertGreaterEqual(counts[family], required, family)

    def test_controls_are_exported_alongside_attacks(self) -> None:
        cases = default_cases()

        self.assertEqual(sum(control_counts(cases).values()), 13)

    def test_every_exported_case_names_an_expectation_basis(self) -> None:
        for record in self.records:
            self.assertTrue(record["expectation_basis"], record["id"])

    def test_every_exported_case_is_marked_as_generated(self) -> None:
        for record in self.records:
            self.assertEqual(record["source_type"], "adversarial_generated")


class ContaminationAuditTests(unittest.TestCase):
    """The generated set is audited like any other benchmark."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = BenchmarkRegistry()
        cls.report = benchmark_audit.audit_benchmark(
            cls.registry.get(ADVERSARIAL_BENCHMARK, ADVERSARIAL_VERSION), cls.registry
        )

    def test_the_generated_benchmark_passes_its_audit(self) -> None:
        self.assertEqual(self.report.status, PASS, self.report.render())

    def test_it_has_no_duplicate_cases(self) -> None:
        counts = self.report.counts()

        self.assertEqual(counts["exact_duplicate"], 0)
        self.assertEqual(counts["near_duplicate"], 0)

    def test_it_does_not_overlap_the_evaluator_development_set(self) -> None:
        """Generated attacks are new text, not recycled examples."""

        self.assertEqual(self.report.counts()["development_overlap"], 0)

    def test_the_auditor_still_fails_the_contaminated_versions(self) -> None:
        """Phase 8.1 did not weaken the audit for anyone else."""

        for version, expected in (("v1", 38), ("v3", 32)):
            report = benchmark_audit.audit_benchmark(
                self.registry.get("semantic", version), self.registry
            )
            self.assertEqual(len(report.findings), expected, version)

    def test_every_registered_benchmark_is_still_auditable(self) -> None:
        reports = benchmark_audit.audit_all(self.registry)

        self.assertEqual(len(reports), len(self.registry.list_benchmarks()))


class BaselineTests(unittest.TestCase):
    def test_the_generated_benchmark_has_a_recorded_baseline(self) -> None:
        registry = BenchmarkRegistry()
        record = registry.get(ADVERSARIAL_BENCHMARK, ADVERSARIAL_VERSION)
        baseline = load_baseline(record, registry)

        self.assertEqual(set(baseline["evaluators"]), set(EVALUATORS))

    def test_the_baseline_is_bound_to_the_dataset_hash(self) -> None:
        registry = BenchmarkRegistry()
        record = registry.get(ADVERSARIAL_BENCHMARK, ADVERSARIAL_VERSION)
        baseline = load_baseline(record, registry)

        for entry in baseline["evaluators"].values():
            self.assertEqual(entry["dataset_hash"], record.dataset_hash)

    def test_the_baseline_records_a_score_for_every_case(self) -> None:
        registry = BenchmarkRegistry()
        record = registry.get(ADVERSARIAL_BENCHMARK, ADVERSARIAL_VERSION)
        baseline = load_baseline(record, registry)

        for entry in baseline["evaluators"].values():
            self.assertEqual(len(entry["case_results"]), record.case_count)

    def test_the_recorded_baseline_is_json(self) -> None:
        registry = BenchmarkRegistry()
        record = registry.get(ADVERSARIAL_BENCHMARK, ADVERSARIAL_VERSION)
        path = registry.directory(record) / "baseline.json"

        json.loads(path.read_text(encoding="utf-8"))


class ExportIntegrityTests(unittest.TestCase):
    def test_verify_all_passes_for_every_version(self) -> None:
        self.assertEqual(set(BenchmarkRegistry().verify_all().values()), {True})

    def test_the_manifest_declares_both_groups(self) -> None:
        registry = BenchmarkRegistry()
        record = registry.get(ADVERSARIAL_BENCHMARK, ADVERSARIAL_VERSION)

        self.assertEqual(set(record.group_counts), {"attack", "control"})

    def test_the_source_names_the_producing_phase(self) -> None:
        registry = BenchmarkRegistry()
        record = registry.get(ADVERSARIAL_BENCHMARK, ADVERSARIAL_VERSION)

        self.assertIn("phase-8.1", record.source)

    def test_the_freeze_hash_scope_is_unaffected(self) -> None:
        """Phase 8.1 added no version to either recorded freeze."""

        from risk_evaluation.release_freeze import FROZEN_VERSION_SCOPE

        self.assertNotIn("semantic/adversarial/v1", FROZEN_VERSION_SCOPE)


if __name__ == "__main__":
    unittest.main()
